import asyncio
from contextlib import suppress
import os
import signal
import socket
from typing import Any

from app.bootstrap.container import Container
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.infrastructure.database import async_session_factory, engine
from app.infrastructure.leader_election import PostgresLeaderElector
from app.listeners.helius_client import HeliusClient
from app.notifications.telegram import TelegramNotifier
from app.repositories.monitor_repository import MonitorRepository
from app.repositories.heartbeat_repository import HeartbeatRepository
from app.repositories.score_snapshot_repository import ScoreSnapshotRepository
from app.services.candidate_enrichment_service import CandidateEnrichmentService
from app.services.monitor_worker import MonitorWorker
from app.services.activity_stats_service import ActivityStatsService


async def heartbeat_loop(
    leader: PostgresLeaderElector,
    instance_id: str,
    interval_seconds: float,
    details: dict[str, Any],
    stop_event: asyncio.Event,
) -> None:
    logger = get_logger("worker-heartbeat")
    while not stop_event.is_set():
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
        await wait_for_stop(stop_event, interval_seconds)


async def wait_for_stop(
    stop_event: asyncio.Event,
    timeout_seconds: float,
) -> bool:
    try:
        await asyncio.wait_for(stop_event.wait(), timeout_seconds)
    except TimeoutError:
        return False
    return True


def discovery_retry_delay(
    interval_seconds: float,
    maximum_seconds: float,
    consecutive_failures: int,
) -> float:
    """Return the normal interval or bounded exponential discovery backoff."""
    if consecutive_failures <= 0:
        return interval_seconds
    return min(
        interval_seconds * (2**consecutive_failures),
        maximum_seconds,
    )


