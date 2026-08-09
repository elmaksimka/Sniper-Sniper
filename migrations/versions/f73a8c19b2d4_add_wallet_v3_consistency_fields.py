"""add wallet v3 consistency fields

Revision ID: f73a8c19b2d4
Revises: e42b61c7d9a3
Create Date: 2026-08-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "f73a8c19b2d4"
down_revision: str | Sequence[str] | None = "e42b61c7d9a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "wallet_score_snapshots",
        sa.Column("realized_position_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "wallet_score_snapshots",
        sa.Column("profitable_position_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "wallet_score_snapshots",
        sa.Column("win_rate", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "wallet_score_snapshots",
        sa.Column("pnl_concentration_ratio", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "wallet_score_snapshots",
        sa.Column("realized_pnl_ex_top_position_sol", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "wallet_score_snapshots",
        sa.Column("realized_roi_ex_top_position", sa.Float(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("wallet_score_snapshots", "realized_roi_ex_top_position")
    op.drop_column("wallet_score_snapshots", "realized_pnl_ex_top_position_sol")
    op.drop_column("wallet_score_snapshots", "pnl_concentration_ratio")
    op.drop_column("wallet_score_snapshots", "win_rate")
    op.drop_column("wallet_score_snapshots", "profitable_position_count")
    op.drop_column("wallet_score_snapshots", "realized_position_count")
