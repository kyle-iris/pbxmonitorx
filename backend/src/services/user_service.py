"""User service — stateless functions for user CRUD, SSO provisioning, and audit logging."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import hash_password
from src.models.models import AppUser, AuditLog

logger = logging.getLogger("pbxmonitorx.user_service")

# Fields safe to expose in API responses (never includes password_hash).
_USER_PUBLIC_FIELDS = (
    "id", "username", "email", "role", "is_active", "auth_method",
    "display_name", "last_login", "created_at", "updated_at", "azure_oid",
)


def _user_to_dict(user: AppUser) -> dict:
    """Serialize an AppUser to a dict, excluding sensitive fields."""
    return {
        field: (
            str(getattr(user, field))
            if isinstance(getattr(user, field), UUID)
            else (
                getattr(user, field).isoformat()
                if isinstance(getattr(user, field), datetime)
                else getattr(user, field)
            )
        )
        for field in _USER_PUBLIC_FIELDS
        if hasattr(user, field)
    }


async def list_users(db: AsyncSession) -> list[dict]:
    """Return all users without password_hash."""
    result = await db.execute(
        select(AppUser).order_by(AppUser.created_at.desc())
    )
    return [_user_to_dict(u) for u in result.scalars().all()]


async def get_user(db: AsyncSession, user_id: UUID) -> Optional[dict]:
    """Get a single user by ID. Returns None if not found."""
    result = await db.execute(
        select(AppUser).where(AppUser.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        return None
    return _user_to_dict(user)


async def get_user_model(db: AsyncSession, user_id: UUID) -> Optional[AppUser]:
    """Get a single user ORM instance by ID. For internal use."""
    result = await db.execute(
        select(AppUser).where(AppUser.id == user_id)
    )
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    username: str,
    email: str,
    password: str,
    role: str,
    display_name: Optional[str],
    created_by: UUID,
) -> dict:
    """Create a local user with hashed password and audit log entry.

    Raises:
        ValueError: If username or email already exists.
    """
    # Check for duplicate username
    existing = await db.execute(
        select(AppUser).where(AppUser.username == username)
    )
    if existing.scalar_one_or_none():
        raise ValueError(f"Username '{username}' already exists")

    # Check for duplicate email
    if email:
        existing_email = await db.execute(
            select(AppUser).where(AppUser.email == email)
        )
        if existing_email.scalar_one_or_none():
            raise ValueError(f"Email '{email}' already exists")

    user = AppUser(
        username=username,
        email=email,
        password_hash=hash_password(password),
        role=role,
        auth_method="local",
        display_name=display_name or username,
        is_active=True,
    )
    db.add(user)
    await db.flush()  # Populate user.id

    db.add(AuditLog(
        user_id=created_by,
        action="user_created",
        target_type="user",
        target_id=user.id,
        target_name=username,
        detail={"role": role, "auth_method": "local"},
        success=True,
    ))
    await db.flush()

    logger.info("User '%s' created by %s with role '%s'", username, created_by, role)
    return _user_to_dict(user)


async def update_user(
    db: AsyncSession,
    user_id: UUID,
    updates: dict,
    updated_by: UUID,
) -> Optional[dict]:
    """Partial update of a user. Returns updated user dict or None if not found.

    Allowed fields: email, role, is_active, display_name, password.
    If 'password' is in updates it will be hashed before storage.
    """
    result = await db.execute(
        select(AppUser).where(AppUser.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        return None

    allowed_fields = {"email", "role", "is_active", "display_name"}
    db_updates: dict = {}
    audit_detail: dict = {}

    for field in allowed_fields:
        if field in updates:
            db_updates[field] = updates[field]
            audit_detail[field] = updates[field]

    # Handle password separately — hash it
    if "password" in updates and updates["password"]:
        db_updates["password_hash"] = hash_password(updates["password"])
        audit_detail["password_changed"] = True

    if not db_updates:
        return _user_to_dict(user)

    db_updates["updated_at"] = datetime.now(timezone.utc)

    await db.execute(
        sa_update(AppUser).where(AppUser.id == user_id).values(**db_updates)
    )

    db.add(AuditLog(
        user_id=updated_by,
        action="user_updated",
        target_type="user",
        target_id=user_id,
        target_name=user.username,
        detail=audit_detail,
        success=True,
    ))
    await db.flush()

    # Re-read to return fresh data
    refreshed = await db.execute(
        select(AppUser).where(AppUser.id == user_id)
    )
    updated_user = refreshed.scalar_one_or_none()
    logger.info("User '%s' updated by %s: %s", user.username, updated_by, list(audit_detail.keys()))
    return _user_to_dict(updated_user) if updated_user else None


async def deactivate_user(
    db: AsyncSession,
    user_id: UUID,
    deactivated_by: UUID,
) -> bool:
    """Soft-delete a user by setting is_active=False. Returns True on success."""
    result = await db.execute(
        select(AppUser).where(AppUser.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        return False

    await db.execute(
        sa_update(AppUser)
        .where(AppUser.id == user_id)
        .values(is_active=False, updated_at=datetime.now(timezone.utc))
    )

    db.add(AuditLog(
        user_id=deactivated_by,
        action="user_deactivated",
        target_type="user",
        target_id=user_id,
        target_name=user.username,
        detail={"deactivated_by": str(deactivated_by)},
        success=True,
    ))
    await db.flush()

    logger.info("User '%s' deactivated by %s", user.username, deactivated_by)
    return True


async def reset_password(
    db: AsyncSession,
    user_id: UUID,
    new_password: str,
    reset_by: UUID,
) -> bool:
    """Reset a user's password. Returns True on success."""
    result = await db.execute(
        select(AppUser).where(AppUser.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        return False

    if user.auth_method != "local":
        raise ValueError("Cannot reset password for SSO users")

    await db.execute(
        sa_update(AppUser)
        .where(AppUser.id == user_id)
        .values(
            password_hash=hash_password(new_password),
            failed_login_count=0,
            locked_until=None,
            updated_at=datetime.now(timezone.utc),
        )
    )

    db.add(AuditLog(
        user_id=reset_by,
        action="user_password_reset",
        target_type="user",
        target_id=user_id,
        target_name=user.username,
        detail={"reset_by": str(reset_by)},
        success=True,
    ))
    await db.flush()

    logger.info("Password reset for user '%s' by %s", user.username, reset_by)
    return True


async def find_or_create_sso_user(
    db: AsyncSession,
    azure_oid: str,
    email: str,
    display_name: Optional[str],
) -> AppUser:
    """Find an existing user by Azure OID, or auto-create a new viewer account.

    Used by the SSO callback to provision just-in-time users.
    """
    # Try to find by Azure OID first
    result = await db.execute(
        select(AppUser).where(AppUser.azure_oid == azure_oid)
    )
    user = result.scalar_one_or_none()

    if user:
        # Update last login and SSO sync timestamp
        await db.execute(
            sa_update(AppUser)
            .where(AppUser.id == user.id)
            .values(
                last_login=datetime.now(timezone.utc),
                last_sso_sync=datetime.now(timezone.utc),
                display_name=display_name or user.display_name,
                email=email or user.email,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await db.flush()

        # Re-fetch for fresh state
        result = await db.execute(
            select(AppUser).where(AppUser.id == user.id)
        )
        user = result.scalar_one_or_none()
        logger.info("SSO login for existing user '%s' (oid=%s)", user.username, azure_oid)
        return user

    # Also try to find by email — link existing account to SSO
    if email:
        result = await db.execute(
            select(AppUser).where(AppUser.email == email)
        )
        user = result.scalar_one_or_none()
        if user:
            await db.execute(
                sa_update(AppUser)
                .where(AppUser.id == user.id)
                .values(
                    azure_oid=azure_oid,
                    auth_method="azure_ad",
                    last_login=datetime.now(timezone.utc),
                    last_sso_sync=datetime.now(timezone.utc),
                    display_name=display_name or user.display_name,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await db.flush()

            result = await db.execute(
                select(AppUser).where(AppUser.id == user.id)
            )
            user = result.scalar_one_or_none()
            logger.info(
                "SSO login linked to existing user '%s' by email (oid=%s)",
                user.username, azure_oid,
            )
            return user

    # Create new user — derive username from email or display_name
    username = email.split("@")[0] if email else display_name or azure_oid
    # Ensure username uniqueness
    base_username = username
    suffix = 0
    while True:
        existing = await db.execute(
            select(AppUser).where(AppUser.username == username)
        )
        if not existing.scalar_one_or_none():
            break
        suffix += 1
        username = f"{base_username}{suffix}"

    from src.core.config import get_settings
    settings = get_settings()

    user = AppUser(
        username=username,
        email=email,
        password_hash=None,
        role=settings.azure_ad_default_role,
        auth_method="azure_ad",
        azure_oid=azure_oid,
        display_name=display_name or username,
        is_active=True,
        last_login=datetime.now(timezone.utc),
        last_sso_sync=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()

    db.add(AuditLog(
        user_id=user.id,
        action="user_sso_created",
        target_type="user",
        target_id=user.id,
        target_name=username,
        detail={
            "azure_oid": azure_oid,
            "email": email,
            "role": settings.azure_ad_default_role,
            "auto_created": True,
        },
        success=True,
    ))
    await db.flush()

    logger.info(
        "SSO auto-created user '%s' (oid=%s) with role '%s'",
        username, azure_oid, settings.azure_ad_default_role,
    )
    return user
