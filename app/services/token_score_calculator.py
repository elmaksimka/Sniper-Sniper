from __future__ import annotations

from app.core.analytics import CreatorAnalytics, TokenAnalytics, TokenHolderSummary
from app.core.scoring import TokenScore


METHODOLOGY_VERSION = "token-v1"


class TokenScoreCalculator:
    """Calculate an explainable 0-100 observed token heuristic."""

    def calculate(
        self,
        analytics: TokenAnalytics,
        holders: TokenHolderSummary,
        creator: CreatorAnalytics | None,
        creator_known: bool,
    ) -> TokenScore:
        activity_score = min(analytics.total_trades / 50, 1) * 20
        participation_score = min(analytics.unique_wallets / 20, 1) * 15

        distribution_score = 0.0
        if holders.active_holder_count > 0:
            concentration_component = (1 - holders.top_holder_share) * 20
            breadth_component = min(holders.active_holder_count / 10, 1) * 5
            distribution_score = concentration_component + breadth_component

        total_flow = analytics.buy_volume + analytics.sell_volume
        flow_balance_score = 0.0
        if total_flow > 0:
            imbalance = abs(analytics.buy_volume - analytics.sell_volume) / total_flow
            flow_balance_score = (1 - self._clamp(imbalance, 0, 1)) * 15

        creator_history_score = 0.0
        if creator is not None and creator.token_count > 0:
            breadth = min(creator.token_count / 5, 1) * 5
            traded_ratio = creator.traded_token_count / creator.token_count
            creator_history_score = breadth + self._clamp(traded_ratio, 0, 1) * 10

        history_quality = (
            (1 - holders.incomplete_holder_ratio) * 7
            if holders.observed_wallet_count > 0
            else 0.0
        )
        metadata_quality = 3.0 if creator_known else 0.0
        data_quality_score = history_quality + metadata_quality

        score = sum(
            (
                activity_score,
                participation_score,
                distribution_score,
                flow_balance_score,
                creator_history_score,
                data_quality_score,
            )
        )
        return TokenScore(
            token_address=analytics.address,
            score=round(self._clamp(score, 0, 100), 2),
            grade=self._grade(score),
            methodology_version=METHODOLOGY_VERSION,
            activity_score=round(activity_score, 2),
            participation_score=round(participation_score, 2),
            holder_distribution_score=round(distribution_score, 2),
            flow_balance_score=round(flow_balance_score, 2),
            creator_history_score=round(creator_history_score, 2),
            data_quality_score=round(data_quality_score, 2),
            observed_holder_count=holders.active_holder_count,
            top_holder_share=round(holders.top_holder_share, 6),
            incomplete_holder_ratio=round(holders.incomplete_holder_ratio, 6),
        )

    @staticmethod
    def _clamp(value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(value, maximum))

    @staticmethod
    def _grade(score: float) -> str:
        if score >= 80:
            return "A"
        if score >= 65:
            return "B"
        if score >= 50:
            return "C"
        if score >= 35:
            return "D"
        return "E"
