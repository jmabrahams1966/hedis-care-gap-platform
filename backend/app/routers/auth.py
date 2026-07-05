from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import log_action
from ..config import settings
from ..db import get_db
from ..deps import client_ip
from ..models import MagicToken, Member, StaffUser
from ..notifications.email_service import send_email
from ..notifications.sms_service import send_sms
from ..notifications.templates import (
    screening_invite_email_body,
    screening_invite_email_subject,
    screening_invite_sms,
)
from ..schemas import MagicLinkRequest, MagicLinkVerify, StaffLogin
from ..security import create_jwt, generate_magic_token, hash_magic_token, magic_token_expiry, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/staff/login")
async def staff_login(body: StaffLogin, request: Request, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(StaffUser).where(StaffUser.email == body.email))
    user = res.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    token = create_jwt(user.id, {"kind": "staff", "role": user.role, "tenant_id": user.tenant_id})
    await log_action(
        db,
        actor_type="staff",
        actor_id=user.id,
        action="login",
        tenant_id=user.tenant_id,
        ip_address=client_ip(request),
    )
    return {"token": token, "role": user.role, "name": user.name, "tenant_id": user.tenant_id}


@router.post("/member/magic")
async def request_magic_link(body: MagicLinkRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Two-factor identity check (member id + DOB) before issuing a magic link —
    prevents enumerating members by external ID alone."""
    res = await db.execute(
        select(Member).where(
            Member.external_member_id == body.external_member_id,
            Member.date_of_birth == body.date_of_birth,
        )
    )
    member = res.scalar_one_or_none()
    if member is None:
        # Same response whether or not the member exists, to avoid leaking enrollment.
        return {"sent": True}

    raw_token, token_hash = generate_magic_token()
    db.add(
        MagicToken(
            member_id=member.id,
            token_hash=token_hash,
            purpose="screening",
            expires_at=magic_token_expiry(),
        )
    )
    await db.commit()

    link = f"https://app.example.com/verify?token={raw_token}"
    if member.preferred_channel == "sms" and member.consent_sms and member.phone:
        send_sms(member.phone, screening_invite_sms("Your health plan", link))
    elif member.consent_email and member.email:
        send_email(
            member.email,
            screening_invite_email_subject("Your health plan"),
            screening_invite_email_body("Your health plan", member.first_name, link),
        )

    await log_action(
        db,
        actor_type="member",
        actor_id=member.id,
        action="magic_link_requested",
        tenant_id=member.tenant_id,
        ip_address=client_ip(request),
    )

    resp = {"sent": True}
    if settings.dev_mode:
        resp["dev_token"] = raw_token  # never returned outside dev_mode
    return resp


@router.post("/member/verify")
async def verify_magic_link(body: MagicLinkVerify, db: AsyncSession = Depends(get_db)):
    token_hash = hash_magic_token(body.token)
    res = await db.execute(select(MagicToken).where(MagicToken.token_hash == token_hash))
    magic = res.scalar_one_or_none()
    if magic is None or magic.used_at is not None or magic.expires_at < datetime.utcnow():
        raise HTTPException(401, "Link is invalid or expired")

    magic.used_at = datetime.utcnow()
    await db.commit()

    member = await db.get(Member, magic.member_id)
    token = create_jwt(member.id, {"kind": "member", "tenant_id": member.tenant_id})
    return {"token": token, "first_name": member.first_name}