async def run(stop_event: asyncio.Event | None = None) -> None:
    stop_event = stop_event or asyncio.Event()
    settings = get_settings()
    helius_client = HeliusClient()
    telegram = TelegramNotifier(
        settings.telegram_bot_token,
        settings.telegram_recipients,
    )
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
            stop_event,
        )
    )
    next_discovery_at = 0.0
    next_status_at = 0.0
    discovery_failures = 0
    worker_announced = False

    try:
        while not stop_event.is_set():
            try:
                acquired = await leader.try_acquire()
            except Exception:
                logger.exception("worker_leadership_acquisition_failed")
                await wait_for_stop(
                    stop_event,
                    settings.worker_standby_poll_seconds,
                )
                continue

            if not acquired:
                await wait_for_stop(
                    stop_event,
                    settings.worker_standby_poll_seconds,
                )
                continue
            if not await leader.verify():
                await wait_for_stop(
                    stop_event,
                    settings.worker_standby_poll_seconds,
                )
                continue
            if stop_event.is_set():
                break

            if not worker_announced:
                await telegram.send_worker_started(
                    settings.monitor_poll_interval_seconds,
                    settings.discovery_poll_interval_seconds,
                    settings.discovery_page_size,
                    len(settings.discovery_programs),
                )
                worker_announced = True
                next_status_at = 0.0

            try:
                async with async_session_factory() as session:
                    heartbeat_details["state"] = "polling"
                    container = Container(session, helius_client=helius_client)
                    container.setup()
                    monitor_worker = MonitorWorker(
                        monitors=MonitorRepository(session),
                        scanner=container.scanner,
                        detection=container.token_detection_service,
                        page_size=settings.monitor_page_size,
                        max_pages=settings.monitor_max_pages,
                    )
                    processed = await monitor_worker.run_once()
                    heartbeat_details["processed_transactions"] = processed
                    now = asyncio.get_running_loop().time()
                    if settings.discovery_enabled and now >= next_discovery_at:
                        discovered = 0
                        discovery_failed = False
                        for program_id in settings.discovery_programs:
                            try:
                                discovery = (
                                    await container.dex_discovery_service.scan_program(
                                        program_id
                                    )
                                )
                                if not discovery.complete:
                                    logger.warning(
                                        "dex_discovery_gap_sampled",
                                        program_id=program_id,
                                    )
                                discovered += discovery.processed_transactions
                            except Exception:
                                discovery_failed = True
                                logger.exception(
                                    "dex_discovery_program_failed",
                                    program_id=program_id,
                                )
                        previous_failures = discovery_failures
                        discovery_failures = (
                            discovery_failures + 1 if discovery_failed else 0
                        )
                        delay = discovery_retry_delay(
                            settings.discovery_poll_interval_seconds,
                            settings.discovery_retry_max_seconds,
                            discovery_failures,
                        )
                        next_discovery_at = asyncio.get_running_loop().time() + delay
                        heartbeat_details.update(
                            discovered_transactions=discovered,
                            discovery_failures=discovery_failures,
                            discovery_next_poll_seconds=delay,
                        )
                        if discovery_failed and previous_failures == 0:
                            await telegram.send_discovery_degraded(
                                discovery_failures,
                                delay,
                            )
                        elif not discovery_failed and previous_failures > 0:
                            await telegram.send_discovery_recovered()
                        if (
                            settings.candidate_enrichment_enabled
                            and not discovery_failed
                        ):
                            try:
                                enrichment = await CandidateEnrichmentService(
                                    scores=ScoreSnapshotRepository(session),
                                    monitors=MonitorRepository(session),
                                    scanner=container.scanner,
                                    detection=container.token_detection_service,
                                    cursors=HeartbeatRepository(session),
                                    minimum_score=(
                                        settings.candidate_enrichment_min_score
                                    ),
                                    history_limit=(
                                        settings.candidate_enrichment_history_limit
                                    ),
                                    maximum_candidates=(
                                        settings.candidate_enrichment_max_per_cycle
                                    ),
                                    retry_seconds=(
                                        settings.candidate_enrichment_retry_seconds
                                    ),
                                ).run_once()
                                reconciled = await (
                                    container.trader_promotion_collector.reconcile()
                                )
                                heartbeat_details.update(
                                    candidate_wallets_enriched=(
                                        enrichment.wallets_enriched
                                    ),
                                    candidate_history_transactions=(
                                        enrichment.transactions_processed
                                    ),
                                    candidate_wallets_promoted=(
                                        enrichment.wallets_promoted + reconciled
                                    ),
                                )
                            except Exception:
                                logger.exception("candidate_enrichment_cycle_failed")
                    heartbeat_details["state"] = "idle"
            except Exception:
                heartbeat_details["state"] = "error"
                logger.exception("monitor_poll_failed")

            if (
                worker_announced
                and asyncio.get_running_loop().time() >= next_status_at
            ):
                try:
                    async with async_session_factory() as status_session:
                        stats = await ActivityStatsService(status_session).get(
                            settings.telegram_status_window_minutes
                        )
                    heartbeat_details.update(
                        total_transactions=stats.total_transactions,
                        total_tokens=stats.total_tokens,
                        recent_transactions=stats.recent_transactions,
                        recent_tokens=stats.recent_tokens,
                        status_window_minutes=stats.window_minutes,
                    )
                except Exception:
                    logger.exception("worker_activity_stats_failed")
                await telegram.send_worker_status(dict(heartbeat_details))
                next_status_at = (
                    asyncio.get_running_loop().time()
                    + settings.telegram_status_interval_seconds
                )

            await wait_for_stop(
                stop_event,
                settings.monitor_poll_interval_seconds,
            )
    finally:
        if worker_announced:
            await telegram.send_worker_stopped()
        heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat_task
        await leader.release()
        await helius_client.aclose()
        await engine.dispose()


async def run_with_signals() -> None:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    logger = get_logger("worker-supervisor")
    registered_signals: list[signal.Signals] = []

    def request_shutdown(signal_name: str) -> None:
        logger.info("worker_shutdown_requested", signal=signal_name)
        stop_event.set()

    for signal_number in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(
                signal_number,
                request_shutdown,
                signal_number.name,
            )
        except NotImplementedError:
            continue
        registered_signals.append(signal_number)

    try:
        await run(stop_event)
    finally:
        for signal_number in registered_signals:
            loop.remove_signal_handler(signal_number)


def main() -> None:
    setup_logging()
    asyncio.run(run_with_signals())


if __name__ == "__main__":
    main()
