from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scoring import EarlyTokenScore, TokenScore, WalletScore
from app.core.assets import is_target_mint
from app.repositories.token_repository import TokenRepository
from app.services.analytics_service import AnalyticsService
from app.services.wallet_score_calculator import WalletScoreCalculator
from app.services.token_score_calculator import TokenScoreCalculator
from app.services.early_token_score_calculator import EarlyTokenScoreCalculator


class ScoringService:
    def __init__(self, session: AsyncSession) -> None:
        self.analytics = AnalyticsService(session)
        self.tokens = TokenRepository(session)
        self.calculator = WalletScoreCalculator()
        self.token_calculator = TokenScoreCalculator()
        self.early_token_calculator = EarlyTokenScoreCalculator()

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
        if not is_target_mint(address):
            return None
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

    async def score_early_token(self, address: str) -> EarlyTokenScore | None:
        if not is_target_mint(address):
            return None
        token = await self.tokens.get_by_address(address)
        if token is None:
            return None

        analytics = await self.analytics.get_token(address)
        if analytics is None:
            return None
        holders = await self.analytics.get_token_holder_summary(address)
        return self.early_token_calculator.calculate(analytics, holders)
