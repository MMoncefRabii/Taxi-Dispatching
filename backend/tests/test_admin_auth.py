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
from sqlalchemy.exc import IntegrityError

import main
from app.config import Settings, settings
from app.db import get_db
from app.models import Admin, AdminSession, AuditLog, Driver, DriverLocation, Vehicle


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
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
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


def test_frontend_origin_gets_credentialed_cors_access():
    with TestClient(main.app) as client:
        response = client.options(
            "/admin/me",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_frontend_origin_gets_patch_cors_access():
    with TestClient(main.app) as client:
        response = client.options(
            "/admin/drivers/00000000-0000-0000-0000-000000000001",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "PATCH",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code == 200
    assert "PATCH" in response.headers["access-control-allow-methods"]


def test_unconfigured_origin_does_not_get_cors_access():
    with TestClient(main.app) as client:
        response = client.options(
            "/admin/me",
            headers={
                "Origin": "https://attacker.example",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize(
    ("method", "path", "json"),
    [
        ("get", "/admin/drivers/latest", None),
        (
            "post",
            "/admin/drivers",
            {
                "name": "Test Driver",
                "phone": "55500001",
                "vehicle": {
                    "taxi_number": "TX-1",
                    "plate_number": "AB 123",
                    "type": "Sedan",
                },
            },
        ),
        (
            "patch",
            "/admin/drivers/00000000-0000-0000-0000-000000000001",
            {"name": "Edited"},
        ),
        (
            "post",
            "/admin/drivers/00000000-0000-0000-0000-000000000001/deactivate",
            None,
        ),
        (
            "post",
            "/admin/drivers/00000000-0000-0000-0000-000000000001/reactivate",
            None,
        ),
        (
            "post",
            "/admin/drivers/00000000-0000-0000-0000-000000000001/token",
            None,
        ),
        ("get", "/admin/me", None),
        ("get", "/admin/admins", None),
        (
            "post",
            "/admin/admins/00000000-0000-0000-0000-000000000001/deactivate",
            None,
        ),
    ],
)
@pytest.mark.usefixtures("mock_db")
def test_admin_routes_require_session(monkeypatch, method, path, json):
    set_app_env(monkeypatch, "development")

    with TestClient(main.app) as client:
        response = client.request(method, path, json=json)

    assert response.status_code == 401


@pytest.mark.usefixtures("mock_db")
def test_list_admins_is_center_scoped_and_returns_only_safe_fields(
    monkeypatch, mock_db
):
    set_app_env(monkeypatch, "development")
    admin = make_admin()
    use_admin_dependency(admin)
    row = make_admin()
    row.center_id = admin.center_id
    row.created_at = datetime.now(timezone.utc)
    row.last_login = None
    row.deactivated_at = None
    mock_db.execute.return_value.scalars.return_value.all.return_value = [row]

    with TestClient(main.app) as client:
        response = client.get("/admin/admins?limit=7&offset=3")

    assert response.status_code == 200
    assert response.json() == [{
        "id": str(row.id),
        "email": row.email,
        "active": row.active,
        "created_at": row.created_at.isoformat(),
        "last_login": None,
        "deactivated_at": None,
        "is_self": False,
    }]
    query = mock_db.execute.await_args.args[0]
    compiled = query.compile()
    assert "admins.center_id =" in str(compiled)
    assert str(admin.center_id) in str(compiled.params.values())
    assert query._limit_clause.value == 7
    assert query._offset_clause.value == 3
    assert "password_hash" not in response.text
    assert "session" not in response.text


@pytest.mark.parametrize("limit", [0, 201, 500])
@pytest.mark.usefixtures("mock_db")
def test_list_admins_rejects_out_of_range_limit(monkeypatch, mock_db, limit):
    set_app_env(monkeypatch, "development")
    use_admin_dependency(make_admin())

    with TestClient(main.app) as client:
        response = client.get(f"/admin/admins?limit={limit}")

    assert response.status_code == 422
    mock_db.execute.assert_not_awaited()


@pytest.mark.usefixtures("mock_db")
def test_list_admins_defaults_to_fifty(monkeypatch, mock_db):
    set_app_env(monkeypatch, "development")
    use_admin_dependency(make_admin())
    mock_db.execute.return_value.scalars.return_value.all.return_value = []

    with TestClient(main.app) as client:
        response = client.get("/admin/admins")

    assert response.status_code == 200
    assert mock_db.execute.await_args.args[0]._limit_clause.value == 50


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (main.AdminNotFoundError(), 404),
        (main.SelfDeactivationError(), 409),
        (main.LastActiveAdminError(), 409),
    ],
)
@pytest.mark.usefixtures("mock_db")
def test_deactivate_admin_returns_generic_scoped_errors(
    monkeypatch, mock_db, error, status
):
    set_app_env(monkeypatch, "development")
    admin = make_admin()
    use_admin_dependency(admin)
    target_id = uuid.uuid4()
    helper = AsyncMock(side_effect=error)
    monkeypatch.setattr(main, "deactivate_admin_in_transaction", helper)

    with TestClient(main.app) as client:
        response = client.post(f"/admin/admins/{target_id}/deactivate")

    assert response.status_code == status
    assert response.json()["detail"] in {
        "Admin not found",
        "Unable to deactivate admin",
    }
    assert str(target_id) not in response.text
    helper.assert_awaited_once_with(
        mock_db,
        target_id,
        center_id=admin.center_id,
        actor_admin_id=admin.id,
    )
    mock_db.rollback.assert_awaited_once()
    mock_db.commit.assert_not_awaited()


@pytest.mark.usefixtures("mock_db")
def test_deactivate_admin_commits_success(monkeypatch, mock_db):
    set_app_env(monkeypatch, "development")
    admin = make_admin()
    use_admin_dependency(admin)
    target_id = uuid.uuid4()
    helper = AsyncMock(return_value=True)
    monkeypatch.setattr(main, "deactivate_admin_in_transaction", helper)

    with TestClient(main.app) as client:
        response = client.post(f"/admin/admins/{target_id}/deactivate")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "changed": True}
    mock_db.commit.assert_awaited_once()


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
    assert session.scalar.await_count == 2
    revoke_query = session.execute.await_args_list[2].args[0]
    assert "UPDATE admin_sessions SET revoked_at" in str(revoke_query.compile())
    assert "admin_sessions.revoked_at IS NULL" in str(revoke_query.compile())
    assert "token_hash" not in str(revoke_query.compile())
    assert capsys.readouterr().out == ""


def test_shared_admin_deactivation_revokes_sessions_and_audits_without_secrets():
    admin = make_admin()
    actor_id = uuid.uuid4()
    session = FakeSession(
        execute_results=[
            scalar_result(admin),
            Mock(),
            Mock(),
        ],
        scalar_result_value=2,
    )
    session.add = Mock()

    changed = asyncio.run(
        main.deactivate_admin_in_transaction(
            session,
            admin.id,
            center_id=admin.center_id,
            actor_admin_id=actor_id,
        )
    )

    assert changed is True
    assert admin.active is False
    assert admin.deactivated_at.tzinfo == timezone.utc
    assert session.execute.await_count == 3
    revoke_query = session.execute.await_args_list[2].args[0]
    assert "admin_sessions.revoked_at IS NULL" in str(revoke_query.compile())
    assert "token_hash" not in str(revoke_query.compile())
    audit = session.add.call_args.args[0]
    assert isinstance(audit, AuditLog)
    assert audit.actor_admin_id == actor_id
    assert audit.center_id == admin.center_id
    assert audit.action == "admin.deactivate"
    assert audit.before_state == {"active": True}
    assert audit.after_state == {"active": False}
    audit_values = repr((audit.before_state, audit.after_state))
    assert admin.email not in audit_values
    assert admin.password_hash not in audit_values


def test_shared_admin_deactivation_refuses_self():
    admin = make_admin()
    session = FakeSession(execute_results=[scalar_result(admin)])

    with pytest.raises(main.SelfDeactivationError):
        asyncio.run(
            main.deactivate_admin_in_transaction(
                session,
                admin.id,
                center_id=admin.center_id,
                actor_admin_id=admin.id,
            )
        )

    session.scalar.assert_not_awaited()
    assert session.execute.await_count == 1


def test_deactivate_admin_already_inactive_makes_no_changes(monkeypatch, capsys):
    admin = make_admin()
    admin.active = False
    original_deactivated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    admin.deactivated_at = original_deactivated_at
    session = FakeSession(
        execute_results=[scalar_result(admin)],
        scalar_result_value=admin.id,
    )
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
    session.scalar.assert_awaited_once()
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


@pytest.mark.parametrize("origin", ["http://testserver", "http://localhost:5173"])
@pytest.mark.usefixtures("mock_db")
def test_websocket_accepts_valid_session_cookie(monkeypatch, mock_db, origin):
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
            headers={"origin": origin},
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
def test_admin_lists_only_drivers_in_session_center(monkeypatch, mock_db, caplog):
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
        active=False,
        online=False,
        deactivated_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    admin_session = make_admin_session(admin, token)
    mock_db.execute.side_effect = [
        scalar_result(admin_session),
        scalar_result(admin),
        Mock(
            all=Mock(
                return_value=[
                    (
                        driver_a,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        "TX-A",
                        "AB 123",
                        "Sedan",
                    )
                ]
            )
        ),
    ]

    with TestClient(main.app) as client:
        client.cookies.set(main.ADMIN_SESSION_COOKIE, token)
        response = client.get("/admin/drivers/latest")

    assert response.status_code == 200
    assert [row["name"] for row in response.json()] == ["Center A Driver"]
    assert response.json()[0]["active"] is False
    assert response.json()[0]["deactivated_at"] == "2025-01-01T00:00:00+00:00"
    assert response.json()[0]["online"] == 0
    assert response.json()[0]["vehicle"] == {
        "taxi_number": "TX-A",
        "plate_number": "AB 123",
        "type": "Sedan",
    }
    assert "token_hash" not in response.text
    assert "driver-a-hash" not in response.text
    assert "driver-a-hash" not in caplog.text
    query = mock_db.execute.await_args_list[2].args[0]
    compiled = query.compile()
    assert "drivers.center_id" in str(compiled)
    assert "driver_locations.center_id" in str(compiled)
    assert center_a in compiled.params.values()
    assert center_b not in compiled.params.values()


@pytest.mark.usefixtures("mock_db")
def test_admin_creates_driver_in_session_center_not_body_center(
    monkeypatch, mock_db, caplog
):
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
                "vehicle": {
                    "taxi_number": "TX-A",
                    "plate_number": " ab 123 ",
                    "type": "Sedan",
                },
            },
        )

    assert response.status_code == 200
    created_driver = next(
        item
        for item in (call.args[0] for call in mock_db.add.call_args_list)
        if isinstance(item, Driver)
    )
    created_vehicle = next(
        item
        for item in (call.args[0] for call in mock_db.add.call_args_list)
        if isinstance(item, Vehicle)
    )
    audit_log = next(
        item
        for item in (call.args[0] for call in mock_db.add.call_args_list)
        if isinstance(item, AuditLog)
    )
    assert created_driver.center_id == admin.center_id
    assert created_vehicle.center_id == admin.center_id
    assert created_vehicle.driver_id == created_driver.id
    assert created_vehicle.plate_number == "AB 123"
    assert created_vehicle.type == "Sedan"
    assert response.json()["vehicle"]["plate_number"] == "AB 123"
    assert created_driver.center_id != center_b
    assert audit_log.center_id == admin.center_id
    assert audit_log.actor_admin_id == admin.id
    assert audit_log.action == "driver.create"
    assert audit_log.entity_id == created_driver.id
    assert "phone" not in (audit_log.after_state or {})
    assert "token" not in str(audit_log.after_state).lower()
    assert "token_hash" not in str(audit_log.after_state).lower()
    assert "token_hash" not in response.text
    assert response.json()["token"] not in caplog.text
    assert created_driver.token_hash not in caplog.text


