import argparse
import asyncio
import getpass
import sys
import uuid
from pathlib import Path

from argon2 import PasswordHasher
from sqlalchemy import func, select

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import SessionLocal, engine
from app.models import Admin, Center


class CenterSelectionError(Exception):
    pass


class PasswordInputError(Exception):
    pass


async def admin_exists(email: str) -> bool:
    normalized_email = email.strip().lower()
    async with SessionLocal() as session:
        result = await session.execute(
            select(Admin).where(func.lower(Admin.email) == normalized_email)
        )
        return result.scalar_one_or_none() is not None


async def seed_admin(
    email: str,
    password: str,
    center_id: uuid.UUID | None = None,
) -> None:
    normalized_email = email.strip().lower()
    async with SessionLocal() as session:
        result = await session.execute(
            select(Admin).where(func.lower(Admin.email) == normalized_email)
        )
        if result.scalar_one_or_none() is not None:
            print("Admin already exists; no changes made.")
            return

        if center_id is None:
            centers = list(
                (
                    await session.scalars(
                        select(Center).order_by(Center.id)
                    )
                ).all()
            )
            if len(centers) != 1:
                raise CenterSelectionError(
                    f"Cannot choose a center: found {len(centers)}; "
                    "specify --center-id."
                )
            center = centers[0]
        else:
            center = await session.get(Center, center_id)
        if center is None:
            raise CenterSelectionError(f"Center {center_id} does not exist.")

        session.add(
            Admin(
                center_id=center.id,
                email=normalized_email,
                password_hash=PasswordHasher().hash(password),
                role="center_admin",
                active=True,
            )
        )
        await session.commit()
    print(f"Created admin {normalized_email} for center {center.id}.")


async def seed_from_prompt(email: str, center_id: uuid.UUID | None) -> None:
    try:
        if await admin_exists(email):
            print("Admin already exists; no changes made.")
            return

        password = getpass.getpass("Admin password: ")
        confirmation = getpass.getpass("Confirm admin password: ")
        if password != confirmation:
            raise PasswordInputError("Passwords do not match.")
        if len(password) < 12 or len(password) > 128:
            raise PasswordInputError(
                "Password must be between 12 and 128 characters."
            )

        await seed_admin(email, password, center_id)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the first center admin.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--center-id", type=uuid.UUID)
    args = parser.parse_args()

    email = args.email.strip().lower()
    if not email or len(email) > 255 or "@" not in email:
        parser.error("--email must be a valid email address.")

    try:
        asyncio.run(seed_from_prompt(email, args.center_id))
    except (CenterSelectionError, PasswordInputError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
