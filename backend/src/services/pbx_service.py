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
    async def list_instances(db: AsyncSession) -> list[dict]:
        result = await db.execute(
            select(PbxInstance).order_by(PbxInstance.name)
        )
        instances = result.scalars().all()

        output = []
        for pbx in instances:
            # Get credential username (not password!)
            cred_result = await db.execute(
                select(PbxCredential.username).where(PbxCredential.pbx_id == pbx.id)
            )
            cred_username = cred_result.scalar_one_or_none()

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
                "credential_username": cred_username,
            })

        return output

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
