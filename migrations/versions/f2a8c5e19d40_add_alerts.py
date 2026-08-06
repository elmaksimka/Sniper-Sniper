"""add alerts

Revision ID: f2a8c5e19d40
Revises: d9b6f41a2e73
Create Date: 2026-08-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "f2a8c5e19d40"
down_revision: str | Sequence[str] | None = "d9b6f41a2e73"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_address", sa.String(length=64), nullable=False),
        sa.Column("alert_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("message", sa.String(length=512), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key"),
    )
    for column in (
        "alert_type",
        "created_at",
        "entity_address",
        "entity_type",
        "severity",
    ):
        op.create_index(
            op.f(f"ix_alerts_{column}"),
            "alerts",
            [column],
            unique=False,
        )


def downgrade() -> None:
    for column in (
        "severity",
        "entity_type",
        "entity_address",
        "created_at",
        "alert_type",
    ):
        op.drop_index(op.f(f"ix_alerts_{column}"), table_name="alerts")
    op.drop_table("alerts")
