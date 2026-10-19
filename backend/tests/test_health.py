from unittest.mock import AsyncMock, Mock

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

import main
from app.db import get_db


def test_health_is_database_independent_and_allows_cors():
    app = main.create_app()

    def unavailable_db():
        raise SQLAlchemyError("database unavailable")

    app.dependency_overrides[get_db] = unavailable_db

    with TestClient(app) as client:
        response = client.get(
            "/health",
            headers={"Origin": "http://localhost:5173"},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["access-control-allow-origin"] == (
        "http://localhost:5173"
    )


def test_ready_returns_ready_when_database_query_succeeds():
    app = main.create_app()
    session = Mock()
    session.execute = AsyncMock()

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    session.execute.assert_awaited_once()
    assert str(session.execute.await_args.args[0]) == "SELECT 1"


def test_ready_returns_not_ready_without_database_error_details():
    app = main.create_app()
    session = Mock()
    session.execute = AsyncMock(
        side_effect=SQLAlchemyError("database unavailable")
    )

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    session.execute.assert_awaited_once()
