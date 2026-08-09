"""add wallet v2 quality fields

Revision ID: c91e7a42d5f0
Revises: b8f4c2d1e6a9
Create Date: 2026-08-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "c91e7a42d5f0"
down_revision: str | Sequence[str] | None = "b8f4c2d1e6a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "wallet_score_snapshots",
        sa.Column(
            "priced_trade_ratio",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "wallet_score_snapshots",
        sa.Column(
            "realized_cost_basis_sol",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("wallet_score_snapshots", "realized_cost_basis_sol")
    op.drop_column("wallet_score_snapshots", "priced_trade_ratio")
