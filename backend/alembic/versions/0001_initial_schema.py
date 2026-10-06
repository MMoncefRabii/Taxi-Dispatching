"""Initial multi-tenant schema.

Revision ID: 0001
Revises:
Create Date: 2026-10-03
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "centers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("timezone", sa.String(50), nullable=False, server_default="Africa/Tunis"),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "super_admins",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "admins",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("center_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("centers.id"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="center_admin"),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("center_id", "email", name="uq_admin_center_email"),
    )
    op.create_index("ix_admins_center_id", "admins", ["center_id"])
    op.create_index("ix_admins_email", "admins", ["email"])
    op.create_table(
        "drivers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("center_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("centers.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("token_hash", sa.String(255), nullable=False, unique=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("online", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_drivers_center_id", "drivers", ["center_id"])
    op.create_table(
        "vehicles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("driver_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("drivers.id"), nullable=False, unique=True),
        sa.Column("taxi_number", sa.String(50), nullable=False, unique=True),
        sa.Column("plate_number", sa.String(50), nullable=False),
        sa.Column("type", sa.String(50), nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_vehicles_driver_id", "vehicles", ["driver_id"])
    op.create_index("ix_vehicles_taxi_number", "vehicles", ["taxi_number"])
    op.create_table(
        "driver_locations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("center_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("centers.id"), nullable=False),
        sa.Column("driver_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("drivers.id"), nullable=False),
        sa.Column("lat", sa.Float, nullable=False),
        sa.Column("lng", sa.Float, nullable=False),
        sa.Column("speed", sa.Float, nullable=True),
        sa.Column("heading", sa.Float, nullable=True),
        sa.Column("accuracy", sa.Float, nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_driver_locations_center_id", "driver_locations", ["center_id"])
    op.create_index("ix_driver_locations_driver_id", "driver_locations", ["driver_id"])
    op.create_index("ix_driver_locations_recorded_at", "driver_locations", ["recorded_at"])
    op.create_index("ix_driver_locations_driver_recorded", "driver_locations", ["driver_id", "recorded_at"])
    op.create_table(
        "driver_status_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("driver_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("drivers.id"), nullable=False),
        sa.Column("online", sa.Boolean, nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_driver_status_logs_driver_id", "driver_status_logs", ["driver_id"])
    op.create_index("ix_driver_status_logs_changed_at", "driver_status_logs", ["changed_at"])
    op.create_table(
        "zones",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("center_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("centers.id"), nullable=False),
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("boundary", sa.Text, nullable=True),
        sa.UniqueConstraint("center_id", "code", name="uq_zone_center_code"),
    )
    op.create_index("ix_zones_center_id", "zones", ["center_id"])
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("center_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("centers.id"), nullable=False),
        sa.Column("actor_admin_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("admins.id"), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("before_state", postgresql.JSONB, nullable=True),
        sa.Column("after_state", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_audit_logs_center_id", "audit_logs", ["center_id"])
    op.create_index("ix_audit_logs_actor_admin_id", "audit_logs", ["actor_admin_id"])
    op.create_index("ix_audit_logs_entity_type", "audit_logs", ["entity_type"])
    op.create_index("ix_audit_logs_entity_id", "audit_logs", ["entity_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("zones")
    op.drop_table("driver_status_logs")
    op.drop_table("driver_locations")
    op.drop_table("vehicles")
    op.drop_table("drivers")
    op.drop_table("admins")
    op.drop_table("super_admins")
    op.drop_table("centers")