"""add daily approval batches

Revision ID: 20260913_0008
Revises: 20260831_0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260913_0008"
down_revision: str | Sequence[str] | None = "20260831_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "approval_batches",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("recipient", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="pending", nullable=False),
        sa.Column("selected_draft_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("approval_batches")
