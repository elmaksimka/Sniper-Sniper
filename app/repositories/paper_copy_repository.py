from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models import (
    PaperCopyOrder,
    PaperCopyPortfolio,
    PaperCopyPosition,
)


class PaperCopyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ensure_portfolio(
        self,
        *,
        source_wallet: str,
        initial_balance_usd: float,
        allocation_usd: float,
        max_open_positions: int,
        reaction_delay_seconds: float,
        slippage_bps: int,
        minimum_liquidity_usd: float,
    ) -> tuple[PaperCopyPortfolio, bool]:
        portfolio = await self.get_portfolio(source_wallet)
        created = portfolio is None
        if portfolio is None:
            portfolio = PaperCopyPortfolio(
                source_wallet=source_wallet,
                initial_balance_usd=initial_balance_usd,
                cash_balance_usd=initial_balance_usd,
                allocation_usd=allocation_usd,
                max_open_positions=max_open_positions,
                reaction_delay_seconds=reaction_delay_seconds,
                slippage_bps=slippage_bps,
                minimum_liquidity_usd=minimum_liquidity_usd,
                enabled=True,
            )
            self.session.add(portfolio)
        else:
            portfolio.allocation_usd = allocation_usd
            portfolio.max_open_positions = max_open_positions
            portfolio.reaction_delay_seconds = reaction_delay_seconds
            portfolio.slippage_bps = slippage_bps
            portfolio.minimum_liquidity_usd = minimum_liquidity_usd
            portfolio.enabled = True
            portfolio.updated_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(portfolio)
        return portfolio, created

    async def get_portfolio(self, source_wallet: str) -> PaperCopyPortfolio | None:
        result = await self.session.execute(
            select(PaperCopyPortfolio).where(
                PaperCopyPortfolio.source_wallet == source_wallet
            )
        )
        return result.scalar_one_or_none()

    async def enqueue(
        self,
        *,
        portfolio: PaperCopyPortfolio,
        source_wallet: str,
        source_signature: str,
        token_address: str,
        side: str,
        source_amount: float,
        source_transaction_at: datetime,
    ) -> bool:
        statement = (
            pg_insert(PaperCopyOrder)
            .values(
                portfolio_id=portfolio.id,
                source_wallet=source_wallet,
                source_signature=source_signature,
                token_address=token_address,
                side=side,
                source_amount=source_amount,
                source_transaction_at=source_transaction_at,
                execute_after=datetime.now(UTC)
                + timedelta(seconds=portfolio.reaction_delay_seconds),
                status="pending",
                attempts=0,
                notification_sent=False,
                created_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing(constraint="uq_paper_copy_order_source_trade")
            .returning(PaperCopyOrder.id)
        )
        result = await self.session.execute(statement)
        await self.session.commit()
        return result.scalar_one_or_none() is not None

    async def next_due(
        self,
    ) -> tuple[PaperCopyOrder, PaperCopyPortfolio] | None:
        result = await self.session.execute(
            select(PaperCopyOrder, PaperCopyPortfolio)
            .join(
                PaperCopyPortfolio,
                PaperCopyPortfolio.id == PaperCopyOrder.portfolio_id,
            )
            .where(
                PaperCopyOrder.status == "pending",
                PaperCopyOrder.execute_after <= datetime.now(UTC),
                PaperCopyPortfolio.enabled.is_(True),
            )
            .order_by(PaperCopyOrder.execute_after.asc(), PaperCopyOrder.id.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        row = result.one_or_none()
        return (row[0], row[1]) if row is not None else None

    async def get_position(
        self,
        portfolio_id: int,
        source_wallet: str,
        token_address: str,
    ) -> PaperCopyPosition | None:
        result = await self.session.execute(
            select(PaperCopyPosition).where(
                PaperCopyPosition.portfolio_id == portfolio_id,
                PaperCopyPosition.source_wallet == source_wallet,
                PaperCopyPosition.token_address == token_address,
                PaperCopyPosition.quantity > 0,
            )
        )
        return result.scalar_one_or_none()

    async def count_open_positions(self, portfolio_id: int) -> int:
        result = await self.session.execute(
            select(func.count(PaperCopyPosition.id)).where(
                PaperCopyPosition.portfolio_id == portfolio_id,
                PaperCopyPosition.quantity > 0,
            )
        )
        return int(result.scalar_one())

    async def equity(self, portfolio: PaperCopyPortfolio) -> float:
        result = await self.session.execute(
            select(
                func.coalesce(
                    func.sum(
                        PaperCopyPosition.quantity * PaperCopyPosition.last_price_usd
                    ),
                    0.0,
                )
            ).where(
                PaperCopyPosition.portfolio_id == portfolio.id,
                PaperCopyPosition.quantity > 0,
            )
        )
        return float(portfolio.cash_balance_usd + float(result.scalar_one()))

    async def list_unsent(
        self,
        portfolio_id: int,
        *,
        limit: int = 500,
    ) -> list[PaperCopyOrder]:
        result = await self.session.execute(
            select(PaperCopyOrder)
            .where(
                PaperCopyOrder.portfolio_id == portfolio_id,
                PaperCopyOrder.status.in_(("filled", "skipped")),
                PaperCopyOrder.notification_sent.is_(False),
            )
            .order_by(PaperCopyOrder.id.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_notifications_sent(self, orders: list[PaperCopyOrder]) -> None:
        for order in orders:
            order.notification_sent = True
        await self.session.commit()

    async def defer_quote(
        self,
        order: PaperCopyOrder,
        *,
        retry_seconds: float,
        maximum_attempts: int,
        reason: str,
    ) -> None:
        order.attempts += 1
        order.reason = reason[:256]
        if order.attempts >= maximum_attempts:
            order.status = "skipped"
            order.executed_at = datetime.now(UTC)
        else:
            order.execute_after = datetime.now(UTC) + timedelta(seconds=retry_seconds)
        await self.session.commit()

    async def finish_skipped(
        self,
        order: PaperCopyOrder,
        portfolio: PaperCopyPortfolio,
        reason: str,
    ) -> None:
        order.status = "skipped"
        order.reason = reason[:256]
        order.cash_balance_after_usd = portfolio.cash_balance_usd
        order.open_positions_after = await self.count_open_positions(portfolio.id)
        order.equity_after_usd = await self.equity(portfolio)
        order.executed_at = datetime.now(UTC)
        await self.session.commit()
