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
async def test_full_tenant_and_screening_flow(client: AsyncClient):
    # --- bootstrap: super_admin creates a tenant with both measures enabled ---
    sa_email, sa_password = await _make_super_admin()
    sa_token = await _login(client, sa_email, sa_password)

    slug = f"acme-{uuid.uuid4().hex[:8]}"
    admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    res = await client.post(
        "/api/tenants",
        json={
            "slug": slug,
            "name": "Acme Health Plan",
            "enabled_measures": ["mental_health", "breast_cancer"],
            "first_admin_email": admin_email,
            "first_admin_password": "admin-password-123",
        },
        headers=_auth(sa_token),
    )
    assert res.status_code == 200, res.text
    tenant_id = res.json()["id"]

    pa_token = await _login(client, admin_email, "admin-password-123")

    # --- measure catalog reflects both enabled, others in the registry left disabled ---
    res = await client.get("/api/tenants/measures/catalog", headers=_auth(pa_token))
    catalog = {m["code"]: m["enabled"] for m in res.json()}
    assert catalog["mental_health"] is True
    assert catalog["breast_cancer"] is True
    assert catalog["colorectal_cancer"] is False

    # --- create a member eligible for BOTH measures (female, 55) ---
    this_year = date.today().year
    res = await client.post(
        "/api/members",
        json={
            "external_member_id": "EXT-TEST-1",
            "first_name": "Fatima",
            "last_name": "Test",
            "date_of_birth": f"{this_year - 55}-05-12",
            "sex": "F",
            "phone": "+15551234567",
            "email": "fatima-test@example.com",
            "preferred_channel": "sms",
            "consent_sms": True,
            "consent_email": True,
        },
        headers=_auth(pa_token),
    )
    assert res.status_code == 200, res.text
    member_external_id = res.json()["external_member_id"]

    # --- disabling breast_cancer stops NEW gaps, doesn't retroactively remove existing ones ---
    res = await client.put(
        f"/api/tenants/{tenant_id}/measures",
        json={"measure_code": "breast_cancer", "enabled": False, "config": {}},
        headers=_auth(pa_token),
    )
    assert res.status_code == 200

    res = await client.post(
        "/api/members",
        json={
            "external_member_id": "EXT-TEST-2",
            "first_name": "Grace",
            "last_name": "Test",
            "date_of_birth": f"{this_year - 60}-02-20",
            "sex": "F",
            "phone": "+15551234568",
            "consent_sms": True,
        },
        headers=_auth(pa_token),
    )
    assert res.status_code == 200

    # --- member magic-link auth (dev mode returns the token directly) ---
    res = await client.post(
        "/api/auth/member/magic",
        json={"external_member_id": member_external_id, "date_of_birth": f"{this_year - 55}-05-12"},
    )
    assert res.status_code == 200
    dev_token = res.json()["dev_token"]

    res = await client.post("/api/auth/member/verify", json={"token": dev_token})
    assert res.status_code == 200
    member_token = res.json()["token"]

    # --- member has both mental_health and breast_cancer gaps pending (created before the toggle) ---
    res = await client.get("/api/screenings/pending", headers=_auth(member_token))
    pending = res.json()
    measures_pending = {g["measure_code"] for g in pending}
    assert measures_pending == {"mental_health", "breast_cancer"}

    mh_gap_id = next(g["care_gap_id"] for g in pending if g["measure_code"] == "mental_health")
    bcs_gap_id = next(g["care_gap_id"] for g in pending if g["measure_code"] == "breast_cancer")

    # --- submit a moderate PHQ-9 (total 10) -> opens a 30-day follow-up, no safety flag ---
    res = await client.post(
        "/api/screenings",
        json={"care_gap_id": mh_gap_id, "responses": {"phq9": [2, 2, 2, 2, 2, 0, 0, 0, 0], "gad7": [1] * 7}},
        headers=_auth(member_token),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "needs_follow_up"
    assert body["safety_flag"] is False
    assert body["needs_follow_up"] is True

    # --- submit BCS: hasn't been screened, wants scheduling help -> follow-up, numerator not met ---
    res = await client.post(
        "/api/screenings",
        json={"care_gap_id": bcs_gap_id, "responses": {"has_completed": False, "wants_scheduling_help": True}},
        headers=_auth(member_token),
    )
    assert res.status_code == 200, res.text
    assert res.json()["needs_follow_up"] is True

    # --- care manager / payer admin: queue shows both gaps ---
    res = await client.get("/api/care-gaps/queue", headers=_auth(pa_token))
    queue = res.json()
    gap_ids_in_queue = {g["id"] for g in queue}
    assert mh_gap_id in gap_ids_in_queue
    assert bcs_gap_id in gap_ids_in_queue

    # --- case detail shows the submission ---
    res = await client.get(f"/api/care-gaps/{mh_gap_id}", headers=_auth(pa_token))
    detail = res.json()
    assert detail["status"] == "needs_follow_up"
    assert detail["submissions"][0]["instrument_scores"]["phq9"]["severity"] == "moderate"

    # --- add a case note ---
    res = await client.post(
        f"/api/care-gaps/{mh_gap_id}/notes", json={"note": "Called member, scheduled follow-up."}, headers=_auth(pa_token)
    )
    assert res.status_code == 200

    # --- exclusion requires a reason ---
    res = await client.patch(f"/api/care-gaps/{bcs_gap_id}/status", json={"status": "excluded"}, headers=_auth(pa_token))
    assert res.status_code == 422

    res = await client.patch(
        f"/api/care-gaps/{bcs_gap_id}/status",
        json={"status": "excluded", "reason": "Member has documented bilateral mastectomy"},
        headers=_auth(pa_token),
    )
    assert res.status_code == 200

    res = await client.get("/api/care-gaps/queue", headers=_auth(pa_token))
    assert bcs_gap_id not in {g["id"] for g in res.json()}

    # --- outreach send to a member with SMS consent on file succeeds ---
    res = await client.get("/api/care-gaps/queue", headers=_auth(pa_token))
    other_open_gap = next(g["id"] for g in res.json() if g["status"] == "open")
    res = await client.post(f"/api/outreach/send/{other_open_gap}", headers=_auth(pa_token))
    assert res.status_code == 200
    assert res.json()["outreach_status"] == "sent"

    # --- HEDIS report: mental_health denominator includes both members, numerator reflects the one screened ---
    res = await client.get(
        f"/api/reports/hedis?measure_code=mental_health&period={this_year}", headers=_auth(pa_token)
    )
    assert res.status_code == 200
    report = res.json()
    assert report["denominator"] >= 2
    assert report["numerator"] >= 1

    # Fatima's breast_cancer gap was excluded, and Grace's member record was created
    # after breast_cancer was disabled for the tenant, so she never got one either —
    # the denominator should be empty.
    res = await client.get(
        f"/api/reports/hedis?measure_code=breast_cancer&period={this_year}", headers=_auth(pa_token)
    )
    bcs_report = res.json()
    assert bcs_report["denominator"] == 0


@pytest.mark.asyncio
async def test_condition_gated_measures_only_open_for_members_with_the_condition(client: AsyncClient):
    """blood_pressure and diabetes_a1c require a diagnosis on file — this is the
    first condition-gated (not just age/sex-gated) measure, worth its own
    end-to-end check via the real roster-ingestion + eligibility path."""
    sa_email, sa_password = await _make_super_admin()
    sa_token = await _login(client, sa_email, sa_password)

    slug = f"condgate-{uuid.uuid4().hex[:8]}"
    admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    res = await client.post(
        "/api/tenants",
        json={
            "slug": slug,
            "name": "Condition Gate Test Plan",
            "enabled_measures": ["blood_pressure", "diabetes_a1c"],
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
            "external_member_id": "COND-1",
            "first_name": "Has",
            "last_name": "Hypertension",
            "date_of_birth": f"{this_year - 50}-01-01",
            "sex": "M",
            "conditions": ["hypertension"],
        },
        headers=_auth(pa_token),
    )
    assert res.status_code == 200

    res = await client.post(
        "/api/members",
        json={
            "external_member_id": "COND-2",
            "first_name": "No",
            "last_name": "Conditions",
            "date_of_birth": f"{this_year - 50}-01-01",
            "sex": "M",
            "conditions": [],
        },
        headers=_auth(pa_token),
    )
    assert res.status_code == 200

    res = await client.get("/api/care-gaps/queue", headers=_auth(pa_token))
    gaps = res.json()
    assert any(g["member_alias"] and g["measure_code"] == "blood_pressure" for g in gaps)
    # exactly one blood_pressure gap total — the member without the condition never got one
    assert sum(1 for g in gaps if g["measure_code"] == "blood_pressure") == 1
    assert sum(1 for g in gaps if g["measure_code"] == "diabetes_a1c") == 0


@pytest.mark.asyncio
async def test_guardian_dependent_flow(client: AsyncClient):
    """Pediatric measures (CIS/WCV) are the first ones where the account
    holder answering outreach isn't the person the measure is about — this
    exercises that whole path: guardian authenticates, sees a gap that's
    actually about their dependent, and submits on the dependent's behalf."""
    sa_email, sa_password = await _make_super_admin()
    sa_token = await _login(client, sa_email, sa_password)

    slug = f"guardiantest-{uuid.uuid4().hex[:8]}"
    admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    res = await client.post(
        "/api/tenants",
        json={
            "slug": slug,
            "name": "Guardian Test Plan",
            "enabled_measures": ["childhood_immunization"],
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
            "external_member_id": "GUARD-1",
            "first_name": "Guardian",
            "last_name": "Test",
            "date_of_birth": f"{this_year - 35}-01-01",
            "sex": "F",
            "phone": "+15559990000",
            "consent_sms": True,
        },
        headers=_auth(pa_token),
    )
    assert res.status_code == 200, res.text
    guardian_id = res.json()["id"]
    guardian_dob = f"{this_year - 35}-01-01"

    # dependent turning 2 this year -> eligible for CIS
    res = await client.post(
        f"/api/members/{guardian_id}/dependents",
        json={
            "external_dependent_id": "KID-1",
            "first_name": "Kiddo",
            "last_name": "Test",
            "date_of_birth": f"{this_year - 2}-06-01",
            "sex": "M",
        },
        headers=_auth(pa_token),
    )
    assert res.status_code == 200, res.text
    dependent_alias = res.json()["alias"]
    assert dependent_alias.startswith("Dependent-")

    # guardian authenticates with their own identity, not the child's
    res = await client.post(
        "/api/auth/member/magic", json={"external_member_id": "GUARD-1", "date_of_birth": guardian_dob}
    )
    dev_token = res.json()["dev_token"]
    res = await client.post("/api/auth/member/verify", json={"token": dev_token})
    guardian_token = res.json()["token"]

    # pending screening is personalized with the dependent's name, not the guardian's
    res = await client.get("/api/screenings/pending", headers=_auth(guardian_token))
    pending = res.json()
    assert len(pending) == 1
    assert pending[0]["measure_code"] == "childhood_immunization"
    assert pending[0]["dependent_first_name"] == "Kiddo"
    cis_gap_id = pending[0]["care_gap_id"]

    # guardian submits on the dependent's behalf
    res = await client.post(
        "/api/screenings",
        json={"care_gap_id": cis_gap_id, "responses": {"has_completed": True}},
        headers=_auth(guardian_token),
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "completed"

    # care manager view shows the dependent's alias, distinct from the guardian's
    res = await client.get(f"/api/care-gaps/{cis_gap_id}", headers=_auth(pa_token))
    detail = res.json()
    assert detail["dependent_alias"] == dependent_alias
    assert detail["member_alias"] != dependent_alias
    assert detail["submissions"][0]["instrument_scores"]["cis"]["has_completed"] is True
