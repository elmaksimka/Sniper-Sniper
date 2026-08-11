from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    JSON,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    pass


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_now_naive() -> datetime:
    return utc_now().replace(tzinfo=None)


class Token(Base):
    __tablename__ = "tokens"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    address: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
    )

    creator: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )

    symbol: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )

    name: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    decimals: Mapped[int | None] = mapped_column(
        nullable=True,
    )

    supply: Mapped[int | None] = mapped_column(
        Numeric(20, 0),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now_naive,
    )

    trades: Mapped[list["Trade"]] = relationship(
        back_populates="token",
    )

    score_snapshot: Mapped["TokenScoreSnapshot | None"] = relationship(
        back_populates="token",
        cascade="all, delete-orphan",
        uselist=False,
    )


class Wallet(Base):
    __tablename__ = "wallets"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    address: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
    )

    first_seen: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now_naive,
    )

    trades: Mapped[list["Trade"]] = relationship(
        back_populates="wallet",
    )

    outgoing_funding_transfers: Mapped[list["FundingTransfer"]] = relationship(
        foreign_keys="FundingTransfer.source_wallet_id",
        back_populates="source_wallet",
    )

    incoming_funding_transfers: Mapped[list["FundingTransfer"]] = relationship(
        foreign_keys="FundingTransfer.destination_wallet_id",
        back_populates="destination_wallet",
    )

    score_snapshot: Mapped["WalletScoreSnapshot | None"] = relationship(
        back_populates="wallet",
        cascade="all, delete-orphan",
        uselist=False,
    )

    monitor: Mapped["WalletMonitor | None"] = relationship(
        back_populates="wallet",
        cascade="all, delete-orphan",
        uselist=False,
    )


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (
        UniqueConstraint(
            "signature",
            "token_id",
            "wallet_id",
            name="uq_trades_signature_token_wallet",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    token_id: Mapped[int] = mapped_column(
        ForeignKey("tokens.id"),
    )

    wallet_id: Mapped[int] = mapped_column(
        ForeignKey("wallets.id"),
    )

    side: Mapped[str] = mapped_column(
        String(10),
    )

    amount: Mapped[float] = mapped_column(
        Float,
    )

    price: Mapped[float] = mapped_column(
        Float,
        default=0,
    )

    sol_change: Mapped[float] = mapped_column(
        Float,
        default=0,
    )

    signature: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )

    token: Mapped["Token"] = relationship(
        back_populates="trades",
    )

    wallet: Mapped["Wallet"] = relationship(
        back_populates="trades",
    )


class FundingTransfer(Base):
    __tablename__ = "funding_transfers"
    __table_args__ = (
        UniqueConstraint(
            "signature",
            "instruction_index",
            name="uq_funding_transfers_signature_instruction",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_wallet_id: Mapped[int] = mapped_column(
        ForeignKey("wallets.id", ondelete="CASCADE"),
        index=True,
    )
    destination_wallet_id: Mapped[int] = mapped_column(
        ForeignKey("wallets.id", ondelete="CASCADE"),
        index=True,
    )
    amount_sol: Mapped[float] = mapped_column(Float)
    signature: Mapped[str] = mapped_column(String(128), index=True)
    instruction_index: Mapped[str] = mapped_column(String(64))
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        index=True,
    )

    source_wallet: Mapped["Wallet"] = relationship(
        foreign_keys=[source_wallet_id],
        back_populates="outgoing_funding_transfers",
    )
    destination_wallet: Mapped["Wallet"] = relationship(
        foreign_keys=[destination_wallet_id],
        back_populates="incoming_funding_transfers",
    )


class WalletScoreSnapshot(Base):
    __tablename__ = "wallet_score_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    wallet_id: Mapped[int] = mapped_column(
        ForeignKey("wallets.id", ondelete="CASCADE"),
        unique=True,
    )
    score: Mapped[float] = mapped_column(Float, index=True)
    grade: Mapped[str] = mapped_column(String(2), index=True)
    methodology_version: Mapped[str] = mapped_column(String(32))
    activity_score: Mapped[float] = mapped_column(Float)
    diversification_score: Mapped[float] = mapped_column(Float)
    exit_experience_score: Mapped[float] = mapped_column(Float)
    realized_performance_score: Mapped[float] = mapped_column(Float)
    data_quality_score: Mapped[float] = mapped_column(Float)
    realized_pnl_sol: Mapped[float] = mapped_column(Float)
    realized_roi: Mapped[float] = mapped_column(Float)
    unmatched_sell_ratio: Mapped[float] = mapped_column(Float)
    priced_trade_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    realized_cost_basis_sol: Mapped[float] = mapped_column(Float, default=0.0)
    realized_position_count: Mapped[int] = mapped_column(default=0)
    profitable_position_count: Mapped[int] = mapped_column(default=0)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    pnl_concentration_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    realized_pnl_ex_top_position_sol: Mapped[float] = mapped_column(Float, default=0.0)
    realized_roi_ex_top_position: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    wallet: Mapped["Wallet"] = relationship(back_populates="score_snapshot")


class TokenScoreSnapshot(Base):
    __tablename__ = "token_score_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_id: Mapped[int] = mapped_column(
        ForeignKey("tokens.id", ondelete="CASCADE"),
        unique=True,
    )
    score: Mapped[float] = mapped_column(Float, index=True)
    grade: Mapped[str] = mapped_column(String(2), index=True)
    methodology_version: Mapped[str] = mapped_column(String(32))
    activity_score: Mapped[float] = mapped_column(Float)
    participation_score: Mapped[float] = mapped_column(Float)
    holder_distribution_score: Mapped[float] = mapped_column(Float)
    flow_balance_score: Mapped[float] = mapped_column(Float)
    creator_history_score: Mapped[float] = mapped_column(Float)
    data_quality_score: Mapped[float] = mapped_column(Float)
    observed_holder_count: Mapped[int] = mapped_column()
    top_holder_share: Mapped[float] = mapped_column(Float)
    incomplete_holder_ratio: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    token: Mapped["Token"] = relationship(back_populates="score_snapshot")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    entity_address: Mapped[str] = mapped_column(String(64), index=True)
    alert_type: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    message: Mapped[str] = mapped_column(String(512))
    details: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    dedupe_key: Mapped[str] = mapped_column(
        String(255),
        unique=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        index=True,
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class WalletMonitor(Base):
    __tablename__ = "wallet_monitors"

    id: Mapped[int] = mapped_column(primary_key=True)
    wallet_id: Mapped[int] = mapped_column(
        ForeignKey("wallets.id", ondelete="CASCADE"),
        unique=True,
    )
    enabled: Mapped[bool] = mapped_column(default=True, index=True)
    checkpoint_signature: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    last_scanned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    wallet: Mapped["Wallet"] = relationship(back_populates="monitor")


class ServiceHeartbeat(Base):
    __tablename__ = "service_heartbeats"

    service_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    instance_id: Mapped[str] = mapped_column(String(128))
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        index=True,
    )
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class PaperCopyPortfolio(Base):
    __tablename__ = "paper_copy_portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_wallet: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    initial_balance_usd: Mapped[float] = mapped_column(Float)
    cash_balance_usd: Mapped[float] = mapped_column(Float)
    allocation_usd: Mapped[float] = mapped_column(Float)
    max_open_positions: Mapped[int]
    reaction_delay_seconds: Mapped[float] = mapped_column(Float)
    slippage_bps: Mapped[int]
    minimum_liquidity_usd: Mapped[float] = mapped_column(Float)
    enabled: Mapped[bool] = mapped_column(default=True, index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class PaperCopyPosition(Base):
    __tablename__ = "paper_copy_positions"
    __table_args__ = (
        UniqueConstraint(
            "portfolio_id",
            "source_wallet",
            "token_address",
            name="uq_paper_copy_position_portfolio_source_token",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("paper_copy_portfolios.id", ondelete="CASCADE"),
        index=True,
    )
    source_wallet: Mapped[str] = mapped_column(String(64), index=True)
    token_address: Mapped[str] = mapped_column(String(64), index=True)
    source_quantity: Mapped[float] = mapped_column(Float, default=0)
    quantity: Mapped[float] = mapped_column(Float, default=0)
    cost_basis_usd: Mapped[float] = mapped_column(Float, default=0)
    entry_price_usd: Mapped[float] = mapped_column(Float, default=0)
    last_price_usd: Mapped[float] = mapped_column(Float, default=0)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class PaperCopyOrder(Base):
    __tablename__ = "paper_copy_orders"
    __table_args__ = (
        UniqueConstraint(
            "portfolio_id",
            "source_signature",
            "token_address",
            name="uq_paper_copy_order_source_trade",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("paper_copy_portfolios.id", ondelete="CASCADE"),
        index=True,
    )
    source_wallet: Mapped[str] = mapped_column(String(64), index=True)
    source_signature: Mapped[str] = mapped_column(String(128))
    token_address: Mapped[str] = mapped_column(String(64), index=True)
    side: Mapped[str] = mapped_column(String(10))
    source_amount: Mapped[float] = mapped_column(Float)
    source_transaction_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    execute_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    execution_price_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    realized_pnl_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    liquidity_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    cash_balance_after_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    equity_after_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    open_positions_after: Mapped[int | None] = mapped_column(nullable=True)
    notification_sent: Mapped[bool] = mapped_column(default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )
    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
