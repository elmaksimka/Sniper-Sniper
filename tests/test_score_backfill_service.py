from typing import Any

import pytest

from app.core.scoring import TokenScore, WalletScore
from app.infrastructure.models import Token, Wallet
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

    async def score_token(self, address: str) -> TokenScore:
        return TokenScore(
            token_address=address,
            score=50,
            grade="C",
            methodology_version="token-v1",
            activity_score=10,
            participation_score=5,
            holder_distribution_score=10,
            flow_balance_score=5,
            creator_history_score=10,
            data_quality_score=10,
            observed_holder_count=2,
            top_holder_share=0.5,
            incomplete_holder_ratio=0,
        )


class FakeSnapshotService:
    def __init__(self) -> None:
        self.wallet_ids: list[int] = []

    async def save(self, wallet_id: int, _: WalletScore) -> object:
        self.wallet_ids.append(wallet_id)
        return object()


class FakeTokenRepository:
    async def list_all(
        self,
        limit: int,
        offset: int,
        creator: str | None = None,
    ) -> list[Token]:
        tokens = [Token(id=1, address="mint-1"), Token(id=2, address="mint-2")]
        return tokens[offset : offset + limit]


class FakeTokenSnapshotService:
    def __init__(self) -> None:
        self.token_ids: list[int] = []

    async def save(self, token_id: int, _: TokenScore) -> object:
        self.token_ids.append(token_id)
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


@pytest.mark.asyncio
async def test_backfill_processes_tokens_in_batches() -> None:
    session: Any = None
    service = ScoreBackfillService(session)
    service_with_fakes: Any = service
    service_with_fakes.tokens = FakeTokenRepository()
    service_with_fakes.scoring = FakeScoringService()
    snapshots = FakeTokenSnapshotService()
    service_with_fakes.token_snapshots = snapshots

    processed = await service.run_tokens(batch_size=1)

    assert processed == 2
    assert snapshots.token_ids == [1, 2]