def _new_driver_payload(**overrides):
    body = {
        "name": "Test Driver",
        "phone": "55500001",
        "vehicle": {
            "taxi_number": "TX-1",
            "plate_number": "AB 123",
            "type": "Sedan",
        },
    }
    body.update(overrides)
    return body


@pytest.mark.usefixtures("mock_db")
def test_create_driver_rejects_invalid_plate_and_extra_fields(
    monkeypatch, mock_db
):
    set_app_env(monkeypatch, "development")
    use_admin_dependency(make_admin())
    invalid_plate = _new_driver_payload()
    invalid_plate["vehicle"]["plate_number"] = "AB/123"
    extra_field = _new_driver_payload(center_id=str(uuid.uuid4()))

    with TestClient(main.app) as client:
        bad_plate_response = client.post("/admin/drivers", json=invalid_plate)
        extra_field_response = client.post("/admin/drivers", json=extra_field)

    assert bad_plate_response.status_code == 422
    assert extra_field_response.status_code == 422
    mock_db.add.assert_not_called()
    mock_db.flush.assert_not_awaited()


@pytest.mark.usefixtures("mock_db")
def test_create_driver_rolls_back_driver_when_vehicle_insert_fails(
    monkeypatch, mock_db
):
    set_app_env(monkeypatch, "development")
    use_admin_dependency(make_admin())
    mock_db.flush.side_effect = IntegrityError(
        "insert vehicle", {}, Exception("unique violation")
    )

    with TestClient(main.app) as client:
        response = client.post("/admin/drivers", json=_new_driver_payload())

    assert response.status_code == 409
    added = [call.args[0] for call in mock_db.add.call_args_list]
    assert any(isinstance(item, Driver) for item in added)
    assert any(isinstance(item, Vehicle) for item in added)
    assert any(isinstance(item, AuditLog) for item in added)
    mock_db.rollback.assert_awaited_once()
    mock_db.commit.assert_not_awaited()
    assert response.json()["detail"] == (
        "Vehicle number or plate already in use in your center"
    )
    assert "token" not in response.text
    assert "token_hash" not in response.text


