from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    String,
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

    symbol: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )

    name: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    creator: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    decimals: Mapped[int | None] = mapped_column(
        nullable=True,
    )

    supply: Mapped[int | None] = mapped_column(
        nullable=True,
    )

    first_seen_tx: Mapped[str | None] = mapped_column(
        String(128),
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