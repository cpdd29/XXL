from __future__ import annotations

import asyncio
from queue import Empty

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    WebSocketException,
    status,
)
from starlette.websockets import WebSocketState

from app.platform.auth.authz import authenticate_websocket, require_authenticated_user, require_permission
from app.modules.dispatch.schemas.tasks import (
    Task,
    TaskActionResponse,
    TaskListResponse,
    TaskRealtimeResponse,
    TaskStepsResponse,
)
from app.modules.organization.application.tenancy_service import ROOT_SCOPE_ROLES, resolve_scope
from app.modules.dispatch.application.task_service import cancel_task, get_task, get_task_steps, list_tasks, retry_task
from app.modules.dispatch.workflow_runtime.workflow_realtime_service import workflow_realtime_service
from app.platform.persistence.runtime_store import store

router = APIRouter(dependencies=[Depends(require_authenticated_user)])


def _resolve_task_scope(
    *,
    current_user: dict,
    tenant_id: str | None = None,
    project_id: str | None = None,
    environment: str | None = None,
) -> dict[str, str] | None:
    role = str(current_user.get("role") or "").strip().lower()
    if role in ROOT_SCOPE_ROLES and not any(
        str(value or "").strip()
        for value in (tenant_id, project_id, environment)
    ):
        return None
    return resolve_scope(
        current_user=current_user,
        tenant_id=tenant_id,
        project_id=project_id,
        environment=environment,
    )


def _build_task_realtime_snapshot(
    task_id: str,
    *,
    scope: dict[str, str] | None,
    message_type: str = "snapshot",
) -> TaskRealtimeResponse:
    task_payload = Task(**get_task(task_id, scope=scope))
    steps_payload = TaskStepsResponse(**get_task_steps(task_id))
    payload_type = "task.keepalive" if message_type == "keepalive" else "task.snapshot"
    return TaskRealtimeResponse(
        type=payload_type,
        message_type=message_type,
        task_id=task_id,
        workflow_id=task_payload.workflow_id,
        timestamp=store.now_string(),
        task=task_payload,
        steps=steps_payload,
    )


@router.get(
    "",
    response_model=TaskListResponse,
    dependencies=[Depends(require_permission("tasks:read"))],
)
def list_tasks_route(
    status: str | None = Query(default=None),
    search: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    agent: str | None = Query(default=None),
    channel: str | None = Query(default=None),
    tenant_id: str | None = Header(default=None, alias="X-WorkBot-Tenant-Id"),
    project_id: str | None = Header(default=None, alias="X-WorkBot-Project-Id"),
    environment: str | None = Header(default=None, alias="X-WorkBot-Environment"),
    current_user: dict = Depends(require_authenticated_user),
) -> TaskListResponse:
    scope = _resolve_task_scope(
        current_user=current_user,
        tenant_id=tenant_id,
        project_id=project_id,
        environment=environment,
    )
    return TaskListResponse(
        **list_tasks(
            status_filter=status,
            search=search,
            priority_filter=priority,
            agent_filter=agent,
            channel_filter=channel,
            scope=scope,
        )
    )


@router.websocket("/realtime")
async def realtime_tasks_route(websocket: WebSocket) -> None:
    current_user = authenticate_websocket(websocket, permission="tasks:read")
    status_filter = str(websocket.query_params.get("status") or "").strip() or None
    search = str(websocket.query_params.get("search") or "").strip() or None
    priority_filter = str(websocket.query_params.get("priority") or "").strip() or None
    agent_filter = str(websocket.query_params.get("agent") or "").strip() or None
    channel_filter = str(websocket.query_params.get("channel") or "").strip() or None
    tenant_id = str(websocket.query_params.get("tenantId") or "").strip() or None
    project_id = str(websocket.query_params.get("projectId") or "").strip() or None
    environment = str(websocket.query_params.get("environment") or "").strip() or None
    try:
        scope = _resolve_task_scope(
            current_user=current_user,
            tenant_id=tenant_id,
            project_id=project_id,
            environment=environment,
        )
    except Exception as exc:  # pragma: no cover - defensive websocket guard
        reason = str(getattr(exc, "detail", "") or exc)
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason=reason or "Scope resolution failed",
        ) from exc

    await websocket.accept()
    await websocket.send_json(
        TaskListResponse(
            **list_tasks(
                status_filter=status_filter,
                search=search,
                priority_filter=priority_filter,
                agent_filter=agent_filter,
                channel_filter=channel_filter,
                scope=scope,
            )
        ).model_dump(mode="json", by_alias=True)
    )
    subscriber = workflow_realtime_service._subscribe_all()
    try:
        while True:
            try:
                await asyncio.to_thread(subscriber.get, True, 3.0)
            except Empty:
                if websocket.client_state is WebSocketState.DISCONNECTED:
                    break
            payload = TaskListResponse(
                **list_tasks(
                    status_filter=status_filter,
                    search=search,
                    priority_filter=priority_filter,
                    agent_filter=agent_filter,
                    channel_filter=channel_filter,
                    scope=scope,
                )
            )
            await websocket.send_json(payload.model_dump(mode="json", by_alias=True))
    except WebSocketDisconnect:
        return
    finally:
        workflow_realtime_service._unsubscribe_all(subscriber)


