"""Phone number inventory service — sync, query, export, and report.

Manages the phone number/DID inventory across all monitored PBX instances.
Numbers are discovered via the 3CX adapter and stored in trunk_phone_number.

Flow:
  1. Sync connects to PBX via adapter, fetches all phone numbers per trunk
  2. Upserts into trunk_phone_number table (add new, update existing)
  3. Numbers not seen during sync are marked stale (last_seen_at not updated)
  4. Query, export, and report functions operate on the local inventory
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, update, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.threecx_v20 import ThreeCXv20Adapter, PhoneNumberData
from src.core.encryption import decrypt_password, EncryptedBlob
from src.models.models import (
    PbxInstance, PbxCredential, TrunkState, TrunkPhoneNumber, AuditLog,
)

logger = logging.getLogger("pbxmonitorx.service.phone_numbers")


# ═══════════════════════════════════════════════════════════════════════════
# SYNC — fetch from PBX and upsert into DB
# ═══════════════════════════════════════════════════════════════════════════

async def sync_phone_numbers(db: AsyncSession, pbx_id: UUID) -> dict:
    """Connect to PBX via adapter, fetch all phone numbers, and upsert.

    Numbers not seen during this sync have their last_seen_at left unchanged
    (stale detection). Numbers are never auto-deleted to preserve audit trail.

    Returns:
        dict with keys: success, synced, added, updated, stale, error
    """
    adapter, pbx = await _get_adapter(db, pbx_id)
    if not adapter:
        error_msg = "Could not connect to PBX" if pbx else "PBX not found"
        return {"success": False, "synced": 0, "added": 0, "updated": 0, "stale": 0, "error": error_msg}

    try:
        # Fetch all phone numbers from the PBX
        phone_numbers: list[PhoneNumberData] = await adapter.get_phone_numbers()
        logger.info(f"Fetched {len(phone_numbers)} phone number(s) from {pbx.name}")

        if not phone_numbers:
            return {
                "success": True, "synced": 0, "added": 0, "updated": 0, "stale": 0,
                "message": "No phone numbers found on PBX",
            }

        # Build a lookup of existing trunk_state records for trunk_id resolution
        trunk_result = await db.execute(
            select(TrunkState).where(TrunkState.pbx_id == pbx_id)
        )
        trunk_map: dict[str, UUID] = {
            t.trunk_name: t.id for t in trunk_result.scalars().all()
        }

        # Load existing phone numbers for this PBX
        existing_result = await db.execute(
            select(TrunkPhoneNumber).where(TrunkPhoneNumber.pbx_id == pbx_id)
        )
        existing_map: dict[tuple[str, str], TrunkPhoneNumber] = {
            (r.phone_number, r.trunk_name): r
            for r in existing_result.scalars().all()
        }

        now = datetime.now(timezone.utc)
        added = 0
        updated = 0
        seen_keys: set[tuple[str, str]] = set()

        for pn in phone_numbers:
            key = (pn.number, pn.trunk_name)
            seen_keys.add(key)

            trunk_id = trunk_map.get(pn.trunk_name)

            if key in existing_map:
                # Update existing record
                existing = existing_map[key]
                await db.execute(
                    update(TrunkPhoneNumber)
                    .where(TrunkPhoneNumber.id == existing.id)
                    .values(
                        trunk_id=trunk_id,
                        display_name=pn.display_name,
                        number_type=pn.number_type,
                        is_main_number=pn.is_main,
                        inbound_enabled=pn.inbound,
                        outbound_enabled=pn.outbound,
                        extra_data=pn.raw,
                        last_seen_at=now,
                        updated_at=now,
                    )
                )
                updated += 1
            else:
                # Insert new record
                db.add(TrunkPhoneNumber(
                    pbx_id=pbx_id,
                    trunk_id=trunk_id,
                    trunk_name=pn.trunk_name,
                    phone_number=pn.number,
                    display_name=pn.display_name,
                    number_type=pn.number_type,
                    is_main_number=pn.is_main,
                    inbound_enabled=pn.inbound,
                    outbound_enabled=pn.outbound,
                    extra_data=pn.raw,
                    last_seen_at=now,
                ))
                added += 1

        # Count stale numbers (exist in DB but not seen in this sync)
        stale = len(existing_map) - len(seen_keys & set(existing_map.keys()))

        # Audit log
        db.add(AuditLog(
            username="system",
            action="phone_numbers_synced",
            target_type="pbx",
            target_id=pbx_id,
            target_name=pbx.name,
            detail={
                "synced": len(phone_numbers),
                "added": added,
                "updated": updated,
                "stale": stale,
            },
            success=True,
        ))
        await db.commit()

        logger.info(
            f"Phone number sync for {pbx.name}: "
            f"synced={len(phone_numbers)}, added={added}, updated={updated}, stale={stale}"
        )

        return {
            "success": True,
            "synced": len(phone_numbers),
            "added": added,
            "updated": updated,
            "stale": stale,
        }

    except Exception as e:
        logger.exception(f"Phone number sync failed for {pbx.name}")
        return {
            "success": False, "synced": 0, "added": 0, "updated": 0, "stale": 0,
            "error": str(e),
        }
    finally:
        await adapter.close()


# ═══════════════════════════════════════════════════════════════════════════
# QUERY — list phone numbers with filtering
# ═══════════════════════════════════════════════════════════════════════════

async def list_phone_numbers(
    db: AsyncSession,
    pbx_id: Optional[UUID] = None,
    trunk_name: Optional[str] = None,
    number_type: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 500,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Query phone numbers with optional filters.

    Args:
        db: Async database session
        pbx_id: Filter by specific PBX instance
        trunk_name: Filter by trunk name (exact match)
        number_type: Filter by number type (did, main, fax, etc.)
        search: Search phone_number or display_name (ILIKE)
        limit: Max results (default 500)
        offset: Pagination offset

    Returns:
        Tuple of (list of phone number dicts, total count)
    """
    q = select(TrunkPhoneNumber).order_by(
        TrunkPhoneNumber.trunk_name, TrunkPhoneNumber.phone_number
    )
    count_q = select(func.count(TrunkPhoneNumber.id))

    # Apply filters
    if pbx_id:
        q = q.where(TrunkPhoneNumber.pbx_id == pbx_id)
        count_q = count_q.where(TrunkPhoneNumber.pbx_id == pbx_id)

    if trunk_name:
        q = q.where(TrunkPhoneNumber.trunk_name == trunk_name)
        count_q = count_q.where(TrunkPhoneNumber.trunk_name == trunk_name)

    if number_type:
        q = q.where(TrunkPhoneNumber.number_type == number_type)
        count_q = count_q.where(TrunkPhoneNumber.number_type == number_type)

    if search:
        search_filter = or_(
            TrunkPhoneNumber.phone_number.ilike(f"%{search}%"),
            TrunkPhoneNumber.display_name.ilike(f"%{search}%"),
        )
        q = q.where(search_filter)
        count_q = count_q.where(search_filter)

    total = (await db.execute(count_q)).scalar() or 0
    result = await db.execute(q.offset(offset).limit(limit))
    records = result.scalars().all()

    # Resolve PBX names for display
    pbx_names = await _get_pbx_name_map(db)

    entries = [
        {
            "id": str(r.id),
            "pbx_id": str(r.pbx_id),
            "pbx_name": pbx_names.get(r.pbx_id, "Unknown"),
            "trunk_name": r.trunk_name,
            "phone_number": r.phone_number,
            "display_name": r.display_name,
            "number_type": r.number_type,
            "is_main_number": r.is_main_number,
            "inbound_enabled": r.inbound_enabled,
            "outbound_enabled": r.outbound_enabled,
            "description": r.description,
            "last_seen_at": r.last_seen_at.isoformat() if r.last_seen_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in records
    ]

    return entries, total


# ═══════════════════════════════════════════════════════════════════════════
# SUMMARY — aggregated stats for dashboard
# ═══════════════════════════════════════════════════════════════════════════

async def get_phone_number_summary(
    db: AsyncSession, pbx_id: Optional[UUID] = None
) -> dict:
    """Return aggregated phone number statistics for the dashboard.

    Returns:
        dict with: total, by_type, by_trunk, by_pbx
    """
    base_filter = []
    if pbx_id:
        base_filter.append(TrunkPhoneNumber.pbx_id == pbx_id)

    # Total count
    total_q = select(func.count(TrunkPhoneNumber.id))
    if base_filter:
        total_q = total_q.where(*base_filter)
    total = (await db.execute(total_q)).scalar() or 0

    # Count by number_type
    type_q = select(
        TrunkPhoneNumber.number_type,
        func.count(TrunkPhoneNumber.id).label("count"),
    ).group_by(TrunkPhoneNumber.number_type)
    if base_filter:
        type_q = type_q.where(*base_filter)
    type_result = await db.execute(type_q)
    by_type = {row[0] or "unknown": row[1] for row in type_result.all()}

    # Count by trunk
    trunk_q = select(
        TrunkPhoneNumber.trunk_name,
        func.count(TrunkPhoneNumber.id).label("count"),
    ).group_by(TrunkPhoneNumber.trunk_name)
    if base_filter:
        trunk_q = trunk_q.where(*base_filter)
    trunk_result = await db.execute(trunk_q)
    by_trunk = {row[0] or "Unknown": row[1] for row in trunk_result.all()}

    # Count by PBX
    pbx_q = select(
        TrunkPhoneNumber.pbx_id,
        func.count(TrunkPhoneNumber.id).label("count"),
    ).group_by(TrunkPhoneNumber.pbx_id)
    if base_filter:
        pbx_q = pbx_q.where(*base_filter)
    pbx_result = await db.execute(pbx_q)

    pbx_names = await _get_pbx_name_map(db)
    by_pbx = {
        pbx_names.get(row[0], str(row[0])): row[1]
        for row in pbx_result.all()
    }

    # Count main numbers
    main_q = select(func.count(TrunkPhoneNumber.id)).where(
        TrunkPhoneNumber.is_main_number == True
    )
    if base_filter:
        main_q = main_q.where(*base_filter)
    main_count = (await db.execute(main_q)).scalar() or 0

    return {
        "total": total,
        "main_numbers": main_count,
        "by_type": by_type,
        "by_trunk": by_trunk,
        "by_pbx": by_pbx,
    }


# ═══════════════════════════════════════════════════════════════════════════
# CSV EXPORT
# ═══════════════════════════════════════════════════════════════════════════

async def export_phone_numbers_csv(
    db: AsyncSession,
    pbx_id: Optional[UUID] = None,
    trunk_name: Optional[str] = None,
) -> str:
    """Export phone numbers as a CSV string.

    Columns: PBX Name, Trunk, Phone Number, Display Name, Type,
             Inbound, Outbound, Description
    """
    entries, _ = await list_phone_numbers(
        db, pbx_id=pbx_id, trunk_name=trunk_name, limit=50000
    )

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "PBX Name", "Trunk", "Phone Number", "Display Name",
        "Type", "Inbound", "Outbound", "Description",
    ])
    writer.writeheader()

    for e in entries:
        writer.writerow({
            "PBX Name": e["pbx_name"],
            "Trunk": e["trunk_name"],
            "Phone Number": e["phone_number"],
            "Display Name": e["display_name"] or "",
            "Type": e["number_type"] or "did",
            "Inbound": _bool_display(e["inbound_enabled"]),
            "Outbound": _bool_display(e["outbound_enabled"]),
            "Description": e["description"] or "",
        })

    return output.getvalue()


