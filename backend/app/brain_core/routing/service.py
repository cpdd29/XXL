from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status

from app.brain_core.routing import planner, rules
from app.services import execution_directory_service


def _normalize_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _contains_any(text: str, hints: set[str]) -> bool:
    return any(hint in text for hint in hints)


SEARCH_HINTS = {"search", "lookup", "查询", "搜索", "检索"}
PDF_HINTS = {"pdf", "文档", "附件"}
WRITE_HINTS = {"写", "生成", "draft", "copy", "演讲"}
PROFESSIONAL_HINTS = {"订单", "crm", "客户", "审批", "order", "salesforce"}

ROUTING_STRATEGY_CHAT_AGENT_DISPATCH = "chat_agent_dispatch"
ROUTING_STRATEGY_CHAT_DIRECT_AGENT_ALIAS = "chat_direct_agent"
ROUTING_STRATEGY_DYNAMIC_MULTI_AGENT_DISPATCH = "dynamic_multi_agent_dispatch"
ROUTING_STRATEGY_WORKFLOW_OR_AGENT_DISPATCH_FALLBACK = "workflow_or_agent_dispatch_fallback"
ROUTING_STRATEGY_WORKFLOW_OR_DIRECT_AGENT_FALLBACK_ALIAS = "workflow_or_direct_agent_fallback"

ROUTE_DECISION_ALIAS_MAP = {
    "workflow_id": "workflowId",
    "workflow_name": "workflowName",
    "execution_agent_id": "executionAgentId",
    "execution_agent": "executionAgent",
    "interaction_mode": "interactionMode",
    "reception_mode": "receptionMode",
    "workflow_mode": "workflowMode",
    "requires_permission": "requiresPermission",
    "required_capabilities": "requiredCapabilities",
    "execution_plan": "executionPlan",
    "selected_by_message_trigger": "selectedByMessageTrigger",
    "route_message": "routeMessage",
    "intent_confidence": "intentConfidence",
    "intent_scores": "intentScores",
    "intent_reasons": "intentReasons",
    "candidate_workflows": "candidateWorkflows",
    "skipped_workflows": "skippedWorkflows",
    "routing_strategy": "routingStrategy",
    "execution_support": "executionSupport",
    "route_version": "routeVersion",
    "confirmation_required": "confirmationRequired",
    "confirmation_status": "confirmationStatus",
    "confirmation_deadline_at": "confirmationDeadlineAt",
    "requires_approval": "requiresApproval",
    "approval_required": "approvalRequired",
    "approval_status": "approvalStatus",
    "audit_id": "auditId",
    "idempotency_key": "idempotencyKey",
    "execution_scope": "executionScope",
    "evidence_policy": "evidencePolicy",
    "schedule_plan": "schedulePlan",
    "user_visible_workflow_mode": "userVisibleWorkflowMode",
    "route_rationale": "routeRationale",
    "fallback_policy": "fallbackPolicy",
}


def _canonical_routing_strategy(value: object) -> str:
    routing_strategy = str(value or "").strip().lower()
    if routing_strategy == ROUTING_STRATEGY_CHAT_DIRECT_AGENT_ALIAS:
        return ROUTING_STRATEGY_CHAT_AGENT_DISPATCH
    if routing_strategy == ROUTING_STRATEGY_WORKFLOW_OR_DIRECT_AGENT_FALLBACK_ALIAS:
        return ROUTING_STRATEGY_WORKFLOW_OR_AGENT_DISPATCH_FALLBACK
    return routing_strategy


def _route_value(route_decision: dict[str, Any], key: str):
    camel_key = ROUTE_DECISION_ALIAS_MAP.get(key)
    if key in route_decision:
        return route_decision.get(key)
    if camel_key and camel_key in route_decision:
        return route_decision.get(camel_key)
    return None


def _set_route_value(route_decision: dict[str, Any], key: str, value: Any) -> None:
    route_decision[key] = value
    camel_key = ROUTE_DECISION_ALIAS_MAP.get(key)
    if camel_key:
        route_decision[camel_key] = value


