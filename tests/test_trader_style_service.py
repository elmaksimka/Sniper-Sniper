from datetime import UTC, datetime, timedelta

from app.infrastructure.models import Token, Trade
from app.services.trader_style_service import TraderStyleService


def service() -> TraderStyleService:
    return TraderStyleService(
        None,  # type: ignore[arg-type]
        min_history_trades=10,
        min_hold_minutes=30,
        max_trades_60s=5,
        max_trades_per_token=4,
        rapid_round_trip_seconds=120,
        max_rapid_round_trips=0,
    )


def observed_trade(
    trade_id: int,
    token_address: str,
    side: str,
    timestamp: datetime,
) -> Trade:
    return Trade(
        id=trade_id,
        token_id=trade_id,
        wallet_id=1,
        token=Token(address=token_address),
        side=side,
        amount=1,
        price=0,
        sol_change=-1 if side == "buy" else 1,
        signature=f"signature-{trade_id}",
        timestamp=timestamp,
    )


def test_patient_holder_is_eligible() -> None:
    started = datetime(2026, 1, 1, tzinfo=UTC)
    trades = [
        observed_trade(index, f"token-{index}", "buy", started + timedelta(minutes=index * 2))
        for index in range(10)
    ]

    profile = service().evaluate_trades(trades, started + timedelta(hours=1))

    assert profile.eligible is True
    assert profile.reason is None
    assert profile.long_hold_positions == 10
    assert profile.max_trades_60s == 1


def test_high_frequency_multi_token_burst_is_rejected() -> None:
    started = datetime(2026, 1, 1, tzinfo=UTC)
    trades = [
        observed_trade(index, f"token-{index}", "buy", started + timedelta(seconds=index))
        for index in range(10)
    ]

    profile = service().evaluate_trades(trades, started + timedelta(hours=1))

    assert profile.eligible is False
    assert profile.reason == "high_frequency_burst"
    assert profile.max_trades_60s == 10


def test_rapid_buy_sell_round_trip_is_rejected() -> None:
    started = datetime(2026, 1, 1, tzinfo=UTC)
    trades = [
        observed_trade(1, "round-trip", "buy", started),
        observed_trade(2, "round-trip", "sell", started + timedelta(seconds=60)),
        *[
            observed_trade(
                index + 3,
                f"token-{index}",
                "buy",
                started + timedelta(minutes=(index + 1) * 3),
            )
            for index in range(8)
        ],
    ]

    profile = service().evaluate_trades(trades, started + timedelta(hours=1))

    assert profile.eligible is False
    assert profile.reason == "rapid_round_trip"
    assert profile.rapid_round_trips == 1


def test_excessive_repeated_token_trading_is_rejected() -> None:
    started = datetime(2026, 1, 1, tzinfo=UTC)
    trades = [
        observed_trade(index, "churned-token", "buy", started + timedelta(minutes=index * 2))
        for index in range(5)
    ] + [
        observed_trade(index + 5, f"token-{index}", "buy", started + timedelta(minutes=15 + index * 2))
        for index in range(5)
    ]

    profile = service().evaluate_trades(trades, started + timedelta(hours=1))

    assert profile.eligible is False
    assert profile.reason == "excessive_token_churn"
    assert profile.max_trades_per_token == 5
