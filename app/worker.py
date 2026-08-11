import asyncio
import os
import signal
import socket
from contextlib import suppress
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.bootstrap.container import Container
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.infrastructure.database import async_session_factory, engine
from app.infrastructure.leader_election import PostgresLeaderElector
from app.listeners.helius_client import HeliusClient
from app.notifications.telegram import TelegramNotifier
from app.repositories.heartbeat_repository import HeartbeatRepository
from app.repositories.monitor_repository import MonitorRepository
from app.repositories.paper_copy_repository import PaperCopyRepository
from app.repositories.score_snapshot_repository import ScoreSnapshotRepository
from app.services.activity_stats_service import ActivityStatsService
from app.services.candidate_audit_progress_service import (
    CandidateAuditProgressService,
)
from app.services.candidate_enrichment_service import CandidateEnrichmentService
from app.services.dexscreener_client import DexScreenerClient
from app.services.monitor_worker import MonitorWorker
from app.services.monitor_service import MonitorService
from app.services.paper_copy_service import PaperCopyService
from app.services.paper_copy_report_service import PaperCopyReportService
from app.services.top_trader_candidate_source import TopTraderCandidateSource


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
                monitors = await MonitorRepository(session).list_all(enabled_only=True)
                scores = ScoreSnapshotRepository(session)
                top_wallets: list[dict[str, Any]] = []
                for monitor in monitors:
                    snapshot = await scores.get_by_wallet_id(monitor.wallet_id)
                    if snapshot is None or snapshot.grade not in {"A", "B"}:
                        continue
                    top_wallets.append(
                        {
                            "address": monitor.wallet.address,
                            "score": snapshot.score,
                            "grade": snapshot.grade,
                        }
                    )
                top_wallets.sort(
                    key=lambda wallet: float(wallet["score"]),
                    reverse=True,
                )
            report_details.update(
                total_transactions=stats.total_transactions,
                total_tokens=stats.total_tokens,
                recent_transactions=stats.recent_transactions,
                recent_tokens=stats.recent_tokens,
                status_window_minutes=stats.window_minutes,
                top_wallets=top_wallets,
            )
        except Exception:
            logger.exception("worker_activity_stats_failed")

        try:
            maximum_transactions = int(
                details.get("candidate_maximum_history_transactions", 1_000)
            )
            async with async_session_factory() as session:
                report_details[
                    "candidate_audit_pairs"
                ] = await CandidateAuditProgressService(
                    HeartbeatRepository(session)
                ).get(maximum_transactions)
        except Exception:
            logger.exception("worker_candidate_audit_progress_failed")

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
    source_window_hours: int,
    source_token_limit: int,
    source_traders_per_token: int,
    source_minimum_token_trades: int,
    source_minimum_token_wallets: int,
    source_minimum_observed_minutes: float,
    source_minimum_current_multiple: float,
    source_early_entry_minutes: float,
    source_early_entry_max_multiple: float,
    details: dict[str, Any],
    stop_event: asyncio.Event,
    external_discovery_interval_seconds: float = 21_600,
    external_token_limit: int = 5,
    external_minimum_realized_pnl_usd: float = 1_000,
    external_minimum_realized_roi: float = 1,
    maximum_history_transactions: int = 1_000,
    dexscreener_renderer_url: str = "",
    dexscreener_renderer_timeout_seconds: float = 75,
    adaptive_initial_transactions: int = 300,
    adaptive_continuation_score: float = 75,
    adaptive_max_unmatched_sell_ratio: float = 0.25,
    adaptive_min_realized_positions: int = 5,
    adaptive_min_priced_trade_ratio: float = 0.6,
) -> None:
    """Enrich candidate wallets without delaying DEX discovery."""
    logger = get_logger("candidate-enrichment-supervisor")
    last_external_discovery_at: float | None = None

    # Let the first discovery cycle claim the shared RPC capacity.
    if await wait_for_stop(stop_event, interval_seconds):
        return

    while not stop_event.is_set():
        if leader.is_leader:
            details["candidate_state"] = "polling"
            try:
                now = asyncio.get_running_loop().time()
                use_external_source = bool(dexscreener_renderer_url) and (
                    last_external_discovery_at is None
                    or now - last_external_discovery_at
                    >= external_discovery_interval_seconds
                )
                async with async_session_factory() as session:
                    container = Container(session, helius_client=helius_client)
                    container.setup(register_trader_promotion=False)
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
                        source_window_hours=source_window_hours,
                        source_token_limit=source_token_limit,
                        source_traders_per_token=source_traders_per_token,
                        source_minimum_token_trades=(source_minimum_token_trades),
                        source_minimum_token_wallets=(source_minimum_token_wallets),
                        source_minimum_observed_minutes=(
                            source_minimum_observed_minutes
                        ),
                        source_minimum_current_multiple=(
                            source_minimum_current_multiple
                        ),
                        source_early_entry_minutes=source_early_entry_minutes,
                        source_early_entry_max_multiple=(
                            source_early_entry_max_multiple
                        ),
                        external_source=(
                            TopTraderCandidateSource(
                                DexScreenerClient(
                                    renderer_url=dexscreener_renderer_url,
                                    renderer_timeout_seconds=(
                                        dexscreener_renderer_timeout_seconds
                                    ),
                                ),
                                token_limit=external_token_limit,
                                traders_per_token=source_traders_per_token,
                                minimum_realized_pnl_usd=(
                                    external_minimum_realized_pnl_usd
                                ),
                                minimum_realized_roi=(external_minimum_realized_roi),
                            )
                            if use_external_source
                            else None
                        ),
                        maximum_history_transactions=(maximum_history_transactions),
                        adaptive_initial_transactions=(adaptive_initial_transactions),
                        adaptive_continuation_score=(adaptive_continuation_score),
                        adaptive_max_unmatched_sell_ratio=(
                            adaptive_max_unmatched_sell_ratio
                        ),
                        adaptive_min_realized_positions=(
                            adaptive_min_realized_positions
                        ),
                        adaptive_min_priced_trade_ratio=(
                            adaptive_min_priced_trade_ratio
                        ),
                        trader_style=container.trader_style_service,
                    ).run_once()
                    promoted_after_audit = 0
                    if enrichment.audit_state == "complete" and enrichment.last_wallet:
                        promoted_after_audit = int(
                            await container.trader_promotion_collector.promote_address(
                                enrichment.last_wallet
                            )
                        )
                    if use_external_source:
                        last_external_discovery_at = now
                        details["candidate_external_source"] = "dexscreener-h24-pnl"
                    details.update(
                        candidate_state="idle",
                        candidate_wallets_enriched=enrichment.wallets_enriched,
                        candidate_history_transactions=(
                            enrichment.transactions_processed
                        ),
                        candidate_wallets_promoted=(
                            enrichment.wallets_promoted + promoted_after_audit
                        ),
                        candidate_last_wallet=enrichment.last_wallet or "",
                        candidate_last_score_before=(enrichment.last_score_before),
                        candidate_last_score_after=enrichment.last_score_after,
                        candidate_history_limit=enrichment.history_limit,
                        candidate_maximum_history_transactions=(
                            maximum_history_transactions
                        ),
                        candidate_audit_state=enrichment.audit_state,
                        candidate_history_transactions_total=(
                            enrichment.history_transactions_total
                        ),
                        candidate_history_capped=enrichment.history_capped,
                        candidate_source_tokens=(enrichment.source_token_count),
                        candidate_source_candidates=(enrichment.source_candidate_count),
                        candidate_source_window_hours=(enrichment.source_window_hours),
                    )
            except Exception:
                details["candidate_state"] = "error"
                logger.exception("candidate_enrichment_cycle_failed")

        await wait_for_stop(stop_event, interval_seconds)


