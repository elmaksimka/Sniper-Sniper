from __future__ import annotations

from app.core.event_bus import EventBus
from app.core.events import TokenCreated
from app.listeners.helius_client import HeliusClient
from app.listeners.transaction_scanner import TransactionScanner


class TokenDetectionService:
    """
    Service responsible for detecting new tokens
    and enriching them with Helius metadata.
    """

    def __init__(
        self,
        scanner: TransactionScanner,
        event_bus: EventBus,
        client: HeliusClient,
    ):
        self.scanner = scanner
        self.event_bus = event_bus
        self.client = client

    async def scan_wallet(
        self,
        wallet: str,
        limit: int = 5,
    ) -> None:

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

                metadata = await self.get_metadata(
                    token_address,
                )

                print(
                    "New token detected:",
                    token_address,
                    metadata.get("symbol"),
                    metadata.get("name"),
                )

                await self.event_bus.publish(
                    TokenCreated(
                        token_address=token_address,
                        creator=metadata.get(
                            "creator",
                            "unknown",
                        ),
                        symbol=metadata.get(
                            "symbol",
                        ),
                        name=metadata.get(
                            "name",
                        ),
                        decimals=metadata.get(
                            "decimals",
                        ),
                        supply=metadata.get(
                            "supply",
                        ),
                    )
                )


    async def get_metadata(
        self,
        token_address: str,
    ) -> dict:
        """
        Fetch token metadata from Helius DAS API.
        """

        response = await self.client.get_asset(
            token_address,
        )

        if "error" in response:

            print(
                "Metadata error:",
                response["error"],
            )

            return {}

        asset = response.get(
            "result",
            {},
        )


        content = asset.get(
            "content",
            {},
        )

        metadata = content.get(
            "metadata",
            {}
        )


        token_info = asset.get(
            "token_info",
            {}
        )


        ownership = asset.get(
            "ownership",
            {}
        )


        return {
            "symbol": metadata.get(
                "symbol",
            ),

            "name": metadata.get(
                "name",
            ),

            "creator": ownership.get(
                "owner",
            ),

            "decimals": token_info.get(
                "decimals",
            ),

            "supply": token_info.get(
                "supply",
            ),
        }