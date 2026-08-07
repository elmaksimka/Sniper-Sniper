from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scoring import TokenScore
from app.infrastructure.models import TokenScoreSnapshot
from app.repositories.token_score_snapshot_repository import (
    TokenScoreSnapshotRepository,
)


class TokenScoreSnapshotService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = TokenScoreSnapshotRepository(session)

    async def save(
        self,
        token_id: int,
        score: TokenScore,
    ) -> TokenScoreSnapshot:
        return await self.repository.upsert(token_id, score)

    async def leaderboard(
        self,
        limit: int,
        offset: int,
        grade: str | None = None,
    ) -> tuple[list[TokenScoreSnapshot], int]:
        return (
            await self.repository.list_leaderboard(limit, offset, grade),
            await self.repository.count(grade),
        )
