from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import mfa
from ..audit import log_action
from ..config import settings
from ..db import get_db
from ..deps import client_ip, get_current_staff
from ..models import MagicToken, Member, StaffUser
from ..notifications.email_service import send_email
from ..notifications.sms_service import send_sms
from ..notifications.templates import (
    screening_invite_email_body,
    screening_invite_email_subject,
    screening_invite_sms,
)
from ..schemas import MagicLinkByPhone, MagicLinkRequest, MagicLinkVerify, MfaCode, MfaVerify, StaffLogin
from ..security import (
    create_jwt,
    decode_jwt,
    generate_magic_token,
    hash_magic_token,
    magic_token_expiry,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Brute-force protection for staff logins: after this many consecutive failures,
# lock the account for the cooldown window. Short/time-based (not permanent) so a
# guessing attacker can't trivially deny service to a legitimate user forever.
import logging

logger = logging.getLogger("auth")

MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15
MFA_CHALLENGE_TTL_MINUTES = 5


def _deliver_magic_link(member: Member, link: str) -> None:
    """Best-effort magic-link delivery: try SMS (if the member prefers it and a
    number is provisioned), otherwise/failing that, email. Delivery problems must
    never break the identity flow — the token is already persisted, so we log and
    move on rather than 500. Mirrors the graceful-degradation approach in
    outreach_service."""
    prefers_sms = member.preferred_channel == "sms" and member.consent_sms and bool(member.phone)
    try:
        if prefers_sms and send_sms(member.phone, screening_invite_sms("Your health plan", link)):
            return  # SMS delivered
    except Exception:
        logger.warning("magic-link SMS delivery failed; falling back to email", exc_info=True)
    try:
        if member.consent_email and member.email:
            send_email(
                member.email,
                screening_invite_email_subject("Your health plan"),
                screening_invite_email_body("Your health plan", member.first_name, link),
            )
    except Exception:
        logger.warning("magic-link email delivery failed", exc_info=True)


@router.post("/staff/login")
async def staff_login(body: StaffLogin, request: Request, db: AsyncSession = Depends(get_db)):
    ip = client_ip(request)
    now = datetime.utcnow()
    res = await db.execute(select(StaffUser).where(StaffUser.email == body.email))
    user = res.scalar_one_or_none()

    if user is not None and user.locked_until is not None and user.locked_until > now:
        await log_action(
            db, actor_type="staff", actor_id=user.id, action="login_locked",
            tenant_id=user.tenant_id, ip_address=ip,
        )
        raise HTTPException(
            status_code=429,
            detail="Account temporarily locked after too many failed attempts. Try again later.",
        )

    if user is None or not verify_password(body.password, user.password_hash):
        if user is not None:
            user.failed_login_count += 1
            if user.failed_login_count >= MAX_FAILED_LOGINS:
                user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
                user.failed_login_count = 0
            await log_action(
                db, actor_type="staff", actor_id=user.id, action="login_failed",
                tenant_id=user.tenant_id, ip_address=ip,
                metadata={"locked": user.locked_until is not None and user.locked_until > now},
            )
        # Same 401 whether the email is unknown or the password is wrong.
        raise HTTPException(401, "Invalid email or password")

    # Password OK — clear any accumulated failures / lock.
    user.failed_login_count = 0
    user.locked_until = None

    # If MFA is on, the password is only the first factor: hand back a short-lived
    # challenge token, not a full session, until the TOTP code is verified.
    if user.mfa_enabled and user.mfa_secret:
        mfa_token = create_jwt(
            user.id,
            {"kind": "mfa_pending", "tenant_id": user.tenant_id},
            expires_delta=timedelta(minutes=MFA_CHALLENGE_TTL_MINUTES),
        )
        await log_action(
            db, actor_type="staff", actor_id=user.id, action="login_mfa_challenge",
            tenant_id=user.tenant_id, ip_address=ip,
        )
        return {"mfa_required": True, "mfa_token": mfa_token}

    token = create_jwt(user.id, {"kind": "staff", "role": user.role, "tenant_id": user.tenant_id})
    await log_action(
        db,
        actor_type="staff",
        actor_id=user.id,
        action="login",
        tenant_id=user.tenant_id,
        ip_address=ip,
    )
    return {"token": token, "role": user.role, "name": user.name, "tenant_id": user.tenant_id}


@router.post("/staff/mfa/verify")
async def staff_mfa_verify(body: MfaVerify, request: Request, db: AsyncSession = Depends(get_db)):
    """Second factor: exchange a valid challenge token + current TOTP code for a
    full staff session."""
    ip = client_ip(request)
    try:
        claims = decode_jwt(body.mfa_token)
    except Exception:
        raise HTTPException(401, "Your sign-in session expired — please sign in again")
    if claims.get("kind") != "mfa_pending":
        raise HTTPException(401, "Invalid MFA session")
    user = await db.get(StaffUser, claims["sub"])
    if user is None or not user.mfa_enabled or not user.mfa_secret:
        raise HTTPException(401, "MFA is not set up for this account")

    if not mfa.verify(user.mfa_secret, body.code):
        await log_action(
            db, actor_type="staff", actor_id=user.id, action="login_mfa_failed",
            tenant_id=user.tenant_id, ip_address=ip,
        )
        raise HTTPException(401, "Invalid authentication code")

    token = create_jwt(user.id, {"kind": "staff", "role": user.role, "tenant_id": user.tenant_id})
    await log_action(
        db, actor_type="staff", actor_id=user.id, action="login",
        tenant_id=user.tenant_id, ip_address=ip, metadata={"mfa": True},
    )
    return {"token": token, "role": user.role, "name": user.name, "tenant_id": user.tenant_id}


@router.get("/staff/mfa/status")
async def staff_mfa_status(staff: StaffUser = Depends(get_current_staff)):
    return {"mfa_enabled": staff.mfa_enabled}


@router.post("/staff/mfa/enroll")
async def staff_mfa_enroll(
    staff: StaffUser = Depends(get_current_staff), db: AsyncSession = Depends(get_db)
):
    """Start enrollment: mint a secret and return the otpauth URI to scan. MFA is
    NOT active until the user confirms a code, so this is safe to re-run."""
    if staff.mfa_enabled:
        raise HTTPException(409, "MFA is already enabled")
    secret = mfa.generate_secret()
    staff.mfa_secret = secret
    await db.commit()
    return {"secret": secret, "otpauth_uri": mfa.provisioning_uri(secret, staff.email)}


@router.post("/staff/mfa/confirm")
async def staff_mfa_confirm(
    body: MfaCode,
    request: Request,
    staff: StaffUser = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
):
    if staff.mfa_enabled:
        raise HTTPException(409, "MFA is already enabled")
    if not staff.mfa_secret or not mfa.verify(staff.mfa_secret, body.code):
        raise HTTPException(400, "That code didn't match — check your authenticator app and try again")
    staff.mfa_enabled = True
    await log_action(
        db, actor_type="staff", actor_id=staff.id, action="mfa_enabled",
        tenant_id=staff.tenant_id, ip_address=client_ip(request),
    )
    return {"mfa_enabled": True}


@router.post("/staff/mfa/disable")
async def staff_mfa_disable(
    body: MfaCode,
    request: Request,
    staff: StaffUser = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
):
    """Turn off MFA — requires a current code so a hijacked session can't silently
    strip the second factor."""
    if not staff.mfa_enabled:
        return {"mfa_enabled": False}
    if not staff.mfa_secret or not mfa.verify(staff.mfa_secret, body.code):
        raise HTTPException(400, "That code didn't match — MFA is still enabled")
    staff.mfa_enabled = False
    staff.mfa_secret = None
    await log_action(
        db, actor_type="staff", actor_id=staff.id, action="mfa_disabled",
        tenant_id=staff.tenant_id, ip_address=client_ip(request),
    )
    return {"mfa_enabled": False}


def _normalize_phone(raw: str) -> str:
    """Best-effort E.164 for US numbers so a member typing (555) 000-1005 matches
    a stored +15550001005. Rosters should store E.164 for this to line up."""
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    if raw.strip().startswith("+"):
        return "+" + digits
    return digits


async def _issue_magic_link(db: AsyncSession, member: Member, request: Request) -> dict:
    """Mint + deliver a single-use magic link for a found member. Shared by the
    by-ID and by-phone entry points."""
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

    link = f"{settings.app_base_url}/verify?token={raw_token}"
    _deliver_magic_link(member, link)

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


@router.post("/member/magic")
async def request_magic_link(body: MagicLinkRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Two-factor identity check (member id + DOB) before issuing a magic link —
    prevents enumerating members by external ID alone."""
    member = (
        await db.execute(
            select(Member).where(
                Member.external_member_id == body.external_member_id,
                Member.date_of_birth == body.date_of_birth,
            )
        )
    ).scalars().first()
    if member is None:
        # Same response whether or not the member exists, to avoid leaking enrollment.
        return {"sent": True}
    return await _issue_magic_link(db, member, request)


@router.post("/member/magic-by-phone")
async def request_magic_link_by_phone(
    body: MagicLinkByPhone, request: Request, db: AsyncSession = Depends(get_db)
):
    """Alternative for members without their member ID: phone + DOB. Works because
    phone/DOB are deterministically encrypted, so an equality lookup still
    matches. Same enumeration-safe response as the by-ID path."""
    member = (
        await db.execute(
            select(Member).where(
                Member.phone == _normalize_phone(body.phone),
                Member.date_of_birth == body.date_of_birth,
            )
        )
    ).scalars().first()
    if member is None:
        return {"sent": True}
    return await _issue_magic_link(db, member, request)


@router.post("/member/verify")
async def verify_magic_link(
    body: MagicLinkVerify, request: Request, db: AsyncSession = Depends(get_db)
):
    """Exchange a magic-link token for a member session.

    Idempotent inside `magic_reuse_grace_minutes` of first use. The token is
    still single-use against later replay (a link harvested from the mailbox
    days after the member used it fails), but a link scanner's hit — or a
    double-tap — no longer locks the member out of their own link.

    Every attempt is audited with the reason, because this failure has only ever
    been diagnosed by speculation. `used_age_seconds` on a rejection is the
    tell: a few seconds means a scanner/double-tap raced the member (widen the
    grace); hours means the link was detonated at delivery (needs a different
    fix — see docs/RECONCILE_AND_HARDEN.md item 5).
    """
    token_hash = hash_magic_token(body.token)
    res = await db.execute(select(MagicToken).where(MagicToken.token_hash == token_hash))
    magic = res.scalar_one_or_none()
    now = datetime.utcnow()
    ip = client_ip(request)

    if magic is None or magic.expires_at < now:
        await log_action(
            db,
            actor_type="member",
            action="magic_verify_rejected",
            resource_type="magic_token",
            resource_id=magic.id if magic else "",
            ip_address=ip,
            metadata={"reason": "unknown_token" if magic is None else "expired"},
        )
        raise HTTPException(401, "Link is invalid or expired")

    reused = magic.used_at is not None
    if reused:
        used_age = (now - magic.used_at).total_seconds()
        if used_age > settings.magic_reuse_grace_minutes * 60:
            await log_action(
                db,
                actor_type="member",
                actor_id=magic.member_id,
                action="magic_verify_rejected",
                resource_type="magic_token",
                resource_id=magic.id,
                ip_address=ip,
                metadata={"reason": "already_used", "used_age_seconds": int(used_age)},
            )
            raise HTTPException(401, "Link is invalid or expired")

    if not reused:
        # Stamp on FIRST use only — never extend, or repeated hits would hold the
        # grace window open indefinitely.
        magic.used_at = now

    member = await db.get(Member, magic.member_id)
    await log_action(
        db,
        actor_type="member",
        actor_id=member.id,
        action="magic_verify_reused_in_grace" if reused else "magic_verify_ok",
        resource_type="magic_token",
        resource_id=magic.id,
        tenant_id=member.tenant_id,
        ip_address=ip,
    )

    token = create_jwt(member.id, {"kind": "member", "tenant_id": member.tenant_id})
    return {"token": token, "first_name": member.first_name}
