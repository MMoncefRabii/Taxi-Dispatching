import argparse
import asyncio
import hashlib
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, insert, select

from app.db import SessionLocal, engine
from app.models import Center, Driver, DriverLocation

DEFAULT_CENTER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
SQLITE_PATH = Path(__file__).resolve().parents[1] / "tracking.db"


async def migrate(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"SQLite database not found: {path}")
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        sqlite_drivers = connection.execute(
            "SELECT id, name, phone, token, online FROM drivers ORDER BY id"
        ).fetchall()
        locations = connection.execute(
            "SELECT driver_id, lat, lng, speed, heading, accuracy, recorded_at "
            "FROM locations ORDER BY id"
        )

        async with SessionLocal() as session:
            center = await session.get(Center, DEFAULT_CENTER_ID)
            if center is None:
                raise RuntimeError(
                    "Default center is missing; run seed_default_center.py first"
                )

            existing_drivers = await session.scalar(
                select(func.count()).select_from(Driver)
            )
            existing_locations = await session.scalar(
                select(func.count()).select_from(DriverLocation)
            )
            if existing_drivers or existing_locations:
                print(
                    "PostgreSQL already contains driver/location data; skipping import "
                    f"(drivers={existing_drivers}, locations={existing_locations})."
                )
                return

            driver_ids: dict[int, uuid.UUID] = {}
            for old_driver in sqlite_drivers:
                token_hash = hashlib.sha256(
                    str(old_driver["token"]).encode("utf-8")
                ).hexdigest()
                driver = Driver(
                    center_id=DEFAULT_CENTER_ID,
                    name=old_driver["name"] or "Unnamed Driver",
                    phone=old_driver["phone"] or "00000",
                    token_hash=token_hash,
                    online=bool(old_driver["online"]),
                )
                session.add(driver)
                await session.flush()
                driver_ids[old_driver["id"]] = driver.id

            migrated_locations = 0
            while batch := locations.fetchmany(1000):
                records = []
                for old_location in batch:
                    driver_id = driver_ids.get(old_location["driver_id"])
                    if driver_id is None:
                        print(
                            "Warning: skipping location for unknown driver "
                            f"{old_location['driver_id']}"
                        )
                        continue
                    recorded_at = old_location["recorded_at"]
                    if recorded_at is None:
                        recorded_at = datetime.now(tz=timezone.utc).timestamp()
                    records.append(
                        {
                            "id": uuid.uuid4(),
                            "center_id": DEFAULT_CENTER_ID,
                            "driver_id": driver_id,
                            "lat": old_location["lat"],
                            "lng": old_location["lng"],
                            "speed": old_location["speed"],
                            "heading": old_location["heading"],
                            "accuracy": old_location["accuracy"],
                            "recorded_at": datetime.fromtimestamp(
                                recorded_at, tz=timezone.utc
                            ),
                        }
                    )
                if records:
                    await session.execute(insert(DriverLocation), records)
                    migrated_locations += len(records)

            await session.commit()
            print(
                f"Migrated {len(driver_ids)} drivers and {migrated_locations} locations "
                f"from {path}."
            )
    finally:
        connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import tracking.db data into PostgreSQL once.")
    parser.add_argument("--sqlite-path", type=Path, default=SQLITE_PATH)
    args = parser.parse_args()
    try:
        asyncio.run(migrate(args.sqlite_path))
    finally:
        asyncio.run(engine.dispose())