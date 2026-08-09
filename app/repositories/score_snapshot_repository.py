from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import distinct, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.scoring import WalletScore
from app.infrastructure.models import (
    Token,
    Trade,
    Wallet,
    WalletMonitor,
    WalletScoreSnapshot,
)


class ScoreSnapshotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(
        self,
        wallet_id: int,
        score: WalletScore,
    ) -> WalletScoreSnapshot:
        values = self._values(wallet_id, score)
        statement = (
            insert(WalletScoreSnapshot)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[WalletScoreSnapshot.wallet_id],
                set_={
                    key: value
                    for key, value in values.items()
                    if key != "wallet_id"
                },
            )
            .returning(WalletScoreSnapshot)
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(statement)
        snapshot = result.scalar_one()
        await self.session.commit()
        return snapshot

    async def get_by_wallet_id(
        self,
        wallet_id: int,
    ) -> WalletScoreSnapshot | None:
        result = await self.session.execute(
            select(WalletScoreSnapshot)
            .where(WalletScoreSnapshot.wallet_id == wallet_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_by_wallet_address(
        self,
        address: str,
    ) -> WalletScoreSnapshot | None:
        result = await self.session.execute(
            select(WalletScoreSnapshot)
            .join(Wallet, Wallet.id == WalletScoreSnapshot.wallet_id)
            .where(Wallet.address == address)
            .options(selectinload(WalletScoreSnapshot.wallet))
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def list_leaderboard(
        self,
        limit: int,
        offset: int,
        grade: str | None = None,
    ) -> list[WalletScoreSnapshot]:
        statement = (
            select(WalletScoreSnapshot)
            .options(selectinload(WalletScoreSnapshot.wallet))
            .execution_options(populate_existing=True)
        )
        if grade:
            statement = statement.where(WalletScoreSnapshot.grade == grade)

        result = await self.session.execute(
            statement
            .order_by(
                WalletScoreSnapshot.score.desc(),
                WalletScoreSnapshot.updated_at.desc(),
                WalletScoreSnapshot.id.asc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def list_top_token_trader_candidates(
        self,
        *,
        minimum_score: float,
        window_hours: int,
        token_limit: int,
        traders_per_token: int,
        minimum_token_trades: int,
        minimum_token_wallets: int,
        minimum_observed_minutes: float,
        minimum_current_multiple: float,
        early_entry_minutes: float,
        early_entry_max_multiple: float,
    ) -> tuple[list[WalletScoreSnapshot], int]:
        """Prioritize repeat early buyers of observed launch winners."""
        cutoff = datetime.now(UTC) - timedelta(hours=window_hours)
        priced_trades = (
            select(
                Trade.id,
                Trade.token_id,
                Trade.wallet_id,
                Trade.signature,
                Trade.timestamp,
                Trade.price,
                func.first_value(Trade.price)
                .over(
                    partition_by=Trade.token_id,
                    order_by=(Trade.timestamp.asc(), Trade.id.asc()),
                )
                .label("first_price"),
                func.first_value(Trade.price)
                .over(
                    partition_by=Trade.token_id,
                    order_by=(Trade.timestamp.desc(), Trade.id.desc()),
                )
                .label("last_price"),
            )
            .where(Trade.timestamp >= cutoff, Trade.price > 0)
            .subquery()
        )
        transaction_count = func.count(distinct(priced_trades.c.signature))
        wallet_count = func.count(distinct(priced_trades.c.wallet_id))
        first_at = func.min(priced_trades.c.timestamp)
        last_at = func.max(priced_trades.c.timestamp)
        first_price = func.max(priced_trades.c.first_price)
        last_price = func.max(priced_trades.c.last_price)
        current_multiple = last_price / func.nullif(first_price, 0)
        observed_minutes = func.extract("epoch", last_at - first_at) / 60
        token_rows = await self.session.execute(
            select(
                priced_trades.c.token_id,
                transaction_count.label("transaction_count"),
                wallet_count.label("wallet_count"),
                first_at.label("first_at"),
                first_price.label("first_price"),
                current_multiple.label("current_multiple"),
            )
            .group_by(priced_trades.c.token_id)
            .having(transaction_count >= minimum_token_trades)
            .having(wallet_count >= minimum_token_wallets)
            .having(observed_minutes >= minimum_observed_minutes)
            .having(current_multiple >= minimum_current_multiple)
            .order_by(
                wallet_count.desc(),
                current_multiple.desc(),
                transaction_count.desc(),
                priced_trades.c.token_id.asc(),
            )
            .limit(token_limit)
        )
        winner_tokens = list(token_rows.all())

        ranked: dict[int, tuple[WalletScoreSnapshot, int, int]] = {}
        for token in winner_tokens:
            early_deadline = token.first_at + timedelta(minutes=early_entry_minutes)
            early_price_ceiling = float(token.first_price) * early_entry_max_multiple
            candidate_rows = await self.session.execute(
                select(
                    WalletScoreSnapshot,
                    func.count(Trade.id).label("early_buys"),
                )
                .join(
                    Trade,
                    Trade.wallet_id == WalletScoreSnapshot.wallet_id,
                )
                .outerjoin(
                    WalletMonitor,
                    WalletMonitor.wallet_id == WalletScoreSnapshot.wallet_id,
                )
                .options(selectinload(WalletScoreSnapshot.wallet))
                .where(
                    Trade.token_id == token.token_id,
                    Trade.side == "buy",
                    Trade.timestamp >= token.first_at,
                    Trade.timestamp <= early_deadline,
                    Trade.price > 0,
                    Trade.price <= early_price_ceiling,
                    WalletScoreSnapshot.score >= minimum_score,
                    or_(
                        WalletMonitor.id.is_(None),
                        WalletMonitor.enabled.is_(False),
                    ),
                )
                .group_by(WalletScoreSnapshot.id)
                .order_by(
                    WalletScoreSnapshot.score.desc(),
                    func.count(Trade.id).desc(),
                    WalletScoreSnapshot.updated_at.desc(),
                )
                .limit(traders_per_token)
            )
            for row in candidate_rows.all():
                snapshot = row[0]
                early_buys = int(row.early_buys)
                existing = ranked.get(snapshot.wallet_id)
                if existing is None:
                    ranked[snapshot.wallet_id] = (snapshot, 1, early_buys)
                    continue
                ranked[snapshot.wallet_id] = (
                    snapshot,
                    existing[1] + 1,
                    existing[2] + early_buys,
                )

        candidates = [
            item[0]
            for item in sorted(
                ranked.values(),
                key=lambda item: (
                    item[1],
                    item[0].score,
                    item[2],
                ),
                reverse=True,
            )
        ]
        return candidates, len(winner_tokens)

    async def count(self, grade: str | None = None) -> int:
        statement = select(func.count(WalletScoreSnapshot.id))
        if grade:
            statement = statement.where(WalletScoreSnapshot.grade == grade)

        result = await self.session.execute(statement)
        return result.scalar_one()

    async def list_top_buyers_for_token(
        self,
        token_address: str,
        minimum_score: float,
    ) -> list[str]:
        result = await self.session.execute(
            select(Wallet.address)
            .distinct()
            .join(Trade, Trade.wallet_id == Wallet.id)
            .join(Token, Token.id == Trade.token_id)
            .join(
                WalletScoreSnapshot,
                WalletScoreSnapshot.wallet_id == Trade.wallet_id,
            )
            .where(
                Token.address == token_address,
                Trade.side == "buy",
                WalletScoreSnapshot.score >= minimum_score,
                WalletScoreSnapshot.grade.in_(("A", "B")),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    def _values(wallet_id: int, score: WalletScore) -> dict[str, object]:
        return {
            "wallet_id": wallet_id,
            "score": score.score,
            "grade": score.grade,
            "methodology_version": score.methodology_version,
            "activity_score": score.activity_score,
            "diversification_score": score.diversification_score,
            "exit_experience_score": score.exit_experience_score,
            "realized_performance_score": score.realized_performance_score,
            "data_quality_score": score.data_quality_score,
            "realized_pnl_sol": score.realized_pnl_sol,
            "realized_roi": score.realized_roi,
            "unmatched_sell_ratio": score.unmatched_sell_ratio,
            "priced_trade_ratio": score.priced_trade_ratio,
            "realized_cost_basis_sol": score.realized_cost_basis_sol,
            "updated_at": datetime.now(UTC),
        }
