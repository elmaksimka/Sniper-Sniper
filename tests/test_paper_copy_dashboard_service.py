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

    async def _portfolio(self):  # type: ignore[no-untyped-def]
        return self.portfolio

    async def _positions(self, portfolio_id):  # type: ignore[no-untyped-def]
        assert portfolio_id == 1
        return [(self.position, "TKN", "Token")]


@pytest.mark.asyncio
async def test_dashboard_calculates_open_position_value_and_pnl() -> None:
    dashboard = await StubDashboardService().get()

    assert dashboard["total_equity_usd"] == pytest.approx(101.88)
    assert dashboard["total_pnl_usd"] == pytest.approx(1.88)
    position = dashboard["positions"][0]
    assert position["market_value_usd"] == pytest.approx(12.0)
    assert position["estimated_exit_value_usd"] == pytest.approx(11.88)
    assert position["unrealized_pnl_usd"] == pytest.approx(1.88)
    assert position["unrealized_roi_pct"] == pytest.approx(18.8)
