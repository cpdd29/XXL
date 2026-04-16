from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from app.core.brain_payload_fields import (
    alias_value,
    dispatch_context_from_run,
    route_decision_from_payload,
    route_decision_from_task,
)
from app.brain_core.orchestration.service import build_execution_plan_snapshot


FAILURE_STAGE_LABELS = {
    "route": "路由",
    "dispatch": "调度",
    "execution": "执行",
    "outbound": "回传",
}

DISPATCH_STATE_LABELS = {
    "queued": "等待调度",
    "dispatching": "调度中",
    "dispatched": "已派发",
    "agent_queued": "等待 Agent 执行",
    "executing": "执行中",
    "completed": "执行完成",
    "failed": "执行失败",
    "execution_timeout": "执行超时",
    "agent_execution_failed": "Agent 执行失败",
}


def _text(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


class TaskViewService:
    """Render lightweight task-facing summaries from task records."""

    def _dispatch_context(self, run: dict[str, Any] | None) -> dict[str, Any]:
        return dispatch_context_from_run(run) or {}

    def _dispatch_context_value(self, dispatch_context: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = _text(dispatch_context.get(key))
            if value is not None:
                return value
        return None

    def _normalize_failure_stage(self, value: object) -> str | None:
        normalized = str(value or "").strip().lower()
        if normalized in FAILURE_STAGE_LABELS:
            return normalized
        return None

    def _infer_failure_stage_from_step(self, step: dict[str, Any] | None) -> str | None:
        if not isinstance(step, dict):
            return None
        haystack = " ".join(
            str(step.get(key) or "").strip().lower()
            for key in ("title", "agent", "message")
        )
        if not haystack:
            return None
        if any(keyword in haystack for keyword in ("路由", "intent", "master bot")):
            return "route"
        if any(keyword in haystack for keyword in ("调度", "dispatcher")):
            return "dispatch"
        if any(keyword in haystack for keyword in ("回传", "发送结果", "输出")):
            return "outbound"
        if any(keyword in haystack for keyword in ("执行", "agent", "超时")):
            return "execution"
        return None

    def _latest_failed_step(self, steps: list[dict[str, Any]] | None) -> dict[str, Any] | None:
        if not isinstance(steps, list):
            return None
        for step in reversed(steps):
            if str(step.get("status") or "").strip().lower() == "failed":
                return step
        return None

    def _latest_active_step(self, steps: list[dict[str, Any]] | None) -> dict[str, Any] | None:
        if not isinstance(steps, list):
            return None
        for status_value in ("running", "pending"):
            for step in reversed(steps):
                if str(step.get("status") or "").strip().lower() == status_value:
                    return step
        return None

    def _derive_failure_stage(
        self,
        task: dict[str, Any],
        *,
        run: dict[str, Any] | None,
        steps: list[dict[str, Any]],
        delivery_status: str | None,
    ) -> str | None:
        dispatch_context = self._dispatch_context(run)
        explicit_failure_stage = self._normalize_failure_stage(
            dispatch_context.get("failure_stage") or dispatch_context.get("failureStage")
        )
        if explicit_failure_stage is not None:
            return explicit_failure_stage

        dispatch_state = self._dispatch_context_value(dispatch_context, "state", "dispatch_state", "dispatchState")
        if dispatch_state in {"execution_timeout", "agent_execution_failed"}:
            return "execution"

        if _text((run or {}).get("last_dispatch_error") or (run or {}).get("lastDispatchError")) is not None:
            return "dispatch"

        failed_step = self._latest_failed_step(steps)
        inferred_from_step = self._infer_failure_stage_from_step(failed_step)
        if inferred_from_step is not None:
            return inferred_from_step

        if str(task.get("status") or "").strip().lower() == "completed" and delivery_status == "failed":
            return "outbound"
        return None

    def _derive_failure_message(
        self,
        task: dict[str, Any],
        *,
        run: dict[str, Any] | None,
        steps: list[dict[str, Any]],
        failure_stage: str | None,
        delivery_status: str | None,
        delivery_message: str | None,
    ) -> str | None:
        dispatch_context = self._dispatch_context(run)
        explicit_message = self._dispatch_context_value(dispatch_context, "failure_message", "failureMessage")
        if explicit_message is not None:
            return explicit_message

        dispatch_error = _text((run or {}).get("last_dispatch_error") or (run or {}).get("lastDispatchError"))
        if dispatch_error is not None:
            return dispatch_error

        failed_step = self._latest_failed_step(steps)
        if failed_step is not None:
            failed_step_message = _text(failed_step.get("message"))
            if failed_step_message is not None:
                return failed_step_message

        if str(task.get("status") or "").strip().lower() == "completed" and failure_stage == "outbound":
            return delivery_message if delivery_status == "failed" else None
        return None

    def _derive_current_stage(
        self,
        task: dict[str, Any],
        *,
        run: dict[str, Any] | None,
        steps: list[dict[str, Any]],
    ) -> str:
        run_stage = _text((run or {}).get("current_stage") or (run or {}).get("currentStage"))
        if run_stage is not None:
            return run_stage

        active_step = self._latest_active_step(steps)
        if active_step is not None:
            return _text(active_step.get("title")) or "执行中"

        failed_step = self._latest_failed_step(steps)
        if failed_step is not None:
            return _text(failed_step.get("title")) or "执行失败"

        task_status = str(task.get("status") or "").strip().lower()
        if task_status == "completed":
            return "执行完成"
        if task_status == "failed":
            return "执行失败"
        if task_status == "cancelled":
            return "已取消"
        if task_status == "running":
            return "执行中"
        return "等待开始"

    def _build_status_reason(
        self,
        task: dict[str, Any],
        *,
        current_stage: str,
        dispatch_state: str | None,
        failure_stage: str | None,
        failure_message: str | None,
        delivery_status: str | None,
        delivery_message: str | None,
    ) -> str | None:
        task_status = str(task.get("status") or "").strip().lower()
        if task_status == "failed" and failure_stage is not None:
            stage_label = FAILURE_STAGE_LABELS.get(failure_stage, failure_stage)
            if failure_message is not None:
                return f"失败于{stage_label}阶段：{failure_message}"
            return f"失败于{stage_label}阶段"

        if delivery_status == "failed":
            return delivery_message or "结果已生成，但渠道回传失败"
        if delivery_status == "skipped":
            return delivery_message or "结果已生成，但当前未自动回传到外部渠道"

        if task_status in {"pending", "running"}:
            if current_stage:
                return f"当前阶段：{current_stage}"
            dispatch_label = DISPATCH_STATE_LABELS.get(str(dispatch_state or "").strip().lower())
            if dispatch_label is not None:
                return dispatch_label

        if task_status == "completed":
            if delivery_status == "sent":
                return "执行完成，结果已自动回传"
            return "执行完成"
        return None

    def build_task_projection(
        self,
        task: dict[str, Any],
        *,
        run: dict[str, Any] | None = None,
        steps: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload = deepcopy(task)
        route_decision = route_decision_from_payload(payload)
        if route_decision is not None:
            for payload_key, route_keys in (
                ("confirmation_status", ("confirmation_status", "confirmationStatus")),
                ("approval_status", ("approval_status", "approvalStatus")),
                ("approval_required", ("approval_required", "approvalRequired")),
                ("audit_id", ("audit_id", "auditId")),
                ("idempotency_key", ("idempotency_key", "idempotencyKey")),
                ("execution_scope", ("execution_scope", "executionScope")),
                ("schedule_plan", ("schedule_plan", "schedulePlan")),
            ):
                candidate = alias_value(route_decision, *route_keys)
                if candidate is not None:
                    payload.setdefault(payload_key, candidate)

        step_items = steps if isinstance(steps, list) else []
        dispatch_context = self._dispatch_context(run)

        manager_packet = payload.get("manager_packet")
        if not isinstance(manager_packet, dict):
            dispatch_manager_packet = dispatch_context.get("manager_packet") or dispatch_context.get("managerPacket")
            if isinstance(dispatch_manager_packet, dict):
                payload["manager_packet"] = deepcopy(dispatch_manager_packet)

        brain_dispatch_summary = payload.get("brain_dispatch_summary")
        if not isinstance(brain_dispatch_summary, dict):
            dispatch_summary = dispatch_context.get("brain_dispatch_summary") or dispatch_context.get("brainDispatchSummary")
            if isinstance(dispatch_summary, dict):
                payload["brain_dispatch_summary"] = deepcopy(dispatch_summary)

        memory_injection_summary = payload.get("memory_injection_summary")
        if not isinstance(memory_injection_summary, dict):
            dispatch_memory_injection = dispatch_context.get("memory_injection") or dispatch_context.get("memoryInjection")
            if isinstance(dispatch_memory_injection, dict):
                payload["memory_injection_summary"] = deepcopy(dispatch_memory_injection)

        state_machine = payload.get("state_machine")
        if not isinstance(state_machine, dict):
            dispatch_state_machine = dispatch_context.get("state_machine") or dispatch_context.get("stateMachine")
            if isinstance(dispatch_state_machine, dict):
                payload["state_machine"] = deepcopy(dispatch_state_machine)

        dispatch_state = self._dispatch_context_value(dispatch_context, "state", "dispatch_state", "dispatchState")
        delivery_status = self._dispatch_context_value(dispatch_context, "delivery_status", "deliveryStatus")
        delivery_message = self._dispatch_context_value(dispatch_context, "delivery_message", "deliveryMessage")
        failure_stage = self._derive_failure_stage(
            payload,
            run=run,
            steps=step_items,
            delivery_status=delivery_status,
        )
        failure_message = self._derive_failure_message(
            payload,
            run=run,
            steps=step_items,
            failure_stage=failure_stage,
            delivery_status=delivery_status,
            delivery_message=delivery_message,
        )
        current_stage = self._derive_current_stage(payload, run=run, steps=step_items)

        payload["current_stage"] = current_stage
        payload["dispatch_state"] = dispatch_state
        payload["failure_stage"] = failure_stage
        payload["failure_message"] = failure_message
        payload["delivery_status"] = delivery_status
        payload["delivery_message"] = delivery_message
        payload["status_reason"] = self._build_status_reason(
            payload,
            current_stage=current_stage,
            dispatch_state=dispatch_state,
            failure_stage=failure_stage,
            failure_message=failure_message,
            delivery_status=delivery_status,
            delivery_message=delivery_message,
        )
        return payload

    def build_scoped_task_projection(
        self,
        task: dict[str, Any],
        *,
        run: dict[str, Any] | None = None,
        steps: list[dict[str, Any]] | None = None,
        attach_scope_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        scoped_task = attach_scope_fn(task) if callable(attach_scope_fn) else deepcopy(task)
        return self.build_task_projection(scoped_task, run=run, steps=steps)

    def build_task_list_response(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        return {"items": items, "total": len(items)}

    def summarize(self, task: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": task.get("id"),
            "title": task.get("title"),
            "status": task.get("status"),
            "current_stage": task.get("current_stage") or task.get("dispatch_state"),
            "status_reason": task.get("status_reason"),
            "updated_at": task.get("updated_at"),
        }

    def build_manager_summary(self, manager_packet: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(manager_packet, dict) or not manager_packet:
            return None

        summary = {
            "manager_role": _text(manager_packet.get("manager_role")),
            "manager_action": _text(manager_packet.get("manager_action")),
            "next_owner": _text(manager_packet.get("next_owner")),
            "delivery_mode": _text(manager_packet.get("delivery_mode")),
            "task_shape": _text(manager_packet.get("task_shape")),
            "response_contract": _text(manager_packet.get("response_contract")),
            "clarify_required": bool(manager_packet.get("clarify_required"))
            if manager_packet.get("clarify_required") is not None
            else None,
            "clarify_question": _text(manager_packet.get("clarify_question")),
            "handoff_summary": _text(manager_packet.get("handoff_summary")),
            "session_state": _text(manager_packet.get("session_state")),
            "state_label": _text(manager_packet.get("state_label")),
        }
        if any(value is not None for value in summary.values()):
            return summary
        return None

    def build_session_execution_plan(
        self,
        task: dict[str, Any],
        *,
        run: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        task_plan = task.get("execution_plan")
        if isinstance(task_plan, dict) and task_plan:
            plan = deepcopy(task_plan)
        else:
            plan = None

        dispatch_context = self._dispatch_context(run)
        if plan is None and isinstance(dispatch_context, dict):
            snapshot = dispatch_context.get("execution_plan_snapshot")
            if isinstance(snapshot, dict) and snapshot:
                plan = deepcopy(snapshot)

        if plan is None:
            route_decision = route_decision_from_task(task)
            manager_packet = task.get("manager_packet") or task.get("managerPacket")
            if isinstance(dispatch_context, dict):
                if route_decision is None:
                    route_decision = route_decision_from_payload(dispatch_context)
                if not isinstance(manager_packet, dict):
                    manager_packet = dispatch_context.get("manager_packet") or dispatch_context.get("managerPacket")
            if route_decision is not None:
                plan = build_execution_plan_snapshot(
                    route_decision=route_decision,
                    manager_packet=manager_packet if isinstance(manager_packet, dict) else None,
                )

        if not isinstance(plan, dict) or not plan:
            return None

        if not isinstance(dispatch_context, dict):
            return plan

        aggregation_contract = dispatch_context.get("aggregation_contract") or dispatch_context.get("aggregationContract")
        aggregation_notes = dispatch_context.get("aggregation_notes") or dispatch_context.get("aggregationNotes")
        state_machine = dispatch_context.get("state_machine") or dispatch_context.get("stateMachine")

        if not isinstance(aggregation_contract, dict) and isinstance(state_machine, dict):
            aggregation_contract = {
                "mode": state_machine.get("coordination_mode"),
                "successful_agents": state_machine.get("successful_agents"),
                "failed_agents": state_machine.get("failed_agents"),
                "cancelled_agents": state_machine.get("cancelled_agents"),
                "branch_results": state_machine.get("branch_results"),
            }
        if not isinstance(aggregation_notes, dict) and isinstance(state_machine, dict):
            aggregation_notes = {
                "selected_branch_id": state_machine.get("selected_branch_id"),
                "selected_agent": state_machine.get("selected_agent"),
            }

        if isinstance(aggregation_contract, dict):
            if aggregation_contract.get("mode"):
                plan["coordination_mode"] = str(aggregation_contract.get("mode"))
            plan["successful_agents"] = int(aggregation_contract.get("successful_agents") or 0)
            plan["failed_agents"] = int(aggregation_contract.get("failed_agents") or 0)
            plan["cancelled_agents"] = int(aggregation_contract.get("cancelled_agents") or 0)
            branch_results = aggregation_contract.get("branch_results")
            if isinstance(branch_results, list):
                plan["branch_results"] = deepcopy(branch_results)

        if isinstance(aggregation_notes, dict):
            plan["selected_branch_id"] = (
                str(aggregation_notes.get("selected_branch_id") or "").strip() or None
            )
            plan["selected_agent"] = (
                str(aggregation_notes.get("selected_agent") or "").strip() or None
            )
        return plan

    def build_session_fallback_history(
        self,
        task: dict[str, Any],
        *,
        run: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        task_history = task.get("fallback_history") or task.get("fallbackHistory")
        if isinstance(task_history, list):
            return deepcopy(task_history)

        dispatch_context = self._dispatch_context(run)
        history = dispatch_context.get("fallback_history") or dispatch_context.get("fallbackHistory")
        if isinstance(history, list):
            return deepcopy(history)
        return []

    def build_ingest_response(
        self,
        *,
        result_message: str,
        entrypoint: str,
        unified_message: dict[str, Any],
        ok: bool = True,
        task_id: str | None = None,
        run_id: str | None = None,
        intent: str | None = None,
        trace_id: str | None = None,
        detected_lang: str | None = None,
        memory_hits: int = 0,
        warnings: list[str] | None = None,
        merged_into_task_id: str | None = None,
        interaction_mode: str | None = None,
        reception_mode: str | None = None,
        route_decision: dict[str, Any] | None = None,
        manager_packet: dict[str, Any] | None = None,
        brain_dispatch_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "ok": ok,
            "message": result_message,
            "entrypoint": entrypoint,
            "task_id": task_id,
            "run_id": run_id,
            "intent": intent,
            "unified_message": deepcopy(unified_message),
            "trace_id": trace_id,
            "detected_lang": detected_lang,
            "memory_hits": memory_hits,
            "warnings": list(warnings or []),
            "merged_into_task_id": merged_into_task_id,
            "interaction_mode": interaction_mode,
            "reception_mode": reception_mode,
            "route_decision": deepcopy(route_decision) if isinstance(route_decision, dict) else None,
            "manager_summary": self.build_manager_summary(manager_packet),
            "brain_dispatch_summary": (
                deepcopy(brain_dispatch_summary)
                if isinstance(brain_dispatch_summary, dict)
                else None
            ),
        }

    def build_task_event_response(
        self,
        *,
        result_message: str,
        entrypoint: str,
        task: dict[str, Any],
        unified_message: dict[str, Any],
        ok: bool = True,
        run_id: str | None = None,
        intent: str | None = None,
        trace_id: str | None = None,
        detected_lang: str | None = None,
        memory_hits: int = 0,
        warnings: list[str] | None = None,
        merged_into_task_id: str | None = None,
        interaction_mode: str | None = None,
        reception_mode: str | None = None,
        include_task_route_decision: bool = True,
    ) -> dict[str, Any]:
        route_decision = None
        if include_task_route_decision:
            route_decision = route_decision_from_task(task)
        if interaction_mode is None and isinstance(route_decision, dict):
            interaction_mode = _text(route_decision.get("interaction_mode") or route_decision.get("interactionMode"))
        if reception_mode is None and isinstance(route_decision, dict):
            reception_mode = _text(route_decision.get("reception_mode") or route_decision.get("receptionMode"))
        resolved_run_id = _text(run_id) or _text(task.get("workflow_run_id") or task.get("workflowRunId"))
        resolved_task_id = _text(task.get("id"))
        return self.build_ingest_response(
            result_message=result_message,
            entrypoint=entrypoint,
            unified_message=unified_message,
            ok=ok,
            task_id=resolved_task_id,
            run_id=resolved_run_id,
            intent=intent,
            trace_id=trace_id,
            detected_lang=detected_lang,
            memory_hits=memory_hits,
            warnings=warnings,
            merged_into_task_id=merged_into_task_id,
            interaction_mode=interaction_mode,
            reception_mode=reception_mode,
            route_decision=route_decision,
            manager_packet=task.get("manager_packet") if isinstance(task.get("manager_packet"), dict) else None,
            brain_dispatch_summary=(
                task.get("brain_dispatch_summary")
                if isinstance(task.get("brain_dispatch_summary"), dict)
                else None
            ),
        )

    def build_context_patch_response(
        self,
        *,
        result_message: str,
        entrypoint: str,
        task: dict[str, Any] | None,
        task_id: str,
        unified_message: dict[str, Any],
        intent: str | None = None,
        trace_id: str | None = None,
        detected_lang: str | None = None,
        memory_hits: int = 0,
        warnings: list[str] | None = None,
        interaction_mode: str | None = "chat",
        reception_mode: str | None = "continuation",
    ) -> dict[str, Any]:
        if isinstance(task, dict):
            return self.build_task_event_response(
                result_message=result_message,
                entrypoint=entrypoint,
                task=task,
                run_id=_text(task.get("workflow_run_id") or task.get("workflowRunId")),
                intent=intent,
                unified_message=unified_message,
                trace_id=trace_id,
                detected_lang=detected_lang,
                memory_hits=memory_hits,
                warnings=warnings,
                merged_into_task_id=task_id,
                interaction_mode=interaction_mode,
                reception_mode=reception_mode,
                include_task_route_decision=False,
            )
        return self.build_ingest_response(
            result_message=result_message,
            entrypoint=entrypoint,
            task_id=task_id,
            intent=intent,
            unified_message=unified_message,
            trace_id=trace_id,
            detected_lang=detected_lang,
            memory_hits=memory_hits,
            warnings=warnings,
            merged_into_task_id=task_id,
            interaction_mode=interaction_mode,
            reception_mode=reception_mode,
        )


task_view_service = TaskViewService()
