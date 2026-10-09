import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import PlatformSession, SuperAdmin

PLATFORM_SESSION_COOKIE = "platform_session"
password_hasher = PasswordHasher()
dummy_password_hash = password_hasher.hash(secrets.token_urlsafe(32))


@dataclass(frozen=True)
class PlatformPrincipal:
    super_admin: SuperAdmin
    session: PlatformSession


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError):
        return False


async def require_super_admin(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> PlatformPrincipal:
    token = request.cookies.get(PLATFORM_SESSION_COOKIE)
    if not token:
        raise HTTPException(401, "Authentication required")

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    session_result = await db.execute(
        select(PlatformSession).where(PlatformSession.token_hash == token_hash)
    )
    platform_session = session_result.scalar_one_or_none()
    if platform_session is None or not secrets.compare_digest(
        platform_session.token_hash, token_hash
    ):
        raise HTTPException(401, "Invalid or expired platform session")

    now = datetime.now(timezone.utc)
    if (
        platform_session.revoked_at is not None
        or platform_session.expires_at <= now
    ):
        raise HTTPException(401, "Invalid or expired platform session")

    admin_result = await db.execute(
        select(SuperAdmin).where(
            SuperAdmin.id == platform_session.super_admin_id,
            SuperAdmin.active.is_(True),
        )
    )
    super_admin = admin_result.scalar_one_or_none()
    if super_admin is None:
        raise HTTPException(401, "Invalid or expired platform session")
    return PlatformPrincipal(super_admin=super_admin, session=platform_session)
