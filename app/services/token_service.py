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
        )

        token = Token(
            address=address,
            symbol=symbol,
            name=name,
        )

        return await self.repository.create(
            token
        )