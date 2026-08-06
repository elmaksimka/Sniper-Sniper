from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models import Token


class TokenRepository:
    def __init__(
        self,
        session: AsyncSession,
    ):
        self.session = session

    async def create(
        self,
        token: Token,
    ) -> Token:
        self.session.add(token)

        await self.session.commit()
        await self.session.refresh(token)

        return token

    async def get_by_address(
        self,
        address: str,
    ) -> Token | None:
        result = await self.session.execute(
            select(Token).where(
                Token.address == address
            )
        )

        return result.scalar_one_or_none()