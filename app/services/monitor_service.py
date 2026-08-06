from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models import WalletMonitor
from app.repositories.monitor_repository import MonitorRepository
from app.services.wallet_service import WalletService


class MonitorService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = MonitorRepository(session)
        self.wallets = WalletService(session)

    async def add(self, address: str) -> WalletMonitor:
        wallet = await self.wallets.create_wallet(address)
        return await self.repository.create_or_enable(wallet.id)

    async def list(self, enabled_only: bool = False) -> list[WalletMonitor]:
        return await self.repository.list_all(enabled_only)

    async def set_enabled(
        self,
        address: str,
        enabled: bool,
    ) -> WalletMonitor | None:
        monitor = await self.repository.get_by_address(address)
        if monitor is None:
            return None
        return await self.repository.set_enabled(monitor, enabled)
