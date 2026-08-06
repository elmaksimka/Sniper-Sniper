import asyncio

from app.bootstrap.container import Container
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.infrastructure.database import async_session_factory, engine
from app.infrastructure.leader_election import PostgresLeaderElector
from app.listeners.helius_client import HeliusClient
from app.repositories.monitor_repository import MonitorRepository
from app.services.monitor_worker import MonitorWorker


async def run() -> None:
    settings = get_settings()
    helius_client = HeliusClient()
    leader = PostgresLeaderElector(engine, settings.worker_leader_lock_key)
    logger = get_logger("worker-supervisor")

    try:
        while True:
            try:
                acquired = await leader.try_acquire()
            except Exception:
                logger.exception("worker_leadership_acquisition_failed")
                await asyncio.sleep(settings.worker_standby_poll_seconds)
                continue

            if not acquired:
                await asyncio.sleep(settings.worker_standby_poll_seconds)
                continue
            if not await leader.verify():
                await asyncio.sleep(settings.worker_standby_poll_seconds)
                continue

            try:
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
            except Exception:
                logger.exception("monitor_poll_failed")

            await asyncio.sleep(settings.monitor_poll_interval_seconds)
    finally:
        await leader.release()
        await helius_client.aclose()
        await engine.dispose()


def main() -> None:
    setup_logging()
    asyncio.run(run())


if __name__ == "__main__":
    main()
