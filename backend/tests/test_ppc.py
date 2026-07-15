import uuid
from datetime import date, timedelta

import pytest
from httpx import AsyncClient

from app.db import SessionLocal
from app.measures.ppc_service import measurement_year_for_delivery
from app.measures.prenatal_postpartum import postpartum_care_measure, prenatal_care_measure
from app.models import StaffRole, StaffUser
from app.security import hash_password

TODAY = date(2026, 7, 5)
PPC_MEASURES = ["ppc_prenatal", "ppc_postpartum"]


# --- Measure interface ---


def test_ppc_measures_are_episode_opened_but_self_reportable():
    for m in (prenatal_care_measure, postpartum_care_measure):
        assert m.data_driven is True  # opened from a delivery episode, not demographics
        assert m.accepts_self_report is True  # member can still confirm the visit


def test_ppc_outreach_templates():
    assert prenatal_care_measure.outreach_template == "prenatal_reminder"
    assert postpartum_care_measure.outreach_template == "postpartum_reminder"


def test_ppc_eligibility_is_female_childbearing_age():
    class Subj:
        def __init__(self, dob, sex):
            self.date_of_birth = dob
            self.sex = sex

    assert prenatal_care_measure.is_eligible(Subj("1995-01-01", "F"), TODAY) is True
    assert prenatal_care_measure.is_eligible(Subj("1995-01-01", "M"), TODAY) is False


def test_prenatal_self_report_meets_numerator():
    ev = prenatal_care_measure.evaluate_submission({"had_prenatal_visit": True})
    assert ev["numerator_met"] is True
    assert ev["needs_follow_up"] is False
    assert prenatal_care_measure.follow_up_window_days(ev) is None


def test_prenatal_missing_key_raises():
    with pytest.raises(KeyError):
        prenatal_care_measure.evaluate_submission({})


def test_postpartum_completed_meets_numerator():
    ev = postpartum_care_measure.evaluate_submission({"had_postpartum_visit": True})
    assert ev["numerator_met"] is True
    assert ev["needs_follow_up"] is False


def test_postpartum_not_done_wants_help_opens_14_day_follow_up():
    ev = postpartum_care_measure.evaluate_submission(
        {"had_postpartum_visit": False, "wants_scheduling_help": True}
    )
    assert ev["numerator_met"] is False
    assert ev["needs_follow_up"] is True
    assert postpartum_care_measure.follow_up_window_days(ev) == 14


@pytest.mark.parametrize(
    "delivery,expected_year",
    [
        (date(2025, 10, 7), 2025),  # last day of the prior measurement year
        (date(2025, 10, 8), 2026),  # window rolls to the next measurement year
        (date(2025, 12, 20), 2026),  # Dec delivery → postpartum visit counts in 2026
        (date(2026, 6, 1), 2026),  # mid-year → same calendar year
    ],
)
def test_measurement_year_window(delivery, expected_year):
    assert measurement_year_for_delivery(delivery) == expected_year


# --- Integration: episode → gaps → self-report → report ---


async def _make_super_admin() -> tuple[str, str]:
    email = f"super-{uuid.uuid4().hex[:8]}@example.com"
    async with SessionLocal() as db:
        db.add(
            StaffUser(
                tenant_id=None,
                email=email,
                password_hash=hash_password("test-password-123"),
                role=StaffRole.super_admin.value,
                name="Test Super Admin",
            )
        )
        await db.commit()
    return email, "test-password-123"


