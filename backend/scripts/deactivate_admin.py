import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import func, select

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import SessionLocal, engine
from app.admin_management import (
    AdminDeactivationError,
    AdminNotFoundError,
    deactivate_admin_in_transaction,
)
from app.models import Admin


async def deactivate_admin(email: str) -> bool:
    normalized_email = email.strip().lower()
    async with SessionLocal() as session:
        async with session.begin():
            admin_id = await session.scalar(
                select(Admin.id).where(func.lower(Admin.email) == normalized_email)
            )
            if admin_id is None:
                raise AdminNotFoundError(f"No admin found for email {email}.")
            return await deactivate_admin_in_transaction(session, admin_id)


async def deactivate_and_dispose(email: str) -> bool:
    try:
        return await deactivate_admin(email)
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Deactivate a center admin.")
    parser.add_argument("--email", required=True)
    args = parser.parse_args()

    email = args.email.strip().lower()
    if not email or len(email) > 255 or "@" not in email:
        parser.error("--email must be a valid email address.")

    try:
        changed = asyncio.run(deactivate_and_dispose(email))
    except AdminDeactivationError as error:
        print(str(error), file=sys.stderr)
        return 1

    if changed:
        print(f"Deactivated admin {email} and revoked its active sessions.")
    else:
        print("Admin is already inactive; no changes made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
