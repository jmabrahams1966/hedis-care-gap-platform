import uuid
from datetime import date, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.crisis import crisis_scan, within_business_hours
from app.db import SessionLocal
from app.messaging_service import get_or_create_conversation, record_inbound_message
from app.models import CareGap, Conversation, MagicToken, Member, Message, StaffRole, StaffUser
from app.security import generate_magic_token, hash_password, magic_token_expiry


async def _make_super_admin() -> tuple[str, str]:
    email = f"super-{uuid.uuid4().hex[:8]}@example.com"
    password = "test-password-123"
    async with SessionLocal() as db:
        db.add(
            StaffUser(
                tenant_id=None,
                email=email,
                password_hash=hash_password(password),
                role=StaffRole.super_admin.value,
                name="Test Super Admin",
            )
        )
        await db.commit()
    return email, password


async def _login(client: AsyncClient, email: str, password: str) -> str:
    res = await client.post("/api/auth/staff/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["token"]


def _auth(token: str) -> dict:
    return {"authorization": f"Bearer {token}"}


async def _tenant_member(client: AsyncClient) -> str:
    sa_email, sa_pw = await _make_super_admin()
    sa = await _login(client, sa_email, sa_pw)
    slug = f"cr-{uuid.uuid4().hex[:8]}"
    admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    res = await client.post(
        "/api/tenants",
        json={
            "slug": slug,
            "name": "Crisis Test Plan",
            "enabled_measures": ["mental_health"],
            "first_admin_email": admin_email,
            "first_admin_password": "admin-password-123",
        },
        headers=_auth(sa),
    )
    assert res.status_code == 200, res.text
    pa = await _login(client, admin_email, "admin-password-123")
    year = date.today().year
    res = await client.post(
        "/api/members",
        json={
            "external_member_id": "CR-1",
            "first_name": "Cris",
            "last_name": "Test",
            "date_of_birth": f"{year - 40}-05-12",
            "sex": "F",
            "email": "cris@example.com",
            "consent_email": True,
        },
        headers=_auth(pa),
    )
    return res.json()["id"]


async def _member_token(client: AsyncClient, member_id: str) -> str:
    raw, token_hash = generate_magic_token()
    async with SessionLocal() as db:
        db.add(
            MagicToken(member_id=member_id, token_hash=token_hash, purpose="messaging", expires_at=magic_token_expiry())
        )
        await db.commit()
    res = await client.post("/api/auth/member/verify", json={"token": raw})
    return res.json()["token"]


def test_crisis_scan_flags_intent_but_not_benign():
    assert crisis_scan("i think i want to die") is True
    assert crisis_scan("Thinking about suicide") is True
    assert crisis_scan("feeling good, thanks for checking in") is False


def test_business_hours_window():
    assert within_business_hours(datetime(2026, 7, 15, 10, 0)) is True  # Wed 10:00
    assert within_business_hours(datetime(2026, 7, 15, 22, 0)) is False  # Wed 22:00
    assert within_business_hours(datetime(2026, 7, 18, 10, 0)) is False  # Sat 10:00


@pytest.mark.asyncio
async def test_member_crisis_message_autoreplies_and_raises_safety_flag(client: AsyncClient):
    member_id = await _tenant_member(client)
    mtok = await _member_token(client, member_id)
    await client.get("/api/member/conversation", headers=_auth(mtok))  # create

    r = await client.post(
        "/api/member/conversation/messages",
        json={"body": "I don't want to be here anymore, I want to die"},
        headers=_auth(mtok),
    )
    assert r.status_code == 200, r.text
    assert r.json()["outcome"] == "crisis"

    async with SessionLocal() as db:
        conv = (
            await db.execute(select(Conversation).where(Conversation.member_id == member_id))
        ).scalar_one()
        assert conv.crisis_flag is True
        msgs = (
            await db.execute(select(Message).where(Message.conversation_id == conv.id))
        ).scalars().all()
        # inbound + the 988 auto-reply
        assert any(m.direction == "outbound" and "988" in m.body for m in msgs)
        # Feature B tie-in: the member's mental-health gap is now safety-flagged
        gap = (
            await db.execute(
                select(CareGap).where(
                    CareGap.member_id == member_id, CareGap.measure_code == "mental_health"
                )
            )
        ).scalars().first()
        assert gap.safety_flag is True


@pytest.mark.asyncio
async def test_after_hours_ack(client: AsyncClient):
    member_id = await _tenant_member(client)
    async with SessionLocal() as db:
        member = await db.get(Member, member_id)
        conv = await get_or_create_conversation(db, member)
        _, outcome = await record_inbound_message(
            db, conv, member, "just a normal question", channel="web", now=datetime(2026, 7, 18, 22, 0)
        )
        await db.commit()
    assert outcome == "after_hours_ack"


@pytest.mark.asyncio
async def test_in_hours_no_ack(client: AsyncClient):
    member_id = await _tenant_member(client)
    async with SessionLocal() as db:
        member = await db.get(Member, member_id)
        conv = await get_or_create_conversation(db, member)
        _, outcome = await record_inbound_message(
            db, conv, member, "just a normal question", channel="web", now=datetime(2026, 7, 15, 10, 0)
        )
        await db.commit()
    assert outcome == "in_hours"
