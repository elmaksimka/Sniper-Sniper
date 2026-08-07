from app.core.analytics import TokenAnalytics, TokenHolderSummary
from app.services.early_token_score_calculator import EarlyTokenScoreCalculator


def analytics(*, trades: int, wallets: int, buys: float, sells: float) -> TokenAnalytics:
    return TokenAnalytics(
        address="mint",
        total_trades=trades,
        buy_count=trades if sells == 0 else trades - 1,
        sell_count=0 if sells == 0 else 1,
        unique_wallets=wallets,
        buy_volume=buys,
        sell_volume=sells,
        net_token_flow=buys - sells,
        net_wallet_sol_change=0,
        first_trade_at=None,
        last_trade_at=None,
    )


def holders(*, wallets: int, top_share: float, incomplete: float = 0) -> TokenHolderSummary:
    return TokenHolderSummary(
        observed_wallet_count=wallets,
        active_holder_count=wallets,
        total_observed_quantity=100,
        top_holder_quantity=100 * top_share,
        top_holder_share=top_share,
        incomplete_holder_count=round(wallets * incomplete),
        incomplete_holder_ratio=incomplete,
    )


def test_single_buy_does_not_receive_high_conviction_score() -> None:
    score = EarlyTokenScoreCalculator().calculate(
        analytics(trades=1, wallets=1, buys=100, sells=0),
        holders(wallets=1, top_share=1),
    )

    assert score.score == 23.5
    assert score.grade == "E"
    assert score.methodology_version == "early-token-v1"


def test_early_multi_wallet_buying_can_clear_signal_threshold() -> None:
    score = EarlyTokenScoreCalculator().calculate(
        analytics(trades=3, wallets=2, buys=300, sells=0),
        holders(wallets=2, top_share=0.6),
    )

    assert score.score == 50.5
    assert score.grade == "C"
    assert score.observed_trade_count == 3
    assert score.observed_wallet_count == 2


def test_sell_pressure_and_incomplete_history_reduce_score() -> None:
    calculator = EarlyTokenScoreCalculator()
    healthy = calculator.calculate(
        analytics(trades=5, wallets=4, buys=400, sells=100),
        holders(wallets=4, top_share=0.35),
    )
    weak = calculator.calculate(
        analytics(trades=5, wallets=4, buys=100, sells=400),
        holders(wallets=4, top_share=0.8, incomplete=0.5),
    )

    assert healthy.score > weak.score
    assert healthy.buy_pressure_score > weak.buy_pressure_score
    assert healthy.data_quality_score > weak.data_quality_score
