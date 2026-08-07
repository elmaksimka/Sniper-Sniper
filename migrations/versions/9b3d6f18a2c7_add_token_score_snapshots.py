"""add token score snapshots

Revision ID: 9b3d6f18a2c7
Revises: 7e4a1c93b8d2
Create Date: 2026-08-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "9b3d6f18a2c7"
down_revision: str | Sequence[str] | None = "7e4a1c93b8d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "token_score_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("grade", sa.String(length=2), nullable=False),
        sa.Column("methodology_version", sa.String(length=32), nullable=False),
        sa.Column("activity_score", sa.Float(), nullable=False),
        sa.Column("participation_score", sa.Float(), nullable=False),
        sa.Column("holder_distribution_score", sa.Float(), nullable=False),
        sa.Column("flow_balance_score", sa.Float(), nullable=False),
        sa.Column("creator_history_score", sa.Float(), nullable=False),
        sa.Column("data_quality_score", sa.Float(), nullable=False),
        sa.Column("observed_holder_count", sa.Integer(), nullable=False),
        sa.Column("top_holder_share", sa.Float(), nullable=False),
        sa.Column("incomplete_holder_ratio", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["token_id"], ["tokens.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_id"),
    )
    op.create_index(
        op.f("ix_token_score_snapshots_grade"),
        "token_score_snapshots",
        ["grade"],
        unique=False,
    )
    op.create_index(
        op.f("ix_token_score_snapshots_score"),
        "token_score_snapshots",
        ["score"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_token_score_snapshots_score"),
        table_name="token_score_snapshots",
    )
    op.drop_index(
        op.f("ix_token_score_snapshots_grade"),
        table_name="token_score_snapshots",
    )
    op.drop_table("token_score_snapshots")
