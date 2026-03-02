"""Enhanced backup management API routes.

Consolidates and extends backup functionality with new endpoints for
bulk operations, remote backup listing, and dashboard status.

Endpoints:
    GET  /backups                     List all downloaded backups
    GET  /backups/status              Backup status summary across all PBXes
    POST /backups/{pbx_id}/pull       Pull latest backup from PBX
    POST /backups/{pbx_id}/pull-all   Pull ALL available backups from PBX
    POST /backups/pull-all            Bulk pull latest from ALL PBXes
    POST /backups/{pbx_id}/trigger    Trigger backup creation on PBX
    GET  /backups/{pbx_id}/schedule   Get backup schedule
    PUT  /backups/{pbx_id}/schedule   Create/update backup schedule
    GET  /backups/{pbx_id}/available  List backups available on PBX (remote)
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.core.auth import get_current_user, require_role, CurrentUser
from src.models.models import PbxInstance, BackupRecord, BackupSchedule
from src.services import backup_service

logger = logging.getLogger("pbxmonitorx.api.backups")

router = APIRouter(prefix="/backups", tags=["Backups"])


# ── helper ──────────────────────────────────────────────────────────────
def _iso(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


# ═══════════════════════════════════════════════════════════════════════════
# LIST DOWNLOADED BACKUPS
# ═══════════════════════════════════════════════════════════════════════════

@router.get("")
async def list_backups(
    pbx_id: Optional[UUID] = Query(None, description="Filter by PBX instance"),
    limit: int = Query(100, le=500, ge=1),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List downloaded backup records, optionally filtered by PBX."""
    return await backup_service.list_backups(db, pbx_id=pbx_id, limit=limit)


