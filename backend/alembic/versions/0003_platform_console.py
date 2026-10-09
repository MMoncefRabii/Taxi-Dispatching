"""Add platform sessions and audit log.

Revision ID: 0003_platform_console
Revises: 0002_admin_sessions
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0003_platform_console"
down_revision = "0002_admin_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    duplicate_email = bind.execute(
        sa.text(
            "SELECT 1 FROM super_admins "
            "GROUP BY lower(email) HAVING count(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicate_email is not None:
        raise RuntimeError(
            "Cannot create the case-insensitive super_admin email index: "
            "case-insensitive duplicates exist."
        )

    op.create_index(
        "uq_super_admin_email_lower",
        "super_admins",
        [sa.text("lower(email)")],
        unique=True,
    )
    op.add_column(
        "super_admins",
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    op.create_table(
        "platform_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "super_admin_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("super_admins.id"),
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
        "ix_platform_sessions_token_hash",
        "platform_sessions",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_platform_sessions_super_admin_id",
        "platform_sessions",
        ["super_admin_id"],
    )

    op.create_table(
        "platform_audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "super_admin_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("super_admins.id"),
            nullable=True,
        ),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target_type", sa.String(100), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ip", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("email_hash", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_platform_audit_log_created_at",
        "platform_audit_log",
        ["created_at"],
    )
    op.create_index(
        "ix_platform_audit_log_super_admin_id",
        "platform_audit_log",
        ["super_admin_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_platform_audit_log_super_admin_id",
        table_name="platform_audit_log",
    )
    op.drop_index(
        "ix_platform_audit_log_created_at",
        table_name="platform_audit_log",
    )
    op.drop_table("platform_audit_log")
    op.drop_index(
        "ix_platform_sessions_super_admin_id",
        table_name="platform_sessions",
    )
    op.drop_index(
        "ix_platform_sessions_token_hash",
        table_name="platform_sessions",
    )
    op.drop_table("platform_sessions")
    op.drop_column("super_admins", "active")
    op.drop_index(
        "uq_super_admin_email_lower",
        table_name="super_admins",
    )