@router.websocket("/{task_id}/realtime")
async def realtime_task_detail_route(task_id: str, websocket: WebSocket) -> None:
    current_user = authenticate_websocket(websocket, permission="tasks:read")
    tenant_id = str(websocket.query_params.get("tenantId") or "").strip() or None
    project_id = str(websocket.query_params.get("projectId") or "").strip() or None
    environment = str(websocket.query_params.get("environment") or "").strip() or None

    try:
        scope = _resolve_task_scope(
            current_user=current_user,
            tenant_id=tenant_id,
            project_id=project_id,
            environment=environment,
        )
        snapshot = _build_task_realtime_snapshot(task_id, scope=scope)
    except HTTPException as exc:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason=str(exc.detail),
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive websocket guard
        reason = str(getattr(exc, "detail", "") or exc)
        raise WebSocketException(
            code=status.WS_1011_INTERNAL_ERROR,
            reason=reason or "Task realtime unavailable",
        ) from exc

    await websocket.accept()
    await websocket.send_json(snapshot.model_dump(mode="json", by_alias=True))

    workflow_id = str(snapshot.workflow_id or "").strip()
    if not workflow_id:
        try:
            while True:
                await asyncio.sleep(3)
                if websocket.client_state is WebSocketState.DISCONNECTED:
                    break
                keepalive = _build_task_realtime_snapshot(task_id, scope=scope, message_type="keepalive")
                await websocket.send_json(keepalive.model_dump(mode="json", by_alias=True))
        except WebSocketDisconnect:
            return
        return

    subscriber = workflow_realtime_service._subscribe(workflow_id)
    try:
        while True:
            try:
                await asyncio.to_thread(subscriber.get, True, 3.0)
            except Empty:
                if websocket.client_state is WebSocketState.DISCONNECTED:
                    break
                keepalive = _build_task_realtime_snapshot(task_id, scope=scope, message_type="keepalive")
                await websocket.send_json(keepalive.model_dump(mode="json", by_alias=True))
                continue

            if websocket.client_state is WebSocketState.DISCONNECTED:
                break
            snapshot = _build_task_realtime_snapshot(task_id, scope=scope)
            await websocket.send_json(snapshot.model_dump(mode="json", by_alias=True))
    except WebSocketDisconnect:
        return
    finally:
        workflow_realtime_service._unsubscribe(workflow_id, subscriber)


@router.get(
    "/{task_id}",
    response_model=Task,
    dependencies=[Depends(require_permission("tasks:read"))],
)
def get_task_route(
    task_id: str,
    tenant_id: str | None = Header(default=None, alias="X-WorkBot-Tenant-Id"),
    project_id: str | None = Header(default=None, alias="X-WorkBot-Project-Id"),
    environment: str | None = Header(default=None, alias="X-WorkBot-Environment"),
    current_user: dict = Depends(require_authenticated_user),
) -> Task:
    scope = _resolve_task_scope(
        current_user=current_user,
        tenant_id=tenant_id,
        project_id=project_id,
        environment=environment,
    )
    return Task(**get_task(task_id, scope=scope))


@router.get(
    "/{task_id}/steps",
    response_model=TaskStepsResponse,
    dependencies=[Depends(require_permission("tasks:read"))],
)
def get_task_steps_route(task_id: str) -> TaskStepsResponse:
    return TaskStepsResponse(**get_task_steps(task_id))


@router.delete(
    "/{task_id}",
    response_model=TaskActionResponse,
    dependencies=[Depends(require_permission("tasks:write"))],
)
def cancel_task_route(task_id: str) -> TaskActionResponse:
    return TaskActionResponse(**cancel_task(task_id))


@router.post(
    "/{task_id}/retry",
    response_model=TaskActionResponse,
    dependencies=[Depends(require_permission("tasks:write"))],
)
def retry_task_route(task_id: str) -> TaskActionResponse:
    return TaskActionResponse(**retry_task(task_id))
