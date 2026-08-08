import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

import app.worker as worker_module
from app.worker import (
    candidate_enrichment_loop,
    discovery_loop,
    discovery_retry_delay,
    telegram_status_loop,
    wait_for_stop,
)


@pytest.mark.asyncio
async def test_wait_for_stop_returns_when_shutdown_is_requested() -> None:
    stop_event = asyncio.Event()
    stop_event.set()

    assert await wait_for_stop(stop_event, 60) is True


@pytest.mark.asyncio
async def test_wait_for_stop_returns_after_timeout() -> None:
    stop_event = asyncio.Event()

    assert await wait_for_stop(stop_event, 0.001) is False


@pytest.mark.parametrize(
    ("failures", "expected"),
    [(0, 120), (1, 240), (2, 480), (3, 900), (20, 900)],
)
def test_discovery_retry_delay_is_bounded(
    failures: int,
    expected: float,
) -> None:
    assert discovery_retry_delay(120, 900, failures) == expected


@pytest.mark.asyncio
async def test_telegram_status_loop_runs_independently(monkeypatch) -> None:
    stop_event = asyncio.Event()
    sent_details: list[dict[str, object]] = []

    class FakeTelegram:
        async def send_worker_status(
            self,
            details: dict[str, object],
        ) -> dict[str, bool]:
            sent_details.append(details)
            stop_event.set()
            return {"chat": True}

    class FakeStatsService:
        def __init__(self, session: object) -> None:
            pass

        async def get(self, window_minutes: int) -> SimpleNamespace:
            return SimpleNamespace(
                total_transactions=100,
                total_tokens=25,
                recent_transactions=12,
                recent_tokens=4,
                window_minutes=window_minutes,
            )

    class FakeMonitorRepository:
        def __init__(self, session: object) -> None:
            pass

        async def list_all(self, enabled_only: bool = False) -> list[SimpleNamespace]:
            assert enabled_only is True
            return [
                SimpleNamespace(
                    wallet_id=7,
                    wallet=SimpleNamespace(address="top-wallet"),
                )
            ]

    class FakeScoreRepository:
        def __init__(self, session: object) -> None:
            pass

        async def get_by_wallet_id(self, wallet_id: int) -> SimpleNamespace:
            assert wallet_id == 7
            return SimpleNamespace(score=88.35, grade="A")

    @asynccontextmanager
    async def fake_session_factory():
        yield object()

    monkeypatch.setattr(worker_module, "ActivityStatsService", FakeStatsService)
    monkeypatch.setattr(worker_module, "MonitorRepository", FakeMonitorRepository)
    monkeypatch.setattr(
        worker_module,
        "ScoreSnapshotRepository",
        FakeScoreRepository,
    )
    monkeypatch.setattr(worker_module, "async_session_factory", fake_session_factory)

    await telegram_status_loop(
        SimpleNamespace(is_leader=True),
        FakeTelegram(),  # type: ignore[arg-type]
        0.001,
        30,
        {"state": "polling"},
        stop_event,
    )

    assert sent_details == [
        {
            "state": "polling",
            "total_transactions": 100,
            "total_tokens": 25,
            "recent_transactions": 12,
            "recent_tokens": 4,
            "status_window_minutes": 30,
            "top_wallets": [
                {"address": "top-wallet", "score": 88.35, "grade": "A"}
            ],
        }
    ]


@pytest.mark.asyncio
async def test_candidate_enrichment_loop_runs_independently(monkeypatch) -> None:
    stop_event = asyncio.Event()

    class FakePromotionCollector:
        async def reconcile(self) -> int:
            return 1

    class FakeContainer:
        scanner = object()
        token_detection_service = object()
        trader_promotion_collector = FakePromotionCollector()

        def __init__(self, *args, **kwargs) -> None:
            pass

        def setup(self) -> None:
            pass

    class FakeEnrichmentService:
        def __init__(self, **kwargs) -> None:
            assert kwargs["history_limit"] == 75

        async def run_once(self) -> SimpleNamespace:
            stop_event.set()
            return SimpleNamespace(
                wallets_enriched=1,
                transactions_processed=75,
                wallets_promoted=0,
                last_wallet="candidate",
                last_score_before=45.0,
                last_score_after=67.0,
                history_limit=75,
                source_token_count=25,
                source_candidate_count=80,
                    source_window_hours=24,
                    audit_state="complete",
                    history_transactions_total=75,
                    history_capped=False,
                )

    @asynccontextmanager
    async def fake_session_factory():
        yield object()

    monkeypatch.setattr(worker_module, "Container", FakeContainer)
    monkeypatch.setattr(
        worker_module,
        "CandidateEnrichmentService",
        FakeEnrichmentService,
    )
    monkeypatch.setattr(worker_module, "ScoreSnapshotRepository", lambda _: object())
    monkeypatch.setattr(worker_module, "MonitorRepository", lambda _: object())
    monkeypatch.setattr(worker_module, "HeartbeatRepository", lambda _: object())
    monkeypatch.setattr(worker_module, "async_session_factory", fake_session_factory)
    details: dict[str, object] = {}

    await candidate_enrichment_loop(
        SimpleNamespace(is_leader=True),  # type: ignore[arg-type]
        SimpleNamespace(),  # type: ignore[arg-type]
        0.001,
        35,
        75,
        1,
        1800,
        24,
        25,
        10,
        10,
        5,
        30,
        3,
        30,
        2,
        details,
        stop_event,
    )

    assert details == {
        "candidate_state": "idle",
        "candidate_wallets_enriched": 1,
        "candidate_history_transactions": 75,
        "candidate_wallets_promoted": 1,
        "candidate_last_wallet": "candidate",
        "candidate_last_score_before": 45.0,
        "candidate_last_score_after": 67.0,
        "candidate_history_limit": 75,
        "candidate_source_tokens": 25,
            "candidate_source_candidates": 80,
            "candidate_source_window_hours": 24,
            "candidate_audit_state": "complete",
            "candidate_history_transactions_total": 75,
            "candidate_history_capped": False,
        }


