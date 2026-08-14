from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.core.events import TradeScored
from app.infrastructure.models import (
    PaperCopyOrder,
    PaperCopyPortfolio,
    PaperCopyPosition,
)
from app.repositories.paper_copy_repository import PaperCopyRepository
from app.services.dexscreener_client import DexScreenerClient, TokenMarketQuote
from app.services.jupiter_quote_client import JupiterQuoteClient, SwapRouteQuote


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
        maximum_trade_age_seconds: float = 30,
        maximum_source_exposure_pct: float = 10,
        maximum_token_exposure_pct: float = 100,
        maximum_buys_per_position: int = 3,
        allow_averaging_down: bool = False,
        maximum_price_impact_pct: float = 1,
        strategy_version: str = "route-risk-v2",
        route_quotes: JupiterQuoteClient | None = None,
    ) -> None:
        self.repository = repository
        self.market_data = market_data or DexScreenerClient()
        self.quote_retry_seconds = quote_retry_seconds
        self.quote_max_attempts = quote_max_attempts
        self.source_wallets = frozenset(source_wallets)
        self.portfolio_wallet = portfolio_wallet
        self.minimum_source_value_usd = minimum_source_value_usd
        self.maximum_trade_age = timedelta(seconds=maximum_trade_age_seconds)
        self.maximum_source_exposure_pct = maximum_source_exposure_pct
        self.maximum_token_exposure_pct = maximum_token_exposure_pct
        self.maximum_buys_per_position = maximum_buys_per_position
        self.allow_averaging_down = allow_averaging_down
        self.maximum_price_impact_pct = maximum_price_impact_pct
        self.strategy_version = strategy_version
        settings = get_settings()
        self.route_quotes = route_quotes or JupiterQuoteClient(
            api_key=settings.jupiter_api_key,
            timeout_seconds=settings.jupiter_timeout_seconds,
        )

    async def enqueue_trade(self, event: TradeScored) -> bool:
        if not event.signature or event.side not in {"buy", "sell"}:
            return False
        if event.sol_change == 0:
            return False
        if self.portfolio_wallet and event.wallet not in self.source_wallets:
            return False
        portfolio_key = self.portfolio_wallet or event.wallet
        portfolio = await self.repository.get_portfolio(portfolio_key)
        if portfolio is None or not portfolio.enabled:
            return False
        transaction_at = event.transaction_at or event.created_at
        transaction_at = self._aware(transaction_at)
        if transaction_at < self._aware(portfolio.started_at):
            return False
        if (
            event.side == "buy"
            and datetime.now(UTC) - transaction_at > self.maximum_trade_age
        ):
            return False
        return await self.repository.enqueue(
            portfolio=portfolio,
            source_wallet=event.wallet,
            source_signature=event.signature,
            token_address=event.token_address,
            side=event.side,
            source_amount=event.amount,
            source_transaction_at=transaction_at,
            strategy_version=self.strategy_version,
        )

    async def execute_next(self) -> PaperCopyOrder | None:
        due = await self.repository.next_due()
        if due is None:
            return None
        order, portfolio = due

        if order.side == "buy" and self._trade_age(order) > self.maximum_trade_age:
            age_seconds = self._trade_age(order).total_seconds()
            await self.repository.finish_skipped(
                order,
                portfolio,
                (
                    f"signal expired before execution ({age_seconds:.1f}s > "
                    f"{self.maximum_trade_age.total_seconds():.1f}s)"
                ),
            )
            return order

        position = await self.repository.get_position(
            portfolio.id,
            order.source_wallet,
            order.token_address,
        )
        if order.side == "buy":
            reason = await self._buy_precondition(portfolio, position)
        else:
            reason = (
                None
                if position is not None and position.quantity > 0
                else "no copied position to sell"
            )
        if reason:
            await self.repository.finish_skipped(order, portfolio, reason)
            return order

        if order.side == "buy":
            quote = await self._market_quote(order)
            if quote is None:
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
            if (
                position is not None
                and position.quantity > 0
                and not self.allow_averaging_down
                and quote.price_usd + 1e-12
                < (position.first_entry_price_usd or position.entry_price_usd)
            ):
                await self.repository.finish_skipped(
                    order,
                    portfolio,
                    "averaging down is disabled",
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
            value = min(
                portfolio.allocation_usd,
                source_value_usd,
                portfolio.cash_balance_usd,
            )
            exposure_reason = await self._source_exposure_precondition(
                portfolio,
                order.source_wallet,
                value,
            )
            if exposure_reason:
                await self.repository.finish_skipped(
                    order,
                    portfolio,
                    exposure_reason,
                )
                return order
            token_exposure_reason = await self._token_exposure_precondition(
                portfolio,
                order.token_address,
                value,
            )
            if token_exposure_reason:
                await self.repository.finish_skipped(
                    order,
                    portfolio,
                    token_exposure_reason,
                )
                return order
            route = await self._buy_route(order, value)
            if route is None:
                return order if order.status == "skipped" else None
            if route.price_impact_pct > self.maximum_price_impact_pct:
                await self.repository.finish_skipped(
                    order,
                    portfolio,
                    (
                        f"price impact {route.price_impact_pct:.2f}% above "
                        f"{self.maximum_price_impact_pct:.2f}%"
                    ),
                )
                return order
            await self._fill_buy(order, portfolio, position, quote, route)
        else:
            if position is None:  # pragma: no cover - guarded above
                raise RuntimeError("Paper position disappeared before sell")
            source_fraction = min(
                1.0,
                order.source_amount
                / max(position.source_quantity, order.source_amount),
            )
            route = await self._sell_route(
                order,
                position.quantity * source_fraction,
            )
            if route is None:
                return order if order.status == "skipped" else None
            quote = await self._optional_market_quote(order.token_address)
            await self._fill_sell(order, portfolio, position, quote, route)
        return order

    async def _market_quote(
        self,
        order: PaperCopyOrder,
    ) -> TokenMarketQuote | None:
        try:
            quote = await self.market_data.get_token_quote(order.token_address)
        except Exception as error:
            await self._defer(order, f"market quote failed: {type(error).__name__}")
            return None
        if quote is None:
            await self._defer(order, "market quote unavailable")
            return None
        return quote

    async def _optional_market_quote(
        self,
        token_address: str,
    ) -> TokenMarketQuote | None:
        try:
            return await self.market_data.get_token_quote(token_address)
        except Exception:
            return None

    async def _buy_route(
        self,
        order: PaperCopyOrder,
        value_usd: float,
    ) -> SwapRouteQuote | None:
        decimals = await self.repository.get_token_decimals(order.token_address)
        if decimals is None:
            await self._defer(order, "token decimals unavailable")
            return None
        try:
            route = await self.route_quotes.get_buy_quote(
                order.token_address,
                value_usd,
                decimals,
            )
        except Exception as error:
            await self._defer(order, f"route quote failed: {type(error).__name__}")
            return None
        if route is None:
            await self._defer(order, "swap route unavailable")
        return route

    async def _sell_route(
        self,
        order: PaperCopyOrder,
        quantity: float,
    ) -> SwapRouteQuote | None:
        decimals = await self.repository.get_token_decimals(order.token_address)
        if decimals is None:
            await self._defer(order, "token decimals unavailable")
            return None
        try:
            route = await self.route_quotes.get_sell_quote(
                order.token_address,
                quantity,
                decimals,
            )
        except Exception as error:
            await self._defer(order, f"route quote failed: {type(error).__name__}")
            return None
        if route is None:
            await self._defer(order, "swap route unavailable")
        return route

    async def _defer(self, order: PaperCopyOrder, reason: str) -> None:
        await self.repository.defer_quote(
            order,
            retry_seconds=self.quote_retry_seconds,
            maximum_attempts=self.quote_max_attempts,
            reason=reason,
        )

    async def _buy_precondition(
        self,
        portfolio: PaperCopyPortfolio,
        position: PaperCopyPosition | None,
    ) -> str | None:
        open_positions = await self.repository.count_open_positions(portfolio.id)
        if (
            (position is None or position.quantity <= 0)
            and open_positions >= portfolio.max_open_positions
        ):
            return "maximum open positions reached"
        if portfolio.cash_balance_usd + 1e-9 < portfolio.allocation_usd:
            return "insufficient paper cash"
        if (
            position is not None
            and position.quantity > 0
            and (position.buy_count or 0) >= self.maximum_buys_per_position
        ):
            return f"maximum {self.maximum_buys_per_position} buys per position reached"
        return None

    async def _source_exposure_precondition(
        self,
        portfolio: PaperCopyPortfolio,
        source_wallet: str,
        value_usd: float,
    ) -> str | None:
        equity = await self.repository.equity(portfolio)
        maximum = equity * self.maximum_source_exposure_pct / 100
        current = await self.repository.source_cost_basis(
            portfolio.id,
            source_wallet,
        )
        if current + value_usd > maximum + 1e-9:
            return (
                f"source exposure ${current + value_usd:.2f} above "
                f"{self.maximum_source_exposure_pct:.1f}% portfolio cap "
                f"(${maximum:.2f})"
            )
        return None

    async def _token_exposure_precondition(
        self,
        portfolio: PaperCopyPortfolio,
        token_address: str,
        value_usd: float,
    ) -> str | None:
        equity = await self.repository.equity(portfolio)
        maximum = equity * self.maximum_token_exposure_pct / 100
        current = await self.repository.token_cost_basis(portfolio.id, token_address)
        if current + value_usd > maximum + 1e-9:
            return (
                f"token exposure ${current + value_usd:.2f} above "
                f"{self.maximum_token_exposure_pct:.1f}% portfolio cap "
                f"(${maximum:.2f})"
            )
        return None

    async def _fill_buy(
        self,
        order: PaperCopyOrder,
        portfolio: PaperCopyPortfolio,
        position: PaperCopyPosition | None,
        quote: TokenMarketQuote,
        route: SwapRouteQuote,
    ) -> None:
        value = route.input_amount
        quantity = route.output_amount
        execution_price = value / quantity
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
                first_entry_price_usd=execution_price,
                buy_count=1,
                maximum_roi_pct=0,
                minimum_roi_pct=0,
                strategy_version=self.strategy_version,
                opened_at=datetime.now(UTC),
            )
            self.repository.session.add(position)
        else:
            if position.quantity <= 0:
                position.source_quantity = 0
                position.quantity = 0
                position.cost_basis_usd = 0
                position.opened_at = datetime.now(UTC)
                position.first_entry_price_usd = execution_price
                position.buy_count = 0
                position.maximum_roi_pct = 0
                position.minimum_roi_pct = 0
                position.strategy_version = self.strategy_version
            position.quantity += quantity
            position.source_quantity += order.source_amount
            position.cost_basis_usd += value
            position.entry_price_usd = position.cost_basis_usd / position.quantity
            position.last_price_usd = quote.price_usd
            position.buy_count = (position.buy_count or 0) + 1
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
            route=route,
        )

    async def _fill_sell(
        self,
        order: PaperCopyOrder,
        portfolio: PaperCopyPortfolio,
        position: PaperCopyPosition,
        quote: TokenMarketQuote | None,
        route: SwapRouteQuote,
    ) -> None:
        quantity = min(position.quantity, route.input_amount)
        position_fraction = min(1.0, quantity / position.quantity)
        if position_fraction >= 1 - 1e-9:
            quantity = position.quantity
            position_fraction = 1.0
        released_cost_basis = position.cost_basis_usd * position_fraction
        value = route.output_amount
        execution_price = value / quantity
        realized_pnl = value - released_cost_basis
        position.quantity -= quantity
        position.source_quantity *= 1 - position_fraction
        position.cost_basis_usd -= released_cost_basis
        if position.quantity <= 1e-12:
            position.quantity = 0
            position.source_quantity = 0
            position.cost_basis_usd = 0
        position.last_price_usd = quote.price_usd if quote is not None else execution_price
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
            liquidity_usd=quote.liquidity_usd if quote is not None else 0,
            route=route,
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
        route: SwapRouteQuote,
    ) -> None:
        order.status = "filled"
        order.execution_price_usd = execution_price
        order.quantity = quantity
        order.value_usd = value
        order.realized_pnl_usd = realized_pnl
        order.liquidity_usd = liquidity_usd
        order.price_impact_pct = route.price_impact_pct
        order.route_fee_bps = route.fee_bps
        order.route_provider = route.router[:32] or None
        order.route_path = route.route[:512] or None
        order.strategy_version = self.strategy_version
        order.cash_balance_after_usd = portfolio.cash_balance_usd
        order.open_positions_after = await self.repository.count_open_positions(
            portfolio.id
        )
        order.equity_after_usd = await self.repository.equity(portfolio)
        order.executed_at = datetime.now(UTC)
        await self.repository.session.commit()

    def _trade_age(self, order: PaperCopyOrder) -> timedelta:
        return datetime.now(UTC) - self._aware(order.source_transaction_at)

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
