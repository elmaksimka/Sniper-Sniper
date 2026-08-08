from functools import lru_cache
import re
from typing import Literal

from pydantic import Field, field_validator
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration.

    Values are loaded from environment variables.
    """

    app_name: str = "Alpha Engine"
    app_version: str = "0.1.0"
    git_sha: str = "development"
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
    birdeye_api_key: str = Field(
        default="",
        description="Birdeye Data Services API key",
    )

    helius_timeout_seconds: float = Field(default=10, gt=0)
    helius_max_retries: int = Field(default=3, ge=0, le=10)
    helius_retry_base_seconds: float = Field(default=0.5, ge=0)
    helius_retry_max_seconds: float = Field(default=10, gt=0)
    helius_max_concurrency: int = Field(default=5, ge=1, le=100)
    transaction_history_mode: Literal["enhanced", "standard"] = "enhanced"

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
    alpha_wallet_score_threshold: float = Field(default=65, ge=0, le=100)
    alpha_early_token_score_threshold: float = Field(default=45, ge=0, le=100)
    alpha_early_token_min_trades: int = Field(default=10, ge=1, le=100)
    alpha_early_token_min_wallets: int = Field(default=5, ge=1, le=100)
    alpha_market_min_liquidity_usd: float = Field(default=15_000, ge=0)
    alpha_market_min_volume_5m_usd: float = Field(default=5_000, ge=0)
    alpha_market_min_transactions_5m: int = Field(default=10, ge=0)
    alpha_market_max_pair_age_minutes: float = Field(default=60, gt=0)
    alpha_trader_min_history_trades: int = Field(default=10, ge=1)
    alpha_trader_min_hold_minutes: float = Field(default=30, gt=0)
    alpha_trader_max_distinct_tokens_60s: int = Field(default=4, ge=1)
    alpha_trader_max_side_switches_per_token: int = Field(default=2, ge=0)
    alpha_trader_side_switch_window_minutes: float = Field(default=10, gt=0)
    alpha_trader_rapid_round_trip_seconds: float = Field(default=120, gt=0)
    alpha_trader_max_rapid_round_trips: int = Field(default=0, ge=0)
    alpha_signal_max_age_seconds: float = Field(default=300, gt=0)
    discovery_enabled: bool = False
    discovery_program_ids: str = ""
    discovery_page_size: int = Field(default=50, ge=1, le=100)
    discovery_max_pages: int = Field(default=1, ge=1, le=10)
    discovery_poll_interval_seconds: float = Field(default=120, gt=0)
    discovery_retry_max_seconds: float = Field(default=900, gt=0)
    candidate_enrichment_enabled: bool = False
    candidate_enrichment_min_score: float = Field(default=35, ge=0, le=65)
    candidate_enrichment_history_limit: int = Field(default=75, ge=1, le=100)
    candidate_enrichment_max_per_cycle: int = Field(default=1, ge=1, le=10)
    candidate_enrichment_retry_seconds: float = Field(default=1800, gt=0)
    candidate_source_window_hours: int = Field(default=24, ge=1, le=168)
    candidate_source_token_limit: int = Field(default=25, ge=1, le=100)
    candidate_source_traders_per_token: int = Field(default=10, ge=1, le=100)
    candidate_source_minimum_token_trades: int = Field(default=10, ge=1)
    candidate_source_minimum_token_wallets: int = Field(default=5, ge=1)
    candidate_source_minimum_observed_minutes: float = Field(default=30, gt=0)
    candidate_source_minimum_current_multiple: float = Field(default=3, gt=1)
    candidate_source_early_entry_minutes: float = Field(default=30, gt=0)
    candidate_source_early_entry_max_multiple: float = Field(default=2, gt=1)
    candidate_external_discovery_interval_seconds: float = Field(
        default=21_600,
        gt=0,
    )
    candidate_external_token_limit: int = Field(default=5, ge=1, le=25)
    candidate_external_minimum_realized_pnl_usd: float = Field(
        default=1_000,
        ge=0,
    )
    candidate_external_minimum_realized_roi: float = Field(default=1, ge=0)
    auto_promote_wallet_score: float = Field(default=65, ge=0, le=100)
    auto_promote_max_monitors: int = Field(default=100, ge=1, le=10_000)

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
    telegram_chat_ids: str = ""
    telegram_status_interval_seconds: float = Field(default=1800, gt=0)
    telegram_status_window_minutes: int = Field(default=30, ge=1, le=1440)

    @property
    def telegram_recipients(self) -> tuple[str, ...]:
        values = [self.telegram_chat_id, *self.telegram_chat_ids.split(",")]
        return tuple(dict.fromkeys(value.strip() for value in values if value.strip()))

    @property
    def discovery_programs(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                value.strip()
                for value in self.discovery_program_ids.split(",")
                if value.strip()
            )
        )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+asyncpg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.discovery_enabled and not self.discovery_programs:
            raise ValueError(
                "DISCOVERY_PROGRAM_IDS is required when discovery is enabled"
            )
        if self.environment.lower() != "production":
            return self

        missing: list[str] = []
        if not self.database_url:
            missing.append("DATABASE_URL")
        if self.transaction_history_mode == "enhanced":
            if not (self.helius_api_key or self.helius_rpc_url):
                missing.append("HELIUS_API_KEY or HELIUS_RPC_URL")
        elif not (self.solana_rpc_url or self.helius_rpc_url or self.helius_api_key):
            missing.append("SOLANA_RPC_URL or another standard RPC URL")
        if len(self.admin_api_key) < 32:
            missing.append("ADMIN_API_KEY (at least 32 characters)")
        allowed_hosts = {
            host.strip()
            for host in self.allowed_hosts.split(",")
            if host.strip()
        }
        if not allowed_hosts or "*" in allowed_hosts:
            missing.append("ALLOWED_HOSTS (explicit host allowlist)")
        if re.fullmatch(r"[0-9a-fA-F]{7,40}", self.git_sha) is None:
            missing.append("GIT_SHA (7-40 hexadecimal characters)")
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
