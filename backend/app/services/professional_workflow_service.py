from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.core.brain_payload_fields import (
    alias_value,
    dispatch_context_from_run,
    route_decision_from_payload,
    route_decision_from_task,
)
from app.execution_gateway import ExecutionRequest, SkillExecutionGateway
from app.execution_gateway.skill_execution_gateway import skill_execution_gateway
from app.services.mcp_runtime_service import MCPRuntimeService, mcp_runtime_service


ROLE_DEFINITIONS: tuple[tuple[str, str], ...] = (
    ("planner_agent", "负责准入判定、任务拆解与执行计划生成"),
    ("system_agent", "负责权限系统、业务系统与结构化查询执行"),
    ("document_agent", "负责文档导出、PDF 包装与结果整理"),
    ("delivery_agent", "负责发送、通知与回传"),
)
CAPABILITY_ROLE_HINTS: dict[str, str] = {
    "permission_validation": "planner_agent",
    "enterprise_system_access": "system_agent",
    "crm_data_access": "system_agent",
    "order_data_access": "system_agent",
    "structured_data_query": "system_agent",
    "system_write_operation": "system_agent",
    "document_export": "document_agent",
    "pdf_processing": "document_agent",
    "notification_delivery": "delivery_agent",
}
ROLE_PERMISSION_HINTS: dict[str, set[str]] = {
    "admin": {"tasks:write", "agents:reload", "agents:read"},
    "operator": {"tasks:write", "agents:reload", "agents:read"},
    "power_user": {"tasks:write", "agents:read"},
    "viewer": {"agents:read"},
}


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_lower(value: object) -> str:
    return _normalize_text(value).lower()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in (_normalize_text(raw) for raw in value) if item]


def _route_value(task: dict, run: dict, *keys: str) -> Any:
    dispatch_context = dispatch_context_from_run(run)
    route_decision = route_decision_from_payload(dispatch_context) or route_decision_from_task(task) or {}
    return alias_value(route_decision, *keys)


def _request_text(task: dict) -> str:
    return _normalize_text(task.get("description") or task.get("title") or "当前专业工作流任务")


def _capability_role(capability: str) -> str:
    normalized = _normalize_text(capability).lower()
    return CAPABILITY_ROLE_HINTS.get(normalized, "planner_agent")


def _role_display_name(role_id: str) -> str:
    return {
        "planner_agent": "Planner Agent",
        "system_agent": "System Agent",
        "document_agent": "Document Agent",
        "delivery_agent": "Delivery Agent",
    }.get(role_id, "Planner Agent")


def _extract_entities(request_text: str) -> dict[str, Any]:
    normalized = _normalize_text(request_text).lower()
    customers = [token for token in ("客户", "customer", "client") if token in normalized]
    orders = [token for token in ("订单", "order") if token in normalized]
    quantities: list[int] = []
    for token in normalized.replace("个", " ").split():
        if token.isdigit():
            try:
                quantities.append(int(token))
            except ValueError:
                continue
    return {
        "customer_entities": customers,
        "order_entities": orders,
        "quantities": quantities[:3],
        "has_evidence": bool(customers or orders or quantities),
    }


def _requires_evidence_gate(request_text: str) -> bool:
    normalized = _normalize_text(request_text).lower()
    if not normalized:
        return False
    return any(
        hint in normalized
        for hint in {
            "上次",
            "之前",
            "历史",
            "也是这个客户",
            "也是他",
            "again",
            "history",
            "last time",
            "same customer",
            "same client",
            "previous order",
        }
    )


def _connector_tool_id(connector: dict[str, Any]) -> str:
    for key in ("tool_id", "toolId", "id"):
        value = _normalize_text(connector.get(key))
        if value:
            return value
    name = _normalize_text(connector.get("name"))
    if name:
        return f"agent-reach-external:mcp:{name}"
    return ""


def _pick_connector(connectors: list[dict[str, Any]], *, keywords: tuple[str, ...]) -> dict[str, Any] | None:
    normalized_keywords = tuple(keyword.lower() for keyword in keywords if keyword)
    if not normalized_keywords:
        return connectors[0] if connectors else None
    for connector in connectors:
        haystacks = [
            _normalize_lower(connector.get("name")),
            _normalize_lower(connector.get("id")),
            _normalize_lower(connector.get("tool_id")),
            _normalize_lower(connector.get("provider")),
        ]
        if any(keyword in haystack for haystack in haystacks for keyword in normalized_keywords):
            return connector
    return connectors[0] if connectors else None


