import asyncio

from app.bootstrap.container import Container
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.infrastructure.database import async_session_factory, engine
from app.listeners.helius_client import HeliusClient
from app.repositories.monitor_repository import MonitorRepository
from app.services.monitor_worker import MonitorWorker


async def run() -> None:
    settings = get_settings()
    helius_client = HeliusClient()

    try:
        while True:
            async with async_session_factory() as session:
                container = Container(session, helius_client=helius_client)
                container.setup()
                worker = MonitorWorker(
                    monitors=MonitorRepository(session),
                    scanner=container.scanner,
                    detection=container.token_detection_service,
                    page_size=settings.monitor_page_size,
                    max_pages=settings.monitor_max_pages,
                )
                await worker.run_once()

            await asyncio.sleep(settings.monitor_poll_interval_seconds)
    finally:
        await helius_client.aclose()
        await engine.dispose()


def main() -> None:
    setup_logging()
    asyncio.run(run())


if __name__ == "__main__":
    main()
