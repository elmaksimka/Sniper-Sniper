"""add wallet monitors

Revision ID: a71c9d2e4f60
Revises: f2a8c5e19d40
Create Date: 2026-08-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "a71c9d2e4f60"
down_revision: str | Sequence[str] | None = "f2a8c5e19d40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "wallet_monitors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("wallet_id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("checkpoint_signature", sa.String(length=128), nullable=True),
        sa.Column("last_scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["wallet_id"],
            ["wallets.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("wallet_id"),
    )
    op.create_index(
        op.f("ix_wallet_monitors_enabled"),
        "wallet_monitors",
        ["enabled"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_wallet_monitors_enabled"), table_name="wallet_monitors")
    op.drop_table("wallet_monitors")
