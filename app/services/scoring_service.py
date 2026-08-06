from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scoring import WalletScore
from app.services.analytics_service import AnalyticsService
from app.services.wallet_score_calculator import WalletScoreCalculator


class ScoringService:
    def __init__(self, session: AsyncSession) -> None:
        self.analytics = AnalyticsService(session)
        self.calculator = WalletScoreCalculator()

    async def score_wallet(self, address: str) -> WalletScore | None:
        analytics = await self.analytics.get_wallet(address)
        if analytics is None:
            return None

        positions = await self.analytics.get_wallet_positions(
            address,
            include_closed=True,
        )
        if positions is None:
            return None

        return self.calculator.calculate(analytics, positions)
