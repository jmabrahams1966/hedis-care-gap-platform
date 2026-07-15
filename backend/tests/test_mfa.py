import base64
import uuid

import pytest
from httpx import AsyncClient

from app import mfa
from app.db import SessionLocal
from app.models import StaffRole, StaffUser
from app.security import hash_password

# RFC 6238 test seed for SHA1: the ASCII string "12345678901234567890".
RFC_SECRET = base64.b32encode(b"12345678901234567890").decode().rstrip("=")


# --- TOTP core (checked against RFC 6238 test vectors) ---


@pytest.mark.parametrize(
    "unix_time,expected6",
    [
        (59, "287082"),        # RFC vector 94287082 -> low 6 digits
        (1111111109, "081804"),  # 07081804
        (1111111111, "050471"),  # 14050471
        (1234567890, "005924"),  # 89005924
        (2000000000, "279037"),  # 69279037
    ],
)
def test_totp_matches_rfc6238(unix_time, expected6):
    assert mfa.totp(RFC_SECRET, at=unix_time) == expected6


def test_verify_accepts_current_and_adjacent_windows():
    t = 1234567890
    assert mfa.verify(RFC_SECRET, mfa.totp(RFC_SECRET, at=t), at=t) is True
    # previous and next 30s step accepted (clock skew tolerance)
    assert mfa.verify(RFC_SECRET, mfa.totp(RFC_SECRET, at=t - 30), at=t) is True
    assert mfa.verify(RFC_SECRET, mfa.totp(RFC_SECRET, at=t + 30), at=t) is True
    # two steps away is rejected
    assert mfa.verify(RFC_SECRET, mfa.totp(RFC_SECRET, at=t - 90), at=t) is False


def test_verify_rejects_garbage():
    assert mfa.verify(RFC_SECRET, "", at=59) is False
    assert mfa.verify(RFC_SECRET, "abcdef", at=59) is False
    assert mfa.verify(RFC_SECRET, "000000", at=59) is False


def test_generate_secret_is_base32():
    s = mfa.generate_secret()
    base64.b32decode(s + "=" * (-len(s) % 8))  # decodes without error
    assert "otpauth://totp/" in mfa.provisioning_uri(s, "user@example.com")


# --- Enrollment + login challenge flow ---


async def _make_staff() -> tuple[str, str]:
    email = f"mfa-{uuid.uuid4().hex[:8]}@example.com"
    async with SessionLocal() as db:
        db.add(
            StaffUser(
                tenant_id=None,
                email=email,
                password_hash=hash_password("pw-correct-123"),
                role=StaffRole.super_admin.value,
                name="MFA Test",
            )
        )
        await db.commit()
    return email, "pw-correct-123"


def _auth(t: str) -> dict:
    return {"authorization": f"Bearer {t}"}


@pytest.mark.asyncio
async def test_full_mfa_enrollment_and_login(client: AsyncClient):
    email, password = await _make_staff()

    # Plain login (no MFA yet) returns a token directly.
    res = await client.post("/api/auth/staff/login", json={"email": email, "password": password})
    assert res.status_code == 200
    token = res.json()["token"]

    # Enroll → get a secret.
    res = await client.post("/api/auth/staff/mfa/enroll", json={}, headers=_auth(token))
    assert res.status_code == 200, res.text
    secret = res.json()["secret"]
    assert res.json()["otpauth_uri"].startswith("otpauth://totp/")

    # Confirm with the current code → MFA enabled.
    res = await client.post("/api/auth/staff/mfa/confirm", json={"code": mfa.totp(secret)}, headers=_auth(token))
    assert res.status_code == 200, res.text
    assert res.json()["mfa_enabled"] is True

    # Now login returns a challenge, NOT a session token.
    res = await client.post("/api/auth/staff/login", json={"email": email, "password": password})
    assert res.status_code == 200
    body = res.json()
    assert body.get("mfa_required") is True
    assert "token" not in body
    mfa_token = body["mfa_token"]

    # Wrong code is rejected.
    res = await client.post("/api/auth/staff/mfa/verify", json={"mfa_token": mfa_token, "code": "000000"})
    assert res.status_code == 401

    # Correct code completes the login.
    res = await client.post(
        "/api/auth/staff/mfa/verify", json={"mfa_token": mfa_token, "code": mfa.totp(secret)}
    )
    assert res.status_code == 200, res.text
    assert "token" in res.json()


@pytest.mark.asyncio
async def test_mfa_confirm_rejects_bad_code(client: AsyncClient):
    email, password = await _make_staff()
    token = (await client.post("/api/auth/staff/login", json={"email": email, "password": password})).json()["token"]
    await client.post("/api/auth/staff/mfa/enroll", json={}, headers=_auth(token))
    res = await client.post("/api/auth/staff/mfa/confirm", json={"code": "111111"}, headers=_auth(token))
    assert res.status_code == 400
    # Still disabled → plain login works.
    res = await client.post("/api/auth/staff/login", json={"email": email, "password": password})
    assert "token" in res.json()


@pytest.mark.asyncio
async def test_mfa_disable_requires_code(client: AsyncClient):
    email, password = await _make_staff()
    token = (await client.post("/api/auth/staff/login", json={"email": email, "password": password})).json()["token"]
    secret = (await client.post("/api/auth/staff/mfa/enroll", json={}, headers=_auth(token))).json()["secret"]
    await client.post("/api/auth/staff/mfa/confirm", json={"code": mfa.totp(secret)}, headers=_auth(token))

    # Re-login through MFA to get a fresh session token.
    ch = (await client.post("/api/auth/staff/login", json={"email": email, "password": password})).json()
    tok2 = (await client.post("/api/auth/staff/mfa/verify", json={"mfa_token": ch["mfa_token"], "code": mfa.totp(secret)})).json()["token"]

    # Bad code can't disable.
    res = await client.post("/api/auth/staff/mfa/disable", json={"code": "000000"}, headers=_auth(tok2))
    assert res.status_code == 400
    # Correct code disables → plain login again.
    res = await client.post("/api/auth/staff/mfa/disable", json={"code": mfa.totp(secret)}, headers=_auth(tok2))
    assert res.status_code == 200
    assert "token" in (await client.post("/api/auth/staff/login", json={"email": email, "password": password})).json()
