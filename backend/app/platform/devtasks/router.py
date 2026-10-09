import ipaddress
import re
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.platform.audit import record_platform_event
from app.platform.auth import PlatformPrincipal, require_super_admin
from app.platform.devtasks.runner import (
    DevTaskManager,
    TaskAlreadyRunning,
    TaskNotRunning,
    read_output,
)
from app.platform.devtasks.tasks import TASKS, TASKS_BY_ID, serialize_task

router = APIRouter(prefix="/platform/dev", tags=["platform-dev"])


class TaskRunBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    test_file: StrictStr | None = Field(default=None, max_length=120)


async def _audit(
    db: AsyncSession,
    request: Request,
    *,
    action: str,
    success: bool,
    principal: PlatformPrincipal | None = None,
) -> None:
    record_platform_event(
        db,
        request,
        action=action,
        target_type="dev_task",
        success=success,
        super_admin_id=principal.super_admin.id if principal else None,
        target_id=None,
        user_agent="",
    )
    await db.commit()


def _action(verb: str, task_id: str | None) -> str:
    safe_task_id = task_id if task_id in TASKS_BY_ID else "unknown"
    return f"dev_task_{verb}:{safe_task_id}"


def _is_loopback(request: Request) -> bool:
    if request.client is None:
        return False
    try:
        address = ipaddress.ip_address(request.client.host)
    except ValueError:
        return False
    return address.is_loopback


async def require_dev_super_admin(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlatformPrincipal:
    path_task_id = request.path_params.get("task_id")
    if not _is_loopback(request):
        await _audit(
            db,
            request,
            action=_action("rejected", path_task_id),
            success=False,
        )
        raise HTTPException(403, "Request not allowed")
    origin = request.headers.get("origin")
    if (
        request.method == "POST"
        and origin is not None
        and origin not in settings.allowed_web_origins
    ):
        await _audit(
            db,
            request,
            action=_action("rejected", path_task_id),
            success=False,
        )
        raise HTTPException(403, "Request not allowed")
    try:
        return await require_super_admin(request, db)
    except HTTPException:
        await _audit(
            db,
            request,
            action=_action("rejected", path_task_id),
            success=False,
        )
        raise


def _manager(request: Request) -> DevTaskManager:
    manager = getattr(request.app.state, "dev_task_manager", None)
    if not isinstance(manager, DevTaskManager):
        raise HTTPException(503, "Development task runner is unavailable")
    return manager


async def _reject(
    db: AsyncSession,
    request: Request,
    *,
    status_code: int,
    task_id: str | None = None,
) -> NoReturn:
    await _audit(
        db,
        request,
        action=_action("rejected", task_id),
        success=False,
    )
    raise HTTPException(status_code, "Invalid development task request")


async def _parse_run_body(
    request: Request,
    db: AsyncSession,
    task_id: str,
) -> dict[str, str]:
    try:
        body = TaskRunBody.model_validate_json(await request.body())
    except ValidationError:
        await _reject(db, request, status_code=422, task_id=task_id)

    parameters = body.model_dump(exclude_unset=True)
    if "test_file" in parameters:
        task_parameters = {
            parameter.name: parameter
            for parameter in TASKS_BY_ID[task_id].parameters
        }
        parameter = task_parameters.get("test_file")
        value = parameters["test_file"]
        if (
            parameter is None
            or not isinstance(value, str)
            or re.fullmatch(parameter.pattern, value) is None
        ):
            await _reject(db, request, status_code=422, task_id=task_id)
        parameters["test_file"] = value
    return parameters


def _parse_integer(
    value: str | None,
    *,
    default: int,
    minimum: int,
    maximum: int | None = None,
) -> int | None:
    if value is None:
        parsed = default
    elif re.fullmatch(r"[0-9]+", value) is None:
        return None
    else:
        try:
            parsed = int(value)
        except ValueError:
            return None
    if parsed < minimum or (maximum is not None and parsed > maximum):
        return None
    return parsed


@router.get("/tasks", dependencies=[Depends(require_dev_super_admin)])
async def list_tasks(
    request: Request,
) -> list[dict[str, object]]:
    _manager(request)
    return [serialize_task(task) for task in TASKS]


@router.post("/tasks/{task_id}/run")
async def run_task(
    task_id: str,
    request: Request,
    principal: PlatformPrincipal = Depends(require_dev_super_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    task = TASKS_BY_ID.get(task_id)
    if task is None:
        await _reject(db, request, status_code=404)
    parameters = await _parse_run_body(request, db, task_id)
    manager = _manager(request)
    try:
        run = await manager.start(task, parameters)
    except TaskAlreadyRunning:
        await _reject(db, request, status_code=409, task_id=task_id)
    except OSError:
        await _reject(db, request, status_code=503, task_id=task_id)
    await _audit(
        db,
        request,
        action=_action("run", task_id),
        success=True,
        principal=principal,
    )
    return run.serialize()


@router.post("/runs/{run_id}/stop")
async def stop_run(
    run_id: str,
    request: Request,
    principal: PlatformPrincipal = Depends(require_dev_super_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    manager = _manager(request)
    run = manager.get_run(run_id)
    if run is None:
        await _reject(db, request, status_code=404)
    try:
        await manager.stop(run)
    except TaskNotRunning:
        await _reject(db, request, status_code=409, task_id=run.task_id)
    except OSError:
        await _reject(db, request, status_code=503, task_id=run.task_id)
    await _audit(
        db,
        request,
        action=_action("stop", run.task_id),
        success=True,
        principal=principal,
    )
    return run.serialize()


@router.get("/runs", dependencies=[Depends(require_dev_super_admin)])
async def list_runs(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    limit = _parse_integer(
        request.query_params.get("limit"),
        default=20,
        minimum=1,
        maximum=50,
    )
    if limit is None:
        await _reject(db, request, status_code=422)
    return {
        "runs": [run.serialize() for run in _manager(request).list_runs(limit)],
    }


@router.get("/runs/{run_id}", dependencies=[Depends(require_dev_super_admin)])
async def get_run_output(
    run_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    offset = _parse_integer(
        request.query_params.get("offset"),
        default=0,
        minimum=0,
    )
    if offset is None:
        await _reject(db, request, status_code=422)
    run = _manager(request).get_run(run_id)
    if run is None:
        await _reject(db, request, status_code=404)
    return read_output(run, offset)
