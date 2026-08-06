from app.core.event_bus import EventBus
from app.core.events import TokenCreated
from app.services.token_discovery import TokenDiscovery


class HeliusListener:
    """
    Listens for Solana blockchain events.

    Uses Helius API to discover tokens.
    """

    def __init__(
        self,
        event_bus: EventBus,
        discovery: TokenDiscovery,
    ):
        self.event_bus = event_bus
        self.discovery = discovery

    async def start(self) -> None:
        """
        Start listening.
        """

        print(
            "Helius listener started"
        )

        token_address = (
            "So11111111111111111111111111111111111111112"
        )

        token = await self.discovery.discover(
            token_address,
        )

        if not token:
            return

        print(
            "Token discovered:",
            token["address"],
            token["symbol"],
            token["name"],
        )

        await self.event_bus.publish(
            TokenCreated(
                token_address=token["address"],
                creator="HeliusListener",
                symbol=token["symbol"],
                name=token["name"],
            )
        )