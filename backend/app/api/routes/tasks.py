from fastapi import APIRouter, Depends, Header, Query

from app.core.authz import require_authenticated_user, require_permission
from app.schemas.tasks import Task, TaskActionResponse, TaskListResponse, TaskStepsResponse
from app.services.tenancy_service import resolve_scope
from app.services.task_service import cancel_task, get_task, get_task_steps, list_tasks, retry_task

router = APIRouter(dependencies=[Depends(require_authenticated_user)])


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
    scope = resolve_scope(
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
    scope = resolve_scope(
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
