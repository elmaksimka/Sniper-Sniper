from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models import Token, Trade, Wallet
from app.repositories.token_repository import TokenRepository
from app.repositories.trade_repository import TradeRepository
from app.repositories.wallet_repository import WalletRepository


class ReadService:
    """Read-only facade used by the HTTP API."""

    def __init__(self, session: AsyncSession) -> None:
        self.tokens = TokenRepository(session)
        self.wallets = WalletRepository(session)
        self.trades = TradeRepository(session)

    async def list_tokens(
        self,
        limit: int,
        offset: int,
        creator: str | None,
    ) -> tuple[list[Token], int]:
        return (
            await self.tokens.list_all(limit, offset, creator),
            await self.tokens.count(creator),
        )

    async def get_token(self, address: str) -> Token | None:
        return await self.tokens.get_by_address(address)

    async def list_wallets(
        self,
        limit: int,
        offset: int,
    ) -> tuple[list[Wallet], int]:
        return await self.wallets.list_all(limit, offset), await self.wallets.count()

    async def get_wallet(self, address: str) -> Wallet | None:
        return await self.wallets.get_by_address(address)

    async def list_trades(
        self,
        limit: int,
        offset: int,
        token_address: str | None,
        wallet_address: str | None,
        side: str | None,
    ) -> tuple[list[Trade], int]:
        filters = (token_address, wallet_address, side)
        return (
            await self.trades.list_all(limit, offset, *filters),
            await self.trades.count(*filters),
        )
