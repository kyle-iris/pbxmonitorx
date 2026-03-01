"""3CX v20 Adapter — Factory and protocol definition."""

from __future__ import annotations
from typing import Optional, Protocol, runtime_checkable

from .adapter import (
    ThreeCXv20Adapter,
    TrunkInfo,
    SBCInfo,
    LicenseInfo,
    BackupInfo,
    ProbeResult,
    CapabilityResult,
    CapabilityLevel,
)


@runtime_checkable
class ThreeCXClient(Protocol):
    """Protocol defining the interface for any 3CX adapter.

    Future adapters (e.g., ThreeCXv18Adapter) must implement this interface.
    """

    async def login(self, username: str, password: str) -> bool: ...
    async def probe_capabilities(self) -> ProbeResult: ...
    async def get_trunks(self) -> list[TrunkInfo]: ...
    async def get_sbcs(self) -> list[SBCInfo]: ...
    async def get_license(self) -> Optional[LicenseInfo]: ...
    async def list_backups(self) -> list[BackupInfo]: ...
    async def download_backup(self, backup_id: str, dest_path: str) -> bool: ...
    async def close(self) -> None: ...


def create_adapter(base_url: str, verify_tls: bool = True, version: str = "v20") -> ThreeCXClient:
    """Factory: create the appropriate adapter based on PBX version.

    Currently only v20 is supported. Future versions can be added here.
    """
    if version.startswith("v20") or version.startswith("20"):
        return ThreeCXv20Adapter(base_url=base_url, verify_tls=verify_tls)
    else:
        # Default to v20 adapter
        return ThreeCXv20Adapter(base_url=base_url, verify_tls=verify_tls)


__all__ = [
    "ThreeCXv20Adapter",
    "ThreeCXClient",
    "create_adapter",
    "TrunkInfo",
    "SBCInfo",
    "LicenseInfo",
    "BackupInfo",
    "ProbeResult",
    "CapabilityResult",
    "CapabilityLevel",
]
