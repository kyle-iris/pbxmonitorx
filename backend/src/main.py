"""PBXMonitorX — FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import get_settings
from src.api.routes import router

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
    version="0.1.0",
    description="3CX v20 Linux PBX Monitor & Backup Management",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Lock down in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
