from types import SimpleNamespace
from typing import Any

import pytest

from app.collectors.alpha_signal_collector import AlphaSignalCollector
from app.core.event_bus import EventBus
from app.core.events import AlphaSignalGenerated, TradeScored
from app.infrastructure.models import Alert


class AddressRepository:
    def __init__(self, entity: object) -> None:
        self.entity = entity

    async def get_by_address(self, address: str) -> object:
        return self.entity


class ScoreRepository:
    def __init__(self, score: float, grade: str) -> None:
        self.snapshot = SimpleNamespace(score=score, grade=grade)

    async def get_by_wallet_id(self, entity_id: int) -> object:
        return self.snapshot

    async def get_by_token_id(self, entity_id: int) -> object:
        return self.snapshot


class FakeAlerts:
    def __init__(self) -> None:
        self.calls = 0

    async def create_alpha_signal(self, event: TradeScored, *_: Any) -> Alert:
        self.calls += 1
        return Alert(severity="high", message="alpha")


@pytest.mark.asyncio
async def test_qualifying_buy_emits_alpha_signal() -> None:
    event_bus = EventBus()
    alerts = FakeAlerts()
    collector = AlphaSignalCollector(
        event_bus=event_bus,
        wallets=AddressRepository(SimpleNamespace(id=1)),  # type: ignore[arg-type]
        tokens=AddressRepository(SimpleNamespace(id=2)),  # type: ignore[arg-type]
        wallet_scores=ScoreRepository(82, "A"),  # type: ignore[arg-type]
        token_scores=ScoreRepository(70, "B"),  # type: ignore[arg-type]
        alerts=alerts,  # type: ignore[arg-type]
        wallet_threshold=65,
        token_threshold=65,
    )
    generated: list[AlphaSignalGenerated] = []

    async def capture(event: AlphaSignalGenerated) -> None:
        generated.append(event)

    collector.register()
    event_bus.subscribe(AlphaSignalGenerated, capture)
    await event_bus.publish(
        TradeScored(
            token_address="token",
            wallet="wallet",
            side="buy",
            amount=100,
            sol_change=-2.5,
            signature="signature",
        )
    )

    assert alerts.calls == 1
    assert len(generated) == 1
    assert generated[0].wallet_score == 82
    assert generated[0].token_score == 70
    assert generated[0].sol_amount == 2.5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("side", "wallet_score", "token_score", "signature"),
    [
        ("sell", 90, 90, "signature"),
        ("buy", 64, 90, "signature"),
        ("buy", 90, 64, "signature"),
        ("buy", 90, 90, None),
    ],
)
async def test_non_qualifying_trade_is_filtered(
    side: str,
    wallet_score: float,
    token_score: float,
    signature: str | None,
) -> None:
    event_bus = EventBus()
    alerts = FakeAlerts()
    collector = AlphaSignalCollector(
        event_bus=event_bus,
        wallets=AddressRepository(SimpleNamespace(id=1)),  # type: ignore[arg-type]
        tokens=AddressRepository(SimpleNamespace(id=2)),  # type: ignore[arg-type]
        wallet_scores=ScoreRepository(wallet_score, "B"),  # type: ignore[arg-type]
        token_scores=ScoreRepository(token_score, "B"),  # type: ignore[arg-type]
        alerts=alerts,  # type: ignore[arg-type]
        wallet_threshold=65,
        token_threshold=65,
    )
    collector.register()

    await event_bus.publish(
        TradeScored(
            token_address="token",
            wallet="wallet",
            side=side,
            amount=100,
            sol_change=-2.5,
            signature=signature,
        )
    )

    assert alerts.calls == 0
