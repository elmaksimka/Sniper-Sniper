from functools import lru_cache

from pydantic import Field
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration.

    Values are loaded from environment variables.
    """

    app_name: str = "Alpha Engine"
    environment: str = "development"

    # Solana
    solana_rpc_url: str = Field(
        default="",
        description="Solana RPC endpoint",
    )

    helius_api_key: str = Field(
        default="",
        description="Helius API key",
    )

    helius_rpc_url: str = Field(
        default="",
        description="Helius RPC endpoint",
    )

    helius_timeout_seconds: float = Field(default=10, gt=0)
    helius_max_retries: int = Field(default=3, ge=0, le=10)
    helius_retry_base_seconds: float = Field(default=0.5, ge=0)
    helius_retry_max_seconds: float = Field(default=10, gt=0)
    helius_max_concurrency: int = Field(default=5, ge=1, le=100)

    wallet_score_alert_threshold: float = Field(
        default=65,
        ge=0,
        le=100,
        description="Minimum wallet score that produces an alert",
    )
    token_score_alert_threshold: float = Field(
        default=65,
        ge=0,
        le=100,
        description="Minimum token score that produces an alert",
    )

    monitor_poll_interval_seconds: float = Field(default=30, gt=0)
    monitor_page_size: int = Field(default=100, ge=1, le=100)
    monitor_max_pages: int = Field(default=10, ge=1, le=100)
    worker_leader_lock_key: int = Field(default=712_493_551, ge=1)
    worker_standby_poll_seconds: float = Field(default=5, gt=0)
    worker_heartbeat_interval_seconds: float = Field(default=15, gt=0)
    worker_heartbeat_stale_seconds: float = Field(default=120, gt=0)
    readiness_check_timeout_seconds: float = Field(default=3, gt=0)

    admin_api_key: str = Field(
        default="",
        description="API key required by administrative endpoints in production",
    )
    allowed_hosts: str = Field(
        default="*",
        description="Comma-separated HTTP Host allowlist",
    )

    # Database
    database_url: str = Field(
        default="",
        description="PostgreSQL connection URL",
    )

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.environment.lower() != "production":
            return self

        missing: list[str] = []
        if not self.database_url:
            missing.append("DATABASE_URL")
        if not (self.helius_api_key or self.helius_rpc_url):
            missing.append("HELIUS_API_KEY or HELIUS_RPC_URL")
        if len(self.admin_api_key) < 32:
            missing.append("ADMIN_API_KEY (at least 32 characters)")
        allowed_hosts = {
            host.strip()
            for host in self.allowed_hosts.split(",")
            if host.strip()
        }
        if not allowed_hosts or "*" in allowed_hosts:
            missing.append("ALLOWED_HOSTS (explicit host allowlist)")
        if missing:
            raise ValueError(
                "Missing or invalid production configuration: "
                + ", ".join(missing)
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """
    Returns cached application settings.
    """
    return Settings()
