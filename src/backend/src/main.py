"""PBXMonitorX — FastAPI Application Entry Point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config.settings import get_settings
from src.modules.auth.router import router as auth_router
from src.modules.pbx.router import router as pbx_router
from src.modules.backup.router import router as backup_router
from src.modules.alert.router import router as alert_router
from src.modules.audit.router import router as audit_router
from src.modules.scheduler.router import router as scheduler_router
from src.modules.settings.router import router as settings_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    # Startup: verify encryption key, check DB connectivity
    settings = get_settings()
    assert len(settings.encryption_key_bytes) == 32, "MASTER_ENCRYPTION_KEY must be 32 bytes (64 hex chars)"
    yield
    # Shutdown: cleanup sessions, close pools


app = FastAPI(
    title="PBXMonitorX",
    description="3CX v20 Monitoring & Backup Management",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(pbx_router, prefix="/api/pbx", tags=["pbx"])
app.include_router(backup_router, prefix="/api/backups", tags=["backups"])
app.include_router(alert_router, prefix="/api/alerts", tags=["alerts"])
app.include_router(audit_router, prefix="/api/audit", tags=["audit"])
app.include_router(scheduler_router, prefix="/api/scheduler", tags=["scheduler"])
app.include_router(settings_router, prefix="/api/settings", tags=["settings"])


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "0.1.0"}
