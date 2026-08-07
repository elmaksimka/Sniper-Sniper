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
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def test_production_settings_accept_complete_configuration() -> None:
    settings = production_settings()

    assert settings.environment == "production"


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"database_url": ""}, "DATABASE_URL"),
        ({"helius_api_key": "", "helius_rpc_url": ""}, "HELIUS_API_KEY"),
        ({"admin_api_key": "short"}, "ADMIN_API_KEY"),
        ({"allowed_hosts": "*"}, "ALLOWED_HOSTS"),
        ({"allowed_hosts": "api.example.com,*"}, "ALLOWED_HOSTS"),
    ],
)
def test_production_settings_reject_incomplete_configuration(
    overrides: dict[str, str],
    expected: str,
) -> None:
    with pytest.raises(ValidationError, match=expected):
        production_settings(**overrides)
