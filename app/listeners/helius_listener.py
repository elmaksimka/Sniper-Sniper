from app.core.event_bus import EventBus
from app.core.events import TokenCreated
from app.listeners.helius_client import HeliusClient


class HeliusListener:
    """
    Listens for Solana blockchain events.

    Uses HeliusClient as external data source.
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

        Temporary mock event.
        """

        print(
            "Helius listener started"
        )

        health = await self.client.get_health()

        print(
            "Helius health:",
            health,
        )

        await self.event_bus.publish(
            TokenCreated(
                token_address="HeliusDemoToken123",
                creator="DemoCreatorWallet",
            )
        )