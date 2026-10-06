import asyncio
import uuid

from sqlalchemy import select

from app.db import SessionLocal, engine
from app.models import Center

DEFAULT_CENTER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


async def seed_default_center() -> None:
    async with SessionLocal() as session:
        center = await session.scalar(select(Center).limit(1))
        if center is None:
            session.add(
                Center(
                    id=DEFAULT_CENTER_ID,
                    name="Tunis Center",
                    city="Tunis",
                    timezone="Africa/Tunis",
                )
            )
            await session.commit()
            print(f"Created Tunis Center ({DEFAULT_CENTER_ID})")
        else:
            print(f"Center already exists; keeping {center.name} ({center.id})")


if __name__ == "__main__":
    try:
        asyncio.run(seed_default_center())
    finally:
        asyncio.run(engine.dispose())