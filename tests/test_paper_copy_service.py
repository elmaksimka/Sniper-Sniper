from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.core.events import TradeScored
from app.infrastructure.models import (
    PaperCopyOrder,
    PaperCopyPortfolio,
    PaperCopyPosition,
)
from app.services.dexscreener_client import TokenMarketQuote
from app.services.jupiter_quote_client import SwapRouteQuote, USDC_MINT
from app.services.paper_copy_service import PaperCopyService


class FakeSession:
    def __init__(self, repository: "FakeRepository") -> None:
        self.repository = repository

    def add(self, item: Any) -> None:
        if isinstance(item, PaperCopyPosition):
            self.repository.position = item

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None


class FakeMarketData:
    def __init__(self, price_usd: float = 1, liquidity_usd: float = 50_000) -> None:
        self.price_usd = price_usd
        self.liquidity_usd = liquidity_usd

    async def get_token_quote(self, token_address: str) -> TokenMarketQuote:
        return TokenMarketQuote(
            price_usd=self.price_usd,
            pair_url=None,
            liquidity_usd=self.liquidity_usd,
        )


class FakeRouteQuotes:
    def __init__(
        self,
        market: FakeMarketData,
        *,
        output_factor: float = 1,
        price_impact_pct: float = 0.1,
        fee_bps: int = 10,
    ) -> None:
        self.market = market
        self.output_factor = output_factor
        self.price_impact_pct = price_impact_pct
        self.fee_bps = fee_bps

    async def get_buy_quote(
        self, token_address: str, usd_amount: float, token_decimals: int
    ) -> SwapRouteQuote:
        return SwapRouteQuote(
            input_mint=USDC_MINT,
            output_mint=token_address,
            input_amount=usd_amount,
            output_amount=(
                usd_amount / self.market.price_usd * self.output_factor
            ),
            price_impact_pct=self.price_impact_pct,
            fee_bps=self.fee_bps,
            router="metis",
            route="Raydium -> Meteora",
        )

    async def get_sell_quote(
        self, token_address: str, token_amount: float, token_decimals: int
    ) -> SwapRouteQuote:
        return SwapRouteQuote(
            input_mint=token_address,
            output_mint=USDC_MINT,
            input_amount=token_amount,
            output_amount=(
                token_amount * self.market.price_usd * self.output_factor
            ),
            price_impact_pct=self.price_impact_pct,
            fee_bps=self.fee_bps,
            router="metis",
            route="Meteora",
        )


