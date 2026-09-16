"""add approval email to topics

Revision ID: 20260916_0009
Revises: 20260913_0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260916_0009"
down_revision: str | Sequence[str] | None = "20260913_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "topics",
        sa.Column("approval_email", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("topics", "approval_email")