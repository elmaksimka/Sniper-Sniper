from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.trader_style import TraderStyleProfile
from app.infrastructure.models import Trade
from app.repositories.analytics_repository import AnalyticsRepository


class TraderStyleService:
    """Classify observed wallets as patient holders or high-frequency bots."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        min_history_trades: int,
        min_hold_minutes: float,
        max_distinct_tokens_60s: int,
        max_side_switches_per_token: int,
        rapid_round_trip_seconds: float,
        max_rapid_round_trips: int,
        side_switch_window_minutes: float = 10,
    ) -> None:
        self.analytics = AnalyticsRepository(session)
        self.min_history_trades = min_history_trades
        self.min_hold_seconds = min_hold_minutes * 60
        self.max_distinct_tokens_60s = max_distinct_tokens_60s
        self.max_side_switches_per_token = max_side_switches_per_token
        self.side_switch_window_seconds = side_switch_window_minutes * 60
        self.rapid_round_trip_seconds = rapid_round_trip_seconds
        self.max_rapid_round_trips = max_rapid_round_trips

    async def evaluate(self, wallet_address: str) -> TraderStyleProfile:
        trades = await self.analytics.list_wallet_trades(wallet_address)
        return self.evaluate_trades(trades)

    def evaluate_trades(
        self,
        trades: list[Trade],
        now: datetime | None = None,
    ) -> TraderStyleProfile:
        observed_at = now or datetime.now(UTC)
        ordered = sorted(trades, key=lambda trade: (trade.timestamp, trade.id or 0))
        per_token: dict[str, list[Trade]] = defaultdict(list)
        for trade in ordered:
            if trade.token is not None:
                per_token[trade.token.address].append(trade)

        burst = self._maximum_rolling_trades(ordered, 60)
        distinct_token_burst = self._maximum_rolling_distinct_tokens(ordered, 60)
        max_per_token = max((len(items) for items in per_token.values()), default=0)
        max_side_switches = max(
            (
                self._maximum_rolling_side_switches(
                    items,
                    self.side_switch_window_seconds,
                )
                for items in per_token.values()
            ),
            default=0,
        )
        rapid_round_trips = 0
        long_holds = 0
        for items in per_token.values():
            position = 0.0
            cycle_started_at: datetime | None = None
            for item in items:
                if item.side == "buy":
                    if position <= 0:
                        cycle_started_at = item.timestamp
                        position = 0.0
                    position += item.amount
                    continue
                if item.side != "sell" or position <= 0 or cycle_started_at is None:
                    continue
                position -= item.amount
                if position > 1e-12:
                    continue
                held_seconds = (
                    self._aware(item.timestamp) - self._aware(cycle_started_at)
                ).total_seconds()
                if held_seconds <= self.rapid_round_trip_seconds:
                    rapid_round_trips += 1
                if held_seconds >= self.min_hold_seconds:
                    long_holds += 1
                position = 0.0
                cycle_started_at = None
            if position > 0 and cycle_started_at is not None:
                held_seconds = (
                    self._aware(observed_at) - self._aware(cycle_started_at)
                ).total_seconds()
                if held_seconds >= self.min_hold_seconds:
                    long_holds += 1

        reason: str | None = None
        if len(ordered) < self.min_history_trades:
            reason = "insufficient_history"
        elif distinct_token_burst > self.max_distinct_tokens_60s:
            reason = "multi_token_burst"
        elif max_side_switches > self.max_side_switches_per_token:
            reason = "repeated_buy_sell_switching"
        elif rapid_round_trips > self.max_rapid_round_trips:
            reason = "rapid_round_trip"
        elif long_holds < 1:
            reason = "no_proven_long_hold"

        return TraderStyleProfile(
            eligible=reason is None,
            reason=reason,
            total_trades=len(ordered),
            unique_tokens=len(per_token),
            max_trades_60s=burst,
            max_distinct_tokens_60s=distinct_token_burst,
            max_trades_per_token=max_per_token,
            max_side_switches_per_token=max_side_switches,
            rapid_round_trips=rapid_round_trips,
            long_hold_positions=long_holds,
        )

    @classmethod
    def _maximum_rolling_trades(cls, trades: list[Trade], seconds: float) -> int:
        left = 0
        maximum = 0
        for right, trade in enumerate(trades):
            while (
                cls._aware(trade.timestamp) - cls._aware(trades[left].timestamp)
            ).total_seconds() > seconds:
                left += 1
            maximum = max(maximum, right - left + 1)
        return maximum

    @classmethod
    def _maximum_rolling_distinct_tokens(
        cls,
        trades: list[Trade],
        seconds: float,
    ) -> int:
        maximum = 0
        for left, first in enumerate(trades):
            addresses: set[str] = set()
            for trade in trades[left:]:
                if (
                    cls._aware(trade.timestamp) - cls._aware(first.timestamp)
                ).total_seconds() > seconds:
                    break
                if trade.token is not None:
                    addresses.add(trade.token.address)
            maximum = max(maximum, len(addresses))
        return maximum

    @classmethod
    def _maximum_rolling_side_switches(
        cls,
        trades: list[Trade],
        seconds: float,
    ) -> int:
        maximum = 0
        for left, first in enumerate(trades):
            switches = 0
            previous_side = first.side
            for trade in trades[left + 1 :]:
                if (
                    cls._aware(trade.timestamp) - cls._aware(first.timestamp)
                ).total_seconds() > seconds:
                    break
                if trade.side != previous_side:
                    switches += 1
                previous_side = trade.side
            maximum = max(maximum, switches)
        return maximum

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
