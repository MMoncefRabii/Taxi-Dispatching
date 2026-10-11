import asyncio
import hashlib
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://localhost/test_db")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.sql.dml import Insert

import main
from app.db import get_db
from app.locations import (
    LocationLimits,
    LocationReason,
    LocationSample,
    validate_location,
)
from app.models import Driver, DriverLocation


NOW = 1_800_000_000.0
TOKEN = "test-driver-token"
LIMITS = LocationLimits(
    max_future_seconds=60,
    max_age_seconds=300,
    min_interval_seconds=2,
    max_speed_kmh=200,
    max_accuracy_m=50,
)


def sample(
    *,
    lat=36.8,
    lng=10.18,
    recorded_at=NOW,
    speed=None,
    heading=None,
    accuracy=None,
):
    return LocationSample(
        lat=lat,
        lng=lng,
        recorded_at=recorded_at,
        speed=speed,
        heading=heading,
        accuracy=accuracy,
    )


def test_validation_rejects_out_of_range_coordinates():
    assert (
        validate_location(
            sample(lat=91),
            now=NOW,
            previous=None,
            limits=LIMITS,
        )
        is LocationReason.INVALID_COORDINATES
    )


@pytest.mark.parametrize(
    ("recorded_at", "max_age", "expected"),
    [
        (NOW - 301, 300, LocationReason.TIMESTAMP_TOO_OLD),
        (NOW + 61, 300, LocationReason.TIMESTAMP_TOO_FUTURE),
        (NOW - 21_601, 21_600, LocationReason.TIMESTAMP_TOO_OLD),
        (NOW - 301, 21_600, None),
    ],
)
def test_validation_applies_live_and_batch_timestamp_windows(
    recorded_at,
    max_age,
    expected,
):
    limits = LocationLimits(
        max_future_seconds=60,
        max_age_seconds=max_age,
        min_interval_seconds=2,
        max_speed_kmh=200,
        max_accuracy_m=50,
    )

    assert (
        validate_location(
            sample(recorded_at=recorded_at),
            now=NOW,
            previous=None,
            limits=limits,
        )
        is expected
    )


def test_validation_rejects_too_frequent_and_implausible_points():
    previous = sample(recorded_at=NOW - 1)
    assert (
        validate_location(
            sample(),
            now=NOW,
            previous=previous,
            limits=LIMITS,
        )
        is LocationReason.TOO_FREQUENT
    )

    far_point = sample(lat=37.8, recorded_at=NOW)
    assert (
        validate_location(
            far_point,
            now=NOW,
            previous=sample(recorded_at=NOW - 3),
            limits=LIMITS,
        )
        is LocationReason.IMPLAUSIBLE_SPEED
    )


def test_validation_accepts_plausible_movement_and_checks_sensor_fields():
    previous = sample(recorded_at=NOW - 10)
    nearby = sample(lat=36.8001, recorded_at=NOW, speed=2, heading=360, accuracy=50)

    assert (
        validate_location(
            nearby,
            now=NOW,
            previous=previous,
            limits=LIMITS,
        )
        is None
    )
    assert (
        validate_location(
            sample(speed=60),
            now=NOW,
            previous=None,
            limits=LIMITS,
        )
        is LocationReason.INVALID_SPEED
    )
    assert (
        validate_location(
            sample(heading=361),
            now=NOW,
            previous=None,
            limits=LIMITS,
        )
        is LocationReason.INVALID_HEADING
    )
    assert (
        validate_location(
            sample(accuracy=50.1),
            now=NOW,
            previous=None,
            limits=LIMITS,
        )
        is LocationReason.LOW_ACCURACY
    )


