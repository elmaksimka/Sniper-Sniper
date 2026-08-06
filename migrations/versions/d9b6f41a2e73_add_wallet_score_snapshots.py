"""add wallet score snapshots

Revision ID: d9b6f41a2e73
Revises: 8c1d7a6f4b20
Create Date: 2026-08-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "d9b6f41a2e73"
down_revision: str | Sequence[str] | None = "8c1d7a6f4b20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "wallet_score_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("wallet_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("grade", sa.String(length=2), nullable=False),
        sa.Column("methodology_version", sa.String(length=32), nullable=False),
        sa.Column("activity_score", sa.Float(), nullable=False),
        sa.Column("diversification_score", sa.Float(), nullable=False),
        sa.Column("exit_experience_score", sa.Float(), nullable=False),
        sa.Column("realized_performance_score", sa.Float(), nullable=False),
        sa.Column("data_quality_score", sa.Float(), nullable=False),
        sa.Column("realized_pnl_sol", sa.Float(), nullable=False),
        sa.Column("realized_roi", sa.Float(), nullable=False),
        sa.Column("unmatched_sell_ratio", sa.Float(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["wallet_id"],
            ["wallets.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("wallet_id"),
    )
    op.create_index(
        op.f("ix_wallet_score_snapshots_grade"),
        "wallet_score_snapshots",
        ["grade"],
        unique=False,
    )
    op.create_index(
        op.f("ix_wallet_score_snapshots_score"),
        "wallet_score_snapshots",
        ["score"],
        unique=False,
    )
def downgrade() -> None:
    op.drop_index(
        op.f("ix_wallet_score_snapshots_score"),
        table_name="wallet_score_snapshots",
    )
    op.drop_index(
        op.f("ix_wallet_score_snapshots_grade"),
        table_name="wallet_score_snapshots",
    )
    op.drop_table("wallet_score_snapshots")