class FakeRepository:
    def __init__(self, portfolio: PaperCopyPortfolio) -> None:
        self.portfolio = portfolio
        self.position: PaperCopyPosition | None = None
        self.due: PaperCopyOrder | None = None
        self.enqueued = False
        self.enqueue_kwargs: dict[str, Any] = {}
        self.session = FakeSession(self)

    async def get_portfolio(self, source_wallet: str) -> PaperCopyPortfolio | None:
        return self.portfolio if source_wallet == self.portfolio.source_wallet else None

    async def enqueue(self, **kwargs: Any) -> bool:
        self.enqueued = True
        self.enqueue_kwargs = kwargs
        return True

    async def next_due(self) -> tuple[PaperCopyOrder, PaperCopyPortfolio] | None:
        return (self.due, self.portfolio) if self.due is not None else None

    async def get_position(
        self, portfolio_id: int, source_wallet: str, token_address: str
    ) -> PaperCopyPosition | None:
        return self.position

    async def count_open_positions(self, portfolio_id: int) -> int:
        return int(self.position is not None and self.position.quantity > 0)

    async def source_cost_basis(self, portfolio_id: int, source_wallet: str) -> float:
        if self.position is None or self.position.quantity <= 0:
            return 0
        return (
            self.position.cost_basis_usd
            if self.position.source_wallet == source_wallet
            else 0
        )

    async def token_cost_basis(self, portfolio_id: int, token_address: str) -> float:
        if self.position is None or self.position.quantity <= 0:
            return 0
        return (
            self.position.cost_basis_usd
            if self.position.token_address == token_address
            else 0
        )

    async def get_token_decimals(self, token_address: str) -> int:
        return 6

    async def equity(self, portfolio: PaperCopyPortfolio) -> float:
        position_value = 0.0
        if self.position is not None and self.position.quantity > 0:
            position_value = self.position.quantity * self.position.last_price_usd
        return portfolio.cash_balance_usd + position_value

    async def finish_skipped(
        self,
        order: PaperCopyOrder,
        portfolio: PaperCopyPortfolio,
        reason: str,
    ) -> None:
        order.status = "skipped"
        order.reason = reason
        order.cash_balance_after_usd = portfolio.cash_balance_usd
        order.equity_after_usd = await self.equity(portfolio)
        order.open_positions_after = await self.count_open_positions(portfolio.id)
        order.executed_at = datetime.now(UTC)

    async def defer_quote(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("quote should be available")


def portfolio() -> PaperCopyPortfolio:
    return PaperCopyPortfolio(
        id=1,
        source_wallet="source-wallet",
        initial_balance_usd=100,
        cash_balance_usd=100,
        allocation_usd=10,
        max_open_positions=5,
        reaction_delay_seconds=20,
        slippage_bps=100,
        minimum_liquidity_usd=15_000,
        enabled=True,
        started_at=datetime.now(UTC),
    )


def order(side: str) -> PaperCopyOrder:
    now = datetime.now(UTC)
    return PaperCopyOrder(
        id=1,
        portfolio_id=1,
        source_wallet="source-wallet",
        source_signature=f"signature-{side}",
        token_address="token-address",
        side=side,
        source_amount=100,
        source_transaction_at=now,
        execute_after=now,
        status="pending",
        attempts=0,
        notification_sent=False,
    )


@pytest.mark.asyncio
async def test_only_new_source_trades_are_queued() -> None:
    account = portfolio()
    repository = FakeRepository(account)
    service = PaperCopyService(repository)  # type: ignore[arg-type]

    transfer = TradeScored(
        wallet=account.source_wallet,
        token_address="token",
        side="buy",
        amount=100_000,
        sol_change=0,
        signature="transfer",
        transaction_at=account.started_at + timedelta(seconds=1),
    )
    assert await service.enqueue_trade(transfer) is False

    historical = TradeScored(
        wallet=account.source_wallet,
        token_address="token",
        side="buy",
        amount=1,
        sol_change=-1,
        signature="old",
        transaction_at=account.started_at - timedelta(seconds=1),
    )
    assert await service.enqueue_trade(historical) is False

    current = TradeScored(
        wallet=account.source_wallet,
        token_address="token",
        side="buy",
        amount=1,
        sol_change=-1,
        signature="new",
        transaction_at=account.started_at + timedelta(seconds=1),
    )
    assert await service.enqueue_trade(current) is True
    assert repository.enqueued is True


@pytest.mark.asyncio
async def test_stale_trade_after_downtime_is_not_queued() -> None:
    account = portfolio()
    account.started_at = datetime.now(UTC) - timedelta(days=1)
    repository = FakeRepository(account)
    service = PaperCopyService(
        repository,  # type: ignore[arg-type]
        maximum_trade_age_seconds=300,
    )
    stale = TradeScored(
        wallet=account.source_wallet,
        token_address="token",
        side="buy",
        amount=1,
        sol_change=-1,
        signature="stale-after-downtime",
        transaction_at=datetime.now(UTC) - timedelta(hours=1),
    )

    assert await service.enqueue_trade(stale) is False
    assert repository.enqueued is False


@pytest.mark.asyncio
async def test_stale_buy_already_in_queue_is_skipped_before_quotes() -> None:
    account = portfolio()
    repository = FakeRepository(account)
    stale = order("buy")
    stale.source_transaction_at = datetime.now(UTC) - timedelta(seconds=31)
    repository.due = stale

    result = await PaperCopyService(
        repository,  # type: ignore[arg-type]
        maximum_trade_age_seconds=30,
    ).execute_next()

    assert result is stale
    assert stale.status == "skipped"
    assert stale.reason is not None
    assert "signal expired before execution" in stale.reason


@pytest.mark.asyncio
async def test_stale_sell_is_still_queued_for_risk_reduction() -> None:
    account = portfolio()
    account.started_at = datetime.now(UTC) - timedelta(days=1)
    repository = FakeRepository(account)
    service = PaperCopyService(
        repository,  # type: ignore[arg-type]
        maximum_trade_age_seconds=30,
    )
    stale_sell = TradeScored(
        wallet=account.source_wallet,
        token_address="token",
        side="sell",
        amount=1,
        sol_change=1,
        signature="stale-sell",
        transaction_at=datetime.now(UTC) - timedelta(hours=1),
    )

    assert await service.enqueue_trade(stale_sell) is True


@pytest.mark.asyncio
async def test_buy_above_maximum_route_price_impact_is_skipped() -> None:
    account = portfolio()
    repository = FakeRepository(account)
    market = FakeMarketData()
    buy = order("buy")
    repository.due = buy

    await PaperCopyService(
        repository,  # type: ignore[arg-type]
        market,  # type: ignore[arg-type]
        route_quotes=FakeRouteQuotes(  # type: ignore[arg-type]
            market,
            price_impact_pct=1.01,
        ),
        maximum_price_impact_pct=1,
    ).execute_next()

    assert buy.status == "skipped"
    assert buy.reason == "price impact 1.01% above 1.00%"


@pytest.mark.asyncio
async def test_route_output_includes_price_impact_and_fees_in_round_trip() -> None:
    account = portfolio()
    repository = FakeRepository(account)
    market = FakeMarketData(price_usd=1)
    service = PaperCopyService(
        repository,
        market,  # type: ignore[arg-type]
        route_quotes=FakeRouteQuotes(market, output_factor=0.99),  # type: ignore[arg-type]
    )

    buy = order("buy")
    repository.due = buy
    await service.execute_next()

    assert buy.status == "filled"
    assert buy.value_usd == pytest.approx(10)
    assert buy.execution_price_usd == pytest.approx(1 / 0.99)
    assert buy.price_impact_pct == pytest.approx(0.1)
    assert buy.route_fee_bps == 10
    assert buy.route_provider == "metis"
    assert account.cash_balance_usd == pytest.approx(90)
    assert buy.open_positions_after == 1
    assert buy.equity_after_usd == pytest.approx(99.9)

    market.price_usd = 2
    sell = order("sell")
    repository.due = sell
    await service.execute_next()

    expected_proceeds = 9.9 * 2 * 0.99
    assert sell.status == "filled"
    assert sell.value_usd == pytest.approx(expected_proceeds)
    assert sell.realized_pnl_usd == pytest.approx(expected_proceeds - 10)
    assert account.cash_balance_usd == pytest.approx(90 + expected_proceeds)
    assert sell.open_positions_after == 0


@pytest.mark.asyncio
async def test_small_source_buy_is_not_scaled_up_to_maximum_allocation() -> None:
    account = portfolio()
    account.allocation_usd = 1
    repository = FakeRepository(account)
    market = FakeMarketData(price_usd=1)
    service = PaperCopyService(repository, market)  # type: ignore[arg-type]
    service.route_quotes = FakeRouteQuotes(market)  # type: ignore[assignment]
    buy = order("buy")
    buy.source_amount = 0.01
    repository.due = buy

    await service.execute_next()

    assert buy.status == "filled"
    assert buy.value_usd == pytest.approx(0.01)
    assert account.cash_balance_usd == pytest.approx(99.99)


@pytest.mark.asyncio
async def test_source_wallet_cannot_exceed_ten_percent_of_equity() -> None:
    account = portfolio()
    repository = FakeRepository(account)
    repository.position = PaperCopyPosition(
        portfolio_id=1,
        source_wallet=account.source_wallet,
        token_address="token-address",
        source_quantity=100,
        quantity=10,
        cost_basis_usd=10,
        entry_price_usd=1,
        last_price_usd=1,
        opened_at=datetime.now(UTC),
    )
    repeated = order("buy")
    repository.due = repeated
    service = PaperCopyService(
        repository,
        FakeMarketData(),  # type: ignore[arg-type]
        route_quotes=FakeRouteQuotes(FakeMarketData()),  # type: ignore[arg-type]
    )

    await service.execute_next()

    assert repeated.status == "skipped"
    assert repeated.reason is not None
    assert "10.0% portfolio cap" in repeated.reason
    assert repository.position.quantity == pytest.approx(10)
    assert account.cash_balance_usd == pytest.approx(100)


@pytest.mark.asyncio
async def test_buy_reopens_existing_closed_position_instead_of_inserting_duplicate() -> None:
    account = portfolio()
    repository = FakeRepository(account)
    closed = PaperCopyPosition(
        portfolio_id=1,
        source_wallet=account.source_wallet,
        token_address="token-address",
        source_quantity=0,
        quantity=0,
        cost_basis_usd=0,
        entry_price_usd=1,
        last_price_usd=1,
        opened_at=datetime(2025, 1, 1, tzinfo=UTC),
    )
    repository.position = closed
    reopened = order("buy")
    repository.due = reopened

    market = FakeMarketData()
    await PaperCopyService(
        repository,
        market,  # type: ignore[arg-type]
        route_quotes=FakeRouteQuotes(market),  # type: ignore[arg-type]
    ).execute_next()

    assert repository.position is closed
    assert closed.quantity == pytest.approx(10)
    assert closed.source_quantity == pytest.approx(100)
    assert closed.opened_at > datetime(2025, 1, 1, tzinfo=UTC)
    assert reopened.status == "filled"


@pytest.mark.asyncio
async def test_allowed_source_is_attributed_to_shared_portfolio() -> None:
    account = portfolio()
    account.source_wallet = "shared-pool"
    repository = FakeRepository(account)
    service = PaperCopyService(
        repository,  # type: ignore[arg-type]
        source_wallets=("trader-one", "trader-two"),
        portfolio_wallet="shared-pool",
    )
    event = TradeScored(
        wallet="trader-two",
        token_address="token",
        side="buy",
        amount=2,
        sol_change=-1,
        signature="shared-signal",
        transaction_at=account.started_at + timedelta(seconds=1),
    )

    assert await service.enqueue_trade(event) is True
    assert repository.enqueue_kwargs["source_wallet"] == "trader-two"


@pytest.mark.asyncio
async def test_shared_portfolio_with_no_eligible_sources_rejects_every_trade() -> None:
    account = portfolio()
    account.source_wallet = "shared-pool"
    repository = FakeRepository(account)
    service = PaperCopyService(
        repository,  # type: ignore[arg-type]
        source_wallets=(),
        portfolio_wallet="shared-pool",
    )
    event = TradeScored(
        wallet="unapproved-trader",
        token_address="token",
        side="buy",
        amount=2,
        sol_change=-1,
        signature="blocked-signal",
        transaction_at=account.started_at + timedelta(seconds=1),
    )

    assert await service.enqueue_trade(event) is False


@pytest.mark.asyncio
async def test_small_source_trade_is_skipped() -> None:
    account = portfolio()
    account.allocation_usd = 1
    repository = FakeRepository(account)
    buy = order("buy")
    buy.source_amount = 0.25
    repository.due = buy
    service = PaperCopyService(
        repository,  # type: ignore[arg-type]
        FakeMarketData(price_usd=1),
        minimum_source_value_usd=1,
        route_quotes=FakeRouteQuotes(FakeMarketData()),  # type: ignore[arg-type]
    )

    await service.execute_next()

    assert buy.status == "skipped"
    assert buy.reason == "source trade $0.2500 below $1.00"
    assert account.cash_balance_usd == 100


def test_paper_copy_telegram_message_contains_execution_and_balance() -> None:
    from app.notifications.telegram import TelegramNotifier

    account = portfolio()
    filled = order("sell")
    filled.status = "filled"
    filled.execution_price_usd = 0.25
    filled.value_usd = 12
    filled.quantity = 48
    filled.realized_pnl_usd = 2
    filled.liquidity_usd = 25_000
    filled.cash_balance_after_usd = 102
    filled.equity_after_usd = 102
    filled.open_positions_after = 0
    filled.executed_at = filled.source_transaction_at + timedelta(seconds=47)

    message = TelegramNotifier.format_paper_copy_order(filled, account)

    assert "PAPER COPY — ПРОДАЖ" in message
    assert "Загальна затримка: 47 с" in message
    assert "Результат позиції: $+2.00" in message
    assert "Paper-баланс: $102.00" in message


def test_paper_copy_message_labels_missing_liquidity_as_unavailable() -> None:
    from app.notifications.telegram import TelegramNotifier

    account = portfolio()
    filled = order("buy")
    filled.status = "filled"
    filled.execution_price_usd = 0.00001
    filled.value_usd = 10
    filled.quantity = 1_000_000
    filled.liquidity_usd = 0
    filled.cash_balance_after_usd = 90
    filled.equity_after_usd = 99.9
    filled.open_positions_after = 1
    filled.executed_at = filled.source_transaction_at + timedelta(seconds=30)

    message = TelegramNotifier.format_paper_copy_order(filled, account)

    assert "Ліквідність: н/д (Pump.fun bonding curve)" in message
    assert "Ліквідність: $0" not in message


def test_paper_copy_summary_aggregates_orders_and_includes_links() -> None:
    from app.notifications.telegram import TelegramNotifier

    account = portfolio()
    account.cash_balance_usd = 91
    buy = order("buy")
    buy.status = "filled"
    buy.value_usd = 10
    buy.token_address = "buy-token"
    sell = order("sell")
    sell.status = "filled"
    sell.value_usd = 12
    sell.realized_pnl_usd = 2
    sell.token_address = "sell-token"
    skipped = order("buy")
    skipped.status = "skipped"
    skipped.token_address = "skipped-token"

    message = TelegramNotifier.format_paper_copy_summary(
        [buy, sell, skipped],
        account,
        open_positions=9,
        trader_count=9,
    )

    assert "звіт за 30 хв" in message
    assert "Пул: 9 трейдерів A/A" in message
    assert "Входи: 1 на $10.00" in message
    assert "Виходи: 1 на $12.00" in message
    assert "Монет у звіті: 2" in message
    assert "Реалізований PnL: +$2.00" in message
    assert "Пропущено сигналів: 1" in message
    assert "Відкритих позицій: 9" in message
    assert "https://dexscreener.com/solana/buy-token" in message
    assert "https://solscan.io/tx/signature-sell" in message


@pytest.mark.asyncio
async def test_global_token_exposure_cap_applies_across_sources() -> None:
    account = portfolio()
    repository = FakeRepository(account)
    market = FakeMarketData()
    buy = order("buy")
    repository.due = buy

    await PaperCopyService(
        repository,
        market,  # type: ignore[arg-type]
        route_quotes=FakeRouteQuotes(market),  # type: ignore[arg-type]
        maximum_token_exposure_pct=3,
    ).execute_next()

    assert buy.status == "skipped"
    assert "token exposure" in str(buy.reason)


@pytest.mark.asyncio
async def test_repeated_buy_is_rejected_after_three_entries() -> None:
    account = portfolio()
    repository = FakeRepository(account)
    repository.position = PaperCopyPosition(
        portfolio_id=1,
        source_wallet=account.source_wallet,
        token_address="token-address",
        source_quantity=3,
        quantity=3,
        cost_basis_usd=3,
        entry_price_usd=1,
        last_price_usd=1,
        first_entry_price_usd=1,
        buy_count=3,
        opened_at=datetime.now(UTC),
    )
    buy = order("buy")
    repository.due = buy

    await PaperCopyService(repository, FakeMarketData()).execute_next()  # type: ignore[arg-type]

    assert buy.status == "skipped"
    assert buy.reason == "maximum 3 buys per position reached"


@pytest.mark.asyncio
async def test_averaging_down_is_rejected() -> None:
    account = portfolio()
    repository = FakeRepository(account)
    repository.position = PaperCopyPosition(
        portfolio_id=1,
        source_wallet=account.source_wallet,
        token_address="token-address",
        source_quantity=1,
        quantity=1,
        cost_basis_usd=2,
        entry_price_usd=2,
        last_price_usd=2,
        first_entry_price_usd=2,
        buy_count=1,
        opened_at=datetime.now(UTC),
    )
    buy = order("buy")
    repository.due = buy

    await PaperCopyService(repository, FakeMarketData(price_usd=1)).execute_next()  # type: ignore[arg-type]

    assert buy.status == "skipped"
    assert buy.reason == "averaging down is disabled"


def test_empty_paper_copy_summary_is_still_reportable() -> None:
    from app.notifications.telegram import TelegramNotifier

    message = TelegramNotifier.format_paper_copy_summary(
        [],
        portfolio(),
        open_positions=0,
        trader_count=9,
    )

    assert "Пул: 9 трейдерів A/A" in message
    assert "Входи: 0 на $0.00" in message
    assert "Виходи: 0 на $0.00" in message
    assert "Відкритих позицій: 0" in message
