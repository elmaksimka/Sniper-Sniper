from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models import PaperCopyPortfolio, PaperCopyPosition, Token


class PaperCopyDashboardService:
    """Build the live paper-copy portfolio view used by the dashboard."""

    def __init__(self, session: AsyncSession, portfolio_wallet: str) -> None:
        self.session = session
        self.portfolio_wallet = portfolio_wallet

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
                "allocation_usd": 0.0,
                "max_open_positions": 0,
                "slippage_bps": 0,
                "started_at": None,
                "positions": [],
            }

        rows = await self._positions(portfolio.id)
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
        equity = portfolio.cash_balance_usd + open_value
        return {
            "updated_at": datetime.now(UTC),
            "portfolio_wallet": portfolio.source_wallet,
            "enabled": portfolio.enabled,
            "initial_balance_usd": portfolio.initial_balance_usd,
            "cash_balance_usd": portfolio.cash_balance_usd,
            "total_equity_usd": equity,
            "total_pnl_usd": equity - portfolio.initial_balance_usd,
            "allocation_usd": portfolio.allocation_usd,
            "max_open_positions": portfolio.max_open_positions,
            "slippage_bps": portfolio.slippage_bps,
            "started_at": portfolio.started_at,
            "positions": positions,
        }

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
