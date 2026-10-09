import hashlib
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PlatformAuditLog


def email_sha256(email: str) -> str:
    return hashlib.sha256(email.encode("utf-8")).hexdigest()


def record_platform_event(
    db: AsyncSession,
    request: Request,
    *,
    action: str,
    target_type: str,
    success: bool,
    super_admin_id: UUID | None = None,
    target_id: UUID | None = None,
    email_hash: str | None = None,
) -> PlatformAuditLog:
    row = PlatformAuditLog(
        super_admin_id=super_admin_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        ip=request.client.host if request.client is not None else None,
        user_agent=request.headers.get("user-agent", "")[:200],
        success=success,
        email_hash=email_hash,
    )
    db.add(row)
    return row
