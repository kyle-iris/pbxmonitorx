"""Pydantic schemas for API request/response validation and serialization."""

from __future__ import annotations
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator
import re


# ── PBX Instance ─────────────────────────────────────────────────────────────

class PbxCreateRequest(BaseModel):
    """Request to add a new PBX instance."""
    name: str = Field(..., min_length=2, max_length=200)
    base_url: str = Field(..., max_length=500)
    username: str = Field(..., min_length=1, max_length=200)
    password: str = Field(..., min_length=1, max_length=500)
    tls_policy: str = Field(default="verify", pattern=r"^(verify|trust_self_signed)$")
    poll_interval_s: int = Field(default=60, ge=30, le=3600)
    notes: Optional[str] = None

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not v.startswith("https://"):
            raise ValueError("URL must start with https://")
        # Basic URL format validation
        pattern = r'^https://[a-zA-Z0-9]([a-zA-Z0-9\-\.]*[a-zA-Z0-9])?(:\d{1,5})?(/.*)?$'
        if not re.match(pattern, v):
            raise ValueError("Invalid URL format")
        return v

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        return v.strip()


class PbxUpdateRequest(BaseModel):
    """Request to update a PBX instance. All fields optional."""
    name: Optional[str] = Field(None, min_length=2, max_length=200)
    base_url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None   # Only sent if changing
    tls_policy: Optional[str] = Field(None, pattern=r"^(verify|trust_self_signed)$")
    poll_interval_s: Optional[int] = Field(None, ge=30, le=3600)
    is_enabled: Optional[bool] = None
    notes: Optional[str] = None


class PbxResponse(BaseModel):
    """PBX instance summary — never includes credentials."""
    id: UUID
    name: str
    base_url: str
    tls_policy: str
    detected_version: Optional[str]
    is_enabled: bool
    poll_interval_s: int
    last_poll_at: Optional[datetime]
    last_success_at: Optional[datetime]
    last_error: Optional[str]
    consecutive_failures: int
    notes: Optional[str]
    created_at: datetime
    credential_username: Optional[str] = None  # PBX login username (not password!)

    model_config = {"from_attributes": True}


class CapabilityResponse(BaseModel):
    feature: str
    status: str
    method: Optional[str]
    endpoint_path: Optional[str]
    notes: Optional[str]
    last_probed_at: Optional[datetime]


# ── Test Connection ──────────────────────────────────────────────────────────

class TestConnectionRequest(BaseModel):
    """Test connectivity without saving anything."""
    base_url: str
    username: str
    password: str
    tls_policy: str = "verify"

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not v.startswith("https://"):
            raise ValueError("URL must start with https://")
        return v


class TestConnectionResponse(BaseModel):
    success: bool
    version: Optional[str] = None
    message: str = ""
    capabilities: list[CapabilityResponse] = []
    steps: list[TestStep] = []


class TestStep(BaseModel):
    """Individual step result from the connection test."""
    step: str
    status: str   # "pass", "fail", "warn", "skip"
    message: str
    duration_ms: Optional[int] = None


# Re-declare TestConnectionResponse after TestStep is defined
class TestConnectionResponse(BaseModel):
    success: bool
    version: Optional[str] = None
    message: str = ""
    capabilities: list[CapabilityResponse] = []
    steps: list[TestStep] = []


# ── Status ───────────────────────────────────────────────────────────────────

class TrunkStateResponse(BaseModel):
    trunk_name: str
    status: str
    last_error: Optional[str]
    last_status_change: Optional[datetime]
    inbound_enabled: Optional[bool]
    outbound_enabled: Optional[bool]
    provider: Optional[str]
    model_config = {"from_attributes": True}


class SbcStateResponse(BaseModel):
    sbc_name: str
    status: str
    last_seen: Optional[datetime]
    tunnel_status: Optional[str]
    model_config = {"from_attributes": True}


class LicenseStateResponse(BaseModel):
    edition: Optional[str]
    license_key_masked: Optional[str]
    expiry_date: Optional[str]
    maintenance_expiry: Optional[str]
    max_sim_calls: Optional[int]
    is_valid: Optional[bool]
    warnings: list[str] = []
    model_config = {"from_attributes": True}


class PbxStatusResponse(BaseModel):
    """Full status for a PBX — trunks, SBCs, license, backups."""
    pbx: PbxResponse
    trunks: list[TrunkStateResponse] = []
    sbcs: list[SbcStateResponse] = []
    license: Optional[LicenseStateResponse] = None
    capabilities: list[CapabilityResponse] = []
    overall_health: str = "unknown"  # healthy, warning, error


# ── Audit ────────────────────────────────────────────────────────────────────

class AuditLogResponse(BaseModel):
    id: UUID
    username: Optional[str]
    action: str
    target_type: Optional[str]
    target_name: Optional[str]
    detail: dict = {}
    success: bool
    error_message: Optional[str]
    created_at: datetime
    model_config = {"from_attributes": True}
