"""ThreeCXv20Adapter — Pluggable adapter for 3CX v20 Linux management interface.

All 3CX-specific logic (authentication, data extraction, endpoint discovery)
is encapsulated here. The rest of the app only interacts through the
ThreeCXClient interface methods.

FRAGILITY NOTES:
- 3CX v20 does NOT have a stable public REST API.
- We replicate the network calls made by the management console.
- Endpoints may change between minor versions — the probe system detects this.
- All methods include fallback strategies and clear error reporting.
"""

from __future__ import annotations

import asyncio
import logging
import ssl
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Data Types
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class CapabilityLevel(str, Enum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


@dataclass
class CapabilityResult:
    feature: str
    status: CapabilityLevel
    method: Optional[str] = None  # "api", "web_call", "scraping"
    endpoint: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class TrunkInfo:
    name: str
    status: str  # "registered", "unregistered", "error"
    last_error: Optional[str] = None
    last_change: Optional[datetime] = None
    inbound_ok: Optional[bool] = None
    outbound_ok: Optional[bool] = None
    provider: Optional[str] = None
    raw: dict = field(default_factory=dict)


@dataclass
class SBCInfo:
    name: str
    status: str  # "online", "offline"
    last_seen: Optional[datetime] = None
    tunnel_status: Optional[str] = None
    connection_info: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)


@dataclass
class LicenseInfo:
    edition: Optional[str] = None
    license_key_masked: Optional[str] = None
    expiry_date: Optional[str] = None
    maintenance_expiry: Optional[str] = None
    max_simultaneous_calls: Optional[int] = None
    is_valid: Optional[bool] = None
    warnings: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


@dataclass
class BackupInfo:
    backup_id: str
    filename: str
    created_at: Optional[datetime] = None
    size_bytes: Optional[int] = None
    backup_type: Optional[str] = None
    raw: dict = field(default_factory=dict)


@dataclass
class ProbeResult:
    success: bool
    version: Optional[str] = None
    build: Optional[str] = None
    capabilities: list[CapabilityResult] = field(default_factory=list)
    error: Optional[str] = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Endpoint Candidates (tried in order)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# These are the known/suspected endpoints from 3CX v20 management console.
# They are tried in order; the first that returns valid data is used.

