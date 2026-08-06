from functools import lru_cache

from pydantic import Field
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

    wallet_score_alert_threshold: float = Field(
        default=65,
        ge=0,
        le=100,
        description="Minimum wallet score that produces an alert",
    )

    monitor_poll_interval_seconds: float = Field(default=30, gt=0)
    monitor_page_size: int = Field(default=100, ge=1, le=100)
    monitor_max_pages: int = Field(default=10, ge=1, le=100)

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


@lru_cache
def get_settings() -> Settings:
    """
    Returns cached application settings.
    """
    return Settings()
