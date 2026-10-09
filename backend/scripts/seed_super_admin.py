import argparse
import asyncio
import getpass
import sys
from pathlib import Path

from argon2 import PasswordHasher
from sqlalchemy import func, select

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import SessionLocal, engine
from app.models import SuperAdmin


class PasswordInputError(Exception):
    pass


async def super_admin_exists(email: str) -> bool:
    normalized_email = email.strip().lower()
    async with SessionLocal() as session:
        result = await session.execute(
            select(SuperAdmin).where(
                func.lower(SuperAdmin.email) == normalized_email
            )
        )
        return result.scalar_one_or_none() is not None


async def any_super_admin_exists() -> bool:
    async with SessionLocal() as session:
        result = await session.scalar(select(SuperAdmin.id).limit(1))
        return result is not None


async def seed_super_admin(email: str, password: str) -> bool:
    normalized_email = email.strip().lower()
    async with SessionLocal() as session:
        async with session.begin():
            result = await session.execute(
                select(SuperAdmin).where(
                    func.lower(SuperAdmin.email) == normalized_email
                )
            )
            if result.scalar_one_or_none() is not None:
                return False
            if await session.scalar(select(SuperAdmin.id).limit(1)) is not None:
                return False

            session.add(
                SuperAdmin(
                    email=normalized_email,
                    password_hash=PasswordHasher().hash(password),
                    active=True,
                )
            )
    return True


async def seed_from_prompt(email: str) -> None:
    try:
        if await super_admin_exists(email):
            print("Super admin already exists; no changes made.")
            return
        if await any_super_admin_exists():
            print(
                "A super admin already exists; this command is only for the "
                "first super admin."
            )
            return

        password = getpass.getpass("Super admin password: ")
        confirmation = getpass.getpass("Confirm super admin password: ")
        if password != confirmation:
            raise PasswordInputError("Passwords do not match.")
        if len(password) < 12 or len(password) > 128:
            raise PasswordInputError(
                "Password must be between 12 and 128 characters."
            )

        if await seed_super_admin(email, password):
            print(f"Created super admin {email}.")
        else:
            print("Super admin already exists; no changes made.")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create the first platform-owner super admin."
    )
    parser.add_argument("--email", required=True)
    args = parser.parse_args()

    email = args.email.strip().lower()
    if not email or len(email) > 255 or "@" not in email:
        parser.error("--email must be a valid email address.")

    try:
        asyncio.run(seed_from_prompt(email))
    except PasswordInputError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
