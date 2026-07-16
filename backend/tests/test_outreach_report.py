import uuid
from datetime import date, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.cadence_service import mark_response_for_gap
from app.db import SessionLocal
from app.models import CareGap, OutreachAttempt, OutreachSequence, StaffRole, StaffUser
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


async def _seed(client: AsyncClient) -> tuple[str, str, str, str]:
    sa_email, sa_pw = await _make_super_admin()
    sa = await _login(client, sa_email, sa_pw)
    slug = f"or-{uuid.uuid4().hex[:8]}"
    admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    res = await client.post(
        "/api/tenants",
        json={
            "slug": slug,
            "name": "Outreach Report Plan",
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
            "external_member_id": "OR-1",
            "first_name": "Ori",
            "last_name": "Test",
            "date_of_birth": f"{year - 40}-05-12",
            "sex": "F",
            "email": "ori@example.com",
            "consent_email": True,
        },
        headers=_auth(pa),
    )
    member_id = res.json()["id"]
    q = await client.get("/api/care-gaps/queue?measure=mental_health", headers=_auth(pa))
    gap_id = q.json()[0]["id"]
    async with SessionLocal() as db:
        tenant_id = (await db.get(CareGap, gap_id)).tenant_id
    return pa, member_id, gap_id, tenant_id


@pytest.mark.asyncio
async def test_outreach_report_aggregates_by_sequence_step_channel(client: AsyncClient):
    pa, member_id, gap_id, tenant_id = await _seed(client)
    year = date.today().year

    async with SessionLocal() as db:
        seq = OutreachSequence(tenant_id=tenant_id, name="DSF cadence")
        db.add(seq)
        await db.flush()

        def _att(sequence_id, step, responded):
            return OutreachAttempt(
                care_gap_id=gap_id,
                member_id=member_id,
                channel="email",
                template_code="screening_invite",
                status="sent",
                sequence_id=sequence_id,
                step_order=step,
                sent_at=datetime(year, 2, 1),
                responded_at=datetime(year, 2, 3) if responded else None,
                response_type="screening_completed" if responded else None,
            )

        db.add(_att(seq.id, 0, True))
        db.add(_att(seq.id, 0, False))
        db.add(_att(None, None, False))  # ad-hoc retry attempt
        await db.commit()

    res = await client.get(f"/api/reports/outreach?period={year}", headers=_auth(pa))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["totals"] == {"sent": 3, "responded": 1, "response_rate": round(1 / 3, 4)}

    seq_row = [r for r in body["rows"] if r["step_order"] == 0][0]
    assert seq_row["sent"] == 2 and seq_row["responded"] == 1 and seq_row["response_rate"] == 0.5
    assert seq_row["sequence_name"] == "DSF cadence"
    adhoc = [r for r in body["rows"] if r["sequence_id"] is None][0]
    assert adhoc["sent"] == 1 and adhoc["sequence_name"] == "Ad-hoc / retry"


@pytest.mark.asyncio
async def test_mark_response_credits_recent_attempt(client: AsyncClient):
    pa, member_id, gap_id, tenant_id = await _seed(client)
    async with SessionLocal() as db:
        db.add(
            OutreachAttempt(
                care_gap_id=gap_id,
                member_id=member_id,
                channel="email",
                template_code="screening_invite",
                status="sent",
                sent_at=datetime.utcnow() - timedelta(days=1),  # within the response window
            )
        )
        await db.commit()

    async with SessionLocal() as db:
        credited = await mark_response_for_gap(db, gap_id, "screening_completed")
        await db.commit()
    assert credited is True

    async with SessionLocal() as db:
        from sqlalchemy import select

        att = (
            await db.execute(select(OutreachAttempt).where(OutreachAttempt.care_gap_id == gap_id))
        ).scalars().first()
        assert att.responded_at is not None and att.response_type == "screening_completed"
