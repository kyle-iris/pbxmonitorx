"""Polling service — connects to each PBX, fetches data, diffs, persists.

This is the heart of the monitoring system. For each enabled PBX:
1. Decrypt credentials
2. Create adapter, login
3. Fetch trunks/sbcs/license
4. Diff against previous state (detect changes)
5. Upsert state tables (trunk_state, sbc_state, license_state)
6. Insert poll_result with diff summary
7. Update pbx_instance.last_poll_at / last_error / consecutive_failures
8. On failure: exponential backoff via consecutive_failures counter
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict
from datetime import datetime, timezone, date
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.adapters.threecx_v20 import ThreeCXv20Adapter, TrunkData, SbcData, LicenseData
from src.core.encryption import decrypt_password, EncryptedBlob
from src.models.models import (
    PbxInstance, PbxCredential, TrunkState, SbcState,
    LicenseState, PollResult, AuditLog,
)
from src.services.event_log_service import log_event, log_error

logger = logging.getLogger("pbxmonitorx.polling")


async def poll_single_instance(db: AsyncSession, pbx_id: UUID) -> dict:
    """Poll a single PBX instance end-to-end.

    Returns a summary dict with success, changes detected, timing.
    """
    t0 = time.monotonic()

    # 1. Load PBX + credentials
    result = await db.execute(select(PbxInstance).where(PbxInstance.id == pbx_id))
    pbx = result.scalar_one_or_none()
    if not pbx or not pbx.is_enabled:
        return {"success": False, "error": "PBX not found or disabled"}

    await log_event(db, "polling", "poll_started", f"Starting poll for {pbx.name}",
                    level="debug", pbx_id=pbx.id, pbx_name=pbx.name)

    cred_result = await db.execute(select(PbxCredential).where(PbxCredential.pbx_id == pbx_id))
    cred = cred_result.scalar_one_or_none()
    if not cred:
        return {"success": False, "error": "No credentials stored"}

    # 2. Decrypt password
    try:
        blob = EncryptedBlob(
            ciphertext=bytes(cred.encrypted_password),
            nonce=bytes(cred.nonce),
            tag=bytes(cred.auth_tag),
        )
        password = decrypt_password(blob)
    except Exception as e:
        logger.error(f"Decrypt failed for PBX {pbx.name}: {e}")
        await _record_failure(db, pbx, str(e), int((time.monotonic() - t0) * 1000))
        return {"success": False, "error": "Credential decryption failed"}

    # 3. Connect and fetch
    verify_tls = pbx.tls_policy != "trust_self_signed"
    adapter = ThreeCXv20Adapter(pbx.base_url, verify_tls=verify_tls)

    try:
        login_ok, _ = await adapter.login(cred.username, password)
        if not login_ok:
            await _record_failure(db, pbx, "Authentication failed", int((time.monotonic() - t0) * 1000))
            return {"success": False, "error": "Authentication failed"}

        # Fetch all data
        trunks = await adapter.get_trunks()
        sbcs = await adapter.get_sbcs()
        license_info = await adapter.get_license()

        duration_ms = int((time.monotonic() - t0) * 1000)

        # 4. Diff and persist
        diff_parts = []

        trunk_changes = await _upsert_trunks(db, pbx_id, trunks)
        if trunk_changes:
            diff_parts.extend(trunk_changes)

        sbc_changes = await _upsert_sbcs(db, pbx_id, sbcs)
        if sbc_changes:
            diff_parts.extend(sbc_changes)

        license_changes = await _upsert_license(db, pbx_id, license_info)
        if license_changes:
            diff_parts.extend(license_changes)

        diff_summary = "; ".join(diff_parts) if diff_parts else "No changes"

        # 5. Record poll result
        db.add(PollResult(
            pbx_id=pbx_id,
            poll_type="full",
            success=True,
            duration_ms=duration_ms,
            trunk_data=[_trunk_to_dict(t) for t in trunks],
            sbc_data=[_sbc_to_dict(s) for s in sbcs],
            license_data=_license_to_dict(license_info) if license_info else None,
            diff_summary=diff_summary,
        ))

        # 6. Update PBX instance
        now = datetime.now(timezone.utc)
        await db.execute(update(PbxInstance).where(PbxInstance.id == pbx_id).values(
            last_poll_at=now,
            last_success_at=now,
            last_error=None,
            consecutive_failures=0,
        ))

        await db.commit()

        await log_event(db, "polling", "poll_completed",
                        f"Poll {pbx.name}: OK in {duration_ms}ms — {diff_summary}",
                        pbx_id=pbx.id, pbx_name=pbx.name, duration_ms=duration_ms,
                        detail={"trunks": len(trunks), "sbcs": len(sbcs), "changes": diff_parts})

        logger.info(f"Poll {pbx.name}: OK in {duration_ms}ms — {diff_summary}")
        return {
            "success": True,
            "pbx_name": pbx.name,
            "duration_ms": duration_ms,
            "trunks": len(trunks),
            "sbcs": len(sbcs),
            "changes": diff_parts,
        }

    except Exception as e:
        logger.exception(f"Poll failed for {pbx.name}")
        await log_error(db, "polling", "poll_failed", f"Poll failed for {pbx.name}: {e}",
                        error=e, pbx_id=pbx.id, pbx_name=pbx.name,
                        duration_ms=int((time.monotonic() - t0) * 1000))
        await _record_failure(db, pbx, str(e), int((time.monotonic() - t0) * 1000))
        return {"success": False, "error": str(e)}

    finally:
        await adapter.close()


async def poll_all_due_instances(db: AsyncSession) -> list[dict]:
    """Poll all due PBX instances with concurrent batches.

    Uses asyncio.gather in batches of 10 for scalability with 100+ instances.
    """
    import asyncio
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(PbxInstance).where(PbxInstance.is_enabled == True)
    )
    instances = result.scalars().all()

    due = [pbx for pbx in instances if _is_poll_due(pbx, now)]
    if not due:
        return []

    results = []
    batch_size = 10  # Poll 10 concurrently

    for i in range(0, len(due), batch_size):
        batch = due[i:i + batch_size]
        batch_results = await asyncio.gather(
            *[poll_single_instance(db, pbx.id) for pbx in batch],
            return_exceptions=True,
        )
        for r in batch_results:
            if isinstance(r, Exception):
                results.append({"success": False, "error": str(r)})
            else:
                results.append(r)

    return results


def _is_poll_due(pbx: PbxInstance, now: datetime) -> bool:
    """Check if this PBX needs polling, respecting backoff."""
    if not pbx.last_poll_at:
        return True

    interval = pbx.poll_interval_s

    # Exponential backoff on failures: double interval per consecutive failure, cap at 600s
    if pbx.consecutive_failures > 0:
        backoff = min(interval * (2 ** pbx.consecutive_failures), 600)
        interval = max(interval, backoff)

    elapsed = (now - pbx.last_poll_at.replace(tzinfo=timezone.utc)).total_seconds()
    return elapsed >= interval


async def _record_failure(db: AsyncSession, pbx: PbxInstance, error: str, duration_ms: int):
    """Record a poll failure."""
    now = datetime.now(timezone.utc)
    new_failures = pbx.consecutive_failures + 1

    await db.execute(update(PbxInstance).where(PbxInstance.id == pbx.id).values(
        last_poll_at=now,
        last_error=error,
        consecutive_failures=new_failures,
    ))

    db.add(PollResult(
        pbx_id=pbx.id,
        poll_type="full",
        success=False,
        duration_ms=duration_ms,
        error_message=error,
    ))

    db.add(AuditLog(
        username="system", action="poll_failed",
        target_type="pbx", target_id=pbx.id, target_name=pbx.name,
        detail={"error": error, "consecutive_failures": new_failures},
        success=False, error_message=error,
    ))

    await db.commit()


# ═══════════════════════════════════════════════════════════════════════════
# UPSERT STATE TABLES (detect changes)
# ═══════════════════════════════════════════════════════════════════════════

async def _upsert_trunks(db: AsyncSession, pbx_id: UUID, trunks: list[TrunkData]) -> list[str]:
    """Upsert trunk_state rows. Returns list of human-readable change descriptions."""
    changes = []

    # Load current state
    result = await db.execute(select(TrunkState).where(TrunkState.pbx_id == pbx_id))
    existing = {t.trunk_name: t for t in result.scalars().all()}
    seen_names = set()

    now = datetime.now(timezone.utc)

    for t in trunks:
        seen_names.add(t.name)
        prev = existing.get(t.name)

        if prev:
            # Check for status change
            if prev.status != t.status:
                changes.append(f"Trunk '{t.name}': {prev.status} → {t.status}")
                await db.execute(update(TrunkState).where(TrunkState.id == prev.id).values(
                    status=t.status, last_error=t.last_error,
                    last_status_change=now, inbound_enabled=t.inbound_ok,
                    outbound_enabled=t.outbound_ok, provider=t.provider,
                    remote_id=t.remote_id, extra_data=t.raw, updated_at=now,
                ))
            else:
                # Update metadata even if status unchanged
                await db.execute(update(TrunkState).where(TrunkState.id == prev.id).values(
                    last_error=t.last_error, inbound_enabled=t.inbound_ok,
                    outbound_enabled=t.outbound_ok, updated_at=now,
                ))
        else:
            # New trunk
            changes.append(f"Trunk '{t.name}' discovered ({t.status})")
            db.add(TrunkState(
                pbx_id=pbx_id, trunk_name=t.name, remote_id=t.remote_id,
                status=t.status, last_error=t.last_error,
                last_status_change=now, inbound_enabled=t.inbound_ok,
                outbound_enabled=t.outbound_ok, provider=t.provider,
                extra_data=t.raw,
            ))

    # Remove trunks no longer reported by PBX
    for name, prev in existing.items():
        if name not in seen_names:
            changes.append(f"Trunk '{name}' removed from PBX")
            await db.execute(delete(TrunkState).where(TrunkState.id == prev.id))

    return changes


async def _upsert_sbcs(db: AsyncSession, pbx_id: UUID, sbcs: list[SbcData]) -> list[str]:
    changes = []
    result = await db.execute(select(SbcState).where(SbcState.pbx_id == pbx_id))
    existing = {s.sbc_name: s for s in result.scalars().all()}
    seen = set()
    now = datetime.now(timezone.utc)

    for s in sbcs:
        seen.add(s.name)
        prev = existing.get(s.name)
        if prev:
            if prev.status != s.status:
                changes.append(f"SBC '{s.name}': {prev.status} → {s.status}")
            await db.execute(update(SbcState).where(SbcState.id == prev.id).values(
                status=s.status, last_seen=now if s.status == "online" else prev.last_seen,
                tunnel_status=s.tunnel_status, remote_id=s.remote_id,
                extra_data=s.raw, updated_at=now,
            ))
        else:
            changes.append(f"SBC '{s.name}' discovered ({s.status})")
            db.add(SbcState(
                pbx_id=pbx_id, sbc_name=s.name, remote_id=s.remote_id,
                status=s.status, last_seen=now if s.status == "online" else None,
                tunnel_status=s.tunnel_status, extra_data=s.raw,
            ))

    for name, prev in existing.items():
        if name not in seen:
            changes.append(f"SBC '{name}' removed")
            await db.execute(delete(SbcState).where(SbcState.id == prev.id))

    return changes


async def _upsert_license(db: AsyncSession, pbx_id: UUID, lic: Optional[LicenseData]) -> list[str]:
    if not lic:
        return []

    changes = []
    result = await db.execute(select(LicenseState).where(LicenseState.pbx_id == pbx_id))
    prev = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)

    # Parse expiry to date
    expiry_date = None
    if lic.expiry:
        try:
            expiry_date = date.fromisoformat(str(lic.expiry)[:10])
        except Exception:
            pass

    maint_date = None
    if lic.maintenance_expiry:
        try:
            maint_date = date.fromisoformat(str(lic.maintenance_expiry)[:10])
        except Exception:
            pass

    if prev:
        if prev.is_valid != lic.is_valid:
            changes.append(f"License validity: {prev.is_valid} → {lic.is_valid}")
        if prev.edition != lic.edition:
            changes.append(f"License edition: {prev.edition} → {lic.edition}")

        await db.execute(update(LicenseState).where(LicenseState.id == prev.id).values(
            edition=lic.edition, license_key_masked=lic.key_masked,
            expiry_date=expiry_date, maintenance_expiry=maint_date,
            max_sim_calls=lic.max_calls, is_valid=lic.is_valid,
            warnings=lic.warnings, extra_data=lic.raw, updated_at=now,
        ))
    else:
        changes.append(f"License discovered: {lic.edition}")
        db.add(LicenseState(
            pbx_id=pbx_id, edition=lic.edition, license_key_masked=lic.key_masked,
            expiry_date=expiry_date, maintenance_expiry=maint_date,
            max_sim_calls=lic.max_calls, is_valid=lic.is_valid,
            warnings=lic.warnings, extra_data=lic.raw,
        ))

    return changes


# ═══════════════════════════════════════════════════════════════════════════
# Serialization helpers
# ═══════════════════════════════════════════════════════════════════════════

def _trunk_to_dict(t: TrunkData) -> dict:
    return {"name": t.name, "status": t.status, "provider": t.provider,
            "last_error": t.last_error, "inbound": t.inbound_ok, "outbound": t.outbound_ok}

def _sbc_to_dict(s: SbcData) -> dict:
    return {"name": s.name, "status": s.status, "tunnel": s.tunnel_status}

def _license_to_dict(l: LicenseData) -> dict:
    return {"edition": l.edition, "expiry": l.expiry, "valid": l.is_valid,
            "calls": l.max_calls, "warnings": l.warnings}
