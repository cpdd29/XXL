from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.brain_payload_fields import alias_bool, alias_text, execution_plan_from_payload
from app.brain_core.manager.policies import (
    build_clarify_question,
    build_decomposition_hint,
    build_delivery_mode,
    build_handoff_summary,
    build_manager_action,
    build_manager_session_state,
    build_manager_state_label,
    build_next_owner,
    build_response_contract,
    build_task_shape,
    build_workflow_admission,
    clarify_required_for_reception_mode,
    truncate_manager_text,
)
from app.brain_core.reception.service import ReceptionPayload

@dataclass(slots=True)
class BrainManagerPacket:
    manager_agent: str
    manager_role: str
    user_goal: str
    intent: str
    interaction_mode: str
    reception_mode: str | None
    workflow_mode: str | None
    workflow_admission: str
    task_shape: str
    decomposition_hint: str
    delivery_mode: str
    clarify_required: bool
    clarify_question: str | None
    manager_action: str
    next_owner: str
    response_contract: str
    handoff_summary: str
    routing_note: str
    session_state: str
    state_label: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "manager_agent": self.manager_agent,
            "manager_role": self.manager_role,
            "user_goal": self.user_goal,
            "intent": self.intent,
            "interaction_mode": self.interaction_mode,
            "reception_mode": self.reception_mode,
            "workflow_mode": self.workflow_mode,
            "workflow_admission": self.workflow_admission,
            "task_shape": self.task_shape,
            "decomposition_hint": self.decomposition_hint,
            "delivery_mode": self.delivery_mode,
            "clarify_required": self.clarify_required,
            "clarify_question": self.clarify_question,
            "manager_action": self.manager_action,
            "next_owner": self.next_owner,
            "response_contract": self.response_contract,
            "handoff_summary": self.handoff_summary,
            "routing_note": self.routing_note,
            "session_state": self.session_state,
            "state_label": self.state_label,
        }


class BrainManagerService:
    """Local receptionist + project manager packet builder for the brain trusted zone."""

    def build_manager_packet(
        self,
        *,
        reception: ReceptionPayload,
        intent: str,
        route_decision: dict[str, Any],
        route_message: str,
        interaction_mode: str,
        reception_mode: str | None,
        execution_agent_name: str,
    ) -> BrainManagerPacket:
        language = str(reception.language or "zh").strip().lower() or "zh"
        workflow_mode = alias_text(route_decision, "workflow_mode", "workflowMode")
        execution_plan = execution_plan_from_payload(route_decision)
        approval_required = bool(alias_bool(route_decision, "approval_required", "approvalRequired"))
        requires_permission = bool(alias_bool(route_decision, "requires_permission", "requiresPermission"))
        clarify_required = clarify_required_for_reception_mode(reception_mode)
        clarify_question = (
            build_clarify_question(language=language, intent=intent)
            if clarify_required
            else None
        )
        manager_action = build_manager_action(
            interaction_mode=interaction_mode,
            reception_mode=reception_mode,
            workflow_mode=workflow_mode,
        )
        task_shape = build_task_shape(
            interaction_mode=interaction_mode,
            workflow_mode=workflow_mode,
            execution_plan=execution_plan if isinstance(execution_plan, dict) else None,
        )
        return BrainManagerPacket(
            manager_agent="项目经理 Agent",
            manager_role="reception_project_manager",
            user_goal=truncate_manager_text(reception.text, 80),
            intent=intent,
            interaction_mode=interaction_mode,
            reception_mode=reception_mode,
            workflow_mode=workflow_mode,
            workflow_admission=build_workflow_admission(
                workflow_mode=workflow_mode,
                approval_required=approval_required,
                requires_permission=requires_permission,
            ),
            task_shape=task_shape,
            decomposition_hint=build_decomposition_hint(
                manager_action=manager_action,
                task_shape=task_shape,
            ),
            delivery_mode=build_delivery_mode(
                interaction_mode=interaction_mode,
                workflow_mode=workflow_mode,
                approval_required=approval_required,
            ),
            clarify_required=clarify_required,
            clarify_question=clarify_question,
            manager_action=manager_action,
            next_owner=build_next_owner(
                manager_action=manager_action,
                execution_agent_name=execution_agent_name,
            ),
            response_contract=build_response_contract(
                interaction_mode=interaction_mode,
                reception_mode=reception_mode,
            ),
            handoff_summary=build_handoff_summary(
                intent=intent,
                interaction_mode=interaction_mode,
                reception_mode=reception_mode,
                workflow_mode=workflow_mode,
                execution_agent_name=execution_agent_name,
                route_message=route_message,
            ),
            routing_note=route_message,
            session_state=build_manager_session_state(
                manager_action=manager_action,
                clarify_required=clarify_required,
                approval_required=approval_required,
                confirmation_status=str(
                    route_decision.get("confirmation_status")
                    or route_decision.get("confirmationStatus")
                    or ""
                ).strip()
                or None,
            ),
            state_label=build_manager_state_label(
                build_manager_session_state(
                    manager_action=manager_action,
                    clarify_required=clarify_required,
                    approval_required=approval_required,
                    confirmation_status=str(
                        route_decision.get("confirmation_status")
                        or route_decision.get("confirmationStatus")
                        or ""
                    ).strip()
                    or None,
                )
            ),
        )

    def refresh_manager_packet(
        self,
        manager_packet: dict[str, Any] | None,
        *,
        approval_required: bool | None = None,
        confirmation_status: str | None = None,
        manager_action: str | None = None,
        next_owner: str | None = None,
        handoff_summary: str | None = None,
        reception_mode: str | None = None,
    ) -> dict[str, Any] | None:
        if not isinstance(manager_packet, dict) or not manager_packet:
            return manager_packet

        if manager_action is not None:
            manager_packet["manager_action"] = manager_action
        if next_owner is not None:
            manager_packet["next_owner"] = next_owner
        if handoff_summary is not None:
            manager_packet["handoff_summary"] = handoff_summary
        if reception_mode is not None:
            manager_packet["reception_mode"] = reception_mode

        session_state = build_manager_session_state(
            manager_action=str(manager_packet.get("manager_action") or "").strip(),
            clarify_required=bool(manager_packet.get("clarify_required")),
            approval_required=bool(
                approval_required
                if approval_required is not None
                else manager_packet.get("approval_required")
            ),
            confirmation_status=confirmation_status,
        )
        manager_packet["session_state"] = session_state
        manager_packet["state_label"] = build_manager_state_label(session_state)
        return manager_packet

    def refresh_dispatch_summary_state(
        self,
        summary: dict[str, Any] | None,
        manager_packet: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not isinstance(summary, dict) or not isinstance(manager_packet, dict):
            return summary
        summary["session_state"] = str(manager_packet.get("session_state") or "").strip() or None
        summary["state_label"] = str(manager_packet.get("state_label") or "").strip() or None
        return summary


brain_manager_service = BrainManagerService()
