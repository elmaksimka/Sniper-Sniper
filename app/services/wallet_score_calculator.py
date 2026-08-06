from __future__ import annotations

from app.core.analytics import TokenPosition, WalletAnalytics
from app.core.scoring import WalletScore


METHODOLOGY_VERSION = "wallet-v1"


class WalletScoreCalculator:
    """Calculate an explainable 0-100 wallet heuristic score."""

    def calculate(
        self,
        analytics: WalletAnalytics,
        positions: list[TokenPosition],
    ) -> WalletScore:
        activity_score = min(analytics.total_trades / 50, 1) * 20
        diversification_score = min(analytics.unique_tokens / 10, 1) * 15
        exit_ratio = min(
            analytics.sell_count / max(analytics.buy_count, 1),
            1,
        )
        exit_experience_score = exit_ratio * 20

        realized_pnl = sum(position.realized_pnl_sol for position in positions)
        sol_spent = sum(position.sol_spent for position in positions)
        realized_roi = realized_pnl / sol_spent if sol_spent > 0 else 0.0
        normalized_roi = (self._clamp(realized_roi, -0.5, 0.5) + 0.5) / 1.0
        performance_score = normalized_roi * 35

        total_sold = sum(position.total_sold for position in positions)
        unmatched_sells = sum(
            position.unmatched_sell_quantity for position in positions
        )
        unmatched_ratio = (
            self._clamp(unmatched_sells / total_sold, 0, 1)
            if total_sold > 0
            else 0.0
        )
        data_quality_score = (1 - unmatched_ratio) * 10

        score = sum(
            (
                activity_score,
                diversification_score,
                exit_experience_score,
                performance_score,
                data_quality_score,
            )
        )

        return WalletScore(
            wallet_address=analytics.address,
            score=round(self._clamp(score, 0, 100), 2),
            grade=self._grade(score),
            methodology_version=METHODOLOGY_VERSION,
            activity_score=round(activity_score, 2),
            diversification_score=round(diversification_score, 2),
            exit_experience_score=round(exit_experience_score, 2),
            realized_performance_score=round(performance_score, 2),
            data_quality_score=round(data_quality_score, 2),
            realized_pnl_sol=round(realized_pnl, 9),
            realized_roi=round(realized_roi, 6),
            unmatched_sell_ratio=round(unmatched_ratio, 6),
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
