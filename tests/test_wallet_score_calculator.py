import pytest

from app.core.analytics import TokenPosition, WalletAnalytics
from app.services.wallet_score_calculator import WalletScoreCalculator


def make_analytics(
    total_trades: int = 50,
    buy_count: int = 10,
    sell_count: int = 10,
    unique_tokens: int = 10,
    priced_trade_count: int | None = None,
) -> WalletAnalytics:
    return WalletAnalytics(
        address="wallet",
        total_trades=total_trades,
        buy_count=buy_count,
        sell_count=sell_count,
        unique_tokens=unique_tokens,
        sol_spent=0,
        sol_received=0,
        net_sol_change=0,
        first_trade_at=None,
        last_trade_at=None,
        priced_trade_count=(
            total_trades if priced_trade_count is None else priced_trade_count
        ),
    )


def make_position(
    realized_pnl: float = 5,
    sol_spent: float = 10,
    total_sold: float = 10,
    unmatched_sells: float = 0,
    realized_cost_basis: float | None = None,
) -> TokenPosition:
    return TokenPosition(
        token_address="mint",
        quantity=0,
        cost_basis_sol=0,
        average_entry_price_sol=0,
        realized_pnl_sol=realized_pnl,
        total_bought=10,
        total_sold=total_sold,
        sol_spent=sol_spent,
        sol_received=15,
        unmatched_sell_quantity=unmatched_sells,
        trade_count=2,
        realized_cost_basis_sol=(
            sol_spent
            if realized_cost_basis is None
            else realized_cost_basis
        ),
    )


def test_maximum_wallet_score_is_explainable() -> None:
    score = WalletScoreCalculator().calculate(
        make_analytics(),
        [make_position()],
    )

    assert score.score == 100
    assert score.grade == "A"
    assert score.activity_score == 20
    assert score.diversification_score == 15
    assert score.exit_experience_score == 20
    assert score.realized_performance_score == 35
    assert score.data_quality_score == 10
    assert score.methodology_version == "wallet-v2"


def test_empty_wallet_receives_no_unearned_baseline_points() -> None:
    score = WalletScoreCalculator().calculate(
        make_analytics(0, 0, 0, 0),
        [],
    )

    assert score.score == 0
    assert score.grade == "E"
    assert score.realized_performance_score == 0
    assert score.data_quality_score == 0


def test_unmatched_sells_reduce_data_quality() -> None:
    score = WalletScoreCalculator().calculate(
        make_analytics(total_trades=20, unique_tokens=1),
        [make_position(realized_pnl=0, unmatched_sells=5)],
    )

    assert score.unmatched_sell_ratio == 0.5
    assert score.data_quality_score == 5


def test_open_inventory_does_not_dilute_realized_roi() -> None:
    score = WalletScoreCalculator().calculate(
        make_analytics(total_trades=3, buy_count=2, sell_count=1),
        [
            make_position(realized_pnl=1, realized_cost_basis=1),
            make_position(
                realized_pnl=0,
                sol_spent=100,
                realized_cost_basis=0,
            ),
        ],
    )

    assert score.realized_roi == 1
    assert score.realized_performance_score == 35


def test_unpriced_trades_reduce_quality_coverage() -> None:
    score = WalletScoreCalculator().calculate(
        make_analytics(total_trades=10, priced_trade_count=6),
        [make_position()],
    )

    assert score.priced_trade_ratio == 0.6
    assert score.data_quality_score == 6


@pytest.mark.parametrize(
    ("score", "grade"),
    [(100, "A"), (80, "A"), (79.99, "B"), (65, "B"), (50, "C"), (35, "D"), (0, "E")],
)
def test_grade_boundaries(score: float, grade: str) -> None:
    assert WalletScoreCalculator._grade(score) == grade
