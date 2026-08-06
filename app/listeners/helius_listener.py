from app.core.event_bus import EventBus
from app.core.events import TokenCreated
from app.listeners.helius_client import HeliusClient


class HeliusListener:
    """
    Listens for Solana blockchain events.

    Uses Helius API to detect and enrich token data.
    """

    def __init__(
        self,
        event_bus: EventBus,
        client: HeliusClient,
    ):
        self.event_bus = event_bus
        self.client = client

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

        token_address = (
            "So11111111111111111111111111111111111111112"
        )

        asset_response = await self.client.get_asset(
            token_address,
        )

        if "error" in asset_response:
            print(
                "Helius asset error:",
                asset_response["error"],
            )
            return

        asset = asset_response.get(
            "result",
            {},
        )

        content = asset.get(
            "content",
            {},
        )

        metadata = content.get(
            "metadata",
            {},
        )

        token_info = asset.get(
            "token_info",
            {},
        )

        symbol = metadata.get(
            "symbol",
        )

        name = metadata.get(
            "name",
        )

        decimals = token_info.get(
            "decimals",
        )

        supply = token_info.get(
            "supply",
        )

        print(
            "Token discovered:",
            token_address,
            symbol,
            name,
            decimals,
            supply,
        )

        await self.event_bus.publish(
            TokenCreated(
                token_address=token_address,
                creator="HeliusListener",
                symbol=symbol,
                name=name,
                decimals=decimals,
                supply=supply,
            )
        )