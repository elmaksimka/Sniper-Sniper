from datetime import UTC, datetime

from app.core.analytics import (
    CreatorAnalytics,
    TokenAnalytics,
    TokenHolderSummary,
)
from app.services.token_score_calculator import TokenScoreCalculator


def make_analytics(
    total_trades: int = 50,
    unique_wallets: int = 20,
    buy_volume: float = 100,
    sell_volume: float = 100,
) -> TokenAnalytics:
    return TokenAnalytics(
        address="mint",
        total_trades=total_trades,
        buy_count=25,
        sell_count=25,
        unique_wallets=unique_wallets,
        buy_volume=buy_volume,
        sell_volume=sell_volume,
        net_token_flow=buy_volume - sell_volume,
        net_wallet_sol_change=0,
        first_trade_at=None,
        last_trade_at=None,
    )


def make_holders(
    observed_wallets: int = 10,
    active_holders: int = 10,
    top_share: float = 0.1,
    incomplete_ratio: float = 0,
) -> TokenHolderSummary:
    return TokenHolderSummary(
        observed_wallet_count=observed_wallets,
        active_holder_count=active_holders,
        total_observed_quantity=100,
        top_holder_quantity=100 * top_share,
        top_holder_share=top_share,
        incomplete_holder_count=int(observed_wallets * incomplete_ratio),
        incomplete_holder_ratio=incomplete_ratio,
    )


def make_creator() -> CreatorAnalytics:
    now = datetime.now(UTC)
    return CreatorAnalytics(
        creator_address="creator",
        token_count=5,
        traded_token_count=5,
        total_trades=100,
        unique_traders=20,
        observed_sol_volume=10,
        net_wallet_sol_change=0,
        first_token_created_at=now,
        latest_token_created_at=now,
        tokens=[],
    )


def test_mature_balanced_token_receives_explainable_high_score() -> None:
    score = TokenScoreCalculator().calculate(
        make_analytics(),
        make_holders(),
        make_creator(),
        creator_known=True,
    )

    assert score.score == 98
    assert score.grade == "A"
    assert score.methodology_version == "token-v1"
    assert score.activity_score == 20
    assert score.participation_score == 15
    assert score.holder_distribution_score == 23
    assert score.flow_balance_score == 15
    assert score.creator_history_score == 15
    assert score.data_quality_score == 10


def test_concentration_incomplete_history_and_unknown_creator_reduce_score() -> None:
    score = TokenScoreCalculator().calculate(
        make_analytics(total_trades=10, unique_wallets=2),
        make_holders(
            observed_wallets=2,
            active_holders=1,
            top_share=1,
            incomplete_ratio=0.5,
        ),
        creator=None,
        creator_known=False,
    )

    assert score.holder_distribution_score == 0.5
    assert score.creator_history_score == 0
    assert score.data_quality_score == 3.5
    assert score.top_holder_share == 1
    assert score.incomplete_holder_ratio == 0.5


def test_empty_token_does_not_receive_free_history_quality_points() -> None:
    score = TokenScoreCalculator().calculate(
        make_analytics(0, 0, 0, 0),
        make_holders(0, 0, 0, 0),
        creator=None,
        creator_known=True,
    )

    assert score.score == 3
    assert score.data_quality_score == 3
    assert score.grade == "E"
