import asyncio
import hashlib
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import engine, get_db
from app.models import Driver, DriverLocation

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_CENTER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
MAX_ACCURACY_M = 50


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
clients: set[WebSocket] = set()


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


def require_admin(key: str | None) -> None:
    if key is None:
        raise HTTPException(401, "Missing admin key")
    expected = settings.admin_key.encode("utf-8", "surrogateescape")
    supplied = key.encode("utf-8", "surrogateescape")
    if not secrets.compare_digest(supplied, expected):
        raise HTTPException(401, "Invalid admin key")


async def get_driver(token: str | None, db: AsyncSession) -> Driver:
    if not token:
        raise HTTPException(401, "Missing driver token")
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    result = await db.execute(
        select(Driver).where(
            Driver.token_hash == token_hash,
            Driver.center_id == DEFAULT_CENTER_ID,
            Driver.active.is_(True),
        )
    )
    driver = result.scalar_one_or_none()
    if driver is None:
        raise HTTPException(401, "Invalid driver token")
    return driver


async def broadcast(message: dict) -> None:
    if not clients:
        return

    async def send_one(ws: WebSocket) -> None:
        try:
            await asyncio.wait_for(ws.send_json(message), timeout=2.0)
        except Exception:
            clients.discard(ws)

    await asyncio.gather(*(send_one(ws) for ws in list(clients)), return_exceptions=True)


@app.post("/admin/drivers")
async def create_driver(
    body: NewDriver,
    x_admin_key: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    require_admin(x_admin_key)
    token = secrets.token_urlsafe(24)
    driver = Driver(
        center_id=DEFAULT_CENTER_ID,
        name=body.name,
        phone=body.phone,
        token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
    )
    db.add(driver)
    await db.commit()
    return {"id": str(driver.id), "name": body.name, "token": token}


@app.get("/admin/drivers/latest")
async def latest_positions(
    x_admin_key: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    require_admin(x_admin_key)
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
        .where(DriverLocation.center_id == DEFAULT_CENTER_ID)
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
            .where(Driver.center_id == DEFAULT_CENTER_ID)
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
    await broadcast({"type": "status", "driver_id": str(driver.id), "online": body.online})
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
            center_id=DEFAULT_CENTER_ID,
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
        await broadcast(broadcast_status)
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
        }
    )
    return {"ok": True}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket, key: str = Query(default="")):
    expected = settings.admin_key.encode("utf-8", "surrogateescape")
    provided = key.encode("utf-8", "surrogateescape")
    if not secrets.compare_digest(provided, expected):
        await ws.close(code=1008)
        return

    await ws.accept()
    clients.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(ws)


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")