import pytest

from app.infrastructure.models import Token
from app.services.token_service import TokenService


class FakeTokenRepository:
    def __init__(self) -> None:
        self.created: Token | None = None

    async def get_by_address(self, address: str) -> None:
        return None

    async def create(self, token: Token) -> Token:
        self.created = token
        return token


@pytest.mark.asyncio
async def test_token_metadata_is_bounded_to_database_columns() -> None:
    repository = FakeTokenRepository()
    service = TokenService.__new__(TokenService)
    service.repository = repository  # type: ignore[assignment]

    token = await service.create_token(
        "mint",
        symbol="s" * 200,
        name="n" * 200,
        creator="c" * 200,
    )

    assert token.symbol == "s" * 32
    assert token.name == "n" * 128
    assert token.creator == "c" * 64


@pytest.mark.asyncio
async def test_token_supply_accepts_full_solana_uint64_range() -> None:
    repository = FakeTokenRepository()
    service = TokenService.__new__(TokenService)
    service.repository = repository  # type: ignore[assignment]

    token = await service.create_token("mint", supply=2**64 - 1)

    assert token.supply == 2**64 - 1