# ═══════════════════════════════════════════════════════════════════════════
# REPORT — comprehensive phone number report
# ═══════════════════════════════════════════════════════════════════════════

async def generate_phone_report(
    db: AsyncSession, pbx_id: Optional[UUID] = None
) -> dict:
    """Generate a comprehensive phone number report.

    Includes:
        - Summary statistics (total, by type, by trunk, by PBX)
        - Per-PBX breakdown with trunk details
        - Type distribution percentages
        - Stale number detection (not seen in recent syncs)
    """
    summary = await get_phone_number_summary(db, pbx_id=pbx_id)

    # Build per-PBX detail
    pbx_names = await _get_pbx_name_map(db)
    per_pbx: list[dict] = []

    base_filter = []
    if pbx_id:
        base_filter.append(TrunkPhoneNumber.pbx_id == pbx_id)

    # Per-PBX, per-trunk breakdown
    breakdown_q = select(
        TrunkPhoneNumber.pbx_id,
        TrunkPhoneNumber.trunk_name,
        TrunkPhoneNumber.number_type,
        func.count(TrunkPhoneNumber.id).label("count"),
    ).group_by(
        TrunkPhoneNumber.pbx_id,
        TrunkPhoneNumber.trunk_name,
        TrunkPhoneNumber.number_type,
    )
    if base_filter:
        breakdown_q = breakdown_q.where(*base_filter)

    breakdown_result = await db.execute(breakdown_q)
    breakdown_rows = breakdown_result.all()

    # Organize into nested structure
    pbx_data: dict[UUID, dict] = {}
    for row_pbx_id, row_trunk, row_type, row_count in breakdown_rows:
        if row_pbx_id not in pbx_data:
            pbx_data[row_pbx_id] = {
                "pbx_id": str(row_pbx_id),
                "pbx_name": pbx_names.get(row_pbx_id, str(row_pbx_id)),
                "total": 0,
                "trunks": {},
            }
        pbx_data[row_pbx_id]["total"] += row_count

        if row_trunk not in pbx_data[row_pbx_id]["trunks"]:
            pbx_data[row_pbx_id]["trunks"][row_trunk] = {"total": 0, "by_type": {}}
        pbx_data[row_pbx_id]["trunks"][row_trunk]["total"] += row_count
        pbx_data[row_pbx_id]["trunks"][row_trunk]["by_type"][row_type or "did"] = row_count

    # Convert trunks dict to list for serialization
    for pbx_entry in pbx_data.values():
        pbx_entry["trunks"] = [
            {"trunk_name": name, **data}
            for name, data in pbx_entry["trunks"].items()
        ]
        per_pbx.append(pbx_entry)

    # Type distribution as percentages
    type_distribution: dict[str, float] = {}
    if summary["total"] > 0:
        for ntype, count in summary["by_type"].items():
            type_distribution[ntype] = round(count / summary["total"] * 100, 1)

    # Stale number count (last_seen_at older than 24 hours)
    from datetime import timedelta
    stale_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    stale_q = select(func.count(TrunkPhoneNumber.id)).where(
        TrunkPhoneNumber.last_seen_at < stale_cutoff
    )
    if base_filter:
        stale_q = stale_q.where(*base_filter)
    stale_count = (await db.execute(stale_q)).scalar() or 0

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "type_distribution_pct": type_distribution,
        "stale_numbers": stale_count,
        "per_pbx": per_pbx,
    }


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

