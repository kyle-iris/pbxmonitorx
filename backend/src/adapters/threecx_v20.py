"""ThreeCXv20Adapter — Production adapter for 3CX v20 Linux PBX systems.

This module encapsulates ALL communication with a 3CX v20 instance.
Nothing outside this adapter knows how data is fetched from 3CX.

Security:
    - All connections over HTTPS (TLS verification configurable per-PBX)
    - Session cookies held in-memory only, never persisted
    - Passwords passed in, never stored in adapter state
    - Connection timeout enforced on all requests
    - Rate limiting via caller (adapter doesn't auto-poll)

Fragility:
    - 3CX v20 has NO official public API — we replicate management console calls
    - Endpoints discovered via probing; may change between minor versions
    - All parsing is behind try/except with degraded fallbacks
    - HTML scraping is last resort, clearly labeled "fragile"

Usage:
    adapter = ThreeCXv20Adapter("https://pbx.example.com", verify_tls=True)
    ok = await adapter.login("admin", "password")
    probe = await adapter.probe_capabilities()
    trunks = await adapter.get_trunks()
    await adapter.close()
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import ssl
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger("pbxmonitorx.adapter.3cx_v20")


# ═════════════════════════════════════════════════════════════════════════════
# DATA TYPES
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class StepResult:
    step: str
    status: str          # pass, fail, warn, skip
    message: str
    duration_ms: int = 0


@dataclass
class CapabilityInfo:
    feature: str
    status: str          # available, degraded, unavailable, untested
    method: Optional[str] = None      # api_json, web_call, html_scrape
    endpoint: Optional[str] = None
    response_shape: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class ProbeResult:
    success: bool
    version: Optional[str] = None
    build: Optional[str] = None
    capabilities: list[CapabilityInfo] = field(default_factory=list)
    steps: list[StepResult] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class TrunkData:
    name: str
    status: str          # registered, unregistered, error, unknown
    remote_id: Optional[str] = None
    last_error: Optional[str] = None
    last_change: Optional[str] = None
    inbound_ok: Optional[bool] = None
    outbound_ok: Optional[bool] = None
    provider: Optional[str] = None
    raw: dict = field(default_factory=dict)


@dataclass
class SbcData:
    name: str
    status: str          # online, offline, unknown
    remote_id: Optional[str] = None
    last_seen: Optional[str] = None
    tunnel_status: Optional[str] = None
    raw: dict = field(default_factory=dict)


@dataclass
class LicenseData:
    edition: Optional[str] = None
    key_masked: Optional[str] = None
    expiry: Optional[str] = None
    maintenance_expiry: Optional[str] = None
    max_calls: Optional[int] = None
    is_valid: Optional[bool] = None
    warnings: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


@dataclass
class BackupEntry:
    backup_id: str
    filename: str
    created_at: Optional[str] = None
    size_bytes: Optional[int] = None
    backup_type: Optional[str] = None
    raw: dict = field(default_factory=dict)


# ═════════════════════════════════════════════════════════════════════════════
# ENDPOINT DISCOVERY TABLE
# ═════════════════════════════════════════════════════════════════════════════
# Each feature has multiple candidate endpoints, tried in priority order.
# Format: (HTTP_method, path, label)
# The adapter tries each and remembers which one worked.

LOGIN_ENDPOINTS = [
    # 3CX v20 webclient API — most common
    ("POST", "/webclient/api/Login/GetAccessToken", "webclient_token"),
    # 3CX v20 management console API
    ("POST", "/api/login", "api_login"),
    # Older/alternate
    ("POST", "/api/Login/GetAccessToken", "alt_token"),
]

FEATURE_ENDPOINTS = {
    "trunks": [
        ("GET", "/xapi/v1/Trunks",                          "xapi_trunks"),
        ("GET", "/api/TrunkList",                            "api_trunk_list"),
        ("GET", "/webclient/api/Trunk/Get",                  "webclient_trunks"),
        ("GET", "/api/SystemStatus",                         "system_status"),
    ],
    "sbcs": [
        ("GET", "/xapi/v1/Sbcs",                             "xapi_sbcs"),
        ("GET", "/api/SbcList",                              "api_sbc_list"),
        ("GET", "/webclient/api/Sbc/Get",                    "webclient_sbcs"),
    ],
    "license": [
        ("GET", "/xapi/v1/License",                          "xapi_license"),
        ("GET", "/api/LicenseInfo",                          "api_license"),
        ("GET", "/webclient/api/License/Get",                "webclient_license"),
        ("GET", "/api/SystemStatus",                         "system_status_lic"),
    ],
    "backup_list": [
        ("GET", "/xapi/v1/Backups",                          "xapi_backups"),
        ("GET", "/api/BackupList",                           "api_backup_list"),
        ("GET", "/webclient/api/BackupAndRestore/Get",       "webclient_backups"),
    ],
    "backup_download": [
        ("GET", "/api/BackupAndRestore/download/{id}",       "api_download"),
        ("GET", "/xapi/v1/Backups({id})/$value",             "xapi_download"),
        ("GET", "/webclient/api/BackupAndRestore/Download",  "webclient_download"),
    ],
    "version": [
        ("GET", "/xapi/v1/SystemStatus",                     "xapi_status"),
        ("GET", "/api/SystemStatus",                         "api_status"),
    ],
}


# ═════════════════════════════════════════════════════════════════════════════
# ADAPTER
# ═════════════════════════════════════════════════════════════════════════════

class ThreeCXv20Adapter:
    """Manages authenticated session with a single 3CX v20 PBX instance.

    Thread safety: NOT thread-safe. Use one adapter per asyncio task.
    Session lifecycle: login() → use → close()
    """

    def __init__(self, base_url: str, verify_tls: bool = True):
        self.base_url = base_url.rstrip("/")
        self.verify_tls = verify_tls
        self._client: Optional[httpx.AsyncClient] = None
        self._authenticated = False
        self._token: Optional[str] = None
        self._endpoints: dict[str, tuple[str, str, str]] = {}   # feature → (method, path, label)
        self._version: Optional[str] = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                verify=self.verify_tls,
                timeout=httpx.Timeout(30.0, connect=10.0),
                follow_redirects=True,
                limits=httpx.Limits(max_connections=5, max_keepalive_connections=2),
                headers={
                    "User-Agent": "PBXMonitorX/1.0",
                    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
                },
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        self._client = None
        self._authenticated = False
        self._token = None

    # ── 1. LOGIN ────────────────────────────────────────────────────────────

    async def login(self, username: str, password: str) -> tuple[bool, list[StepResult]]:
        """Authenticate to the 3CX management interface.

        Tries multiple known login endpoints.
        Returns (success, steps) where steps detail each attempt.
        """
        client = await self._ensure_client()
        self._authenticated = False
        self._token = None
        steps: list[StepResult] = []

        # Step 1: Verify HTTPS connectivity
        t0 = time.monotonic()
        try:
            resp = await client.get("/")
            ms = int((time.monotonic() - t0) * 1000)
            if resp.status_code < 500:
                steps.append(StepResult("tls_connect", "pass",
                    f"HTTPS connection successful ({ms}ms, status {resp.status_code})", ms))
            else:
                steps.append(StepResult("tls_connect", "warn",
                    f"Server returned {resp.status_code}", ms))
        except httpx.ConnectError as e:
            ms = int((time.monotonic() - t0) * 1000)
            steps.append(StepResult("tls_connect", "fail",
                f"Connection failed: {e}", ms))
            return False, steps
        except ssl.SSLCertVerificationError as e:
            ms = int((time.monotonic() - t0) * 1000)
            steps.append(StepResult("tls_connect", "fail",
                f"TLS certificate verification failed: {e}. "
                "Enable 'Trust self-signed' if this PBX uses a self-signed cert.", ms))
            return False, steps
        except Exception as e:
            ms = int((time.monotonic() - t0) * 1000)
            steps.append(StepResult("tls_connect", "fail", f"Unexpected error: {e}", ms))
            return False, steps

        # Step 2: Try login endpoints
        for method, path, label in LOGIN_ENDPOINTS:
            t0 = time.monotonic()
            try:
                # 3CX v20 accepts JSON with Username/Password
                payload = {"Username": username, "Password": password}
                resp = await client.request(method, path, json=payload)
                ms = int((time.monotonic() - t0) * 1000)

                if resp.status_code == 200:
                    # Parse token from response
                    data = self._try_json(resp)
                    token = None
                    if data:
                        # 3CX may return: {"Token": {...}}, {"Status": "Authenticated", "Token": "..."}
                        token = self._extract_token(data)

                    if token:
                        self._token = token
                        client.headers["Authorization"] = f"Bearer {token}"
                        self._authenticated = True
                        self._endpoints["login"] = (method, path, label)
                        steps.append(StepResult("authenticate", "pass",
                            f"Login successful via {label} ({ms}ms)", ms))
                        return True, steps
                    elif resp.cookies:
                        # Session cookie auth (no explicit token)
                        self._authenticated = True
                        self._endpoints["login"] = (method, path, label)
                        steps.append(StepResult("authenticate", "pass",
                            f"Login successful via session cookie at {label} ({ms}ms)", ms))
                        return True, steps
                    else:
                        steps.append(StepResult("authenticate", "warn",
                            f"{label}: got 200 but no token/cookie — trying next", ms))

                elif resp.status_code in (401, 403):
                    steps.append(StepResult("authenticate", "fail",
                        f"{label}: invalid credentials (HTTP {resp.status_code})", ms))
                    # Don't try other endpoints — creds are wrong
                    return False, steps

                elif resp.status_code == 404:
                    steps.append(StepResult("authenticate", "skip",
                        f"{label}: endpoint not found (404), trying next", ms))
                else:
                    steps.append(StepResult("authenticate", "warn",
                        f"{label}: unexpected status {resp.status_code}", ms))

            except Exception as e:
                ms = int((time.monotonic() - t0) * 1000)
                steps.append(StepResult("authenticate", "warn",
                    f"{label}: error — {e}", ms))

        steps.append(StepResult("authenticate", "fail",
            "All login endpoints exhausted — could not authenticate", 0))
        return False, steps

    # ── 2. PROBE CAPABILITIES ───────────────────────────────────────────────

    async def probe_capabilities(self) -> ProbeResult:
        """Discover which data endpoints are available on this PBX.

        Must be called after successful login().
        Tests each feature category and records the working endpoint.
        """
        if not self._authenticated:
            return ProbeResult(success=False, error="Not authenticated")

        client = await self._ensure_client()
        capabilities: list[CapabilityInfo] = []
        steps: list[StepResult] = []

        # Version detection
        for method, path, label in FEATURE_ENDPOINTS["version"]:
            t0 = time.monotonic()
            try:
                resp = await client.request(method, path)
                ms = int((time.monotonic() - t0) * 1000)
                if resp.status_code == 200:
                    data = self._try_json(resp)
                    if data:
                        self._version = (
                            data.get("Version") or data.get("version") or
                            data.get("FQDN") or None
                        )
                        if self._version:
                            steps.append(StepResult("version_detect", "pass",
                                f"Detected version: {self._version}", ms))
                            break
            except Exception:
                pass

        if not self._version:
            steps.append(StepResult("version_detect", "warn",
                "Could not detect PBX version", 0))

        # Probe each feature
        for feature in ["trunks", "sbcs", "license", "backup_list"]:
            cap = await self._probe_single(feature, client)
            capabilities.append(cap)
            status_sym = {"available": "✓", "degraded": "~", "unavailable": "✗"}.get(cap.status, "?")
            steps.append(StepResult(f"probe_{feature}", 
                "pass" if cap.status == "available" else "warn" if cap.status == "degraded" else "fail",
                f"{feature}: {status_sym} {cap.status}" + (f" via {cap.method}" if cap.method else ""),
                0))

        return ProbeResult(
            success=True,
            version=self._version,
            capabilities=capabilities,
            steps=steps,
        )

    async def _probe_single(self, feature: str, client: httpx.AsyncClient) -> CapabilityInfo:
        candidates = FEATURE_ENDPOINTS.get(feature, [])
        for method, path, label in candidates:
            try:
                resp = await client.request(method, path)
                if resp.status_code == 200:
                    ct = resp.headers.get("content-type", "")
                    if "json" in ct:
                        data = self._try_json(resp)
                        if data and self._has_content(data):
                            self._endpoints[feature] = (method, path, label)
                            shape = "list" if isinstance(data, list) else "object"
                            return CapabilityInfo(feature, "available", "api_json", path, shape)
                    elif "html" in ct:
                        # HTML fallback — FRAGILE
                        self._endpoints[feature] = (method, path, label)
                        return CapabilityInfo(feature, "degraded", "html_scrape", path,
                            notes="⚠ HTML scraping — may break on PBX update")
            except Exception:
                continue

        return CapabilityInfo(feature, "unavailable",
            notes="No working endpoint found for this feature")

    # ── 3. DATA RETRIEVAL ───────────────────────────────────────────────────

    async def get_trunks(self) -> list[TrunkData]:
        data = await self._fetch("trunks")
        if data is None:
            return []
        items = self._unwrap_list(data, ["list", "Trunks", "value", "List"])
        return [self._parse_trunk(item) for item in items]

    async def get_sbcs(self) -> list[SbcData]:
        data = await self._fetch("sbcs")
        if data is None:
            return []
        items = self._unwrap_list(data, ["list", "SBCs", "value", "List"])
        return [self._parse_sbc(item) for item in items]

    async def get_license(self) -> Optional[LicenseData]:
        data = await self._fetch("license")
        if data is None:
            return None
        if isinstance(data, list) and data:
            data = data[0]
        return self._parse_license(data)

    async def list_backups(self) -> list[BackupEntry]:
        data = await self._fetch("backup_list")
        if data is None:
            return []
        items = self._unwrap_list(data, ["list", "Backups", "value", "List"])
        return [self._parse_backup(item) for item in items]

    async def download_backup(self, backup_id: str, dest_path: str) -> tuple[bool, str]:
        """Download a backup file via streaming.

        Returns (success, sha256_hash_or_error_message).
        """
        if not self._authenticated:
            return False, "Not authenticated"

        client = await self._ensure_client()
        candidates = FEATURE_ENDPOINTS.get("backup_download", [])

        for method, path_tpl, label in candidates:
            path = path_tpl.replace("{id}", backup_id)
            try:
                hasher = hashlib.sha256()
                total_bytes = 0
                async with client.stream(method, path) as resp:
                    if resp.status_code != 200:
                        continue
                    with open(dest_path, "wb") as f:
                        async for chunk in resp.aiter_bytes(chunk_size=65536):
                            f.write(chunk)
                            hasher.update(chunk)
                            total_bytes += len(chunk)

                if total_bytes > 0:
                    return True, hasher.hexdigest()

            except Exception as e:
                logger.warning(f"Download via {label} failed: {e}")
                continue

        return False, "All download endpoints failed"

    async def trigger_backup(self) -> tuple[bool, str]:
        """Push a backup trigger to the 3CX PBX.

        Tries known endpoints that initiate a new backup on the PBX.
        Returns (success, message).
        """
        if not self._authenticated:
            return False, "Not authenticated"

        client = await self._ensure_client()

        trigger_endpoints = [
            ("POST", "/xapi/v1/Backups/Pbx.StartBackup()", "xapi_trigger"),
            ("POST", "/api/BackupAndRestore/start", "api_trigger"),
            ("POST", "/webclient/api/BackupAndRestore/Post", "webclient_trigger"),
            ("POST", "/api/backup/start", "api_start"),
        ]

        for method, path, label in trigger_endpoints:
            try:
                resp = await client.request(method, path, json={})
                if resp.status_code in (200, 201, 202, 204):
                    logger.info(f"Backup triggered via {label}")
                    return True, f"Backup triggered via {label}"
                elif resp.status_code == 404:
                    continue
                else:
                    logger.debug(f"Trigger via {label}: HTTP {resp.status_code}")
            except Exception as e:
                logger.debug(f"Trigger via {label} failed: {e}")
                continue

        return False, "No backup trigger endpoint found — PBX may not support remote trigger"

    # ── INTERNAL HELPERS ────────────────────────────────────────────────────

    async def _fetch(self, feature: str) -> Optional[Any]:
        if not self._authenticated:
            return None
        client = await self._ensure_client()

        # Try discovered endpoint first
        if feature in self._endpoints:
            method, path, _ = self._endpoints[feature]
            try:
                resp = await client.request(method, path)
                if resp.status_code == 200:
                    ct = resp.headers.get("content-type", "")
                    if "json" in ct:
                        return self._try_json(resp)
                    elif "html" in ct:
                        return self._scrape_html(resp.text, feature)
                elif resp.status_code in (401, 403):
                    self._authenticated = False
                    logger.warning(f"Session expired fetching {feature}")
                    return None
            except Exception as e:
                logger.warning(f"Fetch {feature} via cached endpoint: {e}")

        # Re-probe
        for method, path, label in FEATURE_ENDPOINTS.get(feature, []):
            try:
                resp = await client.request(method, path)
                if resp.status_code == 200:
                    ct = resp.headers.get("content-type", "")
                    if "json" in ct:
                        data = self._try_json(resp)
                        if data and self._has_content(data):
                            self._endpoints[feature] = (method, path, label)
                            return data
            except Exception:
                continue

        return None

    @staticmethod
    def _try_json(resp: httpx.Response) -> Optional[Any]:
        try:
            return resp.json()
        except Exception:
            return None

    @staticmethod
    def _has_content(data) -> bool:
        if data is None:
            return False
        if isinstance(data, list):
            return len(data) > 0
        if isinstance(data, dict):
            return len(data) > 0
        return True

    @staticmethod
    def _unwrap_list(data: Any, keys: list[str]) -> list:
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in keys:
                if key in data and isinstance(data[key], list):
                    return data[key]
        return []

    @staticmethod
    def _extract_token(data: dict) -> Optional[str]:
        """Extract bearer token from various 3CX response formats."""
        if isinstance(data, str):
            return data if len(data) > 20 else None

        for key in ("Token", "token", "access_token", "AccessToken"):
            val = data.get(key)
            if val:
                if isinstance(val, str) and len(val) > 10:
                    return val
                if isinstance(val, dict):
                    return val.get("token") or val.get("value")
        return None

    def _parse_trunk(self, item: dict) -> TrunkData:
        name = item.get("Name") or item.get("name") or item.get("TrunkName") or "Unknown"
        raw_status = str(item.get("Status") or item.get("status") or item.get("State") or "").lower()

        if "register" in raw_status and "un" not in raw_status:
            status = "registered"
        elif "unregister" in raw_status or "failed" in raw_status:
            status = "unregistered"
        elif "error" in raw_status:
            status = "error"
        else:
            status = "unknown"

        return TrunkData(
            name=name, status=status,
            remote_id=str(item.get("Id") or item.get("id") or ""),
            last_error=item.get("LastError") or item.get("lastError"),
            provider=item.get("Provider") or item.get("provider") or item.get("ProviderName"),
            inbound_ok=self._to_bool(item, "InboundEnabled", "inboundEnabled", "IsInbound"),
            outbound_ok=self._to_bool(item, "OutboundEnabled", "outboundEnabled", "IsOutbound"),
            raw=item,
        )

    def _parse_sbc(self, item: dict) -> SbcData:
        name = item.get("Name") or item.get("name") or item.get("FQDN") or "Unknown"
        is_online = (
            item.get("IsOnline") or item.get("isOnline") or
            str(item.get("Status") or "").lower() == "online"
        )
        return SbcData(
            name=name,
            status="online" if is_online else "offline",
            remote_id=str(item.get("Id") or item.get("id") or ""),
            tunnel_status=item.get("TunnelStatus") or item.get("tunnelStatus"),
            raw=item,
        )

    def _parse_license(self, item: dict) -> LicenseData:
        key = item.get("LicenseKey") or item.get("licenseKey") or ""
        masked = f"{key[:4]}…{key[-4:]}" if len(key) > 8 else "••••"

        warnings = []
        expiry = item.get("ExpiryDate") or item.get("expiryDate") or item.get("Expiry")
        is_valid = item.get("IsValid") or item.get("isValid")
        if is_valid is False:
            warnings.append("License is INVALID or EXPIRED")

        return LicenseData(
            edition=item.get("Edition") or item.get("edition") or item.get("ProductName"),
            key_masked=masked,
            expiry=str(expiry) if expiry else None,
            maintenance_expiry=str(item.get("MaintenanceExpiry") or item.get("maintenanceExpiry") or ""),
            max_calls=item.get("MaxSimCalls") or item.get("maxSimCalls") or item.get("MaxSimultaneousCalls"),
            is_valid=is_valid,
            warnings=warnings,
            raw=item,
        )

    def _parse_backup(self, item: dict) -> BackupEntry:
        return BackupEntry(
            backup_id=str(item.get("Id") or item.get("id") or item.get("FileName", "")),
            filename=item.get("FileName") or item.get("fileName") or item.get("Name") or "unknown",
            size_bytes=item.get("Size") or item.get("size") or item.get("FileSize"),
            backup_type=item.get("Type") or item.get("type"),
            raw=item,
        )

    @staticmethod
    def _to_bool(d: dict, *keys) -> Optional[bool]:
        for k in keys:
            if k in d:
                v = d[k]
                if isinstance(v, bool):
                    return v
                if isinstance(v, str):
                    return v.lower() in ("true", "1", "yes")
        return None

    def _scrape_html(self, html: str, feature: str) -> Optional[list[dict]]:
        """FRAGILE FALLBACK: Extract data from HTML admin pages.

        This is a last-resort parser. It WILL break when 3CX updates its UI.
        Each use is logged as a warning.
        """
        logger.warning(f"Using HTML scraping fallback for {feature} — this is fragile")
        try:
            soup = BeautifulSoup(html, "html.parser")
            tables = soup.find_all("table")
            if not tables:
                return None
            results = []
            for table in tables:
                headers = [th.get_text(strip=True) for th in table.find_all("th")]
                for row in table.find_all("tr")[1:]:
                    cells = [td.get_text(strip=True) for td in row.find_all("td")]
                    if cells and headers:
                        results.append(dict(zip(headers, cells)))
            return results or None
        except Exception as e:
            logger.error(f"HTML scraping failed for {feature}: {e}")
            return None
