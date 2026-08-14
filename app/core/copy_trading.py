from __future__ import annotations

from dataclasses import dataclass

from app.core.trader_style import TraderStyleProfile
from app.infrastructure.models import WalletScoreSnapshot


@dataclass(frozen=True, slots=True)
class CopyTradingAssessment:
    score: float
    mode: str


class CopyTradingScoreCalculator:
    """Estimate whether observed wallet trades can be copied reliably."""

    def calculate(
        self,
        snapshot: WalletScoreSnapshot,
        style: TraderStyleProfile,
    ) -> CopyTradingAssessment:
        pricing = 25 * self._clamp(snapshot.priced_trade_ratio, 0, 1)
        matching = 20 * (1 - self._clamp(snapshot.unmatched_sell_ratio, 0, 1))
        experience = 15 * self._clamp(snapshot.realized_position_count / 10, 0, 1)
        consistency = 15 * self._clamp(snapshot.win_rate, 0, 1)
        diversification = 10 * (1 - self._clamp(snapshot.pnl_concentration_ratio, 0, 1))
        resilience = 5 * self._clamp(
            (snapshot.realized_roi_ex_top_position + 0.25) / 0.5,
            0,
            1,
        )
        style_quality = 5 * self._style_factor(style)
        pace = 5 * self._clamp((10 - style.max_trades_60s) / 9, 0, 1)
        score = round(
            self._clamp(
                pricing
                + matching
                + experience
                + consistency
                + diversification
                + resilience
                + style_quality
                + pace,
                0,
                100,
            ),
            2,
        )
        robust_history = (
            snapshot.realized_position_count >= 20
            and snapshot.realized_pnl_sol > 0
            and snapshot.realized_pnl_ex_top_position_sol > 0
            and snapshot.pnl_concentration_ratio <= 0.75
        )
        if score >= 75 and style.eligible and robust_history:
            mode = "automatic"
        elif score >= 55:
            mode = "manual"
        else:
            mode = "unsuitable"
        return CopyTradingAssessment(score=score, mode=mode)

    @staticmethod
    def _style_factor(style: TraderStyleProfile) -> float:
        if style.eligible:
            return 1.0
        return {
            "no_proven_long_hold": 0.6,
            "insufficient_history": 0.4,
            "repeated_buy_sell_switching": 0.3,
            "rapid_round_trip": 0.1,
            "multi_token_burst": 0.0,
        }.get(style.reason or "", 0.0)

    @staticmethod
    def _clamp(value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(value, maximum))
