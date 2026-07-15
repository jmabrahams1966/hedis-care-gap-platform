import uuid
from datetime import date

import pytest
from httpx import AsyncClient

from app.db import SessionLocal
from app.models import StaffRole, StaffUser
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


async def _tenant_member_gap(client: AsyncClient) -> tuple[str, str]:
    """Create a mental_health tenant + one eligible member, return (payer_admin
    token, an open mental_health care-gap id)."""
    sa_email, sa_pw = await _make_super_admin()
    sa = await _login(client, sa_email, sa_pw)
    slug = f"nt-{uuid.uuid4().hex[:8]}"
    admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    res = await client.post(
        "/api/tenants",
        json={
            "slug": slug,
            "name": "Note Type Test Plan",
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
            "external_member_id": "NT-1",
            "first_name": "Nora",
            "last_name": "Test",
            "date_of_birth": f"{year - 40}-05-12",
            "sex": "F",
            "email": "nora@example.com",
            "consent_email": True,
        },
        headers=_auth(pa),
    )
    assert res.status_code == 200, res.text

    q = await client.get("/api/care-gaps/queue?measure=mental_health", headers=_auth(pa))
    assert q.status_code == 200, q.text
    rows = q.json()
    assert rows
    return pa, rows[0]["id"]


@pytest.mark.asyncio
async def test_note_saves_and_returns_type(client: AsyncClient):
    pa, gap_id = await _tenant_member_gap(client)
    res = await client.post(
        f"/api/care-gaps/{gap_id}/notes",
        json={"note": "called member, discussed PHQ-9 follow-up", "note_type": "safety_check"},
        headers=_auth(pa),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["note_type"] == "safety_check"
    assert body["note"] == "called member, discussed PHQ-9 follow-up"

    # it comes back on the case-detail read too
    detail = await client.get(f"/api/care-gaps/{gap_id}", headers=_auth(pa))
    assert detail.status_code == 200
    assert detail.json()["notes"][0]["note_type"] == "safety_check"


@pytest.mark.asyncio
async def test_note_type_defaults_to_other(client: AsyncClient):
    pa, gap_id = await _tenant_member_gap(client)
    res = await client.post(
        f"/api/care-gaps/{gap_id}/notes",
        json={"note": "left voicemail"},
        headers=_auth(pa),
    )
    assert res.status_code == 200, res.text
    assert res.json()["note_type"] == "other"


@pytest.mark.asyncio
async def test_bad_note_type_rejected(client: AsyncClient):
    pa, gap_id = await _tenant_member_gap(client)
    res = await client.post(
        f"/api/care-gaps/{gap_id}/notes",
        json={"note": "x", "note_type": "not_a_real_type"},
        headers=_auth(pa),
    )
    assert res.status_code == 422, res.text
