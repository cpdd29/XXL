from __future__ import annotations

from typing import Any

from app.services.professional_workflow_service import ProfessionalWorkflowService


class _RuntimeStub:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.invocations: list[dict[str, Any]] = []

    def invoke_tool(
        self,
        *,
        tool_id: str,
        payload: dict[str, Any] | None = None,
        trace_context: dict[str, Any] | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        self.invocations.append(
            {
                "tool_id": tool_id,
                "payload": payload or {},
                "trace_context": trace_context or {},
            }
        )
        if self.should_fail:
            return {
                "ok": False,
                "trace_id": "trace-fail",
                "error": {"type": "RuntimeError", "message": "bridge unavailable"},
            }
        return {
            "ok": True,
            "trace_id": "trace-ok",
            "result": {"ok": True, "tool": tool_id},
        }

    def list_servers(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "agent-reach-external:mcp:order-query",
                "tool_id": "agent-reach-external:mcp:order-query",
                "name": "order-query",
                "base_url": "http://order-query-mcp:8094",
                "health_status": "healthy",
                "health_message": "MCP 地址已配置",
            },
            {
                "id": "agent-reach-external:mcp:crm-query",
                "tool_id": "agent-reach-external:mcp:crm-query",
                "name": "crm-query",
                "base_url": "https://mcp.crm.local",
                "health_status": "healthy",
                "health_message": "MCP 地址已配置",
            }
        ]


def test_assess_admission_rejects_non_professional_workflow() -> None:
    service = ProfessionalWorkflowService(runtime_service=_RuntimeStub())

    admission = service.assess_admission(
        route_decision={"workflow_mode": "chat"},
        user_context={"role": "admin"},
    )

    assert admission["admitted"] is False
    assert admission["reason"] == "not_professional_workflow"


def test_assess_admission_rejects_missing_permissions() -> None:
    service = ProfessionalWorkflowService(runtime_service=_RuntimeStub())

    admission = service.assess_admission(
        route_decision={
            "workflow_mode": "professional_workflow",
            "requires_permission": True,
            "required_capabilities": ["document_export", "crm_data_access"],
        },
        user_context={"role": "viewer"},
    )

    assert admission["admitted"] is False
    assert admission["reason"] == "permission_denied"
    assert "tasks:write" in admission["missing_permissions"]


def test_assign_roles_builds_capability_assignments() -> None:
    service = ProfessionalWorkflowService(runtime_service=_RuntimeStub())

    role_plan = service.assign_roles(
        required_capabilities=["crm_data_access", "document_export", "notification_delivery"]
    )

    assert role_plan["lead_agent"]["agent_id"] is not None
    assert role_plan["review_agent"]["agent_id"] is not None
    assert len(role_plan["capability_assignments"]) == 3


def test_execute_professional_request_success_and_runtime_trace() -> None:
    runtime = _RuntimeStub()
    service = ProfessionalWorkflowService(runtime_service=runtime)

    result = service.execute_professional_request(
        request={
            "workflow_mode": "professional_workflow",
            "required_capabilities": ["crm_data_access", "document_export"],
            "runtime_tool_id": "agent-reach-external:mcp:crm-query",
            "payload": {"month": "10"},
        },
        route_decision={
            "workflow_mode": "professional_workflow",
            "requires_permission": True,
            "required_capabilities": ["crm_data_access", "document_export"],
        },
        user_context={"role": "admin"},
    )

    assert result["ok"] is True
    assert result["status"] == "completed"
    assert result["steps"][0]["trace_id"] == "trace-ok"
    assert runtime.invocations


def test_execute_professional_request_returns_failure_attribution_on_runtime_error() -> None:
    runtime = _RuntimeStub(should_fail=True)
    service = ProfessionalWorkflowService(runtime_service=runtime)

    result = service.execute_professional_request(
        request={
            "workflow_mode": "professional_workflow",
            "required_capabilities": ["crm_data_access"],
            "runtime_tool_id": "agent-reach-external:mcp:crm-query",
        },
        route_decision={
            "workflow_mode": "professional_workflow",
            "requires_permission": True,
            "required_capabilities": ["crm_data_access"],
        },
        user_context={"role": "admin"},
    )

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["failure_attribution"]["category"] == "runtime_failure"
    assert result["failure_attribution"]["owner"] == "mcp_runtime"


def test_execute_professional_request_blocks_without_evidence_and_returns_governance() -> None:
    runtime = _RuntimeStub()
    service = ProfessionalWorkflowService(runtime_service=runtime)

    result = service.execute_professional_request(
        request={
            "workflow_mode": "professional_workflow",
            "required_capabilities": ["crm_data_access"],
            "runtime_tool_id": "agent-reach-external:mcp:crm-query",
            "text": "请帮我处理一下",
        },
        route_decision={
            "workflow_mode": "professional_workflow",
            "requires_permission": True,
            "required_capabilities": ["crm_data_access"],
        },
        user_context={"role": "admin"},
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["failure_attribution"]["category"] == "evidence_required"
    assert result["governance"]["evidence_policy"] == "strict"
    assert isinstance(result["governance"]["audit_id"], str)
    assert isinstance(result["governance"]["idempotency_key"], str)
    assert result["governance"]["execution_scope"] == "read_only"
    assert result["governance"]["approval_required"] is False
    assert result["entity_summary"]["has_evidence"] is False


def test_execute_professional_request_success_returns_governance() -> None:
    runtime = _RuntimeStub()
    service = ProfessionalWorkflowService(runtime_service=runtime)

    result = service.execute_professional_request(
        request={
            "workflow_mode": "professional_workflow",
            "required_capabilities": ["crm_data_access"],
            "runtime_tool_id": "agent-reach-external:mcp:crm-query",
            "text": "客户下了 200 个订单，请查询 CRM",
            "execution_scope": "read_only",
            "approval_required": False,
        },
        route_decision={
            "workflow_mode": "professional_workflow",
            "requires_permission": True,
            "required_capabilities": ["crm_data_access"],
        },
        user_context={"role": "admin"},
    )

    assert result["ok"] is True
    assert result["status"] == "completed"
    assert result["governance"]["evidence_policy"] == "strict"
    assert isinstance(result["governance"]["audit_id"], str)
    assert isinstance(result["governance"]["idempotency_key"], str)
    assert result["governance"]["execution_scope"] == "read_only"
    assert result["governance"]["approval_required"] is False
    assert result["entity_summary"]["has_evidence"] is True


def test_execute_infers_order_connector_and_runs_runtime() -> None:
    runtime = _RuntimeStub()
    service = ProfessionalWorkflowService(runtime_service=runtime)

    task = {
        "id": "task-order",
        "title": "客户下了 200 个鼠标垫订单",
        "description": "请查询订单进度",
    }
    run = {
        "id": "run-order",
        "dispatch_context": {
            "route_decision": {
                "workflow_mode": "professional_workflow",
                "requires_permission": True,
                "required_capabilities": ["order_data_access", "structured_data_query"],
            }
        },
    }

    result = service.execute(task=task, run=run, execution_agent=None)

    assert result["title"] == "专业工作流执行结果"
    execution_result = result["structured_data"]["execution_result"]
    assert execution_result["ok"] is True
    assert execution_result["selected_runtime_tool_id"] == "agent-reach-external:mcp:order-query"
    assert runtime.invocations[-1]["tool_id"] == "agent-reach-external:mcp:order-query"
