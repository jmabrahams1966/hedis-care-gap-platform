import uuid
from datetime import date, timedelta

import pytest
from httpx import AsyncClient

from app.db import SessionLocal
from app.models import StaffRole, StaffUser
from app.security import hash_password

PDC_MEASURES = ["pdc_diabetes", "pdc_hypertension", "pdc_statins"]


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


async def _bootstrap(client: AsyncClient) -> tuple[str, str, str]:
    """Create a tenant with the PDC measures enabled + one adult member.
    Returns (payer_admin_token, member_external_id, dob)."""
    sa_email, sa_password = await _make_super_admin()
    sa_token = await _login(client, sa_email, sa_password)

    admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    res = await client.post(
        "/api/tenants",
        json={
            "slug": f"pdc-{uuid.uuid4().hex[:8]}",
            "name": "PDC Test Plan",
            "enabled_measures": PDC_MEASURES,
            "first_admin_email": admin_email,
            "first_admin_password": "admin-password-123",
        },
        headers=_auth(sa_token),
    )
    assert res.status_code == 200, res.text
    pa_token = await _login(client, admin_email, "admin-password-123")

    year = date.today().year
    dob = f"{year - 60}-04-10"
    member_external_id = f"EXT-{uuid.uuid4().hex[:8]}"
    res = await client.post(
        "/api/members",
        json={
            "external_member_id": member_external_id,
            "first_name": "Pdc",
            "last_name": "Tester",
            "date_of_birth": dob,
            "sex": "M",
            "phone": "+15559990000",
            "consent_sms": True,
        },
        headers=_auth(pa_token),
    )
    assert res.status_code == 200, res.text
    return pa_token, member_external_id, dob


def _adherent_diabetes_fills(member_external_id: str) -> list[dict]:
    """Fills every 25 days from Jan 1 to today with 30-day supply → continuous
    coverage → adherent. Deterministic for any run date past late January."""
    year = date.today().year
    d = date(year, 1, 1)
    fills = []
    i = 0
    while d <= date.today():
        fills.append(
            {
                "external_member_id": member_external_id,
                "drug_class": "diabetes",
                "fill_date": d.isoformat(),
                "days_supply": 30,
                "drug_label": "Metformin 500mg",
                "external_claim_id": f"RX-{member_external_id}-diab-{i}",
            }
        )
        d += timedelta(days=25)
        i += 1
    return fills


def _non_adherent_rasa_fills(member_external_id: str) -> list[dict]:
    """Two January fills, then nothing → low PDC → non-adherent."""
    year = date.today().year
    return [
        {
            "external_member_id": member_external_id,
            "drug_class": "rasa",
            "fill_date": date(year, 1, 1).isoformat(),
            "days_supply": 30,
            "external_claim_id": f"RX-{member_external_id}-rasa-0",
        },
        {
            "external_member_id": member_external_id,
            "drug_class": "rasa",
            "fill_date": date(year, 1, 26).isoformat(),
            "days_supply": 30,
            "external_claim_id": f"RX-{member_external_id}-rasa-1",
        },
    ]


async def _queue_gap(client: AsyncClient, pa_token: str, measure_code: str) -> dict:
    res = await client.get("/api/care-gaps/queue", headers=_auth(pa_token))
    assert res.status_code == 200, res.text
    return next(g for g in res.json() if g["measure_code"] == measure_code)


