"""Require vehicle and driver to belong to the same center.

Revision ID: 0007_vehicle_driver_center_fk
Revises: 0006_vehicle_tenant_uniqueness
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_vehicle_driver_center_fk"
down_revision = "0006_vehicle_tenant_uniqueness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    mismatched_count = int(
        op.get_bind()
        .execute(
            sa.text(
                "SELECT count(*) "
                "FROM vehicles AS vehicle "
                "JOIN drivers AS driver ON driver.id = vehicle.driver_id "
                "WHERE vehicle.center_id <> driver.center_id"
            )
        )
        .scalar_one()
    )
    if mismatched_count:
        raise RuntimeError(
            "Cannot enforce vehicle/driver center matching: "
            f"{mismatched_count} vehicle rows have a center_id different "
            "from their driver's center_id."
        )

    op.create_unique_constraint(
        "uq_drivers_id_center_id",
        "drivers",
        ["id", "center_id"],
    )
    op.drop_constraint(
        "vehicles_driver_id_fkey",
        "vehicles",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_vehicles_driver_center_drivers",
        "vehicles",
        "drivers",
        ["driver_id", "center_id"],
        ["id", "center_id"],
        match="SIMPLE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_vehicles_driver_center_drivers",
        "vehicles",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "vehicles_driver_id_fkey",
        "vehicles",
        "drivers",
        ["driver_id"],
        ["id"],
    )
    op.drop_constraint(
        "uq_drivers_id_center_id",
        "drivers",
        type_="unique",
    )
