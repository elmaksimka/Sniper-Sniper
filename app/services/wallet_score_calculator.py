from __future__ import annotations

from app.core.analytics import TokenPosition, WalletAnalytics
from app.core.scoring import WalletScore


METHODOLOGY_VERSION = "wallet-v3"


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
        realized_cost_basis = sum(
            position.realized_cost_basis_sol for position in positions
        )
        realized_roi = (
            realized_pnl / realized_cost_basis
            if realized_cost_basis > 0
            else 0.0
        )
        realized_positions = [
            position
            for position in positions
            if position.realized_cost_basis_sol > 0
        ]
        profitable_positions = [
            position
            for position in realized_positions
            if position.realized_pnl_sol > 0
        ]
        win_rate = (
            len(profitable_positions) / len(realized_positions)
            if realized_positions
            else 0.0
        )
        gross_profit = sum(
            position.realized_pnl_sol for position in profitable_positions
        )
        top_position = max(
            profitable_positions,
            key=lambda position: position.realized_pnl_sol,
            default=None,
        )
        top_pnl = top_position.realized_pnl_sol if top_position else 0.0
        top_cost_basis = (
            top_position.realized_cost_basis_sol if top_position else 0.0
        )
        pnl_concentration = (
            self._clamp(top_pnl / gross_profit, 0, 1)
            if gross_profit > 0
            else 0.0
        )
        pnl_ex_top = realized_pnl - top_pnl
        cost_basis_ex_top = max(realized_cost_basis - top_cost_basis, 0.0)
        roi_ex_top = (
            pnl_ex_top / cost_basis_ex_top
            if cost_basis_ex_top > 0
            else 0.0
        )
        roi_score = self._clamp(realized_roi, 0, 0.5) / 0.5 * 10
        win_rate_score = win_rate * 10
        concentration_score = (
            self._clamp((1 - pnl_concentration) / 0.8, 0, 1) * 5
            if gross_profit > 0
            else 0.0
        )
        robust_roi_score = (
            self._clamp(roi_ex_top, 0, 0.5) / 0.5 * 10
        )
        performance_score = sum(
            (roi_score, win_rate_score, concentration_score, robust_roi_score)
        )

        total_sold = sum(position.total_sold for position in positions)
        unmatched_sells = sum(
            position.unmatched_sell_quantity for position in positions
        )
        unmatched_ratio = (
            self._clamp(unmatched_sells / total_sold, 0, 1)
            if total_sold > 0
            else 0.0
        )
        priced_trade_ratio = (
            self._clamp(
                analytics.priced_trade_count / analytics.total_trades,
                0,
                1,
            )
            if analytics.total_trades > 0
            else 0.0
        )
        data_quality_score = (
            (1 - unmatched_ratio) * priced_trade_ratio * 10
        )

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
            priced_trade_ratio=round(priced_trade_ratio, 6),
            realized_cost_basis_sol=round(realized_cost_basis, 9),
            realized_position_count=len(realized_positions),
            profitable_position_count=len(profitable_positions),
            win_rate=round(win_rate, 6),
            pnl_concentration_ratio=round(pnl_concentration, 6),
            realized_pnl_ex_top_position_sol=round(pnl_ex_top, 9),
            realized_roi_ex_top_position=round(roi_ex_top, 6),
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
