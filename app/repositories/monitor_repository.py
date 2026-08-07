from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.infrastructure.models import Wallet, WalletMonitor


class MonitorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_or_enable(self, wallet_id: int) -> WalletMonitor:
        monitor = await self.get_by_wallet_id(wallet_id)
        if monitor is None:
            monitor = WalletMonitor(wallet_id=wallet_id, enabled=True)
            self.session.add(monitor)
        else:
            monitor.enabled = True
            monitor.last_error = None

        await self.session.commit()
        loaded = await self.get_by_wallet_id(wallet_id)
        if loaded is None:
            raise RuntimeError("Monitor disappeared after commit")
        return loaded

    async def get_by_wallet_id(self, wallet_id: int) -> WalletMonitor | None:
        result = await self.session.execute(
            select(WalletMonitor)
            .options(selectinload(WalletMonitor.wallet))
            .where(WalletMonitor.wallet_id == wallet_id)
        )
        return result.scalar_one_or_none()

    async def get_by_address(self, address: str) -> WalletMonitor | None:
        result = await self.session.execute(
            select(WalletMonitor)
            .join(WalletMonitor.wallet)
            .options(selectinload(WalletMonitor.wallet))
            .where(Wallet.address == address)
        )
        return result.scalar_one_or_none()

    async def list_all(self, enabled_only: bool = False) -> list[WalletMonitor]:
        statement = select(WalletMonitor).options(
            selectinload(WalletMonitor.wallet)
        )
        if enabled_only:
            statement = statement.where(WalletMonitor.enabled.is_(True))

        result = await self.session.execute(
            statement.order_by(WalletMonitor.id.asc())
        )
        return list(result.scalars().all())

    async def count_enabled(self) -> int:
        result = await self.session.execute(
            select(func.count(WalletMonitor.id)).where(
                WalletMonitor.enabled.is_(True)
            )
        )
        return result.scalar_one()

    async def set_enabled(
        self,
        monitor: WalletMonitor,
        enabled: bool,
    ) -> WalletMonitor:
        monitor.enabled = enabled
        monitor.updated_at = datetime.now(UTC)
        await self.session.commit()
        return monitor

    async def mark_success(
        self,
        monitor: WalletMonitor,
        checkpoint_signature: str | None,
    ) -> None:
        monitor.checkpoint_signature = checkpoint_signature
        monitor.last_scanned_at = datetime.now(UTC)
        monitor.last_error = None
        monitor.updated_at = datetime.now(UTC)
        await self.session.commit()

    async def mark_error(self, monitor: WalletMonitor, error: str) -> None:
        monitor.last_error = error[:512]
        monitor.last_scanned_at = datetime.now(UTC)
        monitor.updated_at = datetime.now(UTC)
        await self.session.commit()
