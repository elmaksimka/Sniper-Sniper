"""add durable paper copy trading

Revision ID: 3a9d7c2e6f10
Revises: f73a8c19b2d4
Create Date: 2026-08-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "3a9d7c2e6f10"
down_revision: str | Sequence[str] | None = "f73a8c19b2d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "paper_copy_portfolios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_wallet", sa.String(length=64), nullable=False),
        sa.Column("initial_balance_usd", sa.Float(), nullable=False),
        sa.Column("cash_balance_usd", sa.Float(), nullable=False),
        sa.Column("allocation_usd", sa.Float(), nullable=False),
        sa.Column("max_open_positions", sa.Integer(), nullable=False),
        sa.Column("reaction_delay_seconds", sa.Float(), nullable=False),
        sa.Column("slippage_bps", sa.Integer(), nullable=False),
        sa.Column("minimum_liquidity_usd", sa.Float(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_wallet"),
    )
    op.create_index(
        "ix_paper_copy_portfolios_source_wallet",
        "paper_copy_portfolios",
        ["source_wallet"],
        unique=True,
    )
    op.create_index(
        "ix_paper_copy_portfolios_enabled",
        "paper_copy_portfolios",
        ["enabled"],
    )

    op.create_table(
        "paper_copy_positions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "portfolio_id",
            sa.Integer(),
            sa.ForeignKey("paper_copy_portfolios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_address", sa.String(length=64), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("cost_basis_usd", sa.Float(), nullable=False),
        sa.Column("entry_price_usd", sa.Float(), nullable=False),
        sa.Column("last_price_usd", sa.Float(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "portfolio_id",
            "token_address",
            name="uq_paper_copy_position_portfolio_token",
        ),
    )
    op.create_index(
        "ix_paper_copy_positions_portfolio_id",
        "paper_copy_positions",
        ["portfolio_id"],
    )
    op.create_index(
        "ix_paper_copy_positions_token_address",
        "paper_copy_positions",
        ["token_address"],
    )

    op.create_table(
        "paper_copy_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "portfolio_id",
            sa.Integer(),
            sa.ForeignKey("paper_copy_portfolios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_signature", sa.String(length=128), nullable=False),
        sa.Column("token_address", sa.String(length=64), nullable=False),
        sa.Column("side", sa.String(length=10), nullable=False),
        sa.Column("source_amount", sa.Float(), nullable=False),
        sa.Column("source_transaction_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("execute_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=256), nullable=True),
        sa.Column("execution_price_usd", sa.Float(), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("value_usd", sa.Float(), nullable=True),
        sa.Column("realized_pnl_usd", sa.Float(), nullable=True),
        sa.Column("liquidity_usd", sa.Float(), nullable=True),
        sa.Column("cash_balance_after_usd", sa.Float(), nullable=True),
        sa.Column("equity_after_usd", sa.Float(), nullable=True),
        sa.Column("open_positions_after", sa.Integer(), nullable=True),
        sa.Column("notification_sent", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "portfolio_id",
            "source_signature",
            "token_address",
            name="uq_paper_copy_order_source_trade",
        ),
    )
    op.create_index(
        "ix_paper_copy_orders_portfolio_id",
        "paper_copy_orders",
        ["portfolio_id"],
    )
    op.create_index(
        "ix_paper_copy_orders_token_address",
        "paper_copy_orders",
        ["token_address"],
    )
    op.create_index(
        "ix_paper_copy_orders_execute_after",
        "paper_copy_orders",
        ["execute_after"],
    )
    op.create_index("ix_paper_copy_orders_status", "paper_copy_orders", ["status"])
    op.create_index(
        "ix_paper_copy_orders_notification_sent",
        "paper_copy_orders",
        ["notification_sent"],
    )


def downgrade() -> None:
    op.drop_table("paper_copy_orders")
    op.drop_table("paper_copy_positions")
    op.drop_table("paper_copy_portfolios")
