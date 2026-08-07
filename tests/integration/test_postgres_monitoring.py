from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.infrastructure.leader_election import PostgresLeaderElector
from app.listeners.helius_client import HeliusClient
from app.infrastructure.models import Wallet, WalletMonitor
from app.repositories.monitor_repository import MonitorRepository
from app.repositories.heartbeat_repository import HeartbeatRepository
from app.services.monitor_service import MonitorService
from app.services.system_health_service import SystemHealthService
from app.services.funding_service import FundingService
from app.services.wallet_service import WalletService


pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_funding_transfer_round_trips_and_filters_by_direction(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        wallets = WalletService(session)
        source = await wallets.create_wallet("funding-source")
        destination = await wallets.create_wallet("funding-destination")
        await wallets.create_wallet("empty-funding-wallet")
        service = FundingService(session)

        created = await service.create_transfer(
            source.id,
            destination.id,
            1.25,
            "funding-signature",
            "outer:0",
        )
        repeated = await service.create_transfer(
            source.id,
            destination.id,
            1.25,
            "funding-signature",
            "outer:0",
        )
        await service.create_transfer(
            source.id,
            destination.id,
            0.75,
            "funding-signature-2",
            "outer:0",
        )
        await service.create_transfer(
            destination.id,
            source.id,
            0.5,
            "funding-signature-3",
            "outer:0",
        )

        assert repeated.id == created.id

    async with postgres_session_factory() as session:
        service = FundingService(session)
        incoming, incoming_total = await service.list_transfers(
            10, 0, "funding-destination", "incoming"
        )
        outgoing, outgoing_total = await service.list_transfers(
            10, 0, "funding-destination", "outgoing"
        )
        analytics = await service.get_wallet_analytics(
            "funding-destination",
            counterparty_limit=10,
        )
        empty_analytics = await service.get_wallet_analytics(
            "empty-funding-wallet",
            counterparty_limit=10,
        )

        assert incoming_total == 2
        assert incoming[0].source_wallet.address == "funding-source"
        assert incoming[0].destination_wallet.address == "funding-destination"
        assert sorted(item.amount_sol for item in incoming) == [0.75, 1.25]
        assert outgoing[0].destination_wallet.address == "funding-source"
        assert outgoing_total == 1
        assert analytics is not None
        assert analytics.incoming_transfer_count == 2
        assert analytics.outgoing_transfer_count == 1
        assert analytics.incoming_sol == 2.0
        assert analytics.outgoing_sol == 0.5
        assert analytics.net_sol == 1.5
        assert analytics.unique_funders == 1
        assert analytics.unique_destinations == 1
        assert analytics.first_funder == "funding-source"
        assert len(analytics.counterparties) == 2
        assert analytics.counterparties[0].total_sol == 2.0
        assert empty_analytics is not None
        assert empty_analytics.incoming_transfer_count == 0
        assert empty_analytics.outgoing_transfer_count == 0
        assert empty_analytics.net_sol == 0
        assert empty_analytics.first_funder is None
        assert empty_analytics.first_funding_at is None
        assert empty_analytics.counterparties == []


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

        wallet_count = await session.scalar(
            select(func.count(Wallet.id)).where(
                Wallet.address == "integration-wallet"
            )
        )
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


class HealthyHeliusClient(HeliusClient):
    def __init__(self) -> None:
        pass

    max_retries = 0

    async def get_health(self) -> dict[str, str]:
        return {"result": "ok"}

    async def aclose(self) -> None:
        return None


async def test_readiness_uses_persisted_worker_heartbeat(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        heartbeats = HeartbeatRepository(session)
        heartbeat = await heartbeats.beat(
            "monitor-worker",
            "integration-worker",
            {"state": "idle", "processed_transactions": 3},
        )
        service = SystemHealthService(
            session,
            helius_client=HealthyHeliusClient(),
            worker_stale_after_seconds=120,
            check_timeout_seconds=1,
        )

        report = await service.readiness()

        assert report["status"] == "ready"
        assert report["checks"]["worker"]["instance_id"] == "integration-worker"

        heartbeat.last_heartbeat_at = datetime.now(UTC) - timedelta(minutes=5)
        await session.commit()
        stale_report = await service.readiness()

    assert stale_report["status"] == "not_ready"
    assert stale_report["checks"]["worker"]["reason"] == "heartbeat_stale"
