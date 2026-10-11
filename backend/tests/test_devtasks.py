import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://fleet_tracker:unused@localhost/test_db",
)

import pytest
from fastapi.testclient import TestClient

import main
from app.config import BACKEND_DIR, Settings, settings
from app.db import get_db
from app.models import PlatformAuditLog
from app.platform.devtasks import runner
from app.platform.devtasks.runner import DevTaskManager, TaskRun
from app.platform.devtasks.tasks import BACKEND_DIR, FRONTEND_DIR, TASKS
from app.platform.devtasks.router import require_dev_super_admin


def scalar_result(value=None):
    return Mock(scalar_one_or_none=Mock(return_value=value))


class FakeStream:
    def __init__(self, lines=()):
        self.lines = list(lines)

    async def readline(self):
        if self.lines:
            return self.lines.pop(0)
        return b""


class FakeProcess:
    def __init__(self, *, pid=4321, lines=(), return_code=0, held=False):
        self.pid = pid
        self.stdout = FakeStream(lines)
        self.returncode = return_code if not held else None
        self.held = held
        self.killed = False
        self._done = asyncio.Event()
        if not held:
            self._done.set()

    async def wait(self):
        await self._done.wait()
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9
        self._done.set()

    def finish(self, return_code=0):
        self.returncode = return_code
        self._done.set()


class ImmediateKiller:
    async def wait(self):
        return 0


def test_settings_load_dotenv_values_with_process_environment_precedence(
    tmp_path,
    monkeypatch,
):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=postgresql://file_user:file_password@localhost/file_db\n"
        "APP_ENV=development\n"
        "WEB_ORIGINS=http://file.example\n"
        "DEV_TASKS_ENABLED=true\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("WEB_ORIGINS", raising=False)
    monkeypatch.delenv("DEV_TASKS_ENABLED", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://environment_user:environment_password@localhost/env_db",
    )
    monkeypatch.setenv("APP_ENV", "production")
    loaded = Settings(_env_file=env_file)

    assert Settings.model_config["env_file"] == BACKEND_DIR / ".env"
    assert loaded.database_url.startswith(
        "postgresql://environment_user:"
    )
    assert loaded.app_env == "production"
    assert loaded.allowed_web_origins == ["http://file.example"]
    assert loaded.dev_tasks_enabled is True


@pytest.fixture
def enabled_app(monkeypatch):
    monkeypatch.setattr(settings, "dev_tasks_enabled", True)
    monkeypatch.setattr(settings, "app_env", "development")
    return main.create_app()


@pytest.fixture
def mock_db():
    db = Mock()
    db.execute = AsyncMock(return_value=scalar_result())
    db.added = []
    db.add = Mock(side_effect=db.added.append)
    db.commit = AsyncMock()
    return db


def use_admin(app, db, *, host=("127.0.0.1", 50000)):
    principal = SimpleNamespace(super_admin=SimpleNamespace(id="owner-id"))
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_dev_super_admin] = lambda: principal
    return TestClient(app, client=host)


def test_disabled_feature_does_not_register_dev_routes(monkeypatch):
    monkeypatch.setattr(settings, "dev_tasks_enabled", False)
    app = main.create_app()

    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        response = client.get("/platform/dev/tasks")

    assert response.status_code == 404


def test_enabled_feature_refuses_production_startup(monkeypatch):
    monkeypatch.setattr(settings, "dev_tasks_enabled", True)
    monkeypatch.setattr(settings, "app_env", "production")
    app = main.create_app()

    with pytest.raises(RuntimeError, match="cannot be used in production"):
        with TestClient(app):
            pass


@pytest.mark.parametrize("cookie_name", [None, main.ADMIN_SESSION_COOKIE])
def test_dev_routes_reject_missing_or_center_admin_cookie(
    enabled_app, mock_db, cookie_name
):
    enabled_app.dependency_overrides[get_db] = lambda: mock_db
    with TestClient(enabled_app, client=("127.0.0.1", 50000)) as client:
        if cookie_name is not None:
            client.cookies.set(cookie_name, "center-admin-session")
        response = client.get("/platform/dev/tasks")

    assert response.status_code == 401
    event = mock_db.added[0]
    assert isinstance(event, PlatformAuditLog)
    assert event.target_type == "dev_task"
    assert event.success is False
    assert event.user_agent == ""
    mock_db.commit.assert_awaited_once()


