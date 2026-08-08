from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models import Token
from app.repositories.token_repository import TokenRepository


class TokenService:
    def __init__(
        self,
        session: AsyncSession,
    ):
        self.repository = TokenRepository(
            session
        )

    async def create_token(
        self,
        address: str,
        symbol: str | None = None,
        name: str | None = None,
        creator: str | None = None,
        decimals: int | None = None,
        supply: int | None = None,
    ) -> Token:

        existing_token = await self.repository.get_by_address(
            address
        )

        if existing_token:
            print(
                "Token already exists:",
                address,
            )

            return existing_token

        print(
            "Creating new token:",
            address,
            "|",
            symbol,
            "|",
            name,
            "| creator:",
            creator,
        )

        token = Token(
            address=address,
            symbol=self._bounded(symbol, 32),
            name=self._bounded(name, 128),
            creator=self._bounded(creator, 64),
            decimals=decimals,
            supply=supply,
        )

        return await self.repository.create(
            token
        )

    @staticmethod
    def _bounded(value: str | None, maximum_length: int) -> str | None:
        return value[:maximum_length] if value is not None else None
