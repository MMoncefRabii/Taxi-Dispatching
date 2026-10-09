import asyncio
import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://test:test@localhost/test_db",
)

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import main
import scripts.seed_super_admin as seed_super_admin_script
from app.db import get_db
from app.models import (
    Center,
    PlatformAuditLog,
    PlatformSession,
    SuperAdmin,
)
from app.platform.auth import (
    PLATFORM_SESSION_COOKIE,
    PlatformPrincipal,
    require_super_admin,
)
from app.config import settings


def scalar_result(value=None, rows=()):
    return Mock(
        scalar_one_or_none=Mock(return_value=value),
        all=Mock(return_value=list(rows)),
        scalars=Mock(return_value=Mock(all=Mock(return_value=list(rows)))),
    )


@pytest.fixture
def mock_db():
    db = Mock()
    db.execute = AsyncMock(return_value=scalar_result())
    db.added = []
    db.add = Mock(side_effect=db.added.append)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    main.app.dependency_overrides[get_db] = lambda: db
    yield db
    main.app.dependency_overrides.clear()


def make_super_admin(password="correct horse battery staple"):
    return SuperAdmin(
        id=uuid.uuid4(),
        email="owner@example.com",
        password_hash=PasswordHasher().hash(password),
        active=True,
    )


def make_platform_session(super_admin, token, *, expires=None, revoked=None):
    return PlatformSession(
        id=uuid.uuid4(),
        super_admin_id=super_admin.id,
        token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        created_at=datetime.now(timezone.utc),
        expires_at=expires or datetime.now(timezone.utc) + timedelta(hours=1),
        revoked_at=revoked,
    )


def use_platform_dependency(super_admin=None, platform_session=None):
    if super_admin is None:
        super_admin = make_super_admin()
    if platform_session is None:
        platform_session = make_platform_session(super_admin, "test-platform-token")
    principal = PlatformPrincipal(super_admin, platform_session)
    main.app.dependency_overrides[require_super_admin] = lambda: principal
    return principal


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", "/platform/me", None),
        ("post", "/platform/logout", None),
        ("get", "/platform/centers", None),
        ("post", "/platform/centers", {"name": "A", "city": "B", "timezone": "UTC"}),
        ("get", "/platform/audit", None),
    ],
)
@pytest.mark.usefixtures("mock_db")
def test_all_platform_routes_except_login_require_a_platform_session(
    method, path, body
):
    with TestClient(main.app) as client:
        response = client.request(method, path, json=body)

    assert response.status_code == 401


@pytest.mark.parametrize("state", ["expired", "revoked"])
@pytest.mark.usefixtures("mock_db")
def test_expired_and_revoked_platform_sessions_are_rejected(mock_db, state):
    token = "test-platform-token"
    super_admin = make_super_admin()
    platform_session = make_platform_session(
        super_admin,
        token,
        expires=(
            datetime.now(timezone.utc) - timedelta(minutes=1)
            if state == "expired"
            else datetime.now(timezone.utc) + timedelta(hours=1)
        ),
        revoked=(
            datetime.now(timezone.utc)
            if state == "revoked"
            else None
        ),
    )
    mock_db.execute.return_value = scalar_result(platform_session)

    with TestClient(main.app) as client:
        client.cookies.set(PLATFORM_SESSION_COOKIE, token, path="/platform")
        response = client.get("/platform/me")

    assert response.status_code == 401
    assert mock_db.execute.await_count == 1


@pytest.mark.usefixtures("mock_db")
def test_admin_cookie_is_not_a_platform_session():
    with TestClient(main.app) as client:
        client.cookies.set(main.ADMIN_SESSION_COOKIE, "center-admin-token")
        response = client.get("/platform/me")

    assert response.status_code == 401


@pytest.mark.usefixtures("mock_db")
def test_platform_cookie_is_not_an_admin_session_or_websocket_session():
    with TestClient(main.app) as client:
        client.cookies.set(PLATFORM_SESSION_COOKIE, "platform-owner-token")
        response = client.get("/admin/me")
        assert response.status_code == 401
        with pytest.raises(WebSocketDisconnect) as disconnect:
            with client.websocket_connect("/ws"):
                pass

    assert disconnect.value.code == 1008


