from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scoring import TokenScore, WalletScore
from app.repositories.token_repository import TokenRepository
from app.services.analytics_service import AnalyticsService
from app.services.wallet_score_calculator import WalletScoreCalculator
from app.services.token_score_calculator import TokenScoreCalculator


class ScoringService:
    def __init__(self, session: AsyncSession) -> None:
        self.analytics = AnalyticsService(session)
        self.tokens = TokenRepository(session)
        self.calculator = WalletScoreCalculator()
        self.token_calculator = TokenScoreCalculator()

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

    async def score_token(self, address: str) -> TokenScore | None:
        token = await self.tokens.get_by_address(address)
        if token is None:
            return None

        analytics = await self.analytics.get_token(address)
        if analytics is None:
            return None
        holders = await self.analytics.get_token_holder_summary(address)
        creator_known = bool(token.creator and token.creator != "unknown")
        creator = (
            await self.analytics.get_creator(token.creator, token_limit=1)
            if creator_known and token.creator is not None
            else None
        )
        return self.token_calculator.calculate(
            analytics,
            holders,
            creator,
            creator_known,
        )
