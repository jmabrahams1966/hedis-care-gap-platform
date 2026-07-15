import uuid
from datetime import date

import pytest
from httpx import AsyncClient

from app.crypto import EncryptedString, decrypt_pii, encrypt_pii
from app.db import SessionLocal
from app.models import Member, StaffRole, StaffUser
from app.security import hash_password


# --- Cipher (unit) ---


def test_roundtrip():
    assert decrypt_pii(encrypt_pii("Jane Doe")) == "Jane Doe"
    assert decrypt_pii(encrypt_pii("1995-09-08")) == "1995-09-08"
    assert decrypt_pii(encrypt_pii("")) == ""


def test_deterministic_so_equality_queries_work():
    # Same plaintext -> identical ciphertext (required for the DOB lookup).
    assert encrypt_pii("1980-01-01") == encrypt_pii("1980-01-01")
    assert encrypt_pii("a@b.com") != encrypt_pii("c@d.com")


def test_ciphertext_is_prefixed_and_not_plaintext():
    ct = encrypt_pii("+15551234567")
    assert ct.startswith("enc:v1:")
    assert "+15551234567" not in ct


def test_decrypt_passthrough_for_legacy_plaintext():
    # A pre-migration plaintext value decrypts to itself (transition tolerance).
    assert decrypt_pii("1990-12-25") == "1990-12-25"


def test_type_decorator_bind_and_load():
    t = EncryptedString(512)
    bound = t.process_bind_param("dob-value", None)
    assert bound.startswith("enc:v1:")
    assert t.process_result_value(bound, None) == "dob-value"
    assert t.process_bind_param(None, None) is None
    assert t.process_result_value(None, None) is None


# --- Round-trip through the DB, incl. the deterministic DOB lookup ---


@pytest.mark.asyncio
async def test_member_pii_encrypted_at_rest_but_readable(client: AsyncClient):
    # `client` fixture creates the schema. Insert a member directly.
    ext = f"EXT-{uuid.uuid4().hex[:8]}"
    dob = "1988-03-14"
    async with SessionLocal() as db:
        # need a tenant id; reuse a throwaway one (FK not enforced on sqlite)
        m = Member(
            tenant_id="t-crypto",
            external_member_id=ext,
            first_name="Alice",
            last_name="Nguyen",
            date_of_birth=dob,
            sex="F",
            phone="+15550001234",
            email="alice@example.com",
        )
        db.add(m)
        await db.commit()
        mid = m.id

    # Read back via the ORM → decrypted transparently.
    async with SessionLocal() as db:
        m = await db.get(Member, mid)
        assert m.first_name == "Alice"
        assert m.date_of_birth == dob
        assert m.email == "alice@example.com"

    # The raw stored value is ciphertext, not plaintext.
    async with SessionLocal() as db:
        from sqlalchemy import text

        raw = (await db.execute(text("SELECT date_of_birth FROM members WHERE id = :id"), {"id": mid})).scalar_one()
        assert raw.startswith("enc:v1:")
        assert dob not in raw

    # Equality query on the encrypted DOB still works (the magic-link lookup).
    async with SessionLocal() as db:
        from sqlalchemy import select

        found = (
            await db.execute(select(Member).where(Member.external_member_id == ext, Member.date_of_birth == dob))
        ).scalar_one_or_none()
        assert found is not None
        assert found.id == mid
