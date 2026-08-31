"""add draft media URL

Revision ID: 20260831_0007
Revises: 20260831_0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0007"
down_revision: str | Sequence[str] | None = "20260831_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("content_drafts", sa.Column("media_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("content_drafts", "media_url")