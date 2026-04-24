from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.platform.contracts.payload_aliases import (
    alias_bool,
    alias_dict,
    alias_text,
    execution_plan_from_payload,
    route_decision_from_payload,
    route_decision_from_task,
)
from app.modules.reception.application.manager_service import brain_manager_service
from app.modules.reception.schemas.messages import UnifiedMessage
from app.platform.contracts.execution_protocol import ExecutionRequest


MESSAGE_INGRESS_FORBIDDEN_WORKFLOW_IDS = {"__agent_dispatch__", "__direct_agent_fallback__"}


def _text(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: object) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _bool_alias(payload: dict[str, Any] | None, snake_key: str, camel_key: str) -> bool:
    if not isinstance(payload, dict):
        return False
    value = payload.get(snake_key)
    if isinstance(value, bool):
        return value
    value = payload.get(camel_key)
    return bool(value) if isinstance(value, bool) else False


def _set_protocol_field(payload: dict[str, Any] | None, snake_key: str, camel_key: str, value: object) -> None:
    if not isinstance(payload, dict):
        return
    payload[snake_key] = value
    payload[camel_key] = value


def _build_execution_plan_step(step: dict[str, Any], *, index: int) -> dict[str, Any]:
    execution_agent = _text(step.get("execution_agent") or step.get("executionAgent")) or "unknown"
    intent = _text(step.get("intent")) or None
    role = _text(step.get("role")) or None
    step_id = _text(step.get("id")) or f"step-{index + 1}"
    return {
        "id": step_id,
        "index": index,
        "branch_id": _text(step.get("branch_id") or step.get("branchId")),
        "intent": intent,
        "role": role,
        "completion_policy": _text(step.get("completion_policy") or step.get("completionPolicy")),
        "depends_on": _list(step.get("depends_on") or step.get("dependsOn")),
        "execution_agent_id": _text(step.get("execution_agent_id") or step.get("executionAgentId")),
        "execution_agent": execution_agent,
        "agent_type": _text(step.get("agent_type") or step.get("agentType")),
        "title": f"{execution_agent}{f' · {role}' if role else ''}",
    }


