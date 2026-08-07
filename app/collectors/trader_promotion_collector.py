from __future__ import annotations

from app.core.event_bus import EventBus
from app.core.events import ScoreUpdated
from app.core.logging import get_logger
from app.repositories.monitor_repository import MonitorRepository
from app.services.monitor_service import MonitorService


class TraderPromotionCollector:
    """Promote highly scored observed wallets into continuous monitoring."""

    def __init__(
        self,
        event_bus: EventBus,
        monitors: MonitorRepository,
        monitor_service: MonitorService,
        minimum_score: float,
        maximum_monitors: int,
    ) -> None:
        self.event_bus = event_bus
        self.monitors = monitors
        self.monitor_service = monitor_service
        self.minimum_score = minimum_score
        self.maximum_monitors = maximum_monitors
        self.logger = get_logger("trader-promotion")

    def register(self) -> None:
        self.event_bus.subscribe(ScoreUpdated, self.handle_score_updated)

    async def handle_score_updated(self, event: ScoreUpdated) -> None:
        if (
            event.entity_type != "wallet"
            or event.score < self.minimum_score
            or event.grade not in {"A", "B"}
        ):
            return
        existing = await self.monitors.get_by_address(event.entity)
        if existing is not None:
            if not existing.enabled:
                await self.monitors.set_enabled(existing, True)
            return
        if await self.monitors.count_enabled() >= self.maximum_monitors:
            self.logger.warning(
                "trader_promotion_capacity_reached",
                maximum=self.maximum_monitors,
            )
            return
        await self.monitor_service.add(event.entity)
        self.logger.info(
            "trader_promoted",
            wallet=event.entity,
            score=event.score,
            grade=event.grade,
        )
