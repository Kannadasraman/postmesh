"""add publishing jobs

Revision ID: 20260829_0003
Revises: 20260828_0002
Create Date: 2026-08-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260829_0003"
down_revision: Union[str, Sequence[str], None] = "20260828_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "publishing_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "draft_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "platform",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=50),
            server_default="scheduled",
            nullable=False,
        ),
        sa.Column(
            "content_snapshot",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "scheduled_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "max_attempts",
            sa.Integer(),
            server_default="3",
            nullable=False,
        ),
        sa.Column(
            "queued_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "failed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "cancelled_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "external_post_id",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "external_post_url",
            sa.String(length=1000),
            nullable=True,
        ),
        sa.Column(
            "last_error",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ("
            "'scheduled', "
            "'queued', "
            "'publishing', "
            "'published', "
            "'failed', "
            "'cancelled'"
            ")",
            name="ck_publishing_jobs_status",
        ),
        sa.ForeignKeyConstraint(
            ["draft_id"],
            ["content_drafts.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_publishing_jobs_draft_id"),
        "publishing_jobs",
        ["draft_id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_publishing_jobs_status"),
        "publishing_jobs",
        ["status"],
        unique=False,
    )

    op.create_index(
        op.f("ix_publishing_jobs_scheduled_at"),
        "publishing_jobs",
        ["scheduled_at"],
        unique=False,
    )

    op.create_index(
        "ix_publishing_jobs_status_scheduled_at",
        "publishing_jobs",
        ["status", "scheduled_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_publishing_jobs_status_scheduled_at",
        table_name="publishing_jobs",
    )

    op.drop_index(
        op.f("ix_publishing_jobs_scheduled_at"),
        table_name="publishing_jobs",
    )

    op.drop_index(
        op.f("ix_publishing_jobs_status"),
        table_name="publishing_jobs",
    )

    op.drop_index(
        op.f("ix_publishing_jobs_draft_id"),
        table_name="publishing_jobs",
    )

    op.drop_table("publishing_jobs")
