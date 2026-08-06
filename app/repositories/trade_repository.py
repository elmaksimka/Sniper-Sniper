from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.infrastructure.models import Token, Trade, Wallet


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

    async def get_by_identity(
        self,
        signature: str,
        token_id: int,
        wallet_id: int,
    ) -> Trade | None:
        result = await self.session.execute(
            select(Trade).where(
                Trade.signature == signature,
                Trade.token_id == token_id,
                Trade.wallet_id == wallet_id,
            )
        )

        return result.scalar_one_or_none()

    async def list_all(
        self,
        limit: int,
        offset: int,
        token_address: str | None = None,
        wallet_address: str | None = None,
        side: str | None = None,
    ) -> list[Trade]:
        conditions = self._filters(token_address, wallet_address, side)
        result = await self.session.execute(
            select(Trade)
            .join(Trade.token)
            .join(Trade.wallet)
            .options(
                selectinload(Trade.token),
                selectinload(Trade.wallet),
            )
            .where(*conditions)
            .order_by(Trade.timestamp.desc(), Trade.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count(
        self,
        token_address: str | None = None,
        wallet_address: str | None = None,
        side: str | None = None,
    ) -> int:
        conditions = self._filters(token_address, wallet_address, side)
        result = await self.session.execute(
            select(func.count(Trade.id))
            .join(Trade.token)
            .join(Trade.wallet)
            .where(*conditions)
        )
        return result.scalar_one()

    @staticmethod
    def _filters(
        token_address: str | None,
        wallet_address: str | None,
        side: str | None,
    ) -> list:
        conditions = []
        if token_address:
            conditions.append(Token.address == token_address)
        if wallet_address:
            conditions.append(Wallet.address == wallet_address)
        if side:
            conditions.append(Trade.side == side)
        return conditions
