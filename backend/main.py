import asyncio
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "tracking.db"
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

ADMIN_KEY = os.getenv("ADMIN_KEY")
if ADMIN_KEY is None or ADMIN_KEY == "":
    raise RuntimeError("ADMIN_KEY environment variable is required")

MAX_ACCURACY_M = 50
DB_LOCK = threading.Lock()


def _normalize_recorded_at(value: float | None) -> float:
    now = time.time()
    if value is None:
        return now
    if value > now + 60 or value < now - 86400:
        return now
    return value


db = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
db.row_factory = sqlite3.Row
db.execute("PRAGMA journal_mode=WAL;")
db.executescript(
    """
    CREATE TABLE IF NOT EXISTS drivers (
        id INTEGER PRIMARY KEY,
        name TEXT,
        phone TEXT,
        token TEXT UNIQUE,
        online INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS locations (
        id INTEGER PRIMARY KEY,
        driver_id INTEGER,
        lat REAL,
        lng REAL,
        speed REAL,
        heading REAL,
        accuracy REAL,
        recorded_at REAL
    );
    CREATE INDEX IF NOT EXISTS idx_loc ON locations(driver_id, recorded_at);
    CREATE TABLE IF NOT EXISTS latest (
        driver_id INTEGER PRIMARY KEY,
        lat REAL,
        lng REAL,
        speed REAL,
        heading REAL,
        accuracy REAL,
        recorded_at REAL
    );
    """
)

app = FastAPI(title="Fleet Tracker")
clients: set[WebSocket] = set()


# ---------- models ----------
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


# ---------- helpers ----------
def require_admin(key: str):
    if key is None:
        raise HTTPException(401, "Missing admin key")
    expected = ADMIN_KEY.encode("utf-8", "surrogateescape")
    supplied = (key or "").encode("utf-8", "surrogateescape")
    if not secrets.compare_digest(supplied, expected):
        raise HTTPException(401, "Invalid admin key")


def get_driver(token: str):
    if token is None or token == "":
        raise HTTPException(401, "Missing driver token")
    with DB_LOCK:
        row = db.execute(
            "SELECT id, name FROM drivers WHERE token=?",
            (token,),
        ).fetchone()
    if not row:
        raise HTTPException(401, "Invalid driver token")
    return row


async def broadcast(message: dict):
    if not clients:
        return

    async def send_one(ws: WebSocket):
        try:
            await asyncio.wait_for(ws.send_json(message), timeout=2.0)
        except Exception:
            clients.discard(ws)

    await asyncio.gather(*(send_one(ws) for ws in list(clients)), return_exceptions=True)


# ---------- admin ----------
@app.post("/admin/drivers")
def create_driver(body: NewDriver, x_admin_key: str = Header(None)):
    require_admin(x_admin_key)
    token = secrets.token_urlsafe(24)
    with DB_LOCK:
        cur = db.execute(
            "INSERT INTO drivers (name, phone, token) VALUES (?, ?, ?)",
            (body.name, body.phone, token),
        )
        db.commit()
    return {"id": cur.lastrowid, "name": body.name, "token": token}


@app.get("/admin/drivers/latest")
def latest_positions(x_admin_key: str = Header(None)):
    require_admin(x_admin_key)
    with DB_LOCK:
        rows = db.execute(
            """
            SELECT d.id, d.name, d.phone, d.online,
                   l.lat, l.lng, l.speed, l.heading, l.accuracy, l.recorded_at
            FROM drivers d LEFT JOIN latest l ON l.driver_id = d.id
            """
        ).fetchall()
    return [dict(r) for r in rows]


# ---------- driver ----------
@app.post("/status")
async def set_status(body: Status, x_token: str = Header(None)):
    driver = get_driver(x_token)
    with DB_LOCK:
        db.execute(
            "UPDATE drivers SET online=? WHERE id=?",
            (int(body.online), driver["id"]),
        )
        db.commit()
    await broadcast({"type": "status", "driver_id": driver["id"], "online": body.online})
    return {"ok": True}


@app.post("/location")
async def post_location(loc: Loc, x_token: str = Header(None)):
    driver = get_driver(x_token)
    if loc.accuracy is not None and loc.accuracy > MAX_ACCURACY_M:
        return {"ok": False, "ignored": "low accuracy"}

    ts = _normalize_recorded_at(loc.recorded_at)
    values = (driver["id"], loc.lat, loc.lng, loc.speed, loc.heading, loc.accuracy, ts)

    with DB_LOCK:
        db.execute(
            "INSERT INTO locations (driver_id, lat, lng, speed, heading, accuracy, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            values,
        )
        db.execute(
            """
            INSERT INTO latest (driver_id, lat, lng, speed, heading, accuracy, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(driver_id)
            DO UPDATE SET
                lat = excluded.lat,
                lng = excluded.lng,
                speed = excluded.speed,
                heading = excluded.heading,
                accuracy = excluded.accuracy,
                recorded_at = excluded.recorded_at
            WHERE excluded.recorded_at > latest.recorded_at
            """,
            values,
        )
        online = db.execute("SELECT online FROM drivers WHERE id = ?", (driver["id"],)).fetchone()
        if online and online["online"] == 0:
            db.execute(
                "UPDATE drivers SET online = 1 WHERE id = ?",
                (driver["id"],),
            )
            broadcast_status = {"type": "status", "driver_id": driver["id"], "online": True}
        else:
            broadcast_status = None
        db.commit()

    if broadcast_status is not None:
        await broadcast(broadcast_status)

    await broadcast({
        "type": "location",
        "driver_id": driver["id"],
        "name": driver["name"],
        "lat": loc.lat,
        "lng": loc.lng,
        "speed": loc.speed,
        "heading": loc.heading,
        "recorded_at": ts,
    })
    return {"ok": True}


# ---------- live feed for the dashboard ----------
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket, key: str = Query("")):
    try:
        expected = ADMIN_KEY.encode("utf-8", "surrogateescape")
        provided = (key or "").encode("utf-8", "surrogateescape")
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


# dashboard (must stay last)
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
