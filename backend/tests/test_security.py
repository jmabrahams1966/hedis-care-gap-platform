import uuid

import pytest
from httpx import AsyncClient

from app.db import SessionLocal
from app.models import StaffRole, StaffUser
from app.security import hash_password


async def _make_staff(password: str = "correct-horse-battery") -> str:
    email = f"staff-{uuid.uuid4().hex[:8]}@example.com"
    async with SessionLocal() as db:
        db.add(
            StaffUser(
                tenant_id=None,
                email=email,
                password_hash=hash_password(password),
                role=StaffRole.super_admin.value,
                name="Sec Test",
            )
        )
        await db.commit()
    return email


@pytest.mark.asyncio
async def test_security_headers_present(client: AsyncClient):
    res = await client.get("/health")
    assert res.headers.get("x-content-type-options") == "nosniff"
    assert res.headers.get("x-frame-options") == "DENY"
    assert res.headers.get("referrer-policy") == "no-referrer"
    assert "max-age=" in (res.headers.get("strict-transport-security") or "")
    assert res.headers.get("cache-control") == "no-store"


@pytest.mark.asyncio
async def test_wrong_password_returns_401(client: AsyncClient):
    email = await _make_staff()
    res = await client.post("/api/auth/staff/login", json={"email": email, "password": "wrong"})
    assert res.status_code == 401
    assert res.json()["detail"] == "Invalid email or password"


@pytest.mark.asyncio
async def test_account_locks_after_five_failures(client: AsyncClient):
    email = await _make_staff(password="the-right-one-123")

    for _ in range(5):
        res = await client.post("/api/auth/staff/login", json={"email": email, "password": "nope"})
        assert res.status_code == 401

    # 6th attempt — even with the CORRECT password — is refused while locked.
    res = await client.post("/api/auth/staff/login", json={"email": email, "password": "the-right-one-123"})
    assert res.status_code == 429
    assert "locked" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_successful_login_resets_failure_count(client: AsyncClient):
    email = await _make_staff(password="the-right-one-123")

    # A few failures, then a success before the lock threshold.
    for _ in range(3):
        await client.post("/api/auth/staff/login", json={"email": email, "password": "nope"})
    res = await client.post("/api/auth/staff/login", json={"email": email, "password": "the-right-one-123"})
    assert res.status_code == 200

    # Counter reset — four more failures should NOT lock (would need five in a row).
    for _ in range(4):
        res = await client.post("/api/auth/staff/login", json={"email": email, "password": "nope"})
        assert res.status_code == 401

    res = await client.post("/api/auth/staff/login", json={"email": email, "password": "the-right-one-123"})
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_unknown_email_does_not_500(client: AsyncClient):
    res = await client.post("/api/auth/staff/login", json={"email": "nobody@example.com", "password": "x"})
    assert res.status_code == 401
