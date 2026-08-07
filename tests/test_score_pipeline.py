from datetime import UTC, datetime
from typing import Any

import pytest

from app.collectors.score_collector import ScoreCollector
from app.collectors.trade_collector import TradeCollector
from app.core.event_bus import EventBus
from app.core.events import ScoreUpdated, TradeObserved
from app.core.scoring import TokenScore, WalletScore
from app.infrastructure.models import Token, Wallet


class FakeTokenService:
    async def create_token(self, address: str) -> Token:
        return Token(id=1, address=address)


class FakeWalletService:
    async def create_wallet(self, address: str) -> Wallet:
        return Wallet(id=2, address=address)


class FakeTradeService:
    def __init__(self) -> None:
        self.created = False

    async def create_trade(self, **_: Any) -> object:
        self.created = True
        return object()


class FakeScoringService:
    async def score_wallet(self, address: str) -> WalletScore:
        return WalletScore(
            wallet_address=address,
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

    async def score_token(self, address: str) -> TokenScore:
        return TokenScore(
            token_address=address,
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


class FakeSnapshotService:
    def __init__(self) -> None:
        self.saved: tuple[int, WalletScore] | None = None

    async def save(self, wallet_id: int, score: WalletScore) -> object:
        self.saved = (wallet_id, score)
        return object()


class FakeTokenSnapshotService:
    def __init__(self) -> None:
        self.saved: tuple[int, TokenScore] | None = None

    async def save(self, token_id: int, score: TokenScore) -> object:
        self.saved = (token_id, score)
        return object()


@pytest.mark.asyncio
async def test_trade_persistence_triggers_score_snapshot_pipeline() -> None:
    event_bus = EventBus()
    token_service: Any = FakeTokenService()
    wallet_service: Any = FakeWalletService()
    trade_service: Any = FakeTradeService()
    scoring_service: Any = FakeScoringService()
    snapshot_service: Any = FakeSnapshotService()
    token_snapshot_service: Any = FakeTokenSnapshotService()

    trade_collector = TradeCollector(
        event_bus,
        token_service,
        wallet_service,
        trade_service,
    )
    score_collector = ScoreCollector(
        event_bus,
        scoring_service,
        snapshot_service,
        wallet_service,
        token_snapshot_service,
        token_service,
    )
    score_events: list[ScoreUpdated] = []

    async def capture_score(event: ScoreUpdated) -> None:
        score_events.append(event)

    trade_collector.register()
    score_collector.register()
    event_bus.subscribe(ScoreUpdated, capture_score)

    await event_bus.publish(
        TradeObserved(
            token_address="mint",
            wallet="wallet",
            side="buy",
            amount=10,
            price=0.1,
            sol_change=-1,
            signature="signature",
            transaction_at=datetime.now(UTC),
        )
    )

    assert trade_service.created is True
    assert snapshot_service.saved is not None
    assert snapshot_service.saved[0] == 2
    assert snapshot_service.saved[1].score == 75
    assert token_snapshot_service.saved is not None
    assert token_snapshot_service.saved[0] == 1
    assert token_snapshot_service.saved[1].score == 70
    assert len(score_events) == 1
    assert score_events[0].entity == "wallet"
    assert score_events[0].score == 75
    assert score_events[0].grade == "B"
    assert score_events[0].methodology_version == "wallet-v1"
