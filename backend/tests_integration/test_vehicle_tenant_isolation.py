import asyncio
import uuid
from dataclasses import dataclass
from typing import Protocol, TypedDict

from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
import pytest

import main
from app.db import get_db
from app.models import Admin, Center, Driver, Vehicle


PASSWORD = "integration-test-password"
CONFLICT_DETAIL = "Vehicle number or plate already in use in your center"
pytestmark = pytest.mark.integration


class IntegrationDatabase(Protocol):
    session_factory: async_sessionmaker[AsyncSession]


class CreatedDriver(TypedDict):
    id: str
    name: str
    token: str
    vehicle: dict[str, str | None]


@dataclass(frozen=True)
class CenterAdmin:
    center_id: uuid.UUID
    email: str
    password: str


@dataclass(frozen=True)
class AdminPair:
    center_a: CenterAdmin
    center_b: CenterAdmin


async def _create_admin_pair(database: IntegrationDatabase) -> AdminPair:
    async with database.session_factory() as session:
        center_a = Center(name=f"Integration A {uuid.uuid4()}", city="Test")
        center_b = Center(name=f"Integration B {uuid.uuid4()}", city="Test")
        session.add_all([center_a, center_b])
        await session.flush()

        admin_a = CenterAdmin(
            center_id=center_a.id,
            email=f"{uuid.uuid4().hex}@example.test",
            password=PASSWORD,
        )
        admin_b = CenterAdmin(
            center_id=center_b.id,
            email=f"{uuid.uuid4().hex}@example.test",
            password=PASSWORD,
        )
        password_hasher = PasswordHasher()
        session.add_all(
            [
                Admin(
                    center_id=admin_a.center_id,
                    email=admin_a.email,
                    password_hash=password_hasher.hash(admin_a.password),
                    active=True,
                ),
                Admin(
                    center_id=admin_b.center_id,
                    email=admin_b.email,
                    password_hash=password_hasher.hash(admin_b.password),
                    active=True,
                ),
            ]
        )
        await session.commit()
    return AdminPair(center_a=admin_a, center_b=admin_b)


async def _driver_and_vehicle_centers(
    database: IntegrationDatabase,
    driver_id: uuid.UUID,
) -> tuple[uuid.UUID, uuid.UUID]:
    async with database.session_factory() as session:
        result = await session.execute(
            select(Driver.center_id, Vehicle.center_id)
            .join(Vehicle, Vehicle.driver_id == Driver.id)
            .where(Driver.id == driver_id)
        )
        return result.one()


@pytest.fixture
def admin_pair(integration_database: IntegrationDatabase) -> AdminPair:
    return asyncio.run(_create_admin_pair(integration_database))


@pytest.fixture
def api_client(integration_database: IntegrationDatabase):
    async def override_get_db():
        async with integration_database.session_factory() as session:
            yield session

    main.app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(main.app, base_url="https://testserver") as client:
            yield client
    finally:
        main.app.dependency_overrides.pop(get_db, None)
        main.clients.clear()


def _login(client: TestClient, admin: CenterAdmin) -> None:
    response = client.post(
        "/admin/login",
        json={"email": admin.email, "password": admin.password},
    )
    assert response.status_code == 200


