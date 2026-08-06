from datetime import UTC, datetime
from typing import Any

import pytest

from app.collectors.alert_collector import AlertCollector
from app.core.event_bus import EventBus
from app.core.events import AlertGenerated, ScoreUpdated
from app.infrastructure.models import Alert


class FakeAlertService:
    def __init__(self) -> None:
        self.calls = 0
        self.keys: set[str] = set()

    async def create_score_alert(self, event: ScoreUpdated) -> Alert | None:
        self.calls += 1
        key = f"{event.entity}:{event.methodology_version}:{event.grade}"
        if key in self.keys:
            return None
        self.keys.add(key)
        return Alert(
            id=1,
            entity_type="wallet",
            entity_address=event.entity,
            alert_type="wallet_score_grade",
            severity="critical" if event.grade == "A" else "high",
            message="milestone",
            details={"score": event.score},
            dedupe_key=key,
            created_at=datetime.now(UTC),
        )


@pytest.mark.asyncio
async def test_alert_collector_filters_and_deduplicates_milestones() -> None:
    event_bus = EventBus()
    service: Any = FakeAlertService()
    collector = AlertCollector(event_bus, service, minimum_score=65)
    generated: list[AlertGenerated] = []

    async def capture(event: AlertGenerated) -> None:
        generated.append(event)

    collector.register()
    event_bus.subscribe(AlertGenerated, capture)

    await event_bus.publish(
        ScoreUpdated(
            entity="wallet",
            score=50,
            grade="C",
            methodology_version="wallet-v1",
        )
    )
    milestone = ScoreUpdated(
        entity="wallet",
        score=75,
        grade="B",
        methodology_version="wallet-v1",
    )
    await event_bus.publish(milestone)
    await event_bus.publish(milestone)

    assert service.calls == 2
    assert len(generated) == 1
    assert generated[0].entity == "wallet"
    assert generated[0].severity == "high"
