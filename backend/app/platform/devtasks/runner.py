import asyncio
import os
import re
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from uuid import uuid4

from dotenv import dotenv_values

from app.config import BACKEND_DIR
from app.platform.devtasks.tasks import TaskSpec

IS_WINDOWS = sys.platform == "win32"
MAX_OUTPUT_LINES = 500
URL_CREDENTIALS = re.compile(
    r"(?i)([a-z][a-z0-9+.-]*://)[^:/@\s]+:[^@/\s]*@"
)


class TaskManagerError(Exception):
    """Base error for task lifecycle conflicts."""


class TaskAlreadyRunning(TaskManagerError):
    """Raised when a service already has a live instance."""


class TaskNotRunning(TaskManagerError):
    """Raised when a run is not active."""


@dataclass
class TaskRun:
    id: str
    task_id: str
    kind: str
    status: str = "running"
    service_state: str | None = None
    started_at: float = field(default_factory=time.monotonic)
    finished_at: float | None = None
    duration_seconds: float | None = None
    return_code: int | None = None
    total_lines: int = 0
    output: deque[tuple[int, str]] = field(
        default_factory=lambda: deque(maxlen=MAX_OUTPUT_LINES)
    )
    process: asyncio.subprocess.Process | None = field(default=None, repr=False)
    worker: asyncio.Task[None] | None = field(default=None, repr=False)
    stop_requested: bool = False

    @property
    def running(self) -> bool:
        return self.status == "running"

    def append_output(self, line: str, environment: dict[str, str]) -> None:
        self.total_lines += 1
        self.output.append((self.total_lines, mask_output(line, environment)))

    def finish(self, status: str) -> None:
        self.status = status
        if self.kind == "service":
            self.service_state = "stopped"
        self.finished_at = time.monotonic()
        self.duration_seconds = max(0, self.finished_at - self.started_at)

    def serialize(self) -> dict[str, object]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "kind": self.kind,
            "status": self.status,
            "service_state": self.service_state,
            "duration_seconds": self.duration_seconds
            if self.duration_seconds is not None
            else max(0, time.monotonic() - self.started_at),
            "output_line_count": self.total_lines,
        }


def mask_output(line: str, environment: dict[str, str]) -> str:
    masked = URL_CREDENTIALS.sub(r"\1***@", line)
    secret_values = sorted(
        (
            value
            for name, value in environment.items()
            if any(
                marker in name.upper()
                for marker in ("PASSWORD", "KEY", "TOKEN", "SECRET")
            )
            and value
        ),
        key=len,
        reverse=True,
    )
    for secret in secret_values:
        masked = masked.replace(secret, "***")
    return masked


def task_environment() -> dict[str, str]:
    dotenv_environment = {
        name: value
        for name, value in dotenv_values(BACKEND_DIR / ".env").items()
        if value is not None
    }
    dotenv_environment.update(os.environ)
    return dotenv_environment


