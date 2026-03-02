"""Event Log API — operational logging for troubleshooting.

All endpoints require admin or operator role.

Endpoints:
  GET    /events                  Query event logs (with filters + pagination)
  GET    /events/stats            Get event log summary statistics
  POST   /events/cleanup          Trigger manual cleanup of old events
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.core.auth import get_current_user, require_role, CurrentUser
from src.services import event_log_service

logger = logging.getLogger("pbxmonitorx.api.events")

router = APIRouter(prefix="/events", tags=["Event Log"])


@router.get("")
async def list_events(
    level: Optional[str] = Query(None, description="Filter by level: debug, info, warning, error, critical"),
    source: Optional[str] = Query(None, description="Filter by source: polling, backup, alert, adapter, etc."),
    pbx_id: Optional[str] = Query(None, description="Filter by PBX ID"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    search: Optional[str] = Query(None, description="Search message text"),
    since: Optional[str] = Query(None, description="ISO datetime lower bound"),
    until: Optional[str] = Query(None, description="ISO datetime upper bound"),
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role("operator")),
):
    """Query event logs with optional filters and pagination."""
    parsed_pbx_id = UUID(pbx_id) if pbx_id else None
    parsed_since = datetime.fromisoformat(since) if since else None
    parsed_until = datetime.fromisoformat(until) if until else None

    return await event_log_service.query_events(
        db,
        level=level,
        source=source,
        pbx_id=parsed_pbx_id,
        event_type=event_type,
        search=search,
        since=parsed_since,
        until=parsed_until,
        page=page,
        per_page=per_page,
    )


@router.get("/stats")
async def event_stats(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role("operator")),
):
    """Get summary statistics for event logs."""
    return await event_log_service.get_event_stats(db)


@router.post("/cleanup")
async def cleanup_events(
    debug_days: int = Query(7, ge=1, le=365),
    info_days: int = Query(30, ge=1, le=365),
    warning_days: int = Query(90, ge=1, le=730),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role("admin")),
):
    """Manually trigger cleanup of old event log entries."""
    deleted = await event_log_service.cleanup_old_events(
        db,
        debug_days=debug_days,
        info_days=info_days,
        warning_days=warning_days,
    )
    return {"deleted": deleted, "message": f"Cleaned up {deleted} old event log entries"}
