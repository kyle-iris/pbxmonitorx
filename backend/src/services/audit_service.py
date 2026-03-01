"""Audit service — query, filter, CSV export."""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.models import AuditLog


async def list_audit_entries(
    db: AsyncSession,
    action: Optional[str] = None,
    user_id: Optional[UUID] = None,
    target_type: Optional[str] = None,
    success: Optional[bool] = None,
    limit: int = 200,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Query audit log with filters. Returns (entries, total_count)."""
    q = select(AuditLog).order_by(AuditLog.created_at.desc())
    count_q = select(func.count(AuditLog.id))

    if action:
        q = q.where(AuditLog.action == action)
        count_q = count_q.where(AuditLog.action == action)
    if user_id:
        q = q.where(AuditLog.user_id == user_id)
        count_q = count_q.where(AuditLog.user_id == user_id)
    if target_type:
        q = q.where(AuditLog.target_type == target_type)
        count_q = count_q.where(AuditLog.target_type == target_type)
    if success is not None:
        q = q.where(AuditLog.success == success)
        count_q = count_q.where(AuditLog.success == success)

    total = (await db.execute(count_q)).scalar() or 0
    result = await db.execute(q.offset(offset).limit(limit))
    entries = result.scalars().all()

    return [
        {
            "id": str(e.id),
            "username": e.username,
            "action": e.action,
            "target_type": e.target_type,
            "target_name": e.target_name,
            "detail": e.detail or {},
            "ip_address": e.ip_address,
            "success": e.success,
            "error_message": e.error_message,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in entries
    ], total


async def export_csv(db: AsyncSession, **filters) -> str:
    """Export audit log as CSV string."""
    entries, _ = await list_audit_entries(db, limit=10000, **filters)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "created_at", "username", "action", "target_type",
        "target_name", "success", "error_message", "detail", "ip_address",
    ])
    writer.writeheader()
    for e in entries:
        writer.writerow({
            "created_at": e["created_at"],
            "username": e["username"],
            "action": e["action"],
            "target_type": e["target_type"],
            "target_name": e["target_name"],
            "success": e["success"],
            "error_message": e["error_message"] or "",
            "detail": str(e["detail"]),
            "ip_address": e["ip_address"] or "",
        })
    return output.getvalue()