# ═══════════════════════════════════════════════════════════════════════════
# BACKUP STATUS SUMMARY (dashboard)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/status")
async def backup_status_summary(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Backup status summary across all PBXes for the dashboard.

    Returns per-PBX: latest backup date, schedule status, total size, health.
    """
    # Get all PBX instances
    pbx_result = await db.execute(
        select(PbxInstance).where(PbxInstance.is_enabled == True).order_by(PbxInstance.name)
    )
    instances = pbx_result.scalars().all()

    per_pbx = []
    total_size_all = 0
    total_backups_all = 0

    for pbx in instances:
        # Latest backup for this PBX
        latest_q = select(BackupRecord).where(
            BackupRecord.pbx_id == pbx.id,
            BackupRecord.is_downloaded == True,
        ).order_by(BackupRecord.downloaded_at.desc()).limit(1)
        latest_result = await db.execute(latest_q)
        latest_backup = latest_result.scalar_one_or_none()

        # Total size and count for this PBX
        stats_q = select(
            func.count(BackupRecord.id).label("count"),
            func.coalesce(func.sum(BackupRecord.size_bytes), 0).label("total_size"),
        ).where(
            BackupRecord.pbx_id == pbx.id,
            BackupRecord.is_downloaded == True,
        )
        stats_result = await db.execute(stats_q)
        stats_row = stats_result.one()
        backup_count = stats_row[0]
        total_size = stats_row[1]

        # Schedule for this PBX
        sched_result = await db.execute(
            select(BackupSchedule).where(BackupSchedule.pbx_id == pbx.id)
        )
        schedule = sched_result.scalar_one_or_none()

        # Determine health
        health = "healthy"
        if not latest_backup:
            health = "no_backups"
        elif schedule and schedule.is_enabled:
            if schedule.last_run_success is False:
                health = "error"
            elif schedule.last_run_at and latest_backup.downloaded_at:
                # If last backup is much older than schedule interval, flag warning
                from datetime import datetime, timezone, timedelta
                age = datetime.now(timezone.utc) - latest_backup.downloaded_at
                if age > timedelta(days=7):
                    health = "stale"
                elif age > timedelta(days=2):
                    health = "warning"
        elif not schedule:
            health = "no_schedule"

        total_size_all += total_size
        total_backups_all += backup_count

        per_pbx.append({
            "pbx_id": str(pbx.id),
            "pbx_name": pbx.name,
            "latest_backup": {
                "filename": latest_backup.filename,
                "downloaded_at": _iso(latest_backup.downloaded_at),
                "size_bytes": latest_backup.size_bytes,
                "created_on_pbx": _iso(latest_backup.created_on_pbx),
            } if latest_backup else None,
            "backup_count": backup_count,
            "total_size_bytes": total_size,
            "schedule": {
                "is_enabled": schedule.is_enabled,
                "cron_expr": schedule.cron_expr,
                "next_run_at": _iso(schedule.next_run_at),
                "last_run_at": _iso(schedule.last_run_at),
                "last_run_success": schedule.last_run_success,
                "last_run_error": schedule.last_run_error,
            } if schedule else None,
            "health": health,
        })

    return {
        "total_pbx_count": len(instances),
        "total_backup_count": total_backups_all,
        "total_size_bytes": total_size_all,
        "per_pbx": per_pbx,
    }


# ═══════════════════════════════════════════════════════════════════════════
# PULL LATEST BACKUP
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/{pbx_id}/pull")
async def pull_backup(
    pbx_id: UUID,
    user: CurrentUser = Depends(require_role("admin", "operator")),
):
    """Manually queue a backup pull (download latest from PBX).

    Dispatches a Celery task to download the latest backup asynchronously.
    Requires admin or operator role.
    """
    from src.workers.tasks import pull_backup_now
    pull_backup_now.delay(str(pbx_id))
    return {"message": "Backup pull queued", "pbx_id": str(pbx_id)}


# ═══════════════════════════════════════════════════════════════════════════
# PULL ALL AVAILABLE BACKUPS FROM A SPECIFIC PBX
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/{pbx_id}/pull-all")
async def pull_all_backups_from_pbx(
    pbx_id: UUID,
    user: CurrentUser = Depends(require_role("admin", "operator")),
    db: AsyncSession = Depends(get_db),
):
    """Pull ALL available backups from a specific PBX (not just latest).

    Lists all remote backups on the PBX and queues a download task for each
    one that has not been downloaded yet. Requires admin or operator role.
    """
    # Verify PBX exists
    result = await db.execute(select(PbxInstance).where(PbxInstance.id == pbx_id))
    pbx = result.scalar_one_or_none()
    if not pbx:
        raise HTTPException(404, f"PBX instance {pbx_id} not found")

    # Get list of remote backups via adapter
    adapter, _ = await backup_service._get_adapter(db, pbx_id)
    if not adapter:
        raise HTTPException(502, "Could not connect to PBX")

    try:
        remote_backups = await adapter.list_backups()
    except Exception as e:
        logger.exception(f"Failed to list remote backups from {pbx.name}")
        raise HTTPException(502, f"Failed to list remote backups: {e}")
    finally:
        await adapter.close()

    if not remote_backups:
        return {"message": "No backups available on PBX", "queued": 0}

    # Find which ones we already have
    existing_result = await db.execute(
        select(BackupRecord.remote_backup_id).where(
            BackupRecord.pbx_id == pbx_id,
            BackupRecord.is_downloaded == True,
        )
    )
    downloaded_ids = {r for r in existing_result.scalars().all()}

    # Queue download for each new backup
    from src.workers.tasks import pull_backup_now
    queued = 0
    already_downloaded = 0
    for backup in remote_backups:
        if backup.backup_id in downloaded_ids:
            already_downloaded += 1
            continue
        # Queue each as a separate Celery task with a staggered countdown
        pull_backup_now.apply_async(
            args=[str(pbx_id)],
            countdown=queued * 5,  # Stagger downloads by 5 seconds each
        )
        queued += 1

    return {
        "message": f"Queued {queued} backup download(s), {already_downloaded} already downloaded",
        "pbx_id": str(pbx_id),
        "pbx_name": pbx.name,
        "remote_total": len(remote_backups),
        "queued": queued,
        "already_downloaded": already_downloaded,
    }


# ═══════════════════════════════════════════════════════════════════════════
# BULK PULL LATEST FROM ALL PBXes
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/pull-all")
async def pull_all_latest(
    user: CurrentUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Bulk pull latest backup from ALL enabled PBX instances.

    Queues a Celery backup pull task for each enabled PBX.
    Requires admin role.
    """
    result = await db.execute(
        select(PbxInstance).where(PbxInstance.is_enabled == True).order_by(PbxInstance.name)
    )
    instances = result.scalars().all()

    if not instances:
        return {"message": "No enabled PBX instances found", "queued": 0}

    from src.workers.tasks import pull_backup_now
    queued = []
    for i, pbx in enumerate(instances):
        pull_backup_now.apply_async(
            args=[str(pbx.id)],
            countdown=i * 10,  # Stagger by 10 seconds to avoid overloading
        )
        queued.append({"pbx_id": str(pbx.id), "pbx_name": pbx.name})

    return {
        "message": f"Queued backup pull for {len(queued)} PBX(es)",
        "queued": queued,
    }


# ═══════════════════════════════════════════════════════════════════════════
# TRIGGER BACKUP ON PBX
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/{pbx_id}/trigger")
async def trigger_pbx_backup(
    pbx_id: UUID,
    user: CurrentUser = Depends(require_role("admin", "operator")),
    db: AsyncSession = Depends(get_db),
):
    """Push a backup trigger to the PBX, then queue a pull after 15s.

    Instructs the PBX to create a fresh backup, then schedules a delayed
    pull task to download it. Requires admin or operator role.
    """
    result = await backup_service.trigger_backup_on_pbx(db, pbx_id)
    if result.get("success"):
        from src.workers.tasks import pull_backup_now
        pull_backup_now.apply_async(args=[str(pbx_id)], countdown=15)
    return result


# ═══════════════════════════════════════════════════════════════════════════
# SCHEDULE
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/{pbx_id}/schedule")
async def get_backup_schedule(
    pbx_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the backup schedule for a specific PBX."""
    sched = await backup_service.get_schedule(db, pbx_id)
    if not sched:
        return {"exists": False}
    return {
        "exists": True,
        "cron_expr": sched.cron_expr,
        "is_enabled": sched.is_enabled,
        "retain_count": sched.retain_count,
        "retain_days": sched.retain_days,
        "encrypt_at_rest": sched.encrypt_at_rest,
        "last_run_at": _iso(sched.last_run_at),
        "next_run_at": _iso(sched.next_run_at),
        "last_run_success": sched.last_run_success,
        "last_run_error": sched.last_run_error,
    }


@router.put("/{pbx_id}/schedule")
async def set_backup_schedule(
    pbx_id: UUID,
    request: Request,
    user: CurrentUser = Depends(require_role("admin", "operator")),
    db: AsyncSession = Depends(get_db),
):
    """Create or update a backup schedule for a PBX.

    Body: { cron_expr, retain_count, retain_days, encrypt_at_rest, is_enabled }
    Requires admin or operator role.
    """
    body = await request.json()
    try:
        sched = await backup_service.create_or_update_schedule(
            db, pbx_id,
            cron_expr=body.get("cron_expr", "0 2 * * *"),
            retain_count=body.get("retain_count"),
            retain_days=body.get("retain_days"),
            encrypt_at_rest=body.get("encrypt_at_rest", False),
            is_enabled=body.get("is_enabled", True),
        )
        return {"message": "Schedule saved", "next_run_at": _iso(sched.next_run_at)}
    except ValueError as e:
        raise HTTPException(400, str(e))


# ═══════════════════════════════════════════════════════════════════════════
# LIST AVAILABLE (REMOTE) BACKUPS
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/{pbx_id}/available")
async def list_available_backups(
    pbx_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List backups available on the PBX (remote, not necessarily downloaded).

    Connects to the PBX and queries for all available backup files.
    Compares against local records to show download status for each.
    """
    # Verify PBX exists
    result = await db.execute(select(PbxInstance).where(PbxInstance.id == pbx_id))
    pbx = result.scalar_one_or_none()
    if not pbx:
        raise HTTPException(404, f"PBX instance {pbx_id} not found")

    adapter, _ = await backup_service._get_adapter(db, pbx_id)
    if not adapter:
        raise HTTPException(502, "Could not connect to PBX")

    try:
        remote_backups = await adapter.list_backups()
    except Exception as e:
        logger.exception(f"Failed to list remote backups from {pbx.name}")
        raise HTTPException(502, f"Failed to list remote backups: {e}")
    finally:
        await adapter.close()

    # Check which are already downloaded locally
    existing_result = await db.execute(
        select(BackupRecord.remote_backup_id, BackupRecord.downloaded_at).where(
            BackupRecord.pbx_id == pbx_id,
            BackupRecord.is_downloaded == True,
        )
    )
    downloaded_map = {row[0]: row[1] for row in existing_result.all()}

    entries = []
    for backup in remote_backups:
        is_downloaded = backup.backup_id in downloaded_map
        entries.append({
            "backup_id": backup.backup_id,
            "filename": backup.filename,
            "created_at": backup.created_at,
            "size_bytes": backup.size_bytes,
            "backup_type": backup.backup_type,
            "is_downloaded": is_downloaded,
            "downloaded_at": _iso(downloaded_map.get(backup.backup_id)),
        })

    return {
        "pbx_id": str(pbx_id),
        "pbx_name": pbx.name,
        "remote_backups": entries,
        "total": len(entries),
        "downloaded": sum(1 for e in entries if e["is_downloaded"]),
        "not_downloaded": sum(1 for e in entries if not e["is_downloaded"]),
    }