ENDPOINT_CANDIDATES = {
    "login": [
        ("POST", "/api/login", "api"),
        ("POST", "/webclient/api/Login/GetAccessToken", "web_call"),
    ],
    "trunks": [
        ("GET", "/api/TrunkList", "api"),
        ("GET", "/api/SystemStatus/Trunks", "api"),
        ("GET", "/webclient/api/Trunk/Get", "web_call"),
        ("GET", "/api/trunkstatus", "api"),
    ],
    "sbcs": [
        ("GET", "/api/SbcList", "api"),
        ("GET", "/api/SystemStatus/SBCs", "api"),
        ("GET", "/webclient/api/Sbc/Get", "web_call"),
    ],
    "license": [
        ("GET", "/api/LicenseInfo", "api"),
        ("GET", "/api/SystemStatus/License", "api"),
        ("GET", "/webclient/api/License/Get", "web_call"),
        ("GET", "/api/license", "api"),
    ],
    "backups": [
        ("GET", "/api/BackupList", "api"),
        ("GET", "/api/BackupAndRestore", "api"),
        ("GET", "/webclient/api/Backup/Get", "web_call"),
    ],
    "backup_download": [
        ("GET", "/api/BackupAndRestore/download/{id}", "api"),
        ("GET", "/api/backup/download/{id}", "api"),
    ],
    "version": [
        ("GET", "/api/SystemStatus", "api"),
        ("GET", "/api/version", "api"),
    ],
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ThreeCXv20Adapter
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ThreeCXv20Adapter:
    """Encapsulates all communication with a single 3CX v20 instance.

    Usage:
        adapter = ThreeCXv20Adapter(base_url="https://pbx.example.com", verify_tls=True)
        await adapter.login(username="admin", password="secret")
        probe = await adapter.probe_capabilities()
        trunks = await adapter.get_trunks()
    """

    def __init__(self, base_url: str, verify_tls: bool = True):
        self.base_url = base_url.rstrip("/")
        self.verify_tls = verify_tls
        self._session: Optional[httpx.AsyncClient] = None
        self._authenticated = False
        self._discovered_endpoints: dict[str, tuple[str, str, str]] = {}  # feature -> (method, path, type)
        self._version: Optional[str] = None
        self._lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client with proper TLS settings."""
        if self._session is None or self._session.is_closed:
            verify: bool | ssl.SSLContext = self.verify_tls
            if not self.verify_tls:
                # Create context that doesn't verify
                verify = False
                logger.warning(f"TLS verification DISABLED for {self.base_url}")

            self._session = httpx.AsyncClient(
                base_url=self.base_url,
                verify=verify,
                timeout=httpx.Timeout(30.0, connect=10.0),
                follow_redirects=True,
                headers={"User-Agent": "PBXMonitorX/0.1"},
            )
        return self._session

    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.is_closed:
            await self._session.aclose()
            self._session = None
        self._authenticated = False

    # ── Authentication ─────────────────────────────

    async def login(self, username: str, password: str) -> bool:
        """Authenticate to the 3CX management console.

        Tries known login endpoints in order.
        Returns True if login succeeded.
        """
        client = await self._get_client()
        self._authenticated = False

        for method, path, ep_type in ENDPOINT_CANDIDATES["login"]:
            try:
                payload = {"Username": username, "Password": password}
                resp = await client.request(method, path, json=payload)

                if resp.status_code == 200:
                    # Check if response contains token or session was established
                    data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}

                    # Some 3CX versions return a bearer token
                    if "Token" in data or "token" in data:
                        token = data.get("Token") or data.get("token")
                        client.headers["Authorization"] = f"Bearer {token}"

                    self._authenticated = True
                    self._discovered_endpoints["login"] = (method, path, ep_type)
                    logger.info(f"Authenticated to {self.base_url} via {path}")
                    return True

                elif resp.status_code in (401, 403):
                    logger.warning(f"Auth failed at {path}: {resp.status_code}")
                    continue
                else:
                    logger.debug(f"Unexpected response from {path}: {resp.status_code}")
                    continue

            except httpx.HTTPError as e:
                logger.debug(f"HTTP error trying {path}: {e}")
                continue
            except Exception as e:
                logger.debug(f"Error trying {path}: {e}")
                continue

        logger.error(f"All login endpoints failed for {self.base_url}")
        return False

    async def _ensure_authenticated(self):
        """Check we have a valid session; raise if not."""
        if not self._authenticated:
            raise RuntimeError("Not authenticated. Call login() first.")

    # ── Capability Probe ───────────────────────────

    async def probe_capabilities(self) -> ProbeResult:
        """Test which features/endpoints are available on this PBX.

        Should be called after login(). Tests each feature category
        and records the first working endpoint.
        """
        await self._ensure_authenticated()
        client = await self._get_client()
        capabilities: list[CapabilityResult] = []

        # Version detection
        for method, path, ep_type in ENDPOINT_CANDIDATES["version"]:
            try:
                resp = await client.request(method, path)
                if resp.status_code == 200:
                    data = resp.json()
                    self._version = data.get("Version") or data.get("version")
                    break
            except Exception:
                continue

        # Probe each feature
        for feature in ["trunks", "sbcs", "license", "backups"]:
            cap = await self._probe_feature(feature)
            capabilities.append(cap)

        return ProbeResult(
            success=True,
            version=self._version,
            capabilities=capabilities,
        )

    async def _probe_feature(self, feature: str) -> CapabilityResult:
        """Try each endpoint candidate for a feature, return first success."""
        client = await self._get_client()
        candidates = ENDPOINT_CANDIDATES.get(feature, [])

        for method, path, ep_type in candidates:
            try:
                resp = await client.request(method, path)
                if resp.status_code == 200:
                    # Verify it's actually useful data
                    content_type = resp.headers.get("content-type", "")
                    if "json" in content_type:
                        data = resp.json()
                        if data:  # non-empty response
                            self._discovered_endpoints[feature] = (method, path, ep_type)
                            return CapabilityResult(
                                feature=feature,
                                status=CapabilityLevel.AVAILABLE,
                                method=ep_type,
                                endpoint=path,
                            )
                    elif "html" in content_type:
                        # HTML fallback — mark as degraded
                        self._discovered_endpoints[feature] = (method, path, ep_type)
                        return CapabilityResult(
                            feature=feature,
                            status=CapabilityLevel.DEGRADED,
                            method="scraping",
                            endpoint=path,
                            notes="HTML response; using fallback scraping",
                        )
            except Exception as e:
                logger.debug(f"Probe {feature} via {path}: {e}")
                continue

        return CapabilityResult(
            feature=feature,
            status=CapabilityLevel.UNAVAILABLE,
            notes="No working endpoint found",
        )

    # ── Data Retrieval ─────────────────────────────

    async def get_trunks(self) -> list[TrunkInfo]:
        """Retrieve trunk status from the PBX.

        Uses discovered endpoint or tries candidates.
        Returns structured TrunkInfo list.
        """
        data = await self._fetch_feature("trunks")
        if data is None:
            return []

        # Parse response — adapt to actual 3CX v20 response shape
        # This is the primary "fragile" point: response format may vary
        trunks = []
        items = data if isinstance(data, list) else data.get("list", data.get("Trunks", data.get("value", [])))

        for item in (items if isinstance(items, list) else []):
            trunks.append(TrunkInfo(
                name=item.get("Name") or item.get("name") or item.get("TrunkName", "Unknown"),
                status=self._normalize_trunk_status(item),
                last_error=item.get("LastError") or item.get("lastError"),
                provider=item.get("Provider") or item.get("provider"),
                inbound_ok=item.get("InboundEnabled") or item.get("inboundEnabled"),
                outbound_ok=item.get("OutboundEnabled") or item.get("outboundEnabled"),
                raw=item,
            ))

        return trunks

    async def get_sbcs(self) -> list[SBCInfo]:
        """Retrieve SBC status from the PBX."""
        data = await self._fetch_feature("sbcs")
        if data is None:
            return []

        sbcs = []
        items = data if isinstance(data, list) else data.get("list", data.get("SBCs", data.get("value", [])))

        for item in (items if isinstance(items, list) else []):
            sbcs.append(SBCInfo(
                name=item.get("Name") or item.get("name") or item.get("FQDN", "Unknown"),
                status="online" if item.get("IsOnline") or item.get("isOnline") or item.get("Status") == "Online" else "offline",
                last_seen=None,  # Parse from item if available
                tunnel_status=item.get("TunnelStatus") or item.get("tunnelStatus"),
                raw=item,
            ))

        return sbcs

    async def get_license(self) -> Optional[LicenseInfo]:
        """Retrieve license information from the PBX."""
        data = await self._fetch_feature("license")
        if data is None:
            return None

        # Flatten if nested
        if isinstance(data, list) and len(data) > 0:
            data = data[0]

        warnings = []
        expiry = data.get("ExpiryDate") or data.get("expiryDate") or data.get("Expiry")
        # TODO: Parse date and check proximity for warnings

        return LicenseInfo(
            edition=data.get("Edition") or data.get("edition") or data.get("ProductName"),
            license_key_masked=self._mask_key(data.get("LicenseKey") or data.get("licenseKey") or ""),
            expiry_date=expiry,
            maintenance_expiry=data.get("MaintenanceExpiry") or data.get("maintenanceExpiry"),
            max_simultaneous_calls=data.get("MaxSimCalls") or data.get("maxSimCalls"),
            is_valid=data.get("IsValid") or data.get("isValid"),
            warnings=warnings,
            raw=data,
        )

    async def list_backups(self) -> list[BackupInfo]:
        """List available backups on the PBX."""
        data = await self._fetch_feature("backups")
        if data is None:
            return []

        backups = []
        items = data if isinstance(data, list) else data.get("list", data.get("Backups", data.get("value", [])))

        for item in (items if isinstance(items, list) else []):
            backups.append(BackupInfo(
                backup_id=str(item.get("Id") or item.get("id") or item.get("FileName", "")),
                filename=item.get("FileName") or item.get("fileName") or item.get("Name", "unknown"),
                size_bytes=item.get("Size") or item.get("size") or item.get("FileSize"),
                backup_type=item.get("Type") or item.get("type"),
                raw=item,
            ))

        return backups

    async def download_backup(self, backup_id: str, dest_path: str) -> bool:
        """Download a backup file from the PBX to local storage.

        Streams the file to avoid memory issues with large backups.
        Returns True if download succeeded.
        """
        await self._ensure_authenticated()
        client = await self._get_client()

        # Try known download endpoints
        candidates = ENDPOINT_CANDIDATES.get("backup_download", [])
        for method, path_template, ep_type in candidates:
            path = path_template.replace("{id}", backup_id)
            try:
                async with client.stream(method, path) as resp:
                    if resp.status_code == 200:
                        with open(dest_path, "wb") as f:
                            async for chunk in resp.aiter_bytes(chunk_size=65536):
                                f.write(chunk)
                        logger.info(f"Downloaded backup {backup_id} to {dest_path}")
                        return True
            except Exception as e:
                logger.warning(f"Download attempt via {path} failed: {e}")
                continue

        logger.error(f"Failed to download backup {backup_id}")
        return False

    # ── Internal Helpers ───────────────────────────

    async def _fetch_feature(self, feature: str) -> Optional[Any]:
        """Fetch data for a feature using the discovered or candidate endpoints."""
        await self._ensure_authenticated()
        client = await self._get_client()

        # If we already discovered a working endpoint, use it first
        if feature in self._discovered_endpoints:
            method, path, ep_type = self._discovered_endpoints[feature]
            try:
                resp = await client.request(method, path)
                if resp.status_code == 200:
                    content_type = resp.headers.get("content-type", "")
                    if "json" in content_type:
                        return resp.json()
                    elif "html" in content_type:
                        return self._parse_html_table(resp.text, feature)
            except Exception as e:
                logger.warning(f"Discovered endpoint {path} failed: {e}")
                # Fall through to re-probe

        # Try all candidates
        for method, path, ep_type in ENDPOINT_CANDIDATES.get(feature, []):
            try:
                resp = await client.request(method, path)
                if resp.status_code == 200:
                    content_type = resp.headers.get("content-type", "")
                    if "json" in content_type:
                        data = resp.json()
                        if data:
                            self._discovered_endpoints[feature] = (method, path, ep_type)
                            return data
                    elif "html" in content_type:
                        self._discovered_endpoints[feature] = (method, path, "scraping")
                        return self._parse_html_table(resp.text, feature)
            except Exception:
                continue

        logger.error(f"No working endpoint for feature: {feature}")
        return None

    def _parse_html_table(self, html: str, feature: str) -> Optional[list[dict]]:
        """FRAGILE FALLBACK: Parse HTML admin pages for data.

        This is the last resort when no JSON endpoint is available.
        Labeled as fragile — may break on 3CX UI updates.
        """
        try:
            soup = BeautifulSoup(html, "html.parser")
            # Look for data tables — this is highly version-dependent
            tables = soup.find_all("table")
            if not tables:
                return None

            # Generic table parser
            results = []
            for table in tables:
                headers = [th.get_text(strip=True) for th in table.find_all("th")]
                for row in table.find_all("tr")[1:]:
                    cells = [td.get_text(strip=True) for td in row.find_all("td")]
                    if cells and headers:
                        results.append(dict(zip(headers, cells)))

            return results if results else None
        except Exception as e:
            logger.error(f"HTML parsing failed for {feature}: {e}")
            return None

    @staticmethod
    def _normalize_trunk_status(item: dict) -> str:
        """Normalize trunk status from various 3CX response formats."""
        status = item.get("Status") or item.get("status") or item.get("State") or ""
        status_lower = str(status).lower()
        if "register" in status_lower and "un" not in status_lower:
            return "registered"
        elif "unregister" in status_lower or "failed" in status_lower:
            return "unregistered"
        elif "error" in status_lower:
            return "error"
        return "unknown"

    @staticmethod
    def _mask_key(key: str) -> str:
        """Mask a license key for safe display: show first 4 and last 4 chars."""
        if len(key) <= 8:
            return "****"
        return f"{key[:4]}...{key[-4:]}"
