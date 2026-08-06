from app.core.events import TokenCreated
from app.core.event_bus import EventBus
from app.services.token_service import TokenService


class TokenCollector:

    def __init__(
        self,
        event_bus: EventBus,
        token_service: TokenService,
    ):
        self.event_bus = event_bus
        self.token_service = token_service


    def register(self) -> None:

        self.event_bus.subscribe(
            TokenCreated,
            self.handle_token_created,
        )


    async def handle_token_created(
        self,
        event: TokenCreated,
    ) -> None:

        print(
            "Token event received:",
            event.token_address,
        )


        await self.token_service.create_token(
            address=event.token_address,
            creator=event.creator,
            symbol=event.symbol,
            name=event.name,
        )