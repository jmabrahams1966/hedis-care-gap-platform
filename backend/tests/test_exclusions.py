import uuid
from datetime import date

import pytest
from httpx import AsyncClient

from app.db import SessionLocal
from app.measures import REGISTRY
from app.measures.breast_cancer import breast_cancer_measure
from app.measures.cervical_cancer import cervical_cancer_measure
from app.measures.diabetes import diabetes_a1c_measure
from app.measures.exclusions import all_known_exclusion_codes, excluding_codes_for, is_excluded
from app.models import StaffRole, StaffUser
from app.security import hash_password


# --- Exclusion policy (pure) ---


def test_hysterectomy_excludes_cervical_only():
    assert is_excluded({"hysterectomy"}, cervical_cancer_measure) is True
    assert is_excluded({"hysterectomy"}, breast_cancer_measure) is False
    assert is_excluded({"hysterectomy"}, diabetes_a1c_measure) is False


def test_broad_exclusions_hit_every_measure():
    for code in ("hospice", "deceased", "palliative_care"):
        assert is_excluded({code}, cervical_cancer_measure) is True
        assert is_excluded({code}, breast_cancer_measure) is True
        assert is_excluded({code}, diabetes_a1c_measure) is True


def test_excluding_codes_for_measure_includes_broad_plus_specific():
    codes = excluding_codes_for(cervical_cancer_measure)
    assert "hysterectomy" in codes
    assert "hospice" in codes


def test_all_known_codes_cover_broad_and_measure_specific():
    known = all_known_exclusion_codes()
    assert {"hospice", "deceased", "hysterectomy", "bilateral_mastectomy"} <= known
    # Every measure's declared exclusions are known.
    for m in REGISTRY.values():
        assert getattr(m, "exclusion_codes", frozenset()) <= known


# --- Integration: ingest exclusion → gap drops out of denominator ---


async def _make_super_admin() -> tuple[str, str]:
    email = f"super-{uuid.uuid4().hex[:8]}@example.com"
    async with SessionLocal() as db:
        db.add(
            StaffUser(
                tenant_id=None,
                email=email,
                password_hash=hash_password("test-password-123"),
                role=StaffRole.super_admin.value,
                name="T",
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


async def _bootstrap(client: AsyncClient, measures: list[str]) -> tuple[str, str]:
    sa_email, sa_password = await _make_super_admin()
    sa_token = await _login(client, sa_email, sa_password)
    admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    res = await client.post(
        "/api/tenants",
        json={
            "slug": f"excl-{uuid.uuid4().hex[:8]}",
            "name": "Exclusion Test Plan",
            "enabled_measures": measures,
            "first_admin_email": admin_email,
            "first_admin_password": "admin-password-123",
        },
        headers=_auth(sa_token),
    )
    assert res.status_code == 200, res.text
    return await _login(client, admin_email, "admin-password-123"), admin_email


async def _create_female_member(client: AsyncClient, pa_token: str) -> str:
    year = date.today().year
    ext = f"EXT-{uuid.uuid4().hex[:8]}"
    res = await client.post(
        "/api/members",
        json={
            "external_member_id": ext,
            "first_name": "Ex",
            "last_name": "Cluded",
            "date_of_birth": f"{year - 45}-03-03",
            "sex": "F",
            "phone": "+15559992222",
            "consent_sms": True,
        },
        headers=_auth(pa_token),
    )
    assert res.status_code == 200, res.text
    return ext


async def _denominator(client: AsyncClient, pa_token: str, measure_code: str) -> int:
    res = await client.get(
        "/api/reports/hedis",
        params={"measure_code": measure_code, "period": str(date.today().year)},
        headers=_auth(pa_token),
    )
    assert res.status_code == 200, res.text
    return res.json()["denominator"]


@pytest.mark.asyncio
async def test_exclusion_removes_gap_from_denominator(client: AsyncClient):
    pa_token, _ = await _bootstrap(client, ["cervical_cancer"])
    ext = await _create_female_member(client, pa_token)

    assert await _denominator(client, pa_token, "cervical_cancer") == 1  # gap opened

    res = await client.post(
        "/api/members/exclusions/bulk",
        json=[{"external_member_id": ext, "exclusion_code": "hysterectomy", "reference": "CLAIM-HYST-1"}],
        headers=_auth(pa_token),
    )
    assert res.status_code == 200, res.text
    assert res.json()["gaps_excluded"] == 1

    assert await _denominator(client, pa_token, "cervical_cancer") == 0  # now excluded


@pytest.mark.asyncio
async def test_broad_exclusion_excludes_multiple_measures(client: AsyncClient):
    pa_token, _ = await _bootstrap(client, ["cervical_cancer", "breast_cancer"])
    # 50-year-old female is eligible for both CCS (21-64) and BCS (50-74).
    year = date.today().year
    ext = f"EXT-{uuid.uuid4().hex[:8]}"
    await client.post(
        "/api/members",
        json={"external_member_id": ext, "first_name": "H", "last_name": "S",
              "date_of_birth": f"{year - 55}-03-03", "sex": "F", "consent_sms": True},
        headers=_auth(pa_token),
    )
    assert await _denominator(client, pa_token, "cervical_cancer") == 1
    assert await _denominator(client, pa_token, "breast_cancer") == 1

    res = await client.post(
        "/api/members/exclusions/bulk",
        json=[{"external_member_id": ext, "exclusion_code": "hospice", "reference": "CLAIM-HOSPICE"}],
        headers=_auth(pa_token),
    )
    assert res.json()["gaps_excluded"] == 2

    assert await _denominator(client, pa_token, "cervical_cancer") == 0
    assert await _denominator(client, pa_token, "breast_cancer") == 0


@pytest.mark.asyncio
async def test_unknown_exclusion_code_reported(client: AsyncClient):
    pa_token, _ = await _bootstrap(client, ["cervical_cancer"])
    ext = await _create_female_member(client, pa_token)
    res = await client.post(
        "/api/members/exclusions/bulk",
        json=[{"external_member_id": ext, "exclusion_code": "not_a_real_code"}],
        headers=_auth(pa_token),
    )
    assert res.status_code == 200, res.text
    assert res.json()["exclusions_created"] == 0
    assert len(res.json()["errors"]) == 1


@pytest.mark.asyncio
async def test_reingesting_exclusion_is_idempotent(client: AsyncClient):
    pa_token, _ = await _bootstrap(client, ["cervical_cancer"])
    ext = await _create_female_member(client, pa_token)
    payload = [{"external_member_id": ext, "exclusion_code": "hysterectomy"}]
    await client.post("/api/members/exclusions/bulk", json=payload, headers=_auth(pa_token))
    res = await client.post("/api/members/exclusions/bulk", json=payload, headers=_auth(pa_token))
    assert res.status_code == 200, res.text
    assert res.json()["exclusions_created"] == 0  # already on file
