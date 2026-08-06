from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.infrastructure.leader_election import PostgresLeaderElector
from app.infrastructure.models import Wallet, WalletMonitor
from app.repositories.monitor_repository import MonitorRepository
from app.services.monitor_service import MonitorService


pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_monitor_state_round_trips_through_postgres(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        service = MonitorService(session)
        created = await service.add("integration-wallet")
        repeated = await service.add("integration-wallet")

        assert repeated.id == created.id
        disabled = await service.set_enabled("integration-wallet", False)
        assert disabled is not None
        assert disabled.enabled is False

    async with postgres_session_factory() as session:
        repository = MonitorRepository(session)
        monitor = await repository.get_by_address("integration-wallet")
        assert monitor is not None
        await repository.mark_success(monitor, "checkpoint-signature")

    async with postgres_session_factory() as session:
        monitor = await MonitorRepository(session).get_by_address(
            "integration-wallet"
        )
        assert monitor is not None
        assert monitor.checkpoint_signature == "checkpoint-signature"
        assert monitor.last_scanned_at is not None
        assert monitor.last_error is None

        wallet_count = await session.scalar(select(func.count(Wallet.id)))
        monitor_count = await session.scalar(select(func.count(WalletMonitor.id)))
        assert wallet_count == 1
        assert monitor_count == 1


async def test_postgres_advisory_lock_allows_one_worker_leader(
    postgres_engine: AsyncEngine,
) -> None:
    lock_key = uuid4().int % 2_000_000_000 + 1
    first = PostgresLeaderElector(postgres_engine, lock_key)
    second = PostgresLeaderElector(postgres_engine, lock_key)

    try:
        assert await first.try_acquire() is True
        assert await second.try_acquire() is False

        await first.release()

        assert await second.try_acquire() is True
    finally:
        await first.release()
        await second.release()
