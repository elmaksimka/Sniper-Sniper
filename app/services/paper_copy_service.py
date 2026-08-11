from __future__ import annotations

from datetime import UTC, datetime

from app.core.events import TradeScored
from app.infrastructure.models import (
    PaperCopyOrder,
    PaperCopyPortfolio,
    PaperCopyPosition,
)
from app.repositories.paper_copy_repository import PaperCopyRepository
from app.services.dexscreener_client import DexScreenerClient, TokenMarketQuote


class PaperCopyService:
    """Queue and execute durable delayed paper copies at current market quotes."""

    def __init__(
        self,
        repository: PaperCopyRepository,
        market_data: DexScreenerClient | None = None,
        *,
        quote_retry_seconds: float = 30,
        quote_max_attempts: int = 3,
        source_wallets: tuple[str, ...] = (),
        portfolio_wallet: str = "",
        minimum_source_value_usd: float = 0,
    ) -> None:
        self.repository = repository
        self.market_data = market_data or DexScreenerClient()
        self.quote_retry_seconds = quote_retry_seconds
        self.quote_max_attempts = quote_max_attempts
        self.source_wallets = frozenset(source_wallets)
        self.portfolio_wallet = portfolio_wallet
        self.minimum_source_value_usd = minimum_source_value_usd

    async def enqueue_trade(self, event: TradeScored) -> bool:
        if not event.signature or event.side not in {"buy", "sell"}:
            return False
        if event.sol_change == 0:
            return False
        if self.source_wallets and event.wallet not in self.source_wallets:
            return False
        portfolio_key = self.portfolio_wallet or event.wallet
        portfolio = await self.repository.get_portfolio(portfolio_key)
        if portfolio is None or not portfolio.enabled:
            return False
        transaction_at = event.transaction_at or event.created_at
        if self._aware(transaction_at) < self._aware(portfolio.started_at):
            return False
        return await self.repository.enqueue(
            portfolio=portfolio,
            source_wallet=event.wallet,
            source_signature=event.signature,
            token_address=event.token_address,
            side=event.side,
            source_amount=event.amount,
            source_transaction_at=self._aware(transaction_at),
        )

    async def execute_next(self) -> PaperCopyOrder | None:
        due = await self.repository.next_due()
        if due is None:
            return None
        order, portfolio = due

        position = await self.repository.get_position(
            portfolio.id,
            order.source_wallet,
            order.token_address,
        )
        if order.side == "buy":
            reason = await self._buy_precondition(portfolio, position)
        else:
            reason = None if position is not None else "no copied position to sell"
        if reason:
            await self.repository.finish_skipped(order, portfolio, reason)
            return order

        try:
            quote = await self.market_data.get_token_quote(order.token_address)
        except Exception as error:
            await self.repository.defer_quote(
                order,
                retry_seconds=self.quote_retry_seconds,
                maximum_attempts=self.quote_max_attempts,
                reason=f"quote failed: {type(error).__name__}",
            )
            return order if order.status == "skipped" else None
        if quote is None:
            await self.repository.defer_quote(
                order,
                retry_seconds=self.quote_retry_seconds,
                maximum_attempts=self.quote_max_attempts,
                reason="market quote unavailable",
            )
            return order if order.status == "skipped" else None
        if quote.liquidity_usd < portfolio.minimum_liquidity_usd:
            await self.repository.finish_skipped(
                order,
                portfolio,
                (
                    f"liquidity ${quote.liquidity_usd:,.0f} below "
                    f"${portfolio.minimum_liquidity_usd:,.0f}"
                ),
            )
            return order

        source_value_usd = order.source_amount * quote.price_usd
        if source_value_usd + 1e-9 < self.minimum_source_value_usd:
            await self.repository.finish_skipped(
                order,
                portfolio,
                (
                    f"source trade ${source_value_usd:.4f} below "
                    f"${self.minimum_source_value_usd:.2f}"
                ),
            )
            return order

        if order.side == "buy":
            await self._fill_buy(order, portfolio, position, quote)
        else:
            if position is None:  # pragma: no cover - guarded above
                raise RuntimeError("Paper position disappeared before sell")
            await self._fill_sell(order, portfolio, position, quote)
        return order

    async def _buy_precondition(
        self,
        portfolio: PaperCopyPortfolio,
        position: PaperCopyPosition | None,
    ) -> str | None:
        open_positions = await self.repository.count_open_positions(portfolio.id)
        if position is None and open_positions >= portfolio.max_open_positions:
            return "maximum open positions reached"
        if portfolio.cash_balance_usd + 1e-9 < portfolio.allocation_usd:
            return "insufficient paper cash"
        return None

    async def _fill_buy(
        self,
        order: PaperCopyOrder,
        portfolio: PaperCopyPortfolio,
        position: PaperCopyPosition | None,
        quote: TokenMarketQuote,
    ) -> None:
        execution_price = quote.price_usd * (1 + portfolio.slippage_bps / 10_000)
        source_value_usd = order.source_amount * quote.price_usd
        value = min(
            portfolio.allocation_usd,
            source_value_usd,
            portfolio.cash_balance_usd,
        )
        quantity = value / execution_price
        if position is None:
            position = PaperCopyPosition(
                portfolio_id=portfolio.id,
                source_wallet=order.source_wallet,
                token_address=order.token_address,
                source_quantity=order.source_amount,
                quantity=quantity,
                cost_basis_usd=value,
                entry_price_usd=execution_price,
                last_price_usd=quote.price_usd,
                opened_at=datetime.now(UTC),
            )
            self.repository.session.add(position)
        else:
            position.quantity += quantity
            position.source_quantity += order.source_amount
            position.cost_basis_usd += value
            position.entry_price_usd = position.cost_basis_usd / position.quantity
            position.last_price_usd = quote.price_usd
            position.updated_at = datetime.now(UTC)
        portfolio.cash_balance_usd -= value
        portfolio.updated_at = datetime.now(UTC)
        await self.repository.session.flush()
        await self._finish_fill(
            order,
            portfolio,
            execution_price=execution_price,
            quantity=quantity,
            value=value,
            realized_pnl=None,
            liquidity_usd=quote.liquidity_usd,
        )

    async def _fill_sell(
        self,
        order: PaperCopyOrder,
        portfolio: PaperCopyPortfolio,
        position: PaperCopyPosition,
        quote: TokenMarketQuote,
    ) -> None:
        execution_price = quote.price_usd * (1 - portfolio.slippage_bps / 10_000)
        source_fraction = min(
            1.0,
            order.source_amount / max(position.source_quantity, order.source_amount),
        )
        quantity = position.quantity * source_fraction
        released_cost_basis = position.cost_basis_usd * source_fraction
        value = quantity * execution_price
        realized_pnl = value - released_cost_basis
        position.quantity -= quantity
        position.source_quantity = max(
            0,
            position.source_quantity - order.source_amount,
        )
        position.cost_basis_usd -= released_cost_basis
        if position.quantity <= 1e-12:
            position.quantity = 0
            position.source_quantity = 0
            position.cost_basis_usd = 0
        position.last_price_usd = execution_price
        position.updated_at = datetime.now(UTC)
        portfolio.cash_balance_usd += value
        portfolio.updated_at = datetime.now(UTC)
        await self.repository.session.flush()
        await self._finish_fill(
            order,
            portfolio,
            execution_price=execution_price,
            quantity=quantity,
            value=value,
            realized_pnl=realized_pnl,
            liquidity_usd=quote.liquidity_usd,
        )

    async def _finish_fill(
        self,
        order: PaperCopyOrder,
        portfolio: PaperCopyPortfolio,
        *,
        execution_price: float,
        quantity: float,
        value: float,
        realized_pnl: float | None,
        liquidity_usd: float,
    ) -> None:
        order.status = "filled"
        order.reason = None
        order.execution_price_usd = execution_price
        order.quantity = quantity
        order.value_usd = value
        order.realized_pnl_usd = realized_pnl
        order.liquidity_usd = liquidity_usd
        order.cash_balance_after_usd = portfolio.cash_balance_usd
        order.open_positions_after = await self.repository.count_open_positions(
            portfolio.id
        )
        order.equity_after_usd = await self.repository.equity(portfolio)
        order.executed_at = datetime.now(UTC)
        await self.repository.session.commit()

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
