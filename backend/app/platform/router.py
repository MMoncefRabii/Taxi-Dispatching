import hashlib
import secrets
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.models import (
    Admin,
    AdminInvitation,
    Center,
    Driver,
    PlatformAuditLog,
    PlatformSession,
    SuperAdmin,
)
from app.platform.audit import email_sha256, record_platform_event
from app.platform.invitations import (
    CenterNotFoundError,
    ExistingAdminError,
    InactiveCenterError,
    create_invitation,
)
from app.platform.auth import (
    PLATFORM_SESSION_COOKIE,
    PlatformPrincipal,
    dummy_password_hash,
    require_super_admin,
    verify_password,
)

class PlatformAPIRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        original_handler = super().get_route_handler()

        async def sanitized_handler(request: Request) -> Response:
            try:
                return await original_handler(request)
            except RequestValidationError:
                return JSONResponse(
                    status_code=422,
                    content={"detail": "Invalid platform request"},
                )

        return sanitized_handler


router = APIRouter(
    prefix="/platform",
    tags=["platform"],
    route_class=PlatformAPIRoute,
)
PLATFORM_SESSION_TTL = timedelta(hours=4)


class PlatformLogin(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip()
        if (
            normalized != value
            or "@" not in normalized
            or any(character.isspace() for character in normalized)
        ):
            raise ValueError("Enter a valid email address")
        return value


class NewCenter(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(min_length=1, max_length=200)
    city: str = Field(min_length=1, max_length=100)
    timezone: str = Field(min_length=1, max_length=50)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Unknown IANA timezone")
        return value


class NewAdminInvitation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def validate_email_address(cls, value: str) -> str:
        normalized_input = value.strip()
        local_part, separator, domain = normalized_input.rpartition("@")
        if (
            separator
            and len(domain) > len(".invalid")
            and domain.lower().endswith(".invalid")
        ):
            # Preserve the reserved test domain used for non-deliverable invitations.
            try:
                validate_email(
                    f"{local_part}@{domain[:-len('.invalid')]}.example.com",
                    check_deliverability=False,
                )
            except EmailNotValidError as error:
                raise ValueError("Enter a valid email address") from error
            return normalized_input.lower()
        try:
            normalized = validate_email(
                normalized_input,
                check_deliverability=False,
            )
        except EmailNotValidError as error:
            raise ValueError("Enter a valid email address") from error
        return normalized.normalized.lower()


def _serialize_center(
    center: Center,
    driver_count: int,
    admin_count: int,
) -> dict[str, object]:
    return {
        "id": str(center.id),
        "name": center.name,
        "city": center.city,
        "timezone": center.timezone,
        "active": center.active,
        "created_at": center.created_at,
        "driver_count": driver_count,
        "admin_count": admin_count,
    }


@router.post("/login")
async def platform_login(
    body: PlatformLogin,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    email = body.email.lower()
    result = await db.execute(
        select(SuperAdmin).where(func.lower(SuperAdmin.email) == email)
    )
    super_admin = result.scalar_one_or_none()
    password_hash = (
        super_admin.password_hash
        if super_admin is not None
        else dummy_password_hash
    )
    password_matches = verify_password(password_hash, body.password)
    if super_admin is None or not password_matches or not super_admin.active:
        record_platform_event(
            db,
            request,
            action="login_failure",
            target_type="super_admin",
            success=False,
            email_hash=email_sha256(email),
        )
        await db.commit()
        raise HTTPException(401, "Invalid email or password")

    now = datetime.now(timezone.utc)
    token = secrets.token_urlsafe(32)
    db.add(
        PlatformSession(
            super_admin_id=super_admin.id,
            token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
            created_at=now,
            expires_at=now + PLATFORM_SESSION_TTL,
        )
    )
    super_admin.last_login = now
    record_platform_event(
        db,
        request,
        action="login_success",
        target_type="super_admin",
        success=True,
        super_admin_id=super_admin.id,
        target_id=super_admin.id,
    )
    await db.commit()
    response.set_cookie(
        key=PLATFORM_SESSION_COOKIE,
        value=token,
        max_age=int(PLATFORM_SESSION_TTL.total_seconds()),
        httponly=True,
        secure=settings.app_env == "production",
        samesite="strict",
        path="/platform",
    )
    return {"ok": True}


@router.post("/logout", status_code=204)
async def platform_logout(
    request: Request,
    principal: PlatformPrincipal = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> Response:
    principal.session.revoked_at = datetime.now(timezone.utc)
    record_platform_event(
        db,
        request,
        action="logout",
        target_type="super_admin",
        success=True,
        super_admin_id=principal.super_admin.id,
        target_id=principal.super_admin.id,
    )
    await db.commit()
    response = Response(status_code=204)
    response.delete_cookie(
        key=PLATFORM_SESSION_COOKIE,
        path="/platform",
        secure=settings.app_env == "production",
        httponly=True,
        samesite="strict",
    )
    return response


@router.get("/me")
async def platform_me(
    principal: PlatformPrincipal = Depends(require_super_admin),
) -> dict[str, str]:
    return {"email": principal.super_admin.email.lower()}


@router.get("/centers")
async def list_centers(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _principal: PlatformPrincipal = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, object]]:
    driver_counts = (
        select(
            Driver.center_id.label("center_id"),
            func.count(Driver.id).label("driver_count"),
        )
        .group_by(Driver.center_id)
        .subquery()
    )
    admin_counts = (
        select(
            Admin.center_id.label("center_id"),
            func.count(Admin.id).label("admin_count"),
        )
        .where(Admin.active.is_(True))
        .group_by(Admin.center_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(
                Center,
                func.coalesce(driver_counts.c.driver_count, 0),
                func.coalesce(admin_counts.c.admin_count, 0),
            )
            .outerjoin(driver_counts, driver_counts.c.center_id == Center.id)
            .outerjoin(admin_counts, admin_counts.c.center_id == Center.id)
            .order_by(Center.name, Center.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [
        _serialize_center(center, driver_count, admin_count)
        for center, driver_count, admin_count in rows
    ]


@router.post("/centers", status_code=201)
async def create_center(
    body: NewCenter,
    request: Request,
    principal: PlatformPrincipal = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    center = Center(
        name=body.name,
        city=body.city,
        timezone=body.timezone,
        active=True,
    )
    db.add(center)
    await db.flush()
    record_platform_event(
        db,
        request,
        action="center_created",
        target_type="center",
        success=True,
        super_admin_id=principal.super_admin.id,
        target_id=center.id,
    )
    await db.commit()
    return _serialize_center(center, 0, 0)


@router.post("/centers/{center_id}/invitations", status_code=201)
async def create_center_invitation(
    center_id: uuid.UUID,
    body: NewAdminInvitation,
    request: Request,
    response: Response,
    principal: PlatformPrincipal = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    try:
        token = await create_invitation(
            db,
            center_id,
            body.email,
            principal.super_admin.id,
        )
    except CenterNotFoundError:
        raise HTTPException(404, "Center not found") from None
    except InactiveCenterError:
        raise HTTPException(409, "Center is inactive") from None
    except ExistingAdminError:
        raise HTTPException(409, "An admin already exists for this email") from None

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    invitation_result = await db.execute(
        select(AdminInvitation).where(AdminInvitation.token_hash == token_hash)
    )
    invitation = invitation_result.scalar_one()
    record_platform_event(
        db,
        request,
        action="invitation_created",
        target_type="invitation",
        target_id=invitation.id,
        success=True,
        super_admin_id=principal.super_admin.id,
    )
    await db.commit()
    response.headers["Cache-Control"] = "no-store"
    return {
        "invitation_id": str(invitation.id),
        "email": invitation.email,
        "expires_at": invitation.expires_at,
        "link": f"{settings.frontend_base_url}/invite.html",
        "token": token,
    }


@router.get("/centers/{center_id}/invitations")
async def list_center_invitations(
    center_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _principal: PlatformPrincipal = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, object]]:
    now = datetime.now(timezone.utc)
    invitations = (
        await db.execute(
            select(AdminInvitation)
            .where(AdminInvitation.center_id == center_id)
            .order_by(AdminInvitation.created_at.desc(), AdminInvitation.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()

    def status(invitation: AdminInvitation) -> str:
        if invitation.used_at is not None:
            return "used"
        if invitation.revoked_at is not None:
            return "revoked"
        if invitation.expires_at <= now:
            return "expired"
        return "pending"

    return [
        {
            "id": str(invitation.id),
            "email": invitation.email,
            "created_at": invitation.created_at,
            "expires_at": invitation.expires_at,
            "status": status(invitation),
        }
        for invitation in invitations
    ]


@router.post("/invitations/{invitation_id}/revoke")
async def revoke_invitation(
    invitation_id: uuid.UUID,
    request: Request,
    principal: PlatformPrincipal = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    result = await db.execute(
        select(AdminInvitation).where(AdminInvitation.id == invitation_id)
    )
    invitation = result.scalar_one_or_none()
    if invitation is None:
        raise HTTPException(404, "Invitation not found")

    now = datetime.now(timezone.utc)
    if (
        invitation.used_at is None
        and invitation.revoked_at is None
        and invitation.expires_at > now
    ):
        revoked = await db.execute(
            update(AdminInvitation)
            .where(
                AdminInvitation.id == invitation_id,
                AdminInvitation.used_at.is_(None),
                AdminInvitation.revoked_at.is_(None),
                AdminInvitation.expires_at > now,
            )
            .values(revoked_at=now)
            .returning(AdminInvitation.id)
        )
        if revoked.scalar_one_or_none() is not None:
            record_platform_event(
                db,
                request,
                action="invitation_revoked",
                target_type="invitation",
                target_id=invitation_id,
                success=True,
                super_admin_id=principal.super_admin.id,
            )
            await db.commit()
    return {"ok": True}


@router.get("/audit")
async def list_platform_audit(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _principal: PlatformPrincipal = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, object]]:
    rows = (
        await db.execute(
            select(PlatformAuditLog)
            .order_by(
                PlatformAuditLog.created_at.desc(),
                PlatformAuditLog.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    return [
        {
            "id": str(row.id),
            "super_admin_id": str(row.super_admin_id)
            if row.super_admin_id is not None
            else None,
            "action": row.action,
            "target_type": row.target_type,
            "target_id": str(row.target_id) if row.target_id is not None else None,
            "ip": row.ip,
            "user_agent": row.user_agent,
            "success": row.success,
            "created_at": row.created_at,
        }
        for row in rows
    ]
