"""Scope vehicle numbers and plates to their center.

Revision ID: 0006_vehicle_tenant_uniqueness
Revises: 0005_location_dedup
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "0006_vehicle_tenant_uniqueness"
down_revision = "0005_location_dedup"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _duplicate_group_count(group_columns: tuple[str, ...]) -> int:
    statements = {
        ("center_id", "taxi_number"): sa.text(
            "SELECT count(*) FROM ("
            "SELECT 1 FROM vehicles GROUP BY center_id, taxi_number "
            "HAVING count(*) > 1"
            ") AS duplicate_groups"
        ),
        ("center_id", "plate_number"): sa.text(
            "SELECT count(*) FROM ("
            "SELECT 1 FROM vehicles GROUP BY center_id, plate_number "
            "HAVING count(*) > 1"
            ") AS duplicate_groups"
        ),
        ("taxi_number",): sa.text(
            "SELECT count(*) FROM ("
            "SELECT 1 FROM vehicles GROUP BY taxi_number "
            "HAVING count(*) > 1"
            ") AS duplicate_groups"
        ),
    }
    result = op.get_bind().execute(statements[group_columns])
    return int(result.scalar_one())


def _center_foreign_keys() -> list[dict[str, object]]:
    return [
        foreign_key
        for foreign_key in _inspector().get_foreign_keys("vehicles")
        if foreign_key.get("constrained_columns") == ["center_id"]
        and foreign_key.get("referred_table") == "centers"
    ]


def upgrade() -> None:
    columns = {column["name"]: column for column in _inspector().get_columns("vehicles")}
    if "center_id" not in columns:
        op.add_column(
            "vehicles",
            sa.Column("center_id", UUID(as_uuid=True), nullable=True),
        )

    op.execute(
        sa.text(
            "UPDATE vehicles AS vehicle "
            "SET center_id = driver.center_id "
            "FROM drivers AS driver "
            "WHERE vehicle.driver_id = driver.id "
            "AND vehicle.center_id IS NULL"
        )
    )
    unassigned_count = int(
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM vehicles WHERE center_id IS NULL"))
        .scalar_one()
    )
    if unassigned_count:
        raise RuntimeError(
            "Cannot make vehicles.center_id NOT NULL: "
            f"{unassigned_count} vehicle rows have no owning driver center."
        )

    if not _center_foreign_keys():
        op.create_foreign_key(
            "fk_vehicles_center_id_centers",
            "vehicles",
            "centers",
            ["center_id"],
            ["id"],
        )

    center_indexes = [
        index
        for index in _inspector().get_indexes("vehicles")
        if index.get("column_names") == ["center_id"]
    ]
    if not center_indexes:
        op.create_index("ix_vehicles_center_id", "vehicles", ["center_id"])

    if columns.get("center_id", {}).get("nullable", True):
        op.alter_column("vehicles", "center_id", nullable=False)

    for constraint in _inspector().get_unique_constraints("vehicles"):
        if constraint.get("column_names") == ["taxi_number"]:
            op.drop_constraint(
                constraint["name"],
                "vehicles",
                type_="unique",
            )

    taxi_duplicates = _duplicate_group_count(("center_id", "taxi_number"))
    plate_duplicates = _duplicate_group_count(("center_id", "plate_number"))
    if taxi_duplicates or plate_duplicates:
        raise RuntimeError(
            "Cannot add per-center vehicle uniqueness: "
            f"{taxi_duplicates} duplicate center/taxi-number groups and "
            f"{plate_duplicates} duplicate center/plate-number groups exist."
        )

    op.create_unique_constraint(
        "uq_vehicles_center_taxi_number",
        "vehicles",
        ["center_id", "taxi_number"],
    )
    op.create_unique_constraint(
        "uq_vehicles_center_plate_number",
        "vehicles",
        ["center_id", "plate_number"],
    )


def downgrade() -> None:
    global_taxi_duplicates = _duplicate_group_count(("taxi_number",))
    if global_taxi_duplicates:
        raise RuntimeError(
            "Cannot restore global taxi-number uniqueness: "
            f"{global_taxi_duplicates} duplicate taxi-number groups exist."
        )

    op.drop_constraint(
        "uq_vehicles_center_plate_number",
        "vehicles",
        type_="unique",
    )
    op.drop_constraint(
        "uq_vehicles_center_taxi_number",
        "vehicles",
        type_="unique",
    )
    op.create_unique_constraint(
        "vehicles_taxi_number_key",
        "vehicles",
        ["taxi_number"],
    )
    for foreign_key in _center_foreign_keys():
        name = foreign_key.get("name")
        if not isinstance(name, str):
            raise RuntimeError("Cannot downgrade vehicles.center_id: its foreign key has no name.")
        op.drop_constraint(name, "vehicles", type_="foreignkey")
    if any(
        index.get("name") == "ix_vehicles_center_id"
        for index in _inspector().get_indexes("vehicles")
    ):
        op.drop_index("ix_vehicles_center_id", table_name="vehicles")
    op.drop_column("vehicles", "center_id")
