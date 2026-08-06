from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models import Wallet


class WalletRepository:
    def __init__(
        self,
        session: AsyncSession,
    ):
        self.session = session

    async def create(
        self,
        wallet: Wallet,
    ) -> Wallet:
        self.session.add(wallet)

        await self.session.commit()
        await self.session.refresh(wallet)

        return wallet

    async def get_by_address(
        self,
        address: str,
    ) -> Wallet | None:
        result = await self.session.execute(
            select(Wallet).where(
                Wallet.address == address
            )
        )

        return result.scalar_one_or_none()

    async def list_all(self, limit: int, offset: int) -> list[Wallet]:
        result = await self.session.execute(
            select(Wallet)
            .order_by(Wallet.first_seen.desc(), Wallet.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count(self) -> int:
        result = await self.session.execute(select(func.count(Wallet.id)))
        return result.scalar_one()
