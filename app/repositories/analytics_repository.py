from __future__ import annotations

from sqlalchemy import case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.analytics import TokenAnalytics, WalletAnalytics
from app.infrastructure.models import Token, Trade, Wallet


class AnalyticsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_wallet_metrics(self, address: str) -> WalletAnalytics:
        result = await self.session.execute(
            select(
                func.count(Trade.id).label("total_trades"),
                func.count(Trade.id)
                .filter(Trade.side == "buy")
                .label("buy_count"),
                func.count(Trade.id)
                .filter(Trade.side == "sell")
                .label("sell_count"),
                func.count(distinct(Trade.token_id)).label("unique_tokens"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                (Trade.side == "buy") & (Trade.sol_change < 0),
                                -Trade.sol_change,
                            ),
                            else_=0.0,
                        )
                    ),
                    0.0,
                ).label("sol_spent"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                (Trade.side == "sell") & (Trade.sol_change > 0),
                                Trade.sol_change,
                            ),
                            else_=0.0,
                        )
                    ),
                    0.0,
                ).label("sol_received"),
                func.coalesce(func.sum(Trade.sol_change), 0.0).label(
                    "net_sol_change"
                ),
                func.min(Trade.timestamp).label("first_trade_at"),
                func.max(Trade.timestamp).label("last_trade_at"),
            )
            .select_from(Trade)
            .join(Trade.wallet)
            .where(Wallet.address == address)
        )
        row = result.one()

        return WalletAnalytics(
            address=address,
            total_trades=int(row.total_trades),
            buy_count=int(row.buy_count),
            sell_count=int(row.sell_count),
            unique_tokens=int(row.unique_tokens),
            sol_spent=float(row.sol_spent),
            sol_received=float(row.sol_received),
            net_sol_change=float(row.net_sol_change),
            first_trade_at=row.first_trade_at,
            last_trade_at=row.last_trade_at,
        )

    async def get_token_metrics(self, address: str) -> TokenAnalytics:
        result = await self.session.execute(
            select(
                func.count(Trade.id).label("total_trades"),
                func.count(Trade.id)
                .filter(Trade.side == "buy")
                .label("buy_count"),
                func.count(Trade.id)
                .filter(Trade.side == "sell")
                .label("sell_count"),
                func.count(distinct(Trade.wallet_id)).label("unique_wallets"),
                func.coalesce(
                    func.sum(
                        case((Trade.side == "buy", Trade.amount), else_=0.0)
                    ),
                    0.0,
                ).label("buy_volume"),
                func.coalesce(
                    func.sum(
                        case((Trade.side == "sell", Trade.amount), else_=0.0)
                    ),
                    0.0,
                ).label("sell_volume"),
                func.coalesce(
                    func.sum(
                        case(
                            (Trade.side == "buy", Trade.amount),
                            (Trade.side == "sell", -Trade.amount),
                            else_=0.0,
                        )
                    ),
                    0.0,
                ).label("net_token_flow"),
                func.coalesce(func.sum(Trade.sol_change), 0.0).label(
                    "net_wallet_sol_change"
                ),
                func.min(Trade.timestamp).label("first_trade_at"),
                func.max(Trade.timestamp).label("last_trade_at"),
            )
            .select_from(Trade)
            .join(Trade.token)
            .where(Token.address == address)
        )
        row = result.one()

        return TokenAnalytics(
            address=address,
            total_trades=int(row.total_trades),
            buy_count=int(row.buy_count),
            sell_count=int(row.sell_count),
            unique_wallets=int(row.unique_wallets),
            buy_volume=float(row.buy_volume),
            sell_volume=float(row.sell_volume),
            net_token_flow=float(row.net_token_flow),
            net_wallet_sol_change=float(row.net_wallet_sol_change),
            first_trade_at=row.first_trade_at,
            last_trade_at=row.last_trade_at,
        )

    async def list_wallet_trades(self, address: str) -> list[Trade]:
        result = await self.session.execute(
            select(Trade)
            .join(Trade.wallet)
            .options(selectinload(Trade.token))
            .where(Wallet.address == address)
            .order_by(Trade.timestamp.asc(), Trade.id.asc())
        )
        return list(result.scalars().all())
