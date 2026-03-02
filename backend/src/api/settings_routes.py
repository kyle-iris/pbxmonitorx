"""Admin Settings API — global configuration, branding, notifications, backup storage.

All endpoints require admin role.

Endpoints:
  GET    /settings                      Get all settings (grouped by category)
  GET    /settings/{category}           Get settings for a specific category
  PUT    /settings                      Bulk update settings
  PUT    /settings/{key}                Update a single setting

  GET    /settings/notifications/channels       List notification channels
  POST   /settings/notifications/channels       Create a notification channel
  PATCH  /settings/notifications/channels/{id}  Update a notification channel
  DELETE /settings/notifications/channels/{id}  Delete a notification channel
  POST   /settings/notifications/channels/{id}/test  Test a notification channel
  GET    /settings/notifications/history        Get notification send history

  GET    /settings/branding              Get branding settings (public, no auth needed)
"""

from __future__ import annotations

import logging
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query, status
from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.core.auth import get_current_user, require_role, CurrentUser
from src.models.models import SystemSetting, AuditLog
from src.services import notification_service

logger = logging.getLogger("pbxmonitorx.api.settings")

router = APIRouter(prefix="/settings", tags=["Settings"])


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC ENDPOINT — branding (no auth required)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/branding")
async def get_branding(db: AsyncSession = Depends(get_db)):
    """Get branding settings. This is public so the login page can display them."""
    settings = await notification_service.get_settings_by_category(db, "branding")
    return {k.replace("branding.", ""): v for k, v in settings.items()}


# ═══════════════════════════════════════════════════════════════════════════
# ALL SETTINGS (admin only)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("")
async def get_all_settings(
    admin: CurrentUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Get all system settings grouped by category."""
    result = await db.execute(select(SystemSetting).order_by(SystemSetting.key))
    settings = result.scalars().all()

    grouped = {}
    for s in settings:
        cat = s.category
        if cat not in grouped:
            grouped[cat] = {}
        grouped[cat][s.key] = {
            "value": s.value,
            "description": s.description,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        }
    return grouped


@router.get("/category/{category}")
async def get_category_settings(
    category: str,
    admin: CurrentUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Get all settings for a specific category."""
    result = await db.execute(
        select(SystemSetting).where(SystemSetting.category == category)
    )
    settings = result.scalars().all()
    return {
        s.key: {"value": s.value, "description": s.description}
        for s in settings
    }


@router.put("")
async def bulk_update_settings(
    request: Request,
    admin: CurrentUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Bulk update settings. Body: { "key1": value1, "key2": value2, ... }"""
    body = await request.json()
    updated = []

    for key, value in body.items():
        result = await db.execute(select(SystemSetting).where(SystemSetting.key == key))
        setting = result.scalar_one_or_none()

        if setting:
            await db.execute(
                sa_update(SystemSetting).where(SystemSetting.key == key).values(
                    value=value, updated_by=admin.id,
                )
            )
            updated.append(key)
        else:
            # Infer category from key prefix
            category = key.split(".")[0] if "." in key else "general"
            db.add(SystemSetting(key=key, value=value, category=category, updated_by=admin.id))
            updated.append(key)

    db.add(AuditLog(
        user_id=admin.id, username=admin.username,
        action="settings_updated",
        target_type="system",
        detail={"keys": updated},
        success=True,
    ))
    await db.commit()
    return {"message": f"Updated {len(updated)} settings", "keys": updated}


@router.put("/{key:path}")
async def update_single_setting(
    key: str,
    request: Request,
    admin: CurrentUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Update a single setting by key. Body: { "value": <new_value> }"""
    body = await request.json()
    value = body.get("value")

    result = await db.execute(select(SystemSetting).where(SystemSetting.key == key))
    setting = result.scalar_one_or_none()

    if setting:
        await db.execute(
            sa_update(SystemSetting).where(SystemSetting.key == key).values(
                value=value, updated_by=admin.id,
            )
        )
    else:
        category = key.split(".")[0] if "." in key else "general"
        db.add(SystemSetting(key=key, value=value, category=category, updated_by=admin.id))

    db.add(AuditLog(
        user_id=admin.id, username=admin.username,
        action="settings_updated",
        target_type="system",
        detail={"key": key, "value": value},
        success=True,
    ))
    await db.commit()
    return {"message": "Setting updated", "key": key}


# ═══════════════════════════════════════════════════════════════════════════
# NOTIFICATION CHANNELS (admin only)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/notifications/channels")
async def list_notification_channels(
    admin: CurrentUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    return await notification_service.list_channels(db)


@router.post("/notifications/channels", status_code=201)
async def create_notification_channel(
    request: Request,
    admin: CurrentUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    body = await request.json()
    name = (body.get("name") or "").strip()
    channel_type = (body.get("channel_type") or "").strip()

    if not name:
        raise HTTPException(400, "Name is required")
    if channel_type not in ("email", "webhook", "halopsa"):
        raise HTTPException(400, "channel_type must be email, webhook, or halopsa")

    result = await notification_service.create_channel(
        db, name=name, channel_type=channel_type,
        config=body.get("config", {}),
        is_enabled=body.get("is_enabled", True),
    )

    db.add(AuditLog(
        user_id=admin.id, username=admin.username,
        action="notification_channel_created",
        target_type="notification_channel",
        target_name=name,
        detail={"channel_type": channel_type},
        success=True,
    ))
    await db.commit()
    return result


@router.patch("/notifications/channels/{channel_id}")
async def update_notification_channel(
    channel_id: UUID,
    request: Request,
    admin: CurrentUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    body = await request.json()
    ok = await notification_service.update_channel(db, channel_id, body)
    if not ok:
        raise HTTPException(404, "Channel not found")

    db.add(AuditLog(
        user_id=admin.id, username=admin.username,
        action="notification_channel_updated",
        target_type="notification_channel",
        target_id=channel_id,
        detail=body,
        success=True,
    ))
    await db.commit()
    return {"message": "Channel updated"}


@router.delete("/notifications/channels/{channel_id}", status_code=204)
async def delete_notification_channel(
    channel_id: UUID,
    admin: CurrentUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    ok = await notification_service.delete_channel(db, channel_id)
    if not ok:
        raise HTTPException(404, "Channel not found")

    db.add(AuditLog(
        user_id=admin.id, username=admin.username,
        action="notification_channel_deleted",
        target_type="notification_channel",
        target_id=channel_id,
        success=True,
    ))
    await db.commit()


@router.post("/notifications/channels/{channel_id}/test")
async def test_notification_channel(
    channel_id: UUID,
    admin: CurrentUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await notification_service.test_channel(db, channel_id)
    return result


@router.get("/notifications/history")
async def get_notification_history(
    limit: int = Query(50, le=200),
    channel_id: Optional[UUID] = Query(None),
    admin: CurrentUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    return await notification_service.get_notification_history(db, limit=limit, channel_id=channel_id)
