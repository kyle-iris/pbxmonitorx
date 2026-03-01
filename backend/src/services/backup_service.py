"""Backup service — push schedules to PBX, pull backups, manage retention.

Flow:
  1. User creates a backup_schedule for a PBX (cron, retention, encrypt flag)
  2. The schedule can optionally push a backup trigger to the PBX
  3. On schedule (or manual), pull latest backup from PBX to local storage
  4. Apply retention policy (keep last N or last X days)
  5. Optionally encrypt at rest with AES-256-GCM
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
from uuid import UUID

from croniter import croniter
from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.threecx_v20 import ThreeCXv20Adapter
from src.core.config import get_settings
from src.core.encryption import decrypt_password, encrypt_password, EncryptedBlob
from src.models.models import (
    PbxInstance, PbxCredential, BackupRecord, BackupSchedule, AuditLog,
)

logger = logging.getLogger("pbxmonitorx.backup")


# ═══════════════════════════════════════════════════════════════════════════
# SCHEDULE MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════

async def create_or_update_schedule(
    db: AsyncSession,
    pbx_id: UUID,
    cron_expr: str = "0 2 * * *",
    retain_count: Optional[int] = None,
    retain_days: Optional[int] = None,
    encrypt_at_rest: bool = False,
    is_enabled: bool = True,
) -> BackupSchedule:
    """Create or update a backup schedule for a PBX."""
    # Validate cron
    try:
        croniter(cron_expr)
    except (ValueError, KeyError) as e:
        raise ValueError(f"Invalid cron expression: {e}")

    result = await db.execute(
        select(BackupSchedule).where(BackupSchedule.pbx_id == pbx_id)
    )
    existing = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    next_run = croniter(cron_expr, now).get_next(datetime)

    if existing:
        await db.execute(update(BackupSchedule).where(BackupSchedule.id == existing.id).values(
            cron_expr=cron_expr, retain_count=retain_count,
            retain_days=retain_days, encrypt_at_rest=encrypt_at_rest,
            is_enabled=is_enabled, next_run_at=next_run,
        ))
        await db.commit()
        return existing
    else:
        sched = BackupSchedule(
            pbx_id=pbx_id, cron_expr=cron_expr,
            retain_count=retain_count, retain_days=retain_days,
            encrypt_at_rest=encrypt_at_rest, is_enabled=is_enabled,
            next_run_at=next_run,
        )
        db.add(sched)

        db.add(AuditLog(
            username="system", action="backup_scheduled",
            target_type="pbx", target_id=pbx_id,
            detail={"cron": cron_expr, "retain_count": retain_count, "retain_days": retain_days},
            success=True,
        ))
        await db.commit()
        return sched


async def get_schedule(db: AsyncSession, pbx_id: UUID) -> Optional[BackupSchedule]:
    result = await db.execute(
        select(BackupSchedule).where(BackupSchedule.pbx_id == pbx_id)
    )
    return result.scalar_one_or_none()


# ═══════════════════════════════════════════════════════════════════════════
# BACKUP TRIGGER (push to PBX)
# ═══════════════════════════════════════════════════════════════════════════

async def trigger_backup_on_pbx(db: AsyncSession, pbx_id: UUID) -> dict:
    """Push a backup trigger to the 3CX PBX.

    3CX v20 may support triggering a backup via the management API.
    This calls the adapter's trigger_backup method.
    """
    adapter, pbx = await _get_adapter(db, pbx_id)
    if not adapter:
        return {"success": False, "error": "Could not connect to PBX"}

    try:
        success, message = await adapter.trigger_backup()

        db.add(AuditLog(
            username="system", action="backup_triggered",
            target_type="pbx", target_id=pbx_id, target_name=pbx.name,
            detail={"message": message},
            success=success, error_message=message if not success else None,
        ))
        await db.commit()

        return {"success": success, "message": message}
    except Exception as e:
        logger.exception(f"Trigger backup failed for {pbx.name}")
        return {"success": False, "error": str(e)}
    finally:
        await adapter.close()


# ═══════════════════════════════════════════════════════════════════════════
# BACKUP PULL (download from PBX)
# ═══════════════════════════════════════════════════════════════════════════

async def pull_latest_backup(db: AsyncSession, pbx_id: UUID) -> dict:
    """List backups on PBX, download the latest one not already pulled."""
    settings = get_settings()
    adapter, pbx = await _get_adapter(db, pbx_id)
    if not adapter:
        return {"success": False, "error": "Could not connect to PBX"}

    try:
        remote_backups = await adapter.list_backups()
        if not remote_backups:
            return {"success": False, "error": "No backups available on PBX"}

        # Find the first backup we haven't downloaded yet
        existing_result = await db.execute(
            select(BackupRecord.remote_backup_id).where(
                BackupRecord.pbx_id == pbx_id,
                BackupRecord.is_downloaded == True,
            )
        )
        downloaded_ids = {r for r in existing_result.scalars().all()}

        target = None
        for b in remote_backups:
            if b.backup_id not in downloaded_ids:
                target = b
                break

        if not target:
            # All backups already downloaded — take the latest anyway if forced
            target = remote_backups[0]
            if target.backup_id in downloaded_ids:
                return {"success": True, "message": "All backups already downloaded", "skipped": True}

        # Prepare storage path
        pbx_dir = Path(settings.backup_path) / str(pbx_id)
        pbx_dir.mkdir(parents=True, exist_ok=True)
        dest = pbx_dir / target.filename

        logger.info(f"Downloading backup {target.filename} from {pbx.name}")
        t0 = time.monotonic()
        ok, hash_or_error = await adapter.download_backup(target.backup_id, str(dest))
        duration_ms = int((time.monotonic() - t0) * 1000)

        if not ok:
            return {"success": False, "error": hash_or_error}

        file_size = dest.stat().st_size

        # Record in DB
        db.add(BackupRecord(
            pbx_id=pbx_id, remote_backup_id=target.backup_id,
            filename=target.filename, backup_type=target.backup_type,
            created_on_pbx=datetime.fromisoformat(target.created_at) if target.created_at else None,
            size_bytes=file_size, is_downloaded=True,
            downloaded_at=datetime.now(timezone.utc),
            storage_path=str(dest), sha256_hash=hash_or_error,
        ))

        db.add(AuditLog(
            username="system", action="backup_downloaded",
            target_type="pbx", target_id=pbx_id, target_name=pbx.name,
            detail={"filename": target.filename, "size": file_size, "duration_ms": duration_ms},
            success=True,
        ))
        await db.commit()

        logger.info(f"Backup {target.filename} downloaded ({file_size} bytes) in {duration_ms}ms")
        return {
            "success": True,
            "filename": target.filename,
            "size_bytes": file_size,
            "sha256": hash_or_error,
            "duration_ms": duration_ms,
        }

    except Exception as e:
        logger.exception(f"Backup pull failed for {pbx.name}")
        return {"success": False, "error": str(e)}
    finally:
        await adapter.close()


# ═══════════════════════════════════════════════════════════════════════════
# SCHEDULED BACKUP RUNNER (called by Celery beat)
# ═══════════════════════════════════════════════════════════════════════════

async def run_due_backup_schedules(db: AsyncSession) -> list[dict]:
    """Find all backup schedules that are due and execute them."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(BackupSchedule).where(
            BackupSchedule.is_enabled == True,
            BackupSchedule.next_run_at <= now,
        )
    )
    due_schedules = result.scalars().all()
    results = []

    for sched in due_schedules:
        logger.info(f"Running scheduled backup for PBX {sched.pbx_id}")

        # Optionally trigger a fresh backup on the PBX first
        trigger_result = await trigger_backup_on_pbx(db, sched.pbx_id)
        if trigger_result.get("success"):
            # Wait a bit for PBX to generate backup
            import asyncio
            await asyncio.sleep(10)

        # Pull the backup
        pull_result = await pull_latest_backup(db, sched.pbx_id)
        results.append({"pbx_id": str(sched.pbx_id), **pull_result})

        # Update schedule timing
        next_run = croniter(sched.cron_expr, now).get_next(datetime)
        await db.execute(update(BackupSchedule).where(BackupSchedule.id == sched.id).values(
            last_run_at=now,
            next_run_at=next_run,
            last_run_success=pull_result.get("success", False),
            last_run_error=pull_result.get("error"),
        ))

    await db.commit()
    return results


