import asyncio
from contextlib import suppress
import os
import socket
from typing import Any

from app.bootstrap.container import Container
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.infrastructure.database import async_session_factory, engine
from app.infrastructure.leader_election import PostgresLeaderElector
from app.listeners.helius_client import HeliusClient
from app.repositories.monitor_repository import MonitorRepository
from app.repositories.heartbeat_repository import HeartbeatRepository
from app.services.monitor_worker import MonitorWorker


async def heartbeat_loop(
    leader: PostgresLeaderElector,
    instance_id: str,
    interval_seconds: float,
    details: dict[str, Any],
) -> None:
    logger = get_logger("worker-heartbeat")
    while True:
        if leader.is_leader:
            try:
                async with async_session_factory() as session:
                    await HeartbeatRepository(session).beat(
                        "monitor-worker",
                        instance_id,
                        dict(details),
                    )
            except Exception:
                logger.exception("worker_heartbeat_failed")
        await asyncio.sleep(interval_seconds)


async def run() -> None:
    settings = get_settings()
    helius_client = HeliusClient()
    leader = PostgresLeaderElector(engine, settings.worker_leader_lock_key)
    logger = get_logger("worker-supervisor")
    instance_id = f"{socket.gethostname()}:{os.getpid()}"
    heartbeat_details: dict[str, Any] = {"state": "starting"}
    heartbeat_task = asyncio.create_task(
        heartbeat_loop(
            leader,
            instance_id,
            settings.worker_heartbeat_interval_seconds,
            heartbeat_details,
        )
    )

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
                    heartbeat_details["state"] = "polling"
                    container = Container(session, helius_client=helius_client)
                    container.setup()
                    worker = MonitorWorker(
                        monitors=MonitorRepository(session),
                        scanner=container.scanner,
                        detection=container.token_detection_service,
                        page_size=settings.monitor_page_size,
                        max_pages=settings.monitor_max_pages,
                    )
                    processed = await worker.run_once()
                    heartbeat_details.update(
                        state="idle",
                        processed_transactions=processed,
                    )
            except Exception:
                heartbeat_details["state"] = "error"
                logger.exception("monitor_poll_failed")

            await asyncio.sleep(settings.monitor_poll_interval_seconds)
    finally:
        heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat_task
        await leader.release()
        await helius_client.aclose()
        await engine.dispose()


def main() -> None:
    setup_logging()
    asyncio.run(run())


if __name__ == "__main__":
    main()
