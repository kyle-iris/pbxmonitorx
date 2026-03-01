"""Application configuration — all sensitive values from environment."""
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    # 64-hex-char string = 32 bytes for AES-256
    master_key: str

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    backup_path: str = "/data/backups"

    # Polling
    default_poll_interval: int = 60
    max_backoff_interval: int = 600

    # Rate limiting
    max_login_attempts: int = 5
    lockout_minutes: int = 15

    @property
    def master_key_bytes(self) -> bytes:
        return bytes.fromhex(self.master_key)

    model_config = {"env_file": ".env"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
