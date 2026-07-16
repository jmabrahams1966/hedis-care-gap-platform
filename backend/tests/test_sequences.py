import uuid

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


async def _tenant_admin(client: AsyncClient) -> tuple[str, str]:
    sa_email, sa_pw = await _make_super_admin()
    sa = await _login(client, sa_email, sa_pw)
    slug = f"sq-{uuid.uuid4().hex[:8]}"
    admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    res = await client.post(
        "/api/tenants",
        json={
            "slug": slug,
            "name": "Sequences Test Plan",
            "enabled_measures": ["mental_health"],
            "first_admin_email": admin_email,
            "first_admin_password": "admin-password-123",
        },
        headers=_auth(sa),
    )
    assert res.status_code == 200, res.text
    pa = await _login(client, admin_email, "admin-password-123")
    return pa, slug


_STEPS = [
    {"step_order": 0, "offset_days": 0, "channel": "email", "template_key": "screening_invite"},
    {"step_order": 1, "offset_days": 3, "channel": "member_preferred", "template_key": "screening_invite"},
    {
        "step_order": 2,
        "offset_days": 7,
        "channel": "email",
        "template_key": "screening_invite",
        "recurring": True,
        "repeat_interval_days": 7,
    },
]


@pytest.mark.asyncio
async def test_create_edit_and_list_sequence(client: AsyncClient):
    pa, _ = await _tenant_admin(client)
    res = await client.post(
        "/api/sequences", json={"name": "DSF cadence", "steps": _STEPS}, headers=_auth(pa)
    )
    assert res.status_code == 200, res.text
    seq = res.json()
    assert len(seq["steps"]) == 3 and seq["steps"][0]["channel"] == "email"

    # edit: drop to one step
    upd = await client.put(
        f"/api/sequences/{seq['id']}",
        json={"name": "DSF cadence v2", "steps": _STEPS[:1]},
        headers=_auth(pa),
    )
    assert upd.status_code == 200, upd.text
    assert upd.json()["name"] == "DSF cadence v2" and len(upd.json()["steps"]) == 1

    lst = await client.get("/api/sequences", headers=_auth(pa))
    assert any(s["id"] == seq["id"] for s in lst.json())


@pytest.mark.asyncio
async def test_assign_sequence_to_measure(client: AsyncClient):
    pa, _ = await _tenant_admin(client)
    seq_id = (
        await client.post("/api/sequences", json={"name": "s", "steps": _STEPS[:1]}, headers=_auth(pa))
    ).json()["id"]
    r = await client.patch(
        "/api/measures/mental_health/sequence", json={"sequence_id": seq_id}, headers=_auth(pa)
    )
    assert r.status_code == 200, r.text
    assert r.json()["sequence_id"] == seq_id


@pytest.mark.asyncio
async def test_recurring_without_interval_rejected(client: AsyncClient):
    pa, _ = await _tenant_admin(client)
    bad = [{"step_order": 0, "offset_days": 0, "channel": "email", "template_key": "screening_invite", "recurring": True}]
    res = await client.post("/api/sequences", json={"name": "bad", "steps": bad}, headers=_auth(pa))
    assert res.status_code == 422, res.text


@pytest.mark.asyncio
async def test_sequence_cross_tenant_404(client: AsyncClient):
    pa, _ = await _tenant_admin(client)
    seq_id = (
        await client.post("/api/sequences", json={"name": "s", "steps": _STEPS[:1]}, headers=_auth(pa))
    ).json()["id"]
    pa2, _ = await _tenant_admin(client)
    res = await client.put(
        f"/api/sequences/{seq_id}", json={"name": "hijack", "steps": []}, headers=_auth(pa2)
    )
    assert res.status_code == 404, res.text
