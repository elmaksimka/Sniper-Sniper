"""Remove redundant paper-copy portfolio unique constraint.

Revision ID: 7c9f1a4d2e63
Revises: 6b8e2c4f9a10
"""

from collections.abc import Sequence

from alembic import op


revision: str = "7c9f1a4d2e63"
down_revision: str | Sequence[str] | None = "6b8e2c4f9a10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The unique index ix_paper_copy_portfolios_source_wallet already enforces
    # the same invariant; keeping both makes Alembic metadata drift.
    op.drop_constraint(
        "paper_copy_portfolios_source_wallet_key",
        "paper_copy_portfolios",
        type_="unique",
    )


def downgrade() -> None:
    op.create_unique_constraint(
        "paper_copy_portfolios_source_wallet_key",
        "paper_copy_portfolios",
        ["source_wallet"],
    )