# ═══════════════════════════════════════════════════════════════════════════
# RETENTION
# ═══════════════════════════════════════════════════════════════════════════

async def apply_retention(db: AsyncSession) -> list[str]:
    """Apply retention policies across all PBX backup schedules.

    For each schedule:
    - If retain_count set: keep only the most recent N downloaded backups, delete the rest
    - If retain_days set: delete backups older than X days
    """
    actions = []
    result = await db.execute(select(BackupSchedule))
    schedules = result.scalars().all()

    for sched in schedules:
        if sched.retain_count:
            cleaned = await _retain_by_count(db, sched.pbx_id, sched.retain_count)
            if cleaned:
                actions.extend(cleaned)

        if sched.retain_days:
            cleaned = await _retain_by_days(db, sched.pbx_id, sched.retain_days)
            if cleaned:
                actions.extend(cleaned)

    if actions:
        db.add(AuditLog(
            username="system", action="backup_retention_applied",
            target_type="system",
            detail={"deleted_count": len(actions), "files": actions},
            success=True,
        ))
        await db.commit()

    return actions


async def _retain_by_count(db: AsyncSession, pbx_id: UUID, keep: int) -> list[str]:
    """Keep only the most recent `keep` backups."""
    result = await db.execute(
        select(BackupRecord).where(
            BackupRecord.pbx_id == pbx_id,
            BackupRecord.is_downloaded == True,
        ).order_by(BackupRecord.downloaded_at.desc())
    )
    all_backups = result.scalars().all()
    to_delete = all_backups[keep:]  # Everything after the Nth
    return await _delete_backups(db, to_delete)


