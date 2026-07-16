"""Secure-messaging send logic (Feature D).

HIPAA rule: a message body is PHI and is NEVER placed in an SMS or email. The
member is only *notified* ("you have a new secure message") with a magic-link to
the in-app message center, where the body is shown over an authenticated, TLS
session. `NOTIFY_TEMPLATE` contains only the link — never the body.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .audit import log_action
from .config import settings
from .models import Conversation, MagicToken, Member, Message
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
