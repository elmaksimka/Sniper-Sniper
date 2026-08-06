from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scoring import WalletScore
from app.infrastructure.models import WalletScoreSnapshot
from app.repositories.score_snapshot_repository import ScoreSnapshotRepository


class ScoreSnapshotService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = ScoreSnapshotRepository(session)

    async def save(
        self,
        wallet_id: int,
        score: WalletScore,
    ) -> WalletScoreSnapshot:
        return await self.repository.upsert(wallet_id, score)

    async def leaderboard(
        self,
        limit: int,
        offset: int,
        grade: str | None = None,
    ) -> tuple[list[WalletScoreSnapshot], int]:
        return (
            await self.repository.list_leaderboard(limit, offset, grade),
            await self.repository.count(grade),
        )
