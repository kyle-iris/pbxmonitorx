"""Alert service — evaluates rules against state, fires/resolves/syncs alerts.

Strategy:
  - Base alerts come from 3CX native alert system where available
  - We supplement with our own rule engine for: trunk down, SBC offline,
    license expiring, backup stale
  - Deduplication via fingerprint to avoid alert storms
  - Auto-resolve when condition clears
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta, date
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.models import (
    AlertRule, AlertEvent, TrunkState, SbcState,
    LicenseState, BackupRecord, PbxInstance, AuditLog,
)

logger = logging.getLogger("pbxmonitorx.alerts")


async def evaluate_all_rules(db: AsyncSession) -> list[dict]:
    """Evaluate all enabled alert rules against current state.

    For each rule:
    1. Query relevant state data
    2. Check condition
    3. If condition met and no active alert with same fingerprint → fire
    4. If condition cleared and active alert exists → resolve
    """
    result = await db.execute(
        select(AlertRule).where(AlertRule.is_enabled == True)
    )
    rules = result.scalars().all()

    # Load all PBXes for iteration
    pbx_result = await db.execute(
        select(PbxInstance).where(PbxInstance.is_enabled == True)
    )
    all_pbxes = pbx_result.scalars().all()

    fired = []
    resolved = []

    for rule in rules:
        # Determine which PBXes this rule applies to
        if rule.pbx_id:
            targets = [p for p in all_pbxes if p.id == rule.pbx_id]
        else:
            targets = all_pbxes  # Global rule → all PBXes

        for pbx in targets:
            match rule.condition_type:
                case "trunk_down":
                    f, r = await _check_trunk_down(db, rule, pbx)
                case "sbc_offline":
                    f, r = await _check_sbc_offline(db, rule, pbx)
                case "license_expiring":
                    f, r = await _check_license_expiring(db, rule, pbx)
                case "backup_stale":
                    f, r = await _check_backup_stale(db, rule, pbx)
                case _:
                    continue

            fired.extend(f)
            resolved.extend(r)

    await db.commit()
    return [{"fired": len(fired), "resolved": len(resolved), "details": fired + resolved}]


# ═══════════════════════════════════════════════════════════════════════════
# CONDITION CHECKERS
# ═══════════════════════════════════════════════════════════════════════════

async def _check_trunk_down(
    db: AsyncSession, rule: AlertRule, pbx: PbxInstance
) -> tuple[list[dict], list[dict]]:
    """Fire alert if any trunk is unregistered for longer than threshold."""
    fired, resolved = [], []
    threshold_s = rule.threshold_seconds or 60
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(TrunkState).where(TrunkState.pbx_id == pbx.id)
    )
    trunks = result.scalars().all()

    for trunk in trunks:
        fp = f"trunk_down:{pbx.id}:{trunk.trunk_name}"

        if trunk.status in ("unregistered", "error"):
            # Check duration
            if trunk.last_status_change:
                down_seconds = (now - trunk.last_status_change.replace(tzinfo=timezone.utc)).total_seconds()
            else:
                down_seconds = threshold_s + 1  # Unknown duration, assume exceeded

            if down_seconds >= threshold_s:
                f = await _fire_if_new(db, rule, pbx, fp,
                    f"Trunk '{trunk.trunk_name}' {trunk.status} for {int(down_seconds)}s",
                    {"trunk": trunk.trunk_name, "status": trunk.status, "error": trunk.last_error})
                if f:
                    fired.append(f)
            else:
                # Below threshold, resolve if we had an alert
                r = await _resolve_if_active(db, fp)
                if r:
                    resolved.append(r)
        else:
            # Trunk is registered — resolve any active alert
            r = await _resolve_if_active(db, fp)
            if r:
                resolved.append(r)

    return fired, resolved


async def _check_sbc_offline(
    db: AsyncSession, rule: AlertRule, pbx: PbxInstance
) -> tuple[list[dict], list[dict]]:
    fired, resolved = [], []
    threshold_s = rule.threshold_seconds or 120
    now = datetime.now(timezone.utc)

    result = await db.execute(select(SbcState).where(SbcState.pbx_id == pbx.id))
    sbcs = result.scalars().all()

    for sbc in sbcs:
        fp = f"sbc_offline:{pbx.id}:{sbc.sbc_name}"

        if sbc.status == "offline":
            if sbc.last_seen:
                offline_seconds = (now - sbc.last_seen.replace(tzinfo=timezone.utc)).total_seconds()
            else:
                offline_seconds = threshold_s + 1

            if offline_seconds >= threshold_s:
                f = await _fire_if_new(db, rule, pbx, fp,
                    f"SBC '{sbc.sbc_name}' offline for {int(offline_seconds)}s",
                    {"sbc": sbc.sbc_name, "last_seen": sbc.last_seen.isoformat() if sbc.last_seen else None})
                if f:
                    fired.append(f)
        else:
            r = await _resolve_if_active(db, fp)
            if r:
                resolved.append(r)

    return fired, resolved


async def _check_license_expiring(
    db: AsyncSession, rule: AlertRule, pbx: PbxInstance
) -> tuple[list[dict], list[dict]]:
    fired, resolved = [], []
    threshold_days = rule.threshold_days or 30
    today = date.today()

    result = await db.execute(select(LicenseState).where(LicenseState.pbx_id == pbx.id))
    lic = result.scalar_one_or_none()
    if not lic:
        return fired, resolved

    fp = f"license_expiring:{pbx.id}"

    # Check if expired
    if lic.is_valid is False:
        f = await _fire_if_new(db, rule, pbx, fp,
            f"License EXPIRED for {pbx.name}",
            {"edition": lic.edition, "expiry": str(lic.expiry_date)},
            severity="critical")
        if f:
            fired.append(f)
        return fired, resolved

    # Check if expiring soon
    if lic.expiry_date:
        days_left = (lic.expiry_date - today).days
        if days_left <= threshold_days:
            f = await _fire_if_new(db, rule, pbx, fp,
                f"License expires in {days_left} days for {pbx.name}",
                {"edition": lic.edition, "expiry": str(lic.expiry_date), "days_left": days_left})
            if f:
                fired.append(f)
        else:
            r = await _resolve_if_active(db, fp)
            if r:
                resolved.append(r)
    return fired, resolved


async def _check_backup_stale(
    db: AsyncSession, rule: AlertRule, pbx: PbxInstance
) -> tuple[list[dict], list[dict]]:
    fired, resolved = [], []
    threshold_s = rule.threshold_seconds or 86400  # 24h default
    now = datetime.now(timezone.utc)

    fp = f"backup_stale:{pbx.id}"

    result = await db.execute(
        select(BackupRecord).where(
            BackupRecord.pbx_id == pbx.id,
            BackupRecord.is_downloaded == True,
        ).order_by(BackupRecord.downloaded_at.desc()).limit(1)
    )
    latest = result.scalar_one_or_none()

    if not latest:
        f = await _fire_if_new(db, rule, pbx, fp,
            f"No backups ever downloaded for {pbx.name}",
            {"pbx": pbx.name})
        if f:
            fired.append(f)
    else:
        age_s = (now - latest.downloaded_at.replace(tzinfo=timezone.utc)).total_seconds()
        if age_s >= threshold_s:
            hours = int(age_s / 3600)
            f = await _fire_if_new(db, rule, pbx, fp,
                f"No backup in {hours}h for {pbx.name}",
                {"last_backup": latest.filename, "age_hours": hours})
            if f:
                fired.append(f)
        else:
            r = await _resolve_if_active(db, fp)
            if r:
                resolved.append(r)

    return fired, resolved


# ═══════════════════════════════════════════════════════════════════════════
# ALERT LIFECYCLE
# ═══════════════════════════════════════════════════════════════════════════

async def _fire_if_new(
    db: AsyncSession, rule: AlertRule, pbx: PbxInstance,
    fingerprint: str, title: str, detail: dict,
    severity: str = None,
) -> Optional[dict]:
    """Fire an alert only if there's no active alert with the same fingerprint."""
    result = await db.execute(
        select(AlertEvent).where(
            AlertEvent.fingerprint == fingerprint,
            AlertEvent.state == "firing",
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return None  # Already firing, skip

    sev = severity or rule.severity or "warning"
    event = AlertEvent(
        rule_id=rule.id, pbx_id=pbx.id, state="firing",
        severity=sev, title=title, detail=str(detail),
        fingerprint=fingerprint,
    )
    db.add(event)

    # Send notifications
    try:
        from src.services.notification_service import notify_alert_fired
        await notify_alert_fired(db, event, pbx)
    except Exception as e:
        logger.warning(f"Notification dispatch failed: {e}")

    logger.warning(f"ALERT FIRED [{sev}]: {title}")
    return {"action": "fired", "severity": sev, "title": title, "pbx": pbx.name}


async def _resolve_if_active(db: AsyncSession, fingerprint: str) -> Optional[dict]:
    """Resolve an active alert if the condition has cleared."""
    result = await db.execute(
        select(AlertEvent).where(
            AlertEvent.fingerprint == fingerprint,
            AlertEvent.state == "firing",
        )
    )
    event = result.scalar_one_or_none()
    if not event:
        return None

    now = datetime.now(timezone.utc)
    await db.execute(update(AlertEvent).where(AlertEvent.id == event.id).values(
        state="resolved", resolved_at=now,
    ))

    # Send resolution notification
    try:
        from src.services.notification_service import notify_alert_resolved
        pbx_result = await db.execute(
            select(PbxInstance).where(PbxInstance.id == event.pbx_id)
        )
        pbx = pbx_result.scalar_one_or_none()
        if pbx:
            await notify_alert_resolved(db, event, pbx)
    except Exception as e:
        logger.warning(f"Resolution notification failed: {e}")

    logger.info(f"ALERT RESOLVED: {event.title}")
    return {"action": "resolved", "title": event.title}


# ═══════════════════════════════════════════════════════════════════════════
# ALERT QUERIES
# ═══════════════════════════════════════════════════════════════════════════

async def list_alerts(
    db: AsyncSession, state: str = None, pbx_id: UUID = None, limit: int = 100
) -> list[dict]:
    q = select(AlertEvent).order_by(AlertEvent.fired_at.desc()).limit(limit)
    if state:
        q = q.where(AlertEvent.state == state)
    if pbx_id:
        q = q.where(AlertEvent.pbx_id == pbx_id)

    result = await db.execute(q)
    events = result.scalars().all()

    # Load PBX names
    pbx_result = await db.execute(select(PbxInstance))
    pbx_map = {p.id: p.name for p in pbx_result.scalars().all()}

    return [
        {
            "id": str(e.id), "severity": e.severity, "state": e.state,
            "title": e.title, "detail": e.detail,
            "pbx_id": str(e.pbx_id), "pbx_name": pbx_map.get(e.pbx_id, "Unknown"),
            "fired_at": e.fired_at.isoformat() if e.fired_at else None,
            "resolved_at": e.resolved_at.isoformat() if e.resolved_at else None,
        }
        for e in events
    ]


async def acknowledge_alert(db: AsyncSession, alert_id: UUID, user_id: UUID) -> bool:
    result = await db.execute(select(AlertEvent).where(AlertEvent.id == alert_id))
    event = result.scalar_one_or_none()
    if not event or event.state != "firing":
        return False

    await db.execute(update(AlertEvent).where(AlertEvent.id == alert_id).values(
        state="acknowledged",
        acknowledged_at=datetime.now(timezone.utc),
        acknowledged_by=user_id,
    ))
    db.add(AuditLog(
        user_id=user_id, action="alert_acknowledged",
        target_type="alert", target_id=alert_id, target_name=event.title,
        success=True,
    ))
    await db.commit()
    return True
