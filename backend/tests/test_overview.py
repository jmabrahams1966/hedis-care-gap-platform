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


async def _tenant_with_member(client: AsyncClient) -> tuple[str, int]:
    """Create a tenant (mental_health + breast_cancer) with one female-55 member —
    eligible for both, so two open gaps exist. Returns (payer_admin token, year)."""
    sa_email, sa_pw = await _make_super_admin()
    sa = await _login(client, sa_email, sa_pw)
    slug = f"ov-{uuid.uuid4().hex[:8]}"
    admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    res = await client.post(
        "/api/tenants",
        json={
            "slug": slug,
            "name": "Overview Test Plan",
            "enabled_measures": ["mental_health", "breast_cancer"],
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
            "external_member_id": "OV-1",
            "first_name": "Fatima",
            "last_name": "Test",
            "date_of_birth": f"{year - 55}-05-12",
            "sex": "F",
            "email": "fatima@example.com",
            "consent_email": True,
        },
        headers=_auth(pa),
    )
    assert res.status_code == 200, res.text
    return pa, year


@pytest.mark.asyncio
async def test_overview_returns_kpis_measures_worklist(client: AsyncClient):
    pa, year = await _tenant_with_member(client)

    res = await client.get(f"/api/reports/overview?period={year}", headers=_auth(pa))
    assert res.status_code == 200, res.text
    body = res.json()

    assert set(body["kpis"]) >= {
        "gap_closure_rate",
        "open_safety_flags",
        "members_reached",
        "members_enrolled",
    }
    assert body["kpis"]["members_enrolled"] == 1

    assert isinstance(body["measures"], list) and body["measures"]
    m = body["measures"][0]
    assert set(m) >= {"code", "name", "eligible", "completed", "rate", "remaining", "source_split"}
    assert set(m["source_split"]) == {"self_report", "claims_confirmed"}

    # our single female-55 member is eligible for exactly these two measures
    assert {x["code"] for x in body["measures"]} == {"mental_health", "breast_cancer"}
    assert all(x["eligible"] == 1 and x["completed"] == 0 for x in body["measures"])

    # both open gaps show up in the priority worklist
    assert isinstance(body["worklist"], list)
    assert len(body["worklist"]) == 2


@pytest.mark.asyncio
async def test_overview_super_admin_must_pass_tenant(client: AsyncClient):
    sa_email, sa_pw = await _make_super_admin()
    sa = await _login(client, sa_email, sa_pw)
    year = date.today().year
    res = await client.get(f"/api/reports/overview?period={year}", headers=_auth(sa))
    assert res.status_code == 400, res.text
