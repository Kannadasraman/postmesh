"""add posting platform to topics

Revision ID: 20260916_0010
Revises: 20260916_0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260916_0010"
down_revision: str | Sequence[str] | None = "20260916_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "topics",
        sa.Column(
            "posting_platform",
            sa.String(length=50),
            nullable=False,
            server_default="linkedin",
        ),
    )


def downgrade() -> None:
    op.drop_column("topics", "posting_platform")