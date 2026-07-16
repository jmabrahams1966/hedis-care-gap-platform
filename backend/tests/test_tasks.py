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
    """Return (payer_admin token, member id)."""
    sa_email, sa_pw = await _make_super_admin()
    sa = await _login(client, sa_email, sa_pw)
    slug = f"tk-{uuid.uuid4().hex[:8]}"
    admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    res = await client.post(
        "/api/tenants",
        json={
            "slug": slug,
            "name": "Task Test Plan",
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
            "external_member_id": "TK-1",
            "first_name": "Tam",
            "last_name": "Test",
            "date_of_birth": f"{year - 40}-05-12",
            "sex": "F",
            "email": "tam@example.com",
            "consent_email": True,
        },
        headers=_auth(pa),
    )
    assert res.status_code == 200, res.text
    return pa, res.json()["id"]


@pytest.mark.asyncio
async def test_create_and_list_task(client: AsyncClient):
    pa, member_id = await _tenant_member(client)
    res = await client.post(
        f"/api/members/{member_id}/tasks",
        json={"title": "Call to schedule PHQ-9 recheck"},
        headers=_auth(pa),
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "open"

    lst = await client.get(f"/api/members/{member_id}/tasks", headers=_auth(pa))
    assert lst.status_code == 200
    assert len(lst.json()) == 1
    assert lst.json()[0]["title"] == "Call to schedule PHQ-9 recheck"


@pytest.mark.asyncio
async def test_complete_task(client: AsyncClient):
    pa, member_id = await _tenant_member(client)
    tid = (
        await client.post(
            f"/api/members/{member_id}/tasks", json={"title": "t"}, headers=_auth(pa)
        )
    ).json()["id"]

    res = await client.patch(f"/api/tasks/{tid}", json={"status": "done"}, headers=_auth(pa))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "done"
    assert body["completed_at"] is not None


@pytest.mark.asyncio
async def test_overdue_rollup(client: AsyncClient):
    pa, member_id = await _tenant_member(client)
    # one overdue (past due), one not due yet
    await client.post(
        f"/api/members/{member_id}/tasks",
        json={"title": "overdue one", "due_at": "2020-01-01T00:00:00"},
        headers=_auth(pa),
    )
    await client.post(
        f"/api/members/{member_id}/tasks",
        json={"title": "future one", "due_at": "2999-01-01T00:00:00"},
        headers=_auth(pa),
    )
    res = await client.get("/api/tasks?status=overdue", headers=_auth(pa))
    assert res.status_code == 200, res.text
    rows = res.json()
    assert len(rows) == 1
    assert rows[0]["title"] == "overdue one"
    assert rows[0]["overdue"] is True


@pytest.mark.asyncio
async def test_task_cross_tenant_404(client: AsyncClient):
    pa, member_id = await _tenant_member(client)
    tid = (
        await client.post(
            f"/api/members/{member_id}/tasks", json={"title": "t"}, headers=_auth(pa)
        )
    ).json()["id"]

    pa2, _ = await _tenant_member(client)
    res = await client.patch(f"/api/tasks/{tid}", json={"status": "done"}, headers=_auth(pa2))
    assert res.status_code == 404, res.text
