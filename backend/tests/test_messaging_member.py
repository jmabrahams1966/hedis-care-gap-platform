import uuid
from datetime import date

import pytest
from httpx import AsyncClient

from app.db import SessionLocal
from app.models import Conversation, MagicToken, StaffRole, StaffUser
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


async def _tenant_member(client: AsyncClient) -> tuple[str, str]:
    sa_email, sa_pw = await _make_super_admin()
    sa = await _login(client, sa_email, sa_pw)
    slug = f"mm-{uuid.uuid4().hex[:8]}"
    admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    res = await client.post(
        "/api/tenants",
        json={
            "slug": slug,
            "name": "Member Msg Plan",
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
            "external_member_id": "MM-1",
            "first_name": "Mel",
            "last_name": "Test",
            "date_of_birth": f"{year - 40}-05-12",
            "sex": "F",
            "email": "mel@example.com",
            "consent_email": True,
        },
        headers=_auth(pa),
    )
    return pa, res.json()["id"]


async def _member_token(client: AsyncClient, member_id: str) -> str:
    raw, token_hash = generate_magic_token()
    async with SessionLocal() as db:
        db.add(
            MagicToken(member_id=member_id, token_hash=token_hash, purpose="messaging", expires_at=magic_token_expiry())
        )
        await db.commit()
    res = await client.post("/api/auth/member/verify", json={"token": raw})
    assert res.status_code == 200, res.text
    return res.json()["token"]


async def _conv_id(member_id: str) -> str:
    from sqlalchemy import select

    async with SessionLocal() as db:
        return (
            await db.execute(select(Conversation).where(Conversation.member_id == member_id))
        ).scalar_one().id


@pytest.mark.asyncio
async def test_member_thread_autocreates_and_clears_unread(client: AsyncClient):
    pa, member_id = await _tenant_member(client)
    mtok = await _member_token(client, member_id)

    # first access auto-creates the conversation
    r = await client.get("/api/member/conversation", headers=_auth(mtok))
    assert r.status_code == 200, r.text
    assert r.json()["messages"] == []

    # staff sends → member_unread True; member re-fetch clears it and sees the message
    conv_id = await _conv_id(member_id)
    await client.post(f"/api/conversations/{conv_id}/messages", json={"body": "checking in"}, headers=_auth(pa))
    r2 = await client.get("/api/member/conversation", headers=_auth(mtok))
    assert len(r2.json()["messages"]) == 1 and r2.json()["messages"][0]["body"] == "checking in"

    # thread now shows member_unread cleared (staff view)
    staff_view = await client.get(f"/api/conversations/{conv_id}", headers=_auth(pa))
    assert staff_view.json()["conversation"]["member_unread"] is False


@pytest.mark.asyncio
async def test_member_send_sets_staff_unread(client: AsyncClient):
    pa, member_id = await _tenant_member(client)
    mtok = await _member_token(client, member_id)
    await client.get("/api/member/conversation", headers=_auth(mtok))  # create

    r = await client.post(
        "/api/member/conversation/messages", json={"body": "I have a question"}, headers=_auth(mtok)
    )
    assert r.status_code == 200, r.text
    assert r.json()["direction"] == "inbound"

    conv_id = await _conv_id(member_id)
    # Check via the inbox list, not the thread GET (opening a thread clears staff_unread).
    inbox = await client.get("/api/conversations", headers=_auth(pa))
    row = [c for c in inbox.json() if c["id"] == conv_id][0]
    assert row["staff_unread"] is True