async def paper_copy_execution_loop(
    leader: PostgresLeaderElector,
    interval_seconds: float,
    quote_retry_seconds: float,
    quote_max_attempts: int,
    minimum_source_value_usd: float,
    stop_event: asyncio.Event,
) -> None:
    logger = get_logger("paper-copy-supervisor")
    while not stop_event.is_set():
        if leader.is_leader:
            try:
                async with async_session_factory() as session:
                    repository = PaperCopyRepository(session)
                    service = PaperCopyService(
                        repository,
                        quote_retry_seconds=quote_retry_seconds,
                        quote_max_attempts=quote_max_attempts,
                        minimum_source_value_usd=minimum_source_value_usd,
                    )
                    await service.execute_next()
            except Exception:
                logger.exception("paper_copy_cycle_failed")
        await wait_for_stop(stop_event, interval_seconds)


async def paper_copy_summary_loop(
    leader: PostgresLeaderElector,
    telegram: TelegramNotifier,
    source_wallet: str,
    interval_seconds: float,
    stop_event: asyncio.Event,
) -> None:
    logger = get_logger("paper-copy-summary")
    while not stop_event.is_set():
        await wait_for_stop(stop_event, interval_seconds)
        if stop_event.is_set() or not leader.is_leader:
            continue
        try:
            async with async_session_factory() as session:
                repository = PaperCopyRepository(session)
                portfolio = await repository.get_portfolio(source_wallet)
                if portfolio is None:
                    continue
                orders = await repository.list_unsent(portfolio.id)
                if not orders:
                    continue
                open_positions = await repository.count_open_positions(portfolio.id)
                results = await telegram.send_paper_copy_summary(
                    orders,
                    portfolio,
                    open_positions,
                )
                delivered = not telegram.enabled or (
                    bool(results) and all(results.values())
                )
                if delivered and orders:
                    await repository.mark_notifications_sent(orders)
        except Exception:
            logger.exception("paper_copy_summary_failed")


