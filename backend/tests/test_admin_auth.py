import hashlib
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://fleet_tracker:password@localhost:5432/fleet_tracker",
)

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import main
from app.config import Settings, settings
from app.db import get_db
from app.models import Admin, AdminSession


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
    yield db
    main.app.dependency_overrides.clear()


def set_auth_mode(monkeypatch, *, app_env: str, disabled: bool) -> None:
    monkeypatch.setattr(settings, "app_env", app_env)
    monkeypatch.setattr(settings, "dev_disable_admin_auth", disabled)


def scalar_result(value):
    return Mock(
        scalar_one_or_none=Mock(return_value=value),
        all=Mock(return_value=[]),
    )


def make_admin(password: str = "correct horse battery staple") -> Admin:
    return Admin(
        id=uuid.uuid4(),
        center_id=uuid.uuid4(),
        email="admin@example.com",
        password_hash=PasswordHasher().hash(password),
        active=True,
    )


def test_missing_or_invalid_environment_defaults_to_production(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://fleet_tracker:password@localhost:5432/fleet_tracker",
    )
    monkeypatch.setenv("APP_ENV", "invalid")
    monkeypatch.delenv("DEV_DISABLE_ADMIN_AUTH", raising=False)

    loaded_settings = Settings()

    assert loaded_settings.app_env == "production"
    assert loaded_settings.dev_disable_admin_auth is False


@pytest.mark.parametrize(
    ("method", "path", "json"),
    [
        ("get", "/admin/drivers/latest", None),
        ("post", "/admin/drivers", {"name": "Test Driver", "phone": "55500001"}),
        ("get", "/admin/me", None),
    ],
)
@pytest.mark.usefixtures("mock_db")
def test_admin_routes_require_session_when_flag_is_off(
    monkeypatch, method, path, json
):
    set_auth_mode(monkeypatch, app_env="development", disabled=False)

    with TestClient(main.app) as client:
        response = client.request(method, path, json=json)

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("method", "path", "json"),
    [
        ("get", "/admin/drivers/latest", None),
        ("post", "/admin/drivers", {"name": "Test Driver", "phone": "55500001"}),
    ],
)
@pytest.mark.usefixtures("mock_db")
def test_admin_routes_accept_missing_session_in_development(
    monkeypatch, method, path, json
):
    set_auth_mode(monkeypatch, app_env="development", disabled=True)

    with TestClient(main.app) as client:
        response = client.request(method, path, json=json)

    assert response.status_code == 200


@pytest.mark.usefixtures("mock_db")
def test_websocket_accepts_missing_session_in_development(monkeypatch):
    set_auth_mode(monkeypatch, app_env="development", disabled=True)

    with TestClient(main.app) as client:
        with client.websocket_connect(
            "/ws",
            headers={"origin": "http://testserver"},
        ):
            pass


@pytest.mark.usefixtures("mock_db")
def test_disabled_admin_auth_logs_warning(monkeypatch, caplog):
    set_auth_mode(monkeypatch, app_env="development", disabled=True)

    with caplog.at_level(logging.WARNING):
        with TestClient(main.app):
            pass

    assert "ADMIN AUTH DISABLED (DEV MODE)" in caplog.text


@pytest.mark.usefixtures("mock_db")
def test_app_refuses_to_start_when_admin_auth_is_disabled_in_production(monkeypatch):
    set_auth_mode(monkeypatch, app_env="production", disabled=True)

    with pytest.raises(RuntimeError, match="APP_ENV=production"):
        with TestClient(main.app):
            pass


@pytest.mark.usefixtures("mock_db")
def test_dev_admin_me_reports_bypass(monkeypatch):
    set_auth_mode(monkeypatch, app_env="development", disabled=True)

    with TestClient(main.app) as client:
        response = client.get("/admin/me")

    assert response.status_code == 200
    assert response.json() == {
        "email": None,
        "center_id": None,
        "dev_mode": True,
    }


@pytest.mark.usefixtures("mock_db")
def test_latest_positions_applies_limit_in_sql(monkeypatch, mock_db):
    set_auth_mode(monkeypatch, app_env="development", disabled=True)

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
    set_auth_mode(monkeypatch, app_env="development", disabled=True)

    with TestClient(main.app) as client:
        response = client.get(f"/admin/drivers/latest?limit={limit}")

    assert response.status_code == 422
    mock_db.execute.assert_not_awaited()


@pytest.mark.usefixtures("mock_db")
def test_latest_positions_defaults_to_500_limit(monkeypatch, mock_db):
    set_auth_mode(monkeypatch, app_env="development", disabled=True)

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
    set_auth_mode(monkeypatch, app_env=app_env, disabled=False)
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
    set_auth_mode(monkeypatch, app_env="development", disabled=False)
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
def test_login_rejects_extra_fields_and_oversized_password(monkeypatch, mock_db):
    set_auth_mode(monkeypatch, app_env="development", disabled=False)

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
    set_auth_mode(monkeypatch, app_env="development", disabled=False)
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
    set_auth_mode(monkeypatch, app_env="development", disabled=False)
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


@pytest.mark.usefixtures("mock_db")
def test_logout_revokes_session_and_clears_cookie(monkeypatch, mock_db):
    set_auth_mode(monkeypatch, app_env="development", disabled=False)
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


@pytest.mark.usefixtures("mock_db")
def test_me_returns_admin_fields_without_password_hash(monkeypatch, mock_db):
    set_auth_mode(monkeypatch, app_env="development", disabled=False)
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
        "dev_mode": False,
    }
    assert admin.password_hash not in response.text
    assert "password_hash" not in response.json()


@pytest.mark.usefixtures("mock_db")
def test_websocket_rejects_missing_session(monkeypatch):
    set_auth_mode(monkeypatch, app_env="development", disabled=False)

    with TestClient(main.app) as client:
        with pytest.raises(WebSocketDisconnect) as disconnect:
            with client.websocket_connect("/ws"):
                pass

    assert disconnect.value.code == 1008


@pytest.mark.usefixtures("mock_db")
def test_websocket_accepts_valid_session_cookie(monkeypatch, mock_db):
    set_auth_mode(monkeypatch, app_env="development", disabled=False)
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
            pass

    assert mock_db.execute.await_count == 2


@pytest.mark.usefixtures("mock_db")
def test_websocket_rejects_wrong_origin(monkeypatch):
    set_auth_mode(monkeypatch, app_env="development", disabled=False)

    with TestClient(main.app) as client:
        with pytest.raises(WebSocketDisconnect) as disconnect:
            with client.websocket_connect(
                "/ws",
                headers={"origin": "https://attacker.example"},
            ):
                pass

    assert disconnect.value.code == 1008