@pytest.mark.asyncio
async def test_discovery_loop_runs_independently(monkeypatch) -> None:
    stop_event = asyncio.Event()

    class FakeDiscoveryService:
        async def scan_program(self, program_id: str) -> SimpleNamespace:
            assert program_id == "program"
            stop_event.set()
            return SimpleNamespace(complete=True, processed_transactions=42)

    class FakeContainer:
        dex_discovery_service = FakeDiscoveryService()

        def __init__(self, *args, **kwargs) -> None:
            pass

        def setup(self) -> None:
            pass

    class FakeTelegram:
        async def send_discovery_degraded(self, *args) -> None:
            raise AssertionError("healthy discovery must not alert")

        async def send_discovery_recovered(self) -> None:
            raise AssertionError("healthy discovery must not alert")

    @asynccontextmanager
    async def fake_session_factory():
        yield object()

    monkeypatch.setattr(worker_module, "Container", FakeContainer)
    monkeypatch.setattr(worker_module, "async_session_factory", fake_session_factory)
    details: dict[str, object] = {}

    await discovery_loop(
        SimpleNamespace(is_leader=True),  # type: ignore[arg-type]
        SimpleNamespace(),  # type: ignore[arg-type]
        FakeTelegram(),  # type: ignore[arg-type]
        ("program",),
        120,
        900,
        details,
        stop_event,
    )

    assert details == {
        "discovered_transactions": 42,
        "discovery_failures": 0,
        "discovery_next_poll_seconds": 120,
    }


@pytest.mark.asyncio
async def test_run_finishes_poll_and_releases_resources(monkeypatch) -> None:
    stop_event = asyncio.Event()
    poll_completed = False

    class FakeLeader:
        is_leader = False
        released = False

        async def try_acquire(self) -> bool:
            self.is_leader = True
            return True

        async def verify(self) -> bool:
            return True

        async def release(self) -> None:
            self.is_leader = False
            self.released = True

    class FakeHeliusClient:
        closed = False

        async def aclose(self) -> None:
            self.closed = True

    class FakeEngine:
        disposed = False

        async def dispose(self) -> None:
            self.disposed = True

    class FakeContainer:
        scanner = object()
        token_detection_service = object()

        def __init__(self, *args, **kwargs) -> None:
            pass

        def setup(self) -> None:
            pass

    class FakeMonitorWorker:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def run_once(self) -> int:
            nonlocal poll_completed
            stop_event.set()
            await asyncio.sleep(0)
            poll_completed = True
            return 1

    @asynccontextmanager
    async def fake_session_factory():
        yield object()

    async def fake_heartbeat_loop(*args, **kwargs) -> None:
        await stop_event.wait()

    settings = SimpleNamespace(
        worker_leader_lock_key=1,
        worker_heartbeat_interval_seconds=1,
        worker_standby_poll_seconds=1,
        monitor_page_size=100,
        monitor_max_pages=10,
        monitor_poll_interval_seconds=30,
        discovery_enabled=False,
        discovery_programs=(),
        discovery_poll_interval_seconds=120,
        discovery_retry_max_seconds=900,
        discovery_page_size=20,
        candidate_enrichment_enabled=False,
        candidate_external_discovery_interval_seconds=21_600,
        candidate_external_token_limit=5,
        candidate_source_traders_per_token=10,
        candidate_enrichment_history_limit=75,
        candidate_enrichment_maximum_history_transactions=1_000,
        birdeye_api_key="",
        telegram_bot_token="",
        telegram_recipients=(),
        telegram_status_interval_seconds=1800,
        telegram_status_window_minutes=30,
    )
    leader = FakeLeader()
    helius_client = FakeHeliusClient()
    fake_engine = FakeEngine()
    monkeypatch.setattr(worker_module, "get_settings", lambda: settings)
    monkeypatch.setattr(worker_module, "HeliusClient", lambda: helius_client)
    monkeypatch.setattr(
        worker_module,
        "PostgresLeaderElector",
        lambda *args: leader,
    )
    monkeypatch.setattr(worker_module, "Container", FakeContainer)
    monkeypatch.setattr(worker_module, "MonitorWorker", FakeMonitorWorker)
    monkeypatch.setattr(worker_module, "MonitorRepository", lambda session: object())
    monkeypatch.setattr(worker_module, "async_session_factory", fake_session_factory)
    monkeypatch.setattr(worker_module, "heartbeat_loop", fake_heartbeat_loop)
    monkeypatch.setattr(worker_module, "engine", fake_engine)

    await worker_module.run(stop_event)

    assert poll_completed is True
    assert leader.released is True
    assert helius_client.closed is True
    assert fake_engine.disposed is True
