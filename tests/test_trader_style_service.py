from datetime import UTC, datetime, timedelta

from app.infrastructure.models import Token, Trade
from app.services.trader_style_service import TraderStyleService


def service() -> TraderStyleService:
    return TraderStyleService(
        None,  # type: ignore[arg-type]
        min_history_trades=10,
        min_hold_minutes=30,
        max_distinct_tokens_60s=4,
        max_side_switches_per_token=2,
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
    assert profile.max_distinct_tokens_60s == 1


def test_high_frequency_multi_token_burst_is_rejected() -> None:
    started = datetime(2026, 1, 1, tzinfo=UTC)
    trades = [
        observed_trade(index, f"token-{index}", "buy", started + timedelta(seconds=index))
        for index in range(10)
    ]

    profile = service().evaluate_trades(trades, started + timedelta(hours=1))

    assert profile.eligible is False
    assert profile.reason == "multi_token_burst"
    assert profile.max_trades_60s == 10
    assert profile.max_distinct_tokens_60s == 10


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


def test_multiple_staged_buys_of_one_token_are_allowed() -> None:
    started = datetime(2026, 1, 1, tzinfo=UTC)
    trades = [
        observed_trade(index, "churned-token", "buy", started + timedelta(minutes=index * 2))
        for index in range(5)
    ] + [
        observed_trade(index + 5, f"token-{index}", "buy", started + timedelta(minutes=15 + index * 2))
        for index in range(5)
    ]

    profile = service().evaluate_trades(trades, started + timedelta(hours=1))

    assert profile.eligible is True
    assert profile.reason is None
    assert profile.max_trades_per_token == 5
    assert profile.max_side_switches_per_token == 0


def test_repeated_buy_sell_switching_is_rejected_even_if_position_stays_open() -> None:
    started = datetime(2026, 1, 1, tzinfo=UTC)
    sides = ["buy", "sell", "buy", "sell", "buy", "sell"]
    trades = [
        Trade(
            id=index,
            token_id=1,
            wallet_id=1,
            token=Token(address="alternating-token"),
            side=side,
            amount=10 if index == 1 else 1,
            price=0,
            sol_change=-1 if side == "buy" else 1,
            signature=f"alternating-{index}",
            timestamp=started + timedelta(minutes=index * 3),
        )
        for index, side in enumerate(sides, start=1)
    ] + [
        observed_trade(
            index + 10,
            f"token-{index}",
            "buy",
            started + timedelta(minutes=20 + index * 3),
        )
        for index in range(4)
    ]

    profile = service().evaluate_trades(trades, started + timedelta(hours=1))

    assert profile.eligible is False
    assert profile.reason == "repeated_buy_sell_switching"
    assert profile.max_side_switches_per_token == 3


def test_side_switches_spread_over_time_are_not_treated_as_bot_burst() -> None:
    started = datetime(2026, 1, 1, tzinfo=UTC)
    sides = ["buy", "sell", "buy", "sell", "buy", "sell"]
    trades = [
        Trade(
            id=index,
            token_id=1,
            wallet_id=1,
            token=Token(address="patient-active-token"),
            side=side,
            amount=10 if index == 1 else 1,
            price=0,
            sol_change=-1 if side == "buy" else 1,
            signature=f"patient-active-{index}",
            timestamp=started + timedelta(minutes=(index - 1) * 15),
        )
        for index, side in enumerate(sides, start=1)
    ] + [
        observed_trade(
            index + 10,
            f"token-{index}",
            "buy",
            started + timedelta(minutes=80 + index * 15),
        )
        for index in range(4)
    ]

    profile = service().evaluate_trades(trades, started + timedelta(hours=3))

    assert profile.eligible is True
    assert profile.reason is None
    assert profile.max_side_switches_per_token == 0
