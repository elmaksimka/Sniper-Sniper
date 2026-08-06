from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from app.core.scoring import WalletScore
from app.infrastructure.models import WalletScoreSnapshot
from app.repositories.score_snapshot_repository import ScoreSnapshotRepository


class FakeResult:
    def __init__(self, snapshot: WalletScoreSnapshot) -> None:
        self.snapshot = snapshot

    def scalar_one(self) -> WalletScoreSnapshot:
        return self.snapshot


class CompilingSession:
    def __init__(self) -> None:
        self.sql = ""
        self.committed = False

    async def execute(self, statement: Any) -> FakeResult:
        self.sql = str(statement.compile(dialect=postgresql.dialect()))
        return FakeResult(WalletScoreSnapshot(wallet_id=1))

    async def commit(self) -> None:
        self.committed = True


def make_score() -> WalletScore:
    return WalletScore(
        wallet_address="wallet",
        score=75,
        grade="B",
        methodology_version="wallet-v1",
        activity_score=15,
        diversification_score=10,
        exit_experience_score=15,
        realized_performance_score=27.5,
        data_quality_score=7.5,
        realized_pnl_sol=2,
        realized_roi=0.2,
        unmatched_sell_ratio=0.25,
    )


@pytest.mark.asyncio
async def test_snapshot_upsert_is_atomic_on_wallet_id() -> None:
    session = CompilingSession()
    repository = ScoreSnapshotRepository(session)  # type: ignore[arg-type]

    snapshot = await repository.upsert(1, make_score())

    assert "ON CONFLICT (wallet_id) DO UPDATE" in session.sql
    assert "RETURNING" in session.sql
    assert session.committed is True
    assert snapshot.wallet_id == 1
