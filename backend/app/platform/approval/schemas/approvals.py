from typing import Any, Literal

from pydantic import Field

from app.platform.contracts.api_model import APIModel


ApprovalStatus = Literal["pending", "approved", "rejected", "expired", "cancelled"]
ApprovalRequestType = Literal[
    "settings_change",
    "security_release",
    "manual_handoff",
    "external_capability_release",
]


class ApprovalItem(APIModel):
    id: str
    request_type: ApprovalRequestType
    status: ApprovalStatus
    title: str
    resource: str
    requested_by: str
    requested_at: str
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    reason: str | None = None
    note: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    executed_by: str | None = None
    executed_at: str | None = None
    execution_ref: str | None = None


class ApprovalListResponse(APIModel):
    items: list[ApprovalItem]
    total: int


class CreateApprovalRequest(APIModel):
    request_type: ApprovalRequestType
    title: str
    resource: str
    reason: str | None = None
    note: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ProcessApprovalRequest(APIModel):
    note: str | None = None


class ApprovalActionResponse(APIModel):
    ok: bool
    message: str
    approval: ApprovalItem
    approval_required: bool | None = None
