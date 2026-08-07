import pytest
from pydantic import ValidationError

from app.core.config import Settings


def production_settings(**overrides: str) -> Settings:
    values = {
        "environment": "production",
        "database_url": "postgresql+asyncpg://alpha:secret@postgres/alpha_engine",
        "helius_api_key": "helius-key",
        "admin_api_key": "a" * 32,
        "allowed_hosts": "api.example.com,localhost,127.0.0.1",
        "git_sha": "abcdef1",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def test_production_settings_accept_complete_configuration() -> None:
    settings = production_settings()

    assert settings.environment == "production"


def test_production_settings_accept_standard_solana_rpc() -> None:
    settings = production_settings(
        helius_api_key="",
        solana_rpc_url="https://api.mainnet.solana.com",
        transaction_history_mode="standard",
    )

    assert settings.transaction_history_mode == "standard"


def test_enhanced_history_rejects_plain_solana_rpc_only() -> None:
    with pytest.raises(ValidationError, match="HELIUS_API_KEY"):
        production_settings(
            helius_api_key="",
            solana_rpc_url="https://api.mainnet.solana.com",
            transaction_history_mode="enhanced",
        )


def test_telegram_recipient_list_is_trimmed_and_deduplicated() -> None:
    settings = Settings(
        _env_file=None,
        telegram_chat_id="100",
        telegram_chat_ids="200, 100, ,300",
    )

    assert settings.telegram_recipients == ("100", "200", "300")


@pytest.mark.parametrize("scheme", ["postgres", "postgresql"])
def test_managed_postgres_urls_use_asyncpg(scheme: str) -> None:
    settings = Settings(
        _env_file=None,
        database_url=f"{scheme}://alpha:secret@postgres/alpha_engine",
    )

    assert settings.database_url == (
        "postgresql+asyncpg://alpha:secret@postgres/alpha_engine"
    )


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"database_url": ""}, "DATABASE_URL"),
        ({"helius_api_key": "", "helius_rpc_url": ""}, "HELIUS_API_KEY"),
        ({"admin_api_key": "short"}, "ADMIN_API_KEY"),
        ({"allowed_hosts": "*"}, "ALLOWED_HOSTS"),
        ({"allowed_hosts": "api.example.com,*"}, "ALLOWED_HOSTS"),
        ({"git_sha": "development"}, "GIT_SHA"),
    ],
)
def test_production_settings_reject_incomplete_configuration(
    overrides: dict[str, str],
    expected: str,
) -> None:
    with pytest.raises(ValidationError, match=expected):
        production_settings(**overrides)
