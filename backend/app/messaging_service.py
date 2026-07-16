"""Secure-messaging send logic (Feature D).

HIPAA rule: a message body is PHI and is NEVER placed in an SMS or email. The
member is only *notified* ("you have a new secure message") with a magic-link to
the in-app message center, where the body is shown over an authenticated, TLS
session. `NOTIFY_TEMPLATE` contains only the link — never the body.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .ai_service import AiService
from .audit import log_action
from .config import settings
from .crisis import AFTER_HOURS_ACK, CRISIS_AUTO_REPLY, crisis_scan, within_business_hours
from .models import CareGap, Conversation, GapStatus, MagicToken, Member, Message
from .notifications.email_service import send_email
from .notifications.sms_service import send_sms
from .security import generate_magic_token, magic_token_expiry

# No PHI here — link only.
NOTIFY_TEMPLATE = "New secure message from your care team — tap to view: {link}"


def _notify_link(raw_token: str) -> str:
    return f"{settings.app_base_url}/verify?token={raw_token}&next=messages"


async def get_or_create_conversation(db: AsyncSession, member: Member) -> Conversation:
    """One thread per member — create it on first message from either side."""
    conv = (
        await db.execute(select(Conversation).where(Conversation.member_id == member.id))
    ).scalar_one_or_none()
    if conv is None:
        conv = Conversation(tenant_id=member.tenant_id, member_id=member.id)
        db.add(conv)
        await db.flush()
    return conv


async def notify_member_of_message(db: AsyncSession, member: Member) -> str | None:
    """Issue a magic-link and send a non-PHI notification over the member's
    consented channel. Returns a delivery-status string (or None if unreachable)."""
    raw_token, token_hash = generate_magic_token()
    db.add(
        MagicToken(member_id=member.id, token_hash=token_hash, purpose="messaging", expires_at=magic_token_expiry())
    )
    text = NOTIFY_TEMPLATE.format(link=_notify_link(raw_token))
    try:
        if member.consent_sms and member.phone:
            send_sms(member.phone, text)
            return "notified_sms"
        if member.consent_email and member.email:
            send_email(member.email, "New secure message", text)
            return "notified_email"
    except Exception:  # noqa: BLE001 — a notification failure must not lose the message
        return "notify_failed"
    return None


async def _raise_member_safety_flag(db: AsyncSession, member: Member) -> None:
    """Tie a messaging crisis into Feature B: flag the member's open mental-health
    gap so it surfaces in the queue + the case-workspace SafetyPanel."""
    gap = (
        await db.execute(
            select(CareGap).where(
                CareGap.member_id == member.id,
                CareGap.measure_code == "mental_health",
                CareGap.status.notin_([GapStatus.closed.value, GapStatus.excluded.value]),
            )
        )
    ).scalars().first()
    if gap is not None:
        gap.safety_flag = True


def _system_reply(conversation: Conversation, channel: str, text: str, crisis: bool) -> Message:
    return Message(
        conversation_id=conversation.id,
        direction="outbound",
        channel=channel,
        sender_staff_id=None,
        body=text,
        crisis_flag=crisis,
    )


async def record_inbound_message(
    db: AsyncSession,
    conversation: Conversation,
    member: Member,
    body: str,
    channel: str,
    now: datetime | None = None,
    ai: "AiService | None" = None,
) -> tuple[Message, str]:
    """Append an inbound member message (web or sms) and run the always-on safety
    logic: crisis → immediate 988 auto-reply + Feature B safety flag; else
    after-hours → auto-acknowledge. Returns (message, outcome). Caller commits.

    The deterministic keyword crisis path (below) is the safety net and runs
    unconditionally. AI triage (Feature E) is layered on *after* it, is
    best-effort, and is a no-op when AI is disabled — it can never change the
    crisis handling or the returned outcome."""
    now = now or datetime.utcnow()
    msg = Message(conversation_id=conversation.id, direction="inbound", channel=channel, body=body)
    db.add(msg)
    conversation.staff_unread = True
    conversation.last_message_at = now

    outcome = "in_hours"
    if crisis_scan(body):
        msg.crisis_flag = True
        conversation.crisis_flag = True
        db.add(_system_reply(conversation, channel, CRISIS_AUTO_REPLY, crisis=True))
        conversation.member_unread = True
        if channel == "sms" and member.phone:
            try:
                send_sms(member.phone, CRISIS_AUTO_REPLY)  # 988 text is safe on SMS
            except Exception:  # noqa: BLE001
                pass
        await _raise_member_safety_flag(db, member)
        await log_action(
            db,
            actor_type="system",
            action="message_crisis_detected",
            resource_type="conversation",
            resource_id=conversation.id,
            tenant_id=conversation.tenant_id,
        )
        outcome = "crisis"
    elif not within_business_hours(now):
        db.add(_system_reply(conversation, channel, AFTER_HOURS_ACK, crisis=False))
        conversation.member_unread = True
        if channel == "sms" and member.phone:
            try:
                send_sms(member.phone, AFTER_HOURS_ACK)
            except Exception:  # noqa: BLE001
                pass
        outcome = "after_hours_ack"

    # Feature E: advisory AI triage, strictly additive. No-op when AI is off;
    # any failure is swallowed inside assess_risk. Runs after the deterministic
    # crisis handling above and never alters `outcome`.
    ai = ai or AiService()
    signal = await ai.assess_risk(
        db, text=body, tenant_id=conversation.tenant_id, member_id=member.id
    )
    if signal:
        msg.ai_risk_level = signal["level"]
        msg.ai_risk_rationale = signal["rationale"]

    return msg, outcome


async def send_staff_message(db: AsyncSession, conversation: Conversation, staff, body: str) -> Message:
    """Append a staff web message and notify the member (link only). Caller commits."""
    msg = Message(
        conversation_id=conversation.id,
        direction="outbound",
        channel="web",
        sender_staff_id=staff.id,
        body=body,
    )
    db.add(msg)
    conversation.member_unread = True
    conversation.staff_unread = False
    conversation.last_message_at = datetime.utcnow()

    member = await db.get(Member, conversation.member_id)
    msg.delivery_status = await notify_member_of_message(db, member) if member else None

    await log_action(
        db,
        actor_type="staff",
        actor_id=staff.id,
        action="message_sent",
        resource_type="conversation",
        resource_id=conversation.id,
        tenant_id=conversation.tenant_id,
    )
    return msg
