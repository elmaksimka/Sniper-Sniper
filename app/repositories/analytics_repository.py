from __future__ import annotations

from sqlalchemy import case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.analytics import ObservedTokenHolder, TokenAnalytics, WalletAnalytics
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

    async def list_token_holders(
        self,
        address: str,
        limit: int,
        offset: int,
        include_closed: bool = False,
    ) -> tuple[list[ObservedTokenHolder], int]:
        signed_amount = case(
            (Trade.side == "buy", Trade.amount),
            (Trade.side == "sell", -Trade.amount),
            else_=0.0,
        )
        movements = (
            select(
                Trade.wallet_id.label("wallet_id"),
                Trade.side.label("side"),
                Trade.amount.label("amount"),
                Trade.timestamp.label("timestamp"),
                signed_amount.label("signed_amount"),
                func.sum(signed_amount)
                .over(
                    partition_by=Trade.wallet_id,
                    order_by=(Trade.timestamp.asc(), Trade.id.asc()),
                )
                .label("running_quantity"),
            )
            .join(Trade.token)
            .where(Token.address == address)
            .subquery()
        )
        aggregate = (
            select(
                movements.c.wallet_id,
                func.coalesce(
                    func.sum(
                        case(
                            (movements.c.side == "buy", movements.c.amount),
                            else_=0.0,
                        )
                    ),
                    0.0,
                ).label("total_bought"),
                func.coalesce(
                    func.sum(
                        case(
                            (movements.c.side == "sell", movements.c.amount),
                            else_=0.0,
                        )
                    ),
                    0.0,
                ).label("total_sold"),
                func.sum(movements.c.signed_amount).label("net_quantity"),
                func.min(movements.c.running_quantity).label("minimum_running"),
                func.count().label("trade_count"),
                func.min(movements.c.timestamp).label("first_trade_at"),
                func.max(movements.c.timestamp).label("last_trade_at"),
            )
            .select_from(movements)
            .group_by(movements.c.wallet_id)
            .subquery()
        )
        unmatched_sells = case(
            (aggregate.c.minimum_running < 0, -aggregate.c.minimum_running),
            else_=0.0,
        )
        quantity = aggregate.c.net_quantity + unmatched_sells
        active_condition = quantity > 0

        statement = (
            select(
                Wallet.address.label("wallet_address"),
                quantity.label("quantity"),
                aggregate.c.total_bought,
                aggregate.c.total_sold,
                unmatched_sells.label("unmatched_sell_quantity"),
                aggregate.c.trade_count,
                aggregate.c.first_trade_at,
                aggregate.c.last_trade_at,
            )
            .join(aggregate, aggregate.c.wallet_id == Wallet.id)
            .order_by(quantity.desc(), Wallet.address.asc())
            .limit(limit)
            .offset(offset)
        )
        count_statement = select(func.count()).select_from(aggregate)
        if not include_closed:
            statement = statement.where(active_condition)
            count_statement = count_statement.where(active_condition)

        result = await self.session.execute(statement)
        total_result = await self.session.execute(count_statement)
        return (
            [
                ObservedTokenHolder(
                    wallet_address=row.wallet_address,
                    quantity=float(row.quantity),
                    total_bought=float(row.total_bought),
                    total_sold=float(row.total_sold),
                    unmatched_sell_quantity=float(row.unmatched_sell_quantity),
                    trade_count=int(row.trade_count),
                    first_trade_at=row.first_trade_at,
                    last_trade_at=row.last_trade_at,
                )
                for row in result.all()
            ],
            int(total_result.scalar_one()),
        )
