from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.infrastructure.models import (
    Alert,
    Trade,
    WalletMonitor,
    WalletScoreSnapshot,
    FundingTransfer,
)


class TokenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    address: str
    creator: str | None
    symbol: str | None
    name: str | None
    decimals: int | None
    supply: int | None
    created_at: datetime


class WalletRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    address: str
    first_seen: datetime


class TradeRead(BaseModel):
    id: int
    signature: str | None
    token_address: str
    wallet_address: str
    side: str
    amount: float
    price: float
    sol_change: float
    timestamp: datetime

    @classmethod
    def from_trade(cls, trade: Trade) -> TradeRead:
        return cls(
            id=trade.id,
            signature=trade.signature,
            token_address=trade.token.address,
            wallet_address=trade.wallet.address,
            side=trade.side,
            amount=trade.amount,
            price=trade.price,
            sol_change=trade.sol_change,
            timestamp=trade.timestamp,
        )


class TokenPage(BaseModel):
    items: list[TokenRead]
    total: int
    limit: int
    offset: int


class WalletPage(BaseModel):
    items: list[WalletRead]
    total: int
    limit: int
    offset: int


class TradePage(BaseModel):
    items: list[TradeRead]
    total: int
    limit: int
    offset: int


class FundingTransferRead(BaseModel):
    id: int
    signature: str
    instruction_index: str
    source: str
    destination: str
    amount_sol: float
    timestamp: datetime

    @classmethod
    def from_transfer(cls, transfer: FundingTransfer) -> FundingTransferRead:
        return cls(
            id=transfer.id,
            signature=transfer.signature,
            instruction_index=transfer.instruction_index,
            source=transfer.source_wallet.address,
            destination=transfer.destination_wallet.address,
            amount_sol=transfer.amount_sol,
            timestamp=transfer.timestamp,
        )


class FundingTransferPage(BaseModel):
    items: list[FundingTransferRead]
    total: int
    limit: int
    offset: int


class FundingCounterpartyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    address: str
    direction: str
    transfer_count: int
    total_sol: float
    first_transfer_at: datetime
    last_transfer_at: datetime


class WalletFundingAnalyticsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    counterparties: list[FundingCounterpartyRead]


class WalletAnalyticsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


class TokenAnalyticsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


class ObservedTokenHolderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    wallet_address: str
    quantity: float
    total_bought: float
    total_sold: float
    unmatched_sell_quantity: float
    trade_count: int
    first_trade_at: datetime
    last_trade_at: datetime
    has_incomplete_history: bool


class ObservedTokenHolderPage(BaseModel):
    token_address: str
    items: list[ObservedTokenHolderRead]
    total: int
    limit: int
    offset: int
    include_closed: bool


class CreatorTokenAnalyticsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    token_address: str
    symbol: str | None
    name: str | None
    created_at: datetime
    total_trades: int
    unique_traders: int
    observed_sol_volume: float
    first_trade_at: datetime | None
    last_trade_at: datetime | None


class CreatorAnalyticsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    creator_address: str
    token_count: int
    traded_token_count: int
    total_trades: int
    unique_traders: int
    observed_sol_volume: float
    net_wallet_sol_change: float
    first_token_created_at: datetime
    latest_token_created_at: datetime
    tokens: list[CreatorTokenAnalyticsRead]


class TokenPositionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    has_incomplete_history: bool


class WalletPositionsRead(BaseModel):
    wallet_address: str
    items: list[TokenPositionRead]
    total: int


class WalletScoreRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    wallet_address: str
    score: float
    grade: str
    methodology_version: str
    activity_score: float
    diversification_score: float
    exit_experience_score: float
    realized_performance_score: float
    data_quality_score: float
    realized_pnl_sol: float
    realized_roi: float
    unmatched_sell_ratio: float


class TokenScoreRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    token_address: str
    score: float
    grade: str
    methodology_version: str
    activity_score: float
    participation_score: float
    holder_distribution_score: float
    flow_balance_score: float
    creator_history_score: float
    data_quality_score: float
    observed_holder_count: int
    top_holder_share: float
    incomplete_holder_ratio: float


class WalletScoreSnapshotRead(WalletScoreRead):
    updated_at: datetime

    @classmethod
    def from_snapshot(
        cls,
        snapshot: WalletScoreSnapshot,
    ) -> WalletScoreSnapshotRead:
        return cls(
            wallet_address=snapshot.wallet.address,
            score=snapshot.score,
            grade=snapshot.grade,
            methodology_version=snapshot.methodology_version,
            activity_score=snapshot.activity_score,
            diversification_score=snapshot.diversification_score,
            exit_experience_score=snapshot.exit_experience_score,
            realized_performance_score=snapshot.realized_performance_score,
            data_quality_score=snapshot.data_quality_score,
            realized_pnl_sol=snapshot.realized_pnl_sol,
            realized_roi=snapshot.realized_roi,
            unmatched_sell_ratio=snapshot.unmatched_sell_ratio,
            updated_at=snapshot.updated_at,
        )


class WalletScoreLeaderboardPage(BaseModel):
    items: list[WalletScoreSnapshotRead]
    total: int
    limit: int
    offset: int


class AlertRead(BaseModel):
    id: int
    entity_type: str
    entity_address: str
    alert_type: str
    severity: str
    message: str
    metadata: dict
    dedupe_key: str
    created_at: datetime
    acknowledged_at: datetime | None

    @classmethod
    def from_alert(cls, alert: Alert) -> AlertRead:
        return cls(
            id=alert.id,
            entity_type=alert.entity_type,
            entity_address=alert.entity_address,
            alert_type=alert.alert_type,
            severity=alert.severity,
            message=alert.message,
            metadata=alert.details,
            dedupe_key=alert.dedupe_key,
            created_at=alert.created_at,
            acknowledged_at=alert.acknowledged_at,
        )


class AlertPage(BaseModel):
    items: list[AlertRead]
    total: int
    limit: int
    offset: int


class MonitorCreate(BaseModel):
    address: str


class MonitorRead(BaseModel):
    id: int
    wallet_address: str
    enabled: bool
    checkpoint_signature: str | None
    last_scanned_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_monitor(cls, monitor: WalletMonitor) -> MonitorRead:
        return cls(
            id=monitor.id,
            wallet_address=monitor.wallet.address,
            enabled=monitor.enabled,
            checkpoint_signature=monitor.checkpoint_signature,
            last_scanned_at=monitor.last_scanned_at,
            last_error=monitor.last_error,
            created_at=monitor.created_at,
            updated_at=monitor.updated_at,
        )


class MonitorPage(BaseModel):
    items: list[MonitorRead]
    total: int