async def initialize_paper_copy(
    *,
    portfolio_wallet: str,
    source_wallets: tuple[str, ...],
    initial_balance_usd: float,
    allocation_usd: float,
    max_open_positions: int,
    reaction_delay_seconds: float,
    slippage_bps: int,
    minimum_liquidity_usd: float,
    telegram: TelegramNotifier,
) -> None:
    if not source_wallets:
        raise RuntimeError("PAPER_COPY_SOURCE_WALLETS is required")
    async with async_session_factory() as session:
        portfolio, created = await PaperCopyRepository(session).ensure_portfolio(
            source_wallet=portfolio_wallet,
            initial_balance_usd=initial_balance_usd,
            allocation_usd=allocation_usd,
            max_open_positions=max_open_positions,
            reaction_delay_seconds=reaction_delay_seconds,
            slippage_bps=slippage_bps,
            minimum_liquidity_usd=minimum_liquidity_usd,
        )
        monitors = MonitorService(session)
        for source_wallet in source_wallets:
            await monitors.add(source_wallet)
        if created:
            await telegram.send_paper_copy_started(portfolio)


async def paper_copy_report_loop(
    leader: PostgresLeaderElector,
    telegram: TelegramNotifier,
    source_wallet: str,
    report_hour: int,
    report_minute: int,
    timezone_name: str,
    report_date: str,
    stop_event: asyncio.Event,
) -> None:
    logger = get_logger("paper-copy-report")
    timezone = ZoneInfo(timezone_name)
    while not stop_event.is_set():
        if leader.is_leader:
            local_now = datetime.now(timezone)
            requested_date = report_date or local_now.date().isoformat()
            due = local_now.date().isoformat() == requested_date and (
                local_now.hour,
                local_now.minute,
            ) >= (report_hour, report_minute)
            if due:
                marker = f"paper-copy-report:{requested_date}"
                try:
                    async with async_session_factory() as session:
                        heartbeats = HeartbeatRepository(session)
                        if await heartbeats.get(marker) is None:
                            report = await PaperCopyReportService(session).build(
                                source_wallet
                            )
                            if report is not None:
                                results = await telegram.send_paper_copy_report(report)
                                delivered = not telegram.enabled or (
                                    bool(results) and all(results.values())
                                )
                                if delivered:
                                    await heartbeats.beat(
                                        marker,
                                        "paper-copy-report",
                                        {
                                            "equity_usd": report.total_equity_usd,
                                            "pnl_usd": report.total_pnl_usd,
                                        },
                                    )
                except Exception:
                    logger.exception("paper_copy_report_failed")
        await wait_for_stop(stop_event, 30)


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
                            result = await container.dex_discovery_service.scan_program(
                                program_id
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
            consecutive_failures = consecutive_failures + 1 if discovery_failed else 0
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
        worker_summary_enabled=getattr(
            settings,
            "telegram_worker_summary_enabled",
            True,
        ),
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
    paper_copy_task: asyncio.Task[None] | None = None
    paper_copy_summary_task: asyncio.Task[None] | None = None
    paper_copy_report_task: asyncio.Task[None] | None = None
    paper_copy_initialized = False

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

            paper_copy_enabled = bool(getattr(settings, "paper_copy_enabled", False))
            if paper_copy_enabled and not paper_copy_initialized:
                try:
                    await initialize_paper_copy(
                        portfolio_wallet=settings.paper_copy_portfolio_wallet,
                        source_wallets=settings.paper_copy_sources,
                        initial_balance_usd=float(
                            getattr(settings, "paper_copy_initial_balance_usd", 100)
                        ),
                        allocation_usd=float(
                            getattr(settings, "paper_copy_allocation_usd", 10)
                        ),
                        max_open_positions=int(
                            getattr(settings, "paper_copy_max_open_positions", 5)
                        ),
                        reaction_delay_seconds=float(
                            getattr(settings, "paper_copy_reaction_delay_seconds", 20)
                        ),
                        slippage_bps=int(
                            getattr(settings, "paper_copy_slippage_bps", 100)
                        ),
                        minimum_liquidity_usd=float(
                            getattr(
                                settings,
                                "paper_copy_minimum_liquidity_usd",
                                15_000,
                            )
                        ),
                        telegram=telegram,
                    )
                    paper_copy_task = asyncio.create_task(
                        paper_copy_execution_loop(
                            leader,
                            float(
                                getattr(
                                    settings,
                                    "paper_copy_execution_poll_seconds",
                                    2,
                                )
                            ),
                            float(
                                getattr(
                                    settings,
                                    "paper_copy_quote_retry_seconds",
                                    30,
                                )
                            ),
                            int(
                                getattr(
                                    settings,
                                    "paper_copy_quote_max_attempts",
                                    3,
                                )
                            ),
                            float(
                                getattr(
                                    settings,
                                    "paper_copy_minimum_source_value_usd",
                                    1,
                                )
                            ),
                            stop_event,
                        )
                    )
                    paper_copy_summary_task = asyncio.create_task(
                        paper_copy_summary_loop(
                            leader,
                            telegram,
                            settings.paper_copy_portfolio_wallet,
                            float(
                                getattr(
                                    settings,
                                    "paper_copy_summary_interval_seconds",
                                    1800,
                                )
                            ),
                            stop_event,
                        )
                    )
                    if bool(
                        getattr(
                            settings,
                            "paper_copy_daily_report_enabled",
                            False,
                        )
                    ):
                        paper_copy_report_task = asyncio.create_task(
                            paper_copy_report_loop(
                                leader,
                                telegram,
                                settings.paper_copy_portfolio_wallet,
                                int(
                                    getattr(
                                        settings,
                                        "paper_copy_daily_report_hour",
                                        10,
                                    )
                                ),
                                int(
                                    getattr(
                                        settings,
                                        "paper_copy_daily_report_minute",
                                        30,
                                    )
                                ),
                                str(
                                    getattr(
                                        settings,
                                        "paper_copy_daily_report_timezone",
                                        "Europe/Kyiv",
                                    )
                                ),
                                str(
                                    getattr(
                                        settings,
                                        "paper_copy_daily_report_date",
                                        "",
                                    )
                                ),
                                stop_event,
                            )
                        )
                    paper_copy_initialized = True
                except Exception:
                    logger.exception("paper_copy_initialization_failed")
                    await wait_for_stop(
                        stop_event,
                        settings.worker_standby_poll_seconds,
                    )
                    continue

            if not worker_announced:
                await telegram.send_worker_started(
                    monitor_interval_seconds=(settings.monitor_poll_interval_seconds),
                    rpc_discovery_interval_seconds=(
                        settings.discovery_poll_interval_seconds
                    ),
                    candidate_refresh_interval_seconds=(
                        settings.candidate_external_discovery_interval_seconds
                    ),
                    candidate_token_limit=(settings.candidate_external_token_limit),
                    traders_per_token=(settings.candidate_source_traders_per_token),
                    history_page_size=(settings.candidate_enrichment_history_limit),
                    maximum_history_transactions=(
                        settings.candidate_enrichment_maximum_history_transactions
                    ),
                    external_discovery_enabled=bool(
                        getattr(settings, "dexscreener_renderer_url", "")
                        and settings.candidate_enrichment_enabled
                    ),
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
                            settings.candidate_source_window_hours,
                            settings.candidate_source_token_limit,
                            settings.candidate_source_traders_per_token,
                            settings.candidate_source_minimum_token_trades,
                            settings.candidate_source_minimum_token_wallets,
                            settings.candidate_source_minimum_observed_minutes,
                            settings.candidate_source_minimum_current_multiple,
                            settings.candidate_source_early_entry_minutes,
                            settings.candidate_source_early_entry_max_multiple,
                            heartbeat_details,
                            stop_event,
                            external_discovery_interval_seconds=(
                                settings.candidate_external_discovery_interval_seconds
                            ),
                            external_token_limit=(
                                settings.candidate_external_token_limit
                            ),
                            external_minimum_realized_pnl_usd=(
                                settings.candidate_external_minimum_realized_pnl_usd
                            ),
                            external_minimum_realized_roi=(
                                settings.candidate_external_minimum_realized_roi
                            ),
                            maximum_history_transactions=(
                                settings.candidate_enrichment_maximum_history_transactions
                            ),
                            dexscreener_renderer_url=(
                                settings.dexscreener_renderer_url
                            ),
                            dexscreener_renderer_timeout_seconds=(
                                settings.dexscreener_renderer_timeout_seconds
                            ),
                            adaptive_initial_transactions=getattr(
                                settings,
                                "candidate_adaptive_initial_transactions",
                                300,
                            ),
                            adaptive_continuation_score=getattr(
                                settings,
                                "candidate_adaptive_continuation_score",
                                75,
                            ),
                            adaptive_max_unmatched_sell_ratio=getattr(
                                settings,
                                "candidate_adaptive_max_unmatched_sell_ratio",
                                0.25,
                            ),
                            adaptive_min_realized_positions=getattr(
                                settings,
                                "candidate_adaptive_min_realized_positions",
                                5,
                            ),
                            adaptive_min_priced_trade_ratio=getattr(
                                settings,
                                "candidate_adaptive_min_priced_trade_ratio",
                                0.6,
                            ),
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
                    if paper_copy_enabled:
                        container.setup(register_paper_copy=True)
                    else:
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
        if paper_copy_task is not None:
            paper_copy_task.cancel()
            with suppress(asyncio.CancelledError):
                await paper_copy_task
        if paper_copy_summary_task is not None:
            paper_copy_summary_task.cancel()
            with suppress(asyncio.CancelledError):
                await paper_copy_summary_task
        if paper_copy_report_task is not None:
            paper_copy_report_task.cancel()
            with suppress(asyncio.CancelledError):
                await paper_copy_report_task
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
