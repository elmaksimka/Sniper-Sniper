from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models import Trade
from app.repositories.trade_repository import TradeRepository


class TradeService:
    def __init__(
        self,
        session: AsyncSession,
    ):
        self.repository = TradeRepository(
            session
        )

    async def create_trade(
        self,
        token_id: int,
        wallet_id: int,
        side: str,
        amount: float,
    ) -> Trade:

        trade = Trade(
            token_id=token_id,
            wallet_id=wallet_id,
            side=side,
            amount=amount,
            timestamp=datetime.now(timezone.utc),
        )

        print(
            "Creating trade:",
            side,
            amount,
        )

        return await self.repository.create(
            trade
        )