from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.scoring import WalletScore
from app.infrastructure.models import Token, Trade, Wallet, WalletScoreSnapshot


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
            select(WalletScoreSnapshot).where(
                WalletScoreSnapshot.wallet_id == wallet_id
            )
        )
        return result.scalar_one_or_none()

    async def list_leaderboard(
        self,
        limit: int,
        offset: int,
        grade: str | None = None,
    ) -> list[WalletScoreSnapshot]:
        statement = select(WalletScoreSnapshot).options(
            selectinload(WalletScoreSnapshot.wallet)
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
            "updated_at": datetime.now(UTC),
        }
