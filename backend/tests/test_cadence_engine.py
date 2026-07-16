import uuid
from datetime import date, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.cadence_service import process_due
from app.db import SessionLocal
from app.models import (
    CareGap,
    OutreachAttempt,
    OutreachSequence,
    SequenceEnrollment,
    SequenceStep,
    StaffRole,
    StaffUser,
)
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


async def _seed_member_gap(client: AsyncClient) -> tuple[str, str, str]:
    """Create a mental_health tenant + member; return (member_id, mh gap_id, tenant_id)."""
    sa_email, sa_pw = await _make_super_admin()
    sa = await _login(client, sa_email, sa_pw)
    slug = f"cad-{uuid.uuid4().hex[:8]}"
    admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    res = await client.post(
        "/api/tenants",
        json={
            "slug": slug,
            "name": "Cadence Test Plan",
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
            "external_member_id": "CAD-1",
            "first_name": "Cade",
            "last_name": "Test",
            "date_of_birth": f"{year - 40}-05-12",
            "sex": "F",
            "email": "cade@example.com",
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
    return member_id, gap_id, tenant_id


async def _make_sequence(db, tenant_id: str, steps: list[tuple]) -> str:
    seq = OutreachSequence(tenant_id=tenant_id, name="DSF cadence")
    db.add(seq)
    await db.flush()
    for i, (offset, channel, tpl, recurring, interval) in enumerate(steps):
        db.add(
            SequenceStep(
                sequence_id=seq.id,
                step_order=i,
                offset_days=offset,
                channel=channel,
                template_key=tpl,
                recurring=recurring,
                repeat_interval_days=interval,
            )
        )
    return seq.id


async def _enroll(db, tenant_id, member_id, gap_id, seq_id):
    db.add(
        SequenceEnrollment(
            tenant_id=tenant_id,
            member_id=member_id,
            care_gap_id=gap_id,
            sequence_id=seq_id,
            status="active",
            current_step_order=0,
            next_send_at=datetime.utcnow() - timedelta(days=1),  # due
        )
    )


async def _attempt_count(member_id: str) -> int:
    async with SessionLocal() as db:
        return (
            await db.execute(
                select(func.count()).select_from(OutreachAttempt).where(OutreachAttempt.member_id == member_id)
            )
        ).scalar_one()


async def _enrollment(member_id: str) -> SequenceEnrollment:
    async with SessionLocal() as db:
        return (
            await db.execute(select(SequenceEnrollment).where(SequenceEnrollment.member_id == member_id))
        ).scalar_one()


@pytest.mark.asyncio
async def test_process_due_sends_advances_and_is_idempotent(client: AsyncClient):
    member_id, gap_id, tenant_id = await _seed_member_gap(client)
    async with SessionLocal() as db:
        seq_id = await _make_sequence(
            db,
            tenant_id,
            [(0, "email", "screening_invite", False, None), (3, "email", "screening_invite", False, None)],
        )
        await _enroll(db, tenant_id, member_id, gap_id, seq_id)
        await db.commit()

    async with SessionLocal() as db:
        await process_due(db)

    assert await _attempt_count(member_id) == 1
    enr = await _enrollment(member_id)
    assert enr.status == "active"
    assert enr.current_step_order == 1  # advanced to step 2
    assert enr.next_send_at > datetime.utcnow()

    # same-day re-run: enrollment is scheduled into the future → nothing sent
    async with SessionLocal() as db:
        await process_due(db)
    assert await _attempt_count(member_id) == 1


@pytest.mark.asyncio
async def test_recurring_step_reschedules_and_stays(client: AsyncClient):
    member_id, gap_id, tenant_id = await _seed_member_gap(client)
    async with SessionLocal() as db:
        seq_id = await _make_sequence(db, tenant_id, [(0, "email", "screening_invite", True, 7)])
        await _enroll(db, tenant_id, member_id, gap_id, seq_id)
        await db.commit()

    async with SessionLocal() as db:
        await process_due(db)

    enr = await _enrollment(member_id)
    assert enr.status == "active"
    assert enr.current_step_order == 0  # stays on the recurring step
    assert enr.next_send_at > datetime.utcnow()  # rescheduled ~7d out


@pytest.mark.asyncio
async def test_finite_sequence_ends_after_last_step(client: AsyncClient):
    member_id, gap_id, tenant_id = await _seed_member_gap(client)
    async with SessionLocal() as db:
        seq_id = await _make_sequence(db, tenant_id, [(0, "email", "screening_invite", False, None)])
        await _enroll(db, tenant_id, member_id, gap_id, seq_id)
        await db.commit()

    async with SessionLocal() as db:
        await process_due(db)

    enr = await _enrollment(member_id)
    assert enr.status == "ended"
    assert enr.ended_reason == "completed"
