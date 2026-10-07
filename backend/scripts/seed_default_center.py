import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import SessionLocal, engine
from app.models import Center


async def seed_default_center() -> None:
    async with SessionLocal() as session:
        center = await session.scalar(select(Center).limit(1))
        if center is None:
            center = Center(
                name="Tunis Center",
                city="Tunis",
                timezone="Africa/Tunis",
            )
            session.add(center)
            await session.commit()
            print(f"Created Tunis Center ({center.id})")
        else:
            print(f"Center already exists; keeping {center.name} ({center.id})")


async def seed_and_dispose() -> None:
    try:
        await seed_default_center()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_and_dispose())