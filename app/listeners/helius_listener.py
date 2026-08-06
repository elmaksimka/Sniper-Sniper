from __future__ import annotations

from app.core.event_bus import EventBus
from app.core.events import TokenCreated
from app.listeners.helius_client import HeliusClient
from app.services.token_detector import TokenDetector
from app.services.transaction_scanner import TransactionScanner


class HeliusListener:
    """
    Listens for Solana blockchain events.

    Uses Helius API to discover token creation.
    """

    def __init__(
        self,
        event_bus: EventBus,
        client: HeliusClient,
        detector: TokenDetector,
        scanner: TransactionScanner,
    ):
        self.event_bus = event_bus
        self.client = client
        self.detector = detector
        self.scanner = scanner

    async def start(self) -> None:
        """
        Start listening.
        """

        print(
            "Helius listener started"
        )

        health = await self.client.get_health()

        print(
            "Helius health:",
            health,
        )

        signatures_response = await self.client.get_signatures(
            address="So11111111111111111111111111111111111111112",
            limit=5,
        )

        signatures = [
            item["signature"]
            for item in signatures_response.get(
                "result",
                [],
            )
        ]

        for signature in signatures:
            transaction = await self.client.get_transaction(
                signature,
            )

            token_address = self.detector.detect(
                transaction,
            )

            if not token_address:
                continue

            print(
                "Token detected:",
                token_address,
            )

            await self.event_bus.publish(
                TokenCreated(
                    token_address=token_address,
                    creator="HeliusListener",
                )
            )

            break