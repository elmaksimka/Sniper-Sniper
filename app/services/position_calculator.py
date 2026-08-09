from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.core.analytics import TokenPosition
from app.infrastructure.models import Trade


ZERO = Decimal(0)


@dataclass(slots=True)
class _PositionState:
    quantity: Decimal = ZERO
    priced_quantity: Decimal = ZERO
    cost_basis: Decimal = ZERO
    realized_pnl: Decimal = ZERO
    realized_cost_basis: Decimal = ZERO
    total_bought: Decimal = ZERO
    total_sold: Decimal = ZERO
    sol_spent: Decimal = ZERO
    sol_received: Decimal = ZERO
    unmatched_sells: Decimal = ZERO
    trade_count: int = 0


class PositionCalculator:
    """Build wallet token positions using weighted-average cost basis."""

    def calculate(
        self,
        trades: list[Trade],
        include_closed: bool = False,
    ) -> list[TokenPosition]:
        states: dict[str, _PositionState] = {}

        for trade in trades:
            state = states.setdefault(trade.token.address, _PositionState())
            state.trade_count += 1

            amount = max(Decimal(str(trade.amount)), ZERO)
            sol_change = Decimal(str(trade.sol_change))

            if trade.side == "buy":
                state.quantity += amount
                state.total_bought += amount
                spent = max(-sol_change, ZERO)
                if spent > ZERO:
                    state.priced_quantity += amount
                    state.cost_basis += spent
                state.sol_spent += spent
            elif trade.side == "sell":
                self._apply_sell(state, amount, max(sol_change, ZERO))

        positions = [
            self._to_position(address, state)
            for address, state in states.items()
            if include_closed or state.quantity > ZERO
        ]
        return sorted(positions, key=lambda position: position.token_address)

    @staticmethod
    def _apply_sell(
        state: _PositionState,
        amount: Decimal,
        proceeds: Decimal,
    ) -> None:
        state.total_sold += amount
        state.sol_received += proceeds

        if amount == ZERO:
            return

        matched = min(state.quantity, amount)
        unmatched = amount - matched
        state.unmatched_sells += unmatched

        if matched == ZERO:
            return

        priced_matched = (
            matched * state.priced_quantity / state.quantity
            if state.quantity > ZERO
            else ZERO
        )
        average_cost = (
            state.cost_basis / state.priced_quantity
            if state.priced_quantity > ZERO
            else ZERO
        )
        matched_cost = average_cost * priced_matched
        matched_proceeds = proceeds * (matched / amount)
        priced_proceeds = (
            matched_proceeds * (priced_matched / matched)
            if matched > ZERO
            else ZERO
        )

        if proceeds > ZERO and priced_matched > ZERO:
            state.realized_pnl += priced_proceeds - matched_cost
            state.realized_cost_basis += matched_cost
        state.quantity -= matched
        state.priced_quantity -= priced_matched
        state.cost_basis -= matched_cost

        if state.quantity == ZERO or state.priced_quantity == ZERO:
            state.cost_basis = ZERO
            state.priced_quantity = ZERO

    @staticmethod
    def _to_position(
        token_address: str,
        state: _PositionState,
    ) -> TokenPosition:
        average_entry = (
            state.cost_basis / state.priced_quantity
            if state.priced_quantity > ZERO
            else ZERO
        )
        return TokenPosition(
            token_address=token_address,
            quantity=float(state.quantity),
            cost_basis_sol=float(state.cost_basis),
            average_entry_price_sol=float(average_entry),
            realized_pnl_sol=float(state.realized_pnl),
            total_bought=float(state.total_bought),
            total_sold=float(state.total_sold),
            sol_spent=float(state.sol_spent),
            sol_received=float(state.sol_received),
            unmatched_sell_quantity=float(state.unmatched_sells),
            trade_count=state.trade_count,
            realized_cost_basis_sol=float(state.realized_cost_basis),
        )
