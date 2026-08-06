from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WalletScore:
    wallet_address: str
    score: float
    grade: str
    methodology_version: str
    activity_score: float
    diversification_score: float
    exit_experience_score: float
    realized_performance_score: float
    data_quality_score: float
    realized_pnl_sol: float
    realized_roi: float
    unmatched_sell_ratio: float
