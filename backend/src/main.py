"""PBXMonitorX — FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from src.core.config import get_settings
from src.api.routes import router
from src.api.phone_routes import router as phone_router
from src.api.backup_routes import router as backup_router
from src.api.user_routes import router as user_router
from src.api.sso_routes import router as sso_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    # Fail fast if master key is wrong length
    assert len(settings.master_key_bytes) == 32, (
        "MASTER_KEY must be 32 bytes (64 hex chars). "
        'Generate with: python -c "import secrets; print(secrets.token_hex(32))"'
    )
    logging.getLogger("pbxmonitorx").info("PBXMonitorX starting")
    yield
    logging.getLogger("pbxmonitorx").info("PBXMonitorX shutting down")


app = FastAPI(
    title="PBXMonitorX",
    version="0.2.0",
    description="3CX v20 Linux PBX Monitor & Backup Management",
    lifespan=lifespan,
)

# Session middleware required for SSO OAuth state management
app.add_middleware(SessionMiddleware, secret_key=get_settings().jwt_secret)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Lock down in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Core API routes
app.include_router(router, prefix="/api")
app.include_router(phone_router, prefix="/api")
app.include_router(backup_router, prefix="/api")
app.include_router(user_router, prefix="/api")
app.include_router(sso_router, prefix="/api")
