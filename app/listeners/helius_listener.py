from app.core.event_bus import EventBus
from app.core.events import TokenCreated


class HeliusListener:
    """
    Listens for Solana blockchain events.

    Current version:
    mock listener.

    Later:
    will connect to Helius WebSocket/RPC.
    """

    def __init__(
        self,
        event_bus: EventBus,
    ):
        self.event_bus = event_bus

    async def start(self) -> None:
        """
        Start listening.

        Temporary mock implementation.
        """

        print(
            "Helius listener started"
        )

        await self.event_bus.publish(
            TokenCreated(
                token_address="HeliusDemoToken123",
                creator="DemoCreatorWallet",
            )
        )