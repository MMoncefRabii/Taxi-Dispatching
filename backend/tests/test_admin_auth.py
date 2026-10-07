import asyncio
import hashlib
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://fleet_tracker:password@localhost:5432/fleet_tracker",
)

import scripts.deactivate_admin as deactivate_admin_script
import scripts.seed_admin as seed_admin_script
import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import main
from app.config import Settings, settings
from app.db import get_db
from app.models import Admin, AdminSession, Driver, DriverLocation


@pytest.fixture
def mock_db():
    db = Mock()
    db.execute = AsyncMock(
        return_value=Mock(
            scalar_one_or_none=Mock(return_value=None),
            all=Mock(return_value=[]),
        )
    )
    db.add = Mock()
    db.commit = AsyncMock()
    main.app.dependency_overrides[get_db] = lambda: db
    main.clients.clear()
    yield db
    main.app.dependency_overrides.clear()
    main.clients.clear()


def set_app_env(monkeypatch, app_env: str) -> None:
    monkeypatch.setattr(settings, "app_env", app_env)


def use_admin_dependency(admin: Admin) -> None:
    main.app.dependency_overrides[main.require_admin] = lambda: admin


def scalar_result(value):
    return Mock(
        scalar_one_or_none=Mock(return_value=value),
        all=Mock(return_value=[]),
    )


class FakeAsyncContext:
    def __init__(self):
        self.exception = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        self.exception = exc_value


class FakeSession(FakeAsyncContext):
    def __init__(self, execute_results=(), scalar_result_value=None):
        super().__init__()
        self.execute = AsyncMock(side_effect=execute_results)
        self.scalar = AsyncMock(return_value=scalar_result_value)
        self.transaction = FakeAsyncContext()
        self.begin = Mock(return_value=self.transaction)


def make_admin(password: str = "correct horse battery staple") -> Admin:
    return Admin(
        id=uuid.uuid4(),
        center_id=uuid.uuid4(),
        email="admin@example.com",
        password_hash=PasswordHasher().hash(password),
        active=True,
    )


def make_admin_session(admin: Admin, token: str) -> AdminSession:
    return AdminSession(
        id=uuid.uuid4(),
        admin_id=admin.id,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )


def test_missing_or_invalid_environment_defaults_to_production(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://fleet_tracker:password@localhost:5432/fleet_tracker",
    )
    monkeypatch.setenv("APP_ENV", "invalid")

    loaded_settings = Settings()

    assert loaded_settings.app_env == "production"


@pytest.mark.parametrize(
    ("method", "path", "json"),
    [
        ("get", "/admin/drivers/latest", None),
        ("post", "/admin/drivers", {"name": "Test Driver", "phone": "55500001"}),
        ("get", "/admin/me", None),
    ],
)
@pytest.mark.usefixtures("mock_db")
def test_admin_routes_require_session(monkeypatch, method, path, json):
    set_app_env(monkeypatch, "development")

    with TestClient(main.app) as client:
        response = client.request(method, path, json=json)

    assert response.status_code == 401


@pytest.mark.usefixtures("mock_db")
def test_latest_positions_applies_limit_in_sql(monkeypatch, mock_db):
    set_app_env(monkeypatch, "development")
    use_admin_dependency(make_admin())

    with TestClient(main.app) as client:
        response = client.get("/admin/drivers/latest?limit=1")

    assert response.status_code == 200
    query = mock_db.execute.await_args.args[0]
    assert query._limit_clause.value == 1
    assert "ORDER BY drivers.name, drivers.id" in str(query.compile())
    assert len(response.json()) <= 1


@pytest.mark.parametrize("limit", [0, 1001, 5000])
@pytest.mark.usefixtures("mock_db")
def test_latest_positions_rejects_out_of_range_limit(monkeypatch, mock_db, limit):
    set_app_env(monkeypatch, "development")
    use_admin_dependency(make_admin())

    with TestClient(main.app) as client:
        response = client.get(f"/admin/drivers/latest?limit={limit}")

    assert response.status_code == 422
    mock_db.execute.assert_not_awaited()


@pytest.mark.usefixtures("mock_db")
def test_latest_positions_defaults_to_500_limit(monkeypatch, mock_db):
    set_app_env(monkeypatch, "development")
    use_admin_dependency(make_admin())

    with TestClient(main.app) as client:
        response = client.get("/admin/drivers/latest")

    assert response.status_code == 200
    query = mock_db.execute.await_args.args[0]
    assert query._limit_clause.value == 500
    assert response.json() == []


