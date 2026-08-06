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
