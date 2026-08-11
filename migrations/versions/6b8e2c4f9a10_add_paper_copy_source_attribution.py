"""add paper copy source attribution

Revision ID: 6b8e2c4f9a10
Revises: 3a9d7c2e6f10
Create Date: 2026-08-11

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "6b8e2c4f9a10"
down_revision: str | Sequence[str] | None = "3a9d7c2e6f10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "paper_copy_orders",
        sa.Column(
            "source_wallet", sa.String(length=64), nullable=False, server_default=""
        ),
    )
    op.create_index(
        "ix_paper_copy_orders_source_wallet",
        "paper_copy_orders",
        ["source_wallet"],
    )
    op.add_column(
        "paper_copy_positions",
        sa.Column(
            "source_wallet", sa.String(length=64), nullable=False, server_default=""
        ),
    )
    op.add_column(
        "paper_copy_positions",
        sa.Column("source_quantity", sa.Float(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_paper_copy_positions_source_wallet",
        "paper_copy_positions",
        ["source_wallet"],
    )
    op.drop_constraint(
        "uq_paper_copy_position_portfolio_token",
        "paper_copy_positions",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_paper_copy_position_portfolio_source_token",
        "paper_copy_positions",
        ["portfolio_id", "source_wallet", "token_address"],
    )
    op.alter_column("paper_copy_orders", "source_wallet", server_default=None)
    op.alter_column("paper_copy_positions", "source_wallet", server_default=None)
    op.alter_column("paper_copy_positions", "source_quantity", server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        "uq_paper_copy_position_portfolio_source_token",
        "paper_copy_positions",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_paper_copy_position_portfolio_token",
        "paper_copy_positions",
        ["portfolio_id", "token_address"],
    )
    op.drop_index(
        "ix_paper_copy_positions_source_wallet", table_name="paper_copy_positions"
    )
    op.drop_column("paper_copy_positions", "source_quantity")
    op.drop_column("paper_copy_positions", "source_wallet")
    op.drop_index("ix_paper_copy_orders_source_wallet", table_name="paper_copy_orders")
    op.drop_column("paper_copy_orders", "source_wallet")