def _ensure_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if value is None:
        return []
    return [value]


def _ensure_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _workflow_declares_execution_targets(workflow: dict[str, Any]) -> bool:
    if any(str(item).strip() for item in _ensure_list(workflow.get("agent_bindings"))):
        return True
    for node in _ensure_list(workflow.get("nodes")):
        if not isinstance(node, dict):
            continue
        if str(node.get("agent_id") or "").strip() or str(node.get("agentId") or "").strip():
            return True
        if str(node.get("type") or "").strip().lower() == "agent":
            return True
    return False


def _fallback_mode(route_decision: dict[str, Any]) -> str:
    routing_strategy = _canonical_routing_strategy(_route_value(route_decision, "routing_strategy"))
    if routing_strategy == ROUTING_STRATEGY_WORKFLOW_OR_AGENT_DISPATCH_FALLBACK:
        return "agent_dispatch_fallback"
    if routing_strategy == ROUTING_STRATEGY_DYNAMIC_MULTI_AGENT_DISPATCH:
        return "planner_recovery"
    if str(_route_value(route_decision, "workflow_mode") or "").strip().lower() == "professional_workflow":
        return "approval_gate"
    return "none"


def _build_route_rationale(route_decision: dict[str, Any]) -> dict[str, Any]:
    intent = str(route_decision.get("intent") or "").strip() or None
    workflow_mode = str(_route_value(route_decision, "workflow_mode") or "").strip() or None
    interaction_mode = str(_route_value(route_decision, "interaction_mode") or "").strip() or None
    routing_strategy = _canonical_routing_strategy(_route_value(route_decision, "routing_strategy")) or None
    selected_by_trigger = bool(_route_value(route_decision, "selected_by_message_trigger"))
    candidate_workflows = _ensure_list(_route_value(route_decision, "candidate_workflows"))
    skipped_workflows = _ensure_list(_route_value(route_decision, "skipped_workflows"))
    intent_reasons = _ensure_dict(_route_value(route_decision, "intent_reasons"))
    route_message = str(_route_value(route_decision, "route_message") or "").strip() or None
    return {
        "intent": intent,
        "workflow_mode": workflow_mode,
        "interaction_mode": interaction_mode,
        "routing_strategy": routing_strategy,
        "selected_by_message_trigger": selected_by_trigger,
        "candidate_count": len(candidate_workflows),
        "skipped_count": len(skipped_workflows),
        "intent_reasons": intent_reasons,
        "route_reason_summary": route_message,
    }


