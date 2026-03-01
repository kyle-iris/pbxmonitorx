# PBXMonitorX — Architecture & Design Document

## 1. Overview

**PBXMonitorX** is a Linux-first, Docker-deployed web application for monitoring and managing multiple 3CX v20 PBX instances. It provides real-time status monitoring, backup management, alerting, and audit logging — inspired by PBXMonitor but built for modern self-hosted Linux environments.

---

## 2. Stack Selection: Option C — Python (FastAPI) + React Frontend

### Justification

| Factor | Why Python/FastAPI wins for this project |
|--------|------------------------------------------|
| **3CX Integration** | Python's `httpx`/`aiohttp` + `BeautifulSoup`/`selectolax` are superior for HTTP session replication and HTML fallback parsing. `Playwright` (Python) is battle-tested for headless browser automation if needed. |
| **Async I/O** | FastAPI is fully async — ideal for polling multiple PBX instances concurrently without blocking. |
| **Cryptography** | Python's `cryptography` library provides AES-GCM encryption natively, simpler than Node equivalents. |
| **Scheduling** | Celery + Redis (or APScheduler) provide production-grade task scheduling with retry, monitoring, and backoff. |
| **Ecosystem** | SQLAlchemy + Alembic for DB migrations; Pydantic for validation; all well-suited to this domain. |
| **Docker-friendly** | Single `python:3.12-slim` base image, straightforward Dockerfile. |

### Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Compose                           │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌────────┐  ┌──────────┐  │
│  │   Frontend    │  │   Backend    │  │  Redis │  │ Postgres │  │
│  │  React SPA    │  │  FastAPI     │  │        │  │          │  │
│  │  (nginx)      │◄─┤  + Workers   │◄─┤  Queue │  │  State   │  │
│  │  :3000        │  │  :8000       │  │  :6379 │  │  :5432   │  │
│  └──────────────┘  └──────┬───────┘  └────────┘  └──────────┘  │
│                           │                                     │
│              ┌────────────┼────────────┐                        │
│              │   3CX Adapter Layer     │                        │
│              │  (pluggable per version)│                        │
│              └────────────┬────────────┘                        │
│                           │ HTTPS                               │
└───────────────────────────┼─────────────────────────────────────┘
                            ▼
              ┌─────────────────────────┐
              │  3CX v20 PBX Instances  │
              │  (Linux hosts)          │
              └─────────────────────────┘
