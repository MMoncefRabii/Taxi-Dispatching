import asyncio
import os
import sys
import uuid

from argon2 import PasswordHasher
from sqlalchemy import func, select

from app.db import SessionLocal, engine
from app.models import Admin, Center

DEFAULT_CENTER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


async def seed_admin(email: str, password: str) -> None:
    normalized_email = email.strip().lower()
    async with SessionLocal() as session:
        result = await session.execute(
            select(Admin).where(func.lower(Admin.email) == normalized_email)
        )
        if result.scalar_one_or_none() is not None:
            print("Admin already exists; no changes made.")
            return

        center = await session.get(Center, DEFAULT_CENTER_ID)
        if center is None:
            session.add(
                Center(
                    id=DEFAULT_CENTER_ID,
                    name="Tunis Center",
                    city="Tunis",
                    timezone="Africa/Tunis",
                )
            )
            await session.flush()

        session.add(
            Admin(
                center_id=DEFAULT_CENTER_ID,
                email=normalized_email,
                password_hash=PasswordHasher().hash(password),
                role="center_admin",
                active=True,
            )
        )
        await session.commit()
    print(f"Created admin {normalized_email} for the default center.")


async def seed_and_dispose(email: str, password: str) -> None:
    try:
        await seed_admin(email, password)
    finally:
        await engine.dispose()


def main() -> None:
    email = os.getenv("ADMIN_EMAIL", "")
    password = os.getenv("ADMIN_PASSWORD", "")
    if not email or len(email) > 255 or "@" not in email:
        print("ERROR: ADMIN_EMAIL must be a valid email address.", file=sys.stderr)
        raise SystemExit(1)
    if len(password) < 12 or len(password) > 128:
        print(
            "ERROR: ADMIN_PASSWORD must be between 12 and 128 characters.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    asyncio.run(seed_and_dispose(email, password))


if __name__ == "__main__":
    main()
