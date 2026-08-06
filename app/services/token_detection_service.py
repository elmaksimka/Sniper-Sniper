from __future__ import annotations

from app.core.event_bus import EventBus
from app.core.events import TokenCreated
from app.listeners.transaction_scanner import TransactionScanner


class TokenDetectionService:
    """
    Service responsible for scanning transactions
    and publishing token discovery events.
    """

    def __init__(
        self,
        scanner: TransactionScanner,
        event_bus: EventBus,
    ):
        self.scanner = scanner
        self.event_bus = event_bus

    async def scan_wallet(
        self,
        wallet: str,
        limit: int = 5,
    ) -> None:
        """
        Scan wallet transactions and publish
        TokenCreated events for discovered tokens.
        """

        transactions = await self.scanner.scan_address(
            wallet,
            limit,
        )

        discovered: set[str] = set()

        for transaction in transactions:
            tokens = transaction.get(
                "tokens",
                [],
            )

            for token_address in tokens:
                if token_address in discovered:
                    continue

                discovered.add(
                    token_address
                )

                print(
                    "New token detected:",
                    token_address,
                )

                await self.event_bus.publish(
                    TokenCreated(
                        token_address=token_address,
                        creator="TokenDetectionService",
                    )
                )