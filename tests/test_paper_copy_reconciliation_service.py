from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.infrastructure.models import (
    PaperCopyOrder,
    PaperCopyPortfolio,
    PaperCopyPosition,
)
from app.services.dexscreener_client import TokenMarketQuote
from app.services.jupiter_quote_client import SwapRouteQuote, USDC_MINT
from app.services.paper_copy_reconciliation_service import (
    PaperCopyReconciliationService,
)


class FakeSession:
    def __init__(self) -> None:
        self.orders: list[PaperCopyOrder] = []
        self.commits = 0

    def add(self, item: Any) -> None:
        if isinstance(item, PaperCopyOrder):
            self.orders.append(item)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1


class FakeRepository:
    def __init__(self, position: PaperCopyPosition) -> None:
        self.portfolio = PaperCopyPortfolio(
            id=1,
            source_wallet="paper-pool",
            initial_balance_usd=100,
            cash_balance_usd=90,
            allocation_usd=10,
            max_open_positions=10,
            reaction_delay_seconds=20,
            slippage_bps=100,
            minimum_liquidity_usd=15_000,
            enabled=True,
            started_at=datetime.now(UTC),
        )
        self.position = position
        self.pending: set[tuple[str, str]] = set()
        self.snapshots: list[dict[str, float | int]] = []
        self.session = FakeSession()

    async def get_portfolio(self, source_wallet: str) -> PaperCopyPortfolio | None:
        return self.portfolio if source_wallet == "paper-pool" else None

    async def list_open_positions(self, portfolio_id: int) -> list[PaperCopyPosition]:
        return [self.position] if self.position.quantity > 0 else []

    async def pending_position_keys(self, portfolio_id: int) -> set[tuple[str, str]]:
        return self.pending

    async def count_open_positions(self, portfolio_id: int) -> int:
        return int(self.position.quantity > 0)

    async def get_token_decimals(self, token_address: str) -> int:
        return 6

    async def equity(self, portfolio: PaperCopyPortfolio) -> float:
        return portfolio.cash_balance_usd + (
            self.position.quantity * self.position.last_price_usd
        )

    async def add_position_snapshot(
        self,
        position: PaperCopyPosition,
        **values: float | int,
    ) -> None:
        self.snapshots.append(values)


class FakeBalances:
    def __init__(self, amount: float) -> None:
        self.amount = amount
        self.calls: list[str] = []

    async def get_token_balances(self, owner: str) -> dict[str, float]:
        self.calls.append(owner)
        return {"mint": self.amount} if self.amount else {}


class FailingBalances:
    async def get_token_balances(self, owner: str) -> dict[str, float]:
        raise RuntimeError("RPC unavailable")


class FakeMarketData:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def get_token_quote(self, token_address: str) -> TokenMarketQuote:
        self.calls.append(token_address)
        return TokenMarketQuote(price_usd=2, pair_url=None, liquidity_usd=50_000)


class FakeRouteQuotes:
    async def get_sell_quote(
        self, token_address: str, token_amount: float, token_decimals: int
    ) -> SwapRouteQuote:
        return SwapRouteQuote(
            input_mint=token_address,
            output_mint=USDC_MINT,
            input_amount=token_amount,
            output_amount=token_amount * 1.98,
            price_impact_pct=0.25,
            fee_bps=10,
            router="metis",
            route="Raydium",
        )


class LossRouteQuotes(FakeRouteQuotes):
    async def get_sell_quote(
        self, token_address: str, token_amount: float, token_decimals: int
    ) -> SwapRouteQuote:
        route = await super().get_sell_quote(
            token_address,
            token_amount,
            token_decimals,
        )
        return SwapRouteQuote(
            input_mint=route.input_mint,
            output_mint=route.output_mint,
            input_amount=route.input_amount,
            output_amount=route.input_amount * 0.69,
            price_impact_pct=route.price_impact_pct,
            fee_bps=route.fee_bps,
            router=route.router,
            route=route.route,
        )