@pytest.mark.parametrize(
    ("app_env", "secure_cookie"),
    [("development", False), ("production", True)],
)
@pytest.mark.usefixtures("mock_db")
def test_admin_login_creates_hashed_eight_hour_session(
    monkeypatch, mock_db, app_env, secure_cookie
):
    set_app_env(monkeypatch, app_env)
    admin = make_admin()
    mock_db.execute.return_value = scalar_result(admin)

    with TestClient(main.app) as client:
        response = client.post(
            "/admin/login",
            json={"email": "ADMIN@example.com", "password": "correct horse battery staple"},
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert "admin_session=" in response.headers["set-cookie"]
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=strict" in response.headers["set-cookie"].lower()
    assert ("secure" in response.headers["set-cookie"].lower()) is secure_cookie
    created_session = mock_db.add.call_args.args[0]
    token = response.cookies.get(main.ADMIN_SESSION_COOKIE)
    assert isinstance(created_session, AdminSession)
    assert created_session.admin_id == admin.id
    assert created_session.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert created_session.created_at.tzinfo == timezone.utc
    assert created_session.expires_at - created_session.created_at == timedelta(hours=8)


@pytest.mark.usefixtures("mock_db")
def test_wrong_password_and_unknown_email_share_same_401(monkeypatch, mock_db):
    set_app_env(monkeypatch, "development")
    mock_db.execute.side_effect = [
        scalar_result(make_admin()),
        scalar_result(None),
    ]
    verify_password = Mock(wraps=main._verify_password)
    monkeypatch.setattr(main, "_verify_password", verify_password)

    with TestClient(main.app) as client:
        wrong_password = client.post(
            "/admin/login",
            json={"email": "admin@example.com", "password": "wrong password"},
        )
        unknown_email = client.post(
            "/admin/login",
            json={"email": "unknown@example.com", "password": "wrong password"},
        )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert wrong_password.json()["detail"] == "Invalid email or password"
    assert mock_db.execute.await_count == 2
    assert verify_password.call_count == 2


@pytest.mark.usefixtures("mock_db")
def test_inactive_admin_login_uses_generic_401(monkeypatch, mock_db):
    set_app_env(monkeypatch, "development")
    admin = make_admin()
    admin.active = False
    mock_db.execute.return_value = scalar_result(admin)

    with TestClient(main.app) as client:
        response = client.post(
            "/admin/login",
            json={
                "email": "admin@example.com",
                "password": "correct horse battery staple",
            },
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"
    mock_db.add.assert_not_called()
    mock_db.commit.assert_not_awaited()


@pytest.mark.usefixtures("mock_db")
def test_login_rejects_extra_fields_and_oversized_password(monkeypatch, mock_db):
    set_app_env(monkeypatch, "development")

    with TestClient(main.app) as client:
        extra_field = client.post(
            "/admin/login",
            json={
                "email": "admin@example.com",
                "password": "correct horse battery staple",
                "role": "admin",
            },
        )
        oversized_password = client.post(
            "/admin/login",
            json={"email": "admin@example.com", "password": "x" * 129},
        )

    assert extra_field.status_code == 422
    assert oversized_password.status_code == 422
    mock_db.execute.assert_not_awaited()


@pytest.mark.parametrize("session_state", ["expired", "revoked"])
@pytest.mark.usefixtures("mock_db")
def test_expired_and_revoked_sessions_are_rejected(
    monkeypatch, mock_db, session_state
):
    set_app_env(monkeypatch, "development")
    token = "session-token"
    now = datetime.now(timezone.utc)
    admin_session = AdminSession(
        id=uuid.uuid4(),
        admin_id=uuid.uuid4(),
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=now - timedelta(minutes=1)
        if session_state == "expired"
        else now + timedelta(hours=1),
        revoked_at=now if session_state == "revoked" else None,
    )
    mock_db.execute.return_value = scalar_result(admin_session)

    with TestClient(main.app) as client:
        client.cookies.set(main.ADMIN_SESSION_COOKIE, token)
        response = client.get("/admin/drivers/latest")

    assert response.status_code == 401
    assert mock_db.execute.await_count == 1


@pytest.mark.usefixtures("mock_db")
def test_inactive_admin_session_is_rejected(monkeypatch, mock_db):
    set_app_env(monkeypatch, "development")
    token = "session-token"
    admin_session = AdminSession(
        id=uuid.uuid4(),
        admin_id=uuid.uuid4(),
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    mock_db.execute.side_effect = [
        scalar_result(admin_session),
        scalar_result(None),
    ]

    with TestClient(main.app) as client:
        client.cookies.set(main.ADMIN_SESSION_COOKIE, token)
        response = client.get("/admin/drivers/latest")

    assert response.status_code == 401
    assert mock_db.execute.await_count == 2
    admin_query = mock_db.execute.await_args_list[1].args[0]
    assert "admins.active IS true" in str(admin_query.compile())


@pytest.mark.usefixtures("mock_db")
def test_logout_revokes_session_and_clears_cookie(monkeypatch, mock_db):
    set_app_env(monkeypatch, "development")
    token = "session-token"
    admin_session = AdminSession(
        id=uuid.uuid4(),
        admin_id=uuid.uuid4(),
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    mock_db.execute.return_value = scalar_result(admin_session)

    with TestClient(main.app) as client:
        client.cookies.set(main.ADMIN_SESSION_COOKIE, token)
        response = client.post("/admin/logout")

    assert response.status_code == 204
    assert admin_session.revoked_at is not None
    assert admin_session.revoked_at.tzinfo == timezone.utc
    assert "admin_session=" in response.headers["set-cookie"]
    assert "max-age=0" in response.headers["set-cookie"].lower()
    mock_db.commit.assert_awaited_once()


def test_deactivate_admin_updates_admin_and_revokes_sessions(monkeypatch, capsys):
    admin = make_admin()
    session = FakeSession(
        execute_results=[
            scalar_result(admin),
            Mock(),
            Mock(),
        ],
        scalar_result_value=2,
    )
    monkeypatch.setattr(deactivate_admin_script, "SessionLocal", lambda: session)
    monkeypatch.setattr(
        deactivate_admin_script,
        "engine",
        Mock(dispose=AsyncMock()),
    )
    before = datetime.now(timezone.utc)

    changed = asyncio.run(
        deactivate_admin_script.deactivate_and_dispose(admin.email)
    )

    after = datetime.now(timezone.utc)
    assert changed is True
    assert admin.active is False
    assert before <= admin.deactivated_at <= after
    assert admin.deactivated_at.tzinfo == timezone.utc
    assert session.begin.call_count == 1
    assert session.transaction.exception is None
    assert session.execute.await_count == 3
    assert session.scalar.await_count == 1
    revoke_query = session.execute.await_args_list[2].args[0]
    assert "UPDATE admin_sessions SET revoked_at" in str(revoke_query.compile())
    assert "admin_sessions.revoked_at IS NULL" in str(revoke_query.compile())
    assert "token_hash" not in str(revoke_query.compile())
    assert capsys.readouterr().out == ""


def test_deactivate_admin_already_inactive_makes_no_changes(monkeypatch, capsys):
    admin = make_admin()
    admin.active = False
    original_deactivated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    admin.deactivated_at = original_deactivated_at
    session = FakeSession(execute_results=[scalar_result(admin)])
    monkeypatch.setattr(deactivate_admin_script, "SessionLocal", lambda: session)
    monkeypatch.setattr(
        deactivate_admin_script,
        "engine",
        Mock(dispose=AsyncMock()),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["deactivate_admin", "--email", admin.email],
    )

    exit_code = deactivate_admin_script.main()

    assert exit_code == 0
    assert admin.active is False
    assert admin.deactivated_at is original_deactivated_at
    assert session.execute.await_count == 1
    session.scalar.assert_not_awaited()
    assert "Admin is already inactive; no changes made." in capsys.readouterr().out


def test_deactivate_admin_unknown_email_exits_with_code_one(
    monkeypatch, capsys
):
    session = FakeSession(execute_results=[scalar_result(None)])
    monkeypatch.setattr(deactivate_admin_script, "SessionLocal", lambda: session)
    monkeypatch.setattr(
        deactivate_admin_script,
        "engine",
        Mock(dispose=AsyncMock()),
    )
    monkeypatch.setattr(sys, "argv", ["deactivate_admin", "--email", "missing@example.com"])

    exit_code = deactivate_admin_script.main()

    assert exit_code == 1
    assert "No admin found for email missing@example.com." in capsys.readouterr().err
    assert session.transaction.exception is not None


def test_deactivate_admin_refuses_last_active_admin(monkeypatch):
    admin = make_admin()
    session = FakeSession(
        execute_results=[
            scalar_result(admin),
            Mock(),
        ],
        scalar_result_value=1,
    )
    monkeypatch.setattr(deactivate_admin_script, "SessionLocal", lambda: session)
    monkeypatch.setattr(
        deactivate_admin_script,
        "engine",
        Mock(dispose=AsyncMock()),
    )

    with pytest.raises(
        deactivate_admin_script.AdminDeactivationError,
        match="last active admin",
    ):
        asyncio.run(deactivate_admin_script.deactivate_and_dispose(admin.email))

    assert admin.active is True
    assert admin.deactivated_at is None
    assert session.execute.await_count == 2
    assert session.transaction.exception is not None


def test_seed_admin_existing_email_does_not_prompt(monkeypatch, capsys):
    session = FakeSession(execute_results=[scalar_result(make_admin())])
    monkeypatch.setattr(seed_admin_script, "SessionLocal", lambda: session)
    monkeypatch.setattr(
        seed_admin_script,
        "engine",
        Mock(dispose=AsyncMock()),
    )
    monkeypatch.setattr(
        seed_admin_script.getpass,
        "getpass",
        lambda *_args: pytest.fail("password prompt must not be shown"),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["seed_admin", "--email", "admin@example.com"],
    )

    seed_admin_script.main()

    assert session.execute.await_count == 1
    assert (
        capsys.readouterr().out.strip()
        == "Admin already exists; no changes made."
    )


@pytest.mark.usefixtures("mock_db")
def test_me_returns_admin_fields_without_password_hash(monkeypatch, mock_db):
    set_app_env(monkeypatch, "development")
    token = "session-token"
    admin = make_admin()
    admin_session = AdminSession(
        id=uuid.uuid4(),
        admin_id=admin.id,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    mock_db.execute.side_effect = [
        scalar_result(admin_session),
        scalar_result(admin),
    ]

    with TestClient(main.app) as client:
        client.cookies.set(main.ADMIN_SESSION_COOKIE, token)
        response = client.get("/admin/me")

    assert response.status_code == 200
    assert response.json() == {
        "email": "admin@example.com",
        "center_id": str(admin.center_id),
    }
    assert admin.password_hash not in response.text
    assert "password_hash" not in response.json()


@pytest.mark.usefixtures("mock_db")
def test_websocket_rejects_missing_session(monkeypatch):
    set_app_env(monkeypatch, "development")

    with TestClient(main.app) as client:
        with pytest.raises(WebSocketDisconnect) as disconnect:
            with client.websocket_connect("/ws"):
                pass

    assert disconnect.value.code == 1008


@pytest.mark.usefixtures("mock_db")
def test_websocket_accepts_valid_session_cookie(monkeypatch, mock_db):
    set_app_env(monkeypatch, "development")
    token = "session-token"
    admin = make_admin()
    admin_session = AdminSession(
        id=uuid.uuid4(),
        admin_id=admin.id,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    mock_db.execute.side_effect = [
        scalar_result(admin_session),
        scalar_result(admin),
    ]

    with TestClient(main.app) as client:
        client.cookies.set(main.ADMIN_SESSION_COOKIE, token)
        with client.websocket_connect(
            "/ws",
            headers={"origin": "http://testserver"},
        ):
            assert list(main.clients.values()) == [admin.center_id]

    assert mock_db.execute.await_count == 2


@pytest.mark.usefixtures("mock_db")
def test_websocket_rejects_wrong_origin(monkeypatch):
    set_app_env(monkeypatch, "development")

    with TestClient(main.app) as client:
        with pytest.raises(WebSocketDisconnect) as disconnect:
            with client.websocket_connect(
                "/ws",
                headers={"origin": "https://attacker.example"},
            ):
                pass

    assert disconnect.value.code == 1008


@pytest.mark.usefixtures("mock_db")
def test_admin_lists_only_drivers_in_session_center(monkeypatch, mock_db):
    set_app_env(monkeypatch, "development")
    token = "center-a-session"
    admin = make_admin()
    center_a = admin.center_id
    center_b = uuid.uuid4()
    driver_a = Driver(
        id=uuid.uuid4(),
        center_id=center_a,
        name="Center A Driver",
        phone="55500001",
        token_hash="driver-a-hash",
        online=False,
    )
    admin_session = make_admin_session(admin, token)
    mock_db.execute.side_effect = [
        scalar_result(admin_session),
        scalar_result(admin),
        Mock(all=Mock(return_value=[(driver_a, None, None, None, None, None, None)])),
    ]

    with TestClient(main.app) as client:
        client.cookies.set(main.ADMIN_SESSION_COOKIE, token)
        response = client.get("/admin/drivers/latest")

    assert response.status_code == 200
    assert [row["name"] for row in response.json()] == ["Center A Driver"]
    query = mock_db.execute.await_args_list[2].args[0]
    compiled = query.compile()
    assert "drivers.center_id" in str(compiled)
    assert "driver_locations.center_id" in str(compiled)
    assert center_a in compiled.params.values()
    assert center_b not in compiled.params.values()


@pytest.mark.usefixtures("mock_db")
def test_admin_creates_driver_in_session_center_not_body_center(monkeypatch, mock_db):
    set_app_env(monkeypatch, "development")
    token = "center-a-session"
    admin = make_admin()
    center_b = uuid.uuid4()
    mock_db.execute.side_effect = [
        scalar_result(make_admin_session(admin, token)),
        scalar_result(admin),
    ]

    with TestClient(main.app) as client:
        client.cookies.set(main.ADMIN_SESSION_COOKIE, token)
        response = client.post(
            "/admin/drivers",
            json={
                "name": "Center A Driver",
                "phone": "55500001",
                "center_id": str(center_b),
            },
        )

    assert response.status_code == 200
    created_driver = mock_db.add.call_args.args[0]
    assert isinstance(created_driver, Driver)
    assert created_driver.center_id == admin.center_id


@pytest.mark.usefixtures("mock_db")
def test_location_uses_driver_center_and_only_broadcasts_to_that_center(
    monkeypatch, mock_db
):
    set_app_env(monkeypatch, "development")
    center_a = uuid.uuid4()
    center_b = uuid.uuid4()
    driver = Driver(
        id=uuid.uuid4(),
        center_id=center_a,
        name="Center A Driver",
        phone="55500001",
        token_hash=hashlib.sha256(b"driver-token").hexdigest(),
        active=True,
        online=True,
    )
    mock_db.execute.return_value = scalar_result(driver)
    center_a_client = Mock()
    center_a_client.send_json = AsyncMock()
    center_b_client = Mock()
    center_b_client.send_json = AsyncMock()
    main.clients[center_a_client] = center_a
    main.clients[center_b_client] = center_b

    with TestClient(main.app) as client:
        response = client.post(
            "/location",
            headers={"X-Token": "driver-token"},
            json={
                "lat": 36.8,
                "lng": 10.2,
                "center_id": str(center_b),
            },
        )

    assert response.status_code == 200
    saved_location = mock_db.add.call_args.args[0]
    assert isinstance(saved_location, DriverLocation)
    assert saved_location.center_id == center_a
    center_a_client.send_json.assert_awaited_once()
    center_b_client.send_json.assert_not_awaited()
    assert center_a_client.send_json.await_args.args[0]["type"] == "location"


@pytest.mark.usefixtures("mock_db")
def test_status_uses_driver_center_for_broadcast(monkeypatch, mock_db):
    set_app_env(monkeypatch, "development")
    center_a = uuid.uuid4()
    center_b = uuid.uuid4()
    driver = Driver(
        id=uuid.uuid4(),
        center_id=center_a,
        name="Center A Driver",
        phone="55500001",
        token_hash=hashlib.sha256(b"driver-token").hexdigest(),
        active=True,
        online=True,
    )
    mock_db.execute.return_value = scalar_result(driver)
    center_a_client = Mock()
    center_a_client.send_json = AsyncMock()
    center_b_client = Mock()
    center_b_client.send_json = AsyncMock()
    main.clients[center_a_client] = center_a
    main.clients[center_b_client] = center_b

    with TestClient(main.app) as client:
        response = client.post(
            "/status",
            headers={"X-Token": "driver-token"},
            json={"online": False, "center_id": str(center_b)},
        )

    assert response.status_code == 200
    center_a_client.send_json.assert_awaited_once()
    center_b_client.send_json.assert_not_awaited()
    assert center_a_client.send_json.await_args.args[0]["type"] == "status"
