"""Phone number inventory API routes.

Endpoints:
    GET  /phone-numbers              List all phone numbers with filtering
    GET  /phone-numbers/summary      Aggregated summary/stats
    POST /phone-numbers/sync/{id}    Trigger sync for a specific PBX
    POST /phone-numbers/sync-all     Trigger sync for all PBXes
    GET  /phone-numbers/export       Export as CSV
    GET  /phone-numbers/report       Generate comprehensive report
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.core.auth import get_current_user, require_role, CurrentUser
from src.models.models import PbxInstance
from src.services import phone_number_service

logger = logging.getLogger("pbxmonitorx.api.phone_numbers")

router = APIRouter(prefix="/phone-numbers", tags=["Phone Numbers"])


# ═══════════════════════════════════════════════════════════════════════════
# LIST
# ═══════════════════════════════════════════════════════════════════════════

@router.get("")
async def list_phone_numbers(
    pbx_id: Optional[UUID] = Query(None, description="Filter by PBX instance"),
    trunk_name: Optional[str] = Query(None, description="Filter by trunk name"),
    number_type: Optional[str] = Query(None, description="Filter by number type (did, main, fax, etc.)"),
    search: Optional[str] = Query(None, description="Search phone number or display name"),
    limit: int = Query(500, le=5000, ge=1, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all phone numbers with optional filtering and pagination.

    Supports filtering by PBX, trunk, number type, and free-text search
    against phone number and display name fields.
    """
    entries, total = await phone_number_service.list_phone_numbers(
        db,
        pbx_id=pbx_id,
        trunk_name=trunk_name,
        number_type=number_type,
        search=search,
        limit=limit,
        offset=offset,
    )
    return {"entries": entries, "total": total, "limit": limit, "offset": offset}


# ═══════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/summary")
async def phone_number_summary(
    pbx_id: Optional[UUID] = Query(None, description="Filter by PBX instance"),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return aggregated phone number statistics for the dashboard.

    Includes total count, breakdown by type, by trunk, and by PBX.
    """
    return await phone_number_service.get_phone_number_summary(db, pbx_id=pbx_id)


# ═══════════════════════════════════════════════════════════════════════════
# SYNC
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/sync/{pbx_id}")
async def sync_phone_numbers(
    pbx_id: UUID,
    user: CurrentUser = Depends(require_role("admin", "operator")),
    db: AsyncSession = Depends(get_db),
):
    """Trigger phone number sync for a specific PBX.

    Connects to the PBX, fetches all phone numbers/DIDs, and upserts
    into the inventory. Requires admin or operator role.
    """
    # Verify PBX exists
    result = await db.execute(select(PbxInstance).where(PbxInstance.id == pbx_id))
    pbx = result.scalar_one_or_none()
    if not pbx:
        raise HTTPException(404, f"PBX instance {pbx_id} not found")

    sync_result = await phone_number_service.sync_phone_numbers(db, pbx_id)

    if not sync_result.get("success"):
        raise HTTPException(502, detail=sync_result.get("error", "Sync failed"))

    return sync_result


@router.post("/sync-all")
async def sync_all_phone_numbers(
    user: CurrentUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Trigger phone number sync for ALL enabled PBX instances.

    Iterates through all enabled PBXes and syncs phone numbers from each.
    Requires admin role. Returns per-PBX results.
    """
    result = await db.execute(
        select(PbxInstance).where(PbxInstance.is_enabled == True).order_by(PbxInstance.name)
    )
    instances = result.scalars().all()

    if not instances:
        return {"message": "No enabled PBX instances found", "results": []}

    results = []
    for pbx in instances:
        logger.info(f"Syncing phone numbers for {pbx.name}")
        sync_result = await phone_number_service.sync_phone_numbers(db, pbx.id)
        results.append({
            "pbx_id": str(pbx.id),
            "pbx_name": pbx.name,
            **sync_result,
        })

    total_synced = sum(r.get("synced", 0) for r in results)
    total_added = sum(r.get("added", 0) for r in results)
    successful = sum(1 for r in results if r.get("success"))

    return {
        "message": f"Synced {successful}/{len(instances)} PBX(es), {total_synced} numbers total, {total_added} new",
        "results": results,
    }


# ═══════════════════════════════════════════════════════════════════════════
# EXPORT
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/export")
async def export_phone_numbers(
    pbx_id: Optional[UUID] = Query(None, description="Filter by PBX instance"),
    trunk_name: Optional[str] = Query(None, description="Filter by trunk name"),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export phone numbers as a CSV file download.

    Supports optional filtering by PBX and trunk name.
    """
    csv_text = await phone_number_service.export_phone_numbers_csv(
        db, pbx_id=pbx_id, trunk_name=trunk_name
    )
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=phone_numbers.csv"},
    )


# ═══════════════════════════════════════════════════════════════════════════
# REPORT
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/report")
async def phone_number_report(
    pbx_id: Optional[UUID] = Query(None, description="Filter by PBX instance"),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a comprehensive phone number inventory report.

    Includes per-PBX breakdown, type distribution percentages,
    stale number detection, and trunk-level detail.
    """
    return await phone_number_service.generate_phone_report(db, pbx_id=pbx_id)
