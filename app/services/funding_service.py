from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models import FundingTransfer
from app.core.funding import WalletFundingAnalytics
from app.repositories.funding_repository import FundingRepository
from app.repositories.wallet_repository import WalletRepository


class FundingService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = FundingRepository(session)
        self.wallets = WalletRepository(session)

    async def create_transfer(
        self,
        source_wallet_id: int,
        destination_wallet_id: int,
        amount_sol: float,
        signature: str,
        instruction_index: str,
        timestamp: datetime | None = None,
    ) -> FundingTransfer:
        existing = await self.repository.get_by_identity(
            signature,
            instruction_index,
        )
        if existing is not None:
            return existing

        return await self.repository.create(
            FundingTransfer(
                source_wallet_id=source_wallet_id,
                destination_wallet_id=destination_wallet_id,
                amount_sol=amount_sol,
                signature=signature,
                instruction_index=instruction_index,
                timestamp=timestamp or datetime.now(UTC),
            )
        )

    async def list_transfers(
        self,
        limit: int,
        offset: int,
        wallet_address: str | None = None,
        direction: str | None = None,
    ) -> tuple[list[FundingTransfer], int]:
        transfers = await self.repository.list_all(
            limit, offset, wallet_address, direction
        )
        total = await self.repository.count(wallet_address, direction)
        return transfers, total

    async def get_wallet_analytics(
        self,
        address: str,
        counterparty_limit: int = 10,
    ) -> WalletFundingAnalytics | None:
        wallet = await self.wallets.get_by_address(address)
        if wallet is None:
            return None
        return await self.repository.get_wallet_analytics(
            wallet.id,
            wallet.address,
            counterparty_limit,
        )
