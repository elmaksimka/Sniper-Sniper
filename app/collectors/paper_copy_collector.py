from __future__ import annotations

from app.core.event_bus import EventBus
from app.core.events import TradeScored
from app.services.paper_copy_service import PaperCopyService


class PaperCopyCollector:
    def __init__(self, event_bus: EventBus, service: PaperCopyService) -> None:
        self.event_bus = event_bus
        self.service = service

    def register(self) -> None:
        self.event_bus.subscribe(TradeScored, self.handle_trade_scored)

    async def handle_trade_scored(self, event: TradeScored) -> None:
        await self.service.enqueue_trade(event)
