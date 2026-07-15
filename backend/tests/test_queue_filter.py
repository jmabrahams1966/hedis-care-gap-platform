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


@pytest.mark.asyncio
async def test_queue_filters_by_measure(client: AsyncClient):
    sa_email, sa_pw = await _make_super_admin()
    sa = await _login(client, sa_email, sa_pw)
    slug = f"qf-{uuid.uuid4().hex[:8]}"
    admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    res = await client.post(
        "/api/tenants",
        json={
            "slug": slug,
            "name": "Queue Filter Test Plan",
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
            "external_member_id": "QF-1",
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

    # unfiltered queue has both measures' gaps
    res_all = await client.get("/api/care-gaps/queue", headers=_auth(pa))
    assert res_all.status_code == 200
    all_rows = res_all.json()
    assert len(all_rows) == 2

    # filtered queue returns only the requested measure
    res = await client.get("/api/care-gaps/queue?measure=mental_health", headers=_auth(pa))
    assert res.status_code == 200, res.text
    rows = res.json()
    assert rows and all(r["measure_code"] == "mental_health" for r in rows)
    assert len(rows) < len(all_rows)
