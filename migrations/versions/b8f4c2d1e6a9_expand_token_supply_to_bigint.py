"""expand token supply to bigint

Revision ID: b8f4c2d1e6a9
Revises: 9b3d6f18a2c7
Create Date: 2026-08-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "b8f4c2d1e6a9"
down_revision: str | Sequence[str] | None = "9b3d6f18a2c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "tokens",
        "supply",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "tokens",
        "supply",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=True,
    )
