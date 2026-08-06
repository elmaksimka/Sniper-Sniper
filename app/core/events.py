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
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# -----------------------
# Token Events
# -----------------------

@dataclass(slots=True, kw_only=True)
class TokenCreated(Event):
    token_address: str
    creator: str


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


# -----------------------
# Internal Events
# -----------------------

@dataclass(slots=True, kw_only=True)
class ScoreUpdated(Event):
    entity: str
    score: float


@dataclass(slots=True, kw_only=True)
class AlertGenerated(Event):
    message: str
    metadata: dict[str, Any]