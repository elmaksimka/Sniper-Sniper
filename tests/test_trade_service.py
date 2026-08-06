from typing import Any

import pytest

from app.infrastructure.models import Trade
from app.services.trade_service import TradeService


class FakeTradeRepository:
    def __init__(self) -> None:
        self.trade: Trade | None = None
        self.create_calls = 0

    async def get_by_identity(
        self,
        signature: str,
        token_id: int,
        wallet_id: int,
    ) -> Trade | None:
        if (
            self.trade
            and self.trade.signature == signature
            and self.trade.token_id == token_id
            and self.trade.wallet_id == wallet_id
        ):
            return self.trade

        return None

    async def create(self, trade: Trade) -> Trade:
        self.create_calls += 1
        trade.id = self.create_calls
        self.trade = trade
        return trade


@pytest.mark.asyncio
async def test_create_trade_is_idempotent_for_transaction_identity() -> None:
    session: Any = None
    service = TradeService(session)
    repository = FakeTradeRepository()
    service_with_fake: Any = service
    service_with_fake.repository = repository

    first = await service.create_trade(
        token_id=1,
        wallet_id=2,
        side="buy",
        amount=10,
        price=0.1,
        sol_change=-1,
        signature="signature",
    )
    second = await service.create_trade(
        token_id=1,
        wallet_id=2,
        side="buy",
        amount=10,
        price=0.1,
        sol_change=-1,
        signature="signature",
    )

    assert second is first
    assert repository.create_calls == 1
