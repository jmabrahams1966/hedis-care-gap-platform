import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db import SessionLocal
from app.models import (
    OutreachSequence,
    SequenceEnrollment,
    SequenceStep,
    StaffRole,
    StaffUser,
    TenantMeasureConfig,
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


async def _new_tenant(client: AsyncClient) -> tuple[str, str]:
    """Return (payer_admin token, tenant slug) for a fresh mental_health tenant."""
    sa_email, sa_pw = await _make_super_admin()
    sa = await _login(client, sa_email, sa_pw)
    slug = f"ae-{uuid.uuid4().hex[:8]}"
    admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    res = await client.post(
        "/api/tenants",
        json={
            "slug": slug,
            "name": "Auto-Enroll Test Plan",
            "enabled_measures": ["mental_health"],
            "first_admin_email": admin_email,
            "first_admin_password": "admin-password-123",
        },
        headers=_auth(sa),
    )
    assert res.status_code == 200, res.text
    pa = await _login(client, admin_email, "admin-password-123")
    return pa, slug


async def _create_member(client: AsyncClient, pa: str, ext: str) -> str:
    year = date.today().year
    res = await client.post(
        "/api/members",
        json={
            "external_member_id": ext,
            "first_name": "Ada",
            "last_name": "Test",
            "date_of_birth": f"{year - 40}-05-12",
            "sex": "F",
            "email": f"{ext.lower()}@example.com",
            "consent_email": True,
        },
        headers=_auth(pa),
    )
    assert res.status_code == 200, res.text
    return res.json()["id"]


async def _enrollments_for(member_id: str) -> list[SequenceEnrollment]:
    async with SessionLocal() as db:
        return list(
            (
                await db.execute(select(SequenceEnrollment).where(SequenceEnrollment.member_id == member_id))
            ).scalars().all()
        )


@pytest.mark.asyncio
async def test_no_sequence_means_no_enrollment(client: AsyncClient):
    pa, _ = await _new_tenant(client)
    member_id = await _create_member(client, pa, "AE-NOSEQ")
    assert await _enrollments_for(member_id) == []


@pytest.mark.asyncio
async def test_assigned_sequence_auto_enrolls_on_gap_open(client: AsyncClient):
    pa, slug = await _new_tenant(client)
    # Build a sequence and assign it to the tenant's mental_health measure config.
    async with SessionLocal() as db:
        cfg = (
            await db.execute(
                select(TenantMeasureConfig).where(TenantMeasureConfig.measure_code == "mental_health")
            )
        ).scalars().first()
        seq = OutreachSequence(tenant_id=cfg.tenant_id, name="DSF cadence")
        db.add(seq)
        await db.flush()
        db.add(
            SequenceStep(
                sequence_id=seq.id,
                step_order=0,
                offset_days=0,
                channel="email",
                template_key="screening_invite",
                recurring=False,
                repeat_interval_days=None,
            )
        )
        cfg.sequence_id = seq.id
        await db.commit()

    # A new member's mental_health gap should now auto-enroll.
    member_id = await _create_member(client, pa, "AE-SEQ")
    enrolls = await _enrollments_for(member_id)
    assert len(enrolls) == 1
    assert enrolls[0].status == "active"
    assert enrolls[0].current_step_order == 0
