"""Magic-link exchange semantics (prod bug 2026-07-14: member check-in 401s).

A hard single-use-on-first-hit token is consumed by whatever touches the link
first — on M365 that's Defender/Safe Links headless-rendering it to scan, or the
member double-tapping — and the member's real click then 401s on a link that
just worked. These tests pin the fix: idempotent inside the grace window, still
single-use against later replay.
"""

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.db import SessionLocal
from app.models import AuditLog, MagicToken, Member, Tenant
from app.security import generate_magic_token, magic_token_expiry


async def _member() -> str:
    async with SessionLocal() as db:
        t = Tenant(slug=f"ml-{uuid.uuid4().hex[:8]}", name="Magic Link Plan")
        db.add(t)
        await db.flush()
        m = Member(
            tenant_id=t.id,
            external_member_id=f"ext-{uuid.uuid4().hex[:6]}",
            first_name="Casey",
            last_name="Member",
            date_of_birth="1980-01-01",
            sex="F",
            alias="M-ML",
        )
        db.add(m)
        await db.commit()
        return m.id


async def _issue(member_id: str, used_at=None) -> str:
    raw, token_hash = generate_magic_token()
    async with SessionLocal() as db:
        db.add(
            MagicToken(
                member_id=member_id,
                token_hash=token_hash,
                purpose="checkin",
                expires_at=magic_token_expiry(),
                used_at=used_at,
            )
        )
        await db.commit()
    return raw


@pytest.mark.asyncio
async def test_first_use_succeeds_and_marks_used(client):
    member_id = await _member()
    raw = await _issue(member_id)
    res = await client.post("/api/auth/member/verify", json={"token": raw})
    assert res.status_code == 200, res.text
    assert res.json()["first_name"] == "Casey"
    async with SessionLocal() as db:
        magic = (await db.execute(select(MagicToken).where(MagicToken.member_id == member_id))).scalar_one()
    assert magic.used_at is not None


@pytest.mark.asyncio
async def test_scanner_then_member_click_both_succeed(client):
    """The real-world failure: something consumes the link, then the member taps
    seconds later. Both must get a session."""
    member_id = await _member()
    raw = await _issue(member_id)

    scanner = await client.post("/api/auth/member/verify", json={"token": raw})
    assert scanner.status_code == 200

    member_click = await client.post("/api/auth/member/verify", json={"token": raw})
    assert member_click.status_code == 200, "member locked out of their own link"
    assert member_click.json()["token"]


@pytest.mark.asyncio
async def test_reuse_after_grace_is_rejected(client, monkeypatch):
    """Single-use still holds against a link harvested from the mailbox later."""
    monkeypatch.setattr(settings, "magic_reuse_grace_minutes", 10)
    member_id = await _member()
    stale = datetime.utcnow() - timedelta(minutes=11)
    raw = await _issue(member_id, used_at=stale)
    res = await client.post("/api/auth/member/verify", json={"token": raw})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_grace_is_not_extended_by_repeated_hits(client, monkeypatch):
    """used_at is stamped on FIRST use only — otherwise repeated hits would hold
    the window open forever and the token would never expire."""
    monkeypatch.setattr(settings, "magic_reuse_grace_minutes", 10)
    member_id = await _member()
    raw = await _issue(member_id)

    await client.post("/api/auth/member/verify", json={"token": raw})
    async with SessionLocal() as db:
        first = (await db.execute(select(MagicToken).where(MagicToken.member_id == member_id))).scalar_one().used_at

    await client.post("/api/auth/member/verify", json={"token": raw})
    async with SessionLocal() as db:
        second = (await db.execute(select(MagicToken).where(MagicToken.member_id == member_id))).scalar_one().used_at
    assert first == second, "used_at moved — grace window can be held open indefinitely"


@pytest.mark.asyncio
async def test_expired_token_rejected_even_within_grace(client):
    member_id = await _member()
    raw, token_hash = generate_magic_token()
    async with SessionLocal() as db:
        db.add(
            MagicToken(
                member_id=member_id,
                token_hash=token_hash,
                purpose="checkin",
                expires_at=datetime.utcnow() - timedelta(minutes=1),
            )
        )
        await db.commit()
    res = await client.post("/api/auth/member/verify", json={"token": raw})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_unknown_token_rejected(client):
    res = await client.post("/api/auth/member/verify", json={"token": "not-a-real-token"})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_attempts_are_audited_with_reason(client, monkeypatch):
    """The diagnostic that ends the guesswork: a rejection records how long ago
    the token was used, which distinguishes a scanner race from delivery-time
    detonation."""
    monkeypatch.setattr(settings, "magic_reuse_grace_minutes", 10)
    member_id = await _member()
    raw = await _issue(member_id, used_at=datetime.utcnow() - timedelta(minutes=30))
    await client.post("/api/auth/member/verify", json={"token": raw})

    async with SessionLocal() as db:
        entry = (
            await db.execute(
                select(AuditLog).where(AuditLog.action == "magic_verify_rejected").order_by(AuditLog.created_at.desc())
            )
        ).scalars().first()
    assert entry is not None
    assert entry.metadata_json["reason"] == "already_used"
    assert entry.metadata_json["used_age_seconds"] >= 1800
