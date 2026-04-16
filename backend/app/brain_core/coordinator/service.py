from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.brain_payload_fields import alias_bool, alias_dict, alias_text, execution_plan_from_payload
from app.brain_core.manager.service import BrainManagerService
from app.brain_core.reception.service import ReceptionPayload, ReceptionService
from app.brain_core.routing.rules import target_agent_name
from app.brain_core.routing.service import RoutingService


@dataclass(slots=True)
class BrainDispatchPlan:
    reception: ReceptionPayload
    intent: str
    workflow: dict[str, Any] | None
    route_message: str
    route_decision: dict[str, Any]
    interaction_mode: str
    reception_mode: str | None
    agent_dispatch: bool
    execution_agent_name: str
    manager_packet: dict[str, Any]
    brain_dispatch_summary: dict[str, Any]


class BrainCoordinatorService:
    """Unify reception and routing for the closed-brain entry path."""

    def __init__(
        self,
        *,
        manager_service: BrainManagerService | None = None,
        reception_service: ReceptionService | None = None,
        routing_service: RoutingService | None = None,
    ) -> None:
        self._manager_service = manager_service or BrainManagerService()
        self._reception_service = reception_service or ReceptionService()
        self._routing_service = routing_service or RoutingService()

    def build_dispatch_plan(self, payload: dict[str, Any] | None) -> BrainDispatchPlan:
        reception = self._reception_service.normalize(payload)
        route_result = self._routing_service.route_message(
            text=reception.text,
            channel=reception.channel,
            detected_lang=reception.language,
            metadata=reception.metadata,
        )
        route_decision = dict(route_result.get("route_decision") or {})
        intent = str(route_result.get("intent") or route_decision.get("intent") or "help").strip() or "help"
        route_message = str(route_result.get("route_message") or route_decision.get("route_message") or "").strip()
        interaction_mode = alias_text(route_decision, "interaction_mode", "interactionMode") or "task"
        reception_mode = alias_text(route_decision, "reception_mode", "receptionMode")
        execution_agent_name = str(
            alias_text(route_decision, "execution_agent", "executionAgent") or target_agent_name(intent)
        ).strip() or target_agent_name(intent)
        manager_packet = self._manager_service.build_manager_packet(
            reception=reception,
            intent=intent,
            route_decision=route_decision,
            route_message=route_message,
            interaction_mode=interaction_mode,
            reception_mode=reception_mode,
            execution_agent_name=execution_agent_name,
        ).to_dict()
        brain_dispatch_summary = self._build_brain_dispatch_summary(
            intent=intent,
            workflow=route_result.get("workflow"),
            route_decision=route_decision,
            manager_packet=manager_packet,
            agent_dispatch=route_result.get("workflow") is None,
            execution_agent_name=execution_agent_name,
        )

        return BrainDispatchPlan(
            reception=reception,
            intent=intent,
            workflow=route_result.get("workflow"),
            route_message=route_message,
            route_decision=route_decision,
            interaction_mode=interaction_mode,
            reception_mode=reception_mode,
            agent_dispatch=route_result.get("workflow") is None,
            execution_agent_name=execution_agent_name,
            manager_packet=manager_packet,
            brain_dispatch_summary=brain_dispatch_summary,
        )

    def _build_brain_dispatch_summary(
        self,
        *,
        intent: str,
        workflow: dict[str, Any] | None,
        route_decision: dict[str, Any],
        manager_packet: dict[str, Any],
        agent_dispatch: bool,
        execution_agent_name: str,
    ) -> dict[str, Any]:
        workflow_name = str(
            alias_text(route_decision, "workflow_name", "workflowName") or (workflow or {}).get("name") or ""
        ).strip() or None
        workflow_mode = alias_text(route_decision, "workflow_mode", "workflowMode")
        interaction_mode = alias_text(route_decision, "interaction_mode", "interactionMode")
        reception_mode = alias_text(route_decision, "reception_mode", "receptionMode")
        manager_action = str(manager_packet.get("manager_action") or "").strip() or None
        next_owner = str(manager_packet.get("next_owner") or "").strip() or None
        delivery_mode = str(manager_packet.get("delivery_mode") or "").strip() or None
        response_contract = str(manager_packet.get("response_contract") or "").strip() or None
        execution_scope = alias_text(route_decision, "execution_scope", "executionScope")
        routing_strategy = alias_text(route_decision, "routing_strategy", "routingStrategy")
        execution_plan = execution_plan_from_payload(route_decision) or {}
        fallback_policy = alias_dict(route_decision, "fallback_policy", "fallbackPolicy") or {}
        route_rationale = alias_dict(route_decision, "route_rationale", "routeRationale") or {}
        approval_required = bool(alias_bool(route_decision, "approval_required", "approvalRequired"))
        clarify_required = bool(manager_packet.get("clarify_required"))
        dispatch_mode = "agent_dispatch" if agent_dispatch else "workflow_run"
        dispatch_type = "agent_dispatch" if agent_dispatch else "workflow_run"
        dispatch_type_legacy = "direct_agent" if agent_dispatch else "workflow_run"
        dispatch_target = execution_agent_name if agent_dispatch else (workflow_name or execution_agent_name)
        summary_line = (
            f"项目经理 {manager_action or '完成分发'}"
            f" -> 路由 {workflow_mode or interaction_mode or 'unknown'}"
            f" -> {'直达' if agent_dispatch else '编排'} {dispatch_target or 'unknown'}"
        )
        return {
            "intent": intent,
            "dispatch_mode": dispatch_mode,
            "dispatch_type": dispatch_type,
            "dispatch_type_legacy": dispatch_type_legacy,
            "workflow_mode": workflow_mode,
            "interaction_mode": interaction_mode,
            "reception_mode": reception_mode,
            "workflow_name": workflow_name,
            "execution_agent": execution_agent_name,
            "manager_action": manager_action,
            "next_owner": next_owner,
            "delivery_mode": delivery_mode,
            "response_contract": response_contract,
            "clarify_required": clarify_required,
            "approval_required": approval_required,
            "execution_scope": execution_scope,
            "routing_strategy": routing_strategy,
            "execution_topology": str(execution_plan.get("plan_type") or execution_plan.get("coordination_mode") or "").strip() or None,
            "fallback_mode": str(fallback_policy.get("mode") or "").strip() or None,
            "route_reason_summary": str(route_rationale.get("route_reason_summary") or "").strip() or None,
            "summary_line": summary_line,
            "session_state": str(manager_packet.get("session_state") or "").strip() or None,
            "state_label": str(manager_packet.get("state_label") or "").strip() or None,
        }


brain_coordinator_service = BrainCoordinatorService()
