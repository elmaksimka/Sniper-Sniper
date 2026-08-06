from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
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
        default=datetime.utcnow,
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
        default=datetime.utcnow,
    )

    trades: Mapped[list["Trade"]] = relationship(
        back_populates="wallet",
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
        default=datetime.utcnow,
    )

    token: Mapped["Token"] = relationship(
        back_populates="trades",
    )

    wallet: Mapped["Wallet"] = relationship(
        back_populates="trades",
    )
