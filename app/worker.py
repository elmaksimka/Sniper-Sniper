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


async def telegram_status_loop(
    leader: PostgresLeaderElector,
    telegram: TelegramNotifier,
    interval_seconds: float,
    window_minutes: int,
    details: dict[str, Any],
    stop_event: asyncio.Event,
) -> None:
    """Send periodic worker reports independently from RPC processing."""
    logger = get_logger("worker-telegram-status")
    while not await wait_for_stop(stop_event, interval_seconds):
        if not leader.is_leader:
            continue

        report_details = dict(details)
        try:
            async with async_session_factory() as session:
                stats = await ActivityStatsService(session).get(window_minutes)
            report_details.update(
                total_transactions=stats.total_transactions,
                total_tokens=stats.total_tokens,
                recent_transactions=stats.recent_transactions,
                recent_tokens=stats.recent_tokens,
                status_window_minutes=stats.window_minutes,
            )
        except Exception:
            logger.exception("worker_activity_stats_failed")

        results = await telegram.send_worker_status(report_details)
        logger.info(
            "worker_status_sent",
            recipients_succeeded=sum(results.values()),
            recipients_total=len(results),
        )


async def candidate_enrichment_loop(
    leader: PostgresLeaderElector,
    helius_client: HeliusClient,
    interval_seconds: float,
    minimum_score: float,
    history_limit: int,
    maximum_candidates: int,
    retry_seconds: float,
    details: dict[str, Any],
    stop_event: asyncio.Event,
) -> None:
    """Enrich candidate wallets without delaying DEX discovery."""
    logger = get_logger("candidate-enrichment-supervisor")

    # Let the first discovery cycle claim the shared RPC capacity.
    if await wait_for_stop(stop_event, interval_seconds):
        return

    while not stop_event.is_set():
        if leader.is_leader:
            details["candidate_state"] = "polling"
            try:
                async with async_session_factory() as session:
                    container = Container(session, helius_client=helius_client)
                    container.setup()
                    enrichment = await CandidateEnrichmentService(
                        scores=ScoreSnapshotRepository(session),
                        monitors=MonitorRepository(session),
                        scanner=container.scanner,
                        detection=container.token_detection_service,
                        cursors=HeartbeatRepository(session),
                        minimum_score=minimum_score,
                        history_limit=history_limit,
                        maximum_candidates=maximum_candidates,
                        retry_seconds=retry_seconds,
                    ).run_once()
                    reconciled = (
                        await container.trader_promotion_collector.reconcile()
                    )
                    details.update(
                        candidate_state="idle",
                        candidate_wallets_enriched=enrichment.wallets_enriched,
                        candidate_history_transactions=(
                            enrichment.transactions_processed
                        ),
                        candidate_wallets_promoted=(
                            enrichment.wallets_promoted + reconciled
                        ),
                        candidate_last_wallet=enrichment.last_wallet or "",
                        candidate_last_score_before=(
                            enrichment.last_score_before
                        ),
                        candidate_last_score_after=enrichment.last_score_after,
                        candidate_history_limit=enrichment.history_limit,
                    )
            except Exception:
                details["candidate_state"] = "error"
                logger.exception("candidate_enrichment_cycle_failed")

        await wait_for_stop(stop_event, interval_seconds)


async def discovery_loop(
    leader: PostgresLeaderElector,
    helius_client: HeliusClient,
    telegram: TelegramNotifier,
    program_ids: tuple[str, ...],
    interval_seconds: float,
    retry_max_seconds: float,
    details: dict[str, Any],
    stop_event: asyncio.Event,
) -> None:
    """Discover DEX trades without delaying monitored-wallet polling."""
    logger = get_logger("dex-discovery-supervisor")
    consecutive_failures = 0

    while not stop_event.is_set():
        cycle_started_at = asyncio.get_running_loop().time()
        if leader.is_leader:
            discovered = 0
            discovery_failed = False
            try:
                async with async_session_factory() as session:
                    container = Container(session, helius_client=helius_client)
                    container.setup()
                    for program_id in program_ids:
                        try:
                            result = (
                                await container.dex_discovery_service.scan_program(
                                    program_id
                                )
                            )
                            if not result.complete:
                                logger.warning(
                                    "dex_discovery_gap_sampled",
                                    program_id=program_id,
                                )
                            discovered += result.processed_transactions
                        except Exception:
                            discovery_failed = True
                            logger.exception(
                                "dex_discovery_program_failed",
                                program_id=program_id,
                            )
            except Exception:
                discovery_failed = True
                logger.exception("dex_discovery_cycle_failed")

            previous_failures = consecutive_failures
            consecutive_failures = (
                consecutive_failures + 1 if discovery_failed else 0
            )
            delay = discovery_retry_delay(
                interval_seconds,
                retry_max_seconds,
                consecutive_failures,
            )
            details.update(
                discovered_transactions=discovered,
                discovery_failures=consecutive_failures,
                discovery_next_poll_seconds=delay,
            )
            if discovery_failed and previous_failures == 0:
                await telegram.send_discovery_degraded(
                    consecutive_failures,
                    delay,
                )
            elif not discovery_failed and previous_failures > 0:
                await telegram.send_discovery_recovered()
        else:
            delay = interval_seconds

        elapsed = asyncio.get_running_loop().time() - cycle_started_at
        await wait_for_stop(stop_event, max(0, delay - elapsed))


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
    worker_announced = False
    status_task: asyncio.Task[None] | None = None
    candidate_task: asyncio.Task[None] | None = None
    discovery_task: asyncio.Task[None] | None = None

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
                status_task = asyncio.create_task(
                    telegram_status_loop(
                        leader,
                        telegram,
                        settings.telegram_status_interval_seconds,
                        settings.telegram_status_window_minutes,
                        heartbeat_details,
                        stop_event,
                    )
                )
                if settings.candidate_enrichment_enabled:
                    candidate_task = asyncio.create_task(
                        candidate_enrichment_loop(
                            leader,
                            helius_client,
                            settings.discovery_poll_interval_seconds,
                            settings.candidate_enrichment_min_score,
                            settings.candidate_enrichment_history_limit,
                            settings.candidate_enrichment_max_per_cycle,
                            settings.candidate_enrichment_retry_seconds,
                            heartbeat_details,
                            stop_event,
                        )
                    )
                if settings.discovery_enabled:
                    discovery_task = asyncio.create_task(
                        discovery_loop(
                            leader,
                            helius_client,
                            telegram,
                            settings.discovery_programs,
                            settings.discovery_poll_interval_seconds,
                            settings.discovery_retry_max_seconds,
                            heartbeat_details,
                            stop_event,
                        )
                    )

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
                    heartbeat_details["state"] = "idle"
            except Exception:
                heartbeat_details["state"] = "error"
                logger.exception("monitor_poll_failed")

            await wait_for_stop(
                stop_event,
                settings.monitor_poll_interval_seconds,
            )
    finally:
        if discovery_task is not None:
            discovery_task.cancel()
            with suppress(asyncio.CancelledError):
                await discovery_task
        if candidate_task is not None:
            candidate_task.cancel()
            with suppress(asyncio.CancelledError):
                await candidate_task
        if status_task is not None:
            status_task.cancel()
            with suppress(asyncio.CancelledError):
                await status_task
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
