from sqlalchemy import func, select
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

    async def list_all(
        self,
        limit: int,
        offset: int,
        creator: str | None = None,
    ) -> list[Token]:
        statement = select(Token)
        if creator:
            statement = statement.where(Token.creator == creator)

        result = await self.session.execute(
            statement
            .order_by(Token.created_at.desc(), Token.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count(self, creator: str | None = None) -> int:
        statement = select(func.count(Token.id))
        if creator:
            statement = statement.where(Token.creator == creator)

        result = await self.session.execute(statement)
        return result.scalar_one()
