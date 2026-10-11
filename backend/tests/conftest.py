import os

import pytest


os.environ.update(
    {
        "DATABASE_URL": "postgresql+asyncpg://localhost/test_db",
        "WEB_ORIGINS": "http://localhost:5173",
        "FRONTEND_BASE_URL": "http://localhost:5173",
        "DEV_TASKS_ENABLED": "false",
        "LOCATION_MAX_FUTURE_SECONDS": "60",
        "LOCATION_MAX_AGE_LIVE_SECONDS": "300",
        "LOCATION_MAX_AGE_BATCH_SECONDS": "21600",
        "LOCATION_MIN_INTERVAL_SECONDS": "2",
        "LOCATION_MAX_SPEED_KMH": "200",
        "LOCATION_MAX_ACCURACY_M": "50",
        "LOCATION_BATCH_MAX": "50",
        "APP_ENV": "production",
    }
)


@pytest.fixture(autouse=True)
def force_dev_tasks_disabled(monkeypatch):
    from app.config import settings

    monkeypatch.setenv("DEV_TASKS_ENABLED", "false")
    monkeypatch.setattr(settings, "dev_tasks_enabled", False)
