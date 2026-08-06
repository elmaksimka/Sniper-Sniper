"""add service heartbeats

Revision ID: c4d2b8e71a63
Revises: a71c9d2e4f60
Create Date: 2026-08-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "c4d2b8e71a63"
down_revision: str | Sequence[str] | None = "a71c9d2e4f60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "service_heartbeats",
        sa.Column("service_name", sa.String(length=64), nullable=False),
        sa.Column("instance_id", sa.String(length=128), nullable=False),
        sa.Column(
            "last_heartbeat_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("service_name"),
    )
    op.create_index(
        op.f("ix_service_heartbeats_last_heartbeat_at"),
        "service_heartbeats",
        ["last_heartbeat_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_service_heartbeats_last_heartbeat_at"),
        table_name="service_heartbeats",
    )
    op.drop_table("service_heartbeats")
