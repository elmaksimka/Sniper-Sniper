from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.scoring import TokenScore
from app.infrastructure.models import TokenScoreSnapshot


class TokenScoreSnapshotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(
        self,
        token_id: int,
        score: TokenScore,
    ) -> TokenScoreSnapshot:
        values = self._values(token_id, score)
        statement = (
            insert(TokenScoreSnapshot)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[TokenScoreSnapshot.token_id],
                set_={key: value for key, value in values.items() if key != "token_id"},
            )
            .returning(TokenScoreSnapshot)
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(statement)
        snapshot = result.scalar_one()
        await self.session.commit()
        return snapshot

    async def list_leaderboard(
        self,
        limit: int,
        offset: int,
        grade: str | None = None,
    ) -> list[TokenScoreSnapshot]:
        statement = (
            select(TokenScoreSnapshot)
            .options(selectinload(TokenScoreSnapshot.token))
            .execution_options(populate_existing=True)
        )
        if grade:
            statement = statement.where(TokenScoreSnapshot.grade == grade)
        result = await self.session.execute(
            statement.order_by(
                TokenScoreSnapshot.score.desc(),
                TokenScoreSnapshot.updated_at.desc(),
                TokenScoreSnapshot.id.asc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_by_token_id(
        self,
        token_id: int,
    ) -> TokenScoreSnapshot | None:
        result = await self.session.execute(
            select(TokenScoreSnapshot)
            .where(TokenScoreSnapshot.token_id == token_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def count(self, grade: str | None = None) -> int:
        statement = select(func.count(TokenScoreSnapshot.id))
        if grade:
            statement = statement.where(TokenScoreSnapshot.grade == grade)
        result = await self.session.execute(statement)
        return result.scalar_one()

    @staticmethod
    def _values(token_id: int, score: TokenScore) -> dict[str, object]:
        return {
            "token_id": token_id,
            "score": score.score,
            "grade": score.grade,
            "methodology_version": score.methodology_version,
            "activity_score": score.activity_score,
            "participation_score": score.participation_score,
            "holder_distribution_score": score.holder_distribution_score,
            "flow_balance_score": score.flow_balance_score,
            "creator_history_score": score.creator_history_score,
            "data_quality_score": score.data_quality_score,
            "observed_holder_count": score.observed_holder_count,
            "top_holder_share": score.top_holder_share,
            "incomplete_holder_ratio": score.incomplete_holder_ratio,
            "updated_at": datetime.now(UTC),
        }
