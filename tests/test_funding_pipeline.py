from datetime import UTC, datetime
from typing import Any

import pytest

from app.collectors.funding_collector import FundingCollector
from app.core.event_bus import EventBus
from app.core.events import NativeTransferObserved
from app.infrastructure.models import Wallet


class FakeWalletService:
    async def create_wallet(self, address: str) -> Wallet:
        identifiers = {"source": 1, "destination": 2}
        return Wallet(id=identifiers[address], address=address)


class FakeFundingService:
    def __init__(self) -> None:
        self.created: dict[str, Any] | None = None

    async def create_transfer(self, **values: Any) -> object:
        self.created = values
        return object()


@pytest.mark.asyncio
async def test_native_transfer_event_persists_funding_relationship() -> None:
    event_bus = EventBus()
    wallets: Any = FakeWalletService()
    funding: Any = FakeFundingService()
    collector = FundingCollector(event_bus, wallets, funding)
    collector.register()
    observed_at = datetime.now(UTC)

    await event_bus.publish(
        NativeTransferObserved(
            source="source",
            destination="destination",
            amount_sol=1.5,
            instruction_index="inner:2:0",
            signature="signature",
            transaction_at=observed_at,
        )
    )

    assert funding.created == {
        "source_wallet_id": 1,
        "destination_wallet_id": 2,
        "amount_sol": 1.5,
        "signature": "signature",
        "instruction_index": "inner:2:0",
        "timestamp": observed_at,
    }