class FakeResult:
    def __init__(self, value=None):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeLocationDB:
    def __init__(self, *, active=True, online=True, locations=()):
        self.driver = Driver(
            id=uuid.uuid4(),
            center_id=uuid.uuid4(),
            name="Driver One",
            token_hash=hashlib.sha256(TOKEN.encode()).hexdigest(),
            active=active,
            online=online,
        )
        self.locations = list(locations)
        self.execute = AsyncMock(side_effect=self._execute)
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def _execute(self, statement):
        if isinstance(statement, Insert):
            values = statement.compile().params
            recorded_at = values["recorded_at"]
            existing = next(
                (
                    row
                    for row in self.locations
                    if row.driver_id == self.driver.id
                    and row.recorded_at == recorded_at
                ),
                None,
            )
            if existing is not None:
                return FakeResult()
            row = DriverLocation(
                id=uuid.uuid4(),
                center_id=values["center_id"],
                driver_id=values["driver_id"],
                lat=values["lat"],
                lng=values["lng"],
                speed=values["speed"],
                heading=values["heading"],
                accuracy=values["accuracy"],
                recorded_at=recorded_at,
            )
            self.locations.append(row)
            return FakeResult(row.id)

        entity = statement.column_descriptions[0]["entity"]
        params = statement.compile().params
        if entity is Driver:
            if statement._for_update_arg is not None:
                return FakeResult(
                    self.driver
                    if self.driver.active
                    and params.get("id_1") == self.driver.id
                    else None
                )
            return FakeResult(
                self.driver
                if self.driver.active
                and params.get("token_hash_1") == self.driver.token_hash
                else None
            )

        assert entity is DriverLocation
        matching = [
            row
            for row in self.locations
            if row.driver_id == self.driver.id
        ]
        clause = str(statement.whereclause)
        if "recorded_at <" in clause:
            recorded_at = next(
                value
                for key, value in params.items()
                if key.startswith("recorded_at")
            )
            matching = [row for row in matching if row.recorded_at < recorded_at]
            matching.sort(key=lambda row: (row.recorded_at, row.id), reverse=True)
            return FakeResult(matching[0] if matching else None)
        if "recorded_at =" in clause:
            recorded_at = next(
                value
                for key, value in params.items()
                if key.startswith("recorded_at")
            )
            match = next(
                (row for row in matching if row.recorded_at == recorded_at),
                None,
            )
            if statement.column_descriptions[0]["name"] == "id":
                return FakeResult(match.id if match is not None else None)
            return FakeResult(match)
        matching.sort(key=lambda row: (row.recorded_at, row.id), reverse=True)
        return FakeResult(matching[0] if matching else None)


def make_stored_location(driver_id, recorded_at, *, lat=36.8, lng=10.18):
    return DriverLocation(
        id=uuid.uuid4(),
        center_id=uuid.uuid4(),
        driver_id=driver_id,
        lat=lat,
        lng=lng,
        recorded_at=datetime.fromtimestamp(recorded_at, tz=timezone.utc),
    )


@pytest.fixture
def api(monkeypatch):
    database = FakeLocationDB()
    broadcasts = AsyncMock()
    monkeypatch.setattr(main.time, "time", lambda: NOW)
    monkeypatch.setattr(main, "broadcast", broadcasts)
    main.app.dependency_overrides[get_db] = lambda: database
    main.clients.clear()
    with TestClient(main.app) as client:
        yield client, database, broadcasts
    main.app.dependency_overrides.clear()
    main.clients.clear()


def location_body(recorded_at=NOW, *, lat=36.8, lng=10.18, **values):
    return {
        "lat": lat,
        "lng": lng,
        "recorded_at": recorded_at,
        **values,
    }


def batch_body(*points):
    return {"points": list(points)}


def test_live_location_rejects_old_and_future_timestamps_without_echoing(api):
    client, database, _ = api
    for timestamp, reason in (
        (NOW - 301, "timestamp_too_old"),
        (NOW + 61, "timestamp_too_future"),
    ):
        response = client.post(
            "/location",
            headers={"x-token": TOKEN},
            json=location_body(timestamp, lat=88.123456),
        )
        assert response.status_code == 422
        assert response.json() == {"detail": {"reason": reason}}
        assert "88.123456" not in response.text
    assert database.locations == []


def test_batch_uses_its_age_window_and_rejects_future_points(api):
    client, database, _ = api

    response = client.post(
        "/location/batch",
        headers={"x-token": TOKEN},
        json=batch_body(
            location_body(NOW - 21_601),
            location_body(NOW + 61),
        ),
    )

    assert response.status_code == 200
    assert response.json()["rejections"] == [
        {"index": 0, "reason": "timestamp_too_old"},
        {"index": 1, "reason": "timestamp_too_future"},
    ]
    assert database.locations == []


def test_live_too_frequent_returns_429_and_does_not_store(api):
    client, database, _ = api
    database.locations.append(
        make_stored_location(database.driver.id, NOW - 1)
    )

    response = client.post(
        "/location",
        headers={"x-token": TOKEN},
        json=location_body(),
    )

    assert response.status_code == 429
    assert response.json() == {
        "detail": "Location update received too frequently."
    }
    assert len(database.locations) == 1