@pytest.mark.usefixtures("mock_db")
def test_create_driver_rejects_extra_vehicle_fields(monkeypatch, mock_db):
    set_app_env(monkeypatch, "development")
    use_admin_dependency(make_admin())
    body = _new_driver_payload()
    body["vehicle"]["active"] = False

    with TestClient(main.app) as client:
        response = client.post("/admin/drivers", json=body)

    assert response.status_code == 422
    mock_db.add.assert_not_called()


@pytest.mark.usefixtures("mock_db")
def test_edit_driver_changes_only_provided_fields(monkeypatch, mock_db):
    set_app_env(monkeypatch, "development")
    admin = make_admin()
    use_admin_dependency(admin)
    vehicle = Vehicle(
        id=uuid.uuid4(),
        center_id=admin.center_id,
        driver_id=uuid.uuid4(),
        taxi_number="TX-1",
        plate_number="OLD 123",
        type="Sedan",
    )
    driver = Driver(
        id=vehicle.driver_id,
        center_id=admin.center_id,
        name="Original",
        phone="55500001",
        token_hash="private-token-hash",
        active=True,
        online=False,
    )
    driver.vehicle = vehicle
    mock_db.execute.return_value = scalar_result(driver)

    with TestClient(main.app) as client:
        response = client.patch(
            f"/admin/drivers/{driver.id}",
            json={"name": "Updated", "vehicle": {"plate_number": " xy 456 "}},
        )

    assert response.status_code == 200
    assert driver.name == "Updated"
    assert driver.phone == "55500001"
    assert vehicle.taxi_number == "TX-1"
    assert vehicle.center_id == admin.center_id
    assert vehicle.plate_number == "XY 456"
    assert vehicle.type == "Sedan"
    assert isinstance(mock_db.add.call_args.args[0], AuditLog)
    query = mock_db.execute.await_args.args[0]
    compiled = query.compile()
    assert "drivers.center_id" in str(compiled)
    assert admin.center_id in compiled.params.values()


