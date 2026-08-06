from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models import Trade


class TradeRepository:
    def __init__(
        self,
        session: AsyncSession,
    ):
        self.session = session

    async def create(
        self,
        trade: Trade,
    ) -> Trade:
        self.session.add(trade)

        await self.session.commit()
        await self.session.refresh(trade)

        return trade

    async def get_by_token_id(
        self,
        token_id: int,
    ) -> list[Trade]:

        result = await self.session.execute(
            select(Trade).where(
                Trade.token_id == token_id
            )
        )

        return list(result.scalars().all())