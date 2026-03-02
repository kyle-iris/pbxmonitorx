"""Event log service — structured operational logging for troubleshooting.

Provides a centralized way to log tool-level events (polling, backups, alerts,
adapter interactions, notifications, auth) with structured data, durations,
and error traces. These are queryable via the API for real-time troubleshooting.

Usage:
    from src.services.event_log_service import log_event, log_error

    await log_event(db, "polling", "poll_completed", "Polled PBX acme-pbx in 230ms",
                    pbx_id=pbx.id, pbx_name=pbx.name, duration_ms=230,
                    detail={"trunks": 3, "changes": ["Trunk Main: registered → unregistered"]})

    await log_error(db, "backup", "backup_download_failed", "Download timed out for acme-pbx",
                    pbx_id=pbx.id, pbx_name=pbx.name, error=e)
"""

from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.models import EventLog

logger = logging.getLogger("pbxmonitorx.event_log")

# Valid log levels in priority order
LOG_LEVELS = ("debug", "info", "warning", "error", "critical")

# Valid source categories
LOG_SOURCES = (
    "polling", "backup", "alert", "adapter", "notification",
    "auth", "system", "scheduler", "settings",
)


async def log_event(
    db: AsyncSession,
    source: str,
    event_type: str,
    message: str,
    *,
    level: str = "info",
    pbx_id: Optional[UUID] = None,
    pbx_name: Optional[str] = None,
    detail: Optional[dict] = None,
    duration_ms: Optional[int] = None,
    error_trace: Optional[str] = None,
) -> None:
    """Write a structured event to the event_log table.

    This is non-blocking — errors in logging itself are caught and logged
    to the Python logger to avoid disrupting the main operation.
    """
    try:
        entry = EventLog(
            level=level if level in LOG_LEVELS else "info",
            source=source,
            pbx_id=pbx_id,
            pbx_name=pbx_name,
            event_type=event_type,
            message=message,
            detail=detail or {},
            duration_ms=duration_ms,
            error_trace=error_trace,
        )
        db.add(entry)
        # Don't commit — let the caller's transaction handle it.
        # If the caller doesn't commit, flush so it's at least in the session.
        await db.flush()
    except Exception as e:
        # Never let logging break the main operation
        logger.warning(f"Failed to write event log: {e}")


async def log_error(
    db: AsyncSession,
    source: str,
    event_type: str,
    message: str,
    *,
    error: Optional[Exception] = None,
    pbx_id: Optional[UUID] = None,
    pbx_name: Optional[str] = None,
    detail: Optional[dict] = None,
    duration_ms: Optional[int] = None,
) -> None:
    """Convenience wrapper for logging errors with automatic stack trace capture."""
    trace = None
    if error:
        trace = traceback.format_exception(type(error), error, error.__traceback__)
        trace = "".join(trace)

    error_detail = detail or {}
    if error:
        error_detail["error_type"] = type(error).__name__
        error_detail["error_message"] = str(error)

    await log_event(
        db, source, event_type, message,
        level="error",
        pbx_id=pbx_id,
        pbx_name=pbx_name,
        detail=error_detail,
        duration_ms=duration_ms,
        error_trace=trace,
    )


async def query_events(
    db: AsyncSession,
    *,
    level: Optional[str] = None,
    source: Optional[str] = None,
    pbx_id: Optional[UUID] = None,
    event_type: Optional[str] = None,
    search: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    page: int = 1,
    per_page: int = 100,
) -> dict:
    """Query event logs with filters and pagination."""
    q = select(EventLog).order_by(EventLog.timestamp.desc())
    count_q = select(func.count(EventLog.id))

    # Apply filters
    if level:
        q = q.where(EventLog.level == level)
        count_q = count_q.where(EventLog.level == level)
    if source:
        q = q.where(EventLog.source == source)
        count_q = count_q.where(EventLog.source == source)
    if pbx_id:
        q = q.where(EventLog.pbx_id == pbx_id)
        count_q = count_q.where(EventLog.pbx_id == pbx_id)
    if event_type:
        q = q.where(EventLog.event_type == event_type)
        count_q = count_q.where(EventLog.event_type == event_type)
    if search:
        pattern = f"%{search}%"
        q = q.where(EventLog.message.ilike(pattern))
        count_q = count_q.where(EventLog.message.ilike(pattern))
    if since:
        q = q.where(EventLog.timestamp >= since)
        count_q = count_q.where(EventLog.timestamp >= since)
    if until:
        q = q.where(EventLog.timestamp <= until)
        count_q = count_q.where(EventLog.timestamp <= until)

    # Count
    total_result = await db.execute(count_q)
    total = total_result.scalar()

    # Paginate
    q = q.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(q)
    events = result.scalars().all()

    return {
        "events": [
            {
                "id": str(e.id),
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                "level": e.level,
                "source": e.source,
                "pbx_id": str(e.pbx_id) if e.pbx_id else None,
                "pbx_name": e.pbx_name,
                "event_type": e.event_type,
                "message": e.message,
                "detail": e.detail or {},
                "duration_ms": e.duration_ms,
                "error_trace": e.error_trace,
            }
            for e in events
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, (total + per_page - 1) // per_page),
    }


async def get_event_stats(db: AsyncSession) -> dict:
    """Get summary stats for the event log (counts by level and source)."""
    # Counts by level
    level_result = await db.execute(
        select(EventLog.level, func.count(EventLog.id))
        .group_by(EventLog.level)
    )
    by_level = {row[0]: row[1] for row in level_result.all()}

    # Counts by source (last 24h)
    since = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    source_result = await db.execute(
        select(EventLog.source, func.count(EventLog.id))
        .where(EventLog.timestamp >= since)
        .group_by(EventLog.source)
    )
    by_source_today = {row[0]: row[1] for row in source_result.all()}

    # Recent errors (last 10)
    error_result = await db.execute(
        select(EventLog)
        .where(EventLog.level.in_(["error", "critical"]))
        .order_by(EventLog.timestamp.desc())
        .limit(10)
    )
    recent_errors = [
        {
            "id": str(e.id),
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            "source": e.source,
            "event_type": e.event_type,
            "message": e.message,
            "pbx_name": e.pbx_name,
        }
        for e in error_result.scalars().all()
    ]

    return {
        "by_level": by_level,
        "by_source_today": by_source_today,
        "recent_errors": recent_errors,
    }


async def cleanup_old_events(
    db: AsyncSession,
    debug_days: int = 7,
    info_days: int = 30,
    warning_days: int = 90,
) -> int:
    """Delete old event log entries based on retention policy.

    Returns the number of deleted rows.
    """
    now = datetime.now(timezone.utc)
    from datetime import timedelta

    deleted = 0

    for level, days in [("debug", debug_days), ("info", info_days), ("warning", warning_days)]:
        cutoff = now - timedelta(days=days)
        result = await db.execute(
            delete(EventLog).where(
                EventLog.level == level,
                EventLog.timestamp < cutoff,
            )
        )
        deleted += result.rowcount

    await db.commit()
    return deleted
