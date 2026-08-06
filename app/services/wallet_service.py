from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models import Wallet
from app.repositories.wallet_repository import WalletRepository


class WalletService:
    def __init__(
        self,
        session: AsyncSession,
    ):
        self.repository = WalletRepository(
            session
        )

    async def create_wallet(
        self,
        address: str,
    ) -> Wallet:

        existing_wallet = await self.repository.get_by_address(
            address
        )

        if existing_wallet:
            print(
                "Wallet already exists:",
                address,
            )

            return existing_wallet

        print(
            "Creating new wallet:",
            address,
        )

        wallet = Wallet(
            address=address,
        )

        return await self.repository.create(
            wallet
        )