@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [
        ("patch", "", {"name": "Cross tenant"}),
        ("post", "/deactivate", None),
        ("post", "/reactivate", None),
        ("post", "/token", None),
    ],
)
@pytest.mark.usefixtures("mock_db")
def test_driver_management_is_scoped_to_admin_center(
    monkeypatch, mock_db, method, suffix, body
):
    set_app_env(monkeypatch, "development")
    admin = make_admin()
    use_admin_dependency(admin)
    driver_id = uuid.uuid4()
    mock_db.execute.return_value = scalar_result(None)

    with TestClient(main.app) as client:
        response = client.request(
            method,
            f"/admin/drivers/{driver_id}{suffix}",
            json=body,
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Driver not found"
    query = mock_db.execute.await_args.args[0]
    compiled = query.compile()
    assert "drivers.center_id" in str(compiled)
    assert admin.center_id in compiled.params.values()
    mock_db.add.assert_not_called()


@pytest.mark.usefixtures("mock_db")
def test_deactivate_invalidates_token_and_sets_offline_state(monkeypatch, mock_db):
    set_app_env(monkeypatch, "development")
    admin = make_admin()
    use_admin_dependency(admin)
    old_token = "old-driver-token"
    old_hash = hashlib.sha256(old_token.encode()).hexdigest()
    driver = Driver(
        id=uuid.uuid4(),
        center_id=admin.center_id,
        name="Driver",
        phone="55500001",
        token_hash=old_hash,
        active=True,
        online=True,
        vehicle=None,
    )
    mock_db.execute.side_effect = [
        scalar_result(driver),
        scalar_result(None),
    ]

    with TestClient(main.app) as client:
        deactivated = client.post(f"/admin/drivers/{driver.id}/deactivate")
        old_status = client.post(
            "/status",
            headers={"X-Token": old_token},
            json={"online": True},
        )

    assert deactivated.status_code == 200
    assert old_status.status_code == 401
    assert driver.active is False
    assert driver.online is False
    assert driver.deactivated_at is not None
    assert driver.deactivated_at.tzinfo == timezone.utc
    assert driver.token_hash != old_hash
    assert mock_db.commit.await_count == 1
    assert isinstance(mock_db.add.call_args.args[0], AuditLog)


@pytest.mark.usefixtures("mock_db")
def test_deactivate_is_idempotent(monkeypatch, mock_db):
    set_app_env(monkeypatch, "development")
    admin = make_admin()
    use_admin_dependency(admin)
    deactivated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    token_hash = hashlib.sha256(b"discarded").hexdigest()
    driver = Driver(
        id=uuid.uuid4(),
        center_id=admin.center_id,
        name="Driver",
        phone="55500001",
        token_hash=token_hash,
        active=False,
        online=False,
        deactivated_at=deactivated_at,
        vehicle=None,
    )
    mock_db.execute.return_value = scalar_result(driver)

    with TestClient(main.app) as client:
        response = client.post(f"/admin/drivers/{driver.id}/deactivate")

    assert response.status_code == 200
    assert driver.deactivated_at is deactivated_at
    assert driver.token_hash == token_hash
    assert driver.active is False
    assert driver.online is False


@pytest.mark.usefixtures("mock_db")
def test_deactivation_broadcast_reaches_same_center_only(monkeypatch, mock_db):
    set_app_env(monkeypatch, "development")
    admin = make_admin()
    use_admin_dependency(admin)
    driver = Driver(
        id=uuid.uuid4(),
        center_id=admin.center_id,
        name="Driver",
        phone="55500001",
        token_hash="driver-hash",
        active=True,
        online=True,
        vehicle=None,
    )
    mock_db.execute.return_value = scalar_result(driver)
    center_a_client = Mock(send_json=AsyncMock())
    center_b_client = Mock(send_json=AsyncMock())
    main.clients[center_a_client] = admin.center_id
    main.clients[center_b_client] = uuid.uuid4()

    with TestClient(main.app) as client:
        response = client.post(f"/admin/drivers/{driver.id}/deactivate")

    assert response.status_code == 200
    center_a_client.send_json.assert_awaited_once_with(
        {
            "type": "driver_status",
            "driver_id": str(driver.id),
            "online": False,
            "active": False,
        }
    )
    center_b_client.send_json.assert_not_awaited()


@pytest.mark.usefixtures("mock_db")
def test_reactivate_returns_new_token_once_and_old_token_stays_invalid(
    monkeypatch, mock_db
):
    set_app_env(monkeypatch, "development")
    admin = make_admin()
    use_admin_dependency(admin)
    old_token = "old-driver-token"
    driver = Driver(
        id=uuid.uuid4(),
        center_id=admin.center_id,
        name="Driver",
        phone="55500001",
        token_hash=hashlib.sha256(old_token.encode()).hexdigest(),
        active=False,
        online=False,
        deactivated_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        vehicle=None,
    )
    mock_db.execute.side_effect = [
        scalar_result(driver),
        scalar_result(None),
        scalar_result(driver),
    ]

    with TestClient(main.app) as client:
        reactivated = client.post(f"/admin/drivers/{driver.id}/reactivate")
        old_status = client.post(
            "/status",
            headers={"X-Token": old_token},
            json={"online": True},
        )
        new_token = reactivated.json()["token"]
        new_status = client.post(
            "/status",
            headers={"X-Token": new_token},
            json={"online": True},
        )

    assert reactivated.status_code == 200
    assert reactivated.headers["cache-control"] == "no-store"
    assert driver.active is True
    assert driver.deactivated_at is None
    assert driver.token_hash == hashlib.sha256(new_token.encode()).hexdigest()
    assert old_status.status_code == 401
    assert new_status.status_code == 200


@pytest.mark.parametrize(
    ("suffix", "active"),
    [("/reactivate", True), ("/token", False)],
)
@pytest.mark.usefixtures("mock_db")
def test_token_actions_reject_invalid_driver_state(
    monkeypatch, mock_db, suffix, active
):
    set_app_env(monkeypatch, "development")
    admin = make_admin()
    use_admin_dependency(admin)
    driver = Driver(
        id=uuid.uuid4(),
        center_id=admin.center_id,
        name="Driver",
        phone="55500001",
        token_hash="existing-hash",
        active=active,
        online=False,
        vehicle=None,
    )
    mock_db.execute.return_value = scalar_result(driver)

    with TestClient(main.app) as client:
        response = client.post(f"/admin/drivers/{driver.id}{suffix}")

    assert response.status_code == 409
    assert "token" not in response.text.lower()
    mock_db.commit.assert_not_awaited()


@pytest.mark.usefixtures("mock_db")
def test_regenerate_token_invalidates_old_and_accepts_new(monkeypatch, mock_db):
    set_app_env(monkeypatch, "development")
    admin = make_admin()
    use_admin_dependency(admin)
    old_token = "old-driver-token"
    driver = Driver(
        id=uuid.uuid4(),
        center_id=admin.center_id,
        name="Driver",
        phone="55500001",
        token_hash=hashlib.sha256(old_token.encode()).hexdigest(),
        active=True,
        online=False,
        vehicle=None,
    )
    mock_db.execute.side_effect = [
        scalar_result(driver),
        scalar_result(None),
        scalar_result(driver),
    ]

    with TestClient(main.app) as client:
        regenerated = client.post(f"/admin/drivers/{driver.id}/token")
        old_status = client.post(
            "/status",
            headers={"X-Token": old_token},
            json={"online": True},
        )
        new_token = regenerated.json()["token"]
        new_status = client.post(
            "/status",
            headers={"X-Token": new_token},
            json={"online": True},
        )

    assert regenerated.status_code == 200
    assert regenerated.headers["cache-control"] == "no-store"
    assert old_status.status_code == 401
    assert new_status.status_code == 200
    assert driver.token_hash == hashlib.sha256(new_token.encode()).hexdigest()


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
    mock_db.execute.side_effect = [
        scalar_result(driver),
        scalar_result(driver),
        scalar_result(None),
        scalar_result(None),
        scalar_result(None),
        scalar_result(uuid.uuid4()),
    ]
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
            },
        )
        spoofed_center_response = client.post(
            "/location",
            headers={"X-Token": "driver-token"},
            json={
                "lat": 36.8,
                "lng": 10.2,
                "center_id": str(center_b),
            },
        )

    assert response.status_code == 200
    assert spoofed_center_response.status_code == 422
    assert spoofed_center_response.json() == {
        "detail": {"reason": "invalid_request"}
    }
    insert_statement = mock_db.execute.await_args_list[-1].args[0]
    assert insert_statement.compile().params["center_id"] == center_a
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
