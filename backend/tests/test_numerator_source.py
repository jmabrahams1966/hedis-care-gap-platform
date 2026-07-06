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


async def _bootstrap_bcs_gap(client: AsyncClient) -> tuple[str, str, str]:
    """Returns (payer_admin_token, member_token, bcs_care_gap_id)."""
    sa_email, sa_password = await _make_super_admin()
    sa_token = await _login(client, sa_email, sa_password)

    slug = f"numsrc-{uuid.uuid4().hex[:8]}"
    admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    res = await client.post(
        "/api/tenants",
        json={
            "slug": slug,
            "name": "Numerator Source Test Plan",
            "enabled_measures": ["breast_cancer"],
            "first_admin_email": admin_email,
            "first_admin_password": "admin-password-123",
        },
        headers=_auth(sa_token),
    )
    assert res.status_code == 200, res.text
    pa_token = await _login(client, admin_email, "admin-password-123")

    this_year = date.today().year
    res = await client.post(
        "/api/members",
        json={
            "external_member_id": f"EXT-{uuid.uuid4().hex[:8]}",
            "first_name": "Numerator",
            "last_name": "Test",
            "date_of_birth": f"{this_year - 55}-05-12",
            "sex": "F",
            "phone": "+15559991234",
            "consent_sms": True,
        },
        headers=_auth(pa_token),
    )
    assert res.status_code == 200, res.text
    member_external_id = res.json()["external_member_id"]
    dob = f"{this_year - 55}-05-12"

    res = await client.post(
        "/api/auth/member/magic", json={"external_member_id": member_external_id, "date_of_birth": dob}
    )
    dev_token = res.json()["dev_token"]
    res = await client.post("/api/auth/member/verify", json={"token": dev_token})
    member_token = res.json()["token"]

    res = await client.get("/api/screenings/pending", headers=_auth(member_token))
    bcs_gap_id = next(g["care_gap_id"] for g in res.json() if g["measure_code"] == "breast_cancer")

    return pa_token, member_token, bcs_gap_id


@pytest.mark.asyncio
async def test_self_report_sets_numerator_source(client: AsyncClient):
    pa_token, member_token, gap_id = await _bootstrap_bcs_gap(client)

    res = await client.post(
        "/api/screenings",
        json={"care_gap_id": gap_id, "responses": {"has_completed": True, "completed_date": "2026-01-15"}},
        headers=_auth(member_token),
    )
    assert res.status_code == 200, res.text

    res = await client.get(f"/api/care-gaps/{gap_id}", headers=_auth(pa_token))
    detail = res.json()
    assert detail["numerator_met"] is True
    assert detail["numerator_source"] == "self_report"
    assert detail["numerator_source_reference"] == ""


@pytest.mark.asyncio
async def test_confirm_numerator_requires_reference(client: AsyncClient):
    pa_token, _, gap_id = await _bootstrap_bcs_gap(client)

    res = await client.post(f"/api/care-gaps/{gap_id}/confirm-numerator", json={"reference": ""}, headers=_auth(pa_token))
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_confirm_numerator_upgrades_to_claims_confirmed(client: AsyncClient):
    pa_token, _, gap_id = await _bootstrap_bcs_gap(client)

    res = await client.post(
        f"/api/care-gaps/{gap_id}/confirm-numerator",
        json={"reference": "CLAIM-12345"},
        headers=_auth(pa_token),
    )
    assert res.status_code == 200, res.text
    assert res.json()["numerator_source"] == "claims_confirmed"
    assert res.json()["status"] == "completed"

    res = await client.get(f"/api/care-gaps/{gap_id}", headers=_auth(pa_token))
    detail = res.json()
    assert detail["numerator_met"] is True
    assert detail["numerator_source"] == "claims_confirmed"
    assert detail["numerator_source_reference"] == "CLAIM-12345"
    assert detail["status"] == "completed"


@pytest.mark.asyncio
async def test_later_self_report_does_not_downgrade_claims_confirmed(client: AsyncClient):
    pa_token, member_token, gap_id = await _bootstrap_bcs_gap(client)

    res = await client.post(
        f"/api/care-gaps/{gap_id}/confirm-numerator",
        json={"reference": "CLAIM-99999"},
        headers=_auth(pa_token),
    )
    assert res.status_code == 200, res.text

    # Reopen so the member's next answer isn't blocked by the "already closed" guard.
    res = await client.patch(f"/api/care-gaps/{gap_id}/status", json={"status": "open"}, headers=_auth(pa_token))
    assert res.status_code == 200

    # Member later self-reports a contradicting answer — claims evidence wins.
    res = await client.post(
        "/api/screenings",
        json={"care_gap_id": gap_id, "responses": {"has_completed": False, "wants_scheduling_help": False}},
        headers=_auth(member_token),
    )
    assert res.status_code == 200, res.text

    res = await client.get(f"/api/care-gaps/{gap_id}", headers=_auth(pa_token))
    detail = res.json()
    assert detail["numerator_met"] is True
    assert detail["numerator_source"] == "claims_confirmed"
    assert detail["numerator_source_reference"] == "CLAIM-99999"


@pytest.mark.asyncio
async def test_confirm_numerator_requires_matching_tenant(client: AsyncClient):
    _, _, gap_id = await _bootstrap_bcs_gap(client)

    sa_email, sa_password = await _make_super_admin()
    sa_token = await _login(client, sa_email, sa_password)
    other_admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    res = await client.post(
        "/api/tenants",
        json={
            "slug": f"other-{uuid.uuid4().hex[:8]}",
            "name": "Other Plan",
            "enabled_measures": [],
            "first_admin_email": other_admin_email,
            "first_admin_password": "admin-password-123",
        },
        headers=_auth(sa_token),
    )
    assert res.status_code == 200
    other_token = await _login(client, other_admin_email, "admin-password-123")

    res = await client.post(
        f"/api/care-gaps/{gap_id}/confirm-numerator",
        json={"reference": "CLAIM-SHOULD-NOT-APPLY"},
        headers=_auth(other_token),
    )
    assert res.status_code == 404
