import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select, update

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import SessionLocal, engine
from app.models import Admin, AdminSession, Center


class AdminDeactivationError(Exception):
    pass


async def deactivate_admin(email: str) -> bool:
    normalized_email = email.strip().lower()
    async with SessionLocal() as session:
        async with session.begin():
            result = await session.execute(
                select(Admin)
                .where(func.lower(Admin.email) == normalized_email)
                .with_for_update()
            )
            admin = result.scalar_one_or_none()
            if admin is None:
                raise AdminDeactivationError(f"No admin found for email {email}.")
            if not admin.active:
                return False

            await session.execute(
                select(Center.id)
                .where(Center.id == admin.center_id)
                .with_for_update()
            )
            active_admin_count = await session.scalar(
                select(func.count(Admin.id)).where(
                    Admin.center_id == admin.center_id,
                    Admin.active.is_(True),
                )
            )
            if active_admin_count <= 1:
                raise AdminDeactivationError(
                    "Cannot deactivate the last active admin of this center."
                )

            now = datetime.now(timezone.utc)
            admin.active = False
            admin.deactivated_at = now
            await session.execute(
                update(AdminSession)
                .where(
                    AdminSession.admin_id == admin.id,
                    AdminSession.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
    return True


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
