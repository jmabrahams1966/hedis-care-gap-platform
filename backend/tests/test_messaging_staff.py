import uuid
from datetime import date, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db import SessionLocal
from app.messaging_service import NOTIFY_TEMPLATE
from app.models import Conversation, Member, StaffRole, StaffUser
from app.security import hash_password


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


async def _tenant(client: AsyncClient) -> tuple[str, str]:
    sa_email, sa_pw = await _make_super_admin()
    sa = await _login(client, sa_email, sa_pw)
    slug = f"ms-{uuid.uuid4().hex[:8]}"
    admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    res = await client.post(
        "/api/tenants",
        json={
            "slug": slug,
            "name": "Messaging Test Plan",
            "enabled_measures": ["mental_health"],
            "first_admin_email": admin_email,
            "first_admin_password": "admin-password-123",
        },
        headers=_auth(sa),
    )
    assert res.status_code == 200, res.text
    pa = await _login(client, admin_email, "admin-password-123")
    return pa, slug


async def _member(client: AsyncClient, pa: str, ext: str) -> str:
    year = date.today().year
    res = await client.post(
        "/api/members",
        json={
            "external_member_id": ext,
            "first_name": "Mem",
            "last_name": "Test",
            "date_of_birth": f"{year - 40}-05-12",
            "sex": "F",
            "email": f"{ext.lower()}@example.com",
            "consent_email": True,
        },
        headers=_auth(pa),
    )
    assert res.status_code == 200, res.text
    return res.json()["id"]


async def _conversation(member_id: str, crisis: bool = False) -> str:
    async with SessionLocal() as db:
        m = await db.get(Member, member_id)
        c = Conversation(
            tenant_id=m.tenant_id,
            member_id=member_id,
            crisis_flag=crisis,
            last_message_at=datetime.utcnow(),
        )
        db.add(c)
        await db.commit()
        return c.id


def test_notification_template_carries_no_phi():
    # The notification is link-only — it must never interpolate the message body.
    assert "{body}" not in NOTIFY_TEMPLATE
    assert "{link}" in NOTIFY_TEMPLATE


@pytest.mark.asyncio
async def test_staff_send_creates_message_and_flags_member_unread(client: AsyncClient):
    pa, _ = await _tenant(client)
    member_id = await _member(client, pa, "MS-1")
    conv_id = await _conversation(member_id)

    res = await client.post(
        f"/api/conversations/{conv_id}/messages", json={"body": "How are you feeling this week?"}, headers=_auth(pa)
    )
    assert res.status_code == 200, res.text
    assert res.json()["body"] == "How are you feeling this week?"  # decrypts back
    assert res.json()["direction"] == "outbound"

    thread = await client.get(f"/api/conversations/{conv_id}", headers=_auth(pa))
    assert thread.status_code == 200
    assert len(thread.json()["messages"]) == 1
    assert thread.json()["conversation"]["member_unread"] is True


@pytest.mark.asyncio
async def test_inbox_lists_crisis_first(client: AsyncClient):
    pa, _ = await _tenant(client)
    m1 = await _member(client, pa, "MS-N")
    m2 = await _member(client, pa, "MS-C")
    await _conversation(m1, crisis=False)
    crisis_id = await _conversation(m2, crisis=True)

    res = await client.get("/api/conversations", headers=_auth(pa))
    assert res.status_code == 200
    rows = res.json()
    assert rows[0]["id"] == crisis_id and rows[0]["crisis_flag"] is True

    safety = await client.get("/api/conversations?filter=safety", headers=_auth(pa))
    assert all(c["crisis_flag"] for c in safety.json())


@pytest.mark.asyncio
async def test_conversation_cross_tenant_404(client: AsyncClient):
    pa, _ = await _tenant(client)
    member_id = await _member(client, pa, "MS-X")
    conv_id = await _conversation(member_id)
    pa2, _ = await _tenant(client)
    res = await client.get(f"/api/conversations/{conv_id}", headers=_auth(pa2))
    assert res.status_code == 404, res.text
