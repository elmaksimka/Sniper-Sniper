from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class WalletAnalytics:
    address: str
    total_trades: int
    buy_count: int
    sell_count: int
    unique_tokens: int
    sol_spent: float
    sol_received: float
    net_sol_change: float
    first_trade_at: datetime | None
    last_trade_at: datetime | None
    priced_trade_count: int = 0


@dataclass(frozen=True, slots=True)
class TokenAnalytics:
    address: str
    total_trades: int
    buy_count: int
    sell_count: int
    unique_wallets: int
    buy_volume: float
    sell_volume: float
    net_token_flow: float
    net_wallet_sol_change: float
    first_trade_at: datetime | None
    last_trade_at: datetime | None


@dataclass(frozen=True, slots=True)
class TokenPosition:
    token_address: str
    quantity: float
    cost_basis_sol: float
    average_entry_price_sol: float
    realized_pnl_sol: float
    total_bought: float
    total_sold: float
    sol_spent: float
    sol_received: float
    unmatched_sell_quantity: float
    trade_count: int
    realized_cost_basis_sol: float = 0.0

    @property
    def has_incomplete_history(self) -> bool:
        return self.unmatched_sell_quantity > 0


@dataclass(frozen=True, slots=True)
class ObservedTokenHolder:
    wallet_address: str
    quantity: float
    total_bought: float
    total_sold: float
    unmatched_sell_quantity: float
    trade_count: int
    first_trade_at: datetime
    last_trade_at: datetime

    @property
    def has_incomplete_history(self) -> bool:
        return self.unmatched_sell_quantity > 0


@dataclass(frozen=True, slots=True)
class CreatorTokenAnalytics:
    token_address: str
    symbol: str | None
    name: str | None
    created_at: datetime
    total_trades: int
    unique_traders: int
    observed_sol_volume: float
    first_trade_at: datetime | None
    last_trade_at: datetime | None


@dataclass(frozen=True, slots=True)
class CreatorAnalytics:
    creator_address: str
    token_count: int
    traded_token_count: int
    total_trades: int
    unique_traders: int
    observed_sol_volume: float
    net_wallet_sol_change: float
    first_token_created_at: datetime
    latest_token_created_at: datetime
    tokens: list[CreatorTokenAnalytics]


@dataclass(frozen=True, slots=True)
class TokenHolderSummary:
    observed_wallet_count: int
    active_holder_count: int
    total_observed_quantity: float
    top_holder_quantity: float
    top_holder_share: float
    incomplete_holder_count: int
    incomplete_holder_ratio: float
