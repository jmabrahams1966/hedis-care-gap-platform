import uuid

import pytest
from httpx import AsyncClient

import app.routers.auth as auth_module
from app.config import settings
from app.db import SessionLocal
from app.models import Member


def test_send_sms_no_op_without_origination_number(monkeypatch):
    """With no SMS number provisioned, send_sms must return "" (not raise a boto
    validation error)."""
    from app.notifications import sms_service

    monkeypatch.setattr(settings, "dev_mode", False)
    monkeypatch.setattr(settings, "sms_origination_number", "")
    assert sms_service.send_sms("+15551234567", "hello") == ""


def test_app_base_url_derives_from_cors_origin(monkeypatch):
    monkeypatch.setattr(settings, "cors_origins", "https://app.cogai-payor.com")
    assert settings.app_base_url == "https://app.cogai-payor.com"


async def _make_member(sms: bool = True) -> tuple[str, str]:
    ext = f"EXT-{uuid.uuid4().hex[:8]}"
    dob = "1970-05-05"
    async with SessionLocal() as db:
        db.add(
            Member(
                tenant_id="t-notif",
                external_member_id=ext,
                first_name="Test",
                last_name="Member",
                date_of_birth=dob,
                sex="F",
                phone="+15550009999" if sms else "",
                email="member@example.com",
                preferred_channel="sms" if sms else "email",
                consent_sms=sms,
                consent_email=True,
            )
        )
        await db.commit()
    return ext, dob


@pytest.mark.asyncio
async def test_magic_link_survives_sms_delivery_failure(client: AsyncClient, monkeypatch):
    """The reported bug: a failing SMS send must not 500 the identity flow."""
    ext, dob = await _make_member(sms=True)

    def boom(*a, **k):
        raise RuntimeError("SMS provider exploded")

    monkeypatch.setattr(auth_module, "send_sms", boom)

    res = await client.post("/api/auth/member/magic", json={"external_member_id": ext, "date_of_birth": dob})
    assert res.status_code == 200
    assert res.json()["sent"] is True


@pytest.mark.asyncio
async def test_magic_link_unknown_member_still_ok(client: AsyncClient):
    res = await client.post(
        "/api/auth/member/magic", json={"external_member_id": "EXT-none", "date_of_birth": "2000-01-01"}
    )
    assert res.status_code == 200
    assert res.json()["sent"] is True


async def _make_member_with_phone(phone: str) -> str:
    dob = "1982-07-07"
    async with SessionLocal() as db:
        db.add(
            Member(
                tenant_id="t-phone",
                external_member_id=f"EXT-{uuid.uuid4().hex[:8]}",
                first_name="Phone",
                last_name="Lookup",
                date_of_birth=dob,
                sex="F",
                phone=phone,
                consent_email=False,
                consent_sms=True,
                preferred_channel="email",
            )
        )
        await db.commit()
    return dob


@pytest.mark.asyncio
async def test_magic_by_phone_finds_member_normalizing_format(client: AsyncClient):
    # Unique stored number in E.164; the member types it messily.
    dob = await _make_member_with_phone("+15557778080")
    res = await client.post(
        "/api/auth/member/magic-by-phone", json={"phone": "(555) 777-8080", "date_of_birth": dob}
    )
    assert res.status_code == 200
    assert res.json()["sent"] is True
    assert "dev_token" in res.json()  # matched (dev returns the token only on a hit)


@pytest.mark.asyncio
async def test_magic_by_phone_unknown_is_enumeration_safe(client: AsyncClient):
    res = await client.post(
        "/api/auth/member/magic-by-phone", json={"phone": "+15550000001", "date_of_birth": "1990-01-01"}
    )
    assert res.status_code == 200
    assert res.json()["sent"] is True
    assert "dev_token" not in res.json()  # no match, and no enumeration leak


@pytest.mark.asyncio
async def test_magic_by_phone_wrong_dob_no_match(client: AsyncClient):
    await _make_member_with_phone("+15557778081")
    res = await client.post(
        "/api/auth/member/magic-by-phone", json={"phone": "+15557778081", "date_of_birth": "1900-01-01"}
    )
    assert res.status_code == 200
    assert "dev_token" not in res.json()