def _build_fallback_policy(route_decision: dict[str, Any], execution_plan: dict[str, Any]) -> dict[str, Any]:
    fallback_mode = _fallback_mode(route_decision)
    workflow_mode = str(_route_value(route_decision, "workflow_mode") or "").strip().lower()
    fallback_target = (
        str(_route_value(route_decision, "execution_agent") or "").strip() or None
        if fallback_mode == "agent_dispatch_fallback"
        else "user_confirmation"
        if fallback_mode == "approval_gate"
        else "master_bot_planner"
        if fallback_mode == "planner_recovery"
        else None
    )
    return {
        "mode": fallback_mode,
        "target": fallback_target,
        "on_failure": (
            "retry_or_fail_terminal"
            if execution_plan.get("plan_type") == "multi_agent"
            else "direct_fail"
        ),
        "summary": (
            "Workflow candidates unavailable; fallback to agent dispatch"
            if fallback_mode == "agent_dispatch_fallback"
            else "Professional workflow waits for user confirmation"
            if fallback_mode == "approval_gate"
            else "Planner can retry or degrade to single-agent execution"
            if fallback_mode == "planner_recovery"
            else "No fallback required"
        ),
        "workflow_mode": workflow_mode or None,
    }


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

    def route_message(
        self,
        *,
        text: str,
        channel: str | None = None,
        detected_lang: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        intent_assessment = rules.classify_intent(text)
        intent = str(intent_assessment["intent"])
        interaction_mode = rules.classify_interaction_mode(text, intent=intent)
        reception_mode = rules.classify_reception_mode(
            text,
            intent=intent,
            interaction_mode=interaction_mode,
        )
        interaction_mode, reception_mode = rules.apply_interaction_mode_safety_correction(
            text,
            intent=intent,
            interaction_mode=interaction_mode,
            reception_mode=reception_mode,
        )
        workflow_candidates: list[tuple[dict, str]] = []
        no_workflow_available = False
        try:
            workflow_candidates = execution_directory_service.select_workflow_candidates_for_message(
                intent,
                text,
                channel=channel,
                detected_lang=detected_lang,
            )
        except HTTPException as exc:
            if exc.status_code != status.HTTP_404_NOT_FOUND or exc.detail != "Workflow not found":
                raise
            no_workflow_available = True

        if interaction_mode == "chat" and not workflow_candidates:
            chat_agent_intent, execution_agent, execution_support = planner.resolve_chat_execution_agent(intent)
            execution_agent_name = (
                str(execution_agent.get("name") or "").strip()
                or rules.target_agent_name(chat_agent_intent)
            )
            route_message = f"已识别为接待式对话；直接交由对话 Agent 回复: {execution_agent_name}"
            route_decision = {
                "intent": intent,
                "workflow_id": execution_directory_service.AGENT_DISPATCH_WORKFLOW_ID,
                "workflow_name": execution_directory_service.AGENT_DISPATCH_WORKFLOW_NAME,
                "execution_agent_id": str(execution_agent.get("id") or "").strip() or None,
                "execution_agent": execution_agent_name,
                "selected_by_message_trigger": False,
                "route_message": route_message,
                "intent_confidence": intent_assessment["confidence"],
                "intent_scores": intent_assessment["scores"],
                "intent_reasons": intent_assessment["reasons"],
                "candidate_workflows": [],
                "skipped_workflows": [],
                "routing_strategy": ROUTING_STRATEGY_CHAT_AGENT_DISPATCH,
                "interaction_mode": interaction_mode,
                "interactionMode": interaction_mode,
                "reception_mode": reception_mode,
                "receptionMode": reception_mode,
                "execution_support": {
                    **execution_support,
                    "chat_agent_intent": chat_agent_intent,
                },
            }
            route_decision = self.normalize_route_decision(
                rules.enrich_route_decision_with_workflow_mode(
                    route_decision,
                    text=text,
                    intent=intent,
                    interaction_mode=interaction_mode,
                    reception_mode=reception_mode,
                ),
                route_message=route_message,
                metadata=metadata,
            )
            return {
                "intent": intent,
                "workflow": None,
                "route_message": route_message,
                "route_decision": route_decision,
            }

        dynamic_execution_plan = planner.build_dynamic_execution_plan(text, intent)
        if dynamic_execution_plan is not None:
            execution_steps = dynamic_execution_plan["steps"]
            execution_agent_name = " + ".join(
                str(step.get("execution_agent") or "").strip()
                for step in execution_steps
                if str(step.get("execution_agent") or "").strip()
            )
            route_message = (
                f"已识别意图: {intent}；检测到复合任务；"
                f"已启用 Master Bot 动态编排 ({dynamic_execution_plan['coordination_mode']})："
                f"{dynamic_execution_plan['summary']}"
            )
            route_decision = {
                "intent": intent,
                "workflow_id": execution_directory_service.AGENT_DISPATCH_WORKFLOW_ID,
                "workflow_name": execution_directory_service.AGENT_DISPATCH_WORKFLOW_NAME,
                "execution_agent_id": execution_steps[0].get("execution_agent_id"),
                "execution_agent": execution_agent_name or "Master Bot Planner",
                "execution_plan": dynamic_execution_plan,
                "selected_by_message_trigger": False,
                "route_message": route_message,
                "intent_confidence": intent_assessment["confidence"],
                "intent_scores": intent_assessment["scores"],
                "intent_reasons": intent_assessment["reasons"],
                "candidate_workflows": [],
                "skipped_workflows": [],
                "routing_strategy": ROUTING_STRATEGY_DYNAMIC_MULTI_AGENT_DISPATCH,
                "interaction_mode": interaction_mode,
                "interactionMode": interaction_mode,
                "reception_mode": reception_mode,
                "receptionMode": reception_mode,
                "execution_support": {
                    "mode": "multi_agent",
                    "coordination_mode": dynamic_execution_plan["coordination_mode"],
                    "planned_agent_count": dynamic_execution_plan["planned_agent_count"],
                    "agents": [
                        {
                            "intent": step["intent"],
                            "execution_agent_id": step.get("execution_agent_id"),
                            "execution_agent": step.get("execution_agent"),
                            "agent_type": step.get("agent_type"),
                        }
                        for step in execution_steps
                    ],
                },
            }
            route_decision = self.normalize_route_decision(
                rules.enrich_route_decision_with_workflow_mode(
                    route_decision,
                    text=text,
                    intent=intent,
                    interaction_mode=interaction_mode,
                    reception_mode=reception_mode,
                ),
                route_message=route_message,
                metadata=metadata,
            )
            return {
                "intent": intent,
                "workflow": None,
                "route_message": route_message,
                "route_decision": route_decision,
            }

        skipped_workflows: list[dict[str, str]] = []
        candidate_workflows: list[dict[str, Any]] = []
        execution_agent = None
        execution_support: dict[str, Any] | None = None
        selected_route_message = ""
        selected_workflow = None

        for candidate_workflow, base_route_message in workflow_candidates:
            candidate_execution_agent = execution_directory_service.resolve_workflow_execution_agent(
                candidate_workflow,
                intent,
            )
            candidate_agent_name = (
                str((candidate_execution_agent or {}).get("name") or "").strip()
                or rules.target_agent_name(intent)
            )
            support = planner.execution_agent_support(candidate_execution_agent, intent)
            candidate_workflows.append(
                {
                    "workflow_id": str(candidate_workflow.get("id") or ""),
                    "workflow_name": str(candidate_workflow.get("name") or ""),
                    "route_message": base_route_message,
                    "execution_agent": candidate_agent_name,
                    "supports_intent": support.get("supports_intent"),
                    "support_source": str(support.get("support_source") or "unknown"),
                }
            )
            if candidate_execution_agent is None:
                if not _workflow_declares_execution_targets(candidate_workflow):
                    execution_support = {
                        "supports_intent": True,
                        "support_source": "workflow_without_execution_target",
                        "supported_intents": [],
                        "capabilities": [],
                        "warnings": ["workflow_missing_execution_target"],
                    }
                    selected_workflow = candidate_workflow
                    selected_route_message = base_route_message
                    break
                skipped_workflows.append(
                    {
                        "workflow_id": str(candidate_workflow.get("id") or ""),
                        "workflow_name": str(candidate_workflow.get("name") or ""),
                        "reason": "missing_execution_agent",
                    }
                )
                continue
            if support.get("supports_intent") is False:
                skipped_workflows.append(
                    {
                        "workflow_id": str(candidate_workflow.get("id") or ""),
                        "workflow_name": str(candidate_workflow.get("name") or ""),
                        "reason": "execution_agent_config_mismatch",
                    }
                )
                continue
            execution_agent = candidate_execution_agent
            execution_support = support
            selected_workflow = candidate_workflow
            selected_route_message = base_route_message
            break

        if execution_agent is None or selected_workflow is None:
            execution_agent = execution_directory_service.resolve_agent_dispatch_execution_agent(intent)
            execution_support = planner.execution_agent_support(execution_agent, intent)
            if execution_agent is None:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="No enabled direct execution agent available for intent",
                )

            execution_agent_name = str(execution_agent.get("name") or "").strip() or rules.target_agent_name(intent)
            fallback_reason = "未找到可用工作流" if no_workflow_available else "工作流不可执行"
            route_message = f"已识别意图: {intent}；{fallback_reason}；已切换为直达 Agent 执行: {execution_agent_name}"
            if skipped_workflows:
                route_message = (
                    f"{route_message}；已跳过不可执行工作流: "
                    f"{', '.join(item['workflow_name'] for item in skipped_workflows if item.get('workflow_name'))}"
                )
            route_decision = {
                "intent": intent,
                "workflow_id": execution_directory_service.AGENT_DISPATCH_WORKFLOW_ID,
                "workflow_name": execution_directory_service.AGENT_DISPATCH_WORKFLOW_NAME,
                "execution_agent_id": str(execution_agent.get("id") or "").strip() or None,
                "execution_agent": execution_agent_name,
                "selected_by_message_trigger": False,
                "route_message": route_message,
                "intent_confidence": intent_assessment["confidence"],
                "intent_scores": intent_assessment["scores"],
                "intent_reasons": intent_assessment["reasons"],
                "candidate_workflows": candidate_workflows[:5],
                "skipped_workflows": skipped_workflows,
                "routing_strategy": ROUTING_STRATEGY_WORKFLOW_OR_AGENT_DISPATCH_FALLBACK,
                "interaction_mode": interaction_mode,
                "interactionMode": interaction_mode,
                "reception_mode": reception_mode,
                "receptionMode": reception_mode,
                "execution_support": execution_support,
            }
            route_decision = self.normalize_route_decision(
                rules.enrich_route_decision_with_workflow_mode(
                    route_decision,
                    text=text,
                    intent=intent,
                    interaction_mode=interaction_mode,
                    reception_mode=reception_mode,
                ),
                route_message=route_message,
                metadata=metadata,
            )
            return {
                "intent": intent,
                "workflow": None,
                "route_message": route_message,
                "route_decision": route_decision,
            }

        execution_agent_name = str(execution_agent.get("name") or "").strip() or rules.target_agent_name(intent)
        route_message = f"{selected_route_message}；执行代理: {execution_agent_name}"
        if skipped_workflows:
            route_message = (
                f"{route_message}；已跳过不可执行工作流: "
                f"{', '.join(item['workflow_name'] for item in skipped_workflows if item.get('workflow_name'))}"
            )
        route_decision = {
            "intent": intent,
            "workflow_id": str(selected_workflow["id"]),
            "workflow_name": str(selected_workflow["name"]),
            "execution_agent_id": str(execution_agent.get("id") or "").strip() or None,
            "execution_agent": execution_agent_name,
            "selected_by_message_trigger": "路由依据: intent fallback" not in selected_route_message,
            "route_message": route_message,
            "intent_confidence": intent_assessment["confidence"],
            "intent_scores": intent_assessment["scores"],
            "intent_reasons": intent_assessment["reasons"],
            "candidate_workflows": candidate_workflows[:5],
            "skipped_workflows": skipped_workflows,
            "routing_strategy": "workflow_trigger+execution_agent_support",
            "interaction_mode": interaction_mode,
            "interactionMode": interaction_mode,
            "reception_mode": reception_mode,
            "receptionMode": reception_mode,
            "execution_support": execution_support,
        }
        route_decision = self.normalize_route_decision(
            rules.enrich_route_decision_with_workflow_mode(
                route_decision,
                text=text,
                intent=intent,
                interaction_mode=interaction_mode,
                reception_mode=reception_mode,
            ),
            route_message=route_message,
            metadata=metadata,
        )
        return {
            "intent": intent,
            "workflow": selected_workflow,
            "route_message": route_message,
            "route_decision": route_decision,
        }

    def normalize_route_decision(
        self,
        route_decision: dict[str, Any] | None,
        *,
        route_message: object | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized = dict(route_decision or {})
        metadata = dict(metadata or {})

        workflow_mode = str(_route_value(normalized, "workflow_mode") or "chat").strip() or "chat"
        requires_permission = bool(_route_value(normalized, "requires_permission"))
        required_capabilities = [
            str(item).strip()
            for item in _ensure_list(_route_value(normalized, "required_capabilities"))
            if str(item).strip()
        ]
        execution_scope = str(_route_value(normalized, "execution_scope") or "read_only").strip() or "read_only"
        approval_required = bool(
            _route_value(normalized, "approval_required") or _route_value(normalized, "requires_approval")
        )
        interaction_mode = str(_route_value(normalized, "interaction_mode") or "").strip()
        reception_mode = str(_route_value(normalized, "reception_mode") or "").strip()

        execution_plan = _ensure_dict(_route_value(normalized, "execution_plan"))
        if not execution_plan:
            routing_strategy = _canonical_routing_strategy(_route_value(normalized, "routing_strategy")) or "single_step"
            execution_plan = {
                "mode": workflow_mode,
                "strategy": routing_strategy,
                "step_count": 1,
                "required_capabilities": list(required_capabilities),
                "metadata": metadata,
            }
            execution_agent_id = _route_value(normalized, "execution_agent_id")
            if execution_agent_id:
                execution_plan["execution_agent_id"] = execution_agent_id
            workflow_id = _route_value(normalized, "workflow_id")
            if workflow_id:
                execution_plan["workflow_id"] = workflow_id
        execution_plan.setdefault(
            "plan_type",
            "multi_agent" if isinstance(execution_plan.get("steps"), list) and len(execution_plan.get("steps") or []) > 1 else "single_path",
        )
        execution_plan.setdefault("planner", "brain_router")
        execution_plan.setdefault("aggregator", "brain_router")
        execution_plan.setdefault(
            "coordination_mode",
            "parallel"
            if str(execution_plan.get("coordination_mode") or "").strip().lower() == "parallel"
            else "serial",
        )
        execution_plan["step_count"] = max(
            int(execution_plan.get("step_count") or 0),
            len(execution_plan.get("steps") or []) if isinstance(execution_plan.get("steps"), list) else 1,
        )
        execution_plan["fallback_strategy"] = _fallback_mode(normalized)
        execution_plan["metadata"] = {
            **_ensure_dict(execution_plan.get("metadata")),
            **metadata,
        }

        _set_route_value(normalized, "workflow_mode", workflow_mode)
        _set_route_value(normalized, "requires_permission", requires_permission)
        _set_route_value(normalized, "required_capabilities", required_capabilities)
        _set_route_value(normalized, "execution_scope", execution_scope)
        _set_route_value(normalized, "approval_required", approval_required)
        _set_route_value(normalized, "execution_plan", execution_plan)
        _set_route_value(
            normalized,
            "route_message",
            str(route_message or _route_value(normalized, "route_message") or "").strip(),
        )
        if interaction_mode:
            _set_route_value(normalized, "interaction_mode", interaction_mode)
        if reception_mode:
            _set_route_value(normalized, "reception_mode", reception_mode)

        for key in (
            "workflow_id",
            "workflow_name",
            "execution_agent_id",
            "execution_agent",
            "selected_by_message_trigger",
            "intent_confidence",
            "intent_scores",
            "intent_reasons",
            "candidate_workflows",
            "skipped_workflows",
            "routing_strategy",
            "execution_support",
            "route_version",
            "confirmation_required",
            "confirmation_status",
            "confirmation_deadline_at",
            "requires_approval",
            "approval_status",
            "audit_id",
            "idempotency_key",
            "evidence_policy",
            "schedule_plan",
            "user_visible_workflow_mode",
        ):
            value = _route_value(normalized, key)
            if value is None:
                continue
            if key in {"candidate_workflows", "skipped_workflows"}:
                value = _ensure_list(value)
            elif key in {"intent_scores", "intent_reasons", "execution_support", "schedule_plan"}:
                value = _ensure_dict(value)
            _set_route_value(normalized, key, value)

        _set_route_value(normalized, "route_rationale", _build_route_rationale(normalized))
        _set_route_value(normalized, "fallback_policy", _build_fallback_policy(normalized, execution_plan))

        return normalized

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


routing_service = RoutingService()
