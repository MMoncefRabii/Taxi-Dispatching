import argparse
import asyncio
import getpass
import sys
from datetime import datetime, timezone
from pathlib import Path

from argon2 import PasswordHasher
from sqlalchemy import func, select, update

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import SessionLocal, engine
from app.models import PlatformAuditLog, PlatformSession, SuperAdmin


class PasswordInputError(Exception):
    pass


async def reset_super_admin(email: str, password: str) -> bool:
    normalized_email = email.strip().lower()
    password_hash = PasswordHasher().hash(password)
    now = datetime.now(timezone.utc)

    async with SessionLocal() as session:
        async with session.begin():
            result = await session.execute(
                select(SuperAdmin).where(
                    func.lower(SuperAdmin.email) == normalized_email
                )
            )
            super_admin = result.scalar_one_or_none()
            if super_admin is None:
                return False

            super_admin.password_hash = password_hash
            await session.execute(
                update(PlatformSession)
                .where(
                    PlatformSession.super_admin_id == super_admin.id,
                    PlatformSession.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
            session.add(
                PlatformAuditLog(
                    action="password_reset",
                    target_type="super_admin",
                    target_id=super_admin.id,
                    success=True,
                )
            )
    return True


async def reset_from_prompt(email: str) -> None:
    try:
        password = getpass.getpass("New super admin password: ")
        confirmation = getpass.getpass("Confirm new super admin password: ")
        if password != confirmation:
            raise PasswordInputError("Passwords do not match.")
        if len(password) < 12 or len(password) > 128:
            raise PasswordInputError(
                "Password must be between 12 and 128 characters."
            )

        if await reset_super_admin(email, password):
            print("Super admin password reset; existing sessions were revoked.")
        else:
            print("No super admin found for that email; no changes made.")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reset the password for an existing platform-owner super admin."
    )
    parser.add_argument("--email", required=True)
    args = parser.parse_args()

    email = args.email.strip().lower()
    if not email or len(email) > 255 or "@" not in email:
        parser.error("--email must be a valid email address.")

    try:
        asyncio.run(reset_from_prompt(email))
    except PasswordInputError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
