from __future__ import annotations

from app.core.event_bus import EventBus
from app.core.events import ScoreUpdated
from app.core.logging import get_logger
from app.repositories.monitor_repository import MonitorRepository
from app.repositories.score_snapshot_repository import ScoreSnapshotRepository
from app.services.monitor_service import MonitorService
from app.services.trader_style_service import TraderStyleService


class TraderPromotionCollector:
    """Promote highly scored observed wallets into continuous monitoring."""

    def __init__(
        self,
        event_bus: EventBus,
        monitors: MonitorRepository,
        monitor_service: MonitorService,
        minimum_score: float,
        maximum_monitors: int,
        scores: ScoreSnapshotRepository | None = None,
        trader_style: TraderStyleService | None = None,
    ) -> None:
        self.event_bus = event_bus
        self.monitors = monitors
        self.monitor_service = monitor_service
        self.minimum_score = minimum_score
        self.maximum_monitors = maximum_monitors
        self.scores = scores
        self.trader_style = trader_style
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
        if not await self._has_holder_style(event.entity):
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

    async def reconcile(self) -> int:
        """Promote eligible persisted scores missed by an interrupted event."""
        if self.scores is None:
            return 0
        available = self.maximum_monitors - await self.monitors.count_enabled()
        if available <= 0:
            return 0

        promoted = 0
        snapshots = await self.scores.list_leaderboard(limit=1000, offset=0)
        for snapshot in snapshots:
            if promoted >= available or snapshot.score < self.minimum_score:
                break
            if snapshot.grade not in {"A", "B"}:
                continue
            address = snapshot.wallet.address
            if not await self._has_holder_style(address):
                continue
            if await self.monitors.get_by_address(address) is not None:
                continue
            await self.monitor_service.add(address)
            promoted += 1
            self.logger.info(
                "trader_reconciled",
                wallet=address,
                score=snapshot.score,
                grade=snapshot.grade,
            )
        return promoted

    async def _has_holder_style(self, address: str) -> bool:
        if self.trader_style is None:
            return True
        profile = await self.trader_style.evaluate(address)
        if profile.eligible:
            return True
        self.logger.info(
            "trader_style_rejected",
            wallet=address,
            reason=profile.reason,
            max_trades_60s=profile.max_trades_60s,
            max_trades_per_token=profile.max_trades_per_token,
            rapid_round_trips=profile.rapid_round_trips,
            long_hold_positions=profile.long_hold_positions,
        )
        return False
