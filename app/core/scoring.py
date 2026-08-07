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


@dataclass(frozen=True, slots=True)
class TokenScore:
    token_address: str
    score: float
    grade: str
    methodology_version: str
    activity_score: float
    participation_score: float
    holder_distribution_score: float
    flow_balance_score: float
    creator_history_score: float
    data_quality_score: float
    observed_holder_count: int
    top_holder_share: float
    incomplete_holder_ratio: float


@dataclass(frozen=True, slots=True)
class EarlyTokenScore:
    token_address: str
    score: float
    grade: str
    methodology_version: str
    activity_score: float
    participation_score: float
    buy_pressure_score: float
    holder_distribution_score: float
    data_quality_score: float
    observed_trade_count: int
    observed_wallet_count: int
    top_holder_share: float
    incomplete_holder_ratio: float