async def _get_adapter(
    db: AsyncSession, pbx_id: UUID
) -> tuple[Optional[ThreeCXv20Adapter], Optional[PbxInstance]]:
    """Create an authenticated adapter for a PBX.

    Loads PBX instance and credentials, decrypts password, creates adapter,
    and performs login. Returns (adapter, pbx) or (None, pbx/None) on failure.
    """
    pbx_result = await db.execute(select(PbxInstance).where(PbxInstance.id == pbx_id))
    pbx = pbx_result.scalar_one_or_none()
    if not pbx:
        return None, None

    cred_result = await db.execute(select(PbxCredential).where(PbxCredential.pbx_id == pbx_id))
    cred = cred_result.scalar_one_or_none()
    if not cred:
        logger.warning(f"No credentials found for PBX {pbx.name} ({pbx_id})")
        return None, pbx

    try:
        blob = EncryptedBlob(
            ciphertext=bytes(cred.encrypted_password),
            nonce=bytes(cred.nonce),
            tag=bytes(cred.auth_tag),
        )
        password = decrypt_password(blob)
    except Exception:
        logger.error(f"Failed to decrypt credentials for PBX {pbx.name}")
        return None, pbx

    adapter = ThreeCXv20Adapter(
        pbx.base_url, verify_tls=pbx.tls_policy != "trust_self_signed"
    )
    ok, _ = await adapter.login(cred.username, password)
    if not ok:
        logger.warning(f"Login failed for PBX {pbx.name}")
        await adapter.close()
        return None, pbx

    return adapter, pbx


async def _get_pbx_name_map(db: AsyncSession) -> dict[UUID, str]:
    """Build a mapping of PBX ID -> PBX name for display purposes."""
    result = await db.execute(select(PbxInstance.id, PbxInstance.name))
    return {row[0]: row[1] for row in result.all()}


def _bool_display(value: Optional[bool]) -> str:
    """Convert a boolean to a display string for CSV export."""
    if value is None:
        return "N/A"
    return "Yes" if value else "No"
