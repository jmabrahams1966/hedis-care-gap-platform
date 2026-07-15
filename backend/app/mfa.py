"""TOTP (RFC 6238) for staff multi-factor auth — standard authenticator-app
compatible (SHA1, 6 digits, 30s period). Implemented on the stdlib rather than a
third-party dependency so the auth path has no extra supply-chain surface; the
implementation is checked against the RFC 6238 test vectors in tests/test_mfa.py.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

DIGITS = 6
PERIOD = 30
ISSUER = "HEDIS Care Gap"


def generate_secret() -> str:
    """A fresh base32 TOTP secret (160 bits, the RFC-recommended length)."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _hotp(secret_b32: str, counter: int) -> str:
    padded = secret_b32 + "=" * (-len(secret_b32) % 8)
    key = base64.b32decode(padded, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(binary % (10**DIGITS)).zfill(DIGITS)


def totp(secret_b32: str, at: float | None = None) -> str:
    t = int(at if at is not None else time.time())
    return _hotp(secret_b32, t // PERIOD)


def verify(secret_b32: str, code: str, at: float | None = None, window: int = 1) -> bool:
    """Verify a code, allowing +/- `window` time steps for clock skew. Constant-time
    compare to avoid a timing oracle on the code."""
    if not secret_b32 or not code or not code.strip().isdigit():
        return False
    code = code.strip().zfill(DIGITS)
    t = int(at if at is not None else time.time())
    counter = t // PERIOD
    ok = False
    # Check every candidate (no early return) so timing doesn't reveal the offset.
    for w in range(-window, window + 1):
        if hmac.compare_digest(_hotp(secret_b32, counter + w), code):
            ok = True
    return ok


def provisioning_uri(secret_b32: str, account: str) -> str:
    """otpauth:// URI an authenticator app scans / imports."""
    label = quote(f"{ISSUER}:{account}")
    return (
        f"otpauth://totp/{label}?secret={secret_b32}"
        f"&issuer={quote(ISSUER)}&algorithm=SHA1&digits={DIGITS}&period={PERIOD}"
    )
