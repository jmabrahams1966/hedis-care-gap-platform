import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from .config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_jwt(subject: str, claims: dict, *, expires_delta: timedelta | None = None) -> str:
    payload = {
        "sub": subject,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + (expires_delta or timedelta(hours=settings.jwt_ttl_hours)),
        **claims,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_jwt(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])


def generate_magic_token() -> tuple[str, str]:
    """Returns (raw_token_for_delivery, hash_to_store). Only the hash is persisted —
    a stolen DB row can't be replayed as a login token."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_magic_token(raw)


def hash_magic_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def magic_token_expiry() -> datetime:
    return datetime.utcnow() + timedelta(minutes=settings.magic_ttl_minutes)
