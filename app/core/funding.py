from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class NativeTransfer:
    source: str
    destination: str
    amount_sol: float
    instruction_index: str


@dataclass(frozen=True, slots=True)
class FundingCounterparty:
    address: str
    direction: str
    transfer_count: int
    total_sol: float
    first_transfer_at: datetime
    last_transfer_at: datetime


@dataclass(frozen=True, slots=True)
class WalletFundingAnalytics:
    wallet_address: str
    incoming_transfer_count: int
    outgoing_transfer_count: int
    incoming_sol: float
    outgoing_sol: float
    net_sol: float
    unique_funders: int
    unique_destinations: int
    first_funder: str | None
    first_funding_at: datetime | None
    counterparties: list[FundingCounterparty]
