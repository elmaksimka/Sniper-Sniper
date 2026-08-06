from sqlalchemy import select
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