```

---

## 3. MVP Scope & Acceptance Criteria

### MVP Features

| Feature | Acceptance Criteria |
|---------|-------------------|
| **Add PBX Instance** | User can add a PBX by name + URL + credentials. Credentials encrypted at rest. "Test Connection" validates login and returns capability matrix. |
| **Dashboard** | Shows cards per PBX with green/yellow/red status. Trunk down count, SBC offline count, license warnings, last backup age. Auto-refreshes. |
| **Trunk Monitoring** | Table showing all trunks: name, status (registered/unregistered), last error, last status change. Polls every 60-120s. |
| **SBC Monitoring** | Table showing SBCs: name, status (online/offline), last seen timestamp, connection health. |
| **License Monitoring** | Panel showing edition, expiry date, maintenance status. Yellow warning if < 30 days to expiry. |
| **Backup List** | Lists available backups per PBX with timestamp, size, type. |
| **Backup Download** | "Download" button pulls backup file to app storage. Shows download progress. |
| **Scheduled Backups** | Cron-like schedule per PBX. Configurable retention (keep last N / last X days). |
| **Alerts** | Rule-based: trunk down > 60s, SBC offline > 60s, license < 30 days, no backup > 24h. |
| **Audit Log** | Logs all logins, backup downloads, schedule changes, failures. Filterable, exportable CSV. |
| **Security** | TLS verification, encrypted secrets, session management, rate limiting. |

### Non-Goals (MVP)
- Push configuration changes (Phase 2)
- Deep call analytics
- Mobile-optimized UI (desktop-first, tablet-acceptable)

---

## 4. Capability Matrix Plan

```
┌──────────────────┬─────────────────┬─────────────────┬──────────────────┐
│ Feature          │ Method: API     │ Method: Web Call │ Method: Scraping │
│                  │ (if available)  │ Replication      │ (fallback)       │
├──────────────────┼─────────────────┼─────────────────┼──────────────────┤
│ Login/Auth       │ POST /login     │ Session cookie   │ —                │
│ Trunks           │ —               │ JSON endpoint    │ Admin page parse │
│ SBCs             │ —               │ JSON endpoint    │ Admin page parse │
│ License          │ —               │ JSON endpoint    │ Admin page parse │
│ Backup List      │ —               │ JSON endpoint    │ Admin page parse │
│ Backup Download  │ —               │ File download    │ —                │
│ Trigger Backup   │ —               │ POST action      │ —                │
│ Version Detect   │ —               │ Login page meta  │ HTML parse       │
└──────────────────┴─────────────────┴─────────────────┴──────────────────┘
```

**Strategy**: On first connection, `probeCapabilities()` tests each endpoint and builds a per-PBX capability map stored in the database. Subsequent polls use the best available method.

**Fragile areas**:
- 3CX v20 management console endpoints change between minor versions
- Session token format/expiry may vary
- Backup file paths and naming conventions

**Mitigation**: All extraction logic lives inside `ThreeCXv20Adapter`. Every method has a `try → fallback → mark degraded` pattern.

---

## 5. Security Model

### Secrets Management
- Admin passwords encrypted with **AES-256-GCM**
- Encryption key provided via `MASTER_ENCRYPTION_KEY` env var (or Docker secret)
- Key never stored in database or config files
- Passwords decrypted in-memory only when needed for PBX login

### TLS Policy
- Default: verify certificates strictly
- Per-PBX toggle: "Trust self-signed" with explicit warning shown in UI
- Warning persisted in audit log when enabled

### Authentication (App Users)
- Local auth with bcrypt-hashed passwords
- JWT tokens (short-lived access + refresh)
- RBAC roles: `viewer`, `operator`, `admin`

### Rate Limiting
- PBX polling: configurable 60-120s default, exponential backoff on failure
- API endpoints: rate-limited per user
- Failed login lockout: 5 attempts → 15 min cooldown

### Audit Trail
- Every significant action logged with: timestamp, user, action, target PBX, result, IP address
- Immutable (append-only table, no deletes via API)
- CSV export for compliance

---

## 6. Worker / Scheduler Design

```
┌──────────────────────────────────────────────────┐
│              Celery Beat (Scheduler)              │
│                                                   │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────┐  │
│  │ Poll Trunks │  │ Poll SBCs   │  │ Poll     │  │
│  │ (per PBX)   │  │ (per PBX)   │  │ License  │  │
│  │ every 60s   │  │ every 60s   │  │ every 1h │  │
│  └─────────────┘  └─────────────┘  └──────────┘  │
│                                                   │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────┐  │
│  │ Backup Pull │  │ Alert Check │  │ Retention│  │
│  │ (per sched) │  │ every 30s   │  │ Cleanup  │  │
│  │             │  │             │  │ daily    │  │
│  └─────────────┘  └─────────────┘  └──────────┘  │
│                                                   │
│              All via Redis Queue                  │
└──────────────────────────────────────────────────┘
```

- **Celery Beat** triggers periodic tasks
- **Celery Workers** (configurable concurrency) execute tasks
- Each PBX gets independent polling tasks (failure in one doesn't block others)
- Backoff: on failure, delay doubles up to 10 min max, then alert

---

## 7. Milestones

| # | Milestone | Duration | Deliverable |
|---|-----------|----------|-------------|
| 1 | **Foundation** | Week 1-2 | Docker setup, DB schema, FastAPI skeleton, React shell, auth system |
| 2 | **3CX Adapter** | Week 3-4 | ThreeCXv20Adapter: login, probe, getTrunks, getSBCs, getLicense |
| 3 | **Monitoring** | Week 5-6 | Dashboard, instance detail views, polling worker, real-time status |
| 4 | **Backups** | Week 7-8 | Backup list, download, scheduled pulls, retention, encryption-at-rest |
| 5 | **Alerts** | Week 9 | Alert rules engine, alert events, notification (in-app + optional email/webhook) |
| 6 | **Audit & Polish** | Week 10 | Audit log, CSV export, UI polish, error handling, testing |
| 7 | **Phase 2 Prep** | Week 11-12 | RBAC, dry-run framework, first write action (trunk enable/disable) |

---

## 8. Open Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| 3CX v20 has no stable public API | High | Network-call replication + adapter pattern; probe on connect |
| Session tokens expire unpredictably | Medium | Auto re-auth with backoff; monitor session health |
| Minor version updates break endpoints | High | Version detection + capability matrix; adapter versioning |
| Backup files very large (multi-GB) | Medium | Streaming download; chunked transfer; progress tracking |
| Self-signed certs common in labs | Low | Per-PBX TLS policy with explicit opt-in |
| PBX load from polling | Medium | Conservative defaults; configurable intervals; caching + diffing |

---

## 9. 3CX v20 Authentication Strategy

### Login Flow (Network-Call Replication)

1. **GET** `https://<pbx-url>/` — Discover login page, extract CSRF token if present
2. **POST** `https://<pbx-url>/api/login` (or equivalent) — Submit credentials
   - Expected payload: `{ "Username": "admin", "Password": "..." }`
   - Response: Set-Cookie with session token, or JSON with bearer token
3. **Store session** in-memory per PBX instance (never persist session tokens)
4. **Validate session** before each poll; re-auth if 401/403
5. **Probe endpoints** sequentially:
   - `GET /api/SystemStatus` or similar
   - `GET /api/TrunkList` or equivalent
   - `GET /api/SbcList`
   - `GET /api/LicenseInfo`
   - `GET /api/BackupList`

### Session Management
- Sessions cached per PBX in a thread-safe dict
- TTL: conservative (re-auth every 15 min or on any auth error)
- Concurrent requests to same PBX share session (with lock)

### Endpoint Discovery (Probe)
```python
ENDPOINTS_TO_PROBE = [
    ("login",    "POST", "/api/login"),
    ("trunks",   "GET",  "/api/TrunkList"),
    ("trunks",   "GET",  "/api/SystemStatus/Trunks"),
    ("sbcs",     "GET",  "/api/SbcList"),
    ("sbcs",     "GET",  "/api/SystemStatus/SBCs"),
    ("license",  "GET",  "/api/LicenseInfo"),
    ("license",  "GET",  "/api/SystemStatus/License"),
    ("backups",  "GET",  "/api/BackupList"),
    ("backups",  "GET",  "/api/BackupAndRestore"),
    ("version",  "GET",  "/api/SystemStatus"),
]
```
Each is tried; first successful response shape is recorded in capability map.
