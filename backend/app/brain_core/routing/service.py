from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _normalize_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _contains_any(text: str, hints: set[str]) -> bool:
    return any(hint in text for hint in hints)


SEARCH_HINTS = {"search", "lookup", "查询", "搜索", "检索"}
PDF_HINTS = {"pdf", "文档", "附件"}
WRITE_HINTS = {"写", "生成", "draft", "copy", "演讲"}
PROFESSIONAL_HINTS = {"订单", "crm", "客户", "审批", "order", "salesforce"}


@dataclass(slots=True)
class RouteDecision:
    workflow_mode: str
    requires_permission: bool
    required_capabilities: list[str]
    execution_scope: str
    approval_required: bool
    execution_plan: dict[str, Any]
    route_message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_mode": self.workflow_mode,
            "requires_permission": self.requires_permission,
            "required_capabilities": list(self.required_capabilities),
            "execution_scope": self.execution_scope,
            "approval_required": self.approval_required,
            "execution_plan": dict(self.execution_plan),
            "route_message": self.route_message,
        }


class RoutingService:
    """Brain routing service that emits a normalized route_decision."""

    def decide(self, text: str, *, metadata: dict[str, Any] | None = None) -> RouteDecision:
        normalized = _normalize_text(text).lower()
        metadata = metadata or {}

        workflow_mode = "chat"
        required_capabilities: list[str] = []
        requires_permission = False
        approval_required = False
        execution_scope = "read_only"

        if _contains_any(normalized, PROFESSIONAL_HINTS):
            workflow_mode = "professional_workflow"
            requires_permission = True
            required_capabilities = ["permission_validation", "structured_data_query"]
            approval_required = _contains_any(normalized, {"审批", "approval", "approve"})
            execution_scope = "write_protected" if approval_required else "read_only"
        elif _contains_any(normalized, SEARCH_HINTS | PDF_HINTS | WRITE_HINTS):
            workflow_mode = "free_workflow"
            if _contains_any(normalized, SEARCH_HINTS):
                required_capabilities.append("web_search")
            if _contains_any(normalized, PDF_HINTS):
                required_capabilities.append("pdf_processing")
            if _contains_any(normalized, WRITE_HINTS):
                required_capabilities.append("content_generation")

        execution_plan = {
            "mode": workflow_mode,
            "step_count": 1,
            "strategy": "single_step",
            "metadata": dict(metadata),
        }
        route_message = {
            "chat": "chat_reply",
            "free_workflow": "dispatch_to_free_workflow",
            "professional_workflow": "dispatch_to_professional_workflow",
        }[workflow_mode]
        return RouteDecision(
            workflow_mode=workflow_mode,
            requires_permission=requires_permission,
            required_capabilities=required_capabilities,
            execution_scope=execution_scope,
            approval_required=approval_required,
            execution_plan=execution_plan,
            route_message=route_message,
        )

