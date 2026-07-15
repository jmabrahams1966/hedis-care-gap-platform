import uuid
from datetime import date, datetime

import pytest
from httpx import AsyncClient

from app.db import SessionLocal
from app.models import ScreeningSubmission, StaffRole, StaffUser
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


async def _tenant_member(client: AsyncClient) -> tuple[str, str, str]:
    """Return (payer_admin token, member id, an open mental_health care-gap id)."""
    sa_email, sa_pw = await _make_super_admin()
    sa = await _login(client, sa_email, sa_pw)
    slug = f"sh-{uuid.uuid4().hex[:8]}"
    admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    res = await client.post(
        "/api/tenants",
        json={
            "slug": slug,
            "name": "Screening History Test Plan",
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
            "external_member_id": "SH-1",
            "first_name": "Sam",
            "last_name": "Test",
            "date_of_birth": f"{year - 40}-05-12",
            "sex": "F",
            "email": "sam@example.com",
            "consent_email": True,
        },
        headers=_auth(pa),
    )
    assert res.status_code == 200, res.text
    member_id = res.json()["id"]

    q = await client.get("/api/care-gaps/queue?measure=mental_health", headers=_auth(pa))
    gap_id = q.json()[0]["id"]
    return pa, member_id, gap_id


@pytest.mark.asyncio
async def test_screening_history_returns_scores_chronologically(client: AsyncClient):
    pa, member_id, gap_id = await _tenant_member(client)

    # Insert two DSF submissions out of chronological order to prove the sort.
    async with SessionLocal() as db:
        db.add(
            ScreeningSubmission(
                care_gap_id=gap_id,
                member_id=member_id,
                measure_code="mental_health",
                instrument_scores={"phq9": {"total": 18}, "gad7": {"total": 14}},
                submitted_at=datetime(2026, 3, 1, 10, 0, 0),
            )
        )
        db.add(
            ScreeningSubmission(
                care_gap_id=gap_id,
                member_id=member_id,
                measure_code="mental_health",
                instrument_scores={"phq9": {"total": 9}, "gad7": {"total": 6}},
                submitted_at=datetime(2026, 1, 1, 10, 0, 0),
            )
        )
        await db.commit()

    res = await client.get(
        f"/api/members/{member_id}/screening-history?measure=mental_health", headers=_auth(pa)
    )
    assert res.status_code == 200, res.text
    pts = res.json()
    assert len(pts) == 2
    assert set(pts[0]) >= {"date", "phq9", "gad7"}
    assert pts[0]["date"] <= pts[1]["date"]  # chronological
    assert pts[0]["phq9"] == 9 and pts[0]["gad7"] == 6  # earlier submission first
    assert pts[1]["phq9"] == 18 and pts[1]["gad7"] == 14


@pytest.mark.asyncio
async def test_screening_history_cross_tenant_404(client: AsyncClient):
    pa, member_id, _ = await _tenant_member(client)
    # A second tenant's admin must not read the first tenant's member.
    pa2, _, _ = await _tenant_member(client)
    res = await client.get(
        f"/api/members/{member_id}/screening-history?measure=mental_health", headers=_auth(pa2)
    )
    assert res.status_code == 404, res.text
