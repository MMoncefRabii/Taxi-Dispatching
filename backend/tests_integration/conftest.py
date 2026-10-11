import asyncio
import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_DIR = BACKEND_DIR.parent
COMPOSE_FILE = BACKEND_DIR / "docker-compose.yml"
POSTGRES_SERVICE = "postgres"
DATABASE_NAME = "fleet_integration_test"
SOURCE_DATABASE_NAME = "fleet_tracker"


@dataclass(frozen=True)
class IntegrationDatabase:
    session_factory: async_sessionmaker[AsyncSession]
    url: URL
    run_alembic: Callable[..., str]


def pytest_configure(config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: requires the disposable real-PostgreSQL integration database",
    )


def pytest_ignore_collect(collection_path, config):
    if os.environ.get("INTEGRATION_DB_ENABLED", "").lower() == "true":
        return None
    path = Path(str(collection_path))
    if path.suffix == ".py" and path.parent == Path(__file__).resolve().parent:
        return True
    return None


@pytest.fixture(scope="session")
def integration_database() -> Iterator[IntegrationDatabase]:
    from app.config import settings

    source_url = make_url(settings.async_database_url)
    if (
        source_url.get_backend_name() != "postgresql"
        or source_url.database != SOURCE_DATABASE_NAME
    ):
        raise RuntimeError(
            "Integration tests require the configured PostgreSQL URL to target "
            "fleet_tracker; only fleet_integration_test will be accessed."
        )
    test_url = source_url.set(database=DATABASE_NAME)
    if test_url.database != DATABASE_NAME:
        raise RuntimeError("Refusing to use a database other than fleet_integration_test.")

    compose = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(COMPOSE_FILE),
            "ps",
            "-q",
            POSTGRES_SERVICE,
        ],
        cwd=REPOSITORY_DIR,
        check=False,
        capture_output=True,
        text=True,
    )
    if compose.returncode != 0:
        raise RuntimeError(
            f"Could not locate the existing postgres service (exit code {compose.returncode})."
        )
    container_ids = compose.stdout.splitlines()
    if len(container_ids) != 1 or not container_ids[0].strip():
        raise RuntimeError("The existing postgres service must have exactly one running container.")
    container_id = container_ids[0].strip()

    def docker_exec(*arguments: str) -> None:
        result = subprocess.run(
            ["docker", "exec", container_id, *arguments],
            cwd=REPOSITORY_DIR,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"PostgreSQL container command failed with exit code {result.returncode}."
            )

    def run_alembic(*arguments: str) -> str:
        environment = os.environ.copy()
        environment["DATABASE_URL"] = test_url.render_as_string(hide_password=False)
        environment["DEV_TASKS_ENABLED"] = "false"
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *arguments],
            cwd=BACKEND_DIR,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Alembic {' '.join(arguments)} failed with exit code {result.returncode}."
            )
        return result.stdout + result.stderr

    database_created = False
    engine = None
    try:
        docker_exec(
            "createdb",
            "-U",
            "fleet_tracker",
            "--owner=fleet_tracker",
            DATABASE_NAME,
        )
        database_created = True
        run_alembic("upgrade", "head")
        run_alembic("downgrade", "0005_location_dedup")
        run_alembic("upgrade", "head")
        current = run_alembic("current")
        if "0006_vehicle_tenant_uniqueness" not in current:
            raise RuntimeError("Alembic did not leave fleet_integration_test at revision 0006.")

        engine = create_async_engine(test_url, poolclass=NullPool)
        yield IntegrationDatabase(
            session_factory=async_sessionmaker(engine, expire_on_commit=False),
            url=test_url,
            run_alembic=run_alembic,
        )
    finally:
        try:
            if engine is not None:
                asyncio.run(engine.dispose())
        finally:
            if database_created:
                docker_exec("dropdb", "-U", "fleet_tracker", DATABASE_NAME)
