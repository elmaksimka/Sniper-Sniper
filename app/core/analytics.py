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
