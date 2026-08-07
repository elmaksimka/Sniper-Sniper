from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.infrastructure.models import FundingTransfer


class FundingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, transfer: FundingTransfer) -> FundingTransfer:
        self.session.add(transfer)
        await self.session.commit()
        await self.session.refresh(transfer)
        return transfer

    async def get_by_identity(
        self,
        signature: str,
        instruction_index: str,
    ) -> FundingTransfer | None:
        result = await self.session.execute(
            select(FundingTransfer).where(
                FundingTransfer.signature == signature,
                FundingTransfer.instruction_index == instruction_index,
            )
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        limit: int,
        offset: int,
        wallet_address: str | None = None,
        direction: str | None = None,
    ) -> list[FundingTransfer]:
        result = await self.session.execute(
            select(FundingTransfer)
            .options(
                selectinload(FundingTransfer.source_wallet),
                selectinload(FundingTransfer.destination_wallet),
            )
            .where(*self._filters(wallet_address, direction))
            .order_by(FundingTransfer.timestamp.desc(), FundingTransfer.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count(
        self,
        wallet_address: str | None = None,
        direction: str | None = None,
    ) -> int:
        result = await self.session.execute(
            select(func.count(FundingTransfer.id)).where(
                *self._filters(wallet_address, direction)
            )
        )
        return result.scalar_one()

    @staticmethod
    def _filters(
        wallet_address: str | None,
        direction: str | None,
    ) -> list:
        if not wallet_address:
            return []

        # Relationship predicates avoid joining the wallets table twice.
        outgoing = FundingTransfer.source_wallet.has(address=wallet_address)
        incoming = FundingTransfer.destination_wallet.has(address=wallet_address)
        if direction == "outgoing":
            return [outgoing]
        if direction == "incoming":
            return [incoming]
        return [or_(outgoing, incoming)]
