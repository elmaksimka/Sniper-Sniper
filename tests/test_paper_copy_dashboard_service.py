from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.services.paper_copy_dashboard_service import PaperCopyDashboardService


class StubDashboardService(PaperCopyDashboardService):
    def __init__(self) -> None:
        super().__init__(None, "paper-copy-pool")  # type: ignore[arg-type]
        now = datetime.now(UTC)
        self.portfolio = SimpleNamespace(
            id=1,
            source_wallet="paper-copy-pool",
            enabled=True,
            initial_balance_usd=100.0,
            cash_balance_usd=90.0,
            allocation_usd=2.0,
            max_open_positions=20,
            slippage_bps=100,
            started_at=now,
        )
        self.position = SimpleNamespace(
            source_wallet="trader",
            token_address="mint",
            source_quantity=1_000.0,
            quantity=10.0,
            cost_basis_usd=10.0,
            entry_price_usd=1.0,
            last_price_usd=1.2,
            opened_at=now,
            updated_at=now,
        )
        self.closed = SimpleNamespace(
            source_wallet="trader",
            token_address="mint",
            source_signature="signature",
            source_amount=1_000.0,
            quantity=5.0,
            value_usd=6.0,
            realized_pnl_usd=1.0,
            execution_price_usd=1.2,
            source_transaction_at=now,
            executed_at=now,
        )

    async def _portfolio(self):  # type: ignore[no-untyped-def]
        return self.portfolio

    async def _positions(self, portfolio_id):  # type: ignore[no-untyped-def]
        assert portfolio_id == 1
        return [(self.position, "TKN", "Token")]

    async def _closed_positions(self, portfolio_id):  # type: ignore[no-untyped-def]
        assert portfolio_id == 1
        return [(self.closed, "TKN", "Token")]


@pytest.mark.asyncio
async def test_dashboard_calculates_open_position_value_and_pnl() -> None:
    dashboard = await StubDashboardService().get()

    assert dashboard["total_equity_usd"] == pytest.approx(101.88)
    assert dashboard["total_pnl_usd"] == pytest.approx(1.88)
    assert dashboard["open_pnl_usd"] == pytest.approx(1.88)
    assert dashboard["realized_pnl_usd"] == pytest.approx(1.0)
    position = dashboard["positions"][0]
    assert position["market_value_usd"] == pytest.approx(12.0)
    assert position["estimated_exit_value_usd"] == pytest.approx(11.88)
    assert position["unrealized_pnl_usd"] == pytest.approx(1.88)
    assert position["unrealized_roi_pct"] == pytest.approx(18.8)
    closed = dashboard["closed_positions"][0]
    assert closed["cost_basis_usd"] == pytest.approx(5.0)
    assert closed["realized_pnl_usd"] == pytest.approx(1.0)
    assert closed["realized_roi_pct"] == pytest.approx(20.0)
    trader = dashboard["trader_stats"][0]
    assert trader["source_wallet"] == "trader"
    assert trader["current_aa"] is False
    assert trader["open_positions"] == 1
    assert trader["closed_trades"] == 1
    assert trader["profitable_closed_trades"] == 1
    assert trader["realized_pnl_usd"] == pytest.approx(1.0)
    assert trader["open_pnl_usd"] == pytest.approx(1.88)
    assert trader["total_pnl_usd"] == pytest.approx(2.88)
    assert trader["total_roi_pct"] == pytest.approx(19.2)
    assert trader["closed_win_rate_pct"] == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_dashboard_includes_all_current_aa_sources_without_trades() -> None:
    service = StubDashboardService()
    service.source_wallets = ("trader", "idle-aa-trader")

    dashboard = await service.get()

    assert [item["source_wallet"] for item in dashboard["trader_stats"]] == [
        "trader",
        "idle-aa-trader",
    ]
    assert all(item["current_aa"] for item in dashboard["trader_stats"])
    idle = dashboard["trader_stats"][1]
    assert idle["closed_trades"] == 0
    assert idle["open_positions"] == 0
    assert idle["total_pnl_usd"] == 0
