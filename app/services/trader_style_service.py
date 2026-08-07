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
        max_trades_60s: int,
        max_trades_per_token: int,
        rapid_round_trip_seconds: float,
        max_rapid_round_trips: int,
    ) -> None:
        self.analytics = AnalyticsRepository(session)
        self.min_history_trades = min_history_trades
        self.min_hold_seconds = min_hold_minutes * 60
        self.max_trades_60s = max_trades_60s
        self.max_trades_per_token = max_trades_per_token
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
        max_per_token = max((len(items) for items in per_token.values()), default=0)
        rapid_round_trips = 0
        long_holds = 0
        for items in per_token.values():
            first_buy = next((item for item in items if item.side == "buy"), None)
            if first_buy is None:
                continue
            first_sell = next(
                (
                    item
                    for item in items
                    if item.side == "sell" and item.timestamp >= first_buy.timestamp
                ),
                None,
            )
            held_until = first_sell.timestamp if first_sell is not None else observed_at
            held_seconds = (
                self._aware(held_until) - self._aware(first_buy.timestamp)
            ).total_seconds()
            if first_sell is not None and held_seconds <= self.rapid_round_trip_seconds:
                rapid_round_trips += 1
            if held_seconds >= self.min_hold_seconds:
                long_holds += 1

        reason: str | None = None
        if len(ordered) < self.min_history_trades:
            reason = "insufficient_history"
        elif burst > self.max_trades_60s:
            reason = "high_frequency_burst"
        elif max_per_token > self.max_trades_per_token:
            reason = "excessive_token_churn"
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
            max_trades_per_token=max_per_token,
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

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
