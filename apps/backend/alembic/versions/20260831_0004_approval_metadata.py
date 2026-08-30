"""add approval metadata to content drafts

Revision ID: 20260831_0004
Revises: 20260829_0003
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260831_0004"
down_revision: str | Sequence[str] | None = "20260829_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "content_drafts",
        sa.Column("approval_channel", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "content_drafts",
        sa.Column("approval_recipient", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "content_drafts",
        sa.Column("review_notes", sa.Text(), nullable=True),
    )
    op.add_column(
        "content_drafts",
        sa.Column(
            "request_next_post",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("content_drafts", "request_next_post")
    op.drop_column("content_drafts", "review_notes")
    op.drop_column("content_drafts", "approval_recipient")
    op.drop_column("content_drafts", "approval_channel")