def _create_driver(
    client: TestClient,
    *,
    name: str,
    taxi_number: str,
    plate_number: str,
) -> CreatedDriver:
    response = client.post(
        "/admin/drivers",
        json={
            "name": name,
            "phone": "55500001",
            "vehicle": {
                "taxi_number": taxi_number,
                "plate_number": plate_number,
                "type": "Sedan",
            },
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_vehicle_numbers_are_unique_within_center_only(
    integration_database: IntegrationDatabase,
    admin_pair: AdminPair,
    api_client: TestClient,
):
    _login(api_client, admin_pair.center_a)
    driver_a = _create_driver(
        api_client,
        name="Center A driver",
        taxi_number="SHARED-TAXI",
        plate_number="SHARED-PLATE",
    )
    driver_a_id = uuid.UUID(driver_a["id"])
    assert asyncio.run(
        _driver_and_vehicle_centers(integration_database, driver_a_id)
    ) == (admin_pair.center_a.center_id, admin_pair.center_a.center_id)

    _login(api_client, admin_pair.center_b)
    _create_driver(
        api_client,
        name="Center B driver",
        taxi_number="SHARED-TAXI",
        plate_number="SHARED-PLATE",
    )

    _login(api_client, admin_pair.center_a)
    patch_target = _create_driver(
        api_client,
        name="Patch target",
        taxi_number="PATCH-TAXI",
        plate_number="PATCH-PLATE",
    )
    duplicate_taxi = api_client.post(
        "/admin/drivers",
        json={
            "name": "Duplicate taxi",
            "phone": "55500002",
            "vehicle": {
                "taxi_number": "SHARED-TAXI",
                "plate_number": "OTHER-PLATE",
            },
        },
    )
    duplicate_plate = api_client.post(
        "/admin/drivers",
        json={
            "name": "Duplicate plate",
            "phone": "55500003",
            "vehicle": {
                "taxi_number": "OTHER-TAXI",
                "plate_number": "SHARED-PLATE",
            },
        },
    )
    duplicate_patch = api_client.patch(
        f"/admin/drivers/{patch_target['id']}",
        json={"vehicle": {"taxi_number": "SHARED-TAXI"}},
    )

    assert duplicate_taxi.status_code == 409
    assert duplicate_taxi.json()["detail"] == CONFLICT_DETAIL
    assert duplicate_plate.status_code == 409
    assert duplicate_plate.json()["detail"] == CONFLICT_DETAIL
    assert duplicate_patch.status_code == 409
    assert duplicate_patch.json()["detail"] == CONFLICT_DETAIL
    assert "Center B" not in duplicate_taxi.text
    assert "Center B" not in duplicate_plate.text
    assert "Center B" not in duplicate_patch.text


def test_center_admin_cannot_access_or_create_for_another_center(
    integration_database: IntegrationDatabase,
    admin_pair: AdminPair,
    api_client: TestClient,
):
    _login(api_client, admin_pair.center_a)
    driver_a = _create_driver(
        api_client,
        name="Visible A",
        taxi_number="A-TAXI",
        plate_number="A-PLATE",
    )
    _login(api_client, admin_pair.center_b)
    driver_b = _create_driver(
        api_client,
        name="Hidden B",
        taxi_number="B-TAXI",
        plate_number="B-PLATE",
    )

    _login(api_client, admin_pair.center_a)
    latest = api_client.get("/admin/drivers/latest")
    assert latest.status_code == 200
    assert [driver["name"] for driver in latest.json()] == ["Visible A"]

    driver_b_id = driver_b["id"]
    requests = (
        ("patch", f"/admin/drivers/{driver_b_id}", {"name": "Changed"}),
        ("post", f"/admin/drivers/{driver_b_id}/deactivate", None),
        ("post", f"/admin/drivers/{driver_b_id}/reactivate", None),
        ("post", f"/admin/drivers/{driver_b_id}/token", None),
    )
    for method, path, body in requests:
        response = api_client.request(method, path, json=body)
        assert response.status_code == 404
        assert response.json()["detail"] == "Driver not found"

    forged_create = api_client.post(
        "/admin/drivers",
        json={
            "name": "Attempted B driver",
            "phone": "55500004",
            "center_id": str(admin_pair.center_b.center_id),
            "vehicle": {
                "taxi_number": "FORGED-TAXI",
                "plate_number": "FORGED-PLATE",
            },
        },
    )
    assert forged_create.status_code == 422
    assert [driver["name"] for driver in api_client.get(
        "/admin/drivers/latest"
    ).json()] == ["Visible A"]

    assert asyncio.run(
        _driver_and_vehicle_centers(
            integration_database,
            uuid.UUID(driver_a["id"]),
        )
    ) == (admin_pair.center_a.center_id, admin_pair.center_a.center_id)


def test_deactivated_driver_token_is_rejected(
    admin_pair: AdminPair,
    api_client: TestClient,
):
    _login(api_client, admin_pair.center_a)
    driver = _create_driver(
        api_client,
        name="To deactivate",
        taxi_number="DEACTIVATE-TAXI",
        plate_number="DEACTIVATE-PLATE",
    )
    deactivated = api_client.post(f"/admin/drivers/{driver['id']}/deactivate")
    assert deactivated.status_code == 200

    status = api_client.post(
        "/status",
        headers={"X-Token": driver["token"]},
        json={"online": True},
    )
    assert status.status_code == 401
