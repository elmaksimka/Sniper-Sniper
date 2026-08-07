"""make trade timestamps timezone aware

Revision ID: 7e4a1c93b8d2
Revises: 4d7c2a91e6b3
Create Date: 2026-08-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "7e4a1c93b8d2"
down_revision: str | Sequence[str] | None = "4d7c2a91e6b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "trades",
        "timestamp",
        existing_type=sa.DateTime(timezone=False),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        postgresql_using="\"timestamp\" AT TIME ZONE 'UTC'",
    )


def downgrade() -> None:
    op.alter_column(
        "trades",
        "timestamp",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(timezone=False),
        existing_nullable=False,
        postgresql_using="\"timestamp\" AT TIME ZONE 'UTC'",
    )
