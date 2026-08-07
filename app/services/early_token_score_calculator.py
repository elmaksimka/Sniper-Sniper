from __future__ import annotations

from app.core.analytics import TokenAnalytics, TokenHolderSummary
from app.core.scoring import EarlyTokenScore


METHODOLOGY_VERSION = "early-token-v1"


class EarlyTokenScoreCalculator:
    """Score sparse early trading data without treating one buy as conviction."""

    def calculate(
        self,
        analytics: TokenAnalytics,
        holders: TokenHolderSummary,
    ) -> EarlyTokenScore:
        activity_score = min(analytics.total_trades / 10, 1) * 15
        participation_score = min(analytics.unique_wallets / 5, 1) * 20

        total_flow = analytics.buy_volume + analytics.sell_volume
        buy_pressure_score = 0.0
        if total_flow > 0:
            buy_ratio = analytics.buy_volume / total_flow
            evidence = min(analytics.total_trades / 5, 1)
            buy_pressure_score = self._clamp(buy_ratio, 0, 1) * evidence * 30

        holder_distribution_score = 0.0
        if holders.active_holder_count > 0:
            concentration = (1 - holders.top_holder_share) * 15
            breadth = min(holders.active_holder_count / 5, 1) * 5
            holder_distribution_score = concentration + breadth

        data_quality_score = 0.0
        if holders.observed_wallet_count > 0:
            history = (1 - holders.incomplete_holder_ratio) * 10
            coverage = min(holders.observed_wallet_count / 5, 1) * 5
            data_quality_score = history + coverage

        score = sum(
            (
                activity_score,
                participation_score,
                buy_pressure_score,
                holder_distribution_score,
                data_quality_score,
            )
        )
        score = self._clamp(score, 0, 100)
        return EarlyTokenScore(
            token_address=analytics.address,
            score=round(score, 2),
            grade=self._grade(score),
            methodology_version=METHODOLOGY_VERSION,
            activity_score=round(activity_score, 2),
            participation_score=round(participation_score, 2),
            buy_pressure_score=round(buy_pressure_score, 2),
            holder_distribution_score=round(holder_distribution_score, 2),
            data_quality_score=round(data_quality_score, 2),
            observed_trade_count=analytics.total_trades,
            observed_wallet_count=analytics.unique_wallets,
            top_holder_share=round(holders.top_holder_share, 6),
            incomplete_holder_ratio=round(holders.incomplete_holder_ratio, 6),
        )

    @staticmethod
    def _clamp(value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(value, maximum))

    @staticmethod
    def _grade(score: float) -> str:
        if score >= 75:
            return "A"
        if score >= 60:
            return "B"
        if score >= 45:
            return "C"
        if score >= 30:
            return "D"
        return "E"
