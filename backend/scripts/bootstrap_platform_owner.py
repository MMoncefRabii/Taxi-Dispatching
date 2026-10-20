import argparse
import asyncio
import getpass
import os
import sys
from pathlib import Path

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import func, select, update
from sqlalchemy.exc import ArgumentError
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import PlatformAuditLog, PlatformSession, SuperAdmin
from app.passwords import PasswordValidationError, hash_admin_password


class BootstrapError(Exception):
    pass


PASSWORD_ENV_VAR = "PLATFORM_OWNER_BOOTSTRAP_PASSWORD"
engine: AsyncEngine | None = None
SessionLocal: async_sessionmaker[AsyncSession] | None = None


def _session_factory() -> async_sessionmaker[AsyncSession]:
    global engine, SessionLocal
    if SessionLocal is None:
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise BootstrapError("DATABASE_URL must be set.")

        try:
            url = make_url(database_url)
        except ArgumentError as error:
            raise BootstrapError("DATABASE_URL is invalid.") from error
        if url.drivername in {"postgres", "postgresql"}:
            url = url.set(drivername="postgresql+asyncpg")
        elif url.drivername != "postgresql+asyncpg":
            raise BootstrapError("DATABASE_URL must use PostgreSQL.")

        engine = create_async_engine(
            url,
            pool_pre_ping=True,
            hide_parameters=True,
        )
        SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    return SessionLocal


async def _dispose_engine() -> None:
    global engine, SessionLocal
    if engine is not None:
        await engine.dispose()
        engine = None
        SessionLocal = None


def _normalize_email(email: str) -> str:
    candidate = email.strip()
    if not candidate or len(candidate) > 255:
        raise BootstrapError("Enter a valid email address.")
    try:
        normalized = validate_email(
            candidate,
            check_deliverability=False,
        ).normalized.lower()
    except EmailNotValidError as error:
        raise BootstrapError("Enter a valid email address.") from error
    if len(normalized) > 255:
        raise BootstrapError("Enter a valid email address.")
    return normalized


def _app_env() -> str:
    value = os.environ.get("APP_ENV", "").lower()
    return value if value in {"development", "production"} else "production"


async def _email_exists(email: str) -> bool:
    async with _session_factory()() as session:
        return (
            await session.scalar(
                select(SuperAdmin.id).where(
                    func.lower(SuperAdmin.email) == email
                )
            )
        ) is not None


async def _save_owner(email: str, password_hash: str, *, reset: bool) -> str:
    async with _session_factory()() as session:
        async with session.begin():
            owner = await session.scalar(
                select(SuperAdmin).where(
                    func.lower(SuperAdmin.email) == email
                )
            )
            if owner is not None:
                if not reset:
                    return "exists"
                owner.password_hash = password_hash
                await session.execute(
                    update(PlatformSession)
                    .where(
                        PlatformSession.super_admin_id == owner.id,
                        PlatformSession.revoked_at.is_(None),
                    )
                    .values(revoked_at=func.now())
                )
                session.add(
                    PlatformAuditLog(
                        action="password_reset",
                        target_type="super_admin",
                        target_id=owner.id,
                        success=True,
                    )
                )
                return "reset"

            if reset:
                raise BootstrapError(
                    "No platform owner exists for that email; nothing was reset."
                )

            any_owner_id = await session.scalar(select(SuperAdmin.id).limit(1))
            if any_owner_id is not None:
                raise BootstrapError(
                    "A platform owner already exists; bootstrap will not create another."
                )

            session.add(
                SuperAdmin(
                    email=email,
                    password_hash=password_hash,
                    active=True,
                )
            )
            return "created"


async def bootstrap_from_prompt(
    *,
    email: str | None = None,
    reset: bool = False,
) -> None:
    try:
        normalized_email = _normalize_email(
            input("Platform owner email: ") if email is None else email
        )
        exists = await _email_exists(normalized_email)
        if exists and not reset:
            print(
                f"Platform owner {normalized_email} already exists; no changes made."
            )
            return
        if reset and not exists:
            raise BootstrapError(
                "No platform owner exists for that email; nothing was reset."
            )

        if reset:
            confirmation = input(
                "Type "
                f"{normalized_email} to confirm resetting this platform owner's password: "
            )
            if confirmation.strip().lower() != normalized_email:
                raise BootstrapError("Reset confirmation did not match.")

        if PASSWORD_ENV_VAR in os.environ:
            password = os.environ.pop(PASSWORD_ENV_VAR)
            if not password:
                raise BootstrapError(f"{PASSWORD_ENV_VAR} must not be empty.")
        else:
            password = getpass.getpass("Platform owner password: ")
            confirmation = getpass.getpass("Confirm platform owner password: ")
            if password != confirmation:
                raise BootstrapError("Passwords do not match.")

        password_hash = hash_admin_password(password)
        result = await _save_owner(
            normalized_email,
            password_hash,
            reset=reset,
        )
        if result == "created":
            print(f"Created platform owner {normalized_email}.")
        elif result == "reset":
            print(f"Updated platform owner {normalized_email}.")
        else:
            print(
                f"Platform owner {normalized_email} already exists; "
                "no changes made."
            )
    finally:
        await _dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bootstrap the first platform-owner super admin."
    )
    parser.add_argument(
        "--email",
        help="Platform owner email; prompts when omitted.",
    )
    parser.add_argument(
        "--allow-dev",
        action="store_true",
        help="Allow this command when APP_ENV=development.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset an existing owner's password after a separate confirmation.",
    )
    args = parser.parse_args()

    if _app_env() != "production" and not args.allow_dev:
        parser.error("APP_ENV is development; pass --allow-dev to continue.")

    try:
        asyncio.run(
            bootstrap_from_prompt(
                email=args.email,
                reset=args.reset,
            )
        )
    except (BootstrapError, PasswordValidationError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
