from __future__ import annotations

from sqlalchemy import distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.funding import FundingCounterparty, WalletFundingAnalytics
from app.infrastructure.models import FundingTransfer, Wallet


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

    async def get_wallet_analytics(
        self,
        wallet_id: int,
        wallet_address: str,
        counterparty_limit: int = 10,
    ) -> WalletFundingAnalytics:
        metrics_result = await self.session.execute(
            select(
                func.count(FundingTransfer.id)
                .filter(FundingTransfer.destination_wallet_id == wallet_id)
                .label("incoming_count"),
                func.count(FundingTransfer.id)
                .filter(FundingTransfer.source_wallet_id == wallet_id)
                .label("outgoing_count"),
                func.coalesce(
                    func.sum(FundingTransfer.amount_sol).filter(
                        FundingTransfer.destination_wallet_id == wallet_id
                    ),
                    0.0,
                ).label("incoming_sol"),
                func.coalesce(
                    func.sum(FundingTransfer.amount_sol).filter(
                        FundingTransfer.source_wallet_id == wallet_id
                    ),
                    0.0,
                ).label("outgoing_sol"),
                func.count(distinct(FundingTransfer.source_wallet_id))
                .filter(FundingTransfer.destination_wallet_id == wallet_id)
                .label("unique_funders"),
                func.count(distinct(FundingTransfer.destination_wallet_id))
                .filter(FundingTransfer.source_wallet_id == wallet_id)
                .label("unique_destinations"),
            )
        )
        metrics = metrics_result.one()

        first_result = await self.session.execute(
            select(FundingTransfer)
            .options(selectinload(FundingTransfer.source_wallet))
            .where(FundingTransfer.destination_wallet_id == wallet_id)
            .order_by(FundingTransfer.timestamp.asc(), FundingTransfer.id.asc())
            .limit(1)
        )
        first_transfer = first_result.scalar_one_or_none()
        counterparties = await self._list_counterparties(
            wallet_id,
            counterparty_limit,
        )

        incoming_sol = float(metrics.incoming_sol)
        outgoing_sol = float(metrics.outgoing_sol)
        return WalletFundingAnalytics(
            wallet_address=wallet_address,
            incoming_transfer_count=int(metrics.incoming_count),
            outgoing_transfer_count=int(metrics.outgoing_count),
            incoming_sol=incoming_sol,
            outgoing_sol=outgoing_sol,
            net_sol=incoming_sol - outgoing_sol,
            unique_funders=int(metrics.unique_funders),
            unique_destinations=int(metrics.unique_destinations),
            first_funder=(
                first_transfer.source_wallet.address if first_transfer else None
            ),
            first_funding_at=(first_transfer.timestamp if first_transfer else None),
            counterparties=counterparties,
        )

    async def _list_counterparties(
        self,
        wallet_id: int,
        limit: int,
    ) -> list[FundingCounterparty]:
        incoming = await self._counterparties_for_direction(
            wallet_id,
            "incoming",
            limit,
        )
        outgoing = await self._counterparties_for_direction(
            wallet_id,
            "outgoing",
            limit,
        )
        return sorted(
            [*incoming, *outgoing],
            key=lambda item: (-item.total_sol, item.address, item.direction),
        )[:limit]

    async def _counterparties_for_direction(
        self,
        wallet_id: int,
        direction: str,
        limit: int,
    ) -> list[FundingCounterparty]:
        incoming = direction == "incoming"
        counterparty_id = (
            FundingTransfer.source_wallet_id
            if incoming
            else FundingTransfer.destination_wallet_id
        )
        wallet_condition = (
            FundingTransfer.destination_wallet_id == wallet_id
            if incoming
            else FundingTransfer.source_wallet_id == wallet_id
        )
        total_sol = func.sum(FundingTransfer.amount_sol)
        result = await self.session.execute(
            select(
                Wallet.address,
                func.count(FundingTransfer.id).label("transfer_count"),
                total_sol.label("total_sol"),
                func.min(FundingTransfer.timestamp).label("first_transfer_at"),
                func.max(FundingTransfer.timestamp).label("last_transfer_at"),
            )
            .join(Wallet, Wallet.id == counterparty_id)
            .where(wallet_condition)
            .group_by(Wallet.id, Wallet.address)
            .order_by(total_sol.desc(), Wallet.address.asc())
            .limit(limit)
        )
        return [
            FundingCounterparty(
                address=row.address,
                direction=direction,
                transfer_count=int(row.transfer_count),
                total_sol=float(row.total_sol),
                first_transfer_at=row.first_transfer_at,
                last_transfer_at=row.last_transfer_at,
            )
            for row in result.all()
        ]

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