async def _login(client: AsyncClient, email: str, password: str) -> str:
    res = await client.post("/api/auth/staff/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["token"]


def _auth(token: str) -> dict:
    return {"authorization": f"Bearer {token}"}


async def _bootstrap(client: AsyncClient) -> tuple[str, str, str]:
    sa_email, sa_password = await _make_super_admin()
    sa_token = await _login(client, sa_email, sa_password)

    admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    res = await client.post(
        "/api/tenants",
        json={
            "slug": f"ppc-{uuid.uuid4().hex[:8]}",
            "name": "PPC Test Plan",
            "enabled_measures": PPC_MEASURES,
            "first_admin_email": admin_email,
            "first_admin_password": "admin-password-123",
        },
        headers=_auth(sa_token),
    )
    assert res.status_code == 200, res.text
    pa_token = await _login(client, admin_email, "admin-password-123")

    year = date.today().year
    dob = f"{year - 30}-06-15"
    member_external_id = f"EXT-{uuid.uuid4().hex[:8]}"
    res = await client.post(
        "/api/members",
        json={
            "external_member_id": member_external_id,
            "first_name": "Ppc",
            "last_name": "Tester",
            "date_of_birth": dob,
            "sex": "F",
            "phone": "+15559991111",
            "consent_sms": True,
        },
        headers=_auth(pa_token),
    )
    assert res.status_code == 200, res.text
    return pa_token, member_external_id, dob


@pytest.mark.asyncio
async def test_episode_opens_both_ppc_gaps(client: AsyncClient):
    pa_token, member_external_id, _ = await _bootstrap(client)
    delivery = (date.today() - timedelta(days=30)).isoformat()

    res = await client.post(
        "/api/maternity/episodes/bulk",
        json=[{"external_member_id": member_external_id, "delivery_date": delivery}],
        headers=_auth(pa_token),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["episodes_created"] == 1
    opened = {g["measure_code"] for g in body["gaps"] if g["opened"]}
    assert opened == {"ppc_prenatal", "ppc_postpartum"}

    res = await client.get("/api/care-gaps/queue", headers=_auth(pa_token))
    codes = {g["measure_code"] for g in res.json()}
    assert {"ppc_prenatal", "ppc_postpartum"} <= codes


@pytest.mark.asyncio
async def test_ingesting_same_episode_twice_is_idempotent(client: AsyncClient):
    pa_token, member_external_id, _ = await _bootstrap(client)
    delivery = (date.today() - timedelta(days=20)).isoformat()
    payload = [{"external_member_id": member_external_id, "delivery_date": delivery, "external_episode_id": "EP-1"}]

    await client.post("/api/maternity/episodes/bulk", json=payload, headers=_auth(pa_token))
    # Second ingest: gaps already exist for this member/measure/period → not re-opened.
    res = await client.post("/api/maternity/episodes/bulk", json=payload, headers=_auth(pa_token))
    assert res.status_code == 200, res.text
    assert all(g["opened"] is False for g in res.json()["gaps"])

    res = await client.get("/api/care-gaps/queue", headers=_auth(pa_token))
    postpartum = [g for g in res.json() if g["measure_code"] == "ppc_postpartum"]
    assert len(postpartum) == 1  # not duplicated


@pytest.mark.asyncio
async def test_two_deliveries_same_year_get_separate_gaps(client: AsyncClient):
    pa_token, member_external_id, _ = await _bootstrap(client)
    year = date.today().year
    payload = [
        {"external_member_id": member_external_id, "delivery_date": f"{year}-02-01", "external_episode_id": "EP-A"},
        {"external_member_id": member_external_id, "delivery_date": f"{year}-05-01", "external_episode_id": "EP-B"},
    ]
    res = await client.post("/api/maternity/episodes/bulk", json=payload, headers=_auth(pa_token))
    assert res.status_code == 200, res.text
    assert res.json()["episodes_created"] == 2
    # 2 deliveries x 2 PPC measures = 4 distinct gaps opened (episode-scoped).
    assert len([g for g in res.json()["gaps"] if g["opened"]]) == 4

    res = await client.get("/api/care-gaps/queue", headers=_auth(pa_token))
    postpartum = [g for g in res.json() if g["measure_code"] == "ppc_postpartum"]
    assert len(postpartum) == 2  # one per delivery, not collapsed into one

    res = await client.get(
        "/api/reports/hedis",
        params={"measure_code": "ppc_postpartum", "period": str(year)},
        headers=_auth(pa_token),
    )
    assert res.json()["denominator"] == 2  # both deliveries count


@pytest.mark.asyncio
async def test_member_can_self_report_postpartum_visit(client: AsyncClient):
    pa_token, member_external_id, dob = await _bootstrap(client)
    delivery = (date.today() - timedelta(days=30)).isoformat()
    await client.post(
        "/api/maternity/episodes/bulk",
        json=[{"external_member_id": member_external_id, "delivery_date": delivery}],
        headers=_auth(pa_token),
    )

    res = await client.post(
        "/api/auth/member/magic", json={"external_member_id": member_external_id, "date_of_birth": dob}
    )
    dev_token = res.json()["dev_token"]
    member_token = (await client.post("/api/auth/member/verify", json={"token": dev_token})).json()["token"]

    # PPC gaps DO appear in the member's screening list (unlike PDC).
    res = await client.get("/api/screenings/pending", headers=_auth(member_token))
    pending = {g["measure_code"]: g["care_gap_id"] for g in res.json()}
    assert "ppc_postpartum" in pending

    res = await client.post(
        "/api/screenings",
        json={"care_gap_id": pending["ppc_postpartum"], "responses": {"had_postpartum_visit": True}},
        headers=_auth(member_token),
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "completed"

    res = await client.get(f"/api/care-gaps/{pending['ppc_postpartum']}", headers=_auth(pa_token))
    detail = res.json()
    assert detail["numerator_met"] is True
    assert detail["numerator_source"] == "self_report"


@pytest.mark.asyncio
async def test_hedis_report_counts_ppc(client: AsyncClient):
    pa_token, member_external_id, dob = await _bootstrap(client)
    delivery = (date.today() - timedelta(days=30)).isoformat()
    await client.post(
        "/api/maternity/episodes/bulk",
        json=[{"external_member_id": member_external_id, "delivery_date": delivery}],
        headers=_auth(pa_token),
    )
    res = await client.get(
        "/api/reports/hedis",
        params={"measure_code": "ppc_postpartum", "period": str(date.today().year)},
        headers=_auth(pa_token),
    )
    assert res.status_code == 200, res.text
    assert res.json()["denominator"] == 1
    assert res.json()["numerator"] == 0  # not met until confirmed
