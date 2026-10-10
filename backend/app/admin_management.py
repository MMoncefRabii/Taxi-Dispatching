from datetime import datetime, timezone
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Admin, AdminSession, AuditLog, Center


class AdminDeactivationError(Exception):
    pass


class AdminNotFoundError(AdminDeactivationError):
    pass


class SelfDeactivationError(AdminDeactivationError):
    pass


class LastActiveAdminError(AdminDeactivationError):
    pass


async def deactivate_admin_in_transaction(
    session: AsyncSession,
    admin_id: uuid.UUID,
    *,
    center_id: uuid.UUID | None = None,
    actor_admin_id: uuid.UUID | None = None,
) -> bool:
    statement = select(Admin).where(Admin.id == admin_id).with_for_update()
    if center_id is not None:
        statement = statement.where(Admin.center_id == center_id)

    result = await session.execute(statement)
    target = result.scalar_one_or_none()
    if target is None:
        raise AdminNotFoundError("Admin not found.")
    if actor_admin_id == target.id:
        raise SelfDeactivationError
    if not target.active:
        return False

    await session.execute(
        select(Center.id)
        .where(Center.id == target.center_id)
        .with_for_update()
    )
    active_admin_count = await session.scalar(
        select(func.count(Admin.id)).where(
            Admin.center_id == target.center_id,
            Admin.active.is_(True),
        )
    )
    if active_admin_count is None or active_admin_count <= 1:
        raise LastActiveAdminError(
            "Cannot deactivate the last active admin of this center."
        )

    now = datetime.now(timezone.utc)
    target.active = False
    target.deactivated_at = now
    await session.execute(
        update(AdminSession)
        .where(
            AdminSession.admin_id == target.id,
            AdminSession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    if actor_admin_id is not None:
        session.add(
            AuditLog(
                center_id=target.center_id,
                actor_admin_id=actor_admin_id,
                action="admin.deactivate",
                entity_type="admin",
                entity_id=target.id,
                before_state={"active": True},
                after_state={"active": False},
            )
        )
    return True
