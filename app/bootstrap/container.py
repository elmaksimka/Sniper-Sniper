from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.token_collector import TokenCollector
from app.core.event_bus import EventBus
from app.listeners.helius_client import HeliusClient
from app.listeners.helius_listener import HeliusListener
from app.services.token_service import TokenService


class Container:
    """
    Application dependency container.

    Responsible for creating and connecting
    application components.
    """

    def __init__(
        self,
        session: AsyncSession,
    ):
        self.session = session

        self.event_bus = EventBus()

        self.token_service = TokenService(
            session=session,
        )

        self.token_collector = TokenCollector(
            event_bus=self.event_bus,
            token_service=self.token_service,
        )

        self.helius_client = HeliusClient()

        self.helius_listener = HeliusListener(
            event_bus=self.event_bus,
            client=self.helius_client,
        )

    def setup(self) -> None:
        """
        Register event handlers.
        """

        self.token_collector.register()