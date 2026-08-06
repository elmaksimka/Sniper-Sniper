from datetime import UTC, datetime
from typing import Any

import pytest

from app.analyzer import TokenTrade
from app.core.event_bus import EventBus
from app.core.events import TokenCreated, TradeObserved
from app.services.token_detection_service import TokenDetectionService
from app.services.token_store import TokenStore


class FakeScanner:
    async def scan_address(
        self,
        wallet: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        assert wallet == "wallet"
        assert limit == 2
        return [
            {
                "signature": "signature",
                "timestamp": 1_700_000_000,
                "tokens": ["mint"],
                "trades": [
                    TokenTrade(
                        mint="mint",
                        wallet="wallet",
                        sol_change=-0.5,
                        token_change=2.0,
                    )
                ],
            }
        ]


class FakeMetadataService:
    async def get_metadata(self, mint: str) -> dict[str, Any]:
        assert mint == "mint"
        return {
            "name": "Token",
            "symbol": "TKN",
            "creator": "creator",
            "decimals": 6,
            "supply": 1_000_000,
        }


@pytest.mark.asyncio
async def test_scan_wallet_publishes_token_then_trade_events() -> None:
    event_bus = EventBus()
    published: list[TokenCreated | TradeObserved] = []

    async def capture_token(event: TokenCreated) -> None:
        published.append(event)

    async def capture_trade(event: TradeObserved) -> None:
        published.append(event)

    event_bus.subscribe(TokenCreated, capture_token)
    event_bus.subscribe(TradeObserved, capture_trade)

    scanner: Any = FakeScanner()
    metadata: Any = FakeMetadataService()
    service = TokenDetectionService(
        scanner=scanner,
        store=TokenStore(),
        metadata=metadata,
        event_bus=event_bus,
    )

    result = await service.scan_wallet("wallet", limit=2)

    assert result == ["mint"]
    assert isinstance(published[0], TokenCreated)
    assert published[0].token_address == "mint"
    assert published[0].creator == "creator"
    assert published[1] == TradeObserved(
        token_address="mint",
        wallet="wallet",
        side="buy",
        amount=2.0,
        price=0.25,
        sol_change=-0.5,
        signature="signature",
        transaction_at=datetime.fromtimestamp(1_700_000_000, UTC),
        id=published[1].id,
        created_at=published[1].created_at,
    )

    await service.scan_wallet("wallet", limit=2)

    assert len([event for event in published if isinstance(event, TokenCreated)]) == 1
    assert len([event for event in published if isinstance(event, TradeObserved)]) == 2
