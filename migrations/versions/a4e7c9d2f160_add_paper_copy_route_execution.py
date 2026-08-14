"""add paper copy route execution metadata

Revision ID: a4e7c9d2f160
Revises: 7c9f1a4d2e63
Create Date: 2026-08-14

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "a4e7c9d2f160"
down_revision: str | Sequence[str] | None = "7c9f1a4d2e63"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "paper_copy_orders",
        sa.Column("price_impact_pct", sa.Float(), nullable=True),
    )
    op.add_column(
        "paper_copy_orders",
        sa.Column("route_fee_bps", sa.Integer(), nullable=True),
    )
    op.add_column(
        "paper_copy_orders",
        sa.Column("route_provider", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "paper_copy_orders",
        sa.Column("route_path", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("paper_copy_orders", "route_path")
    op.drop_column("paper_copy_orders", "route_provider")
    op.drop_column("paper_copy_orders", "route_fee_bps")
    op.drop_column("paper_copy_orders", "price_impact_pct")