def test_old_live_client_shape_still_succeeds_and_uses_server_time(api):
    client, database, broadcasts = api
    database.driver.online = False

    response = client.post(
        "/location",
        headers={"x-token": TOKEN},
        json={"lat": 36.8, "lng": 10.18},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert len(database.locations) == 1
    assert database.locations[0].recorded_at.timestamp() == NOW
    assert broadcasts.await_count == 2
    assert broadcasts.await_args_list[-1].args[0]["recorded_at"] == NOW
    assert broadcasts.await_args_list[-1].args[1] == database.driver.center_id


def test_batch_accepts_chronological_plausible_points_and_broadcasts_only_newest(api):
    client, database, broadcasts = api
    response = client.post(
        "/location/batch",
        headers={"x-token": TOKEN},
        json=batch_body(
            location_body(NOW - 14, lng=10.1800),
            location_body(NOW - 7, lng=10.1801),
            location_body(NOW, lng=10.1802),
        ),
    )

    assert response.status_code == 200
    assert response.json() == {
        "accepted": 3,
        "duplicates": 0,
        "rejected": 0,
        "rejections": [],
    }
    assert [row.recorded_at.timestamp() for row in database.locations] == [
        NOW - 14,
        NOW - 7,
        NOW,
    ]
    location_calls = [
        call.args
        for call in broadcasts.await_args_list
        if call.args[0]["type"] == "location"
    ]
    assert len(location_calls) == 1
    assert location_calls[0][0]["recorded_at"] == NOW
    assert location_calls[0][0]["lng"] == 10.1802
    assert location_calls[0][1] == database.driver.center_id


def test_out_of_order_batch_points_are_stored_but_not_broadcast(api):
    client, database, broadcasts = api
    database.locations.append(
        make_stored_location(database.driver.id, NOW, lat=36.8002)
    )

    response = client.post(
        "/location/batch",
        headers={"x-token": TOKEN},
        json=batch_body(
            location_body(NOW - 14, lng=10.1800),
            location_body(NOW - 7, lng=10.1801),
        ),
    )

    assert response.status_code == 200
    assert response.json()["accepted"] == 2
    assert not any(
        call.args[0]["type"] == "location"
        for call in broadcasts.await_args_list
    )


def test_batch_ignores_duplicate_timestamps(api):
    client, database, _ = api
    database.locations.append(
        make_stored_location(database.driver.id, NOW, lat=36.8)
    )

    response = client.post(
        "/location/batch",
        headers={"x-token": TOKEN},
        json=batch_body(location_body(NOW, lat=91)),
    )

    assert response.status_code == 200
    assert response.json() == {
        "accepted": 0,
        "duplicates": 1,
        "rejected": 0,
        "rejections": [],
    }


def test_batch_returns_indexed_generic_rejections(api):
    client, database, _ = api
    database.locations.append(
        make_stored_location(database.driver.id, NOW - 10)
    )

    response = client.post(
        "/location/batch",
        headers={"x-token": TOKEN},
        json=batch_body(
            location_body(NOW - 21_601, lat=88.123456),
            location_body(NOW, lat=37.8),
        ),
    )

    assert response.status_code == 200
    assert response.json() == {
        "accepted": 0,
        "duplicates": 0,
        "rejected": 2,
        "rejections": [
            {"index": 0, "reason": "timestamp_too_old"},
            {"index": 1, "reason": "implausible_speed"},
        ],
    }
    assert "88.123456" not in response.text
    assert len(database.locations) == 1


def test_batch_with_51_points_and_extra_fields_is_rejected_without_echo(api):
    client, _, _ = api
    too_many = client.post(
        "/location/batch",
        headers={"x-token": TOKEN},
        json=batch_body(*(location_body(NOW + index * 3) for index in range(51))),
    )
    extra_field = client.post(
        "/location/batch",
        headers={"x-token": TOKEN},
        json={"points": [location_body(extra_secret_value=987654321)]},
    )

    assert too_many.status_code == 422
    assert too_many.json() == {"detail": {"reason": "invalid_request"}}
    assert extra_field.status_code == 422
    assert extra_field.json() == {"detail": {"reason": "invalid_request"}}
    assert "987654321" not in extra_field.text


def test_batch_rejects_raw_body_above_64_kib(api):
    client, _, _ = api
    response = client.post(
        "/location/batch",
        headers={"x-token": TOKEN},
        content=b" " * (64 * 1024 + 1),
    )

    assert response.status_code == 413
    assert response.json() == {"detail": {"reason": "request_too_large"}}


@pytest.mark.parametrize("active,headers", [(False, {"x-token": TOKEN}), (True, {})])
def test_inactive_or_missing_driver_token_returns_401(api, active, headers):
    client, database, _ = api
    database.driver.active = active

    response = client.post("/location", headers=headers, json=location_body())

    assert response.status_code == 401
    assert database.locations == []


def test_broadcast_only_sends_to_matching_center():
    async def check():
        center_id = uuid.uuid4()
        other_center_id = uuid.uuid4()
        same_center_socket = AsyncMock()
        other_center_socket = AsyncMock()
        main.clients.clear()
        main.clients[same_center_socket] = center_id
        main.clients[other_center_socket] = other_center_id
        try:
            await main.broadcast({"type": "location"}, center_id)
        finally:
            main.clients.clear()
        same_center_socket.send_json.assert_awaited_once_with(
            {"type": "location"}
        )
        other_center_socket.send_json.assert_not_awaited()

    asyncio.run(check())
