from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from app.core.scoring import TokenScore
from app.infrastructure.models import TokenScoreSnapshot
from app.repositories.token_score_snapshot_repository import (
    TokenScoreSnapshotRepository,
)


class FakeResult:
    def scalar_one(self) -> TokenScoreSnapshot:
        return TokenScoreSnapshot(token_id=1)


class CompilingSession:
    def __init__(self) -> None:
        self.sql = ""
        self.committed = False

    async def execute(self, statement: Any) -> FakeResult:
        self.sql = str(statement.compile(dialect=postgresql.dialect()))
        return FakeResult()

    async def commit(self) -> None:
        self.committed = True


def make_score() -> TokenScore:
    return TokenScore(
        token_address="mint",
        score=70,
        grade="B",
        methodology_version="token-v1",
        activity_score=10,
        participation_score=10,
        holder_distribution_score=15,
        flow_balance_score=10,
        creator_history_score=15,
        data_quality_score=10,
        observed_holder_count=5,
        top_holder_share=0.3,
        incomplete_holder_ratio=0,
    )


@pytest.mark.asyncio
async def test_token_snapshot_upsert_is_atomic_on_token_id() -> None:
    session = CompilingSession()
    repository = TokenScoreSnapshotRepository(session)  # type: ignore[arg-type]

    snapshot = await repository.upsert(1, make_score())

    assert "ON CONFLICT (token_id) DO UPDATE" in session.sql
    assert "RETURNING" in session.sql
    assert session.committed is True
    assert snapshot.token_id == 1
