from datetime import UTC, datetime

import pytest

from app.infrastructure.models import Token, Trade
from app.services.position_calculator import PositionCalculator


def make_trade(
    trade_id: int,
    token: Token,
    side: str,
    amount: float,
    sol_change: float,
) -> Trade:
    return Trade(
        id=trade_id,
        token_id=token.id,
        wallet_id=1,
        token=token,
        side=side,
        amount=amount,
        price=0,
        sol_change=sol_change,
        timestamp=datetime.now(UTC),
    )


def test_weighted_cost_basis_and_partial_sell() -> None:
    token = Token(id=1, address="mint")
    trades = [
        make_trade(1, token, "buy", 10, -1),
        make_trade(2, token, "buy", 10, -2),
        make_trade(3, token, "sell", 5, 1),
    ]

    positions = PositionCalculator().calculate(trades)

    assert len(positions) == 1
    position = positions[0]
    assert position.quantity == 15
    assert position.cost_basis_sol == pytest.approx(2.25)
    assert position.average_entry_price_sol == pytest.approx(0.15)
    assert position.realized_pnl_sol == pytest.approx(0.25)
    assert position.sol_spent == 3
    assert position.sol_received == 1
    assert position.has_incomplete_history is False


def test_sell_without_known_inventory_is_marked_unmatched() -> None:
    token = Token(id=1, address="mint")
    trades = [make_trade(1, token, "sell", 5, 1)]

    positions = PositionCalculator().calculate(trades, include_closed=True)

    assert len(positions) == 1
    assert positions[0].quantity == 0
    assert positions[0].realized_pnl_sol == 0
    assert positions[0].unmatched_sell_quantity == 5
    assert positions[0].has_incomplete_history is True


def test_oversell_allocates_proceeds_only_to_matched_quantity() -> None:
    token = Token(id=1, address="mint")
    trades = [
        make_trade(1, token, "buy", 10, -1),
        make_trade(2, token, "sell", 20, 3),
    ]

    position = PositionCalculator().calculate(
        trades,
        include_closed=True,
    )[0]

    assert position.quantity == 0
    assert position.unmatched_sell_quantity == 10
    assert position.realized_pnl_sol == pytest.approx(0.5)


def test_closed_positions_are_hidden_by_default() -> None:
    token = Token(id=1, address="mint")
    trades = [
        make_trade(1, token, "buy", 2, -1),
        make_trade(2, token, "sell", 2, 1.5),
    ]

    assert PositionCalculator().calculate(trades) == []
    assert len(PositionCalculator().calculate(trades, include_closed=True)) == 1
