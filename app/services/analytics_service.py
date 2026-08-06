from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics import TokenAnalytics, TokenPosition, WalletAnalytics
from app.repositories.analytics_repository import AnalyticsRepository
from app.repositories.token_repository import TokenRepository
from app.repositories.wallet_repository import WalletRepository
from app.services.position_calculator import PositionCalculator


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.analytics = AnalyticsRepository(session)
        self.tokens = TokenRepository(session)
        self.wallets = WalletRepository(session)
        self.positions = PositionCalculator()

    async def get_wallet(self, address: str) -> WalletAnalytics | None:
        if await self.wallets.get_by_address(address) is None:
            return None

        return await self.analytics.get_wallet_metrics(address)

    async def get_token(self, address: str) -> TokenAnalytics | None:
        if await self.tokens.get_by_address(address) is None:
            return None

        return await self.analytics.get_token_metrics(address)

    async def get_wallet_positions(
        self,
        address: str,
        include_closed: bool = False,
    ) -> list[TokenPosition] | None:
        if await self.wallets.get_by_address(address) is None:
            return None

        trades = await self.analytics.list_wallet_trades(address)
        return self.positions.calculate(trades, include_closed)
