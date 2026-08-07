from __future__ import annotations

from app.core.event_bus import EventBus
from app.core.events import NativeTransferObserved
from app.services.funding_service import FundingService
from app.services.wallet_service import WalletService


class FundingCollector:
    def __init__(
        self,
        event_bus: EventBus,
        wallet_service: WalletService,
        funding_service: FundingService,
    ) -> None:
        self.event_bus = event_bus
        self.wallet_service = wallet_service
        self.funding_service = funding_service

    def register(self) -> None:
        self.event_bus.subscribe(
            NativeTransferObserved,
            self.handle_native_transfer,
        )

    async def handle_native_transfer(self, event: NativeTransferObserved) -> None:
        source = await self.wallet_service.create_wallet(event.source)
        destination = await self.wallet_service.create_wallet(event.destination)
        await self.funding_service.create_transfer(
            source_wallet_id=source.id,
            destination_wallet_id=destination.id,
            amount_sol=event.amount_sol,
            signature=event.signature,
            instruction_index=event.instruction_index,
            timestamp=event.transaction_at,
        )