@pytest.mark.parametrize(
    ("app_env", "secure_cookie"),
    [("development", False), ("production", True)],
)
@pytest.mark.usefixtures("mock_db")
def test_platform_login_creates_hashed_four_hour_session_and_audit(
    monkeypatch, mock_db, app_env, secure_cookie
):
    monkeypatch.setattr(settings, "app_env", app_env)
    super_admin = make_super_admin()
    mock_db.execute.return_value = scalar_result(super_admin)

    with TestClient(main.app) as client:
        response = client.post(
            "/platform/login",
            json={
                "email": "owner@example.com",
                "password": "correct horse battery staple",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    cookie = response.headers["set-cookie"].lower()
    assert "platform_session=" in cookie
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "path=/platform" in cookie
    assert ("secure" in cookie) is secure_cookie
    token = response.cookies.get(PLATFORM_SESSION_COOKIE)
    session = next(row for row in mock_db.added if isinstance(row, PlatformSession))
    event = next(row for row in mock_db.added if isinstance(row, PlatformAuditLog))
    assert session.super_admin_id == super_admin.id
    assert session.token_hash == hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert session.created_at.tzinfo == timezone.utc
    assert session.expires_at - session.created_at == timedelta(hours=4)
    assert event.action == "login_success"
    assert event.super_admin_id == super_admin.id
    assert event.success is True
    mock_db.commit.assert_awaited_once()
    assert "password_hash" not in response.text


@pytest.mark.usefixtures("mock_db")
def test_wrong_password_and_unknown_email_share_401_and_store_only_email_hash(
    mock_db,
):
    mock_db.execute.side_effect = [
        scalar_result(make_super_admin()),
        scalar_result(None),
    ]

    with TestClient(main.app) as client:
        wrong_password = client.post(
            "/platform/login",
            json={"email": "owner@example.com", "password": "incorrect"},
        )
        unknown_email = client.post(
            "/platform/login",
            json={"email": "Missing@example.com", "password": "incorrect"},
        )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert wrong_password.json()["detail"] == "Invalid email or password"
    events = [row for row in mock_db.added if isinstance(row, PlatformAuditLog)]
    assert len(events) == 2
    assert all(event.action == "login_failure" for event in events)
    assert all(event.super_admin_id is None for event in events)
    assert events[0].email_hash == hashlib.sha256(
        b"owner@example.com"
    ).hexdigest()
    assert events[1].email_hash == hashlib.sha256(
        b"missing@example.com"
    ).hexdigest()
    assert all("owner@example.com" not in repr(event) for event in events)
    assert all(event.success is False for event in events)
    assert mock_db.commit.await_count == 2


@pytest.mark.usefixtures("mock_db")
def test_inactive_super_admin_cannot_log_in(mock_db):
    super_admin = make_super_admin()
    super_admin.active = False
    mock_db.execute.return_value = scalar_result(super_admin)

    with TestClient(main.app) as client:
        response = client.post(
            "/platform/login",
            json={
                "email": "owner@example.com",
                "password": "correct horse battery staple",
            },
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"
    assert not any(isinstance(row, PlatformSession) for row in mock_db.added)


@pytest.mark.usefixtures("mock_db")
def test_login_rejects_extra_fields_and_oversized_password(mock_db):
    with TestClient(main.app) as client:
        extra = client.post(
            "/platform/login",
            json={
                "email": "owner@example.com",
                "password": "valid-password",
                "active": True,
            },
        )
        oversized = client.post(
            "/platform/login",
            json={"email": "owner@example.com", "password": "x" * 129},
        )

    assert extra.status_code == oversized.status_code == 422
    assert "valid-password" not in extra.text
    assert "x" * 129 not in oversized.text
    mock_db.execute.assert_not_awaited()


@pytest.mark.usefixtures("mock_db")
def test_logout_revokes_platform_session_and_clears_cookie(mock_db):
    principal = use_platform_dependency()

    with TestClient(main.app) as client:
        response = client.post("/platform/logout")

    assert response.status_code == 204
    assert principal.session.revoked_at is not None
    assert principal.session.revoked_at.tzinfo == timezone.utc
    cookie = response.headers["set-cookie"].lower()
    assert "platform_session=" in cookie
    assert "path=/platform" in cookie
    assert "max-age=0" in cookie
    assert any(
        isinstance(row, PlatformAuditLog) and row.action == "logout"
        for row in mock_db.added
    )
    mock_db.commit.assert_awaited_once()


@pytest.mark.usefixtures("mock_db")
def test_platform_me_returns_only_owner_email(mock_db):
    principal = use_platform_dependency()

    with TestClient(main.app) as client:
        response = client.get("/platform/me")

    assert response.status_code == 200
    assert response.json() == {"email": principal.super_admin.email}
    assert "password_hash" not in response.text


@pytest.mark.usefixtures("mock_db")
def test_centers_list_aggregates_counts_and_respects_limit_offset(mock_db):
    use_platform_dependency()
    center = Center(
        id=uuid.uuid4(),
        name="Central",
        city="Tunis",
        timezone="Africa/Tunis",
        active=True,
        created_at=datetime.now(timezone.utc),
    )
    mock_db.execute.return_value = scalar_result(
        rows=[(center, 4, 2)]
    )

    with TestClient(main.app) as client:
        response = client.get("/platform/centers?limit=7&offset=3")

    assert response.status_code == 200
    assert response.json()[0] == {
        "id": str(center.id),
        "name": "Central",
        "city": "Tunis",
        "timezone": "Africa/Tunis",
        "active": True,
        "created_at": center.created_at.isoformat().replace("+00:00", "Z"),
        "driver_count": 4,
        "admin_count": 2,
    }
    query = mock_db.execute.await_args.args[0]
    assert query._limit_clause.value == 7
    assert query._offset_clause.value == 3
    compiled = str(query.compile())
    assert "drivers.center_id" in compiled
    assert "admins.active IS true" in compiled
    assert "count(" in compiled.lower()


@pytest.mark.usefixtures("mock_db")
def test_centers_list_rejects_limit_above_max(mock_db):
    use_platform_dependency()

    with TestClient(main.app) as client:
        response = client.get("/platform/centers?limit=201")

    assert response.status_code == 422
    mock_db.execute.assert_not_awaited()


@pytest.mark.parametrize(
    "body",
    [
        {"name": "Central", "city": "Tunis", "timezone": "Not/AZone"},
        {
            "name": "Central",
            "city": "Tunis",
            "timezone": "Africa/Tunis",
            "active": True,
        },
    ],
)
@pytest.mark.usefixtures("mock_db")
def test_center_creation_rejects_invalid_timezone_and_extra_fields(mock_db, body):
    use_platform_dependency()

    with TestClient(main.app) as client:
        response = client.post("/platform/centers", json=body)

    assert response.status_code == 422
    mock_db.execute.assert_not_awaited()
    mock_db.add.assert_not_called()


@pytest.mark.usefixtures("mock_db")
def test_center_creation_is_audited_in_same_transaction(mock_db):
    principal = use_platform_dependency()
    created_at = datetime.now(timezone.utc)

    async def flush():
        center = next(row for row in mock_db.added if isinstance(row, Center))
        center.id = center.id or uuid.uuid4()
        center.created_at = created_at

    mock_db.flush.side_effect = flush
    with TestClient(main.app) as client:
        response = client.post(
            "/platform/centers",
            json={
                "name": "Coastal",
                "city": "Sousse",
                "timezone": "Africa/Tunis",
            },
        )

    assert response.status_code == 201
    assert response.json()["name"] == "Coastal"
    center = next(row for row in mock_db.added if isinstance(row, Center))
    event = next(row for row in mock_db.added if isinstance(row, PlatformAuditLog))
    assert event.action == "center_created"
    assert event.super_admin_id == principal.super_admin.id
    assert event.target_id == center.id
    assert event.target_type == "center"
    mock_db.commit.assert_awaited_once()


@pytest.mark.usefixtures("mock_db")
def test_platform_audit_requires_authentication_and_respects_limit(mock_db):
    use_platform_dependency()
    event = PlatformAuditLog(
        id=uuid.uuid4(),
        action="login_failure",
        target_type="super_admin",
        success=False,
        email_hash="a" * 64,
        created_at=datetime.now(timezone.utc),
    )
    mock_db.execute.return_value = scalar_result(rows=[event])

    with TestClient(main.app) as client:
        response = client.get("/platform/audit?limit=2&offset=5")

    assert response.status_code == 200
    assert response.json()[0]["action"] == "login_failure"
    assert "email_hash" not in response.text
    assert "token_hash" not in response.text
    query = mock_db.execute.await_args.args[0]
    assert query._limit_clause.value == 2
    assert query._offset_clause.value == 5
    assert "ORDER BY platform_audit_log.created_at DESC" in str(query.compile())


def test_platform_login_cors_allowed_origin_and_rejects_disallowed_origin():
    with TestClient(main.app) as client:
        allowed = client.options(
            "/platform/login",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        denied = client.options(
            "/platform/login",
            headers={
                "Origin": "https://attacker.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert allowed.headers["access-control-allow-credentials"] == "true"
    assert not any(
        header.lower().startswith("access-control-")
        for header in denied.headers
    )


def test_seed_script_does_not_prompt_when_email_exists(monkeypatch, capsys):
    session = Mock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.execute = AsyncMock(return_value=scalar_result(make_super_admin()))
    monkeypatch.setattr(seed_super_admin_script, "SessionLocal", lambda: session)
    monkeypatch.setattr(
        seed_super_admin_script,
        "engine",
        Mock(dispose=AsyncMock()),
    )
    monkeypatch.setattr(
        seed_super_admin_script,
        "getpass",
        Mock(side_effect=AssertionError("existing account must not prompt")),
    )

    asyncio.run(seed_super_admin_script.seed_from_prompt("owner@example.com"))

    assert capsys.readouterr().out == "Super admin already exists; no changes made.\n"
    seed_super_admin_script.getpass.assert_not_called()


def test_seed_script_does_not_prompt_after_first_super_admin(monkeypatch, capsys):
    session = Mock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.execute = AsyncMock(return_value=scalar_result())
    session.scalar = AsyncMock(return_value=uuid.uuid4())
    monkeypatch.setattr(seed_super_admin_script, "SessionLocal", lambda: session)
    monkeypatch.setattr(
        seed_super_admin_script,
        "engine",
        Mock(dispose=AsyncMock()),
    )
    monkeypatch.setattr(
        seed_super_admin_script,
        "getpass",
        Mock(side_effect=AssertionError("bootstrap must not prompt twice")),
    )

    asyncio.run(seed_super_admin_script.seed_from_prompt("second@example.com"))

    assert capsys.readouterr().out == (
        "A super admin already exists; this command is only for the first "
        "super admin.\n"
    )
    seed_super_admin_script.getpass.assert_not_called()
