"""expand token supply to uint64-compatible numeric

Revision ID: e42b61c7d9a3
Revises: c91e7a42d5f0
Create Date: 2026-08-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "e42b61c7d9a3"
down_revision: str | Sequence[str] | None = "c91e7a42d5f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "tokens",
        "supply",
        existing_type=sa.BigInteger(),
        type_=sa.Numeric(precision=20, scale=0),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "tokens",
        "supply",
        existing_type=sa.Numeric(precision=20, scale=0),
        type_=sa.BigInteger(),
        existing_nullable=True,
    )
