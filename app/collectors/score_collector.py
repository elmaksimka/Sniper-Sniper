from __future__ import annotations

from app.core.event_bus import EventBus
from app.core.events import ScoreUpdated, WalletUpdated
from app.services.score_snapshot_service import ScoreSnapshotService
from app.services.scoring_service import ScoringService
from app.services.wallet_service import WalletService


class ScoreCollector:
    """Recalculate and materialize wallet scores after wallet updates."""

    def __init__(
        self,
        event_bus: EventBus,
        scoring_service: ScoringService,
        snapshot_service: ScoreSnapshotService,
        wallet_service: WalletService,
    ) -> None:
        self.event_bus = event_bus
        self.scoring_service = scoring_service
        self.snapshot_service = snapshot_service
        self.wallet_service = wallet_service

    def register(self) -> None:
        self.event_bus.subscribe(WalletUpdated, self.handle_wallet_updated)

    async def handle_wallet_updated(self, event: WalletUpdated) -> None:
        score = await self.scoring_service.score_wallet(event.wallet)
        if score is None:
            return

        wallet = await self.wallet_service.create_wallet(event.wallet)
        await self.snapshot_service.save(wallet.id, score)
        await self.event_bus.publish(
            ScoreUpdated(
                entity=event.wallet,
                score=score.score,
                grade=score.grade,
                methodology_version=score.methodology_version,
            )
        )
