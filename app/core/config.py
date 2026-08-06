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