from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any
from uuid import UUID, uuid4


@dataclass(slots=True, kw_only=True)
class Event:
    """
    Base event.

    Every event in the system inherits from this class.
    """

    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )


# -----------------------
# Token Events
# -----------------------

@dataclass(slots=True, kw_only=True)
class TokenCreated(Event):
    token_address: str
    creator: str

    symbol: str | None = None
    name: str | None = None

    decimals: int | None = None
    supply: int | None = None


@dataclass(slots=True, kw_only=True)
class LiquidityAdded(Event):
    token_address: str
    liquidity_usd: float


# -----------------------
# Wallet Events
# -----------------------

@dataclass(slots=True, kw_only=True)
class WalletDiscovered(Event):
    wallet: str


@dataclass(slots=True, kw_only=True)
class WalletUpdated(Event):
    wallet: str


@dataclass(slots=True, kw_only=True)
class TokenUpdated(Event):
    token_address: str


# -----------------------
# Trading Events
# -----------------------

@dataclass(slots=True, kw_only=True)
class TradeObserved(Event):
    token_address: str
    wallet: str
    side: str
    amount: float
    price: float
    sol_change: float
    signature: str | None = None
    transaction_at: datetime | None = None


@dataclass(slots=True, kw_only=True)
class TradeScored(Event):
    token_address: str
    wallet: str
    side: str
    amount: float
    sol_change: float
    signature: str | None
    transaction_at: datetime | None = None


@dataclass(slots=True, kw_only=True)
class NativeTransferObserved(Event):
    source: str
    destination: str
    amount_sol: float
    instruction_index: str
    signature: str
    transaction_at: datetime | None = None


# -----------------------
# Internal Events
# -----------------------

@dataclass(slots=True, kw_only=True)
class ScoreUpdated(Event):
    entity_type: str
    entity: str
    score: float
    grade: str
    methodology_version: str


@dataclass(slots=True, kw_only=True)
class AlertGenerated(Event):
    entity: str
    severity: str
    dedupe_key: str
    message: str
    metadata: dict[str, Any]


@dataclass(slots=True, kw_only=True)
class AlphaSignalGenerated(Event):
    wallet: str
    token_address: str
    wallet_score: float
    wallet_grade: str
    token_score: float
    token_grade: str
    token_score_methodology: str
    observed_trade_count: int
    observed_wallet_count: int
    token_amount: float
    sol_amount: float
    signature: str
    severity: str
    message: str
    market_price_usd: float | None = None
    market_pair_url: str | None = None
    market_liquidity_usd: float | None = None
    market_volume_5m_usd: float | None = None
    market_buys_5m: int | None = None
    market_sells_5m: int | None = None
    trader_entry_price_sol: float | None = None
    trader_entry_price_usd: float | None = None
    trader_buy_value_usd: float | None = None
    market_price_vs_entry: float | None = None
    observed_top_trader_count: int = 1
    trader_long_hold_positions: int = 0
    trader_max_trades_60s: int = 0
    trader_max_distinct_tokens_60s: int = 0
    trader_rapid_round_trips: int = 0
    trader_max_side_switches_per_token: int = 0
