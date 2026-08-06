from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.infrastructure.models import Trade, WalletScoreSnapshot


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
