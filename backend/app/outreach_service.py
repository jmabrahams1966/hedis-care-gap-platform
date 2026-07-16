"""Outreach sending logic shared between the authenticated API endpoints
(app/routers/outreach.py) and the scheduled batch job (app/scripts/run_outreach_cron.py).
Kept separate from the router so the cron entrypoint doesn't need a fake staff
JWT to call into it.
"""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .measures import REGISTRY
from .models import CareGap, GapStatus, MagicToken, Member, OutreachAttempt, OutreachStatus, Tenant
from .notifications.email_service import send_email
from .notifications.sms_service import send_sms
from .notifications.templates import OUTREACH_TEMPLATES
from .security import generate_magic_token, magic_token_expiry

RETRY_CADENCE_DAYS = 7


async def send_to_member(
    db: AsyncSession,
    tenant: Tenant,
    member: Member,
    gap: CareGap,
    template_override: str | None = None,
    channel_override: str | None = None,
) -> OutreachAttempt:
    """Send one outreach to a member for a gap. `template_override` /
    `channel_override` let the cadence engine (Feature C1) drive a specific
    step's template + channel; both default to the measure/member-preference
    behavior used by the standard retry batch."""
    raw_token, token_hash = generate_magic_token()
    db.add(
        MagicToken(member_id=member.id, token_hash=token_hash, purpose="screening", expires_at=magic_token_expiry())
    )
    # `focus` tells the check-in page which measure this outreach was about, so
    # the member lands on that specific screen (not just the first in their list).
    link = f"{settings.app_base_url}/verify?token={raw_token}&focus={gap.id}"

    # Pick outreach copy by the measure's template (screening invite / refill
    # reminder / pre- or postnatal reminder). Falls back to the screening invite
    # for anything unrecognized.
    measure = REGISTRY.get(gap.measure_code)
    template_code = template_override or getattr(measure, "outreach_template", "screening_invite")
    tpl = OUTREACH_TEMPLATES.get(template_code, OUTREACH_TEMPLATES["screening_invite"])

    # Best-effort delivery: try the preferred channel (a cadence step may force
    # sms/email; otherwise use the member's preference), fall back to email if SMS
    # is unavailable/unconfigured, and never let a provider error crash the batch —
    # record a failed attempt for the queue instead.
    if channel_override in ("sms", "email"):
        prefers_sms = channel_override == "sms" and member.consent_sms and bool(member.phone)
    else:
        prefers_sms = member.preferred_channel == "sms" and member.consent_sms and bool(member.phone)
    can_email = bool(member.consent_email and member.email)
    channel, message_id, error = "", "", ""

    if prefers_sms:
        channel = "sms"
        try:
            message_id = send_sms(member.phone, tpl["sms"](tenant.name, link))
        except Exception as e:  # noqa: BLE001 — delivery must not crash the batch
            error = str(e)[:500]
    if not message_id and can_email:
        channel = "email"
        try:
            message_id = send_email(
                member.email,
                tpl["email_subject"](tenant.name),
                tpl["email_body"](tenant.name, member.first_name, link),
            )
        except Exception as e:  # noqa: BLE001
            error = str(e)[:500]
    if not channel:
        channel = member.preferred_channel
        error = error or "No consent on file for any contact channel"

    attempt = OutreachAttempt(
        care_gap_id=gap.id,
        member_id=member.id,
        channel=channel,
        template_code=template_code,
        status=OutreachStatus.sent.value if message_id else OutreachStatus.failed.value,
        provider_message_id=message_id,
        error="" if message_id else (error or "delivery not confirmed"),
    )
    db.add(attempt)
    return attempt


async def run_batch_for_tenant(db: AsyncSession, tenant: Tenant) -> dict:
    """Sends outreach for every one of this tenant's open gaps due for (re)contact."""
    now = datetime.utcnow()
    res = await db.execute(
        select(CareGap).where(
            CareGap.tenant_id == tenant.id,
            CareGap.status.in_([GapStatus.open.value, GapStatus.outreach_sent.value]),
            (CareGap.next_outreach_at.is_(None)) | (CareGap.next_outreach_at <= now),
        )
    )
    gaps = res.scalars().all()

    sent = 0
    for gap in gaps:
        member = await db.get(Member, gap.member_id)
        attempt = await send_to_member(db, tenant, member, gap)
        if attempt.status == OutreachStatus.sent.value:
            gap.status = GapStatus.outreach_sent.value
            gap.last_outreach_at = now
            gap.next_outreach_at = now + timedelta(days=RETRY_CADENCE_DAYS)
            sent += 1
    await db.commit()
    return {"tenant_id": tenant.id, "tenant_slug": tenant.slug, "evaluated": len(gaps), "sent": sent}
