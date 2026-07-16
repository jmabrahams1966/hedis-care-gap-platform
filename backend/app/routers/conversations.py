from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import get_current_member, require_role
from ..messaging_service import get_or_create_conversation, record_inbound_message, send_staff_message
from ..models import Conversation, Member, Message, StaffRole, StaffUser
from ..schemas import ConversationAssign, MessageSend

router = APIRouter(prefix="/api/conversations", tags=["conversations"])
member_router = APIRouter(prefix="/api/member/conversation", tags=["conversations"])

_ROLES = (StaffRole.care_manager.value, StaffRole.payer_admin.value, StaffRole.super_admin.value)


async def _member_alias(db: AsyncSession, member_id: str) -> str:
    member = await db.get(Member, member_id)
    return member.alias if member else "Member"


async def _summary(db: AsyncSession, c: Conversation) -> dict:
    return {
        "id": c.id,
        "member_id": c.member_id,
        "member_alias": await _member_alias(db, c.member_id),
        "assigned_staff_id": c.assigned_staff_id,
        "status": c.status,
        "crisis_flag": c.crisis_flag,
        "last_message_at": c.last_message_at,
        "staff_unread": c.staff_unread,
        "member_unread": c.member_unread,
    }


def _msg(m: Message) -> dict:
    return {
        "id": m.id,
        "direction": m.direction,
        "channel": m.channel,
        "sender_staff_id": m.sender_staff_id,
        "body": m.body,
        "crisis_flag": m.crisis_flag,
        "created_at": m.created_at,
    }


@router.get("")
async def inbox(
    filter: str = "all",
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    """Tenant inbox, crisis-flagged first then most-recent. `filter`: all | unread
    | mine | unassigned | safety."""
    stmt = select(Conversation).where(Conversation.tenant_id == staff.tenant_id)
    if filter == "unread":
        stmt = stmt.where(Conversation.staff_unread.is_(True))
    elif filter == "mine":
        stmt = stmt.where(Conversation.assigned_staff_id == staff.id)
    elif filter == "unassigned":
        stmt = stmt.where(Conversation.assigned_staff_id.is_(None))
    elif filter == "safety":
        stmt = stmt.where(Conversation.crisis_flag.is_(True))
    rows = (
        await db.execute(
            stmt.order_by(Conversation.crisis_flag.desc(), Conversation.last_message_at.desc().nulls_last())
        )
    ).scalars().all()
    return [await _summary(db, c) for c in rows]


async def _load(db: AsyncSession, staff: StaffUser, conversation_id: str) -> Conversation:
    c = await db.get(Conversation, conversation_id)
    if c is None or c.tenant_id != staff.tenant_id:
        raise HTTPException(404, "Conversation not found")
    return c


@router.get("/{conversation_id}")
async def thread(
    conversation_id: str,
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    c = await _load(db, staff, conversation_id)
    msgs = (
        await db.execute(
            select(Message).where(Message.conversation_id == c.id).order_by(Message.created_at.asc())
        )
    ).scalars().all()
    if c.staff_unread:
        c.staff_unread = False
        await db.commit()
    return {"conversation": await _summary(db, c), "messages": [_msg(m) for m in msgs]}


@router.post("/{conversation_id}/messages")
async def send(
    conversation_id: str,
    body: MessageSend,
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    c = await _load(db, staff, conversation_id)
    if not body.body.strip():
        raise HTTPException(422, "Message body is required")
    msg = await send_staff_message(db, c, staff, body.body.strip())
    await db.commit()
    await db.refresh(msg)
    return _msg(msg)


@router.post("/{conversation_id}/assign")
async def assign(
    conversation_id: str,
    body: ConversationAssign,
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    c = await _load(db, staff, conversation_id)
    c.assigned_staff_id = body.staff_id or staff.id
    await db.commit()
    return await _summary(db, c)


@router.post("/{conversation_id}/close")
async def close(
    conversation_id: str,
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    c = await _load(db, staff, conversation_id)
    c.status = "closed"
    await db.commit()
    return await _summary(db, c)


# --- Member side (magic-link authenticated) ---


@member_router.get("")
async def member_thread(
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    c = await get_or_create_conversation(db, member)
    msgs = (
        await db.execute(
            select(Message).where(Message.conversation_id == c.id).order_by(Message.created_at.asc())
        )
    ).scalars().all()
    if c.member_unread:
        c.member_unread = False
    await db.commit()
    return {
        "conversation": {"id": c.id, "status": c.status, "crisis_flag": c.crisis_flag},
        "messages": [_msg(m) for m in msgs],
    }


@member_router.post("/messages")
async def member_send(
    body: MessageSend,
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    if not body.body.strip():
        raise HTTPException(422, "Message body is required")
    c = await get_or_create_conversation(db, member)
    msg, outcome = await record_inbound_message(db, c, member, body.body.strip(), channel="web")
    await db.commit()
    await db.refresh(msg)
    return {**_msg(msg), "outcome": outcome}
