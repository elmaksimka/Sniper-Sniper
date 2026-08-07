from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    JSON,
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
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now_naive,
    )

    trades: Mapped[list["Trade"]] = relationship(
        back_populates="token",
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
        DateTime,
        default=utc_now_naive,
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
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    wallet: Mapped["Wallet"] = relationship(back_populates="score_snapshot")


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