def test_unknown_task_is_not_found_and_is_audited(enabled_app, mock_db):
    with use_admin(enabled_app, mock_db) as client:
        response = client.post(
            "/platform/dev/tasks/not-allowlisted/run",
            json={},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Invalid development task request"
    event = mock_db.added[0]
    assert event.action == "dev_task_rejected:unknown"
    assert event.target_id is None
    assert mock_db.commit.await_count == 1


@pytest.mark.parametrize(
    "body",
    [
        {"test_file": "../scripts/seed_admin.py"},
        {"test_file": "tests/test_devtasks.py", "unexpected": "value"},
    ],
)
def test_task_parameters_are_strict_and_regex_bounded(
    enabled_app, mock_db, body
):
    with use_admin(enabled_app, mock_db) as client:
        response = client.post(
            "/platform/dev/tasks/run_tests/run",
            json=body,
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid development task request"
    assert len(mock_db.added) == 1
    assert mock_db.added[0].action == "dev_task_rejected:run_tests"
    assert mock_db.commit.await_count == 1


def test_non_loopback_client_is_forbidden_and_audited(enabled_app, mock_db):
    enabled_app.dependency_overrides[get_db] = lambda: mock_db
    with TestClient(enabled_app, client=("192.0.2.10", 50000)) as client:
        response = client.get("/platform/dev/tasks")

    assert response.status_code == 403
    assert mock_db.added[0].action == "dev_task_rejected:unknown"
    assert mock_db.added[0].success is False
    mock_db.commit.assert_awaited_once()


def test_post_rejects_unlisted_origin_and_audits(enabled_app, mock_db):
    enabled_app.dependency_overrides[get_db] = lambda: mock_db
    with TestClient(enabled_app, client=("127.0.0.1", 50000)) as client:
        response = client.post(
            "/platform/dev/tasks/db_status/run",
            json={},
            headers={"Origin": "https://attacker.invalid"},
        )

    assert response.status_code == 403
    assert mock_db.added[0].action == "dev_task_rejected:db_status"
    assert mock_db.added[0].success is False
    mock_db.commit.assert_awaited_once()


def test_run_acceptance_records_audit_without_parameters(
    enabled_app, mock_db, monkeypatch
):
    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProcess(lines=[b"ready\n"])

    monkeypatch.setattr(
        runner.asyncio,
        "create_subprocess_exec",
        fake_create_subprocess_exec,
    )
    with use_admin(enabled_app, mock_db) as client:
        response = client.post(
            "/platform/dev/tasks/run_tests/run",
            json={"test_file": "tests/test_devtasks.py"},
        )

    assert response.status_code == 200
    event = mock_db.added[0]
    assert event.action == "dev_task_run:run_tests"
    assert event.target_type == "dev_task"
    assert event.target_id is None
    assert event.success is True
    assert "test_devtasks.py" not in event.action
    mock_db.commit.assert_awaited_once()


@pytest.mark.parametrize("task_id", ["db_backup", "db_restore_test"])
def test_backup_tasks_run_fixed_commands_without_client_parameters(
    task_id, enabled_app, mock_db, monkeypatch
):
    task = next(task for task in TASKS if task.id == task_id)
    calls = []

    async def fake_create_subprocess_exec(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeProcess(lines=[b"completed\n"])

    monkeypatch.setattr(
        runner.asyncio,
        "create_subprocess_exec",
        fake_create_subprocess_exec,
    )
    with use_admin(enabled_app, mock_db) as client:
        response = client.post(f"/platform/dev/tasks/{task_id}/run", json={})

    assert response.status_code == 200
    assert calls[0][0] == task.command
    assert calls[0][1]["cwd"] == task.cwd
    assert task.timeout == 1800
    assert task.parameters == ()
    assert mock_db.added[0].action == f"dev_task_run:{task_id}"
    mock_db.commit.assert_awaited_once()


def test_allowlisted_commands_are_argument_sequences():
    dangerous = set(";&|><$`")
    by_id = {task.id: task for task in TASKS}

    assert by_id["db_start"].command == ("docker", "compose", "up", "-d")
    assert by_id["db_start"].cwd == BACKEND_DIR
    assert by_id["db_status"].command == ("docker", "ps")
    assert by_id["db_backup"].command[-1].endswith(
        "scripts\\backup\\backup-db.ps1"
    )
    assert by_id["db_restore_test"].command[-1].endswith(
        "scripts\\backup\\restore-test.ps1"
    )
    assert by_id["alembic_current"].command[-2:] == ("alembic", "current")
    assert by_id["alembic_upgrade"].command[-2:] == ("upgrade", "head")
    assert by_id["run_tests"].command[-2:] == ("pytest", "-q")
    assert by_id["frontend_serve"].cwd == FRONTEND_DIR
    for task in TASKS:
        assert isinstance(task.command, tuple)
        assert all(not dangerous.intersection(argument) for argument in task.command)
        assert "-v" not in task.command
        assert "down" not in task.command


def test_only_one_oneshot_process_runs_at_a_time(monkeypatch):
    async def scenario():
        manager = DevTaskManager()
        task = next(task for task in TASKS if task.id == "db_status")
        processes = []
        started = asyncio.Event()

        async def fake_create_subprocess_exec(*args, **kwargs):
            process = FakeProcess(pid=5000 + len(processes), held=True)
            processes.append(process)
            started.set()
            return process

        monkeypatch.setattr(
            runner.asyncio,
            "create_subprocess_exec",
            fake_create_subprocess_exec,
        )
        first = await manager.start(task, {})
        await asyncio.wait_for(started.wait(), timeout=1)
        second = await manager.start(task, {})
        await asyncio.sleep(0)
        assert len(processes) == 1

        started.clear()
        processes[0].finish(0)
        await asyncio.wait_for(started.wait(), timeout=1)
        assert len(processes) == 2
        processes[1].finish(0)
        await asyncio.wait_for(
            asyncio.gather(first.worker, second.worker),
            timeout=1,
        )
        assert len(processes) == 2
        assert first.status == second.status == "ok"

    asyncio.run(scenario())


def test_oneshot_timeout_kills_process(monkeypatch):
    async def scenario():
        manager = DevTaskManager()
        task = next(task for task in TASKS if task.id == "db_status")
        task = type(task)(**{**task.__dict__, "timeout": 0.01})
        process = FakeProcess(held=True)

        async def fake_create_subprocess_exec(*args, **kwargs):
            if args[0] == "taskkill":
                process.finish(-9)
                return ImmediateKiller()
            return process

        monkeypatch.setattr(
            runner.asyncio,
            "create_subprocess_exec",
            fake_create_subprocess_exec,
        )
        run = await manager.start(task, {})
        await asyncio.wait_for(run.worker, timeout=1)
        assert process.returncode == -9
        assert run.status == "timeout"

    asyncio.run(scenario())


def test_output_is_masked_before_it_is_stored(monkeypatch):
    async def scenario():
        monkeypatch.setenv("API_TOKEN", "token-value")
        process = FakeProcess(
            lines=[
                b"API_TOKEN=token-value\n",
                b"postgresql://user:db-password@localhost/fleet\n",
            ]
        )
        run = TaskRun(id="run-id", task_id="db_status", kind="oneshot")
        manager = DevTaskManager()
        await manager._read_output(run, process)
        stored = "\n".join(line for _, line in run.output)
        assert "token-value" not in stored
        assert "db-password" not in stored
        assert "***@" in stored

    asyncio.run(scenario())


def test_task_environment_merges_dotenv_and_prefers_process_environment(
    tmp_path,
    monkeypatch,
):
    (tmp_path / ".env").write_text(
        "APP_ENV=development\nAPI_TOKEN=file-secret\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(runner, "BACKEND_DIR", tmp_path)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("API_TOKEN", raising=False)

    environment = runner.task_environment()

    assert environment["APP_ENV"] == "production"
    assert environment["API_TOKEN"] == "file-secret"


def test_stop_kills_windows_process_tree(monkeypatch):
    async def scenario():
        manager = DevTaskManager()
        service = next(task for task in TASKS if task.id == "frontend_serve")
        process = FakeProcess(pid=3210, held=True)
        calls = []

        async def fake_create_subprocess_exec(*args, **kwargs):
            calls.append(args)
            if args[0] == "taskkill":
                process.finish(-9)
                return ImmediateKiller()
            return process

        monkeypatch.setattr(runner, "IS_WINDOWS", True)
        monkeypatch.setattr(
            runner.asyncio,
            "create_subprocess_exec",
            fake_create_subprocess_exec,
        )
        run = await manager.start(service, {})
        await manager.stop(run)
        assert calls[-1] == ("taskkill", "/PID", "3210", "/T", "/F")
        assert run.status == "ok"
        assert run.service_state == "stopped"

    asyncio.run(scenario())


def test_run_history_limit_and_output_ring_are_bounded():
    manager = DevTaskManager()
    run = TaskRun(id="run-id", task_id="db_status", kind="oneshot")
    for index in range(501):
        run.append_output(str(index), {})

    assert len(run.output) == 500
    assert run.output[0] == (2, "1")
    assert len(manager.list_runs(50)) == 0
