from typing import Any

import pytest

from app.core.scoring import WalletScore
from app.infrastructure.models import Wallet
from app.services.score_backfill_service import ScoreBackfillService


class FakeWalletRepository:
    async def list_all(self, limit: int, offset: int) -> list[Wallet]:
        wallets = [
            Wallet(id=1, address="wallet-1"),
            Wallet(id=2, address="wallet-2"),
            Wallet(id=3, address="wallet-3"),
        ]
        return wallets[offset : offset + limit]


class FakeScoringService:
    async def score_wallet(self, address: str) -> WalletScore:
        return WalletScore(
            wallet_address=address,
            score=50,
            grade="C",
            methodology_version="wallet-v1",
            activity_score=10,
            diversification_score=5,
            exit_experience_score=10,
            realized_performance_score=17.5,
            data_quality_score=7.5,
            realized_pnl_sol=0,
            realized_roi=0,
            unmatched_sell_ratio=0.25,
        )


class FakeSnapshotService:
    def __init__(self) -> None:
        self.wallet_ids: list[int] = []

    async def save(self, wallet_id: int, _: WalletScore) -> object:
        self.wallet_ids.append(wallet_id)
        return object()


@pytest.mark.asyncio
async def test_backfill_processes_wallets_in_batches() -> None:
    session: Any = None
    service = ScoreBackfillService(session)
    service_with_fakes: Any = service
    service_with_fakes.wallets = FakeWalletRepository()
    service_with_fakes.scoring = FakeScoringService()
    snapshots = FakeSnapshotService()
    service_with_fakes.snapshots = snapshots

    processed = await service.run(batch_size=2)

    assert processed == 3
    assert snapshots.wallet_ids == [1, 2, 3]
