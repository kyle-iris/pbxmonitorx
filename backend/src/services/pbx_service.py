"""PBX Instance service — business logic layer.

Handles: creating instances, encrypting credentials, test connections,
fetching status, and audit logging.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.threecx_v20 import ThreeCXv20Adapter
from src.core.encryption import encrypt_password, decrypt_password, EncryptedBlob
from src.models.models import (
    PbxInstance, PbxCredential, PbxCapability,
    TrunkState, SbcState, LicenseState, AuditLog,
)

logger = logging.getLogger("pbxmonitorx.service.pbx")


class PbxService:
    """Stateless service — receives DB session per call."""

    # ── TEST CONNECTION (no DB write) ────────────────────────────────────

    @staticmethod
    async def test_connection(
        base_url: str, username: str, password: str, tls_policy: str
    ) -> dict:
        """Test connectivity to a 3CX PBX without saving anything.

        Returns a dict with: success, version, steps, capabilities
        """
        verify_tls = tls_policy != "trust_self_signed"
        adapter = ThreeCXv20Adapter(base_url, verify_tls=verify_tls)

        try:
            # Step 1: Login
            login_ok, login_steps = await adapter.login(username, password)

            if not login_ok:
                return {
                    "success": False,
                    "version": None,
                    "message": "Authentication failed",
                    "steps": [_step_to_dict(s) for s in login_steps],
                    "capabilities": [],
                }

            # Step 2: Probe
            probe = await adapter.probe_capabilities()

            all_steps = login_steps + probe.steps
            return {
                "success": True,
                "version": probe.version,
                "message": f"Connected to 3CX {probe.version or 'unknown version'}",
                "steps": [_step_to_dict(s) for s in all_steps],
                "capabilities": [
                    {
                        "feature": c.feature,
                        "status": c.status,
                        "method": c.method,
                        "endpoint_path": c.endpoint,
                        "notes": c.notes,
                    }
                    for c in probe.capabilities
                ],
            }

        except Exception as e:
            logger.exception("test_connection error")
            return {
                "success": False,
                "version": None,
                "message": f"Connection error: {str(e)}",
                "steps": [{"step": "connect", "status": "fail", "message": str(e)}],
                "capabilities": [],
            }
        finally:
            await adapter.close()

    # ── CREATE INSTANCE ──────────────────────────────────────────────────

    @staticmethod
    async def create_instance(
        db: AsyncSession,
        name: str,
        base_url: str,
        username: str,
        password: str,
        tls_policy: str = "verify",
        poll_interval_s: int = 60,
        notes: Optional[str] = None,
        created_by: Optional[UUID] = None,
        detected_version: Optional[str] = None,
        capabilities: Optional[list[dict]] = None,
    ) -> PbxInstance:
        """Create a new PBX instance with encrypted credentials.

        1. Encrypt the password using AES-256-GCM
        2. Create PBX instance record
        3. Create credential record (encrypted)
        4. Save capability matrix if provided
        5. Write audit log
        """
        # 1. Encrypt password
        blob = encrypt_password(password)

        # 2. Create PBX instance
        pbx = PbxInstance(
            name=name,
            base_url=base_url.rstrip("/"),
            tls_policy=tls_policy,
            detected_version=detected_version,
            is_enabled=True,
            poll_interval_s=poll_interval_s,
            notes=notes,
            created_by=created_by,
        )
        db.add(pbx)
        await db.flush()  # Get the UUID

        # 3. Create credential (encrypted)
        cred = PbxCredential(
            pbx_id=pbx.id,
            username=username,
            encrypted_password=blob.ciphertext,
            nonce=blob.nonce,
            auth_tag=blob.tag,
        )
        db.add(cred)

        # 4. Save capabilities if test was run
        if capabilities:
            for cap in capabilities:
                db.add(PbxCapability(
                    pbx_id=pbx.id,
                    feature=cap["feature"],
                    status=cap["status"],
                    method=cap.get("method"),
                    endpoint_path=cap.get("endpoint_path"),
                    notes=cap.get("notes"),
                    last_probed_at=datetime.utcnow(),
                ))

        # 5. Audit log
        db.add(AuditLog(
            user_id=created_by,
            username=None,  # Filled by caller
            action="pbx_created",
            target_type="pbx",
            target_id=pbx.id,
            target_name=name,
            detail={"base_url": base_url, "tls_policy": tls_policy},
            success=True,
        ))

        await db.flush()
        return pbx

    # ── GET DECRYPTED PASSWORD (in-memory only) ─────────────────────────

    @staticmethod
    async def get_decrypted_password(db: AsyncSession, pbx_id: UUID) -> tuple[str, str]:
        """Retrieve and decrypt credentials for a PBX.

        Returns (username, decrypted_password).
        Password is decrypted in-memory and never persisted.
        """
        result = await db.execute(
            select(PbxCredential).where(PbxCredential.pbx_id == pbx_id)
        )
        cred = result.scalar_one_or_none()
        if not cred:
            raise ValueError(f"No credentials found for PBX {pbx_id}")

        blob = EncryptedBlob(
            ciphertext=bytes(cred.encrypted_password),
            nonce=bytes(cred.nonce),
            tag=bytes(cred.auth_tag),
        )
        password = decrypt_password(blob)
        return cred.username, password

    # ── LIST INSTANCES ───────────────────────────────────────────────────

    @staticmethod
    async def list_instances(
        db: AsyncSession, search: str = None, is_enabled: bool = None,
        page: int = 1, per_page: int = 50,
    ) -> dict:
        """List PBX instances with pagination and search."""
        from sqlalchemy import func

        q = select(PbxInstance)
        count_q = select(func.count(PbxInstance.id))

        if search:
            pattern = f"%{search}%"
            q = q.where(PbxInstance.name.ilike(pattern) | PbxInstance.base_url.ilike(pattern))
            count_q = count_q.where(PbxInstance.name.ilike(pattern) | PbxInstance.base_url.ilike(pattern))
        if is_enabled is not None:
            q = q.where(PbxInstance.is_enabled == is_enabled)
            count_q = count_q.where(PbxInstance.is_enabled == is_enabled)

        total_result = await db.execute(count_q)
        total = total_result.scalar()

        q = q.order_by(PbxInstance.name).offset((page - 1) * per_page).limit(per_page)
        result = await db.execute(q)
        instances = result.scalars().all()

        # Batch load credential usernames
        if instances:
            pbx_ids = [pbx.id for pbx in instances]
            cred_result = await db.execute(
                select(PbxCredential.pbx_id, PbxCredential.username).where(
                    PbxCredential.pbx_id.in_(pbx_ids)
                )
            )
            cred_map = {row.pbx_id: row.username for row in cred_result.all()}
        else:
            cred_map = {}

        output = []
        for pbx in instances:
            output.append({
                "id": str(pbx.id),
                "name": pbx.name,
                "base_url": pbx.base_url,
                "tls_policy": pbx.tls_policy,
                "detected_version": pbx.detected_version,
                "is_enabled": pbx.is_enabled,
                "poll_interval_s": pbx.poll_interval_s,
                "last_poll_at": pbx.last_poll_at.isoformat() if pbx.last_poll_at else None,
                "last_success_at": pbx.last_success_at.isoformat() if pbx.last_success_at else None,
                "last_error": pbx.last_error,
                "consecutive_failures": pbx.consecutive_failures,
                "notes": pbx.notes,
                "created_at": pbx.created_at.isoformat() if pbx.created_at else None,
                "credential_username": cred_map.get(pbx.id),
            })

        return {
            "instances": output,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page,
        }

    @staticmethod
    async def get_dashboard_summary(db: AsyncSession) -> dict:
        """Aggregated dashboard data optimized for 100+ PBXes."""
        from sqlalchemy import func, case

        # PBX counts
        pbx_result = await db.execute(
            select(
                func.count(PbxInstance.id).label("total"),
                func.count(case((PbxInstance.is_enabled == True, 1))).label("enabled"),
                func.count(case((PbxInstance.consecutive_failures > 3, 1))).label("error_count"),
            )
        )
        pbx_stats = pbx_result.one()

        # Trunk stats
        trunk_result = await db.execute(
            select(
                func.count(TrunkState.id).label("total"),
                func.count(case((TrunkState.status == "registered", 1))).label("registered"),
                func.count(case((TrunkState.status.in_(["unregistered", "error"]), 1))).label("down"),
            )
        )
        trunk_stats = trunk_result.one()

        # SBC stats
        sbc_result = await db.execute(
            select(
                func.count(SbcState.id).label("total"),
                func.count(case((SbcState.status == "online", 1))).label("online"),
                func.count(case((SbcState.status == "offline", 1))).label("offline"),
            )
        )
        sbc_stats = sbc_result.one()

        # Alert counts
        from src.models.models import AlertEvent
        alert_result = await db.execute(
            select(
                func.count(case((AlertEvent.state == "firing", 1))).label("firing"),
                func.count(case((AlertEvent.state == "acknowledged", 1))).label("acknowledged"),
            )
        )
        alert_stats = alert_result.one()

        # Backup stats
        from src.models.models import BackupRecord
        backup_result = await db.execute(
            select(
                func.count(BackupRecord.id).label("total"),
                func.sum(BackupRecord.size_bytes).label("total_bytes"),
            ).where(BackupRecord.is_downloaded == True)
        )
        backup_stats = backup_result.one()

        # Recent problem PBXes (for quick overview)
        problem_result = await db.execute(
            select(PbxInstance).where(
                (PbxInstance.consecutive_failures > 0) & (PbxInstance.is_enabled == True)
            ).order_by(PbxInstance.consecutive_failures.desc()).limit(10)
        )
        problem_pbxes = [
            {"id": str(p.id), "name": p.name, "failures": p.consecutive_failures, "error": p.last_error}
            for p in problem_result.scalars().all()
        ]

        return {
            "pbx": {"total": pbx_stats.total, "enabled": pbx_stats.enabled, "errors": pbx_stats.error_count},
            "trunks": {"total": trunk_stats.total, "registered": trunk_stats.registered, "down": trunk_stats.down},
            "sbcs": {"total": sbc_stats.total, "online": sbc_stats.online, "offline": sbc_stats.offline},
            "alerts": {"firing": alert_stats.firing, "acknowledged": alert_stats.acknowledged},
            "backups": {"total": backup_stats.total or 0, "total_bytes": backup_stats.total_bytes or 0},
            "problem_pbxes": problem_pbxes,
        }

    @staticmethod
    async def list_all_sbcs(db: AsyncSession, status_filter: str = None) -> list[dict]:
        """List all SBCs across all PBXes with their PBX name."""
        q = select(SbcState, PbxInstance.name.label("pbx_name")).join(
            PbxInstance, SbcState.pbx_id == PbxInstance.id
        )
        if status_filter:
            q = q.where(SbcState.status == status_filter)
        q = q.order_by(PbxInstance.name, SbcState.sbc_name)

        result = await db.execute(q)
        return [
            {
                "id": str(row.SbcState.id),
                "pbx_id": str(row.SbcState.pbx_id),
                "pbx_name": row.pbx_name,
                "sbc_name": row.SbcState.sbc_name,
                "status": row.SbcState.status,
                "tunnel_status": row.SbcState.tunnel_status,
                "last_seen": row.SbcState.last_seen.isoformat() if row.SbcState.last_seen else None,
                "connection_info": row.SbcState.connection_info or {},
                "extra_data": row.SbcState.extra_data or {},
            }
            for row in result.all()
        ]

    # ── GET INSTANCE + STATUS ────────────────────────────────────────────

    @staticmethod
    async def get_instance_status(db: AsyncSession, pbx_id: UUID) -> Optional[dict]:
        result = await db.execute(
            select(PbxInstance).where(PbxInstance.id == pbx_id)
        )
        pbx = result.scalar_one_or_none()
        if not pbx:
            return None

        # Trunks
        trunk_result = await db.execute(
            select(TrunkState).where(TrunkState.pbx_id == pbx_id)
        )
        trunks = trunk_result.scalars().all()

        # SBCs
        sbc_result = await db.execute(
            select(SbcState).where(SbcState.pbx_id == pbx_id)
        )
        sbcs = sbc_result.scalars().all()

        # License
        lic_result = await db.execute(
            select(LicenseState).where(LicenseState.pbx_id == pbx_id)
        )
        license = lic_result.scalar_one_or_none()

        # Capabilities
        cap_result = await db.execute(
            select(PbxCapability).where(PbxCapability.pbx_id == pbx_id)
        )
        caps = cap_result.scalars().all()

        # Calculate health
        health = "healthy"
        if any(t.status != "registered" for t in trunks):
            health = "warning"
        if any(s.status == "offline" for s in sbcs):
            health = "warning"
        if license and not license.is_valid:
            health = "error"
        if pbx.consecutive_failures > 3:
            health = "error"

        return {
            "pbx": pbx,
            "trunks": trunks,
            "sbcs": sbcs,
            "license": license,
            "capabilities": caps,
            "overall_health": health,
        }

    # ── DELETE INSTANCE ──────────────────────────────────────────────────

    @staticmethod
    async def delete_instance(
        db: AsyncSession, pbx_id: UUID, user_id: Optional[UUID] = None
    ) -> bool:
        result = await db.execute(
            select(PbxInstance).where(PbxInstance.id == pbx_id)
        )
        pbx = result.scalar_one_or_none()
        if not pbx:
            return False

        db.add(AuditLog(
            user_id=user_id,
            action="pbx_deleted",
            target_type="pbx",
            target_id=pbx_id,
            target_name=pbx.name,
            success=True,
        ))

        await db.delete(pbx)  # CASCADE handles credentials, capabilities, states
        return True


def _step_to_dict(step) -> dict:
    return {
        "step": step.step,
        "status": step.status,
        "message": step.message,
        "duration_ms": step.duration_ms,
    }
