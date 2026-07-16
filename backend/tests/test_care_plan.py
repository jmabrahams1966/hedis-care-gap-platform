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


async def _tenant_member(client: AsyncClient) -> tuple[str, str]:
    sa_email, sa_pw = await _make_super_admin()
    sa = await _login(client, sa_email, sa_pw)
    slug = f"cp-{uuid.uuid4().hex[:8]}"
    admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    res = await client.post(
        "/api/tenants",
        json={
            "slug": slug,
            "name": "Care Plan Test Plan",
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
            "external_member_id": "CP-1",
            "first_name": "Cara",
            "last_name": "Test",
            "date_of_birth": f"{year - 40}-05-12",
            "sex": "F",
            "email": "cara@example.com",
            "consent_email": True,
        },
        headers=_auth(pa),
    )
    assert res.status_code == 200, res.text
    return pa, res.json()["id"]


@pytest.mark.asyncio
async def test_create_list_and_update_goal(client: AsyncClient):
    pa, member_id = await _tenant_member(client)
    res = await client.post(
        f"/api/members/{member_id}/care-plan",
        json={
            "goal_text": "Reduce PHQ-9 below 10",
            "interventions_text": "Weekly CBT + medication review",
            "target_date": "2026-09-01",
        },
        headers=_auth(pa),
    )
    assert res.status_code == 200, res.text
    gid = res.json()["id"]
    assert res.json()["status"] == "open"
    assert res.json()["goal_text"] == "Reduce PHQ-9 below 10"  # decrypts back

    lst = await client.get(f"/api/members/{member_id}/care-plan", headers=_auth(pa))
    assert lst.status_code == 200 and len(lst.json()) == 1

    upd = await client.patch(f"/api/care-plan/{gid}", json={"status": "met"}, headers=_auth(pa))
    assert upd.status_code == 200, upd.text
    assert upd.json()["status"] == "met"


@pytest.mark.asyncio
async def test_care_plan_cross_tenant_404(client: AsyncClient):
    pa, member_id = await _tenant_member(client)
    gid = (
        await client.post(
            f"/api/members/{member_id}/care-plan",
            json={"goal_text": "g"},
            headers=_auth(pa),
        )
    ).json()["id"]
    pa2, _ = await _tenant_member(client)
    res = await client.patch(f"/api/care-plan/{gid}", json={"status": "met"}, headers=_auth(pa2))
    assert res.status_code == 404, res.text