def position() -> PaperCopyPosition:
    return PaperCopyPosition(
        id=1,
        portfolio_id=1,
        source_wallet="trader",
        token_address="mint",
        source_quantity=100,
        quantity=10,
        cost_basis_usd=10,
        entry_price_usd=1,
        last_price_usd=1,
        opened_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_reconciliation_closes_position_absent_on_chain() -> None:
    tracked = position()
    repository = FakeRepository(tracked)

    result = await PaperCopyReconciliationService(
        repository,  # type: ignore[arg-type]
        FakeBalances(0),  # type: ignore[arg-type]
        FakeMarketData(),  # type: ignore[arg-type]
        FakeRouteQuotes(),  # type: ignore[arg-type]
    ).reconcile("paper-pool")

    assert result.positions_closed == 1
    assert tracked.source_quantity == 0
    assert tracked.quantity == 0
    assert tracked.cost_basis_usd == 0
    assert repository.portfolio.cash_balance_usd == pytest.approx(109.8)
    assert repository.session.orders[0].status == "filled"
    assert repository.session.orders[0].source_signature.startswith("reconcile-")


@pytest.mark.asyncio
async def test_reconciliation_reduces_partial_source_exit_proportionally() -> None:
    tracked = position()
    repository = FakeRepository(tracked)

    result = await PaperCopyReconciliationService(
        repository,  # type: ignore[arg-type]
        FakeBalances(40),  # type: ignore[arg-type]
        FakeMarketData(),  # type: ignore[arg-type]
        FakeRouteQuotes(),  # type: ignore[arg-type]
    ).reconcile("paper-pool")

    assert result.positions_reduced == 1
    assert result.positions_closed == 0
    assert tracked.source_quantity == pytest.approx(40)
    assert tracked.quantity == pytest.approx(4)
    assert tracked.cost_basis_usd == pytest.approx(4)


@pytest.mark.asyncio
async def test_reconciliation_tracks_larger_source_balance_without_fake_buy() -> None:
    tracked = position()
    repository = FakeRepository(tracked)

    result = await PaperCopyReconciliationService(
        repository,  # type: ignore[arg-type]
        FakeBalances(150),  # type: ignore[arg-type]
        FakeMarketData(),  # type: ignore[arg-type]
    ).reconcile("paper-pool")

    assert result.positions_increased == 1
    assert tracked.source_quantity == 150
    assert tracked.quantity == 10
    assert repository.session.orders == []


@pytest.mark.asyncio
async def test_startup_reconciliation_refreshes_open_position_prices() -> None:
    tracked = position()
    repository = FakeRepository(tracked)
    market_data = FakeMarketData()

    result = await PaperCopyReconciliationService(
        repository,  # type: ignore[arg-type]
        FakeBalances(100),  # type: ignore[arg-type]
        market_data,  # type: ignore[arg-type]
        FakeRouteQuotes(),  # type: ignore[arg-type]
    ).reconcile("paper-pool", refresh_prices=True)

    assert result.positions_checked == 1
    assert result.positions_repriced == 1
    assert result.prices_deferred == 0
    assert tracked.last_price_usd == pytest.approx(1.98)
    assert market_data.calls == []
    assert repository.snapshots[0]["roi_pct"] == pytest.approx(98)
    assert repository.session.commits == 1


@pytest.mark.asyncio
async def test_periodic_reconciliation_does_not_refresh_unchanged_prices() -> None:
    tracked = position()
    repository = FakeRepository(tracked)
    market_data = FakeMarketData()

    result = await PaperCopyReconciliationService(
        repository,  # type: ignore[arg-type]
        FakeBalances(100),  # type: ignore[arg-type]
        market_data,  # type: ignore[arg-type]
    ).reconcile("paper-pool")

    assert result.positions_repriced == 0
    assert tracked.last_price_usd == 1
    assert market_data.calls == []
    assert repository.session.commits == 0


@pytest.mark.asyncio
async def test_reconciliation_defers_position_with_pending_source_orders() -> None:
    tracked = position()
    repository = FakeRepository(tracked)
    repository.pending.add(("trader", "mint"))
    balances = FakeBalances(0)

    result = await PaperCopyReconciliationService(
        repository,  # type: ignore[arg-type]
        balances,  # type: ignore[arg-type]
        FakeMarketData(),  # type: ignore[arg-type]
    ).reconcile("paper-pool")

    assert result.positions_deferred == 1
    assert balances.calls == []
    assert tracked.quantity == 10


@pytest.mark.asyncio
async def test_reconciliation_does_not_mutate_position_when_rpc_fails() -> None:
    tracked = position()
    repository = FakeRepository(tracked)

    with pytest.raises(RuntimeError, match="RPC unavailable"):
        await PaperCopyReconciliationService(
            repository,  # type: ignore[arg-type]
            FailingBalances(),  # type: ignore[arg-type]
            FakeMarketData(),  # type: ignore[arg-type]
        ).reconcile("paper-pool")

    assert tracked.source_quantity == 100
    assert tracked.quantity == 10
    assert repository.session.orders == []


@pytest.mark.asyncio
async def test_executable_quote_triggers_emergency_stop() -> None:
    tracked = position()
    repository = FakeRepository(tracked)

    result = await PaperCopyReconciliationService(
        repository,  # type: ignore[arg-type]
        FakeBalances(100),  # type: ignore[arg-type]
        FakeMarketData(),  # type: ignore[arg-type]
        LossRouteQuotes(),  # type: ignore[arg-type]
    ).reconcile("paper-pool", refresh_prices=True)

    assert result.risk_exits == 1
    assert tracked.quantity == 0
    assert repository.session.orders[0].status == "filled"
    assert "risk stop" in str(repository.session.orders[0].reason)
