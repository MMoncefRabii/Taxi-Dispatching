"""Create one-time center admin invitations.

Revision ID: 0004_admin_invitations
Revises: 0003_platform_console
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0004_admin_invitations"
down_revision = "0003_platform_console"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "center_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("centers.id"),
            nullable=False,
        ),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by_super_admin_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("super_admins.id"),
            nullable=True,
        ),
        sa.CheckConstraint(
            "email = lower(email)",
            name="ck_admin_invitations_email_lowercase",
        ),
    )
    op.create_index(
        "ix_admin_invitations_center_id",
        "admin_invitations",
        ["center_id"],
    )
    op.create_index(
        "ix_admin_invitations_token_hash",
        "admin_invitations",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_admin_invitations_token_hash",
        table_name="admin_invitations",
    )
    op.drop_index(
        "ix_admin_invitations_center_id",
        table_name="admin_invitations",
    )
    op.drop_table("admin_invitations")
