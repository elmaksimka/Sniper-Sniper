from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TraderStyleProfile:
    eligible: bool
    reason: str | None
    total_trades: int
    unique_tokens: int
    max_trades_60s: int
    max_distinct_tokens_60s: int
    max_trades_per_token: int
    max_side_switches_per_token: int
    rapid_round_trips: int
    long_hold_positions: int
