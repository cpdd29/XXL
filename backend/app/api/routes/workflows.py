from typing import Any

from fastapi import APIRouter, Depends, Header, Query, WebSocket
from fastapi.responses import JSONResponse

from app.core.authz import authenticate_websocket, require_authenticated_user, require_permission
from app.schemas.approvals import ApprovalActionResponse, ApprovalItem
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
    WorkflowRunManualHandoffRequest,
)
from app.services.control_plane_approval_service import (
    create_bound_approval,
    require_approved_execution,
)
from app.services.tenancy_service import resolve_scope
from app.services.workflow_service import (
    create_workflow,
    get_internal_event_delivery,
    get_workflow_monitor,
    get_run,
    list_runs,
    list_internal_event_deliveries,
    request_manual_handoff,
    list_workflows,
    replay_internal_event_delivery,
    retry_internal_event_delivery,
    run_workflow,
    tick_run,
    trigger_workflow_internal,
    update_workflow,
)
from app.services.workflow_realtime_service import workflow_realtime_service
from app.services.control_plane_audit_service import append_control_plane_audit_log

router = APIRouter(dependencies=[Depends(require_authenticated_user)])


def _operator_identity(current_user: dict[str, Any]) -> str:
    return (
        str(current_user.get("email") or "").strip()
        or str(current_user.get("id") or "").strip()
        or "system"
    )


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
    dependencies=[Depends(require_permission("workflows:definition:write"))],
)
def create_workflow_route(
    payload: UpsertWorkflowRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> WorkflowActionResponse:
    response = WorkflowActionResponse(**create_workflow(payload.model_dump()))
    append_control_plane_audit_log(
        action="workflow.definition.created",
        user=_operator_identity(current_user),
        resource="workflow.definition",
        details=f"创建工作流 {response.workflow.id if response.workflow else 'unknown'}",
    )
    return response


@router.put(
    "/{workflow_id}",
    response_model=WorkflowActionResponse,
    dependencies=[Depends(require_permission("workflows:definition:write"))],
)
def update_workflow_route(
    workflow_id: str,
    payload: UpsertWorkflowRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> WorkflowActionResponse:
    response = WorkflowActionResponse(**update_workflow(workflow_id, payload.model_dump()))
    append_control_plane_audit_log(
        action="workflow.definition.updated",
        user=_operator_identity(current_user),
        resource=f"workflow.definition.{workflow_id}",
        details=f"更新工作流定义 {workflow_id}",
    )
    return response


@router.post(
    "/internal/{event_name:path}",
    response_model=WorkflowActionResponse,
    dependencies=[Depends(require_permission("workflows:trigger:internal"))],
)
def trigger_internal_workflow_route(
    event_name: str,
    payload: InternalWorkflowTriggerRequest | None = None,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> WorkflowActionResponse:
    request_payload = payload or InternalWorkflowTriggerRequest()
    response = WorkflowActionResponse(
        **trigger_workflow_internal(
            event_name,
            request_payload.payload,
            source=request_payload.source,
            idempotency_key=request_payload.idempotency_key,
        )
    )
    append_control_plane_audit_log(
        action="workflow.internal.triggered",
        user=_operator_identity(current_user),
        resource=f"workflow.internal.{event_name}",
        details=f"触发内部工作流事件 {event_name}",
    )
    return response


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
    dependencies=[Depends(require_permission("workflows:delivery:retry"))],
)
def retry_internal_event_delivery_route(
    delivery_id: str,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> InternalEventDeliveryActionResponse:
    response = InternalEventDeliveryActionResponse(**retry_internal_event_delivery(delivery_id))
    append_control_plane_audit_log(
        action="workflow.delivery.retried",
        user=_operator_identity(current_user),
        resource=f"workflow.delivery.{delivery_id}",
        details=f"重试内部事件投递 {delivery_id}",
    )
    return response


@router.post(
    "/internal-deliveries/{delivery_id}/replay",
    response_model=InternalEventDeliveryActionResponse,
    dependencies=[Depends(require_permission("workflows:delivery:replay"))],
)
def replay_internal_event_delivery_route(
    delivery_id: str,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> InternalEventDeliveryActionResponse:
    response = InternalEventDeliveryActionResponse(**replay_internal_event_delivery(delivery_id))
    append_control_plane_audit_log(
        action="workflow.delivery.replayed",
        user=_operator_identity(current_user),
        resource=f"workflow.delivery.{delivery_id}",
        details=f"重放内部事件投递 {delivery_id}",
    )
    return response


@router.post(
    "/{workflow_id}/run",
    response_model=WorkflowActionResponse,
    dependencies=[Depends(require_permission("workflows:run:create"))],
)
def run_workflow_route(
    workflow_id: str,
    payload: RunWorkflowRequest | None = None,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> WorkflowActionResponse:
    response = WorkflowActionResponse(**run_workflow(workflow_id, payload.model_dump() if payload else None))
    append_control_plane_audit_log(
        action="workflow.run.created",
        user=_operator_identity(current_user),
        resource=f"workflow.run.{workflow_id}",
        details=f"手动启动工作流 {workflow_id}",
    )
    return response


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
    tenant_id: str | None = Header(default=None, alias="X-WorkBot-Tenant-Id"),
    project_id: str | None = Header(default=None, alias="X-WorkBot-Project-Id"),
    environment: str | None = Header(default=None, alias="X-WorkBot-Environment"),
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> WorkflowRunListResponse:
    scope = resolve_scope(
        current_user=current_user,
        tenant_id=tenant_id,
        project_id=project_id,
        environment=environment,
    )
    return WorkflowRunListResponse(**list_runs(workflow_id=workflow_id, task_id=task_id, scope=scope))


@router.get(
    "/runs/{run_id}",
    response_model=WorkflowRun,
    dependencies=[Depends(require_permission("workflows:read"))],
)
def get_workflow_run_route(
    run_id: str,
    tenant_id: str | None = Header(default=None, alias="X-WorkBot-Tenant-Id"),
    project_id: str | None = Header(default=None, alias="X-WorkBot-Project-Id"),
    environment: str | None = Header(default=None, alias="X-WorkBot-Environment"),
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> WorkflowRun:
    scope = resolve_scope(
        current_user=current_user,
        tenant_id=tenant_id,
        project_id=project_id,
        environment=environment,
    )
    return WorkflowRun(**get_run(run_id, scope=scope))


@router.post(
    "/runs/{run_id}/tick",
    response_model=WorkflowRun,
    dependencies=[Depends(require_permission("workflows:run:tick"))],
)
def tick_workflow_run_route(
    run_id: str,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> WorkflowRun:
    response = WorkflowRun(**tick_run(run_id))
    append_control_plane_audit_log(
        action="workflow.run.ticked",
        user=_operator_identity(current_user),
        resource=f"workflow.run.{run_id}",
        details=f"推进工作流运行 {run_id}",
    )
    return response


@router.post(
    "/runs/{run_id}/manual-handoff",
    response_model=WorkflowRun | ApprovalActionResponse,
    dependencies=[Depends(require_permission("workflows:handoff"))],
)
def request_workflow_run_manual_handoff_route(
    run_id: str,
    payload: WorkflowRunManualHandoffRequest | None = None,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> WorkflowRun:
    request_payload = payload or WorkflowRunManualHandoffRequest()
    operator = _operator_identity(current_user)
    approval_payload = {
        "run_id": run_id,
        "operator": request_payload.operator,
        "note": request_payload.note,
    }
    if not request_payload.approval_id:
        approval = create_bound_approval(
            request_type="manual_handoff",
            title=f"人工接管工作流运行 {run_id}",
            resource=f"workflow.run.{run_id}.manual_handoff",
            requested_by=operator,
            request_payload=approval_payload,
            target_action="workflow.run.manual_handoff",
            reason=request_payload.approval_reason,
            note=request_payload.approval_note or request_payload.note,
        )
        return JSONResponse(
            status_code=202,
            content=ApprovalActionResponse(
                ok=True,
                message="Approval required before manual handoff",
                approval=ApprovalItem(**approval),
                approval_required=True,
            ).model_dump(by_alias=True, exclude_none=True),
        )
    require_approved_execution(
        request_payload.approval_id,
        request_type="manual_handoff",
        resource=f"workflow.run.{run_id}.manual_handoff",
        request_payload=approval_payload,
        target_action="workflow.run.manual_handoff",
        executed_by=operator,
        execution_ref=f"workflow.run.{run_id}.manual_handoff",
    )
    return WorkflowRun(
        **request_manual_handoff(
            run_id,
            operator=request_payload.operator,
            note=request_payload.note,
        )
    )


@router.websocket("/{workflow_id}/realtime")
async def workflow_realtime_route(websocket: WebSocket, workflow_id: str) -> None:
    authenticate_websocket(websocket, permission="workflows:read")
    await workflow_realtime_service.stream(websocket, workflow_id)
