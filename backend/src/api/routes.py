"""PBXMonitorX API — all horizontal services.

Endpoints:
  Auth:     POST /auth/login, /auth/refresh
  PBX:      POST /pbx/test-connection
            CRUD /pbx/instances
            PATCH /pbx/instances/{id}
            POST /pbx/instances/{id}/poll        (manual poll)
  Backups:  GET  /backups
            POST /backups/{pbx_id}/pull          (manual pull)
            POST /backups/{pbx_id}/trigger       (push trigger to PBX)
            GET|PUT /backups/{pbx_id}/schedule
  Alerts:   GET  /alerts
            POST /alerts/{id}/acknowledge
  Audit:    GET  /audit
            GET  /audit/export                   (CSV download)
  Health:   GET  /health
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import (
    APIRouter, Depends, HTTPException, Request, Response, Query, status,
)
from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.core.auth import (
    authenticate_user, create_access_token, create_refresh_token,
    decode_token, get_current_user, require_role, CurrentUser,
)
from src.core.encryption import encrypt_password as encrypt_pw
from src.models.models import PbxInstance, PbxCredential
from src.services.pbx_service import PbxService
from src.services import backup_service, alert_service, audit_service

logger = logging.getLogger("pbxmonitorx.api")
router = APIRouter()

# Valid poll intervals: 1 min, 5 min, 10 min, 60 min
VALID_POLL_INTERVALS = (60, 300, 600, 3600)


# ═══════════════════════════════════════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/auth/login")
async def login(request: Request, db: AsyncSession = Depends(get_db)):
    """Authenticate and get JWT access + refresh tokens."""
    body = await request.json()
    ip = request.client.host if request.client else None
    user, err = await authenticate_user(
        db, body.get("username", ""), body.get("password", ""), ip,
    )
    if not user:
        raise HTTPException(401, err)

    access, expires = create_access_token(str(user.id), user.username, user.role)
    refresh = create_refresh_token(str(user.id))
    return {
        "access_token": access, "refresh_token": refresh,
        "token_type": "bearer", "expires_at": expires.isoformat(),
        "user": {"id": str(user.id), "username": user.username, "role": user.role},
    }


@router.post("/auth/refresh")
async def refresh_token(request: Request):
    body = await request.json()
    payload = decode_token(body.get("refresh_token", ""))
    if payload.get("type") != "refresh":
        raise HTTPException(400, "Not a refresh token")
    access, expires = create_access_token(payload["sub"], payload.get("username", ""), payload.get("role", ""))
    return {"access_token": access, "expires_at": expires.isoformat()}


# ═══════════════════════════════════════════════════════════════════════════
# PBX — TEST CONNECTION
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/pbx/test-connection")
async def test_connection(request: Request):
    """Test connectivity to a 3CX PBX without persisting anything."""
    body = await request.json()
    url = (body.get("base_url") or "").strip().rstrip("/")
    if not url.startswith("https://"):
        raise HTTPException(400, "URL must start with https://")
    if not body.get("username") or not body.get("password"):
        raise HTTPException(400, "Username and password required")

    return await PbxService.test_connection(
        base_url=url,
        username=body["username"],
        password=body["password"],
        tls_policy=body.get("tls_policy", "verify"),
    )


# ═══════════════════════════════════════════════════════════════════════════
# PBX — CRUD
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/pbx/instances", status_code=201)
async def create_instance(request: Request, db: AsyncSession = Depends(get_db)):
    """Add a new PBX instance. Encrypts credentials before storing."""
    body = await request.json()
    url = (body.get("base_url") or "").strip().rstrip("/")
    name = (body.get("name") or "").strip()

    if not url.startswith("https://"):
        raise HTTPException(400, "URL must start with https://")
    if len(name) < 2:
        raise HTTPException(400, "Name must be ≥ 2 characters")
    if not body.get("username") or not body.get("password"):
        raise HTTPException(400, "Username and password required")

    poll = body.get("poll_interval_s", 60)
    if poll not in VALID_POLL_INTERVALS:
        raise HTTPException(400, f"poll_interval_s must be one of {VALID_POLL_INTERVALS}")

    pbx = await PbxService.create_instance(
        db=db, name=name, base_url=url,
        username=body["username"], password=body["password"],
        tls_policy=body.get("tls_policy", "verify"),
        poll_interval_s=poll,
        notes=body.get("notes"),
        detected_version=body.get("detected_version"),
        capabilities=body.get("capabilities"),
    )
    return {
        "id": str(pbx.id), "name": pbx.name, "base_url": pbx.base_url,
        "poll_interval_s": pbx.poll_interval_s, "message": "Instance created",
    }


@router.get("/pbx/instances")
async def list_instances(
    search: Optional[str] = Query(None),
    is_enabled: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=10, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List all PBX instances with pagination. Never returns passwords."""
    return await PbxService.list_instances(
        db, search=search, is_enabled=is_enabled, page=page, per_page=per_page
    )


