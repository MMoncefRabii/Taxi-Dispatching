"""Deduplicate driver locations by driver and recorded timestamp."""

from alembic import op
import sqlalchemy as sa


revision = "0005_location_dedup"
down_revision = "0004_admin_invitations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM driver_locations
                    GROUP BY driver_id, recorded_at
                    HAVING COUNT(*) > 1
                ) THEN
                    RAISE EXCEPTION
                        'Cannot add driver location uniqueness: duplicate (driver_id, recorded_at) rows exist in driver_locations';
                END IF;
            END
            $$;
            """
        )
    )
    op.create_unique_constraint(
        "uq_driver_locations_driver_recorded_at",
        "driver_locations",
        ["driver_id", "recorded_at"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_driver_locations_driver_recorded_at",
        "driver_locations",
        type_="unique",
    )
