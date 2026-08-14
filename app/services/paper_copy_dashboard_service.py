from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models import (
    PaperCopyOrder,
    PaperCopyPortfolio,
    PaperCopyPosition,
    Token,
)


class PaperCopyDashboardService:
    """Build the live paper-copy portfolio view used by the dashboard."""

    def __init__(
        self,
        session: AsyncSession,
        portfolio_wallet: str,
        source_wallets: tuple[str, ...] = (),
    ) -> None:
        self.session = session
        self.portfolio_wallet = portfolio_wallet
        self.source_wallets = source_wallets

    async def get(self) -> dict[str, Any]:
        portfolio = await self._portfolio()
        if portfolio is None:
            return {
                "updated_at": datetime.now(UTC),
                "portfolio_wallet": self.portfolio_wallet,
                "enabled": False,
                "initial_balance_usd": 0.0,
                "cash_balance_usd": 0.0,
                "total_equity_usd": 0.0,
                "total_pnl_usd": 0.0,
                "realized_pnl_usd": 0.0,
                "open_pnl_usd": 0.0,
                "allocation_usd": 0.0,
                "max_open_positions": 0,
                "slippage_bps": 0,
                "started_at": None,
                "positions": [],
                "closed_positions": [],
                "trader_stats": [],
            }

        rows = await self._positions(portfolio.id)
        closed_rows = await self._closed_positions(portfolio.id)
        sell_factor = 1 - portfolio.slippage_bps / 10_000
        positions: list[dict[str, Any]] = []
        open_value = 0.0
        for position, symbol, name in rows:
            market_value = position.quantity * position.last_price_usd
            exit_value = market_value * sell_factor
            unrealized_pnl = exit_value - position.cost_basis_usd
            roi = (
                unrealized_pnl / position.cost_basis_usd * 100
                if position.cost_basis_usd > 0
                else 0.0
            )
            open_value += exit_value
            positions.append(
                {
                    "source_wallet": position.source_wallet,
                    "token_address": position.token_address,
                    "symbol": symbol,
                    "name": name,
                    "source_quantity": position.source_quantity,
                    "quantity": position.quantity,
                    "cost_basis_usd": position.cost_basis_usd,
                    "entry_price_usd": position.entry_price_usd,
                    "last_price_usd": position.last_price_usd,
                    "market_value_usd": market_value,
                    "estimated_exit_value_usd": exit_value,
                    "unrealized_pnl_usd": unrealized_pnl,
                    "unrealized_roi_pct": roi,
                    "opened_at": position.opened_at,
                    "updated_at": position.updated_at,
                }
            )
        positions.sort(key=lambda item: item["opened_at"], reverse=True)
        closed_positions: list[dict[str, Any]] = []
        realized_pnl = 0.0
        for order, symbol, name in closed_rows:
            value = float(order.value_usd or 0)
            pnl = float(order.realized_pnl_usd or 0)
            quantity = float(order.quantity or 0)
            cost_basis = value - pnl
            realized_pnl += pnl
            closed_positions.append(
                {
                    "source_wallet": order.source_wallet,
                    "token_address": order.token_address,
                    "symbol": symbol,
                    "name": name,
                    "source_signature": order.source_signature,
                    "source_amount": order.source_amount,
                    "quantity": quantity,
                    "cost_basis_usd": cost_basis,
                    "entry_price_usd": cost_basis / quantity if quantity > 0 else 0,
                    "exit_price_usd": float(order.execution_price_usd or 0),
                    "exit_value_usd": value,
                    "realized_pnl_usd": pnl,
                    "realized_roi_pct": (
                        pnl / cost_basis * 100 if cost_basis > 0 else 0
                    ),
                    "source_transaction_at": order.source_transaction_at,
                    "closed_at": order.executed_at or order.source_transaction_at,
                }
            )
        equity = portfolio.cash_balance_usd + open_value
        open_cost = sum(float(item["cost_basis_usd"]) for item in positions)
        open_pnl = open_value - open_cost
        trader_stats = self._trader_stats(positions, closed_positions)
        return {
            "updated_at": datetime.now(UTC),
            "portfolio_wallet": portfolio.source_wallet,
            "enabled": portfolio.enabled,
            "initial_balance_usd": portfolio.initial_balance_usd,
            "cash_balance_usd": portfolio.cash_balance_usd,
            "total_equity_usd": equity,
            "total_pnl_usd": equity - portfolio.initial_balance_usd,
            "realized_pnl_usd": realized_pnl,
            "open_pnl_usd": open_pnl,
            "allocation_usd": portfolio.allocation_usd,
            "max_open_positions": portfolio.max_open_positions,
            "slippage_bps": portfolio.slippage_bps,
            "started_at": portfolio.started_at,
            "positions": positions,
            "closed_positions": closed_positions,
            "trader_stats": trader_stats,
        }

    def _trader_stats(
        self,
        positions: list[dict[str, Any]],
        closed_positions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        stats: dict[str, dict[str, Any]] = {}
        current_sources = set(self.source_wallets)

        def row(wallet: str) -> dict[str, Any]:
            return stats.setdefault(
                wallet,
                {
                    "source_wallet": wallet,
                    "current_aa": wallet in current_sources,
                    "open_positions": 0,
                    "closed_trades": 0,
                    "profitable_closed_trades": 0,
                    "realized_pnl_usd": 0.0,
                    "open_pnl_usd": 0.0,
                    "total_pnl_usd": 0.0,
                    "total_cost_basis_usd": 0.0,
                    "total_roi_pct": 0.0,
                    "closed_win_rate_pct": 0.0,
                },
            )

        for wallet in self.source_wallets:
            row(wallet)
        for position in positions:
            trader = row(str(position["source_wallet"]))
            trader["open_positions"] += 1
            trader["open_pnl_usd"] += float(position["unrealized_pnl_usd"])
            trader["total_cost_basis_usd"] += float(position["cost_basis_usd"])
        for position in closed_positions:
            trader = row(str(position["source_wallet"]))
            pnl = float(position["realized_pnl_usd"])
            trader["closed_trades"] += 1
            trader["profitable_closed_trades"] += int(pnl > 0)
            trader["realized_pnl_usd"] += pnl
            trader["total_cost_basis_usd"] += float(position["cost_basis_usd"])

        for trader in stats.values():
            trader["total_pnl_usd"] = (
                trader["realized_pnl_usd"] + trader["open_pnl_usd"]
            )
            cost_basis = trader["total_cost_basis_usd"]
            trader["total_roi_pct"] = (
                trader["total_pnl_usd"] / cost_basis * 100 if cost_basis > 0 else 0.0
            )
            closed_trades = trader["closed_trades"]
            trader["closed_win_rate_pct"] = (
                trader["profitable_closed_trades"] / closed_trades * 100
                if closed_trades > 0
                else 0.0
            )
        return sorted(
            stats.values(),
            key=lambda trader: (
                trader["current_aa"],
                trader["total_pnl_usd"],
                trader["source_wallet"],
            ),
            reverse=True,
        )

    async def _portfolio(self) -> PaperCopyPortfolio | None:
        result = await self.session.execute(
            select(PaperCopyPortfolio).where(
                PaperCopyPortfolio.source_wallet == self.portfolio_wallet
            )
        )
        return result.scalar_one_or_none()

    async def _positions(
        self, portfolio_id: int
    ) -> list[tuple[PaperCopyPosition, str | None, str | None]]:
        result = await self.session.execute(
            select(PaperCopyPosition, Token.symbol, Token.name)
            .outerjoin(Token, Token.address == PaperCopyPosition.token_address)
            .where(
                PaperCopyPosition.portfolio_id == portfolio_id,
                PaperCopyPosition.quantity > 0,
            )
        )
        return [(row[0], row[1], row[2]) for row in result.all()]

    async def _closed_positions(
        self, portfolio_id: int
    ) -> list[tuple[PaperCopyOrder, str | None, str | None]]:
        result = await self.session.execute(
            select(PaperCopyOrder, Token.symbol, Token.name)
            .outerjoin(Token, Token.address == PaperCopyOrder.token_address)
            .where(
                PaperCopyOrder.portfolio_id == portfolio_id,
                PaperCopyOrder.status == "filled",
                PaperCopyOrder.side == "sell",
            )
            .order_by(PaperCopyOrder.executed_at.desc(), PaperCopyOrder.id.desc())
        )
        return [(row[0], row[1], row[2]) for row in result.all()]
