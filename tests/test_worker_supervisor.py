import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

import app.worker as worker_module
from app.worker import discovery_retry_delay, wait_for_stop


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
