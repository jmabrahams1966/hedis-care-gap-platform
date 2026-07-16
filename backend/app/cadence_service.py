"""Outreach cadence engine (Feature C1).

Evaluates due `SequenceEnrollment`s and sends the current step via the shared
`outreach_service.send_to_member`, then advances the enrollment. Idempotency is
carried by `next_send_at`: once a step fires, the enrollment is rescheduled into
the future, so a same-day re-run selects nothing. Driven by the daily cron
(`scripts/run_outreach_cron.py`) after the standard retry batch.

Quiet-hours windowing is deferred (spec §10 open question) — sends are not
time-of-day gated yet.
"""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import CareGap, Member, SequenceEnrollment, SequenceStep, Tenant
from .outreach_service import send_to_member


def _consent_ok(member: Member, channel: str) -> bool:
    if channel == "sms":
        return bool(member.consent_sms and member.phone)
    if channel == "email":
        return bool(member.consent_email and member.email)
    # member_preferred — any consented channel works
    return bool((member.consent_sms and member.phone) or (member.consent_email and member.email))


async def _step(db: AsyncSession, sequence_id: str, order: int) -> SequenceStep | None:
    return (
        await db.execute(
            select(SequenceStep).where(
                SequenceStep.sequence_id == sequence_id, SequenceStep.step_order == order
            )
        )
    ).scalar_one_or_none()


async def _next_step(db: AsyncSession, sequence_id: str, after: int) -> SequenceStep | None:
    return (
        await db.execute(
            select(SequenceStep)
            .where(SequenceStep.sequence_id == sequence_id, SequenceStep.step_order > after)
            .order_by(SequenceStep.step_order.asc())
        )
    ).scalars().first()


async def process_due(db: AsyncSession, now: datetime | None = None) -> dict:
    now = now or datetime.utcnow()
    enrolls = (
        await db.execute(
            select(SequenceEnrollment).where(
                SequenceEnrollment.status == "active", SequenceEnrollment.next_send_at <= now
            )
        )
    ).scalars().all()

    sent = 0
    for e in enrolls:
        step = await _step(db, e.sequence_id, e.current_step_order)
        if step is None:
            e.status, e.ended_reason = "ended", "completed"
            continue

        member = await db.get(Member, e.member_id)
        gap = await db.get(CareGap, e.care_gap_id) if e.care_gap_id else None
        if member is not None and gap is not None and _consent_ok(member, step.channel):
            tenant = await db.get(Tenant, e.tenant_id)
            attempt = await send_to_member(
                db, tenant, member, gap, template_override=step.template_key, channel_override=step.channel
            )
            if attempt.status == "sent":
                sent += 1

        if step.recurring:
            e.next_send_at = now + timedelta(days=step.repeat_interval_days or 7)
        else:
            nxt = await _next_step(db, e.sequence_id, e.current_step_order)
            if nxt is None:
                e.status, e.ended_reason = "ended", "completed"
            else:
                e.current_step_order = nxt.step_order
                e.next_send_at = now + timedelta(days=nxt.offset_days)

    await db.commit()
    return {"evaluated": len(enrolls), "sent": sent}
