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


async def _tenant_member_gap(client: AsyncClient) -> tuple[str, str, str]:
    """Return (payer_admin token, member id, an open mental_health care-gap id)."""
    sa_email, sa_pw = await _make_super_admin()
    sa = await _login(client, sa_email, sa_pw)
    slug = f"sf-{uuid.uuid4().hex[:8]}"
    admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    res = await client.post(
        "/api/tenants",
        json={
            "slug": slug,
            "name": "Safety Test Plan",
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
            "external_member_id": "SF-1",
            "first_name": "Sky",
            "last_name": "Test",
            "date_of_birth": f"{year - 40}-05-12",
            "sex": "F",
            "email": "sky@example.com",
            "consent_email": True,
        },
        headers=_auth(pa),
    )
    assert res.status_code == 200, res.text
    member_id = res.json()["id"]
    q = await client.get("/api/care-gaps/queue?measure=mental_health", headers=_auth(pa))
    return pa, member_id, q.json()[0]["id"]


@pytest.mark.asyncio
async def test_safety_plan_upsert_roundtrip(client: AsyncClient):
    pa, member_id, _ = await _tenant_member_gap(client)
    res = await client.put(
        f"/api/members/{member_id}/safety-plan",
        json={"warning_signs": "isolation, sleeplessness", "coping_strategies": "call sister"},
        headers=_auth(pa),
    )
    assert res.status_code == 200, res.text
    assert res.json()["warning_signs"] == "isolation, sleeplessness"  # decrypts back

    got = await client.get(f"/api/members/{member_id}/safety-plan", headers=_auth(pa))
    assert got.status_code == 200
    assert got.json()["coping_strategies"] == "call sister"


@pytest.mark.asyncio
async def test_escalation_steps_seed_and_toggle(client: AsyncClient):
    pa, _, gap_id = await _tenant_member_gap(client)
    # protocol steps returned, all incomplete initially
    res = await client.get(f"/api/care-gaps/{gap_id}/escalation", headers=_auth(pa))
    assert res.status_code == 200, res.text
    steps = res.json()
    assert len(steps) >= 4
    assert all(s["completed"] is False for s in steps)
    key = steps[0]["step_key"]

    # toggle on
    t = await client.post(f"/api/care-gaps/{gap_id}/escalation/{key}", headers=_auth(pa))
    assert t.status_code == 200, t.text
    assert t.json()["completed"] is True

    res2 = await client.get(f"/api/care-gaps/{gap_id}/escalation", headers=_auth(pa))
    done = [s for s in res2.json() if s["step_key"] == key][0]
    assert done["completed"] is True and done["completed_by"] is not None

    # toggle off
    t2 = await client.post(f"/api/care-gaps/{gap_id}/escalation/{key}", headers=_auth(pa))
    assert t2.json()["completed"] is False


@pytest.mark.asyncio
async def test_unknown_escalation_step_422(client: AsyncClient):
    pa, _, gap_id = await _tenant_member_gap(client)
    res = await client.post(f"/api/care-gaps/{gap_id}/escalation/not_a_step", headers=_auth(pa))
    assert res.status_code == 422, res.text


@pytest.mark.asyncio
async def test_safety_cross_tenant_404(client: AsyncClient):
    pa, member_id, _ = await _tenant_member_gap(client)
    pa2, _, _ = await _tenant_member_gap(client)
    res = await client.get(f"/api/members/{member_id}/safety-plan", headers=_auth(pa2))
    assert res.status_code == 404, res.text