@router.get("/pbx/dashboard-summary")
async def dashboard_summary(db: AsyncSession = Depends(get_db)):
    """Aggregated dashboard data — optimized single query for 100+ PBXes."""
    return await PbxService.get_dashboard_summary(db)


@router.get("/sbcs")
async def list_all_sbcs(
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """List all SBCs across all PBX instances."""
    return await PbxService.list_all_sbcs(db, status_filter=status)


@router.get("/pbx/instances/{pbx_id}/status")
async def get_instance_status(pbx_id: UUID, db: AsyncSession = Depends(get_db)):
    """Full status: trunks, SBCs, license, capabilities, health."""
    result = await PbxService.get_instance_status(db, pbx_id)
    if not result:
        raise HTTPException(404, "Instance not found")
    pbx = result["pbx"]
    return {
        "pbx": {
            "id": str(pbx.id), "name": pbx.name, "base_url": pbx.base_url,
            "detected_version": pbx.detected_version,
            "poll_interval_s": pbx.poll_interval_s,
            "last_poll_at": _iso(pbx.last_poll_at),
            "last_success_at": _iso(pbx.last_success_at),
            "last_error": pbx.last_error,
            "consecutive_failures": pbx.consecutive_failures,
        },
        "trunks": [
            {"trunk_name": t.trunk_name, "status": t.status, "last_error": t.last_error,
             "inbound_enabled": t.inbound_enabled, "outbound_enabled": t.outbound_enabled,
             "provider": t.provider, "last_status_change": _iso(t.last_status_change)}
            for t in result["trunks"]
        ],
        "sbcs": [
            {"sbc_name": s.sbc_name, "status": s.status,
             "tunnel_status": s.tunnel_status, "last_seen": _iso(s.last_seen)}
            for s in result["sbcs"]
        ],
        "license": _lic_dict(result["license"]),
        "capabilities": [
            {"feature": c.feature, "status": c.status, "method": c.method}
            for c in result["capabilities"]
        ],
        "overall_health": result["overall_health"],
    }


@router.patch("/pbx/instances/{pbx_id}")
async def update_instance(
    pbx_id: UUID, request: Request, db: AsyncSession = Depends(get_db),
):
    """Update PBX settings. Password only re-encrypted if provided."""
    body = await request.json()

    result = await db.execute(select(PbxInstance).where(PbxInstance.id == pbx_id))
    pbx = result.scalar_one_or_none()
    if not pbx:
        raise HTTPException(404, "Instance not found")

    updates = {}
    for field in ("name", "tls_policy", "notes"):
        if field in body:
            updates[field] = body[field]
    if "is_enabled" in body:
        updates["is_enabled"] = bool(body["is_enabled"])
    if "poll_interval_s" in body:
        if body["poll_interval_s"] not in VALID_POLL_INTERVALS:
            raise HTTPException(400, f"poll_interval_s must be one of {VALID_POLL_INTERVALS}")
        updates["poll_interval_s"] = body["poll_interval_s"]

    if updates:
        await db.execute(
            sa_update(PbxInstance).where(PbxInstance.id == pbx_id).values(**updates)
        )

    # Re-encrypt password if changed
    if body.get("password"):
        blob = encrypt_pw(body["password"])
        cred_upd = {
            "encrypted_password": blob.ciphertext,
            "nonce": blob.nonce, "auth_tag": blob.tag,
        }
        if body.get("username"):
            cred_upd["username"] = body["username"]
        await db.execute(
            sa_update(PbxCredential).where(PbxCredential.pbx_id == pbx_id).values(**cred_upd)
        )

    await db.commit()
    return {"message": "Updated", "id": str(pbx_id)}


@router.delete("/pbx/instances/{pbx_id}", status_code=204)
async def delete_instance(pbx_id: UUID, db: AsyncSession = Depends(get_db)):
    if not await PbxService.delete_instance(db, pbx_id):
        raise HTTPException(404, "Instance not found")


# ═══════════════════════════════════════════════════════════════════════════
# PBX — MANUAL POLL
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/pbx/instances/{pbx_id}/poll")
async def trigger_poll(pbx_id: UUID):
    """Queue an immediate poll via Celery. Returns instantly."""
    from src.workers.tasks import poll_single
    poll_single.delay(str(pbx_id))
    return {"message": "Poll queued", "pbx_id": str(pbx_id)}


# ═══════════════════════════════════════════════════════════════════════════
# BACKUPS
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/backups")
async def list_backups(
    pbx_id: Optional[UUID] = Query(None),
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
):
    """List downloaded backup records, optionally filtered by PBX."""
    return await backup_service.list_backups(db, pbx_id=pbx_id, limit=limit)


@router.post("/backups/{pbx_id}/pull")
async def pull_backup(pbx_id: UUID):
    """Manually queue a backup pull (download latest from PBX)."""
    from src.workers.tasks import pull_backup_now
    pull_backup_now.delay(str(pbx_id))
    return {"message": "Backup pull queued"}


@router.post("/backups/{pbx_id}/trigger")
async def trigger_pbx_backup(pbx_id: UUID, db: AsyncSession = Depends(get_db)):
    """Push a backup trigger to the PBX, then queue a pull after 15s."""
    result = await backup_service.trigger_backup_on_pbx(db, pbx_id)
    if result.get("success"):
        from src.workers.tasks import pull_backup_now
        pull_backup_now.apply_async(args=[str(pbx_id)], countdown=15)
    return result


@router.get("/backups/{pbx_id}/schedule")
async def get_backup_schedule(pbx_id: UUID, db: AsyncSession = Depends(get_db)):
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


@router.put("/backups/{pbx_id}/schedule")
async def set_backup_schedule(
    pbx_id: UUID, request: Request, db: AsyncSession = Depends(get_db),
):
    """Create or update a backup schedule.

    Body: { cron_expr, retain_count, retain_days, encrypt_at_rest, is_enabled }
    The cron triggers: (1) push backup trigger to PBX, (2) pull backup to app.
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
# ALERTS
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/alerts")
async def list_alerts(
    state: Optional[str] = Query(None, pattern="^(firing|acknowledged|resolved)$"),
    pbx_id: Optional[UUID] = Query(None),
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
):
    return await alert_service.list_alerts(db, state=state, pbx_id=pbx_id, limit=limit)


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Acknowledge a firing alert. Requires JWT auth."""
    ok = await alert_service.acknowledge_alert(db, alert_id, user.id)
    if not ok:
        raise HTTPException(404, "Alert not found or not in firing state")
    return {"message": "Acknowledged"}


# ═══════════════════════════════════════════════════════════════════════════
# AUDIT LOG
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/audit")
async def list_audit(
    action: Optional[str] = Query(None),
    target_type: Optional[str] = Query(None),
    success: Optional[bool] = Query(None),
    limit: int = Query(200, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    entries, total = await audit_service.list_audit_entries(
        db, action=action, target_type=target_type,
        success=success, limit=limit, offset=offset,
    )
    return {"entries": entries, "total": total}


@router.get("/audit/export")
async def export_audit_csv(
    action: Optional[str] = Query(None),
    target_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Download audit log as CSV."""
    csv_text = await audit_service.export_csv(db, action=action, target_type=target_type)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_log.csv"},
    )


# ═══════════════════════════════════════════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


# ── helpers ──────────────────────────────────────────────────────────────
def _iso(dt) -> Optional[str]:
    return dt.isoformat() if dt else None

def _lic_dict(lic):
    if not lic:
        return None
    return {
        "edition": lic.edition,
        "expiry_date": str(lic.expiry_date) if lic.expiry_date else None,
        "maintenance_expiry": str(lic.maintenance_expiry) if lic.maintenance_expiry else None,
        "max_sim_calls": lic.max_sim_calls,
        "is_valid": lic.is_valid,
        "warnings": lic.warnings or [],
    }
