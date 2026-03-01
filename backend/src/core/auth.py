"""Authentication service — JWT tokens, bcrypt passwords, lockout protection."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.db.session import get_db
from src.models.models import AppUser, AuditLog

logger = logging.getLogger("pbxmonitorx.auth")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: str, username: str, role: str) -> tuple[str, datetime]:
    settings = get_settings()
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "exp": expires,
        "type": "access",
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires


def create_refresh_token(user_id: str) -> str:
    settings = get_settings()
    expires = datetime.now(timezone.utc) + timedelta(days=7)
    payload = {"sub": user_id, "exp": expires, "type": "refresh"}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


async def authenticate_user(
    db: AsyncSession, username: str, password: str, ip: str = None
) -> tuple[Optional[AppUser], str]:
    """Authenticate a user. Returns (user, error_message).

    Handles lockout protection: after N failed attempts, locks for M minutes.
    """
    settings = get_settings()
    result = await db.execute(select(AppUser).where(AppUser.username == username))
    user = result.scalar_one_or_none()

    if not user:
        return None, "Invalid username or password"

    if not user.is_active:
        return None, "Account is disabled"

    # Check lockout
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        remaining = int((user.locked_until - datetime.now(timezone.utc)).total_seconds() / 60) + 1
        return None, f"Account locked. Try again in {remaining} minute(s)"

    # Verify password
    if not verify_password(password, user.password_hash):
        new_count = user.failed_login_count + 1
        updates = {"failed_login_count": new_count}

        if new_count >= settings.max_login_attempts:
            lockout_until = datetime.now(timezone.utc) + timedelta(minutes=settings.lockout_minutes)
            updates["locked_until"] = lockout_until
            logger.warning(f"User {username} locked out until {lockout_until} after {new_count} failures")

        await db.execute(update(AppUser).where(AppUser.id == user.id).values(**updates))

        db.add(AuditLog(
            user_id=user.id, username=username, action="user_login_failed",
            target_type="user", target_name=username,
            detail={"attempt": new_count, "ip": ip},
            success=False, error_message="Invalid password",
            ip_address=ip,
        ))
        await db.commit()
        return None, "Invalid username or password"

    # Success — reset failures
    await db.execute(update(AppUser).where(AppUser.id == user.id).values(
        failed_login_count=0, locked_until=None,
        last_login=datetime.now(timezone.utc),
    ))

    db.add(AuditLog(
        user_id=user.id, username=username, action="user_login",
        target_type="user", target_name=username,
        detail={"ip": ip}, success=True, ip_address=ip,
    ))
    await db.commit()
    return user, ""


class CurrentUser:
    """Resolved from JWT token — injected as dependency."""
    def __init__(self, id: UUID, username: str, role: str):
        self.id = id
        self.username = username
        self.role = role


async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> CurrentUser:
    """FastAPI dependency — extracts and validates JWT from Authorization header."""
    if not creds:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(creds.credentials)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    return CurrentUser(
        id=UUID(payload["sub"]),
        username=payload["username"],
        role=payload["role"],
    )


def require_role(*roles: str):
    """Dependency factory — restricts endpoints by role."""
    async def check(user: CurrentUser = Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=403, detail=f"Requires role: {', '.join(roles)}")
        return user
    return check