def _infer_runtime_tool_id(
    *,
    request_text: str,
    required_capabilities: list[str],
    target_systems: list[str],
    connectors: list[dict[str, Any]],
) -> str:
    lowered_text = _normalize_lower(request_text)
    lowered_capabilities = {_normalize_lower(item) for item in required_capabilities}
    lowered_targets = {_normalize_lower(item) for item in target_systems}

    order_like = (
        "order_data_access" in lowered_capabilities
        or "order" in lowered_targets
        or "订单" in lowered_text
        or "order" in lowered_text
    )
    crm_like = (
        "crm_data_access" in lowered_capabilities
        or "crm" in lowered_targets
        or "客户" in lowered_text
        or "crm" in lowered_text
    )

    if order_like:
        connector = _pick_connector(connectors, keywords=("order", "订单"))
        if isinstance(connector, dict):
            return _connector_tool_id(connector)
    if crm_like:
        connector = _pick_connector(connectors, keywords=("crm", "customer", "客户"))
        if isinstance(connector, dict):
            return _connector_tool_id(connector)

    connector = connectors[0] if connectors else None
    if isinstance(connector, dict):
        return _connector_tool_id(connector)
    return ""


class ProfessionalWorkflowService:
    def __init__(
        self,
        *,
        runtime_service: MCPRuntimeService | None = None,
        execution_gateway: SkillExecutionGateway | None = None,
    ) -> None:
        self._runtime_service = runtime_service or mcp_runtime_service
        self._execution_gateway = execution_gateway or skill_execution_gateway

    def assess_admission(
        self,
        *,
        route_decision: dict[str, Any],
        user_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        user_context = user_context or {}
        workflow_mode = _normalize_text(
            alias_value(route_decision, "workflow_mode", "workflowMode") or "chat"
        ).lower()
        if workflow_mode != "professional_workflow":
            return {
                "admitted": False,
                "reason": "not_professional_workflow",
                "missing_permissions": [],
                "required_permissions": [],
            }

        requires_permission = bool(
            alias_value(route_decision, "requires_permission", "requiresPermission")
        )
        role = _normalize_text(user_context.get("role") or "viewer").lower()
        granted_permissions = ROLE_PERMISSION_HINTS.get(role, ROLE_PERMISSION_HINTS["viewer"])
        required_permissions = {"agents:read"}
        if requires_permission:
            required_permissions.update({"tasks:write", "agents:reload"})

        missing_permissions = sorted(required_permissions - granted_permissions)
        if missing_permissions:
            return {
                "admitted": False,
                "reason": "permission_denied",
                "missing_permissions": missing_permissions,
                "required_permissions": sorted(required_permissions),
            }
        return {
            "admitted": True,
            "reason": "admitted",
            "missing_permissions": [],
            "required_permissions": sorted(required_permissions),
        }

    def assign_roles(self, *, required_capabilities: list[str]) -> dict[str, Any]:
        normalized_capabilities = [item.lower() for item in _string_list(required_capabilities)]
        assignments: list[dict[str, Any]] = []
        for capability in normalized_capabilities:
            role_id = _capability_role(capability)
            assignments.append(
                {
                    "capability": capability,
                    "role_id": role_id,
                    "role_name": _role_display_name(role_id),
                }
            )

        lead_agent = {
            "agent_id": "planner-agent",
            "name": "Planner Agent",
            "role_id": "planner_agent",
        }
        review_agent = {
            "agent_id": "delivery-agent",
            "name": "Delivery Agent",
            "role_id": "delivery_agent",
        }
        return {
            "lead_agent": lead_agent,
            "review_agent": review_agent,
            "capability_assignments": assignments,
            "roles": [
                {"id": role_id, "name": _role_display_name(role_id), "description": description}
                for role_id, description in ROLE_DEFINITIONS
            ],
        }

    def execute_professional_request(
        self,
        *,
        request: dict[str, Any],
        route_decision: dict[str, Any],
        user_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        admission = self.assess_admission(route_decision=route_decision, user_context=user_context or {})
        required_capabilities = _string_list(
            alias_value(request, "required_capabilities", "requiredCapabilities")
            or alias_value(route_decision, "required_capabilities", "requiredCapabilities")
            or []
        )
        role_plan = self.assign_roles(required_capabilities=required_capabilities)
        if not admission["admitted"]:
            return {
                "ok": False,
                "status": "rejected",
                "admission": admission,
                "role_plan": role_plan,
                "steps": [],
                "failure_attribution": {
                    "category": "admission_failure",
                    "owner": "professional_workflow",
                    "reason": admission["reason"],
                },
                "governance": {
                    "audit_id": f"audit-{uuid4().hex[:12]}",
                    "idempotency_key": f"professional:{uuid4().hex[:16]}",
                    "execution_scope": "read_only",
                    "approval_required": False,
                },
            }

        runtime_tool_id = _normalize_text(
            alias_value(request, "runtime_tool_id", "runtimeToolId")
            or alias_value(request, "tool_id", "toolId")
        )
        payload = deepcopy(alias_value(request, "payload") or {})
        request_text = _normalize_text(
            str(
                alias_value(request, "text", "description", "message")
                or ""
            )
        )
        entity_summary = _extract_entities(request_text)
        governance = {
            "audit_id": str(alias_value(request, "audit_id", "auditId") or f"audit-{uuid4().hex[:12]}"),
            "idempotency_key": str(
                alias_value(request, "idempotency_key", "idempotencyKey") or f"professional:{uuid4().hex[:16]}"
            ),
            "execution_scope": str(alias_value(request, "execution_scope", "executionScope") or "read_only"),
            "approval_required": bool(alias_value(request, "approval_required", "approvalRequired") or False),
            "evidence_policy": "strict",
            "has_evidence": bool(entity_summary.get("has_evidence")),
        }
        if governance["evidence_policy"] == "strict" and request_text and not governance["has_evidence"]:
            return {
                "ok": False,
                "status": "blocked",
                "admission": admission,
                "role_plan": role_plan,
                "steps": [],
                "failure_attribution": {
                    "category": "evidence_required",
                    "owner": "professional_workflow",
                    "reason": "missing_evidence_for_professional_assertion",
                },
                "entity_summary": entity_summary,
                "governance": governance,
                "connectors": self._runtime_service.list_servers(),
                "selected_runtime_tool_id": runtime_tool_id or None,
            }
        if not runtime_tool_id:
            connectors = self._runtime_service.list_servers()
            runtime_tool_id = _infer_runtime_tool_id(
                request_text=request_text,
                required_capabilities=required_capabilities,
                target_systems=[
                    item.upper() if item != "oa" else "OA"
                    for item in ("crm", "erp", "oa", "sap", "salesforce", "order")
                    if item in request_text.lower()
                ],
                connectors=connectors,
            )
        else:
            connectors = self._runtime_service.list_servers()

        if not runtime_tool_id:
            return {
                "ok": False,
                "status": "failed",
                "admission": admission,
                "role_plan": role_plan,
                "steps": [],
                "failure_attribution": {
                    "category": "runtime_selection_failure",
                    "owner": "professional_workflow",
                    "reason": "missing_runtime_tool_id",
                },
                "entity_summary": entity_summary,
                "governance": governance,
                "connectors": connectors,
                "selected_runtime_tool_id": None,
            }

        gateway_outcome = self._execution_gateway.execute(
            request=ExecutionRequest(
                tool_id=runtime_tool_id,
                payload=payload,
                trace_context={
                    "workflow_mode": "professional_workflow",
                    "required_capabilities": required_capabilities,
                    "audit_id": governance["audit_id"],
                    "idempotency_key": governance["idempotency_key"],
                    "execution_scope": governance["execution_scope"],
                },
            ),
            mode="runtime_primary",
            runtime_executor=lambda request: self._runtime_service.invoke_tool(
                tool_id=runtime_tool_id,
                payload=request.payload,
                trace_context=request.trace_context,
            ),
            builtin_executor=lambda request: {
                "ok": False,
                "error": {"message": "builtin_not_available_for_professional_workflow"},
                "result": {"payload": deepcopy(request.payload)},
            },
            strict_runtime_required=True,
        )
        runtime_response = gateway_outcome.runtime_result or {
            "ok": False,
            "trace_id": None,
            "error": {"message": gateway_outcome.fallback_reason or "runtime_error"},
        }
        if not runtime_response.get("ok"):
            return {
                "ok": False,
                "status": "failed",
                "admission": admission,
                "role_plan": role_plan,
                "steps": [
                    {
                        "stage": "runtime_execution",
                        "status": "failed",
                        "trace_id": runtime_response.get("trace_id"),
                        "error": runtime_response.get("error"),
                    }
                ],
                "failure_attribution": {
                    "category": "runtime_failure",
                    "owner": "mcp_runtime",
                    "reason": str((runtime_response.get("error") or {}).get("message") or "runtime_error"),
                },
                "entity_summary": entity_summary,
                "governance": governance,
                "connectors": connectors,
                "selected_runtime_tool_id": runtime_tool_id,
            }

        return {
            "ok": True,
            "status": "completed",
            "admission": admission,
            "role_plan": role_plan,
            "steps": [
                {
                    "stage": "runtime_execution",
                    "status": "completed",
                    "trace_id": runtime_response.get("trace_id"),
                    "result": runtime_response.get("result"),
                }
            ],
            "runtime_result": runtime_response.get("result"),
            "entity_summary": entity_summary,
            "governance": governance,
            "connectors": connectors,
            "selected_runtime_tool_id": runtime_tool_id,
        }

    # Compatibility API for agent_execution_service.
    def assess(self, *, task: dict, run: dict) -> dict[str, Any]:
        required_capabilities = _string_list(
            _route_value(task, run, "required_capabilities", "requiredCapabilities") or []
        )
        route_decision = {
            "workflow_mode": _route_value(task, run, "workflow_mode", "workflowMode") or "professional_workflow",
            "requires_permission": bool(
                _route_value(task, run, "requires_permission", "requiresPermission") or False
            ),
            "required_capabilities": required_capabilities,
        }
        admission = self.assess_admission(
            route_decision=route_decision,
            user_context={"role": "admin"},
        )
        request_text = _request_text(task)
        lowered = request_text.lower()
        target_systems = [
            item.upper() if item != "oa" else "OA"
            for item in ("crm", "erp", "oa", "sap", "salesforce", "order")
            if item in lowered
        ]
        return {
            "workflow_mode": route_decision["workflow_mode"],
            "requires_permission": route_decision["requires_permission"],
            "required_capabilities": required_capabilities,
            "target_systems": target_systems,
            "structured_result_required": any(
                capability in {"structured_data_query", "document_export", "notification_delivery"}
                for capability in required_capabilities
            ),
            "approval_required": "审批" in request_text or "approval" in lowered,
            "entity_summary": _extract_entities(request_text),
            "connectors": self._runtime_service.list_servers(),
            "roles": self.assign_roles(required_capabilities=required_capabilities)["roles"],
            "admission": admission,
        }

    def execute(self, *, task: dict, run: dict, execution_agent: dict | None = None) -> dict[str, Any]:
        assessment = self.assess(task=task, run=run)
        required_capabilities = assessment["required_capabilities"]
        role_plan = self.assign_roles(required_capabilities=required_capabilities)
        connectors = assessment["connectors"]
        request_text = _request_text(task)
        route_decision = {
            "workflow_mode": _route_value(task, run, "workflow_mode", "workflowMode") or "professional_workflow",
            "requires_permission": bool(
                _route_value(task, run, "requires_permission", "requiresPermission") or False
            ),
            "required_capabilities": required_capabilities,
            "execution_scope": _route_value(task, run, "execution_scope", "executionScope") or "read_only",
            "approval_required": bool(
                _route_value(task, run, "approval_required", "approvalRequired") or assessment["approval_required"]
            ),
        }
        runtime_tool_id = _normalize_text(
            _route_value(task, run, "runtime_tool_id", "runtimeToolId", "tool_id", "toolId")
        ) or _infer_runtime_tool_id(
            request_text=request_text,
            required_capabilities=required_capabilities,
            target_systems=assessment["target_systems"],
            connectors=connectors,
        )
        execution_result = self.execute_professional_request(
            request={
                "text": request_text,
                "payload": {
                    "query": request_text,
                    "task_id": str(task.get("id") or ""),
                    "workflow_run_id": str(run.get("id") or ""),
                    "required_capabilities": required_capabilities,
                    "target_systems": assessment["target_systems"],
                },
                "required_capabilities": required_capabilities,
                "runtime_tool_id": runtime_tool_id,
                "execution_scope": route_decision["execution_scope"],
                "approval_required": route_decision["approval_required"],
                "audit_id": _route_value(task, run, "audit_id", "auditId"),
                "idempotency_key": _route_value(task, run, "idempotency_key", "idempotencyKey"),
            },
            route_decision=route_decision,
            user_context={"role": "admin"},
        )
        selected_tool = _normalize_text(execution_result.get("selected_runtime_tool_id") or runtime_tool_id)
        connector_note = (
            f"已识别可桥接来源：{connectors[0]['name']}（{connectors[0].get('health_message') or connectors[0].get('health_status') or 'unknown'}）"
            if connectors
            else "当前没有命中可直接执行的外部连接器，系统将保持准入等待状态。"
        )
        if selected_tool:
            connector_note = f"{connector_note}；本次执行触手：{selected_tool}"
        execution_status = "执行成功" if execution_result.get("ok") else f"执行未完成（{execution_result.get('status')}）"
        failure_reason = _normalize_text(
            ((execution_result.get("failure_attribution") or {}).get("reason"))
            or ((execution_result.get("failure_attribution") or {}).get("category"))
            or ""
        )
        content = "\n".join(
            [
                "已进入专业工作流处理链路。",
                "",
                f"请求：{request_text}",
                f"权限要求：{'需要' if assessment['requires_permission'] else '不需要'}",
                f"目标系统：{', '.join(assessment['target_systems']) if assessment['target_systems'] else '待补充'}",
                f"结构化结果：{'需要' if assessment['structured_result_required'] else '可选'}",
                "",
                "角色分工：",
                *[
                    f"- {item['name']}：{item['description']}"
                    for item in role_plan["roles"]
                ],
                "",
                f"执行状态：{execution_status}",
                f"执行范围：{(execution_result.get('governance') or {}).get('execution_scope') or route_decision['execution_scope']}",
                f"审批要求：{'需要' if (execution_result.get('governance') or {}).get('approval_required') else '不需要'}",
                f"审计ID：{(execution_result.get('governance') or {}).get('audit_id') or '-'}",
                "",
                "桥接连接器：",
                f"- {connector_note}",
                "",
                "当前已完成准入与触手执行链路。",
                f"失败原因：{failure_reason or '无'}",
            ]
        )
        return {
            "kind": "help_note",
            "title": "专业工作流执行结果",
            "summary": "已完成专业工作流准入评估并尝试触手执行",
            "content": content,
            "bullets": [
                "本次请求已被专业工作流接管，而不是落回自由工作流或接待兜底。",
                f"已识别能力需求：{', '.join(required_capabilities) or '待补充'}。",
                connector_note,
                f"执行状态：{execution_status}",
            ],
            "references": [
                {
                    "title": f"MCP / {item.get('name')}",
                    "detail": item.get("base_url") or item.get("health_message") or "-",
                }
                for item in connectors[:3]
            ],
            "execution_trace": [
                {
                    "stage": "admission_check",
                    "title": "专业工作流准入",
                    "status": "completed",
                    "detail": "已完成权限、系统访问与结构化结果需求评估。",
                    "metadata": {
                        "checked_at": _utc_now_iso(),
                        "admission": assessment["admission"],
                    },
                },
                {
                    "stage": "planning",
                    "title": "角色拆解",
                    "status": "completed",
                    "detail": "已按 Planner / System / Document / Delivery 生成协作分工。",
                    "metadata": {"role_plan": role_plan},
                },
                {
                    "stage": "connector_bridge",
                    "title": "外部桥接检查",
                    "status": "completed",
                    "detail": connector_note,
                    "metadata": {
                        "connectors": connectors,
                        "selected_runtime_tool_id": selected_tool or None,
                    },
                },
                {
                    "stage": "runtime_execution",
                    "title": "专业触手执行",
                    "status": "completed" if execution_result.get("ok") else "failed",
                    "detail": execution_status,
                    "metadata": {
                        "result_status": execution_result.get("status"),
                        "failure_attribution": execution_result.get("failure_attribution"),
                        "runtime_result": execution_result.get("runtime_result"),
                        "governance": execution_result.get("governance"),
                    },
                },
            ],
            "structured_data": {
                **assessment,
                "execution_result": execution_result,
            },
        }


professional_workflow_service = ProfessionalWorkflowService()
