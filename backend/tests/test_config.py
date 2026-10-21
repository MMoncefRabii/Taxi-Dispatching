import logging

import pytest

from app.config import Settings
from main import _validate_startup_configuration


STRONG_PASSWORD = "not-a-placeholder-72b8f1c9"


def make_settings(**overrides):
    values = {
        "DATABASE_URL": (
            "postgresql+asyncpg://fleet_user:"
            f"{STRONG_PASSWORD}@db:5432/fleet_tracker"
        ),
        "WEB_ORIGINS": "https://admin.example.com",
        "FRONTEND_BASE_URL": "https://admin.example.com",
        "APP_ENV": "production",
        "DEV_TASKS_ENABLED": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_production_https_configuration_passes(caplog):
    configuration = make_settings()

    with caplog.at_level(logging.INFO):
        _validate_startup_configuration(configuration)

    assert "Configuration guard passed for APP_ENV=production." in caplog.text


def test_production_localhost_http_passes_with_one_warning(caplog):
    configuration = make_settings(
        WEB_ORIGINS="http://localhost:5173,http://127.0.0.1:5174",
        FRONTEND_BASE_URL="http://localhost:5173",
    )

    with caplog.at_level(logging.WARNING):
        _validate_startup_configuration(configuration)

    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "production traffic must use HTTPS" in warnings[0].message


@pytest.mark.parametrize(
    ("overrides", "expected_problem"),
    [
        ({"WEB_ORIGINS": "https://admin.example.com/path"}, "no path"),
        ({"WEB_ORIGINS": "https://admin.example.com,*"}, "wildcard"),
        ({"WEB_ORIGINS": "https://*.example.com"}, "wildcard"),
        ({"WEB_ORIGINS": "https://admin.example.com,"}, "must not be empty"),
        (
            {"WEB_ORIGINS": "http://admin.example.com"},
            "WEB_ORIGINS entry 1 must use HTTPS",
        ),
        (
            {"FRONTEND_BASE_URL": "http://admin.example.com"},
            "FRONTEND_BASE_URL must use HTTPS",
        ),
        (
            {
                "DATABASE_URL": (
                    "postgresql+asyncpg://fleet_user:changeme@db:5432/fleet_tracker"
                )
            },
            "DATABASE_URL password looks like a placeholder",
        ),
        (
            {
                "DATABASE_URL": (
                    "postgresql+asyncpg://fleet_user:@db:5432/fleet_tracker"
                )
            },
            "DATABASE_URL password looks like a placeholder",
        ),
        (
            {"DATABASE_URL": "postgresql+asyncpg://db:5432/fleet_tracker"},
            "DATABASE_URL password looks like a placeholder",
        ),
        ({"DEV_TASKS_ENABLED": True}, "DEV_TASKS_ENABLED cannot be used in production"),
    ],
)
def test_production_rejects_each_invalid_condition(overrides, expected_problem):
    configuration = make_settings(**overrides)

    with pytest.raises(RuntimeError, match=expected_problem):
        _validate_startup_configuration(configuration)


def test_production_reports_all_problems_without_secret_values():
    secret_password = "changeme"
    configuration = make_settings(
        DATABASE_URL=(
            "postgresql+asyncpg://fleet_user:"
            f"{secret_password}@db:5432/fleet_tracker"
        ),
        WEB_ORIGINS="*,http://admin.example.com,https://admin.example.com/path,,",
        FRONTEND_BASE_URL="http://admin.example.com",
        DEV_TASKS_ENABLED=True,
    )

    with pytest.raises(RuntimeError) as error:
        _validate_startup_configuration(configuration)

    message = str(error.value)
    for expected_problem in (
        "WEB_ORIGINS must not contain a wildcard origin",
        "WEB_ORIGINS entry 2 must use HTTPS",
        "WEB_ORIGINS entry 3 must be a bare",
        "WEB_ORIGINS entry 4 must not be empty",
        "DATABASE_URL password looks like a placeholder",
        "FRONTEND_BASE_URL must use HTTPS",
        "DEV_TASKS_ENABLED cannot be used in production",
    ):
        assert expected_problem in message
    assert secret_password not in message


def test_origin_path_and_insecure_scheme_are_reported_independently():
    configuration = make_settings(
        WEB_ORIGINS="http://admin.example.com/path",
    )

    with pytest.raises(RuntimeError) as error:
        _validate_startup_configuration(configuration)

    assert "must be a bare scheme://host[:port] origin with no path" in str(error.value)
    assert "must use HTTPS unless its host is localhost or 127.0.0.1" in str(
        error.value
    )


def test_missing_web_origins_fails_in_production(monkeypatch):
    monkeypatch.delenv("WEB_ORIGINS", raising=False)
    configuration = Settings(
        _env_file=None,
        DATABASE_URL=(
            "postgresql+asyncpg://fleet_user:"
            f"{STRONG_PASSWORD}@db:5432/fleet_tracker"
        ),
        FRONTEND_BASE_URL="https://admin.example.com",
        APP_ENV="production",
    )

    assert configuration.web_origins == "http://localhost:5173"
    with pytest.raises(RuntimeError, match="WEB_ORIGINS must be explicitly set"):
        _validate_startup_configuration(configuration)


def test_missing_frontend_base_url_fails_in_production(monkeypatch):
    monkeypatch.delenv("FRONTEND_BASE_URL", raising=False)
    configuration = Settings(
        _env_file=None,
        DATABASE_URL=(
            "postgresql+asyncpg://fleet_user:"
            f"{STRONG_PASSWORD}@db:5432/fleet_tracker"
        ),
        WEB_ORIGINS="https://admin.example.com",
        APP_ENV="production",
    )

    assert configuration.frontend_base_url == "http://localhost:5173"
    with pytest.raises(RuntimeError, match="FRONTEND_BASE_URL must be explicitly set"):
        _validate_startup_configuration(configuration)


def test_missing_web_origins_defaults_in_development(monkeypatch, caplog):
    monkeypatch.delenv("WEB_ORIGINS", raising=False)
    monkeypatch.delenv("FRONTEND_BASE_URL", raising=False)
    configuration = Settings(
        _env_file=None,
        DATABASE_URL=(
            "postgresql+asyncpg://fleet_user:"
            f"{STRONG_PASSWORD}@db:5432/fleet_tracker"
        ),
        APP_ENV="development",
    )

    with caplog.at_level(logging.INFO):
        _validate_startup_configuration(configuration)

    assert configuration.web_origins == "http://localhost:5173"
    assert "WEB_ORIGINS must be explicitly set" in caplog.text


def test_development_only_warns_for_production_configuration_problems(caplog):
    configuration = make_settings(
        APP_ENV="development",
        WEB_ORIGINS="http://admin.example.com",
    )

    with caplog.at_level(logging.INFO):
        _validate_startup_configuration(configuration)

    assert "Development configuration does not meet production requirements" in caplog.text
    assert "Configuration guard passed for APP_ENV=development." in caplog.text
