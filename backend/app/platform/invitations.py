import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Admin, AdminInvitation, Center
from app.passwords import PasswordValidationError, hash_admin_password
from app.platform.audit import record_platform_event

INVITATION_TTL = timedelta(hours=48)
INVALID_INVITATION_MESSAGE = "Invalid or expired invitation"


class CenterNotFoundError(Exception):
    pass


class InactiveCenterError(Exception):
    pass


class ExistingAdminError(Exception):
    pass


class InvalidInvitationError(Exception):
    pass


async def create_invitation(
    session: AsyncSession,
    center_id: uuid.UUID,
    email: str,
    created_by: uuid.UUID | None,
) -> str:
    normalized_email = email.strip().lower()
    center_result = await session.execute(
        select(Center).where(Center.id == center_id).with_for_update()
    )
    center = center_result.scalar_one_or_none()
    if center is None:
        raise CenterNotFoundError
    if not center.active:
        raise InactiveCenterError

    admin_result = await session.execute(
        select(Admin.id).where(Admin.email == normalized_email)
    )
    if admin_result.scalar_one_or_none() is not None:
        raise ExistingAdminError

    now = datetime.now(timezone.utc)
    await session.execute(
        update(AdminInvitation)
        .where(
            AdminInvitation.center_id == center_id,
            AdminInvitation.email == normalized_email,
            AdminInvitation.used_at.is_(None),
            AdminInvitation.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )

    token = secrets.token_urlsafe(32)
    session.add(
        AdminInvitation(
            center_id=center_id,
            email=normalized_email,
            token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
            created_at=now,
            expires_at=now + INVITATION_TTL,
            created_by_super_admin_id=created_by,
        )
    )
    await session.flush()
    return token


async def accept_invitation(
    session: AsyncSession,
    token: str,
    password: str,
) -> uuid.UUID:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    claim_result = await session.execute(
        update(AdminInvitation)
        .where(
            AdminInvitation.token_hash == token_hash,
            AdminInvitation.used_at.is_(None),
            AdminInvitation.revoked_at.is_(None),
            AdminInvitation.expires_at > func.now(),
        )
        .values(used_at=func.now())
        .returning(AdminInvitation.center_id, AdminInvitation.email)
    )
    invitation = claim_result.one_or_none()
    if invitation is None:
        await session.rollback()
        raise InvalidInvitationError

    center_id, email = invitation
    existing_admin = await session.execute(
        select(Admin.id).where(Admin.email == email)
    )
    if existing_admin.scalar_one_or_none() is not None:
        await session.rollback()
        raise InvalidInvitationError

    try:
        password_hash = hash_admin_password(password)
        session.add(
            Admin(
                center_id=center_id,
                email=email,
                password_hash=password_hash,
                role="center_admin",
                active=True,
            )
        )
        await session.flush()
    except IntegrityError as error:
        await session.rollback()
        constraint_name = getattr(error.orig, "constraint_name", None)
        if constraint_name != "uq_admin_email":
            raise
        raise InvalidInvitationError from error
    except PasswordValidationError:
        await session.rollback()
        raise

    return center_id


class AcceptInvitationRoute(APIRoute):
    def get_route_handler(self) -> Callable[..., Any]:
        original_handler = super().get_route_handler()

        async def sanitized_handler(request: Request) -> Response:
            try:
                return await original_handler(request)
            except RequestValidationError:
                return JSONResponse(
                    status_code=422,
                    content={"detail": "Invalid invitation request"},
                )

        return sanitized_handler


class AcceptInvitationBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    token: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=12, max_length=128)


public_router = APIRouter(route_class=AcceptInvitationRoute)


@public_router.post("/invitations/accept", status_code=201)
async def accept_invitation_route(
    body: AcceptInvitationBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    try:
        center_id = await accept_invitation(db, body.token, body.password)
    except InvalidInvitationError:
        raise HTTPException(400, INVALID_INVITATION_MESSAGE) from None

    record_platform_event(
        db,
        request,
        action="invitation_accepted",
        target_type="center",
        target_id=center_id,
        success=True,
    )
    await db.commit()
    return {"ok": True}
