"""add funding transfers

Revision ID: 4d7c2a91e6b3
Revises: c4d2b8e71a63
Create Date: 2026-08-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "4d7c2a91e6b3"
down_revision: str | Sequence[str] | None = "c4d2b8e71a63"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "funding_transfers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_wallet_id", sa.Integer(), nullable=False),
        sa.Column("destination_wallet_id", sa.Integer(), nullable=False),
        sa.Column("amount_sol", sa.Float(), nullable=False),
        sa.Column("signature", sa.String(length=128), nullable=False),
        sa.Column("instruction_index", sa.String(length=64), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["destination_wallet_id"], ["wallets.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_wallet_id"], ["wallets.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "signature",
            "instruction_index",
            name="uq_funding_transfers_signature_instruction",
        ),
    )
    for column in (
        "source_wallet_id",
        "destination_wallet_id",
        "signature",
        "timestamp",
    ):
        op.create_index(
            op.f(f"ix_funding_transfers_{column}"),
            "funding_transfers",
            [column],
            unique=False,
        )


def downgrade() -> None:
    for column in (
        "timestamp",
        "signature",
        "destination_wallet_id",
        "source_wallet_id",
    ):
        op.drop_index(
            op.f(f"ix_funding_transfers_{column}"),
            table_name="funding_transfers",
        )
    op.drop_table("funding_transfers")
