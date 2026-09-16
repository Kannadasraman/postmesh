"""add users and tenant ownership

Revision ID: 20260916_0011
Revises: 20260916_0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260916_0011"
down_revision: str | Sequence[str] | None = "20260916_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=False)
    bind = op.get_bind()
    bootstrap_id = "00000000-0000-0000-0000-000000000001"
    bind.execute(sa.text("INSERT INTO users (id, email, password_hash, display_name) VALUES (:id, :email, :password_hash, :display_name)"), {"id": bootstrap_id, "email": "owner@postmesh.local", "password_hash": "!bootstrap-login-disabled", "display_name": "PostMesh Owner"})
    for table in ("topics", "research_items", "content_drafts", "publishing_jobs", "social_connections"):
        op.add_column(table, sa.Column("user_id", sa.UUID(), nullable=True))
        op.create_index(f"ix_{table}_user_id", table, ["user_id"], unique=False)
        op.create_foreign_key(f"fk_{table}_user_id_users", table, "users", ["user_id"], ["id"], ondelete="CASCADE")
        bind.execute(sa.text(f"UPDATE {table} SET user_id = :user_id WHERE user_id IS NULL"), {"user_id": bootstrap_id})


def downgrade() -> None:
    for table in ("social_connections", "publishing_jobs", "content_drafts", "research_items", "topics"):
        op.drop_constraint(f"fk_{table}_user_id_users", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_user_id", table)
        op.drop_column(table, "user_id")
    op.drop_index("ix_users_email", "users")
    op.drop_table("users")