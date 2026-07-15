"""Application-level field encryption for member PII (name / DOB / phone /
email), defense-in-depth beyond Aurora's at-rest KMS encryption — see
docs/SECURITY_HIPAA.md §6.

Uses AES-256-SIV (RFC 5297), which is *deterministic* authenticated encryption:
the same plaintext always yields the same ciphertext under a given key. That's
what lets an equality query (e.g. the magic-link `date_of_birth == …` lookup)
keep working through the ORM — SQLAlchemy encrypts the bound value the same way
the stored value was encrypted. The tradeoff is that equal plaintexts are
visible as equal ciphertexts, which is acceptable for these low-cardinality
identity fields given the DB is already private + encrypted at rest.

`decrypt` is transition-tolerant: a value without the version prefix is assumed
to be legacy plaintext and returned as-is, so deploying the encrypted columns
doesn't break rows written before the data was migrated.
"""

import base64
import hashlib

from cryptography.hazmat.primitives.ciphers.aead import AESSIV
from sqlalchemy import String, Text
from sqlalchemy.types import TypeDecorator

from .config import settings

_PREFIX = "enc:v1:"


def _key() -> bytes:
    raw = settings.pii_encryption_key
    if raw:
        key = base64.b64decode(raw)
        if len(key) != 64:
            raise ValueError("PII_ENCRYPTION_KEY must be 64 bytes (base64) for AES-256-SIV")
        return key
    # Dev/test fallback — a fixed, well-known key. NEVER used in production, where
    # PII_ENCRYPTION_KEY is injected from Secrets Manager.
    return hashlib.sha512(b"hedis-dev-pii-key-not-for-production").digest()


_siv = AESSIV(_key())


def encrypt_pii(plaintext: str) -> str:
    # AES-SIV rejects zero-length input, and an empty string carries no PII to
    # protect — leave it as-is (decrypt passes "" through untouched).
    if plaintext == "":
        return ""
    ct = _siv.encrypt(plaintext.encode("utf-8"), None)
    return _PREFIX + base64.b64encode(ct).decode("ascii")


def decrypt_pii(value: str) -> str:
    if not value.startswith(_PREFIX):
        return value  # legacy plaintext (pre-migration) — transition tolerance
    ct = base64.b64decode(value[len(_PREFIX):])
    return _siv.decrypt(ct, None).decode("utf-8")


class EncryptedString(TypeDecorator):
    """A String column whose value is transparently encrypted at rest and
    decrypted on load. Deterministic, so it can still be used in equality
    filters."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else encrypt_pii(value)

    def process_result_value(self, value, dialect):
        return None if value is None else decrypt_pii(value)


class EncryptedText(TypeDecorator):
    """Like EncryptedString but backed by TEXT, for unbounded free-text PHI
    (clinical notes, care-plan/safety-plan bodies). Same deterministic AES-SIV
    scheme and the same transition tolerance — a pre-existing plaintext value
    decrypts to itself, so an existing TEXT column can be switched to this type
    without migrating stored rows."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else encrypt_pii(value)

    def process_result_value(self, value, dialect):
        return None if value is None else decrypt_pii(value)
