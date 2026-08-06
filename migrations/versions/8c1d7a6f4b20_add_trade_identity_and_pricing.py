"""add trade identity and pricing

Revision ID: 8c1d7a6f4b20
Revises: 0f2b1f541f98
Create Date: 2026-08-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "8c1d7a6f4b20"
down_revision: str | Sequence[str] | None = "0f2b1f541f98"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "trades",
        sa.Column("price", sa.Float(), server_default="0", nullable=False),
    )
    op.add_column(
        "trades",
        sa.Column("sol_change", sa.Float(), server_default="0", nullable=False),
    )
    op.add_column(
        "trades",
        sa.Column("signature", sa.String(length=128), nullable=True),
    )
    op.create_index(
        op.f("ix_trades_signature"),
        "trades",
        ["signature"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_trades_signature_token_wallet",
        "trades",
        ["signature", "token_id", "wallet_id"],
    )
    op.alter_column("trades", "price", server_default=None)
    op.alter_column("trades", "sol_change", server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        "uq_trades_signature_token_wallet",
        "trades",
        type_="unique",
    )
    op.drop_index(op.f("ix_trades_signature"), table_name="trades")
    op.drop_column("trades", "signature")
    op.drop_column("trades", "sol_change")
    op.drop_column("trades", "price")
