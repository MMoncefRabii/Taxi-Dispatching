"""Add globally unique admin emails and admin sessions.

Revision ID: 0002_admin_sessions
Revises: 0001
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_admin_sessions"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE admins SET email = lower(email)")
    op.drop_constraint("uq_admin_center_email", "admins", type_="unique")
    op.drop_index("ix_admins_email", table_name="admins")
    op.create_check_constraint(
        "ck_admin_email_lowercase",
        "admins",
        "email = lower(email)",
    )
    op.create_unique_constraint("uq_admin_email", "admins", ["email"])

    op.create_table(
        "admin_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "admin_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("admins.id"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_admin_sessions_token_hash",
        "admin_sessions",
        ["token_hash"],
        unique=True,
    )
    op.create_index("ix_admin_sessions_admin_id", "admin_sessions", ["admin_id"])


def downgrade() -> None:
    op.drop_index("ix_admin_sessions_admin_id", table_name="admin_sessions")
    op.drop_index("ix_admin_sessions_token_hash", table_name="admin_sessions")
    op.drop_table("admin_sessions")

    op.drop_constraint("uq_admin_email", "admins", type_="unique")
    op.drop_constraint("ck_admin_email_lowercase", "admins", type_="check")
    op.create_unique_constraint(
        "uq_admin_center_email",
        "admins",
        ["center_id", "email"],
    )
    op.create_index("ix_admins_email", "admins", ["email"])
