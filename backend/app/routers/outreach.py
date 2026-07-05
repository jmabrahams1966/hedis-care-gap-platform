from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import require_role
from ..models import CareGap, GapStatus, Member, OutreachAttempt, OutreachStatus, StaffRole, StaffUser, Tenant
from ..notifications.email_service import send_email
from ..notifications.sms_service import send_sms
from ..notifications.templates import (
    screening_invite_email_body,
    screening_invite_email_subject,
    screening_invite_sms,
)
from ..security import generate_magic_token, magic_token_expiry
from ..models import MagicToken

router = APIRouter(prefix="/api/outreach", tags=["outreach"])

_ROLES = (StaffRole.care_manager.value, StaffRole.payer_admin.value, StaffRole.super_admin.value)
RETRY_CADENCE_DAYS = 7


async def _send_to_member(db: AsyncSession, tenant: Tenant, member: Member, gap: CareGap) -> OutreachAttempt:
    raw_token, token_hash = generate_magic_token()
    db.add(
        MagicToken(member_id=member.id, token_hash=token_hash, purpose="screening", expires_at=magic_token_expiry())
    )
    link = f"https://app.example.com/verify?token={raw_token}"

    channel = "sms" if (member.preferred_channel == "sms" and member.consent_sms and member.phone) else "email"
    if channel == "sms":
        message_id = send_sms(member.phone, screening_invite_sms(tenant.name, link))
    elif member.consent_email and member.email:
        message_id = send_email(
            member.email, screening_invite_email_subject(tenant.name), screening_invite_email_body(
                tenant.name, member.first_name, link
            ),
        )
    else:
        attempt = OutreachAttempt(
            care_gap_id=gap.id,
            member_id=member.id,
            channel=member.preferred_channel,
            template_code="screening_invite",
            status=OutreachStatus.failed.value,
            error="No consent on file for any contact channel",
        )
        db.add(attempt)
        return attempt

    attempt = OutreachAttempt(
        care_gap_id=gap.id,
        member_id=member.id,
        channel=channel,
        template_code="screening_invite",
        status=OutreachStatus.sent.value,
        provider_message_id=message_id,
    )
    db.add(attempt)
    return attempt


@router.post("/send/{gap_id}")
async def send_outreach(
    gap_id: str,
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    gap = await db.get(CareGap, gap_id)
    if gap is None or gap.tenant_id != staff.tenant_id:
        raise HTTPException(404, "Not found")
    tenant = await db.get(Tenant, staff.tenant_id)
    member = await db.get(Member, gap.member_id)

    attempt = await _send_to_member(db, tenant, member, gap)
    if attempt.status == OutreachStatus.sent.value:
        gap.status = GapStatus.outreach_sent.value
        gap.last_outreach_at = datetime.utcnow()
        gap.next_outreach_at = datetime.utcnow() + timedelta(days=RETRY_CADENCE_DAYS)
    await db.commit()
    return {"gap_id": gap.id, "outreach_status": attempt.status, "channel": attempt.channel}


@router.post("/run-batch")
async def run_batch(
    staff: StaffUser = Depends(require_role(StaffRole.payer_admin.value, StaffRole.super_admin.value)),
    db: AsyncSession = Depends(get_db),
):
    """Sends outreach for every open gap due for (re)contact. Intended to be invoked
    by a scheduled ECS task / EventBridge rule, not a human — see docs/DEPLOYMENT.md."""
    tenant = await db.get(Tenant, staff.tenant_id)
    now = datetime.utcnow()
    res = await db.execute(
        select(CareGap).where(
            CareGap.tenant_id == staff.tenant_id,
            CareGap.status.in_([GapStatus.open.value, GapStatus.outreach_sent.value]),
            (CareGap.next_outreach_at.is_(None)) | (CareGap.next_outreach_at <= now),
        )
    )
    gaps = res.scalars().all()

    sent = 0
    for gap in gaps:
        member = await db.get(Member, gap.member_id)
        attempt = await _send_to_member(db, tenant, member, gap)
        if attempt.status == OutreachStatus.sent.value:
            gap.status = GapStatus.outreach_sent.value
            gap.last_outreach_at = now
            gap.next_outreach_at = now + timedelta(days=RETRY_CADENCE_DAYS)
            sent += 1
    await db.commit()
    return {"evaluated": len(gaps), "sent": sent}
