from types import SimpleNamespace

from app.core.copy_trading import CopyTradingScoreCalculator
from app.core.trader_style import TraderStyleProfile


def style(*, eligible: bool = True, burst: int = 34) -> TraderStyleProfile:
    return TraderStyleProfile(
        eligible=eligible,
        reason=None if eligible else "multi_token_burst",
        total_trades=347,
        unique_tokens=12,
        max_trades_60s=burst,
        max_distinct_tokens_60s=1,
        max_trades_per_token=289,
        max_side_switches_per_token=1,
        rapid_round_trips=0,
        long_hold_positions=11,
    )


def snapshot(**overrides: float | int) -> SimpleNamespace:
    values: dict[str, float | int] = {
        "priced_trade_ratio": 0.95389,
        "unmatched_sell_ratio": 0,
        "realized_position_count": 5,
        "win_rate": 0.6,
        "pnl_concentration_ratio": 0.741111,
        "realized_roi_ex_top_position": 116.137587,
        "realized_pnl_sol": 10,
        "realized_pnl_ex_top_position_sol": 2,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_fast_profitable_wallet_is_manual_copy_candidate() -> None:
    result = CopyTradingScoreCalculator().calculate(
        snapshot(),  # type: ignore[arg-type]
        style(),
    )

    assert result.score == 72.94
    assert result.mode == "manual"


def test_same_wallet_with_copyable_pace_is_automatic() -> None:
    result = CopyTradingScoreCalculator().calculate(
        snapshot(realized_position_count=20),  # type: ignore[arg-type]
        style(burst=1),
    )

    assert result.score == 85.44
    assert result.mode == "automatic"


def test_low_quality_burst_wallet_is_unsuitable() -> None:
    result = CopyTradingScoreCalculator().calculate(
        snapshot(
            priced_trade_ratio=0.2,
            unmatched_sell_ratio=0.8,
            realized_position_count=1,
            win_rate=0.2,
            pnl_concentration_ratio=1,
            realized_roi_ex_top_position=-1,
        ),  # type: ignore[arg-type]
        style(eligible=False),
    )

    assert result.score < 55
    assert result.mode == "unsuitable"