def build_execution_plan_snapshot(
    *,
    route_decision: dict[str, Any] | None,
    manager_packet: dict[str, Any] | None,
) -> dict[str, Any]:
    route_decision = _dict(route_decision)
    manager_packet = _dict(manager_packet)
    execution_plan = execution_plan_from_payload(route_decision) or {}
    fallback_policy = alias_dict(route_decision, "fallback_policy", "fallbackPolicy") or {}
    route_rationale = alias_dict(route_decision, "route_rationale", "routeRationale") or {}

    execution_agent = alias_text(route_decision, "execution_agent", "executionAgent")
    execution_agent_id = alias_text(route_decision, "execution_agent_id", "executionAgentId")
    workflow_id = alias_text(route_decision, "workflow_id", "workflowId")
    workflow_name = alias_text(route_decision, "workflow_name", "workflowName")
    coordination_mode = alias_text(execution_plan, "coordination_mode", "coordinationMode") or "serial"
    plan_type = alias_text(execution_plan, "plan_type", "planType") or "single_path"
    steps = [
        _build_execution_plan_step(step, index=index)
        for index, step in enumerate(_list(execution_plan.get("steps")))
        if isinstance(step, dict)
    ]
    if not steps:
        steps = [
            {
                "id": "dispatch",
                "index": 0,
                "intent": _text(route_decision.get("intent")),
                "role": "execution",
                "execution_agent_id": execution_agent_id,
                "execution_agent": execution_agent or workflow_name or "unknown",
                "agent_type": None,
                "title": execution_agent or workflow_name or "主脑调度",
            }
        ]

    current_owner = _text(manager_packet.get("next_owner") or manager_packet.get("nextOwner")) or steps[0]["execution_agent"]
    plan_summary = _text(execution_plan.get("summary")) or " -> ".join(
        step["execution_agent"] for step in steps if _text(step.get("execution_agent"))
    )
    return {
        "version": "execution_plan.v1",
        "planner": _text(execution_plan.get("planner")) or "brain_router",
        "aggregator": _text(execution_plan.get("aggregator")) or "brain_router",
        "plan_type": plan_type,
        "coordination_mode": coordination_mode,
        "step_count": max(int(execution_plan.get("step_count") or 0), len(steps)),
        "planned_agent_count": max(int(execution_plan.get("planned_agent_count") or 0), len(steps)),
        "workflow_id": workflow_id,
        "workflow_name": workflow_name,
        "execution_agent_id": execution_agent_id,
        "execution_agent": execution_agent,
        "current_owner": current_owner,
        "summary": plan_summary,
        "steps": steps,
        "fan_out": alias_dict(execution_plan, "fan_out", "fanOut") or {},
        "fan_in": alias_dict(execution_plan, "fan_in", "fanIn") or {},
        "winner_strategy": alias_text(execution_plan, "winner_strategy", "winnerStrategy"),
        "quorum": _dict(execution_plan.get("quorum")),
        "merge_strategy": alias_text(execution_plan, "merge_strategy", "mergeStrategy"),
        "cancel_policy": alias_dict(execution_plan, "cancel_policy", "cancelPolicy") or {},
        "fallback": {
            "mode": _text(fallback_policy.get("mode")),
            "target": _text(fallback_policy.get("target")),
            "on_failure": alias_text(fallback_policy, "on_failure", "onFailure"),
            "summary": _text(fallback_policy.get("summary")),
        },
        "route_rationale": {
            "intent": _text(route_rationale.get("intent")),
            "workflow_mode": alias_text(route_rationale, "workflow_mode", "workflowMode"),
            "interaction_mode": alias_text(route_rationale, "interaction_mode", "interactionMode"),
            "routing_strategy": alias_text(route_rationale, "routing_strategy", "routingStrategy"),
            "route_reason_summary": alias_text(route_rationale, "route_reason_summary", "routeReasonSummary"),
            "candidate_count": int(alias_text(route_rationale, "candidate_count", "candidateCount") or 0),
            "skipped_count": int(alias_text(route_rationale, "skipped_count", "skippedCount") or 0),
        },
        "metadata": _dict(execution_plan.get("metadata")),
    }


@dataclass(frozen=True, slots=True)
class ConfirmationFollowUpPlan:
    run_id: str | None
    should_sync_run_from_task: bool
    should_tick_run: bool


@dataclass(frozen=True, slots=True)
class ContextPatchFollowUpPlan:
    run_id: str | None
    should_append_patch_to_run: bool
    should_persist_task_steps: bool


@dataclass(frozen=True, slots=True)
class MessageDispatchMetadata:
    route_decision: dict[str, Any]
    manager_packet: dict[str, Any]
    brain_dispatch_summary: dict[str, Any]
    confirmation_pending: bool


@dataclass(frozen=True, slots=True)
class MessageTaskArtifacts:
    route_decision: dict[str, Any]
    manager_packet: dict[str, Any]
    brain_dispatch_summary: dict[str, Any]
    dispatch_context: dict[str, Any]
    task: dict[str, Any]
    task_steps: list[dict[str, Any]]
    confirmation_pending: bool


@dataclass(frozen=True, slots=True)
class MessageRunLaunchPlan:
    mode: str
    workflow_id: str | None
    execution_agent_id: str | None
    should_queue_agent_execution: bool


