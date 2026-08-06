from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models import Trade
from app.repositories.trade_repository import TradeRepository


class TradeService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = TradeRepository(session)

    async def create_trade(
        self,
        token_id: int,
        wallet_id: int,
        side: str,
        amount: float,
        price: float,
        sol_change: float,
        signature: str | None = None,
        timestamp: datetime | None = None,
    ) -> Trade:
        if signature:
            existing_trade = await self.repository.get_by_identity(
                signature=signature,
                token_id=token_id,
                wallet_id=wallet_id,
            )
            if existing_trade:
                return existing_trade

        trade = Trade(
            token_id=token_id,
            wallet_id=wallet_id,
            side=side,
            amount=amount,
            price=price,
            sol_change=sol_change,
            signature=signature,
            timestamp=timestamp or datetime.now(UTC),
        )

        return await self.repository.create(trade)