class DevTaskManager:
    def __init__(self) -> None:
        self.runs: dict[str, TaskRun] = {}
        self._oneshot_lock = asyncio.Lock()
        self._service_lock = asyncio.Lock()
        self._shutdown = False

    def get_run(self, run_id: str) -> TaskRun | None:
        return self.runs.get(run_id)

    def get_active_service(self, task_id: str) -> TaskRun | None:
        return next(
            (
                run
                for run in reversed(tuple(self.runs.values()))
                if run.task_id == task_id
                and run.kind == "service"
                and run.running
            ),
            None,
        )

    def list_runs(self, limit: int) -> list[TaskRun]:
        return list(reversed(tuple(self.runs.values())))[:limit]

    async def start(self, task: TaskSpec, parameters: dict[str, str]) -> TaskRun:
        if self._shutdown:
            raise TaskManagerError("Task manager is shutting down.")
        run = TaskRun(id=str(uuid4()), task_id=task.id, kind=task.kind)
        if task.kind == "service":
            async with self._service_lock:
                if self.get_active_service(task.id) is not None:
                    raise TaskAlreadyRunning
                process = await self._spawn(task, parameters)
                run.process = process
                run.service_state = "running"
                self.runs[run.id] = run
                run.worker = asyncio.create_task(self._watch_service(run, process))
        else:
            self.runs[run.id] = run
            run.worker = asyncio.create_task(self._run_oneshot(run, task, parameters))
        return run

    async def _spawn(
        self,
        task: TaskSpec,
        parameters: dict[str, str],
    ) -> asyncio.subprocess.Process:
        command = [*task.command]
        if "test_file" in parameters:
            command.append(parameters["test_file"])
        return await asyncio.create_subprocess_exec(
            *command,
            cwd=task.cwd,
            env=task_environment(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

    async def _read_output(
        self,
        run: TaskRun,
        process: asyncio.subprocess.Process,
    ) -> None:
        if process.stdout is None:
            return
        environment = task_environment()
        while line := await process.stdout.readline():
            run.append_output(
                line.decode("utf-8", errors="replace").rstrip("\r\n"),
                environment,
            )

    async def _run_oneshot(
        self,
        run: TaskRun,
        task: TaskSpec,
        parameters: dict[str, str],
    ) -> None:
        async with self._oneshot_lock:
            try:
                process = await self._spawn(task, parameters)
            except OSError:
                run.append_output(
                    "The task process could not be started.",
                    os.environ.copy(),
                )
                run.finish("failed")
                return
            run.process = process
            reader = asyncio.create_task(self._read_output(run, process))
            timed_out = False
            try:
                await asyncio.wait_for(process.wait(), timeout=task.timeout)
            except TimeoutError:
                timed_out = True
                try:
                    await self._kill_process_tree(process)
                except OSError:
                    run.append_output(
                        "The task timed out and its process could not be stopped.",
                        os.environ.copy(),
                    )
                    run.finish("failed")
                    await reader
                    return
                await process.wait()
            await reader
            run.return_code = process.returncode
            if timed_out:
                run.finish("timeout")
            elif run.stop_requested:
                run.finish("ok")
            else:
                run.finish("ok" if process.returncode == 0 else "failed")

    async def _watch_service(
        self,
        run: TaskRun,
        process: asyncio.subprocess.Process,
    ) -> None:
        reader = asyncio.create_task(self._read_output(run, process))
        await process.wait()
        await reader
        run.return_code = process.returncode
        if run.stop_requested:
            run.finish("ok")
        else:
            run.finish("ok" if process.returncode == 0 else "failed")

    async def stop(self, run: TaskRun) -> None:
        if not run.running:
            raise TaskNotRunning
        run.stop_requested = True
        process = run.process
        if process is None:
            if run.worker is not None:
                run.worker.cancel()
                try:
                    await run.worker
                except asyncio.CancelledError:
                    run.finish("ok")
            return
        if process.returncode is None:
            await self._kill_process_tree(process)
        if run.worker is not None:
            await run.worker

    async def _kill_process_tree(
        self,
        process: asyncio.subprocess.Process,
    ) -> None:
        pid = process.pid
        if pid is None or not isinstance(pid, int) or pid <= 0:
            raise OSError("Invalid child process ID.")
        if IS_WINDOWS:
            killer = await asyncio.create_subprocess_exec(
                "taskkill",
                "/PID",
                str(pid),
                "/T",
                "/F",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            result = await killer.wait()
            if result != 0 and process.returncode is None:
                raise OSError("Windows could not stop the task process tree.")
        elif process.returncode is None:
            process.kill()

    async def shutdown(self) -> None:
        self._shutdown = True
        failures: list[Exception] = []
        for run in tuple(self.runs.values()):
            if run.running:
                try:
                    await self.stop(run)
                except (OSError, TaskManagerError) as error:
                    failures.append(error)
        if failures:
            raise RuntimeError(
                f"Could not stop {len(failures)} development task process(es)."
            ) from failures[0]


def read_output(run: TaskRun, offset: int) -> dict[str, object]:
    oldest = run.output[0][0] if run.output else run.total_lines + 1
    lines = [
        line
        for index, line in run.output
        if index > max(offset, oldest - 1)
    ]
    return {
        "run_id": run.id,
        "offset": run.total_lines,
        "lines": lines,
        "status": run.status,
        "service_state": run.service_state,
        "duration_seconds": run.duration_seconds
        if run.duration_seconds is not None
        else max(0, time.monotonic() - run.started_at),
    }