async def _retain_by_days(db: AsyncSession, pbx_id: UUID, days: int) -> list[str]:
    """Delete backups older than `days` days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(BackupRecord).where(
            BackupRecord.pbx_id == pbx_id,
            BackupRecord.is_downloaded == True,
            BackupRecord.downloaded_at < cutoff,
        )
    )
    return await _delete_backups(db, result.scalars().all())


async def _delete_backups(db: AsyncSession, backups) -> list[str]:
    """Delete backup files from disk and remove DB records."""
    deleted = []
    for b in backups:
        # Delete file from disk
        if b.storage_path:
            try:
                path = Path(b.storage_path)
                if path.exists():
                    path.unlink()
                    logger.info(f"Deleted backup file: {path}")
            except Exception as e:
                logger.warning(f"Could not delete {b.storage_path}: {e}")

        deleted.append(b.filename)
        await db.execute(delete(BackupRecord).where(BackupRecord.id == b.id))

    return deleted


# ═══════════════════════════════════════════════════════════════════════════
# LIST BACKUPS
# ═══════════════════════════════════════════════════════════════════════════

async def list_backups(
    db: AsyncSession, pbx_id: Optional[UUID] = None, limit: int = 100
) -> list[dict]:
    """List backup records, optionally filtered by PBX."""
    q = select(BackupRecord).order_by(BackupRecord.downloaded_at.desc()).limit(limit)
    if pbx_id:
        q = q.where(BackupRecord.pbx_id == pbx_id)

    result = await db.execute(q)
    return [
        {
            "id": str(b.id), "pbx_id": str(b.pbx_id),
            "filename": b.filename, "backup_type": b.backup_type,
            "created_on_pbx": b.created_on_pbx.isoformat() if b.created_on_pbx else None,
            "size_bytes": b.size_bytes, "is_downloaded": b.is_downloaded,
            "downloaded_at": b.downloaded_at.isoformat() if b.downloaded_at else None,
            "sha256_hash": b.sha256_hash,
        }
        for b in result.scalars().all()
    ]


# ═══════════════════════════════════════════════════════════════════════════
# HELPER
# ═══════════════════════════════════════════════════════════════════════════

async def _get_adapter(db: AsyncSession, pbx_id: UUID) -> tuple[Optional[ThreeCXv20Adapter], Optional[PbxInstance]]:
    """Create an authenticated adapter for a PBX."""
    pbx_result = await db.execute(select(PbxInstance).where(PbxInstance.id == pbx_id))
    pbx = pbx_result.scalar_one_or_none()
    if not pbx:
        return None, None

    cred_result = await db.execute(select(PbxCredential).where(PbxCredential.pbx_id == pbx_id))
    cred = cred_result.scalar_one_or_none()
    if not cred:
        return None, pbx

    try:
        blob = EncryptedBlob(ciphertext=bytes(cred.encrypted_password), nonce=bytes(cred.nonce), tag=bytes(cred.auth_tag))
        password = decrypt_password(blob)
    except Exception:
        return None, pbx

    adapter = ThreeCXv20Adapter(pbx.base_url, verify_tls=pbx.tls_policy != "trust_self_signed")
    ok, _ = await adapter.login(cred.username, password)
    if not ok:
        await adapter.close()
        return None, pbx

    return adapter, pbx
