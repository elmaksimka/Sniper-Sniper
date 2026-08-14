"""add paper copy risk controls

Revision ID: d5b8f1c3a720
Revises: a4e7c9d2f160
Create Date: 2026-08-14

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "d5b8f1c3a720"
down_revision: str | Sequence[str] | None = "a4e7c9d2f160"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "paper_copy_positions",
        sa.Column("first_entry_price_usd", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "paper_copy_positions",
        sa.Column("buy_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "paper_copy_positions",
        sa.Column("maximum_roi_pct", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "paper_copy_positions",
        sa.Column("minimum_roi_pct", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "paper_copy_positions",
        sa.Column("strategy_version", sa.String(length=32), nullable=False, server_default="legacy"),
    )
    op.add_column(
        "paper_copy_orders",
        sa.Column("strategy_version", sa.String(length=32), nullable=False, server_default="legacy"),
    )
    op.create_table(
        "paper_copy_position_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "position_id",
            sa.Integer(),
            sa.ForeignKey("paper_copy_positions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("strategy_version", sa.String(length=32), nullable=False),
        sa.Column("executable_value_usd", sa.Float(), nullable=False),
        sa.Column("executable_price_usd", sa.Float(), nullable=False),
        sa.Column("roi_pct", sa.Float(), nullable=False),
        sa.Column("price_impact_pct", sa.Float(), nullable=False),
        sa.Column("route_fee_bps", sa.Integer(), nullable=False),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_paper_copy_position_snapshots_position_id",
        "paper_copy_position_snapshots",
        ["position_id"],
    )
    op.create_index(
        "ix_paper_copy_position_snapshots_strategy_version",
        "paper_copy_position_snapshots",
        ["strategy_version"],
    )
    op.create_index(
        "ix_paper_copy_position_snapshots_observed_at",
        "paper_copy_position_snapshots",
        ["observed_at"],
    )


def downgrade() -> None:
    op.drop_table("paper_copy_position_snapshots")
    op.drop_column("paper_copy_orders", "strategy_version")
    op.drop_column("paper_copy_positions", "strategy_version")
    op.drop_column("paper_copy_positions", "minimum_roi_pct")
    op.drop_column("paper_copy_positions", "maximum_roi_pct")
    op.drop_column("paper_copy_positions", "buy_count")
    op.drop_column("paper_copy_positions", "first_entry_price_usd")
