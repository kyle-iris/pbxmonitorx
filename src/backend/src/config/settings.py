"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://pbxmonitorx:changeme@localhost:5432/pbxmonitorx"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Security
    master_encryption_key: str  # 64-char hex string (32 bytes)
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # CORS
    cors_origins: str = "http://localhost:3000"

    # Backup storage
    backup_storage_path: str = "/data/backups"
    encrypt_backups: bool = False

    # Polling defaults
    default_poll_interval_s: int = 60
    max_poll_interval_s: int = 600  # max backoff
    min_poll_interval_s: int = 30

    # Rate limiting
    login_max_attempts: int = 5
    login_lockout_minutes: int = 15

    # Logging
    log_level: str = "info"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    @property
    def encryption_key_bytes(self) -> bytes:
        return bytes.fromhex(self.master_encryption_key)

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
