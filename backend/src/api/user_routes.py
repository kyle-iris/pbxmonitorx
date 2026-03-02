"""User management API routes — admin-only CRUD with audit logging.

Endpoints:
  GET    /users          List all users (admin)
  POST   /users          Create user (admin)
  GET    /users/me       Get current authenticated user
  GET    /users/{id}     Get specific user (admin)
  PATCH  /users/{id}     Update user (admin)
  DELETE /users/{id}     Deactivate user (admin, soft-delete)
  POST   /users/{id}/reset-password   Reset password (admin)
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import get_current_user, require_role, CurrentUser
from src.db.session import get_db
from src.services import user_service

logger = logging.getLogger("pbxmonitorx.api.users")

router = APIRouter(prefix="/users", tags=["Users"])

# Valid roles for validation
VALID_ROLES = {"viewer", "operator", "admin"}


# ═══════════════════════════════════════════════════════════════════════════
# LIST USERS (admin only)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("")
async def list_users(
    admin: CurrentUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """List all users. Returns public fields only — never exposes password_hash."""
    users = await user_service.list_users(db)
    return {"users": users, "count": len(users)}


# ═══════════════════════════════════════════════════════════════════════════
# GET CURRENT USER (any authenticated user)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/me")
async def get_current_user_info(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the currently authenticated user's profile."""
    user_data = await user_service.get_user(db, user.id)
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user_data


# ═══════════════════════════════════════════════════════════════════════════
# CREATE USER (admin only)
# ═══════════════════════════════════════════════════════════════════════════

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(
    request: Request,
    admin: CurrentUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Create a new local user. Requires admin role.

    Body: { username, email, password, role, display_name }
    """
    body = await request.json()

    # Validate required fields
    username = (body.get("username") or "").strip()
    email = (body.get("email") or "").strip()
    password = body.get("password", "")
    role = (body.get("role") or "viewer").strip().lower()
    display_name = (body.get("display_name") or "").strip() or None

    if not username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username is required",
        )
    if len(username) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username must be at least 3 characters",
        )
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is required",
        )
    if not password or len(password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters",
        )
    if role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Role must be one of: {', '.join(sorted(VALID_ROLES))}",
        )

    try:
        user_data = await user_service.create_user(
            db=db,
            username=username,
            email=email,
            password=password,
            role=role,
            display_name=display_name,
            created_by=admin.id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    logger.info("Admin '%s' created user '%s'", admin.username, username)
    return user_data


# ═══════════════════════════════════════════════════════════════════════════
# GET USER BY ID (admin only)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/{user_id}")
async def get_user(
    user_id: UUID,
    admin: CurrentUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific user by ID. Requires admin role."""
    user_data = await user_service.get_user(db, user_id)
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user_data


# ═══════════════════════════════════════════════════════════════════════════
# UPDATE USER (admin only)
# ═══════════════════════════════════════════════════════════════════════════

@router.patch("/{user_id}")
async def update_user(
    user_id: UUID,
    request: Request,
    admin: CurrentUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Partial update of a user. Requires admin role.

    Updatable fields: email, role, is_active, display_name, password.
    Admin cannot change their own role (safety guard).
    """
    body = await request.json()

    if not body:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    # Prevent admin from changing their own role
    if "role" in body and user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot change your own role",
        )

    # Validate role if provided
    if "role" in body and body["role"] not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Role must be one of: {', '.join(sorted(VALID_ROLES))}",
        )

    # Validate password length if provided
    if "password" in body and body["password"] and len(body["password"]) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters",
        )

    # Filter to only allowed fields
    allowed = {"email", "role", "is_active", "display_name", "password"}
    updates = {k: v for k, v in body.items() if k in allowed}

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid fields to update",
        )

    updated = await user_service.update_user(
        db=db,
        user_id=user_id,
        updates=updates,
        updated_by=admin.id,
    )

    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    logger.info("Admin '%s' updated user %s", admin.username, user_id)
    return updated


# ═══════════════════════════════════════════════════════════════════════════
# DEACTIVATE USER (admin only, soft-delete)
# ═══════════════════════════════════════════════════════════════════════════

@router.delete("/{user_id}", status_code=status.HTTP_200_OK)
async def deactivate_user(
    user_id: UUID,
    admin: CurrentUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate a user (soft-delete via is_active=false). Requires admin role.

    Admin cannot deactivate themselves.
    """
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot deactivate your own account",
        )

    success = await user_service.deactivate_user(
        db=db,
        user_id=user_id,
        deactivated_by=admin.id,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    logger.info("Admin '%s' deactivated user %s", admin.username, user_id)
    return {"message": "User deactivated", "user_id": str(user_id)}


# ═══════════════════════════════════════════════════════════════════════════
# RESET PASSWORD (admin only)
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: UUID,
    request: Request,
    admin: CurrentUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Reset a user's password. Requires admin role.

    Body: { new_password }
    Also clears failed login attempts and account lockout.
    """
    body = await request.json()
    new_password = body.get("new_password", "")

    if not new_password or len(new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 8 characters",
        )

    try:
        success = await user_service.reset_password(
            db=db,
            user_id=user_id,
            new_password=new_password,
            reset_by=admin.id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    logger.info("Admin '%s' reset password for user %s", admin.username, user_id)
    return {"message": "Password reset successfully", "user_id": str(user_id)}
