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
        if self.position is not None and self.position.quantity > 0:
            return self.position
        return None

    async def count_open_positions(self, portfolio_id: int) -> int:
        return int(self.position is not None and self.position.quantity > 0)

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
async def test_maximum_allocation_and_slippage_are_applied_to_round_trip() -> None:
    account = portfolio()
    repository = FakeRepository(account)
    market = FakeMarketData(price_usd=1)
    service = PaperCopyService(
        repository,
        market,  # type: ignore[arg-type]
    )

    buy = order("buy")
    repository.due = buy
    await service.execute_next()

    assert buy.status == "filled"
    assert buy.value_usd == pytest.approx(10)
    assert buy.execution_price_usd == pytest.approx(1.01)
    assert account.cash_balance_usd == pytest.approx(90)
    assert buy.open_positions_after == 1
    assert buy.equity_after_usd == pytest.approx(99.9009901)

    market.price_usd = 2
    sell = order("sell")
    repository.due = sell
    await service.execute_next()

    expected_proceeds = (10 / 1.01) * 1.98
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
    buy = order("buy")
    buy.source_amount = 0.01
    repository.due = buy

    await service.execute_next()

    assert buy.status == "filled"
    assert buy.value_usd == pytest.approx(0.01)
    assert account.cash_balance_usd == pytest.approx(99.99)


@pytest.mark.asyncio
async def test_repeated_buy_is_added_to_the_same_source_position() -> None:
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
    )

    await service.execute_next()

    assert repeated.status == "filled"
    assert repository.position.quantity == pytest.approx(10 + 10 / 1.01)
    assert repository.position.source_quantity == pytest.approx(200)
    assert account.cash_balance_usd == pytest.approx(90)


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
    )

    assert "звіт за 30 хв" in message
    assert "Входи: 1 на $10.00" in message
    assert "Виходи: 1 на $12.00" in message
    assert "Монет у звіті: 2" in message
    assert "Реалізований PnL: +$2.00" in message
    assert "Пропущено сигналів: 1" in message
    assert "Відкритих позицій: 9" in message
    assert "https://dexscreener.com/solana/buy-token" in message
    assert "https://solscan.io/tx/signature-sell" in message
