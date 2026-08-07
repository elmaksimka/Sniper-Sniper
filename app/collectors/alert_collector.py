from __future__ import annotations

from app.core.event_bus import EventBus
from app.core.events import AlertGenerated, ScoreUpdated
from app.services.alert_service import AlertService


class AlertCollector:
    """Generate deduplicated alerts from score milestones."""

    def __init__(
        self,
        event_bus: EventBus,
        alert_service: AlertService,
        minimum_score: float,
        token_minimum_score: float | None = None,
    ) -> None:
        self.event_bus = event_bus
        self.alert_service = alert_service
        self.minimum_score = minimum_score
        self.token_minimum_score = (
            token_minimum_score
            if token_minimum_score is not None
            else minimum_score
        )

    def register(self) -> None:
        self.event_bus.subscribe(ScoreUpdated, self.handle_score_updated)

    async def handle_score_updated(self, event: ScoreUpdated) -> None:
        minimum_score = {
            "wallet": self.minimum_score,
            "token": self.token_minimum_score,
        }.get(event.entity_type)
        if (
            minimum_score is None
            or event.score < minimum_score
            or event.grade not in {"A", "B"}
        ):
            return

        alert = await self.alert_service.create_score_alert(event)
        if alert is None:
            return

        await self.event_bus.publish(
            AlertGenerated(
                entity=alert.entity_address,
                severity=alert.severity,
                dedupe_key=alert.dedupe_key,
                message=alert.message,
                metadata=alert.details,
            )
        )
