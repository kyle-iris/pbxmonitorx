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

    # Azure AD SSO
    azure_ad_enabled: bool = False
    azure_ad_tenant_id: str = ""
    azure_ad_client_id: str = ""
    azure_ad_client_secret: str = ""
    azure_ad_redirect_uri: str = "http://localhost:8000/api/auth/sso/callback"
    azure_ad_auto_create_users: bool = True
    azure_ad_default_role: str = "viewer"

    @property
    def master_key_bytes(self) -> bytes:
        return bytes.fromhex(self.master_key)

    model_config = {"env_file": ".env"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
