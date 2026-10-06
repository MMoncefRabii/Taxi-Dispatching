import logging
import os
from unittest.mock import AsyncMock, Mock

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://fleet_tracker:test@localhost:5432/fleet_tracker",
)
os.environ.setdefault("ADMIN_KEY", "test-admin-key")

import pytest
from fastapi.testclient import TestClient

import main
from app.config import Settings, settings
from app.db import get_db


@pytest.fixture
def mock_db():
    db = Mock()
    db.execute = AsyncMock(return_value=Mock(all=Mock(return_value=[])))
    db.add = Mock()
    db.commit = AsyncMock()
    main.app.dependency_overrides[get_db] = lambda: db
    yield db
    main.app.dependency_overrides.clear()


def set_auth_mode(monkeypatch, *, app_env: str, disabled: bool) -> None:
    monkeypatch.setattr(settings, "app_env", app_env)
    monkeypatch.setattr(settings, "dev_disable_admin_auth", disabled)


def test_missing_or_invalid_environment_defaults_to_production(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://fleet_tracker:test@localhost:5432/fleet_tracker",
    )
    monkeypatch.setenv("ADMIN_KEY", "test-admin-key")
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
    ],
)
@pytest.mark.usefixtures("mock_db")
def test_admin_routes_require_key_when_flag_is_off(monkeypatch, method, path, json):
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
def test_admin_routes_accept_missing_key_in_development(monkeypatch, method, path, json):
    set_auth_mode(monkeypatch, app_env="development", disabled=True)

    with TestClient(main.app) as client:
        response = client.request(method, path, json=json)

    assert response.status_code == 200


@pytest.mark.usefixtures("mock_db")
def test_websocket_accepts_missing_key_in_development(monkeypatch):
    set_auth_mode(monkeypatch, app_env="development", disabled=True)

    with TestClient(main.app) as client:
        with client.websocket_connect("/ws"):
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
