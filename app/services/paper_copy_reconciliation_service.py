from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256

from app.infrastructure.models import (
    PaperCopyOrder,
    PaperCopyPortfolio,
    PaperCopyPosition,
)
from app.listeners.helius_client import HeliusClient
from app.repositories.paper_copy_repository import PaperCopyRepository
from app.services.dexscreener_client import DexScreenerClient, TokenMarketQuote
from app.services.jupiter_quote_client import JupiterQuoteClient, SwapRouteQuote
from app.services.paper_copy_service import PaperCopyService


@dataclass(frozen=True, slots=True)
class PaperCopyReconciliationResult:
    wallets_checked: int = 0
    positions_checked: int = 0
    positions_reduced: int = 0
    positions_closed: int = 0
    positions_increased: int = 0
    positions_deferred: int = 0
    positions_repriced: int = 0
    prices_deferred: int = 0
    risk_exits: int = 0


class PaperCopyReconciliationService:
    """Align paper-copy source positions with confirmed on-chain balances."""

    def __init__(
        self,
        repository: PaperCopyRepository,
        balances: HeliusClient,
        market_data: DexScreenerClient | None = None,
        route_quotes: JupiterQuoteClient | None = None,
        stop_loss_pct: float = 30,
        break_even_activation_pct: float = 50,
        trailing_activation_pct: float = 100,
        trailing_drawdown_pct: float = 25,
        strategy_version: str = "route-risk-v2",
    ) -> None:
        self.repository = repository
        self.balances = balances
        self.market_data = market_data or DexScreenerClient()
        self.paper_copy = PaperCopyService(
            repository,
            self.market_data,
            route_quotes=route_quotes,
            strategy_version=strategy_version,
        )
        self.stop_loss_pct = stop_loss_pct
        self.break_even_activation_pct = break_even_activation_pct
        self.trailing_activation_pct = trailing_activation_pct
        self.trailing_drawdown_pct = trailing_drawdown_pct

    async def reconcile(
        self,
        portfolio_wallet: str,
        *,
        refresh_prices: bool = False,
    ) -> PaperCopyReconciliationResult:
        portfolio = await self.repository.get_portfolio(portfolio_wallet)
        if portfolio is None or not portfolio.enabled:
            return PaperCopyReconciliationResult()

        positions = await self.repository.list_open_positions(portfolio.id)
        pending = await self.repository.pending_position_keys(portfolio.id)
        by_wallet: dict[str, list[PaperCopyPosition]] = {}
        deferred = 0
        for position in positions:
            key = (position.source_wallet, position.token_address)
            if key in pending:
                deferred += 1
                continue
            by_wallet.setdefault(position.source_wallet, []).append(position)

        reduced = closed = increased = checked = repriced = prices_deferred = 0
        risk_exits = 0
        for wallet, wallet_positions in by_wallet.items():
            current = await self.balances.get_token_balances(wallet)
            for position in wallet_positions:
                checked += 1
                actual = max(0.0, current.get(position.token_address, 0.0))
                tracked = max(0.0, position.source_quantity)
                tolerance = max(1e-9, tracked * 1e-9)
                quote = None
                if actual < tracked - tolerance:
                    quote = await self._get_market_quote(position.token_address)
                if actual > tracked + tolerance:
                    position.source_quantity = actual
                    position.updated_at = datetime.now(UTC)
                    increased += 1
                elif actual < tracked - tolerance:
                    filled = await self._reduce_position(
                        position,
                        portfolio,
                        actual,
                        quote,
                    )
                    if filled:
                        reduced += 1
                        if actual <= tolerance:
                            closed += 1
                    else:
                        deferred += 1

                if refresh_prices and position.quantity > 0:
                    risk_result = await self._refresh_risk(position, portfolio)
                    if risk_result is None:
                        prices_deferred += 1
                    else:
                        repriced += 1
                        if risk_result:
                            risk_exits += 1
                            closed += 1

        if increased or repriced:
            portfolio.updated_at = datetime.now(UTC)
            await self.repository.session.commit()
        return PaperCopyReconciliationResult(
            wallets_checked=len(by_wallet),
            positions_checked=checked,
            positions_reduced=reduced,
            positions_closed=closed,
            positions_increased=increased,
            positions_deferred=deferred,
            positions_repriced=repriced,
            prices_deferred=prices_deferred,
            risk_exits=risk_exits,
        )

    async def close_all_positions(
        self,
        portfolio_wallet: str,
        *,
        reason: str = "strategy reset",
        write_off_unroutable: bool = False,
    ) -> tuple[int, int, int]:
        portfolio = await self.repository.get_portfolio(portfolio_wallet)
        if portfolio is None:
            return 0, 0, 0
        await self.repository.skip_pending_buys(portfolio, reason)
        positions = await self.repository.list_open_positions(portfolio.id)
        closed = deferred = written_off = 0
        for position in positions:
            route = await self._get_sell_route(position)
            if route is None:
                if not write_off_unroutable:
                    deferred += 1
                    continue
                route = SwapRouteQuote(
                    input_mint=position.token_address,
                    output_mint="unavailable",
                    input_amount=position.quantity,
                    output_amount=0,
                    price_impact_pct=100,
                    fee_bps=0,
                    router="unavailable",
                    route="no executable route; written off",
                )
                written_off += 1
            order = self._exit_order(position, reason)
            self.repository.session.add(order)
            await self.repository.session.flush()
            await self.paper_copy._fill_sell(order, portfolio, position, None, route)
            closed += 1
        return closed, deferred, written_off

    async def _refresh_risk(
        self,
        position: PaperCopyPosition,
        portfolio: PaperCopyPortfolio,
    ) -> bool | None:
        route = await self._get_sell_route(position)
        if route is None or position.cost_basis_usd <= 0 or position.quantity <= 0:
            return None
        executable_value = route.output_amount
        executable_price = executable_value / position.quantity
        roi_pct = (executable_value / position.cost_basis_usd - 1) * 100
        position.last_price_usd = executable_price
        position.maximum_roi_pct = max(position.maximum_roi_pct or 0, roi_pct)
        position.minimum_roi_pct = min(position.minimum_roi_pct or 0, roi_pct)
        position.updated_at = datetime.now(UTC)
        await self.repository.add_position_snapshot(
            position,
            executable_value_usd=executable_value,
            executable_price_usd=executable_price,
            roi_pct=roi_pct,
            price_impact_pct=route.price_impact_pct,
            route_fee_bps=route.fee_bps,
        )

        reason: str | None = None
        if roi_pct <= -self.stop_loss_pct:
            reason = f"risk stop: executable ROI {roi_pct:.2f}%"
        elif (
            position.maximum_roi_pct >= self.trailing_activation_pct
            and executable_value
            <= position.cost_basis_usd
            * (1 + position.maximum_roi_pct / 100)
            * (1 - self.trailing_drawdown_pct / 100)
        ):
            reason = (
                f"trailing stop: ROI {roi_pct:.2f}%, "
                f"peak {position.maximum_roi_pct:.2f}%"
            )
        elif (
            position.maximum_roi_pct >= self.break_even_activation_pct
            and roi_pct <= 0
        ):
            reason = (
                f"break-even protection: ROI {roi_pct:.2f}%, "
                f"peak {position.maximum_roi_pct:.2f}%"
            )
        if reason is None:
            return False

        order = self._exit_order(position, reason)
        self.repository.session.add(order)
        await self.repository.session.flush()
        await self.paper_copy._fill_sell(order, portfolio, position, None, route)
        return True

    async def _get_sell_route(
        self,
        position: PaperCopyPosition,
    ) -> SwapRouteQuote | None:
        decimals = await self.repository.get_token_decimals(position.token_address)
        if decimals is None:
            return None
        try:
            return await self.paper_copy.route_quotes.get_sell_quote(
                position.token_address,
                position.quantity,
                decimals,
            )
        except Exception:
            return None

    @staticmethod
    def _exit_order(position: PaperCopyPosition, reason: str) -> PaperCopyOrder:
        now = datetime.now(UTC)
        fingerprint = f"{position.id}:{reason}:{now.isoformat()}"
        return PaperCopyOrder(
            portfolio_id=position.portfolio_id,
            source_wallet=position.source_wallet,
            source_signature=f"risk-{sha256(fingerprint.encode()).hexdigest()[:40]}",
            token_address=position.token_address,
            side="sell",
            source_amount=position.source_quantity,
            source_transaction_at=now,
            execute_after=now,
            status="pending",
            attempts=0,
            reason=reason,
            notification_sent=False,
            strategy_version=position.strategy_version,
            created_at=now,
        )

    async def _get_market_quote(self, token_address: str) -> TokenMarketQuote | None:
        try:
            return await self.market_data.get_token_quote(token_address)
        except Exception:
            return None

    async def _reduce_position(
        self,
        position: PaperCopyPosition,
        portfolio: PaperCopyPortfolio,
        actual: float,
        quote: TokenMarketQuote | None,
    ) -> bool:
        now = datetime.now(UTC)
        source_amount = max(0.0, position.source_quantity - actual)
        fingerprint = (
            f"{position.portfolio_id}:{position.source_wallet}:"
            f"{position.token_address}:{position.source_quantity:.12g}:{actual:.12g}"
        )
        order = PaperCopyOrder(
            portfolio_id=position.portfolio_id,
            source_wallet=position.source_wallet,
            source_signature=f"reconcile-{sha256(fingerprint.encode()).hexdigest()[:40]}",
            token_address=position.token_address,
            side="sell",
            source_amount=source_amount,
            source_transaction_at=now,
            execute_after=now,
            status="pending",
            attempts=0,
            reason="on-chain balance reconciliation",
            notification_sent=False,
            created_at=now,
        )
        self.repository.session.add(order)
        await self.repository.session.flush()

        decimals = await self.repository.get_token_decimals(position.token_address)
        if decimals is None:
            await self.repository.session.commit()
            return False
        source_fraction = min(
            1.0,
            source_amount / max(position.source_quantity, source_amount),
        )
        try:
            route = await self.paper_copy.route_quotes.get_sell_quote(
                position.token_address,
                position.quantity * source_fraction,
                decimals,
            )
        except Exception:
            route = None
        if route is None:
            await self.repository.session.commit()
            return False
        await self.paper_copy._fill_sell(order, portfolio, position, quote, route)
        return True
