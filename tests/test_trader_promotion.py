from types import SimpleNamespace

import pytest

from app.collectors.trader_promotion_collector import TraderPromotionCollector
from app.core.event_bus import EventBus
from app.core.events import ScoreUpdated
from app.core.trader_style import TraderStyleProfile


class FakeMonitors:
    def __init__(self, count: int = 0) -> None:
        self.count = count

    async def get_by_address(self, address: str) -> None:
        return None

    async def count_enabled(self) -> int:
        return self.count


class FakeMonitorService:
    def __init__(self) -> None:
        self.added: list[str] = []

    async def add(self, address: str) -> object:
        self.added.append(address)
        return SimpleNamespace()


class FakeScores:
    async def list_leaderboard(self, **_: object) -> list[object]:
        return [
            SimpleNamespace(
                score=70,
                grade="B",
                wallet=SimpleNamespace(address="persisted-wallet"),
            )
        ]

    async def get_by_wallet_address(self, address: str) -> object:
        return SimpleNamespace(score=82, grade="A")


class RejectedStyle:
    async def evaluate(self, address: str) -> TraderStyleProfile:
        return TraderStyleProfile(
            eligible=False,
            reason="rapid_round_trip",
            total_trades=20,
            unique_tokens=5,
            max_trades_60s=4,
            max_distinct_tokens_60s=3,
            max_trades_per_token=4,
            max_side_switches_per_token=3,
            rapid_round_trips=1,
            long_hold_positions=2,
        )


def wallet_score(score: float, grade: str = "B") -> ScoreUpdated:
    return ScoreUpdated(
        entity_type="wallet",
        entity="wallet",
        score=score,
        grade=grade,
        methodology_version="wallet-v1",
    )


@pytest.mark.asyncio
async def test_high_score_wallet_is_promoted() -> None:
    event_bus = EventBus()
    service = FakeMonitorService()
    collector = TraderPromotionCollector(
        event_bus,
        FakeMonitors(),  # type: ignore[arg-type]
        service,  # type: ignore[arg-type]
        minimum_score=65,
        maximum_monitors=100,
    )
    collector.register()

    await event_bus.publish(wallet_score(70))

    assert service.added == ["wallet"]


@pytest.mark.asyncio
async def test_low_score_or_full_capacity_is_not_promoted() -> None:
    event_bus = EventBus()
    service = FakeMonitorService()
    collector = TraderPromotionCollector(
        event_bus,
        FakeMonitors(count=100),  # type: ignore[arg-type]
        service,  # type: ignore[arg-type]
        minimum_score=65,
        maximum_monitors=100,
    )
    collector.register()

    await event_bus.publish(wallet_score(64, "C"))
    await event_bus.publish(wallet_score(90, "A"))

    assert service.added == []


@pytest.mark.asyncio
async def test_high_score_bot_style_is_not_promoted() -> None:
    event_bus = EventBus()
    service = FakeMonitorService()
    collector = TraderPromotionCollector(
        event_bus,
        FakeMonitors(),  # type: ignore[arg-type]
        service,  # type: ignore[arg-type]
        minimum_score=65,
        maximum_monitors=100,
        trader_style=RejectedStyle(),  # type: ignore[arg-type]
    )
    collector.register()

    await event_bus.publish(wallet_score(80, "A"))

    assert service.added == []


@pytest.mark.asyncio
async def test_reconcile_promotes_persisted_eligible_wallet() -> None:
    service = FakeMonitorService()
    collector = TraderPromotionCollector(
        EventBus(),
        FakeMonitors(),  # type: ignore[arg-type]
        service,  # type: ignore[arg-type]
        minimum_score=65,
        maximum_monitors=100,
        scores=FakeScores(),  # type: ignore[arg-type]
    )

    promoted = await collector.reconcile()

    assert promoted == 1
    assert service.added == ["persisted-wallet"]


@pytest.mark.asyncio
async def test_completed_audit_can_promote_one_persisted_address() -> None:
    service = FakeMonitorService()
    collector = TraderPromotionCollector(
        EventBus(),
        FakeMonitors(),  # type: ignore[arg-type]
        service,  # type: ignore[arg-type]
        minimum_score=65,
        maximum_monitors=100,
        scores=FakeScores(),  # type: ignore[arg-type]
    )

    promoted = await collector.promote_address("audited-wallet")

    assert promoted is True
    assert service.added == ["audited-wallet"]
