from typing import Any

from fastapi import APIRouter, Depends, Query

from app.platform.auth.authz import require_authenticated_user, require_permission
from app.platform.approval.schemas.approvals import (
    ApprovalActionResponse,
    ApprovalItem,
    ApprovalListResponse,
    CreateApprovalRequest,
    ProcessApprovalRequest,
)
from app.platform.approval.approval_service import create_approval, list_approvals, process_approval


router = APIRouter(dependencies=[Depends(require_authenticated_user)])


def _operator_identity(current_user: dict[str, Any]) -> str:
    return (
        str(current_user.get("email") or "").strip()
        or str(current_user.get("id") or "").strip()
        or "system"
    )


@router.get(
    "",
    response_model=ApprovalListResponse,
    dependencies=[Depends(require_permission("approvals:read"))],
)
def list_approvals_route(
    status_value: str | None = Query(default=None, alias="status"),
    request_type: str | None = Query(default=None, alias="requestType"),
) -> ApprovalListResponse:
    return ApprovalListResponse(**list_approvals(status_filter=status_value, request_type=request_type))


@router.post(
    "",
    response_model=ApprovalActionResponse,
    dependencies=[Depends(require_permission("approvals:write"))],
)
def create_approval_route(
    payload: CreateApprovalRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> ApprovalActionResponse:
    approval = create_approval(
        request_type=payload.request_type,
        title=payload.title,
        resource=payload.resource,
        requested_by=_operator_identity(current_user),
        reason=payload.reason,
        note=payload.note,
        payload=payload.payload,
    )
    return ApprovalActionResponse(ok=True, message="Approval created", approval=ApprovalItem(**approval))


@router.post(
    "/{approval_id}/approve",
    response_model=ApprovalActionResponse,
    dependencies=[Depends(require_permission("approvals:write"))],
)
def approve_approval_route(
    approval_id: str,
    payload: ProcessApprovalRequest | None = None,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> ApprovalActionResponse:
    request_payload = payload or ProcessApprovalRequest()
    approval = process_approval(
        approval_id,
        next_status="approved",
        reviewer=_operator_identity(current_user),
        note=request_payload.note,
    )
    return ApprovalActionResponse(ok=True, message="Approval approved", approval=ApprovalItem(**approval))


@router.post(
    "/{approval_id}/reject",
    response_model=ApprovalActionResponse,
    dependencies=[Depends(require_permission("approvals:write"))],
)
def reject_approval_route(
    approval_id: str,
    payload: ProcessApprovalRequest | None = None,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> ApprovalActionResponse:
    request_payload = payload or ProcessApprovalRequest()
    approval = process_approval(
        approval_id,
        next_status="rejected",
        reviewer=_operator_identity(current_user),
        note=request_payload.note,
    )
    return ApprovalActionResponse(ok=True, message="Approval rejected", approval=ApprovalItem(**approval))
