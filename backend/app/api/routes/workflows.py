from fastapi import APIRouter, Depends, Query, WebSocket

from app.core.authz import authenticate_websocket, require_authenticated_user, require_permission
from app.schemas.workflows import (
    InternalEventDelivery,
    InternalEventDeliveryActionResponse,
    InternalEventDeliveryListResponse,
    InternalWorkflowTriggerRequest,
    RunWorkflowRequest,
    UpsertWorkflowRequest,
    WorkflowActionResponse,
    WorkflowListResponse,
    WorkflowMonitorResponse,
    WorkflowRun,
    WorkflowRunListResponse,
)
from app.services.workflow_service import (
    create_workflow,
    get_internal_event_delivery,
    get_workflow_monitor,
    get_run,
    list_runs,
    list_internal_event_deliveries,
    list_workflows,
    replay_internal_event_delivery,
    retry_internal_event_delivery,
    run_workflow,
    tick_run,
    trigger_workflow_internal,
    update_workflow,
)
from app.services.workflow_realtime_service import workflow_realtime_service

router = APIRouter(dependencies=[Depends(require_authenticated_user)])


@router.get(
    "",
    response_model=WorkflowListResponse,
    dependencies=[Depends(require_permission("workflows:read"))],
)
def list_workflows_route() -> WorkflowListResponse:
    return WorkflowListResponse(**list_workflows())


@router.post(
    "",
    response_model=WorkflowActionResponse,
    dependencies=[Depends(require_permission("workflows:write"))],
)
def create_workflow_route(payload: UpsertWorkflowRequest) -> WorkflowActionResponse:
    return WorkflowActionResponse(**create_workflow(payload.model_dump()))


@router.put(
    "/{workflow_id}",
    response_model=WorkflowActionResponse,
    dependencies=[Depends(require_permission("workflows:write"))],
)
def update_workflow_route(
    workflow_id: str, payload: UpsertWorkflowRequest
) -> WorkflowActionResponse:
    return WorkflowActionResponse(**update_workflow(workflow_id, payload.model_dump()))


@router.post(
    "/internal/{event_name:path}",
    response_model=WorkflowActionResponse,
    dependencies=[Depends(require_permission("workflows:write"))],
)
def trigger_internal_workflow_route(
    event_name: str,
    payload: InternalWorkflowTriggerRequest | None = None,
) -> WorkflowActionResponse:
    request_payload = payload or InternalWorkflowTriggerRequest()
    return WorkflowActionResponse(
        **trigger_workflow_internal(
            event_name,
            request_payload.payload,
            source=request_payload.source,
            idempotency_key=request_payload.idempotency_key,
        )
    )


@router.get(
    "/internal-deliveries",
    response_model=InternalEventDeliveryListResponse,
    dependencies=[Depends(require_permission("workflows:read"))],
)
def list_internal_event_deliveries_route(
    status: str | None = Query(default=None),
    event_name: str | None = Query(default=None, alias="eventName"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> InternalEventDeliveryListResponse:
    return InternalEventDeliveryListResponse(
        **list_internal_event_deliveries(
            status_filter=status,
            event_name=event_name,
            limit=limit,
            offset=offset,
        )
    )


@router.get(
    "/internal-deliveries/{delivery_id}",
    response_model=InternalEventDelivery,
    dependencies=[Depends(require_permission("workflows:read"))],
)
def get_internal_event_delivery_route(delivery_id: str) -> InternalEventDelivery:
    return InternalEventDelivery(**get_internal_event_delivery(delivery_id))


@router.post(
    "/internal-deliveries/{delivery_id}/retry",
    response_model=InternalEventDeliveryActionResponse,
    dependencies=[Depends(require_permission("workflows:write"))],
)
def retry_internal_event_delivery_route(
    delivery_id: str,
) -> InternalEventDeliveryActionResponse:
    return InternalEventDeliveryActionResponse(**retry_internal_event_delivery(delivery_id))


@router.post(
    "/internal-deliveries/{delivery_id}/replay",
    response_model=InternalEventDeliveryActionResponse,
    dependencies=[Depends(require_permission("workflows:write"))],
)
def replay_internal_event_delivery_route(
    delivery_id: str,
) -> InternalEventDeliveryActionResponse:
    return InternalEventDeliveryActionResponse(**replay_internal_event_delivery(delivery_id))


@router.post(
    "/{workflow_id}/run",
    response_model=WorkflowActionResponse,
    dependencies=[Depends(require_permission("workflows:write"))],
)
def run_workflow_route(
    workflow_id: str,
    payload: RunWorkflowRequest | None = None,
) -> WorkflowActionResponse:
    return WorkflowActionResponse(**run_workflow(workflow_id, payload.model_dump() if payload else None))


@router.get(
    "/{workflow_id}/monitor",
    response_model=WorkflowMonitorResponse,
    dependencies=[Depends(require_permission("workflows:read"))],
)
def get_workflow_monitor_route(
    workflow_id: str,
    task_id: str | None = Query(default=None, alias="taskId"),
    limit: int = Query(default=20, ge=1, le=100),
    unhealthy_only: bool = Query(default=False, alias="unhealthyOnly"),
) -> WorkflowMonitorResponse:
    return WorkflowMonitorResponse(
        **get_workflow_monitor(
            workflow_id,
            task_id=task_id,
            limit=limit,
            unhealthy_only=unhealthy_only,
        )
    )


@router.get(
    "/{workflow_id}/runs",
    response_model=WorkflowRunListResponse,
    dependencies=[Depends(require_permission("workflows:read"))],
)
def list_workflow_runs_route(
    workflow_id: str,
    task_id: str | None = Query(default=None, alias="taskId"),
) -> WorkflowRunListResponse:
    return WorkflowRunListResponse(**list_runs(workflow_id=workflow_id, task_id=task_id))


@router.get(
    "/runs/{run_id}",
    response_model=WorkflowRun,
    dependencies=[Depends(require_permission("workflows:read"))],
)
def get_workflow_run_route(run_id: str) -> WorkflowRun:
    return WorkflowRun(**get_run(run_id))


@router.post(
    "/runs/{run_id}/tick",
    response_model=WorkflowRun,
    dependencies=[Depends(require_permission("workflows:write"))],
)
def tick_workflow_run_route(run_id: str) -> WorkflowRun:
    return WorkflowRun(**tick_run(run_id))


@router.websocket("/{workflow_id}/realtime")
async def workflow_realtime_route(websocket: WebSocket, workflow_id: str) -> None:
    authenticate_websocket(websocket, permission="workflows:read")
    await workflow_realtime_service.stream(websocket, workflow_id)