@pytest.mark.asyncio
async def test_adherent_fills_close_gap_claims_confirmed(client: AsyncClient):
    pa_token, member_external_id, _ = await _bootstrap(client)

    res = await client.post(
        "/api/medications/fills/bulk",
        json=_adherent_diabetes_fills(member_external_id),
        headers=_auth(pa_token),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["errors"] == []
    diab = next(g for g in body["gaps"] if g["measure_code"] == "pdc_diabetes")
    assert diab["eligible"] is True
    assert diab["adherent"] is True

    gap = await _queue_gap_by_status(client, pa_token, "pdc_diabetes")
    assert gap["numerator_met"] is True
    assert gap["numerator_source"] == "claims_confirmed"


async def _queue_gap_by_status(client: AsyncClient, pa_token: str, measure_code: str) -> dict:
    # Adherent gaps are 'completed' (closed), so query that status explicitly.
    res = await client.get("/api/care-gaps/queue", params={"status": "completed"}, headers=_auth(pa_token))
    assert res.status_code == 200, res.text
    return next(g for g in res.json() if g["measure_code"] == measure_code)


@pytest.mark.asyncio
async def test_non_adherent_fills_open_gap_not_met(client: AsyncClient):
    pa_token, member_external_id, _ = await _bootstrap(client)

    res = await client.post(
        "/api/medications/fills/bulk",
        json=_non_adherent_rasa_fills(member_external_id),
        headers=_auth(pa_token),
    )
    assert res.status_code == 200, res.text
    rasa = next(g for g in res.json()["gaps"] if g["measure_code"] == "pdc_hypertension")
    assert rasa["eligible"] is True
    assert rasa["adherent"] is False

    gap = await _queue_gap(client, pa_token, "pdc_hypertension")
    assert gap["numerator_met"] is False
    assert gap["status"] == "open"


@pytest.mark.asyncio
async def test_single_fill_opens_no_gap(client: AsyncClient):
    pa_token, member_external_id, _ = await _bootstrap(client)
    year = date.today().year
    res = await client.post(
        "/api/medications/fills/bulk",
        json=[
            {
                "external_member_id": member_external_id,
                "drug_class": "statins",
                "fill_date": date(year, 3, 1).isoformat(),
                "days_supply": 30,
            }
        ],
        headers=_auth(pa_token),
    )
    assert res.status_code == 200, res.text
    statins = next(g for g in res.json()["gaps"] if g["measure_code"] == "pdc_statins")
    assert statins["eligible"] is False

    res = await client.get("/api/care-gaps/queue", headers=_auth(pa_token))
    assert not any(g["measure_code"] == "pdc_statins" for g in res.json())


@pytest.mark.asyncio
async def test_unknown_drug_class_reported_as_error(client: AsyncClient):
    pa_token, member_external_id, _ = await _bootstrap(client)
    res = await client.post(
        "/api/medications/fills/bulk",
        json=[
            {
                "external_member_id": member_external_id,
                "drug_class": "antibiotics",
                "fill_date": date(date.today().year, 2, 1).isoformat(),
                "days_supply": 10,
            }
        ],
        headers=_auth(pa_token),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["fills_created"] == 0
    assert len(body["errors"]) == 1
    assert "drug_class" in body["errors"][0]["error"]


@pytest.mark.asyncio
async def test_hedis_report_counts_pdc_numerator(client: AsyncClient):
    pa_token, member_external_id, _ = await _bootstrap(client)
    await client.post(
        "/api/medications/fills/bulk",
        json=_adherent_diabetes_fills(member_external_id),
        headers=_auth(pa_token),
    )
    res = await client.get(
        "/api/reports/hedis",
        params={"measure_code": "pdc_diabetes", "period": str(date.today().year)},
        headers=_auth(pa_token),
    )
    assert res.status_code == 200, res.text
    report = res.json()
    assert report["denominator"] == 1
    assert report["numerator"] == 1
    assert report["rate"] == 1.0


@pytest.mark.asyncio
async def test_pdc_gap_rejects_member_self_report(client: AsyncClient):
    pa_token, member_external_id, dob = await _bootstrap(client)
    await client.post(
        "/api/medications/fills/bulk",
        json=_non_adherent_rasa_fills(member_external_id),
        headers=_auth(pa_token),
    )
    gap = await _queue_gap(client, pa_token, "pdc_hypertension")

    # Log in as the member and try to submit a screening against the PDC gap.
    res = await client.post(
        "/api/auth/member/magic", json={"external_member_id": member_external_id, "date_of_birth": dob}
    )
    dev_token = res.json()["dev_token"]
    res = await client.post("/api/auth/member/verify", json={"token": dev_token})
    member_token = res.json()["token"]

    # It must not appear in the member's screening list...
    res = await client.get("/api/screenings/pending", headers=_auth(member_token))
    assert not any(g["measure_code"] == "pdc_hypertension" for g in res.json())

    # ...and a direct submit is rejected.
    res = await client.post(
        "/api/screenings",
        json={"care_gap_id": gap["id"], "responses": {"anything": True}},
        headers=_auth(member_token),
    )
    assert res.status_code == 422
