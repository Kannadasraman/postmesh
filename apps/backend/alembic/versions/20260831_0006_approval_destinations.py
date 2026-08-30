"""add separate approval destinations

Revision ID: 20260831_0006
Revises: 20260831_0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0006"
down_revision: str | Sequence[str] | None = "20260831_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("content_drafts", sa.Column("approval_email", sa.String(length=255), nullable=True))
    op.add_column("content_drafts", sa.Column("approval_whatsapp", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("content_drafts", "approval_whatsapp")
    op.drop_column("content_drafts", "approval_email")