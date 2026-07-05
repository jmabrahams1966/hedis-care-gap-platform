from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_db
from .models import Member, StaffUser
from .security import decode_jwt

bearer = HTTPBearer(auto_error=False)


async def _decode(creds: HTTPAuthorizationCredentials | None) -> dict:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing credentials")
    try:
        return decode_jwt(creds.credentials)
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")


async def get_current_staff(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> StaffUser:
    claims = await _decode(creds)
    if claims.get("kind") != "staff":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Staff token required")
    user = await db.get(StaffUser, claims["sub"])
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


async def get_current_member(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> Member:
    claims = await _decode(creds)
    if claims.get("kind") != "member":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Member token required")
    member = await db.get(Member, claims["sub"])
    if member is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Member not found")
    return member


def require_role(*roles: str):
    async def checker(staff: StaffUser = Depends(get_current_staff)) -> StaffUser:
        if staff.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return staff

    return checker


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "")
