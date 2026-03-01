"""PBX Instance management endpoints."""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, HttpUrl

from src.adapters.threecx_v20 import create_adapter, CapabilityLevel
from src.common.crypto.encryption import encrypt_secret, decrypt_secret

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Request/Response Models ───────────────────────

class PBXCreateRequest(BaseModel):
    name: str
    base_url: str  # e.g., https://pbx.example.com
    username: str
    password: str
    tls_policy: str = "strict"  # "strict" | "trust_self_signed"
    poll_interval_s: int = 60
    notes: Optional[str] = None


class PBXUpdateRequest(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None  # Only set if changing
    tls_policy: Optional[str] = None
    poll_interval_s: Optional[int] = None
    notes: Optional[str] = None


class PBXResponse(BaseModel):
    id: str
    name: str
    base_url: str
    tls_policy: str
    version: Optional[str]
    is_enabled: bool
    poll_interval_s: int
    last_seen: Optional[str]
    last_error: Optional[str]
    notes: Optional[str]


class TestConnectionRequest(BaseModel):
    base_url: str
    username: str
    password: str
    tls_policy: str = "strict"


class TestConnectionResponse(BaseModel):
    success: bool
    version: Optional[str] = None
    capabilities: list[dict] = []
    error: Optional[str] = None


class PBXStatusResponse(BaseModel):
    pbx_id: str
    name: str
    overall_status: str  # "healthy", "warning", "error", "unknown"
    trunks: list[dict] = []
    sbcs: list[dict] = []
    license: Optional[dict] = None
    last_polled: Optional[str] = None


# ── Endpoints ─────────────────────────────────────

@router.post("/test-connection", response_model=TestConnectionResponse)
async def test_connection(req: TestConnectionRequest):
    """Test connectivity to a 3CX instance without saving it.

    This is the "connectivity probe" — validates URL, TLS, login,
    and discovers available features.
    """
    verify_tls = req.tls_policy != "trust_self_signed"
    adapter = create_adapter(base_url=req.base_url, verify_tls=verify_tls)

    try:
        # Step 1: Attempt login
        login_ok = await adapter.login(username=req.username, password=req.password)
        if not login_ok:
            return TestConnectionResponse(
                success=False,
                error="Authentication failed. Check credentials and URL.",
            )

        # Step 2: Probe capabilities
        probe = await adapter.probe_capabilities()

        return TestConnectionResponse(
            success=True,
            version=probe.version,
            capabilities=[
                {
                    "feature": cap.feature,
                    "status": cap.status.value,
                    "method": cap.method,
                    "endpoint": cap.endpoint,
                    "notes": cap.notes,
                }
                for cap in probe.capabilities
            ],
        )

    except Exception as e:
        logger.exception(f"Test connection failed: {e}")
        return TestConnectionResponse(
            success=False,
            error=f"Connection failed: {str(e)}",
        )
    finally:
        await adapter.close()


@router.post("", response_model=PBXResponse, status_code=status.HTTP_201_CREATED)
async def add_pbx_instance(req: PBXCreateRequest):
    """Add a new PBX instance to monitor.

    Encrypts credentials before storage. Optionally runs test connection.
    """
    # Encrypt the password
    ciphertext, iv, tag = encrypt_secret(req.password)

    # TODO: Save to database (pbx_instance + secret_ref tables)
    # For now, return a stub response
    # In production, this would use SQLAlchemy async session

    return PBXResponse(
        id="placeholder-uuid",
        name=req.name,
        base_url=req.base_url,
        tls_policy=req.tls_policy,
        version=None,
        is_enabled=True,
        poll_interval_s=req.poll_interval_s,
        last_seen=None,
        last_error=None,
        notes=req.notes,
    )


@router.get("", response_model=list[PBXResponse])
async def list_pbx_instances():
    """List all configured PBX instances."""
    # TODO: Query database
    return []


@router.get("/{pbx_id}", response_model=PBXResponse)
async def get_pbx_instance(pbx_id: UUID):
    """Get details for a specific PBX instance."""
    # TODO: Query database
    raise HTTPException(status_code=404, detail="PBX instance not found")


@router.get("/{pbx_id}/status", response_model=PBXStatusResponse)
async def get_pbx_status(pbx_id: UUID):
    """Get current monitoring status for a PBX instance.

    Returns latest trunk, SBC, license, and backup info from cached poll results.
    """
    # TODO: Query latest poll_result + trunk_state + sbc_state + license_state
    raise HTTPException(status_code=404, detail="PBX instance not found")


@router.delete("/{pbx_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_pbx_instance(pbx_id: UUID):
    """Remove a PBX instance and its credentials.

    Does NOT delete backup files — those must be cleaned separately.
    """
    # TODO: Delete from database (cascade deletes secret_ref, capabilities, etc.)
    pass