@dataclass(slots=True)
class OrchestrationService:
    """Build execution-gateway requests from brain decisions."""

    def build_execution_request(
        self,
        *,
        tool_id: str,
        payload: dict[str, Any],
        task_id: str | None = None,
        run_id: str | None = None,
        workflow_mode: str | None = None,
    ) -> ExecutionRequest:
        trace_context = {
            "task_id": task_id,
            "run_id": run_id,
            "workflow_mode": workflow_mode or "unknown",
        }
        return ExecutionRequest(
            tool_id=tool_id,
            payload=dict(payload),
            trace_context=trace_context,
        )

    def build_message_dispatch_context(
        self,
        *,
        message: UnifiedMessage,
        entrypoint: str,
        entrypoint_agent: str,
        trace_id: str,
        preferred_language: str | None,
        memory_hits: int,
        memory_items: list[dict[str, Any]],
        memory_injection_summary: dict[str, Any] | None = None,
        route_decision: dict[str, Any],
        manager_packet: dict[str, Any] | None,
        interaction_mode: str,
        truncate_text: Any,
        dispatch_context_memory_items: Any,
        build_channel_delivery_binding: Any,
        preview_limit: int,
        now_string: Any,
        clone: Any,
        tenant_id: str | None = None,
        tenant_name: str | None = None,
        security_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        reception_mode = str(
            route_decision.get("reception_mode") or route_decision.get("receptionMode") or ""
        ).strip() or None
        request_context = {
            "channel": message.channel.value,
            "message_id": str(message.message_id),
            "platform_user_id": str(message.platform_user_id),
            "chat_id": str(message.chat_id),
            "session_id": str(message.session_id or ""),
            "user_key": str(message.user_key or ""),
            "detected_lang": message.detected_lang,
        }
        dispatch_context = {
            "type": "message_dispatch",
            "state": "queued",
            "queued_at": now_string(),
            "entrypoint": entrypoint,
            "entrypoint_agent": entrypoint_agent,
            "trace_id": trace_id,
            "channel": message.channel.value,
            "message_id": str(message.message_id),
            "platform_user_id": str(message.platform_user_id),
            "chat_id": str(message.chat_id),
            "user_key": str(message.user_key or ""),
            "session_id": str(message.session_id or ""),
            "detected_lang": message.detected_lang,
            "preferred_language": preferred_language,
            "message_preview": truncate_text(message.text, preview_limit),
            "memory_hits": memory_hits,
            "memory_items": dispatch_context_memory_items(memory_items),
            "memory_injection": clone(memory_injection_summary or {}),
            "interaction_mode": interaction_mode,
            "interactionMode": interaction_mode,
            "reception_mode": reception_mode,
            "receptionMode": reception_mode,
            "route_decision": clone(route_decision),
            "request_context": request_context,
        }
        if tenant_id:
            dispatch_context["tenant_context"] = {
                "tenant_id": tenant_id,
                "tenant_name": tenant_name or f"{tenant_id} 租户",
            }
        if isinstance(security_context, dict) and security_context:
            dispatch_context["security_context"] = clone(security_context)
        execution_plan = route_decision.get("execution_plan") or route_decision.get("executionPlan")
        if isinstance(execution_plan, dict) and execution_plan:
            dispatch_context["execution_plan"] = clone(execution_plan)
        dispatch_context["execution_plan_snapshot"] = build_execution_plan_snapshot(
            route_decision=route_decision,
            manager_packet=manager_packet,
        )
        fallback_policy = route_decision.get("fallback_policy") or route_decision.get("fallbackPolicy")
        if isinstance(fallback_policy, dict) and fallback_policy:
            dispatch_context["fallback_policy"] = clone(fallback_policy)
        route_rationale = route_decision.get("route_rationale") or route_decision.get("routeRationale")
        if isinstance(route_rationale, dict) and route_rationale:
            dispatch_context["route_rationale"] = clone(route_rationale)
        if isinstance(manager_packet, dict) and manager_packet:
            dispatch_context["manager_packet"] = clone(manager_packet)
        channel_delivery = build_channel_delivery_binding(message)
        if channel_delivery is not None:
            dispatch_context["channel_delivery"] = channel_delivery
        return dispatch_context

    def build_task_state_machine(
        self,
        *,
        dispatch_state: str,
        task_status: str,
        manager_packet: dict[str, Any] | None,
        version: str,
    ) -> dict[str, Any]:
        return {
            "version": version,
            "dispatch_state": str(dispatch_state or "queued"),
            "task_status": str(task_status or "pending"),
            "session_state": _text((manager_packet or {}).get("session_state")),
        }

    def build_message_task_record(
        self,
        *,
        task_id: str,
        intent: str,
        message_text: str,
        route_decision: dict[str, Any],
        manager_packet: dict[str, Any] | None,
        brain_dispatch_summary: dict[str, Any] | None,
        memory_items: list[dict[str, Any]],
        memory_injection_summary: dict[str, Any] | None,
        execution_agent_name: str,
        confirmation_pending: bool,
        channel: str,
        user_key: str,
        session_id: str,
        preferred_language: str | None,
        detected_lang: str | None,
        trace_id: str,
        created_at: str,
        dispatch_state: str,
        state_machine_version: str,
        clone: Any,
        memory_context_lines: Any,
        tenant_id: str | None = None,
        tenant_name: str | None = None,
        security_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        task_status = "pending" if confirmation_pending else "running"
        task_state_machine = self.build_task_state_machine(
            dispatch_state=dispatch_state,
            task_status=task_status,
            manager_packet=manager_packet,
            version=state_machine_version,
        )
        schedule_plan = route_decision.get("schedule_plan") or route_decision.get("schedulePlan")
        return {
            "id": task_id,
            "title": f"渠道消息任务 - {intent}",
            "description": "\n".join([message_text, *memory_context_lines(memory_items)]),
            "status": task_status,
            "priority": "medium",
            "created_at": created_at,
            "completed_at": None,
            "agent": execution_agent_name,
            "tokens": 0,
            "duration": None,
            "channel": channel,
            "user_key": user_key,
            "session_id": session_id,
            "trace_id": trace_id,
            "preferred_language": preferred_language,
            "detected_lang": detected_lang,
            "confirmation_status": _text(
                route_decision.get("confirmation_status") or route_decision.get("confirmationStatus")
            ),
            "approval_status": _text(
                route_decision.get("approval_status") or route_decision.get("approvalStatus")
            ),
            "approval_required": bool(
                route_decision.get("approval_required")
                if isinstance(route_decision.get("approval_required"), bool)
                else route_decision.get("approvalRequired")
            ),
            "audit_id": _text(route_decision.get("audit_id") or route_decision.get("auditId")),
            "idempotency_key": _text(
                route_decision.get("idempotency_key") or route_decision.get("idempotencyKey")
            ),
            "execution_scope": _text(
                route_decision.get("execution_scope") or route_decision.get("executionScope")
            ),
            "schedule_plan": clone(schedule_plan) if isinstance(schedule_plan, dict) else None,
            "route_decision": clone(route_decision),
            "manager_packet": clone(manager_packet or {}),
            "brain_dispatch_summary": clone(brain_dispatch_summary or {}),
            "memory_injection_summary": clone(memory_injection_summary or {}),
            "context_patch_audit": [],
            "state_machine": task_state_machine,
            "result": None,
            "tenant_id": tenant_id,
            "tenant_name": tenant_name,
            "security_context": clone(security_context or {}),
        }

    def prepare_message_dispatch_metadata(
        self,
        *,
        route_decision: dict[str, Any],
        manager_packet: dict[str, Any] | None,
        brain_dispatch_summary: dict[str, Any] | None,
        interaction_mode: str,
        approval_required: bool,
        confirmation_status: str | None,
        confirmation_required: bool,
        clone: Any,
    ) -> MessageDispatchMetadata:
        normalized_route_decision = clone(route_decision)
        normalized_manager_packet = clone(manager_packet or {})
        normalized_summary = clone(brain_dispatch_summary or {})

        _set_protocol_field(
            normalized_route_decision,
            "interaction_mode",
            "interactionMode",
            interaction_mode,
        )
        brain_manager_service.refresh_manager_packet(
            normalized_manager_packet,
            approval_required=approval_required,
            confirmation_status=confirmation_status,
        )
        brain_manager_service.refresh_dispatch_summary_state(
            normalized_summary,
            normalized_manager_packet,
        )
        confirmation_pending = bool(confirmation_required and confirmation_status == "pending")
        return MessageDispatchMetadata(
            route_decision=normalized_route_decision,
            manager_packet=normalized_manager_packet,
            brain_dispatch_summary=normalized_summary,
            confirmation_pending=confirmation_pending,
        )

    def build_message_task_artifacts(
        self,
        *,
        task_id: str,
        message: UnifiedMessage,
        entrypoint: str,
        entrypoint_agent: str,
        trace_id: str,
        preferred_language: str | None,
        memory_hits: int,
        memory_items: list[dict[str, Any]],
        memory_injection_summary: dict[str, Any] | None,
        metadata: MessageDispatchMetadata,
        intent: str,
        route_message: str,
        execution_agent_name: str,
        agent_dispatch: bool,
        state_machine_version: str,
        warnings: list[str],
        truncate_text: Any,
        dispatch_context_memory_items: Any,
        build_channel_delivery_binding: Any,
        preview_limit: int,
        now_string: Any,
        clone: Any,
        memory_context_lines: Any,
        memory_step_message: Any,
        tenant_id: str | None = None,
        tenant_name: str | None = None,
        security_context: dict[str, Any] | None = None,
    ) -> MessageTaskArtifacts:
        interaction_mode = _text(
            metadata.route_decision.get("interaction_mode") or metadata.route_decision.get("interactionMode")
        ) or "task"
        dispatch_context = self.build_message_dispatch_context(
            message=message,
            entrypoint=entrypoint,
            entrypoint_agent=entrypoint_agent,
            trace_id=trace_id,
            preferred_language=preferred_language,
            memory_hits=memory_hits,
            memory_items=memory_items,
            memory_injection_summary=memory_injection_summary,
            route_decision=metadata.route_decision,
            manager_packet=metadata.manager_packet,
            interaction_mode=interaction_mode,
            truncate_text=truncate_text,
            dispatch_context_memory_items=dispatch_context_memory_items,
            build_channel_delivery_binding=build_channel_delivery_binding,
            preview_limit=preview_limit,
            now_string=now_string,
            clone=clone,
            tenant_id=tenant_id,
            tenant_name=tenant_name,
            security_context=security_context,
        )
        if metadata.confirmation_pending:
            dispatch_context["state"] = "awaiting_confirmation"
        dispatch_context["brain_dispatch_summary"] = clone(metadata.brain_dispatch_summary)
        dispatch_state = str(dispatch_context.get("state") or "queued")
        dispatch_context["state_machine"] = self.build_task_state_machine(
            dispatch_state=dispatch_state,
            task_status="pending" if metadata.confirmation_pending else "running",
            manager_packet=metadata.manager_packet,
            version=state_machine_version,
        )
        task = self.build_message_task_record(
            task_id=task_id,
            intent=intent,
            message_text=message.text,
            route_decision=metadata.route_decision,
            manager_packet=metadata.manager_packet,
            brain_dispatch_summary=metadata.brain_dispatch_summary,
            memory_items=memory_items,
            memory_injection_summary=memory_injection_summary,
            execution_agent_name=execution_agent_name,
            confirmation_pending=metadata.confirmation_pending,
            channel=message.channel.value,
            user_key=message.user_key,
            session_id=message.session_id,
            preferred_language=preferred_language,
            detected_lang=message.detected_lang,
            trace_id=trace_id,
            created_at=now_string(),
            dispatch_state=dispatch_state,
            state_machine_version=state_machine_version,
            clone=clone,
            memory_context_lines=memory_context_lines,
            tenant_id=tenant_id,
            tenant_name=tenant_name,
            security_context=security_context,
        )
        task_steps = self.create_task_steps(
            task_id=task_id,
            entrypoint_agent=entrypoint_agent,
            memory_items=memory_items,
            memory_injection_summary=memory_injection_summary,
            trace_id=trace_id,
            warnings=warnings,
            route_message=route_message,
            manager_packet=metadata.manager_packet,
            execution_agent_name=execution_agent_name,
            agent_dispatch=agent_dispatch,
            waiting_for_confirmation=metadata.confirmation_pending,
            now_string=now_string,
            memory_step_message=memory_step_message,
        )
        return MessageTaskArtifacts(
            route_decision=metadata.route_decision,
            manager_packet=metadata.manager_packet,
            brain_dispatch_summary=metadata.brain_dispatch_summary,
            dispatch_context=dispatch_context,
            task=task,
            task_steps=task_steps,
            confirmation_pending=metadata.confirmation_pending,
        )

    def build_message_run_launch_plan(
        self,
        *,
        agent_dispatch: bool,
        confirmation_pending: bool,
        workflow_id: str | None,
        route_decision: dict[str, Any],
    ) -> MessageRunLaunchPlan:
        resolved_workflow_id = _text(
            workflow_id
            or route_decision.get("workflow_id")
            or route_decision.get("workflowId")
        )
        if agent_dispatch:
            raise ValueError("Message ingress launch plan no longer supports agent_dispatch mode")
        if not resolved_workflow_id:
            raise ValueError("Message ingress launch plan requires a real workflow_id")
        if resolved_workflow_id in MESSAGE_INGRESS_FORBIDDEN_WORKFLOW_IDS:
            raise ValueError("Message ingress launch plan must resolve to a real workflow")
        execution_agent_id = _text(
            route_decision.get("execution_agent_id") or route_decision.get("executionAgentId")
        )
        return MessageRunLaunchPlan(
            mode="workflow_run",
            workflow_id=resolved_workflow_id,
            execution_agent_id=execution_agent_id,
            should_queue_agent_execution=False,
        )

    def apply_confirmation_transition(
        self,
        *,
        task: dict[str, Any],
        run: dict[str, Any] | None,
        action: str,
        transition: Any,
        now_string: Any,
    ) -> None:
        route_decision = route_decision_from_task(task)
        _set_protocol_field(route_decision, "confirmation_status", "confirmationStatus", action)
        task["confirmation_status"] = action
        task["status"] = transition.task_status
        task["completed_at"] = (
            task.get("completed_at") or transition.completed_at
            if transition.completed_at is not None
            else None
        )

        approval_required = alias_bool(route_decision, "approval_required", "approvalRequired") or False
        manager_packet = task.get("manager_packet")
        brain_dispatch_summary = task.get("brain_dispatch_summary")
        brain_manager_service.refresh_manager_packet(
            manager_packet,
            approval_required=approval_required,
            confirmation_status=action,
            manager_action=transition.manager_update.manager_action,
            next_owner=transition.manager_update.next_owner,
            handoff_summary=transition.manager_update.handoff_summary,
            reception_mode=transition.manager_update.reception_mode,
        )
        brain_manager_service.refresh_dispatch_summary_state(brain_dispatch_summary, manager_packet)

        dispatch_context = (run or {}).get("dispatch_context")
        if not isinstance(dispatch_context, dict):
            return
        dispatch_route_decision = route_decision_from_payload(dispatch_context)
        _set_protocol_field(dispatch_route_decision, "confirmation_status", "confirmationStatus", action)
        dispatch_context["updated_at"] = now_string()
        dispatch_context["state"] = transition.dispatch_state
        dispatch_manager_packet = dispatch_context.get("manager_packet")
        dispatch_summary = (
            dispatch_context.get("brain_dispatch_summary")
            or dispatch_context.get("brainDispatchSummary")
        )
        brain_manager_service.refresh_manager_packet(
            dispatch_manager_packet,
            approval_required=approval_required,
            confirmation_status=action,
            manager_action=transition.manager_update.manager_action,
            next_owner=transition.manager_update.next_owner,
            handoff_summary=transition.manager_update.handoff_summary,
            reception_mode=transition.manager_update.reception_mode,
        )
        brain_manager_service.refresh_dispatch_summary_state(dispatch_summary, dispatch_manager_packet)

    def apply_context_patch_plan(
        self,
        *,
        task: dict[str, Any],
        plan: Any,
    ) -> dict[str, Any]:
        task["description"] = plan.updated_description
        task["updated_at"] = plan.updated_at
        task["tokens"] = task.get("tokens", 0) + plan.token_delta

        manager_packet = task.get("manager_packet")
        brain_manager_service.refresh_manager_packet(
            manager_packet,
            approval_required=bool(task.get("approval_required")),
            confirmation_status=str(task.get("confirmation_status") or "").strip() or None,
            manager_action=plan.manager_update.manager_action,
            next_owner=plan.manager_update.next_owner,
            handoff_summary=plan.manager_update.handoff_summary,
            reception_mode=plan.manager_update.reception_mode,
        )
        brain_manager_service.refresh_dispatch_summary_state(task.get("brain_dispatch_summary"), manager_packet)

        updated_session_state = str((manager_packet or {}).get("session_state") or "").strip() or None
        audit_entry = dict(plan.audit_entry)
        audit_entry["session_state"] = updated_session_state
        task.setdefault("context_patch_audit", []).append(audit_entry)

        step_entry = dict(plan.step_entry)
        metadata = dict(step_entry.get("metadata") or {})
        metadata["session_state"] = updated_session_state
        step_entry["metadata"] = metadata

        realtime_metadata = dict(plan.realtime_metadata)
        realtime_metadata["manager_action"] = str((manager_packet or {}).get("manager_action") or "").strip() or None
        realtime_metadata["session_state"] = updated_session_state
        return {
            "audit_entry": audit_entry,
            "step_entry": step_entry,
            "realtime_metadata": realtime_metadata,
        }

    def build_confirmation_step(
        self,
        *,
        task_id: str,
        existing_step_count: int,
        title: str,
        message: str,
        status_value: str = "completed",
        now_string: Any,
    ) -> dict[str, Any]:
        timestamp = now_string()
        return {
            "id": f"{task_id}-confirm-{existing_step_count + 1}",
            "title": title,
            "status": status_value,
            "agent": "项目经理 Agent",
            "started_at": timestamp,
            "finished_at": timestamp if status_value in {"completed", "cancelled"} else None,
            "message": message,
            "tokens": 0,
        }

    def build_confirmation_follow_up_plan(
        self,
        *,
        task: dict[str, Any],
        action: str,
    ) -> ConfirmationFollowUpPlan:
        run_id = _text(task.get("workflow_run_id") or task.get("workflowRunId"))
        normalized_action = str(action or "").strip().lower()
        should_sync_run_from_task = normalized_action == "cancel" and run_id is not None
        should_tick_run = normalized_action != "cancel" and run_id is not None
        return ConfirmationFollowUpPlan(
            run_id=run_id,
            should_sync_run_from_task=should_sync_run_from_task,
            should_tick_run=should_tick_run,
        )

    def build_context_patch_step(
        self,
        *,
        task_id: str,
        existing_step_count: int,
        step_entry: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "id": f"{task_id}-ctx-{existing_step_count + 1}",
            **dict(step_entry),
        }

    def build_context_patch_follow_up_plan(
        self,
        *,
        task: dict[str, Any],
    ) -> ContextPatchFollowUpPlan:
        run_id = _text(task.get("workflow_run_id") or task.get("workflowRunId"))
        return ContextPatchFollowUpPlan(
            run_id=run_id,
            should_append_patch_to_run=run_id is not None,
            should_persist_task_steps=run_id is None,
        )

    def create_task_steps(
        self,
        *,
        task_id: str,
        entrypoint_agent: str,
        memory_items: list[dict[str, Any]],
        memory_injection_summary: dict[str, Any] | None = None,
        trace_id: str,
        warnings: list[str],
        route_message: str,
        manager_packet: dict[str, Any] | None,
        execution_agent_name: str,
        agent_dispatch: bool = False,
        waiting_for_confirmation: bool = False,
        now_string: Any,
        memory_step_message: Any,
    ) -> list[dict[str, Any]]:
        warning_suffix = f"，附带处理: {', '.join(warnings)}" if warnings else ""
        if waiting_for_confirmation:
            final_step_title = "等待确认"
            final_step_agent = str((manager_packet or {}).get("manager_agent") or "项目经理 Agent")
            final_step_message = "专业工作流已完成分发评估，等待用户确认后才会进入执行"
        else:
            final_step_title = "执行节点" if agent_dispatch else "等待调度"
            final_step_agent = execution_agent_name if agent_dispatch else "Workflow Dispatcher"
            final_step_message = (
                f"已直达 {execution_agent_name}，等待 Agent Worker 执行"
                if agent_dispatch
                else f"已生成 dispatch context，等待派发到 {execution_agent_name}"
            )
        manager_handoff = (
            str((manager_packet or {}).get("handoff_summary") or "").strip()
            if isinstance(manager_packet, dict)
            else ""
        )
        route_excerpt = str(route_message or "").strip()
        manager_metadata = {
            "state_machine_version": "brain_fact_layer_v1",
            "manager_action": str((manager_packet or {}).get("manager_action") or "").strip() or None,
            "next_owner": str((manager_packet or {}).get("next_owner") or "").strip() or None,
            "delivery_mode": str((manager_packet or {}).get("delivery_mode") or "").strip() or None,
            "decomposition_hint": str((manager_packet or {}).get("decomposition_hint") or "").strip() or None,
            "workflow_admission": str((manager_packet or {}).get("workflow_admission") or "").strip() or None,
            "session_state": str((manager_packet or {}).get("session_state") or "").strip() or None,
        }
        return [
            {
                "id": f"{task_id}-1",
                "title": "接入层标准化",
                "status": "completed",
                "agent": entrypoint_agent,
                "started_at": now_string(),
                "finished_at": now_string(),
                "message": f"渠道负载已标准化为 UnifiedMessage (trace={trace_id})",
                "tokens": 0,
            },
            {
                "id": f"{task_id}-2",
                "title": "安全网关",
                "status": "completed",
                "agent": "安全网关",
                "started_at": now_string(),
                "finished_at": now_string(),
                "message": f"消息已通过五层安全检查{warning_suffix}",
                "tokens": 0,
            },
            {
                "id": f"{task_id}-3",
                "title": "长期记忆检索",
                "status": "completed",
                "agent": "Memory Service",
                "started_at": now_string(),
                "finished_at": now_string(),
                "message": memory_step_message(memory_items),
                "metadata": dict(memory_injection_summary or {}),
                "tokens": 0,
            },
            {
                "id": f"{task_id}-4",
                "title": "项目经理分发",
                "status": "completed",
                "agent": str((manager_packet or {}).get("manager_agent") or "项目经理 Agent"),
                "started_at": now_string(),
                "finished_at": now_string(),
                "message": (
                    (
                        manager_handoff
                        if not route_excerpt or route_excerpt in manager_handoff
                        else f"{manager_handoff}；{route_excerpt}"
                    )
                    if manager_handoff
                    else route_excerpt
                )
                + (
                    f"；next_owner={manager_metadata['next_owner']}"
                    if manager_metadata["next_owner"]
                    else ""
                ),
                "metadata": manager_metadata,
                "tokens": 0,
            },
            {
                "id": f"{task_id}-5",
                "title": final_step_title,
                "status": "running",
                "agent": final_step_agent,
                "started_at": now_string(),
                "finished_at": None,
                "message": (
                    final_step_message
                    + (
                        f"；delivery_mode={manager_metadata['delivery_mode']}"
                        if manager_metadata["delivery_mode"]
                        else ""
                    )
                ),
                "metadata": manager_metadata,
                "tokens": 0,
            },
        ]


orchestration_service = OrchestrationService()
