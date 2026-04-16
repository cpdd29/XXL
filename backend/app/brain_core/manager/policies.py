from __future__ import annotations


def truncate_manager_text(value: object, limit: int) -> str:
    normalized = " ".join(str(value or "").strip().split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: max(limit - 3, 1)].rstrip()}..."


def build_clarify_question(*, language: str, intent: str) -> str:
    if language == "en":
        if intent == "write":
            return "What do you want me to write, and who is it for?"
        if intent == "search":
            return "What exact information do you want me to check first?"
        return "What is the main goal you want me to help you move forward right now?"
    if intent == "write":
        return "你想让我写什么，给谁用，先告诉我这两个点就行。"
    if intent == "search":
        return "你先告诉我最想查清楚的那一个问题，我先从那里开始。"
    return "你先告诉我这次最想推进的目标是什么，我先按那个来接。"


def clarify_required_for_reception_mode(reception_mode: str | None) -> bool:
    return reception_mode == "clarify"


def build_response_contract(*, interaction_mode: str, reception_mode: str | None) -> str:
    if reception_mode == "clarify":
        return "clarify_first"
    if interaction_mode == "chat":
        return "reception_chat"
    if reception_mode == "continuation":
        return "continue_existing_thread"
    if reception_mode == "task_handoff":
        return "task_handoff"
    return "direct_tasking"


def build_handoff_summary(
    *,
    intent: str,
    interaction_mode: str,
    reception_mode: str | None,
    workflow_mode: str | None,
    execution_agent_name: str,
    route_message: str,
) -> str:
    mode_label = workflow_mode or interaction_mode or "unknown"
    reception_label = reception_mode or "auto"
    route_excerpt = truncate_manager_text(route_message, 72)
    return (
        f"intent={intent}; mode={mode_label}; reception={reception_label}; "
        f"execution_agent={execution_agent_name}; route={route_excerpt}"
    )


def build_manager_action(
    *,
    interaction_mode: str,
    reception_mode: str | None,
    workflow_mode: str | None,
) -> str:
    if reception_mode == "clarify":
        return "clarify_request"
    if interaction_mode == "chat":
        return "reception_reply"
    if workflow_mode == "professional_workflow":
        return "admit_professional_workflow"
    if reception_mode == "continuation":
        return "continue_active_task"
    if reception_mode == "task_handoff":
        return "handoff_to_execution"
    return "direct_task_entry"


def build_next_owner(
    *,
    manager_action: str,
    execution_agent_name: str,
) -> str:
    if manager_action in {"clarify_request", "reception_reply"}:
        return "项目经理 Agent"
    if manager_action == "admit_professional_workflow":
        return "Workflow Router"
    return execution_agent_name or "Execution Agent"


def build_workflow_admission(
    *,
    workflow_mode: str | None,
    approval_required: bool,
    requires_permission: bool,
) -> str:
    if workflow_mode == "professional_workflow":
        if approval_required:
            return "professional_workflow_with_approval"
        if requires_permission:
            return "professional_workflow_guarded"
        return "professional_workflow_open"
    if workflow_mode == "free_workflow":
        return "free_workflow"
    if workflow_mode == "chat":
        return "chat"
    return "undecided"


def build_task_shape(
    *,
    interaction_mode: str,
    workflow_mode: str | None,
    execution_plan: dict[str, object] | None,
) -> str:
    if interaction_mode == "chat":
        return "chat"
    if workflow_mode == "professional_workflow":
        return "professional_case"
    if isinstance(execution_plan, dict) and int(execution_plan.get("planned_agent_count") or 0) > 1:
        return "multi_step"
    return "single_step"


def build_decomposition_hint(
    *,
    manager_action: str,
    task_shape: str,
) -> str:
    if manager_action == "clarify_request":
        return "clarify_before_execution"
    if manager_action == "reception_reply":
        return "reply_in_reception_mode"
    if manager_action == "continue_active_task":
        return "append_context_and_continue"
    if manager_action == "admit_professional_workflow":
        return "handoff_to_professional_workflow"
    if task_shape == "multi_step":
        return "research_then_synthesize"
    return "direct_execute"


def build_delivery_mode(
    *,
    interaction_mode: str,
    workflow_mode: str | None,
    approval_required: bool,
) -> str:
    if interaction_mode == "chat":
        return "conversational"
    if approval_required:
        return "approval_flow"
    if workflow_mode == "professional_workflow":
        return "workflow_execution"
    return "structured_result"


def build_manager_session_state(
    *,
    manager_action: str,
    clarify_required: bool,
    approval_required: bool,
    confirmation_status: str | None,
) -> str:
    normalized_confirmation = str(confirmation_status or "").strip().lower()
    if manager_action == "clarify_request" or clarify_required:
        return "awaiting_clarification"
    if approval_required and normalized_confirmation in {"", "pending"}:
        return "awaiting_confirmation"
    if normalized_confirmation == "confirm":
        return "ready_for_execution"
    if normalized_confirmation == "cancel":
        return "cancelled_by_user"
    if manager_action == "continue_active_task":
        return "continuing_active_task"
    if manager_action == "reception_reply":
        return "reception_reply"
    return "executing"


def build_manager_state_label(session_state: str) -> str:
    mapping = {
        "awaiting_clarification": "待澄清",
        "awaiting_confirmation": "待确认",
        "ready_for_execution": "待执行",
        "continuing_active_task": "继续处理中",
        "reception_reply": "接待回复",
        "cancelled_by_user": "已取消",
        "executing": "执行中",
    }
    return mapping.get(session_state, "处理中")
