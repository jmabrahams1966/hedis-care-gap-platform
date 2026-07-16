import uuid
from datetime import date, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.cadence_service import end_active_enrollments_for_member
from app.db import SessionLocal
from app.models import CareGap, OutreachSequence, SequenceEnrollment, StaffRole, StaffUser
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


async def _seed(client: AsyncClient) -> tuple[str, str, str, str, str]:
    """Return (payer_admin token, member_id, gap_id, tenant_id, enrollment_id)."""
    sa_email, sa_pw = await _make_super_admin()
    sa = await _login(client, sa_email, sa_pw)
    slug = f"el-{uuid.uuid4().hex[:8]}"
    admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    res = await client.post(
        "/api/tenants",
        json={
            "slug": slug,
            "name": "Enroll Lifecycle Plan",
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
            "external_member_id": "EL-1",
            "first_name": "Eli",
            "last_name": "Test",
            "date_of_birth": f"{year - 40}-05-12",
            "sex": "F",
            "email": "eli@example.com",
            "consent_email": True,
        },
        headers=_auth(pa),
    )
    assert res.status_code == 200, res.text
    member_id = res.json()["id"]
    q = await client.get("/api/care-gaps/queue?measure=mental_health", headers=_auth(pa))
    gap_id = q.json()[0]["id"]
    async with SessionLocal() as db:
        tenant_id = (await db.get(CareGap, gap_id)).tenant_id
        seq = OutreachSequence(tenant_id=tenant_id, name="x")
        db.add(seq)
        await db.flush()
        enr = SequenceEnrollment(
            tenant_id=tenant_id,
            member_id=member_id,
            care_gap_id=gap_id,
            sequence_id=seq.id,
            status="active",
            current_step_order=0,
            next_send_at=datetime.utcnow(),
        )
        db.add(enr)
        await db.commit()
        enrollment_id = enr.id
    return pa, member_id, gap_id, tenant_id, enrollment_id


async def _status(enrollment_id: str) -> SequenceEnrollment:
    async with SessionLocal() as db:
        return await db.get(SequenceEnrollment, enrollment_id)


@pytest.mark.asyncio
async def test_list_pause_end(client: AsyncClient):
    pa, member_id, _, _, eid = await _seed(client)
    lst = await client.get(f"/api/members/{member_id}/enrollments", headers=_auth(pa))
    assert lst.status_code == 200 and len(lst.json()) == 1

    p = await client.post(f"/api/enrollments/{eid}/pause", headers=_auth(pa))
    assert p.status_code == 200 and p.json()["status"] == "paused"

    e = await client.post(f"/api/enrollments/{eid}/end", headers=_auth(pa))
    assert e.status_code == 200 and e.json()["status"] == "ended"
    assert (await _status(eid)).ended_by is not None


@pytest.mark.asyncio
async def test_closing_gap_ends_enrollment(client: AsyncClient):
    pa, _, gap_id, _, eid = await _seed(client)
    r = await client.patch(
        f"/api/care-gaps/{gap_id}/status", json={"status": "closed", "reason": "done"}, headers=_auth(pa)
    )
    assert r.status_code == 200, r.text
    enr = await _status(eid)
    assert enr.status == "ended"
    assert enr.ended_reason == "gap_closed"


@pytest.mark.asyncio
async def test_optout_ends_active_enrollments(client: AsyncClient):
    _, member_id, _, _, eid = await _seed(client)
    async with SessionLocal() as db:
        n = await end_active_enrollments_for_member(db, member_id, "opt_out")
        await db.commit()
    assert n == 1
    enr = await _status(eid)
    assert enr.status == "ended" and enr.ended_reason == "opt_out"


@pytest.mark.asyncio
async def test_enrollment_cross_tenant_404(client: AsyncClient):
    _, _, _, _, eid = await _seed(client)
    pa2, _, _, _, _ = await _seed(client)
    r = await client.post(f"/api/enrollments/{eid}/pause", headers=_auth(pa2))
    assert r.status_code == 404, r.text
