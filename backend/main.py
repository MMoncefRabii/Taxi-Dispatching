import asyncio
import hashlib
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import engine, get_db
from app.models import Admin, AdminSession, Driver, DriverLocation

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
MAX_ACCURACY_M = 50
ADMIN_SESSION_COOKIE = "admin_session"
ADMIN_SESSION_TTL = timedelta(hours=8)
password_hasher = PasswordHasher()
dummy_password_hash = password_hasher.hash(secrets.token_urlsafe(32))


def _normalize_recorded_at(value: float | None) -> float:
    now = time.time()
    if value is None or value > now + 60 or value < now - 86400:
        return now
    return value


def _as_utc_datetime(timestamp: float) -> datetime:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(title="Fleet Tracker", lifespan=lifespan)
clients: dict[WebSocket, uuid.UUID] = {}


class NewDriver(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    phone: str = Field(..., min_length=5, max_length=20)


class Loc(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    speed: float | None = Field(default=None, ge=0)
    heading: float | None = Field(default=None, ge=0, le=360)
    accuracy: float | None = Field(default=None, ge=0)
    recorded_at: float | None = None


class Status(BaseModel):
    online: bool


class AdminLogin(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


def _verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError):
        return False


async def _admin_from_session(token: str, db: AsyncSession) -> Admin | None:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    result = await db.execute(
        select(AdminSession).where(AdminSession.token_hash == token_hash)
    )
    admin_session = result.scalar_one_or_none()
    if admin_session is None or not secrets.compare_digest(
        admin_session.token_hash, token_hash
    ):
        return None

    now = datetime.now(timezone.utc)
    if admin_session.revoked_at is not None or admin_session.expires_at <= now:
        return None

    admin_result = await db.execute(
        select(Admin).where(
            Admin.id == admin_session.admin_id,
            Admin.active.is_(True),
        )
    )
    return admin_result.scalar_one_or_none()


async def require_admin(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Admin:
    token = request.cookies.get(ADMIN_SESSION_COOKIE)
    if not token:
        raise HTTPException(401, "Authentication required")
    admin = await _admin_from_session(token, db)
    if admin is None:
        raise HTTPException(401, "Invalid or expired admin session")
    return admin


def _origin_matches_host(origin: str | None, host: str | None) -> bool:
    if not origin or not host:
        return False
    try:
        parsed_origin = urlsplit(origin)
    except ValueError:
        return False
    return (
        parsed_origin.scheme in {"http", "https"}
        and parsed_origin.netloc.lower() == host.lower()
        and parsed_origin.path in {"", "/"}
        and not parsed_origin.query
        and not parsed_origin.fragment
        and parsed_origin.username is None
        and parsed_origin.password is None
    )


@app.post("/admin/login")
async def admin_login(
    body: AdminLogin,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    email = body.email.strip().lower()
    result = await db.execute(
        select(Admin).where(func.lower(Admin.email) == email)
    )
    admin = result.scalar_one_or_none()
    password_hash = admin.password_hash if admin is not None else dummy_password_hash
    password_matches = _verify_password(password_hash, body.password)
    if admin is None or not password_matches or not admin.active:
        raise HTTPException(401, "Invalid email or password")

    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    db.add(
        AdminSession(
            admin_id=admin.id,
            token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
            created_at=now,
            expires_at=now + ADMIN_SESSION_TTL,
        )
    )
    await db.commit()
    response.set_cookie(
        key=ADMIN_SESSION_COOKIE,
        value=token,
        max_age=int(ADMIN_SESSION_TTL.total_seconds()),
        httponly=True,
        secure=settings.app_env == "production",
        samesite="strict",
        path="/",
    )
    return {"ok": True}


@app.post("/admin/logout", status_code=204)
async def admin_logout(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    token = request.cookies.get(ADMIN_SESSION_COOKIE)
    if token:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        result = await db.execute(
            select(AdminSession).where(AdminSession.token_hash == token_hash)
        )
        admin_session = result.scalar_one_or_none()
        if (
            admin_session is not None
            and secrets.compare_digest(admin_session.token_hash, token_hash)
            and admin_session.revoked_at is None
        ):
            admin_session.revoked_at = datetime.now(timezone.utc)
            await db.commit()

    response = Response(status_code=204)
    response.delete_cookie(
        key=ADMIN_SESSION_COOKIE,
        path="/",
        secure=settings.app_env == "production",
        httponly=True,
        samesite="strict",
    )
    return response


@app.get("/admin/me")
async def admin_me(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    admin = await require_admin(request, db)
    return {
        "email": admin.email.lower(),
        "center_id": str(admin.center_id),
    }


async def get_driver(token: str | None, db: AsyncSession) -> Driver:
    if not token:
        raise HTTPException(401, "Missing driver token")
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    result = await db.execute(
        select(Driver).where(
            Driver.token_hash == token_hash,
            Driver.active.is_(True),
        )
    )
    driver = result.scalar_one_or_none()
    if driver is None:
        raise HTTPException(401, "Invalid driver token")
    return driver


async def broadcast(message: dict, center_id: uuid.UUID) -> None:
    recipients = [
        ws for ws, client_center_id in clients.items() if client_center_id == center_id
    ]
    if not recipients:
        return

    async def send_one(ws: WebSocket) -> None:
        try:
            await asyncio.wait_for(ws.send_json(message), timeout=2.0)
        except (OSError, RuntimeError, TimeoutError, WebSocketDisconnect):
            clients.pop(ws, None)

    await asyncio.gather(*(send_one(ws) for ws in recipients))


@app.post("/admin/drivers")
async def create_driver(
    body: NewDriver,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(require_admin),
):
    token = secrets.token_urlsafe(24)
    driver = Driver(
        center_id=admin.center_id,
        name=body.name,
        phone=body.phone,
        token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
    )
    db.add(driver)
    await db.commit()
    return {"id": str(driver.id), "name": body.name, "token": token}


@app.get("/admin/drivers/latest")
async def latest_positions(
    limit: int = Query(default=500, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(require_admin),
):
    center_id = admin.center_id
    ranked_locations = (
        select(
            DriverLocation.driver_id.label("driver_id"),
            DriverLocation.lat.label("lat"),
            DriverLocation.lng.label("lng"),
            DriverLocation.speed.label("speed"),
            DriverLocation.heading.label("heading"),
            DriverLocation.accuracy.label("accuracy"),
            DriverLocation.recorded_at.label("recorded_at"),
            func.row_number()
            .over(
                partition_by=DriverLocation.driver_id,
                order_by=(DriverLocation.recorded_at.desc(), DriverLocation.id.desc()),
            )
            .label("row_number"),
        )
        .where(DriverLocation.center_id == center_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(
                Driver,
                ranked_locations.c.lat,
                ranked_locations.c.lng,
                ranked_locations.c.speed,
                ranked_locations.c.heading,
                ranked_locations.c.accuracy,
                ranked_locations.c.recorded_at,
            )
            .outerjoin(
                ranked_locations,
                (ranked_locations.c.driver_id == Driver.id)
                & (ranked_locations.c.row_number == 1),
            )
            .where(Driver.center_id == center_id)
            .order_by(Driver.name, Driver.id)
            .limit(limit)
        )
    ).all()
    return [
        {
            "id": str(driver.id),
            "name": driver.name,
            "phone": driver.phone,
            "online": int(driver.online),
            "lat": lat,
            "lng": lng,
            "speed": speed,
            "heading": heading,
            "accuracy": accuracy,
            "recorded_at": recorded_at.timestamp()
            if recorded_at is not None
            else None,
        }
        for driver, lat, lng, speed, heading, accuracy, recorded_at in rows
    ]


@app.post("/status")
async def set_status(
    body: Status,
    x_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    driver = await get_driver(x_token, db)
    driver.online = body.online
    await db.commit()
    await broadcast(
        {"type": "status", "driver_id": str(driver.id), "online": body.online},
        driver.center_id,
    )
    return {"ok": True}


@app.post("/location")
async def post_location(
    loc: Loc,
    x_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    driver = await get_driver(x_token, db)
    if loc.accuracy is not None and loc.accuracy > MAX_ACCURACY_M:
        return {"ok": False, "ignored": "low accuracy"}

    timestamp = _normalize_recorded_at(loc.recorded_at)
    db.add(
        DriverLocation(
            center_id=driver.center_id,
            driver_id=driver.id,
            lat=loc.lat,
            lng=loc.lng,
            speed=loc.speed,
            heading=loc.heading,
            accuracy=loc.accuracy,
            recorded_at=_as_utc_datetime(timestamp),
        )
    )
    broadcast_status = None
    if not driver.online:
        driver.online = True
        broadcast_status = {
            "type": "status",
            "driver_id": str(driver.id),
            "online": True,
        }
    await db.commit()

    if broadcast_status is not None:
        await broadcast(broadcast_status, driver.center_id)
    await broadcast(
        {
            "type": "location",
            "driver_id": str(driver.id),
            "name": driver.name,
            "lat": loc.lat,
            "lng": loc.lng,
            "speed": loc.speed,
            "heading": loc.heading,
            "recorded_at": timestamp,
        },
        driver.center_id,
    )
    return {"ok": True}


@app.websocket("/ws")
async def ws_endpoint(
    ws: WebSocket,
    db: AsyncSession = Depends(get_db),
):
    if not _origin_matches_host(ws.headers.get("origin"), ws.headers.get("host")):
        await ws.close(code=1008)
        return

    token = ws.cookies.get(ADMIN_SESSION_COOKIE)
    if not token:
        await ws.close(code=1008)
        return
    admin = await _admin_from_session(token, db)
    if admin is None:
        await ws.close(code=1008)
        return

    await ws.accept()
    clients[ws] = admin.center_id
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        clients.pop(ws, None)


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")