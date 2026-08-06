from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from app.repositories.analytics_repository import AnalyticsRepository


class FakeResult:
    def __init__(self, row: SimpleNamespace) -> None:
        self.row = row

    def one(self) -> SimpleNamespace:
        return self.row


class CompilingSession:
    def __init__(self, row: SimpleNamespace) -> None:
        self.row = row
        self.sql = ""

    async def execute(self, statement: Any) -> FakeResult:
        self.sql = str(statement.compile(dialect=postgresql.dialect()))
        return FakeResult(self.row)


@pytest.mark.asyncio
async def test_wallet_analytics_query_and_mapping() -> None:
    session = CompilingSession(
        SimpleNamespace(
            total_trades=3,
            buy_count=2,
            sell_count=1,
            unique_tokens=2,
            sol_spent=2.5,
            sol_received=1,
            net_sol_change=-1.5,
            first_trade_at=None,
            last_trade_at=None,
        )
    )
    repository = AnalyticsRepository(session)  # type: ignore[arg-type]

    metrics = await repository.get_wallet_metrics("wallet")

    assert "JOIN wallets" in session.sql
    assert "FILTER" in session.sql
    assert "count(DISTINCT trades.token_id)" in session.sql
    assert metrics.total_trades == 3
    assert metrics.sol_spent == 2.5


@pytest.mark.asyncio
async def test_token_analytics_query_and_mapping() -> None:
    session = CompilingSession(
        SimpleNamespace(
            total_trades=4,
            buy_count=3,
            sell_count=1,
            unique_wallets=2,
            buy_volume=20,
            sell_volume=5,
            net_token_flow=15,
            net_wallet_sol_change=-2,
            first_trade_at=None,
            last_trade_at=None,
        )
    )
    repository = AnalyticsRepository(session)  # type: ignore[arg-type]

    metrics = await repository.get_token_metrics("mint")

    assert "JOIN tokens" in session.sql
    assert "count(DISTINCT trades.wallet_id)" in session.sql
    assert metrics.unique_wallets == 2
    assert metrics.net_token_flow == 15
