from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models import (
    PaperCopyOrder,
    PaperCopyPortfolio,
    PaperCopyPosition,
)
from app.services.dexscreener_client import DexScreenerClient


@dataclass(frozen=True, slots=True)
class PaperCopyReport:
    source_wallet: str
    initial_balance_usd: float
    cash_balance_usd: float
    total_equity_usd: float
    total_pnl_usd: float
    realized_pnl_usd: float
    open_pnl_usd: float
    filled_buys: int
    filled_sells: int
    skipped_orders: int
    open_positions: int
    stale_quotes: int


class PaperCopyReportService:
    def __init__(
        self,
        session: AsyncSession,
        market_data: DexScreenerClient | None = None,
    ) -> None:
        self.session = session
        self.market_data = market_data or DexScreenerClient()

    async def build(self, source_wallet: str) -> PaperCopyReport | None:
        portfolio = await self._portfolio(source_wallet)
        if portfolio is None:
            return None
        positions = await self._positions(portfolio.id)
        realized_pnl, buys, sells, skipped = await self._order_stats(portfolio.id)
        open_value = 0.0
        open_cost = 0.0
        stale_quotes = 0
        sell_factor = 1 - portfolio.slippage_bps / 10_000
        for position in positions:
            price = position.last_price_usd
            try:
                quote = await self.market_data.get_token_quote(
                    position.token_address
                )
            except Exception:
                quote = None
            if quote is None:
                stale_quotes += 1
            else:
                price = quote.price_usd
            open_value += position.quantity * price * sell_factor
            open_cost += position.cost_basis_usd
        equity = portfolio.cash_balance_usd + open_value
        return PaperCopyReport(
            source_wallet=portfolio.source_wallet,
            initial_balance_usd=portfolio.initial_balance_usd,
            cash_balance_usd=portfolio.cash_balance_usd,
            total_equity_usd=equity,
            total_pnl_usd=equity - portfolio.initial_balance_usd,
            realized_pnl_usd=realized_pnl,
            open_pnl_usd=open_value - open_cost,
            filled_buys=buys,
            filled_sells=sells,
            skipped_orders=skipped,
            open_positions=len(positions),
            stale_quotes=stale_quotes,
        )

    async def _portfolio(self, source_wallet: str) -> PaperCopyPortfolio | None:
        result = await self.session.execute(
            select(PaperCopyPortfolio).where(
                PaperCopyPortfolio.source_wallet == source_wallet
            )
        )
        return result.scalar_one_or_none()

    async def _positions(self, portfolio_id: int) -> list[PaperCopyPosition]:
        result = await self.session.execute(
            select(PaperCopyPosition).where(
                PaperCopyPosition.portfolio_id == portfolio_id,
                PaperCopyPosition.quantity > 0,
            )
        )
        return list(result.scalars().all())

    async def _order_stats(self, portfolio_id: int) -> tuple[float, int, int, int]:
        result = await self.session.execute(
            select(
                func.coalesce(
                    func.sum(PaperCopyOrder.realized_pnl_usd).filter(
                        PaperCopyOrder.status == "filled",
                        PaperCopyOrder.side == "sell",
                    ),
                    0.0,
                ),
                func.count(PaperCopyOrder.id).filter(
                    PaperCopyOrder.status == "filled",
                    PaperCopyOrder.side == "buy",
                ),
                func.count(PaperCopyOrder.id).filter(
                    PaperCopyOrder.status == "filled",
                    PaperCopyOrder.side == "sell",
                ),
                func.count(PaperCopyOrder.id).filter(
                    PaperCopyOrder.status == "skipped"
                ),
            ).where(PaperCopyOrder.portfolio_id == portfolio_id)
        )
        row = result.one()
        return float(row[0]), int(row[1]), int(row[2]), int(row[3])
