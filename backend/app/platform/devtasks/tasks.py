import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

REPO_DIR = Path(__file__).resolve().parents[4]
BACKEND_DIR = REPO_DIR / "backend"
FRONTEND_DIR = REPO_DIR / "frontend"


@dataclass(frozen=True)
class TaskParameter:
    name: str
    description: str
    pattern: str


@dataclass(frozen=True)
class TaskSpec:
    id: str
    label: str
    description: str
    kind: Literal["oneshot", "service"]
    command: tuple[str, ...]
    cwd: Path
    timeout: float | None = None
    parameters: tuple[TaskParameter, ...] = ()


TASKS = (
    TaskSpec(
        id="db_start",
        label="Start database",
        description="Start the local PostgreSQL service without removing volumes.",
        kind="oneshot",
        command=("docker", "compose", "up", "-d"),
        cwd=BACKEND_DIR,
        timeout=120,
    ),
    TaskSpec(
        id="db_status",
        label="Database status",
        description="Show running Docker containers.",
        kind="oneshot",
        command=("docker", "ps"),
        cwd=BACKEND_DIR,
        timeout=30,
    ),
    TaskSpec(
        id="alembic_current",
        label="Current database revision",
        description="Show the current Alembic revision.",
        kind="oneshot",
        command=(sys.executable, "-m", "alembic", "current"),
        cwd=BACKEND_DIR,
        timeout=60,
    ),
    TaskSpec(
        id="alembic_upgrade",
        label="Upgrade database",
        description="Upgrade the database to Alembic head.",
        kind="oneshot",
        command=(sys.executable, "-m", "alembic", "upgrade", "head"),
        cwd=BACKEND_DIR,
        timeout=120,
    ),
    TaskSpec(
        id="run_tests",
        label="Run backend tests",
        description="Run the backend pytest suite or one selected test module.",
        kind="oneshot",
        command=(sys.executable, "-m", "pytest", "-q"),
        cwd=BACKEND_DIR,
        timeout=600,
        parameters=(
            TaskParameter(
                name="test_file",
                description="Optional test module under backend/tests.",
                pattern=r"tests/test_[A-Za-z0-9_]+\.py",
            ),
        ),
    ),
    TaskSpec(
        id="frontend_serve",
        label="Serve frontend",
        description="Serve the static frontend on localhost:5173.",
        kind="service",
        command=(
            sys.executable,
            "-m",
            "http.server",
            "5173",
            "--bind",
            "localhost",
        ),
        cwd=FRONTEND_DIR,
    ),
)

TASKS_BY_ID = {task.id: task for task in TASKS}


def serialize_task(task: TaskSpec) -> dict[str, object]:
    return {
        "id": task.id,
        "label": task.label,
        "description": task.description,
        "kind": task.kind,
        "parameters": [
            {
                "name": parameter.name,
                "description": parameter.description,
                "pattern": parameter.pattern,
            }
            for parameter in task.parameters
        ],
    }
