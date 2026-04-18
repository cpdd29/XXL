from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
from threading import Lock
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status

from app.core.brain_payload_fields import (
    alias_bool,
    alias_text,
    dispatch_context_from_run,
    route_decision_from_payload,
    route_decision_from_task,
)
from app.core.nats_event_bus import nats_event_bus
from app.config import get_settings
from app.services.agent_execution_service import agent_execution_service
from app.services.external_agent_registry_service import external_agent_registry_service
from app.services.tenancy_service import attach_scope, matches_scope
from app.services.agent_service import is_agent_routable, routing_priority
from app.services.channel_outbound_service import channel_outbound_service
from app.services.document_search_service import document_search_service
from app.services.language_service import detect_language
from app.services.memory_service import memory_service
from app.services.mcp_runtime_service import mcp_runtime_service
from app.services.persistence_service import persistence_service
from app.services.trace_exporter_service import trace_exporter_service
from app.services.workflow_scheduler_service import workflow_scheduler_service
from app.services.workflow_realtime_service import workflow_realtime_service
from app.services.store import store

LABEL_AGENT_TYPE_MAP = {
    "安全检测": "security",
    "意图识别": "intent",
    "对话 Agent": "conversation",
    "需求分析任务分发 Agent": "task_dispatcher",
    "搜索 Agent": "search",
    "写作 Agent": "write",
    "发送结果": "output",
}
KNOWN_AGENT_TYPES = {"security", "intent", "conversation", "task_dispatcher", "search", "write", "output"}
INTENT_AGENT_TYPE_MAP = {
    "search": "search",
    "write": "write",
    "help": "write",
    "manual": None,
}
RESULT_KIND_INTENT_MAP = {
    "search_report": "search",
    "draft_message": "write",
    "help_note": "help",
}
SEARCH_INTENT_HINTS = (
    "search",
    "find",
    "lookup",
    "查询",
    "查",
    "搜索",
    "检索",
    "文档",
    "知识库",
    "规格",
)
WRITE_INTENT_HINTS = (
    "write",
    "draft",
    "reply",
    "email",
    "announcement",
    "写",
    "生成",
    "总结",
    "草稿",
    "回复",
    "邮件",
    "公告",
)
STEP_HINTS_BY_AGENT_TYPE = {
    "security": ("安全", "网关"),
    "intent": ("意图", "路由", "Master Bot"),
    "conversation": ("对话", "澄清", "handoff"),
    "task_dispatcher": ("分发", "路由", "执行意图"),
    "search": ("搜索", "检索", "知识库"),
    "write": ("写作", "回复", "生成"),
    "output": ("发送结果", "输出", "回传"),
}
ACTIVE_NODE_STATUSES = {"completed", "running", "waiting", "error"}
TERMINAL_TASK_STATUSES = {"completed", "failed", "cancelled"}
def _task_confirmation_pending(task: dict | None) -> bool:
    if not isinstance(task, dict):
        return False
    route_decision = route_decision_from_task(task)
    if route_decision is None:
        return False
    workflow_mode = str(alias_text(route_decision, "workflow_mode", "workflowMode") or "").lower()
    confirmation_required = alias_bool(route_decision, "confirmation_required", "confirmationRequired")
    confirmation_status = str(
        alias_text(route_decision, "confirmation_status", "confirmationStatus") or ""
    ).lower()
    return (
        workflow_mode == "professional_workflow"
        and bool(confirmation_required)
        and confirmation_status == "pending"
        and str(task.get("status") or "").strip().lower() == "pending"
    )


def _refresh_confirmation_pending_run_locked(*, run: dict, task: dict) -> dict:
    dispatch_context = _run_dispatch_context(run)
    if isinstance(dispatch_context, dict):
        dispatch_context["state"] = "awaiting_confirmation"
        dispatch_context["updated_at"] = store.now_string()
    refreshed_run = _refresh_run_state(run, task)
    _publish_run_event(refreshed_run, "workflow_run.updated")
    _persist_execution_state(
        task=task,
        steps=_ensure_task_steps_loaded(task["id"]),
        run=refreshed_run,
    )
    _cancel_scheduled_run(refreshed_run["id"])
    return refreshed_run


MANUAL_AUTO_START_DELAY_SECONDS = 0.6
AUTO_STEP_DELAY_SECONDS = 0.6
TASK_RETRY_FOLLOW_UP_DELAY_SECONDS = 5.0
CONTEXT_PATCH_PREVIEW_LIMIT = 160
DEFAULT_WORKFLOW_MAX_DISPATCH_RETRY = 6
DEFAULT_WORKFLOW_DISPATCH_RETRY_BACKOFF_SECONDS = 2.0
DEFAULT_WORKFLOW_EXECUTION_TIMEOUT_SECONDS = 45.0
AGENT_DISPATCH_WORKFLOW_ID = "__agent_dispatch__"
AGENT_DISPATCH_WORKFLOW_NAME = "Direct Agent Fallback"
LEGACY_AGENT_DISPATCH_WORKFLOW_ID = "__direct_agent_fallback__"
AGENT_DISPATCH_WORKFLOW_IDS = {AGENT_DISPATCH_WORKFLOW_ID, LEGACY_AGENT_DISPATCH_WORKFLOW_ID}
DIRECT_AGENT_FALLBACK_WORKFLOW_ID = LEGACY_AGENT_DISPATCH_WORKFLOW_ID
DIRECT_AGENT_FALLBACK_WORKFLOW_NAME = AGENT_DISPATCH_WORKFLOW_NAME
LEGACY_DIRECT_AGENT_DISPATCH_TYPE = "direct_agent_dispatch"
LEGACY_DIRECT_AGENT_FALLBACK_MODE = "direct_agent_fallback"
AGENT_DISPATCH_RUN_TYPES = {"agent_dispatch", LEGACY_DIRECT_AGENT_DISPATCH_TYPE}
AGENT_DISPATCH_FALLBACK_POLICY_MODES = {"agent_dispatch_fallback", LEGACY_DIRECT_AGENT_FALLBACK_MODE}
AUTO_RECOVERY_FALLBACK_MODES = {"planner_recovery", *AGENT_DISPATCH_FALLBACK_POLICY_MODES}
_TICK_LOCK = Lock()
logger = logging.getLogger(__name__)
AUTHORITATIVE_TASK_STEP_CACHE: set[str] = set()


def mark_task_steps_authoritative(task_id: str) -> None:
    AUTHORITATIVE_TASK_STEP_CACHE.add(task_id)


def _publish_run_event(run: dict, event_type: str) -> None:
    workflow_realtime_service.publish_run_event(run, event_type)


def _schedule_manual_auto_progress(run_id: str) -> None:
    step_delay = _workflow_step_delay_for_run(run_id)
    workflow_scheduler_service.schedule(
        run_id,
        delay=step_delay,
        step_delay=step_delay,
    )


def _schedule_message_auto_progress(run_id: str) -> None:
    step_delay = _workflow_step_delay_for_run(run_id)
    configured_delay = float(get_settings().message_debounce_seconds)
    delay = configured_delay
    if (
        not getattr(persistence_service, "enabled", False)
        and not bool(getattr(nats_event_bus, "is_connected", lambda: False)())
    ):
        delay = min(configured_delay, step_delay)
    workflow_scheduler_service.schedule(
        run_id,
        delay=delay,
        step_delay=step_delay,
    )


def _schedule_follow_up(run_id: str) -> None:
    step_delay = _workflow_step_delay_for_run(run_id)
    workflow_scheduler_service.schedule(
        run_id,
        delay=step_delay,
        step_delay=step_delay,
    )


def _schedule_retry_follow_up(run_id: str) -> None:
    step_delay = _workflow_step_delay_for_run(run_id)
    workflow_scheduler_service.schedule(
        run_id,
        delay=TASK_RETRY_FOLLOW_UP_DELAY_SECONDS,
        step_delay=step_delay,
    )


def schedule_retry_follow_up(run_id: str) -> None:
    _schedule_retry_follow_up(run_id)


def _cancel_scheduled_run(run_id: str) -> None:
    workflow_scheduler_service.cancel(run_id)


def _persist_runtime_state() -> None:
    persistence_service.persist_runtime_state()


def _persist_execution_state(
    *,
    task: dict | None = None,
    steps: list[dict] | None = None,
    run: dict | None = None,
) -> None:
    persist_execution_state = getattr(persistence_service, "persist_execution_state", None)
    if callable(persist_execution_state):
        if persist_execution_state(task=task, task_steps=steps, workflow_run=run):
            return
        if getattr(persistence_service, "enabled", False):
            return
    _persist_runtime_state()


def _persist_agent_state(agent: dict | None) -> None:
    if agent is None:
        return

    persist_agent_state = getattr(persistence_service, "persist_agent_state", None)
    if callable(persist_agent_state):
        if persist_agent_state(agent=agent):
            return
        if getattr(persistence_service, "enabled", False):
            return
    _persist_runtime_state()


def _find_cached_workflow(workflow_id: str) -> dict | None:
    for workflow in store.workflows:
        if workflow["id"] == workflow_id:
            return workflow
    return None


def _sync_cached_workflow(workflow_payload: dict) -> dict:
    workflow_id = str(workflow_payload.get("id") or "").strip()
    cached_workflow = _find_cached_workflow(workflow_id)
    payload = store.clone(workflow_payload)
    if cached_workflow is None:
        store.workflows.append(payload)
        return payload

    cached_workflow.clear()
    cached_workflow.update(payload)
    return cached_workflow


def _load_database_workflow(workflow_id: str) -> tuple[dict | None, bool]:
    if not getattr(persistence_service, "enabled", False):
        return None, False

    database_workflow = persistence_service.get_workflow(workflow_id)
    if database_workflow is not None:
        return database_workflow, True

    database_workflows = persistence_service.list_workflows()
    if database_workflows is None:
        return None, True

    for candidate in database_workflows:
        if str(candidate.get("id") or "").strip() == workflow_id:
            return candidate, True
    return None, True


def _find_workflow(workflow_id: str) -> dict:
    database_workflow, database_authoritative = _load_database_workflow(workflow_id)
    if database_authoritative:
        if database_workflow is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
        return _sync_cached_workflow(database_workflow)

    cached_workflow = _find_cached_workflow(workflow_id)
    if cached_workflow is not None:
        return cached_workflow

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")


def _find_cached_run(run_id: str) -> dict | None:
    for run in store.workflow_runs:
        if run["id"] == run_id:
            return run
    return None


def _sync_cached_run(run_payload: dict) -> dict:
    run_id = str(run_payload.get("id") or "").strip()
    cached_run = _find_cached_run(run_id)
    payload = store.clone(run_payload)
    if cached_run is None:
        store.workflow_runs.insert(0, payload)
        return payload

    cached_run.clear()
    cached_run.update(payload)
    return cached_run


def _load_database_run(run_id: str) -> tuple[dict | None, bool]:
    if not getattr(persistence_service, "enabled", False):
        return None, False

    database_run = persistence_service.get_workflow_run(run_id)
    if database_run is not None:
        return database_run, True

    database_runs = persistence_service.list_workflow_runs()
    if database_runs is None:
        return None, True

    for candidate in database_runs:
        if str(candidate.get("id") or "").strip() == run_id:
            return candidate, True
    return None, True


def _find_run(run_id: str) -> dict:
    database_run, database_authoritative = _load_database_run(run_id)
    if database_authoritative:
        if database_run is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow run not found")
        return _sync_cached_run(database_run)

    cached_run = _find_cached_run(run_id)
    if cached_run is not None:
        return cached_run

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow run not found")


def _find_cached_task(task_id: str) -> dict | None:
    for task in store.tasks:
        if task["id"] == task_id:
            return task
    return None


def _sync_cached_task(task_payload: dict) -> dict:
    task_id = str(task_payload.get("id") or "").strip()
    cached_task = _find_cached_task(task_id)
    payload = store.clone(task_payload)
    if cached_task is None:
        store.tasks.append(payload)
        return payload

    cached_task.clear()
    cached_task.update(payload)
    return cached_task


def _load_database_task(task_id: str) -> tuple[dict | None, bool]:
    if not getattr(persistence_service, "enabled", False):
        return None, False

    database_task = persistence_service.get_task(task_id)
    if database_task is not None:
        return database_task, True

    database_tasks = persistence_service.list_tasks()
    if database_tasks is None:
        return None, True

    for candidate in database_tasks:
        if str(candidate.get("id") or "").strip() == task_id:
            return candidate, True
    return None, True


def _find_task(task_id: str | None) -> dict | None:
    if not task_id:
        return None

    database_task, database_authoritative = _load_database_task(task_id)
    if database_authoritative:
        if database_task is None:
            return None
        return _sync_cached_task(database_task)

    return _find_cached_task(task_id)


def _refresh_task_steps_from_database(task_id: str) -> list[dict] | None:
    database_steps = persistence_service.get_task_steps(task_id)
    if database_steps is None and getattr(persistence_service, "enabled", False):
        store.task_steps[task_id] = []
        mark_task_steps_authoritative(task_id)
        return store.task_steps[task_id]
    if database_steps is None:
        return None
    store.task_steps[task_id] = store.clone(database_steps)
    mark_task_steps_authoritative(task_id)
    return store.task_steps[task_id]


def _ensure_task_steps_loaded(task_id: str) -> list[dict]:
    if task_id in store.task_steps and (
        not getattr(persistence_service, "enabled", False) or task_id in AUTHORITATIVE_TASK_STEP_CACHE
    ):
        return store.task_steps[task_id]

    if getattr(persistence_service, "enabled", False):
        database_steps = persistence_service.get_task_steps(task_id)
        if database_steps is not None:
            store.task_steps[task_id] = store.clone(database_steps)
            mark_task_steps_authoritative(task_id)
            return store.task_steps[task_id]
        store.task_steps[task_id] = []
        mark_task_steps_authoritative(task_id)
        return store.task_steps[task_id]

    database_steps = persistence_service.get_task_steps(task_id)
    if database_steps is not None:
        store.task_steps[task_id] = store.clone(database_steps)
        return store.task_steps[task_id]

    return store.task_steps.setdefault(task_id, [])


def _load_workflows_for_selection() -> list[dict]:
    database_workflows = persistence_service.list_workflows()
    if database_workflows is not None:
        store.workflows = [store.clone(workflow) for workflow in database_workflows]
        return store.workflows

    if getattr(persistence_service, "enabled", False):
        return []

    if store.workflows:
        return store.workflows
    return store.workflows


def _load_agents_for_execution() -> list[dict]:
    database_agents = persistence_service.list_agents()
    if database_agents is not None:
        base_agents = [store.clone(agent) for agent in database_agents]
    elif getattr(persistence_service, "enabled", False):
        base_agents = []
    else:
        base_agents = [store.clone(agent) for agent in store.agents]

    merged: dict[str, dict] = {
        str(agent.get("id") or "").strip(): agent
        for agent in base_agents
        if str(agent.get("id") or "").strip()
    }
    for external_agent in external_agent_registry_service.list_agents(include_offline=True):
        agent_id = str(external_agent.get("id") or "").strip()
        if not agent_id or agent_id in merged:
            continue
        merged[agent_id] = store.clone(external_agent)

    store.agents = [store.clone(agent) for agent in merged.values()]
    return store.agents


def _load_database_agent(agent_id: str) -> tuple[dict | None, bool]:
    if not getattr(persistence_service, "enabled", False):
        return None, False

    database_agent = persistence_service.get_agent(agent_id)
    if database_agent is not None:
        return database_agent, True

    database_agents = persistence_service.list_agents()
    if database_agents is None:
        return None, True

    for candidate in database_agents:
        if str(candidate.get("id") or "").strip() == agent_id:
            return candidate, True
    return None, True


def _find_agent_mutable(agent_id: str) -> dict | None:
    normalized_agent_id = str(agent_id or "").strip()
    if not normalized_agent_id:
        return None

    database_agent, database_authoritative = _load_database_agent(normalized_agent_id)
    if database_authoritative:
        if database_agent is None:
            return None
        payload = store.clone(database_agent)
        for agent in store.agents:
            if str(agent.get("id") or "") != normalized_agent_id:
                continue
            agent.clear()
            agent.update(payload)
            return agent

        store.agents.append(payload)
        return payload

    for agent in store.agents:
        if str(agent.get("id") or "") == normalized_agent_id:
            return agent

    external_agent = external_agent_registry_service.get_agent(normalized_agent_id)
    if external_agent is not None:
        payload = store.clone(external_agent)
        store.agents.append(payload)
        return payload

    return None


def _next_task_id() -> str:
    numeric_ids = [int(task["id"]) for task in store.tasks if str(task.get("id", "")).isdigit()]
    database_tasks = persistence_service.list_tasks()
    if database_tasks is not None:
        numeric_ids.extend(
            int(task["id"])
            for task in database_tasks
            if str(task.get("id", "")).isdigit()
        )
    return str(max(numeric_ids, default=0) + 1)


def _time_only(value: str | None) -> str:
    if not value:
        return "--:--:--"
    if "T" in value:
        return value.split("T", maxsplit=1)[1][:8]
    if " " in value:
        return value.rsplit(" ", maxsplit=1)[-1][:8]
    return value[:8]


def _trigger_haystack(trigger: object) -> str:
    if isinstance(trigger, str):
        return trigger.lower()
    if isinstance(trigger, dict):
        return " ".join(
            str(trigger.get(field) or "")
            for field in (
                "type",
                "keyword",
                "description",
                "cron",
                "webhook_path",
                "internal_event",
                "internalEvent",
            )
        ).lower()
    return ""


def _resolve_agent_type(agent_binding: str | None) -> str | None:
    if not agent_binding:
        return None

    agent = _find_agent_mutable(str(agent_binding))
    if agent is not None:
        return str(agent.get("type") or agent_binding)
    return str(agent_binding)


def _normalize_node_binding(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _derive_agent_binding(node: dict) -> str | None:
    agent_binding = _normalize_node_binding(node.get("agent_id") or node.get("agentId"))
    if agent_binding is not None:
        return agent_binding

    fallback_type = LABEL_AGENT_TYPE_MAP.get(node.get("label"))
    return fallback_type


def _derive_agent_type(node: dict) -> str | None:
    return _resolve_agent_type(_derive_agent_binding(node)) or LABEL_AGENT_TYPE_MAP.get(node.get("label"))


def _derive_tool_binding(node: dict) -> str | None:
    return _normalize_node_binding(node.get("tool_id") or node.get("toolId"))


def _derive_workflow_binding(node: dict) -> str | None:
    return _normalize_node_binding(node.get("workflow_id") or node.get("workflowId"))


def _execution_node_label(node: dict, *, fallback: str) -> str:
    return str(node.get("label") or "").strip() or fallback


def _node_config(node: dict | None) -> dict[str, Any]:
    config = (node or {}).get("config")
    return store.clone(config) if isinstance(config, dict) else {}


def _node_config_text(node: dict | None, *keys: str) -> str | None:
    config = _node_config(node)
    for key in keys:
        value = config.get(key)
        if value in {None, ""}:
            continue
        normalized = str(value).strip()
        if normalized:
            return normalized
    return None


def _append_description_text(base_text: str | None, *extra_lines: str | None) -> str | None:
    parts = [str(base_text or "").strip()]
    parts.extend(str(line or "").strip() for line in extra_lines)
    normalized = [part for part in parts if part]
    return "\n".join(normalized) if normalized else None


def _workflow_node_template_context(*, task: dict, run: dict, node: dict) -> dict[str, str]:
    request_text = _primary_request_text(task)
    return {
        "input": request_text,
        "query": request_text,
        "text": request_text,
        "task_id": str(task.get("id") or "").strip(),
        "task_title": str(task.get("title") or "").strip(),
        "task_description": str(task.get("description") or "").strip(),
        "workflow_run_id": str(run.get("id") or "").strip(),
        "workflow_id": str(run.get("workflow_id") or "").strip(),
        "workflow_name": str(run.get("workflow_name") or "").strip(),
        "node_id": str(node.get("id") or "").strip(),
        "node_label": _execution_node_label(node, fallback="工作流节点"),
        "node_description": str(node.get("description") or "").strip(),
        "intent": str(run.get("intent") or "").strip(),
        "trigger": str(run.get("trigger") or "").strip(),
    }


def _render_node_template(template: str, *, context: dict[str, str]) -> object:
    rendered = str(template)
    for key, value in context.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    stripped = rendered.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            return json.loads(rendered)
        except json.JSONDecodeError:
            return rendered
    return rendered


def _build_tool_payload(*, task: dict, run: dict, node: dict) -> dict[str, object]:
    request_text = _primary_request_text(task)
    base_payload: dict[str, object] = {
        "query": request_text,
        "text": request_text,
        "task_id": str(task.get("id") or ""),
        "workflow_run_id": str(run.get("id") or ""),
        "workflow_id": str(run.get("workflow_id") or ""),
        "node_id": str(node.get("id") or ""),
        "node_label": _execution_node_label(node, fallback="工具节点"),
    }
    payload_template = _node_config_text(node, "payloadTemplate", "payload_template")
    if not payload_template:
        return base_payload

    rendered_template = _render_node_template(
        payload_template,
        context=_workflow_node_template_context(task=task, run=run, node=node),
    )
    if isinstance(rendered_template, dict):
        return {**base_payload, **rendered_template}
    if isinstance(rendered_template, list):
        return {**base_payload, "items": rendered_template}

    rendered_text = str(rendered_template or "").strip()
    if not rendered_text:
        return base_payload
    return {
        **base_payload,
        "query": rendered_text,
        "text": rendered_text,
        "payload_template": payload_template,
    }


def _message_trigger_keywords(workflow: dict) -> list[str]:
    trigger = workflow.get("trigger")
    raw_keywords = ""

    if isinstance(trigger, str):
        trigger_type, _, pattern = trigger.partition(".")
        if trigger_type and trigger_type != "message":
            return []
        raw_keywords = pattern
    elif isinstance(trigger, dict):
        trigger_type = str(trigger.get("type") or "message").strip().lower()
        if trigger_type not in {"", "message"}:
            return []
        raw_keywords = str(trigger.get("keyword") or "")
    else:
        return []

    return [
        keyword.strip().lower()
        for keyword in raw_keywords.replace("，", ",").split(",")
        if keyword.strip()
    ]


def _normalize_language(value: str | None) -> str | None:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    return normalized.replace("_", "-").split("-", maxsplit=1)[0]


def _normalize_positive_int(value: object, *, default: int) -> int:
    if value in {None, ""}:
        return default
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return default
    return normalized if normalized > 0 else default


def _normalize_positive_float(value: object, *, default: float) -> float:
    if value in {None, ""}:
        return default
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        return default
    return normalized if normalized > 0 else default


def _workflow_trigger_config(workflow: dict | None) -> dict:
    trigger = (workflow or {}).get("trigger")
    return trigger if isinstance(trigger, dict) else {}


def _workflow_policy_from_workflow(workflow: dict | None) -> dict:
    trigger = _workflow_trigger_config(workflow)
    return {
        "step_delay_seconds": _normalize_positive_float(
            trigger.get("step_delay_seconds") or trigger.get("stepDelaySeconds"),
            default=AUTO_STEP_DELAY_SECONDS,
        ),
        "max_dispatch_retry": _normalize_positive_int(
            trigger.get("max_dispatch_retry") or trigger.get("maxDispatchRetry"),
            default=DEFAULT_WORKFLOW_MAX_DISPATCH_RETRY,
        ),
        "dispatch_retry_backoff_seconds": _normalize_positive_float(
            trigger.get("dispatch_retry_backoff_seconds")
            or trigger.get("dispatchRetryBackoffSeconds"),
            default=DEFAULT_WORKFLOW_DISPATCH_RETRY_BACKOFF_SECONDS,
        ),
        "execution_timeout_seconds": _normalize_positive_float(
            trigger.get("execution_timeout_seconds") or trigger.get("executionTimeoutSeconds"),
            default=DEFAULT_WORKFLOW_EXECUTION_TIMEOUT_SECONDS,
        ),
    }


def _dispatch_context_workflow_policy(dispatch_context: dict | None) -> dict | None:
    if not isinstance(dispatch_context, dict):
        return None
    policy = dispatch_context.get("workflow_policy")
    if not isinstance(policy, dict):
        policy = dispatch_context.get("workflowPolicy")
    if not isinstance(policy, dict):
        return None
    return {
        "step_delay_seconds": _normalize_positive_float(
            policy.get("step_delay_seconds") or policy.get("stepDelaySeconds"),
            default=AUTO_STEP_DELAY_SECONDS,
        ),
        "max_dispatch_retry": _normalize_positive_int(
            policy.get("max_dispatch_retry") or policy.get("maxDispatchRetry"),
            default=DEFAULT_WORKFLOW_MAX_DISPATCH_RETRY,
        ),
        "dispatch_retry_backoff_seconds": _normalize_positive_float(
            policy.get("dispatch_retry_backoff_seconds")
            or policy.get("dispatchRetryBackoffSeconds"),
            default=DEFAULT_WORKFLOW_DISPATCH_RETRY_BACKOFF_SECONDS,
        ),
        "execution_timeout_seconds": _normalize_positive_float(
            policy.get("execution_timeout_seconds") or policy.get("executionTimeoutSeconds"),
            default=DEFAULT_WORKFLOW_EXECUTION_TIMEOUT_SECONDS,
        ),
    }


def _run_workflow_policy(run: dict | None, *, workflow: dict | None = None) -> dict:
    dispatch_context_policy = _dispatch_context_workflow_policy(_run_dispatch_context(run))
    if dispatch_context_policy is not None:
        return dispatch_context_policy
    return _workflow_policy_from_workflow(workflow)


def _build_run_dispatch_context(
    *,
    dispatch_context: dict | None,
    workflow: dict | None,
    created_at: str,
    default_type: str,
    default_state: str,
) -> dict:
    context = store.clone(dispatch_context) if isinstance(dispatch_context, dict) else {}
    context["type"] = (
        _normalize_dispatch_context_type(str(context.get("type") or default_type).strip() or default_type)
        or default_type
    )
    context["state"] = str(context.get("state") or default_state).strip() or default_state
    context["queued_at"] = str(context.get("queued_at") or context.get("queuedAt") or created_at).strip()
    context["updated_at"] = str(context.get("updated_at") or context.get("updatedAt") or created_at).strip()
    _normalize_dispatch_fallback_policy_mode_for_write(context)
    context["workflow_policy"] = _workflow_policy_from_workflow(workflow)
    return context


def _workflow_step_delay_for_run(run_id: str) -> float:
    try:
        run = _find_run(run_id)
    except HTTPException:
        return AUTO_STEP_DELAY_SECONDS

    workflow = None
    workflow_id = str((run or {}).get("workflow_id") or "").strip()
    if workflow_id:
        try:
            workflow = _find_workflow(workflow_id)
        except HTTPException:
            workflow = None

    policy = _run_workflow_policy(run, workflow=workflow)
    return _normalize_positive_float(
        policy.get("step_delay_seconds"),
        default=AUTO_STEP_DELAY_SECONDS,
    )


def _normalize_workflow_node_type(node_type: str | None) -> str:
    normalized = str(node_type or "").strip().lower()
    if normalized == "aggregate":
        return "merge"
    return normalized or "agent"


def _message_trigger_channels(workflow: dict) -> list[str]:
    trigger = workflow.get("trigger")
    raw_channels = None
    if isinstance(trigger, dict):
        raw_channels = trigger.get("channels")

    if raw_channels is None:
        return []
    if isinstance(raw_channels, str):
        items = raw_channels.replace("，", ",").split(",")
    elif isinstance(raw_channels, list):
        items = raw_channels
    else:
        return []

    channels: list[str] = []
    for item in items:
        normalized = str(item).strip().lower()
        if normalized and normalized not in channels:
            channels.append(normalized)
    return channels


def _message_trigger_preferred_language(workflow: dict) -> str | None:
    trigger = workflow.get("trigger")
    if not isinstance(trigger, dict):
        return None
    return _normalize_language(
        str(trigger.get("preferred_language") or trigger.get("preferredLanguage") or "")
    )


def _message_trigger_priority(workflow: dict) -> int:
    trigger = workflow.get("trigger")
    if not isinstance(trigger, dict):
        return 100
    try:
        return int(trigger.get("priority") or 100)
    except (TypeError, ValueError):
        return 100


def _select_workflow_for_intent(intent: str | None = None) -> dict:
    workflows = _load_workflows_for_selection()
    if not workflows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    selected_agent_type = INTENT_AGENT_TYPE_MAP.get(intent)
    if selected_agent_type:
        for workflow in workflows:
            if any(
                _derive_agent_type(node) == selected_agent_type
                for node in workflow["nodes"]
            ):
                return workflow

    if intent:
        for workflow in workflows:
            if intent.lower() in _trigger_haystack(workflow.get("trigger")):
                return workflow
    return workflows[0]


def _format_route_message(intent: str, workflow: dict, route_reason: str) -> str:
    return f"已识别意图: {intent}；命中工作流: {workflow['name']}；路由依据: {route_reason}"


def _collect_message_route_candidates(
    intent: str,
    message_text: str,
    *,
    channel: str | None = None,
    detected_lang: str | None = None,
) -> list[tuple[tuple[int, int, int, int, int, int], dict, str]]:
    workflows = _load_workflows_for_selection()
    if not workflows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    normalized_text = message_text.lower()
    normalized_channel = str(channel or "").strip().lower()
    normalized_lang = _normalize_language(detected_lang)
    selected_agent_type = INTENT_AGENT_TYPE_MAP.get(intent)
    candidates: list[tuple[tuple[int, int, int, int, int, int], dict, str]] = []

    for index, workflow in enumerate(workflows):
        if str(workflow.get("status") or "").lower() not in {"", "active", "running"}:
            continue

        channels = _message_trigger_channels(workflow)
        if channels and normalized_channel and normalized_channel not in channels:
            continue

        preferred_language = _message_trigger_preferred_language(workflow)
        if preferred_language and normalized_lang and preferred_language != normalized_lang:
            continue

        keywords = _message_trigger_keywords(workflow)
        matched_keywords = [keyword for keyword in keywords if keyword in normalized_text]
        if keywords and not matched_keywords:
            continue

        match_count = len(matched_keywords)
        priority = _message_trigger_priority(workflow)
        channel_specific = int(bool(channels))
        language_specific = int(bool(preferred_language))
        agent_match = int(
            selected_agent_type is not None
            and any(_derive_agent_type(node) == selected_agent_type for node in workflow["nodes"])
        )
        route_reasons = [f"意图={intent}"]
        if channels:
            route_reasons.append(f"渠道={normalized_channel or channels[0]}")
        if preferred_language:
            route_reasons.append(f"语言={preferred_language}")
        if matched_keywords:
            route_reasons.append(f"关键词={', '.join(matched_keywords[:3])}")
        elif not keywords:
            route_reasons.append("message 默认兜底")

        candidate = (
            (
                channel_specific,
                language_specific,
                priority,
                match_count,
                agent_match,
                -index,
            ),
            workflow,
            "；".join(route_reasons),
        )
        candidates.append(candidate)

    candidates.sort(key=lambda entry: entry[0], reverse=True)
    return candidates


def select_workflow_candidates_for_message(
    intent: str,
    message_text: str,
    *,
    channel: str | None = None,
    detected_lang: str | None = None,
) -> list[tuple[dict, str]]:
    candidates = _collect_message_route_candidates(
        intent,
        message_text,
        channel=channel,
        detected_lang=detected_lang,
    )
    if candidates:
        return [
            (
                candidate[1],
                _format_route_message(intent, candidate[1], candidate[2]),
            )
            for candidate in candidates
        ]

    workflow = _select_workflow_for_intent(intent)
    route_message = _format_route_message(intent, workflow, "intent fallback")
    return [(workflow, route_message)]


def select_workflow_for_message(
    intent: str,
    message_text: str,
    *,
    channel: str | None = None,
    detected_lang: str | None = None,
) -> tuple[dict, str]:
    candidates = select_workflow_candidates_for_message(
        intent,
        message_text,
        channel=channel,
        detected_lang=detected_lang,
    )
    workflow, route_message = candidates[0]
    return workflow, route_message


def _step_haystack(step: dict) -> str:
    return f"{step.get('title', '')} {step.get('agent', '')} {step.get('message', '')}"


def _find_step(steps: list[dict], *keywords: str) -> dict | None:
    patterns = [keyword for keyword in keywords if keyword]
    for step in steps:
        haystack = _step_haystack(step)
        if any(keyword in haystack for keyword in patterns):
            return step
    return None


def _find_steps(steps: list[dict], *keywords: str) -> list[dict]:
    patterns = [keyword for keyword in keywords if keyword]
    return [step for step in steps if any(keyword in _step_haystack(step) for keyword in patterns)]


def _status_from_step(step: dict | None, fallback: str = "idle") -> str:
    if not step:
        return fallback
    raw_status = step.get("status")
    if raw_status == "completed":
        return "completed"
    if raw_status == "running":
        return "running"
    if raw_status == "failed":
        return "error"
    if raw_status == "pending":
        return "waiting"
    return fallback


def _agent_name_for_intent(intent: str | None) -> str:
    return {
        "search": "搜索Agent",
        "write": "写作Agent",
        "help": "输出Agent",
        "manual": "Workflow Engine",
        None: "Workflow Engine",
    }[intent]


def _normalize_intent(value: str | None) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"search", "write", "help", "manual"}:
        return normalized
    return None


def _execution_route_seed(
    *,
    run: dict | None = None,
    workflow: dict | None = None,
    agent_type: str | None = None,
) -> str | None:
    parts = [
        str((run or {}).get("id") or "").strip(),
        str((run or {}).get("task_id") or "").strip(),
        str((workflow or {}).get("id") or "").strip(),
        str(agent_type or "").strip().lower(),
    ]
    items = [part for part in parts if part]
    if not items:
        return None
    return ":".join(items)


def _find_enabled_agent_by_type(agent_type: str | None, *, route_seed: str | None = None) -> dict | None:
    normalized_type = str(agent_type or "").strip().lower()
    if not normalized_type:
        return None

    selected_external = external_agent_registry_service.select_agent(
        agent_type=normalized_type,
        route_seed=route_seed,
    )
    if selected_external is not None:
        return selected_external

    candidates: list[dict] = []
    for agent in _load_agents_for_execution():
        if str(agent.get("type") or "").strip().lower() != normalized_type:
            continue
        if not bool(agent.get("enabled", False)):
            continue
        candidates.append(agent)

    if not candidates:
        return None

    healthy = [agent for agent in candidates if is_agent_routable(agent, include_degraded=False)]
    if healthy:
        healthy.sort(key=routing_priority, reverse=True)
        return healthy[0]

    degraded_candidates = [agent for agent in candidates if is_agent_routable(agent, include_degraded=True)]
    if degraded_candidates:
        degraded_candidates.sort(key=routing_priority, reverse=True)
        return degraded_candidates[0]
    return None


def resolve_agent_dispatch_execution_agent(intent: str | None, *, route_seed: str | None = None) -> dict | None:
    selected_agent_type = INTENT_AGENT_TYPE_MAP.get(_normalize_intent(intent))
    if not selected_agent_type:
        return None
    return _find_enabled_agent_by_type(selected_agent_type, route_seed=route_seed)


def resolve_direct_execution_agent(intent: str | None, *, route_seed: str | None = None) -> dict | None:
    # Compatibility wrapper for legacy callers.
    return resolve_agent_dispatch_execution_agent(intent, route_seed=route_seed)


def _normalize_dispatch_context_type(dispatch_type: str | None) -> str:
    normalized = str(dispatch_type or "").strip().lower()
    if normalized == LEGACY_DIRECT_AGENT_DISPATCH_TYPE:
        return "agent_dispatch"
    return normalized


def _normalize_fallback_policy_mode(mode: str | None) -> str:
    normalized = str(mode or "").strip().lower()
    if normalized == LEGACY_DIRECT_AGENT_FALLBACK_MODE:
        return "agent_dispatch_fallback"
    return normalized


def _normalize_fallback_policy_payload_mode_for_write(policy: object) -> None:
    if not isinstance(policy, dict):
        return
    normalized_mode = _normalize_fallback_policy_mode(policy.get("mode"))
    if normalized_mode:
        policy["mode"] = normalized_mode


def _normalize_dispatch_fallback_policy_mode_for_write(dispatch_context: dict) -> None:
    _normalize_fallback_policy_payload_mode_for_write(dispatch_context.get("fallback_policy"))
    route_decision = _dispatch_context_route_decision(dispatch_context)
    if not isinstance(route_decision, dict):
        return
    _normalize_fallback_policy_payload_mode_for_write(route_decision.get("fallback_policy"))
    _normalize_fallback_policy_payload_mode_for_write(route_decision.get("fallbackPolicy"))


def _resolve_agent_binding(
    binding: str | None,
    *,
    expected_type: str | None,
    route_seed: str | None = None,
) -> dict | None:
    normalized_binding = str(binding or "").strip()
    if not normalized_binding:
        return None

    agent = _find_agent_mutable(normalized_binding)
    if agent is not None:
        if not bool(agent.get("enabled", False)):
            return None
        if not is_agent_routable(agent):
            return None
        if expected_type and str(agent.get("type") or "").strip().lower() != expected_type:
            return None
        return agent

    binding_type = normalized_binding.lower()
    if binding_type not in KNOWN_AGENT_TYPES:
        return None
    if expected_type and binding_type != expected_type:
        return None
    return _find_enabled_agent_by_type(binding_type, route_seed=route_seed)


def resolve_workflow_execution_agent(
    workflow: dict,
    intent: str | None,
    *,
    route_seed: str | None = None,
) -> dict | None:
    selected_agent_type = INTENT_AGENT_TYPE_MAP.get(intent)
    if not selected_agent_type:
        return None

    selected_node = _selected_branch_node(workflow, intent)
    explicit_node_binding = str((selected_node or {}).get("agent_id") or "").strip()
    if explicit_node_binding:
        return _resolve_agent_binding(
            explicit_node_binding,
            expected_type=selected_agent_type,
            route_seed=route_seed,
        )

    if selected_node is not None:
        node_agent = _find_enabled_agent_by_type(
            _derive_agent_type(selected_node) or selected_agent_type,
            route_seed=route_seed,
        )
        if node_agent is not None:
            return node_agent

    for binding in workflow.get("agent_bindings") or []:
        resolved = _resolve_agent_binding(
            str(binding),
            expected_type=selected_agent_type,
            route_seed=route_seed,
        )
        if resolved is not None:
            return resolved

    return _find_enabled_agent_by_type(selected_agent_type, route_seed=route_seed)


def _is_agent_dispatch_run(run: dict | None) -> bool:
    if not isinstance(run, dict):
        return False
    dispatch_context = _run_dispatch_context(run)
    dispatch_type = _normalize_dispatch_context_type((dispatch_context or {}).get("type"))
    if dispatch_type == "agent_dispatch":
        return True
    return str(run.get("workflow_id") or "").strip() in AGENT_DISPATCH_WORKFLOW_IDS

def _run_dispatch_context(run: dict | None) -> dict | None:
    return dispatch_context_from_run(run)


def _dispatch_context_route_decision(dispatch_context: dict | None) -> dict | None:
    return route_decision_from_payload(dispatch_context)


def _dispatch_context_execution_agent_id(dispatch_context: dict | None) -> str | None:
    route_decision = _dispatch_context_route_decision(dispatch_context)
    if route_decision is None:
        return None
    execution_agent_id = str(
        route_decision.get("execution_agent_id") or route_decision.get("executionAgentId") or ""
    ).strip()
    if execution_agent_id:
        return execution_agent_id
    return None


def _dispatch_context_state(dispatch_context: dict | None) -> str | None:
    if not isinstance(dispatch_context, dict):
        return None
    state = str(dispatch_context.get("state") or "").strip().lower()
    if state:
        return state
    return None


def _mark_dispatch_context_state(run: dict, state: str, **updates: object) -> None:
    dispatch_context = _run_dispatch_context(run)
    if dispatch_context is None:
        return

    dispatch_context["state"] = state
    dispatch_context["updated_at"] = store.now_string()
    for key, value in updates.items():
        dispatch_context[key] = value
    state_machine = dispatch_context.get("state_machine")
    if not isinstance(state_machine, dict):
        state_machine = {"version": "brain_fact_layer_v1"}
        dispatch_context["state_machine"] = state_machine
    state_machine["dispatch_state"] = state


def _mark_dispatch_context_failure(
    run: dict,
    *,
    state: str,
    failure_stage: str,
    failure_message: str,
    failed_at: str | None = None,
    **updates: object,
) -> None:
    timestamp = failed_at or store.now_string()
    _mark_dispatch_context_state(
        run,
        state,
        failed_at=timestamp,
        failure_stage=failure_stage,
        failure_message=failure_message,
        **updates,
    )
    _append_fallback_history(
        run,
        state=state,
        failure_stage=failure_stage,
        failure_message=failure_message,
        failed_at=timestamp,
    )


def _dispatch_context_fallback_policy(dispatch_context: dict | None) -> dict:
    if not isinstance(dispatch_context, dict):
        return {}
    policy = dispatch_context.get("fallback_policy")
    if not isinstance(policy, dict):
        policy = dispatch_context.get("fallbackPolicy")
    if not isinstance(policy, dict):
        route_decision = _dispatch_context_route_decision(dispatch_context)
        if isinstance(route_decision, dict):
            policy = route_decision.get("fallback_policy") or route_decision.get("fallbackPolicy")
    return policy if isinstance(policy, dict) else {}


def _classify_fallback_reason(*, state: str, failure_stage: str, failure_message: str) -> str:
    normalized_message = str(failure_message or "").strip().lower()
    if "timeout" in normalized_message or "超时" in normalized_message or state == "execution_timeout":
        return "execution_timeout"
    if "协议" in normalized_message or "protocol" in normalized_message:
        return "protocol_error"
    if "不可用" in normalized_message or "missing" in normalized_message or "缺少可用" in normalized_message:
        return "executor_unavailable"
    if "结果" in normalized_message and ("不合格" in normalized_message or "invalid" in normalized_message):
        return "invalid_result"
    if failure_stage == "dispatch":
        return "dispatch_failure"
    if failure_stage == "execution":
        return "execution_failure"
    if failure_stage == "outbound":
        return "delivery_failure"
    return "unknown_failure"


def _resolved_fallback_action(*, fallback_policy: dict, reason: str) -> str:
    mode = _normalize_fallback_policy_mode(fallback_policy.get("mode"))
    on_failure = str(
        fallback_policy.get("on_failure") or fallback_policy.get("onFailure") or ""
    ).strip().lower()
    if mode == "approval_gate":
        return "human_handoff"
    if mode == "planner_recovery":
        return (
            "planner_retry"
            if reason in {"execution_timeout", "executor_unavailable", "dispatch_failure"}
            else "planner_review"
        )
    if mode == "agent_dispatch_fallback":
        return "reroute_agent_execution"
    if on_failure == "retry_or_fail_terminal":
        return "retry_or_fail_terminal"
    if on_failure:
        return on_failure
    return "fail_terminal"


def _state_machine_fallback_attempts(dispatch_context: dict | None) -> int:
    if not isinstance(dispatch_context, dict):
        return 0
    state_machine = dispatch_context.get("state_machine")
    if not isinstance(state_machine, dict):
        return 0
    try:
        return max(int(state_machine.get("fallback_attempt_count") or 0), 0)
    except (TypeError, ValueError):
        return 0


def _increment_fallback_attempts(dispatch_context: dict | None) -> int:
    if not isinstance(dispatch_context, dict):
        return 0
    state_machine = dispatch_context.setdefault("state_machine", {"version": "brain_fact_layer_v1"})
    if not isinstance(state_machine, dict):
        state_machine = {"version": "brain_fact_layer_v1"}
        dispatch_context["state_machine"] = state_machine
    attempts = _state_machine_fallback_attempts(dispatch_context) + 1
    state_machine["fallback_attempt_count"] = attempts
    return attempts


def _should_auto_recover_fallback(*, fallback_policy: dict, reason: str, dispatch_context: dict | None) -> bool:
    mode = _normalize_fallback_policy_mode(fallback_policy.get("mode"))
    if mode not in AUTO_RECOVERY_FALLBACK_MODES:
        return False
    if reason not in {
        "execution_timeout",
        "executor_unavailable",
        "dispatch_failure",
        "protocol_error",
        "invalid_result",
    }:
        return False
    return _state_machine_fallback_attempts(dispatch_context) < 1


def _append_fallback_step(task_id: str, *, message: str) -> None:
    _append_step(
        task_id=task_id,
        title="主脑自动回退",
        status="completed",
        agent="Brain Fallback Controller",
        message=message,
        tokens=0,
    )


def _append_workflow_runtime_audit(
    *,
    run: dict,
    task: dict | None,
    action: str,
    status_value: str,
    details: str,
    metadata: dict[str, object] | None = None,
) -> None:
    payload = {
        "id": f"audit-workflow-{uuid4().hex[:10]}",
        "timestamp": store.now_string(),
        "action": action,
        "user": str(
            (task or {}).get("user_key")
            or (task or {}).get("session_id")
            or (task or {}).get("id")
            or "system"
        ),
        "resource": f"workflow_run:{str(run.get('id') or '').strip() or 'unknown'}",
        "status": status_value,
        "ip": "-",
        "details": details,
    }
    if metadata:
        payload["metadata"] = store.clone(metadata)
    store.audit_logs.insert(0, store.clone(payload))
    del store.audit_logs[200:]
    persistence_service.append_audit_log(log=payload)
    trace_exporter_service.export_audit_event(payload)


def _is_valid_task_result_payload(task_result: object) -> bool:
    if not isinstance(task_result, dict):
        return False
    result_kind = str(task_result.get("kind") or "").strip()
    if not result_kind:
        return False
    for key in ("title", "summary", "content", "text"):
        if str(task_result.get(key) or "").strip():
            return True
    bullets = task_result.get("bullets")
    if isinstance(bullets, list) and any(str(item or "").strip() for item in bullets):
        return True
    return False


def _normalize_agent_execution_failure_message(exc: Exception) -> str:
    message = str(exc or "").strip() or "Agent 执行失败"
    if "protocol" in message.lower() or "协议" in message:
        return f"Agent 执行协议错误：{message}"
    return message


def _attempt_fallback_recovery_locked(
    *,
    task: dict | None,
    run: dict,
    failure_stage: str,
    failure_message: str,
    state: str,
    recovery_trigger: str,
) -> dict | None:
    if task is None:
        return None
    dispatch_context = _run_dispatch_context(run)
    fallback_policy = _dispatch_context_fallback_policy(dispatch_context)
    mode = _normalize_fallback_policy_mode(fallback_policy.get("mode"))
    reason = _classify_fallback_reason(
        state=state,
        failure_stage=failure_stage,
        failure_message=failure_message,
    )
    if mode == "approval_gate":
        return _enter_manual_handoff_locked(
            task=task,
            run=run,
            failure_stage=failure_stage,
            failure_message=failure_message,
            state=state,
            reason=reason,
            handoff_source="fallback_policy",
            operator="Brain Fallback Controller",
        )
    if not _should_auto_recover_fallback(
        fallback_policy=fallback_policy,
        reason=reason,
        dispatch_context=dispatch_context,
    ):
        return None

    attempts = _increment_fallback_attempts(dispatch_context)
    timestamp = store.now_string()
    _append_fallback_history(
        run,
        state=state,
        failure_stage=failure_stage,
        failure_message=failure_message,
        failed_at=timestamp,
    )
    recovery_action = _resolved_fallback_action(
        fallback_policy=fallback_policy,
        reason=reason,
    )
    _append_fallback_step(
        str(task.get("id") or ""),
        message=(
            f"检测到{reason}，已按策略执行自动回退；"
            f"action={recovery_action}；attempt={attempts}"
        ),
    )
    restarted_run = restart_workflow_run_for_task(
        task,
        intent=run.get("intent"),
        trigger=recovery_trigger,
    )
    restarted_run = _find_run(str(restarted_run.get("id") or ""))
    restarted_context = _run_dispatch_context(restarted_run)
    if isinstance(restarted_context, dict):
        restarted_context["fallback_recovery_state"] = "scheduled"
        restarted_context["fallback_recovery_reason"] = reason
        restarted_context["fallback_recovery_action"] = recovery_action
        restarted_context["fallback_recovery_at"] = timestamp
        restarted_context["updated_at"] = timestamp
    restarted_run = _refresh_run_state(restarted_run, task)
    _publish_run_event(restarted_run, "workflow_run.updated")
    _persist_execution_state(
        task=task,
        steps=_ensure_task_steps_loaded(str(task.get("id") or "")),
        run=restarted_run,
    )
    _schedule_retry_follow_up(restarted_run["id"])
    return restarted_run


def _enter_manual_handoff_locked(
    *,
    task: dict,
    run: dict,
    failure_stage: str,
    failure_message: str,
    state: str,
    reason: str | None = None,
    handoff_source: str,
    operator: str | None = None,
    note: str | None = None,
) -> dict:
    timestamp = store.now_string()
    steps = _ensure_task_steps_loaded(str(task.get("id") or ""))
    dispatch_context = _run_dispatch_context(run)
    fallback_policy = _dispatch_context_fallback_policy(dispatch_context)
    resolved_reason = reason or _classify_fallback_reason(
        state=state,
        failure_stage=failure_stage,
        failure_message=failure_message,
    )
    resolved_action = _resolved_fallback_action(
        fallback_policy=fallback_policy,
        reason=resolved_reason,
    )
    running_step = next(
        (step for step in reversed(steps) if step.get("status") == "running"),
        None,
    )
    handoff_message = note or failure_message or "任务已转入人工接管，等待人工确认"
    if running_step is not None:
        running_step["status"] = "failed"
        running_step["finished_at"] = timestamp
        running_step["message"] = handoff_message
    else:
        _append_step(
            task_id=str(task.get("id") or ""),
            title="人工接管",
            status="failed",
            agent="Brain Manual Handoff Controller",
            message=handoff_message,
            tokens=0,
        )
    _append_fallback_step(
        str(task.get("id") or ""),
        message=(
            f"检测到{resolved_reason}，已转入人工接管；"
            f"action={resolved_action}；source={handoff_source}"
        ),
    )

    task["status"] = "failed"
    task["completed_at"] = timestamp
    task["duration"] = task.get("duration") or "等待人工接管"
    task["result"] = None

    route_decision = _dispatch_context_route_decision(dispatch_context)
    if isinstance(route_decision, dict):
        route_decision["approval_required"] = True
        route_decision["requires_approval"] = True
        route_decision["approval_status"] = "pending_manual_handoff"

    _mark_dispatch_context_state(
        run,
        "manual_handoff_required",
        failed_at=timestamp,
        failure_stage=failure_stage,
        failure_message=failure_message,
        fallback_recovery_state="handoff_required",
        fallback_recovery_reason=resolved_reason,
        fallback_recovery_action=resolved_action,
        fallback_recovery_at=timestamp,
        manual_handoff_required_at=timestamp,
        manual_handoff_source=handoff_source,
        manual_handoff_operator=str(operator or "").strip() or None,
        manual_handoff_note=str(note or "").strip() or None,
        approval_status="pending_manual_handoff",
    )
    _append_fallback_history(
        run,
        state=state,
        failure_stage=failure_stage,
        failure_message=failure_message,
        failed_at=timestamp,
    )
    _append_workflow_runtime_audit(
        run=run,
        task=task,
        action="workflow.manual_handoff",
        status_value="warning",
        details=(
            f"run={run.get('id')}; task={task.get('id')}; reason={resolved_reason}; "
            f"source={handoff_source}; note={str(note or '').strip() or '-'}"
        ),
        metadata={
            "workflow_run_id": str(run.get("id") or ""),
            "task_id": str(task.get("id") or ""),
            "reason": resolved_reason,
            "failure_stage": failure_stage,
            "handoff_source": handoff_source,
            "operator": str(operator or "").strip() or None,
            "action": resolved_action,
        },
    )

    try:
        refreshed_run = _refresh_run_state(run, task)
    except HTTPException as exc:
        if not _is_workflow_not_found(exc):
            raise
        refreshed_run = _refresh_run_state_without_workflow(run, task)
    _publish_run_event(refreshed_run, "workflow_run.updated")
    _persist_execution_state(task=task, steps=steps, run=refreshed_run)
    _cancel_scheduled_run(refreshed_run["id"])
    return refreshed_run


def _append_fallback_history(
    run: dict,
    *,
    state: str,
    failure_stage: str,
    failure_message: str,
    failed_at: str,
) -> None:
    dispatch_context = _run_dispatch_context(run)
    if dispatch_context is None:
        return
    fallback_policy = _dispatch_context_fallback_policy(dispatch_context)
    reason = _classify_fallback_reason(
        state=state,
        failure_stage=failure_stage,
        failure_message=failure_message,
    )
    history = dispatch_context.setdefault("fallback_history", [])
    if not isinstance(history, list):
        history = []
        dispatch_context["fallback_history"] = history
    history.append(
        {
            "id": f"fallback-{uuid4().hex[:10]}",
            "timestamp": failed_at,
            "state": state,
            "failure_stage": failure_stage,
            "reason": reason,
            "message": failure_message,
            "policy_mode": str(fallback_policy.get("mode") or "").strip() or None,
            "policy_target": str(fallback_policy.get("target") or "").strip() or None,
            "resolved_action": _resolved_fallback_action(
                fallback_policy=fallback_policy,
                reason=reason,
            ),
        }
    )
    state_machine = dispatch_context.setdefault("state_machine", {"version": "brain_fact_layer_v1"})
    if isinstance(state_machine, dict):
        state_machine["last_fallback_reason"] = reason
        state_machine["last_fallback_at"] = failed_at


def _record_delivery_state(run: dict, delivery: dict | None, *, preserve_failure: bool = True) -> None:
    dispatch_context = _run_dispatch_context(run)
    if dispatch_context is None or not isinstance(delivery, dict):
        return

    status_value = str(delivery.get("status") or "").strip().lower() or None
    message = str(delivery.get("message") or "").strip() or None
    timestamp = store.now_string()
    dispatch_context["delivery_status"] = status_value
    dispatch_context["delivery_message"] = message
    dispatch_context["updated_at"] = timestamp
    if status_value == "sent":
        dispatch_context["delivery_completed_at"] = timestamp
        dispatch_context.pop("delivery_failed_at", None)
    elif status_value == "failed":
        dispatch_context["delivery_failed_at"] = timestamp
        dispatch_context.pop("delivery_completed_at", None)
        if not preserve_failure and message:
            dispatch_context["failure_stage"] = "outbound"
            dispatch_context["failure_message"] = message
    elif status_value == "skipped":
        dispatch_context.pop("delivery_completed_at", None)
        dispatch_context.pop("delivery_failed_at", None)


def _mask_delivery_target(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    if len(normalized) <= 8:
        return "*" * len(normalized)
    return f"{normalized[:3]}***{normalized[-4:]}"


def _delivery_target_type(*, run: dict, channel: str, target_id: str | None) -> str | None:
    dispatch_context = _run_dispatch_context(run)
    channel_delivery = None
    if isinstance(dispatch_context, dict):
        candidate = dispatch_context.get("channel_delivery") or dispatch_context.get("channelDelivery")
        if isinstance(candidate, dict):
            channel_delivery = candidate
    if isinstance(channel_delivery, dict):
        target_type = str(
            channel_delivery.get("target_type")
            or channel_delivery.get("targetType")
            or ""
        ).strip()
        if target_type:
            return target_type
        if channel == "dingtalk" and str(channel_delivery.get("session_webhook") or channel_delivery.get("sessionWebhook") or "").strip():
            return "session_webhook"
        if channel == "dingtalk" and str(channel_delivery.get("platform_user_id") or channel_delivery.get("platformUserId") or "").strip():
            return "openapi_user"
    if target_id:
        return "chat_id" if channel == "telegram" else "session_id"
    return None


def _delivery_result_title(task_result: dict | None) -> str | None:
    if not isinstance(task_result, dict):
        return None
    for key in ("title", "text", "summary", "content"):
        value = str(task_result.get(key) or "").strip()
        if value:
            return value[:120]
    return None


def _build_delivery_fact_context(
    *,
    task: dict,
    run: dict,
    delivery: dict | None,
    task_result: dict | None = None,
) -> dict[str, object]:
    manager_packet = task.get("manager_packet") if isinstance(task.get("manager_packet"), dict) else {}
    dispatch_context = _run_dispatch_context(run)
    if not isinstance(dispatch_context, dict):
        dispatch_context = {}
    channel = str(task.get("channel") or dispatch_context.get("channel") or "").strip() or None
    target_id = None
    if channel:
        try:
            target_id = channel_outbound_service._resolve_target_id(task, run=run, channel=channel)
        except Exception:
            target_id = None
    if not target_id:
        if channel == "telegram":
            target_id = (
                str(dispatch_context.get("chat_id") or dispatch_context.get("chatId") or "").strip()
                or str(task.get("session_id") or "").strip().removeprefix("telegram:")
                or str(task.get("user_key") or "").strip().removeprefix("telegram:")
                or None
            )
        elif channel:
            target_id = (
                str(task.get("session_id") or "").strip()
                or str(dispatch_context.get("session_id") or dispatch_context.get("sessionId") or "").strip()
                or str(dispatch_context.get("chat_id") or dispatch_context.get("chatId") or "").strip()
                or None
            )
    status_value = str((delivery or {}).get("status") or "").strip().lower() or None
    return {
        "delivery_mode": str(manager_packet.get("delivery_mode") or manager_packet.get("deliveryMode") or "").strip() or None,
        "response_contract": str(manager_packet.get("response_contract") or manager_packet.get("responseContract") or "").strip() or None,
        "channel": channel,
        "target_type": _delivery_target_type(run=run, channel=channel or "", target_id=target_id),
        "target_present": bool(target_id),
        "target_ref": _mask_delivery_target(target_id),
        "result_kind": str((task_result or {}).get("kind") or dispatch_context.get("result_kind") or "").strip() or None,
        "result_title": _delivery_result_title(task_result),
        "fallback_delivery": status_value in {"failed", "skipped"},
    }


def _requeue_dispatch_context(run: dict, *, queued_at: str | None = None) -> None:
    dispatch_context = _run_dispatch_context(run)
    if dispatch_context is None:
        return

    timestamp = queued_at or store.now_string()
    for key in (
        "dispatched_at",
        "completed_at",
        "failed_at",
        "failure_stage",
        "failure_message",
        "delivery_status",
        "delivery_message",
        "delivery_completed_at",
        "delivery_failed_at",
        "result_kind",
        "delivery_fact_context",
        "execution_target_type",
        "execution_target_id",
        "execution_target",
    ):
        dispatch_context.pop(key, None)
    dispatch_context["execution_agent_id"] = None
    dispatch_context["execution_agent"] = None
    dispatch_context["queued_at"] = timestamp
    dispatch_context["state"] = "queued"
    dispatch_context["updated_at"] = timestamp


def _clone_requeued_dispatch_context(
    run: dict | None,
    *,
    queued_at: str,
) -> dict | None:
    dispatch_context = store.clone(_run_dispatch_context(run))
    if not isinstance(dispatch_context, dict):
        return None

    cloned_run = {"dispatch_context": dispatch_context}
    _requeue_dispatch_context(cloned_run, queued_at=queued_at)
    return dispatch_context


def _dispatch_context_matches_retry_target(
    dispatch_context: dict | None,
    *,
    workflow_id: str,
    intent: str | None,
) -> bool:
    route_decision = _dispatch_context_route_decision(dispatch_context)
    if route_decision is None:
        return True

    route_workflow_id = str(
        route_decision.get("workflow_id") or route_decision.get("workflowId") or ""
    ).strip()
    route_intent = _normalize_intent(route_decision.get("intent"))
    if route_workflow_id and route_workflow_id != workflow_id:
        return False
    if route_intent and route_intent != intent:
        return False
    return True


def _apply_context_patch_to_dispatch_context(
    run: dict,
    *,
    task: dict | None,
    message_text: str,
    trace_id: str,
) -> None:
    dispatch_context = _run_dispatch_context(run)
    if dispatch_context is None:
        return

    timestamp = store.now_string()
    try:
        existing_patch_count = int(dispatch_context.get("context_patch_count") or 0)
    except (TypeError, ValueError):
        existing_patch_count = 0

    dispatch_context["context_patch_count"] = existing_patch_count + 1
    dispatch_context["last_context_patch_at"] = timestamp
    dispatch_context["last_context_patch_trace_id"] = str(trace_id or "").strip() or None
    dispatch_context["last_context_patch_preview"] = (
        _truncate_text(message_text, CONTEXT_PATCH_PREVIEW_LIMIT) or None
    )
    audit_items = dispatch_context.setdefault("context_patch_audit", [])
    if isinstance(audit_items, list):
        audit_items.append(
            {
                "patched_at": timestamp,
                "trace_id": str(trace_id or "").strip() or None,
                "message_preview": _truncate_text(message_text, CONTEXT_PATCH_PREVIEW_LIMIT) or None,
                "state_before": _dispatch_context_state(dispatch_context),
            }
        )

    current_state = _dispatch_context_state(dispatch_context)
    should_requeue = current_state in {"failed"}
    if isinstance(task, dict):
        task_status = str(task.get("status") or "").strip().lower()
        if task_status == "pending":
            should_requeue = True
        elif task_status == "running":
            try:
                workflow = _find_workflow(run["workflow_id"])
            except HTTPException:
                workflow = None
            task_id = str(task.get("id") or "").strip()
            steps = _ensure_task_steps_loaded(task_id) if task_id else []
            selected_node = _selected_branch_node(workflow, run.get("intent")) if workflow else None
            execution_step = _execution_step_for_node(steps, selected_node) if workflow else None
            if execution_step is None and current_state != "completed":
                should_requeue = True

    if should_requeue:
        _requeue_dispatch_context(run, queued_at=timestamp)
        return

    dispatch_context["updated_at"] = timestamp


def _resolve_dispatch_execution_agent(
    workflow: dict,
    run: dict,
    intent: str | None,
) -> dict | None:
    dispatch_context = _run_dispatch_context(run)
    execution_agent_id = _dispatch_context_execution_agent_id(dispatch_context)
    selected_agent_type = INTENT_AGENT_TYPE_MAP.get(intent)
    route_seed = _execution_route_seed(run=run, workflow=workflow, agent_type=selected_agent_type)
    if execution_agent_id:
        resolved = _resolve_agent_binding(
            execution_agent_id,
            expected_type=selected_agent_type,
            route_seed=route_seed,
        )
        if resolved is not None:
            return resolved
    try:
        return resolve_workflow_execution_agent(
            workflow,
            intent,
            route_seed=route_seed,
        )
    except TypeError as exc:
        if "route_seed" not in str(exc):
            raise
        return resolve_workflow_execution_agent(workflow, intent)


def _workflow_has_execution_target(
    workflow: dict,
    run: dict,
    intent: str | None,
) -> bool:
    del run
    return _selected_branch_node(workflow, intent) is not None


def _refresh_agent_success_rate(agent: dict) -> None:
    total = max(int(agent.get("tasks_total", 0)), 0)
    completed = max(int(agent.get("tasks_completed", 0)), 0)
    if total <= 0:
        return
    agent["success_rate"] = round((completed / total) * 100, 1)


def _mark_execution_agent_started(agent: dict | None) -> None:
    if agent is None:
        return

    agent["status"] = "running"
    agent["last_active"] = "刚刚"
    agent["tasks_total"] = int(agent.get("tasks_total", 0)) + 1
    _refresh_agent_success_rate(agent)
    _persist_agent_state(agent)


def _mark_execution_agent_succeeded(agent: dict | None, *, tokens_used: int) -> None:
    if agent is None:
        return

    next_completed = int(agent.get("tasks_completed", 0)) + 1
    agent["tasks_completed"] = next_completed
    agent["tasks_total"] = max(int(agent.get("tasks_total", 0)), next_completed)
    agent["tokens_used"] = int(agent.get("tokens_used", 0)) + max(int(tokens_used), 0)
    agent["status"] = "idle"
    agent["last_active"] = "刚刚"
    _refresh_agent_success_rate(agent)
    _persist_agent_state(agent)


def _mark_execution_agent_failed(agent: dict | None) -> None:
    if agent is None:
        return

    completed = int(agent.get("tasks_completed", 0))
    agent["tasks_total"] = max(int(agent.get("tasks_total", 0)), completed + 1)
    agent["status"] = "idle"
    agent["last_active"] = "刚刚"
    _refresh_agent_success_rate(agent)
    _persist_agent_state(agent)


def _selected_branch_node(workflow: dict, intent: str | None) -> dict | None:
    selected_agent_type = INTENT_AGENT_TYPE_MAP.get(intent)
    nodes = workflow.get("nodes") or []
    if not selected_agent_type:
        for node in nodes:
            if _normalize_workflow_node_type(node.get("type")) == "workflow" and _derive_workflow_binding(node):
                return node
            if _normalize_workflow_node_type(node.get("type")) == "tool" and _derive_tool_binding(node):
                return node
        for node in nodes:
            if _normalize_workflow_node_type(node.get("type")) != "agent":
                continue
            if _derive_agent_binding(node) or _derive_agent_type(node) or str(node.get("label") or "").strip():
                return node
        return None

    for node in nodes:
        if _normalize_workflow_node_type(node.get("type")) != "agent":
            continue
        if _derive_agent_type(node) == selected_agent_type:
            return node

    for node in nodes:
        if _normalize_workflow_node_type(node.get("type")) != "agent":
            continue
        if selected_agent_type in str(node.get("label", "")).lower():
            return node

    for node in nodes:
        if _normalize_workflow_node_type(node.get("type")) == "workflow" and _derive_workflow_binding(node):
            return node
        if _normalize_workflow_node_type(node.get("type")) == "tool" and _derive_tool_binding(node):
            return node
    return None


def _manager_packet_for_run(task: dict, run: dict) -> dict[str, Any]:
    dispatch_context = _run_dispatch_context(run) or {}
    manager_packet = dispatch_context.get("manager_packet")
    if isinstance(manager_packet, dict):
        return manager_packet
    manager_packet = task.get("manager_packet")
    return manager_packet if isinstance(manager_packet, dict) else {}


def _conversation_node_message(task: dict, run: dict) -> str | None:
    manager_packet = _manager_packet_for_run(task, run)
    handoff_summary = str(
        manager_packet.get("handoff_summary") or manager_packet.get("handoffSummary") or ""
    ).strip()
    if handoff_summary:
        return handoff_summary
    normalized_intent = str(run.get("intent") or "").strip().lower()
    if normalized_intent and normalized_intent != "manual":
        return "已完成需求澄清，并整理出可供分发层消费的 handoff summary"
    return None


def _task_dispatcher_node_message(task: dict, run: dict) -> str | None:
    dispatch_context = _run_dispatch_context(run) or {}
    route_decision = route_decision_from_payload(dispatch_context) or route_decision_from_task(task) or {}
    route_reason = str(
        route_decision.get("route_reason_summary") or route_decision.get("routeReasonSummary") or ""
    ).strip()
    if route_reason:
        return route_reason
    normalized_intent = str(run.get("intent") or "").strip().lower()
    if normalized_intent and normalized_intent != "manual":
        return f"已完成需求分析，并选定执行意图: {normalized_intent}"
    return None


def _execution_step_for_node(steps: list[dict], node: dict | None) -> dict | None:
    if not node:
        return None

    agent_type = _derive_agent_type(node)
    agent_markers = [str(node.get("label") or "").strip()]
    generic_agent_name = {
        "search": "搜索Agent",
        "write": "写作Agent",
        "output": "输出Agent",
    }.get(agent_type)
    if generic_agent_name:
        agent_markers.append(generic_agent_name)

    agent_binding = _derive_agent_binding(node)
    resolved_agent = _resolve_agent_binding(
        agent_binding,
        expected_type=agent_type,
    )
    resolved_agent_name = str((resolved_agent or {}).get("name") or "").strip()
    if resolved_agent_name:
        agent_markers.append(resolved_agent_name)

    for step in steps:
        step_title = str(step.get("title") or "").strip()
        if step_title in {"等待调度", "等待执行策略"}:
            continue
        if step_title in {"执行节点", "执行异常", "调度异常"}:
            return step
        step_agent = str(step.get("agent") or "").strip()
        if any(marker and marker in step_agent for marker in agent_markers):
            return step
    return None


def _execution_status_from_task(task: dict) -> str:
    if task["status"] == "completed":
        return "completed"
    if task["status"] == "failed":
        return "error"
    if task["status"] == "cancelled":
        return "idle"
    if task["status"] == "pending":
        return "waiting"
    if task["status"] == "running":
        return "running"
    return "idle"


def _context_patch_count(steps: list[dict]) -> int:
    return len(_find_steps(steps, "上下文", "context_patch"))


def _parse_datetime(value: str | None) -> datetime | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _duration_ms_between(started_at: str | None, finished_at: str | None) -> int | None:
    started = _parse_datetime(started_at)
    finished = _parse_datetime(finished_at)
    if started is None or finished is None:
        return None
    duration_ms = round((finished - started).total_seconds() * 1000)
    return max(duration_ms, 0)


def _step_duration_ms(step: dict | None) -> int:
    if not isinstance(step, dict):
        return 0
    duration_ms = _duration_ms_between(step.get("started_at"), step.get("finished_at"))
    if duration_ms is None:
        return 0
    return duration_ms


def _normalize_run_metrics_payload(payload: dict | None) -> dict:
    metrics = payload if isinstance(payload, dict) else {}
    tokens_total = 0
    duration_ms = metrics.get("duration_ms")
    step_count = 0
    for field in ("tokens_total", "step_count"):
        try:
            metrics[field] = max(int(metrics.get(field) or 0), 0)
        except (TypeError, ValueError):
            metrics[field] = 0
    tokens_total = metrics["tokens_total"]
    step_count = metrics["step_count"]
    try:
        normalized_duration_ms = max(int(duration_ms), 0) if duration_ms is not None else None
    except (TypeError, ValueError):
        normalized_duration_ms = None

    return {
        "tokens_total": tokens_total,
        "duration_ms": normalized_duration_ms,
        "step_count": step_count,
        "execution_agent_id": str(metrics.get("execution_agent_id") or "").strip() or None,
        "execution_agent": str(metrics.get("execution_agent") or "").strip() or None,
        "agent_started_at": str(metrics.get("agent_started_at") or "").strip() or None,
        "agent_finished_at": str(metrics.get("agent_finished_at") or "").strip() or None,
    }


def _run_metrics_from_dispatch_context(run: dict | None) -> dict | None:
    dispatch_context = _run_dispatch_context(run)
    if not isinstance(dispatch_context, dict):
        return None
    return _normalize_run_metrics_payload(dispatch_context.get("run_metrics"))


def _apply_stored_run_metrics(run: dict) -> dict:
    metrics = _run_metrics_from_dispatch_context(run)
    if metrics is None:
        metrics = _normalize_run_metrics_payload(None)
    run["metrics"] = store.clone(metrics)
    run["tokens_total"] = metrics["tokens_total"]
    run["duration_ms"] = metrics["duration_ms"]
    run["step_count"] = metrics["step_count"]
    run["execution_agent_id"] = metrics["execution_agent_id"]
    run["execution_agent"] = metrics["execution_agent"]
    run["agent_started_at"] = metrics["agent_started_at"]
    run["agent_finished_at"] = metrics["agent_finished_at"]
    return run


def _compute_run_metrics(*, run: dict, task: dict, steps: list[dict]) -> dict:
    dispatch_context = _run_dispatch_context(run)
    execution_agent_id = None
    execution_agent = None
    if isinstance(dispatch_context, dict):
        execution_agent_id = str(dispatch_context.get("execution_agent_id") or "").strip() or None
        execution_agent = str(dispatch_context.get("execution_agent") or "").strip() or None

    execution_steps = [
        step
        for step in steps
        if str(step.get("agent") or "").strip() not in {"安全Agent", "意图识别Agent", "输出Agent"}
    ]
    primary_execution_step = execution_steps[-1] if execution_steps else None

    agent_started_at = None
    agent_finished_at = None
    if isinstance(primary_execution_step, dict):
        agent_started_at = str(primary_execution_step.get("started_at") or "").strip() or None
        agent_finished_at = str(primary_execution_step.get("finished_at") or "").strip() or None
        if execution_agent is None:
            execution_agent = str(primary_execution_step.get("agent") or "").strip() or None

    duration_ms = _duration_ms_between(run.get("started_at"), task.get("completed_at") or run.get("completed_at"))
    if duration_ms is None:
        duration_ms = sum(_step_duration_ms(step) for step in steps)
        if duration_ms <= 0:
            duration_ms = None

    return _normalize_run_metrics_payload(
        {
            "tokens_total": sum(max(int(step.get("tokens") or 0), 0) for step in steps),
            "duration_ms": duration_ms,
            "step_count": len(steps),
            "execution_agent_id": execution_agent_id,
            "execution_agent": execution_agent,
            "agent_started_at": agent_started_at,
            "agent_finished_at": agent_finished_at,
        }
    )


def _sync_run_metrics(run: dict, task: dict, steps: list[dict]) -> dict:
    metrics = _compute_run_metrics(run=run, task=task, steps=steps)
    dispatch_context = _run_dispatch_context(run)
    if isinstance(dispatch_context, dict):
        dispatch_context["run_metrics"] = store.clone(metrics)

    _apply_stored_run_metrics(run)
    return metrics


def _build_brain_fact_snapshot(*, run: dict, task: dict, steps: list[dict]) -> dict:
    dispatch_context = _run_dispatch_context(run) or {}
    route_decision = _dispatch_context_route_decision(dispatch_context) or {}
    manager_packet = dispatch_context.get("manager_packet")
    if not isinstance(manager_packet, dict):
        manager_packet = task.get("manager_packet") if isinstance(task.get("manager_packet"), dict) else {}
    brain_dispatch_summary = dispatch_context.get("brain_dispatch_summary")
    if not isinstance(brain_dispatch_summary, dict):
        brain_dispatch_summary = (
            task.get("brain_dispatch_summary")
            if isinstance(task.get("brain_dispatch_summary"), dict)
            else {}
        )
    fallback_history = dispatch_context.get("fallback_history")
    if not isinstance(fallback_history, list):
        fallback_history = []
    run_metrics = _run_metrics_from_dispatch_context(run) or _compute_run_metrics(run=run, task=task, steps=steps)
    delivery_fact_context = dispatch_context.get("delivery_fact_context")
    if not isinstance(delivery_fact_context, dict):
        delivery_fact_context = {}
    return {
        "version": "brain_fact.v1",
        "routing_fact": {
            "intent": str(run.get("intent") or route_decision.get("intent") or "").strip() or None,
            "workflow_id": str(run.get("workflow_id") or route_decision.get("workflow_id") or route_decision.get("workflowId") or "").strip() or None,
            "workflow_name": str(run.get("workflow_name") or route_decision.get("workflow_name") or route_decision.get("workflowName") or "").strip() or None,
            "interaction_mode": str(route_decision.get("interaction_mode") or route_decision.get("interactionMode") or "").strip() or None,
            "workflow_mode": str(route_decision.get("workflow_mode") or route_decision.get("workflowMode") or "").strip() or None,
            "execution_agent_id": str(dispatch_context.get("execution_agent_id") or route_decision.get("execution_agent_id") or route_decision.get("executionAgentId") or "").strip() or None,
            "execution_agent": str(dispatch_context.get("execution_agent") or route_decision.get("execution_agent") or route_decision.get("executionAgent") or "").strip() or None,
            "approval_required": bool(
                route_decision.get("approval_required")
                if isinstance(route_decision.get("approval_required"), bool)
                else route_decision.get("approvalRequired")
            ),
            "approval_status": str(route_decision.get("approval_status") or route_decision.get("approvalStatus") or "").strip() or None,
            "route_reason_summary": str(brain_dispatch_summary.get("route_reason_summary") or brain_dispatch_summary.get("routeReasonSummary") or "").strip() or None,
        },
        "manager_fact": {
            "manager_action": str(manager_packet.get("manager_action") or manager_packet.get("managerAction") or "").strip() or None,
            "next_owner": str(manager_packet.get("next_owner") or manager_packet.get("nextOwner") or "").strip() or None,
            "delivery_mode": str(manager_packet.get("delivery_mode") or manager_packet.get("deliveryMode") or "").strip() or None,
            "response_contract": str(manager_packet.get("response_contract") or manager_packet.get("responseContract") or "").strip() or None,
            "session_state": str(manager_packet.get("session_state") or manager_packet.get("sessionState") or "").strip() or None,
        },
        "fallback_fact": {
            "count": len(fallback_history),
            "last_reason": str((fallback_history[-1] or {}).get("reason") or "").strip() or None if fallback_history else None,
            "last_failure_stage": str((fallback_history[-1] or {}).get("failure_stage") or "").strip() or None if fallback_history else None,
            "recovery_action": str(dispatch_context.get("fallback_recovery_action") or "").strip() or None,
            "manual_handoff_required": str(dispatch_context.get("state") or "").strip() == "manual_handoff_required",
        },
        "delivery_fact": {
            "delivery_mode": str(delivery_fact_context.get("delivery_mode") or manager_packet.get("delivery_mode") or manager_packet.get("deliveryMode") or "").strip() or None,
            "response_contract": str(delivery_fact_context.get("response_contract") or manager_packet.get("response_contract") or manager_packet.get("responseContract") or "").strip() or None,
            "channel": str(delivery_fact_context.get("channel") or task.get("channel") or dispatch_context.get("channel") or "").strip() or None,
            "target_type": str(delivery_fact_context.get("target_type") or "").strip() or None,
            "target_present": bool(delivery_fact_context.get("target_present")),
            "target_ref": str(delivery_fact_context.get("target_ref") or "").strip() or None,
            "delivery_status": str(dispatch_context.get("delivery_status") or "").strip() or None,
            "delivery_message": str(dispatch_context.get("delivery_message") or "").strip() or None,
            "delivery_completed_at": str(dispatch_context.get("delivery_completed_at") or "").strip() or None,
            "delivery_failed_at": str(dispatch_context.get("delivery_failed_at") or "").strip() or None,
            "result_kind": str(delivery_fact_context.get("result_kind") or dispatch_context.get("result_kind") or "").strip() or None,
            "result_title": str(delivery_fact_context.get("result_title") or "").strip() or None,
            "fallback_delivery": bool(delivery_fact_context.get("fallback_delivery")),
        },
        "execution_fact": {
            "status": str(task.get("status") or "").strip() or None,
            "tokens_total": int(run_metrics.get("tokens_total") or 0),
            "duration_ms": run_metrics.get("duration_ms"),
            "step_count": int(run_metrics.get("step_count") or 0),
            "current_stage": str(run.get("current_stage") or "").strip() or None,
        },
        "state_fact": {
            "dispatch_state": str(dispatch_context.get("state") or "").strip() or None,
            "task_status": str(task.get("status") or "").strip() or None,
            "updated_at": str(run.get("updated_at") or store.now_string()),
        },
    }


def _node_issue_sort_key(issue: dict) -> datetime:
    return _parse_datetime(issue.get("timestamp")) or datetime.min.replace(tzinfo=UTC)


def _build_issue_entry(
    *,
    entry_id: str,
    timestamp: str | None,
    severity: str,
    source: str,
    agent: str,
    message: str,
    step_id: str | None = None,
    step_title: str | None = None,
) -> dict:
    return {
        "id": entry_id,
        "timestamp": timestamp,
        "severity": severity,
        "source": source,
        "agent": agent,
        "message": message,
        "step_id": step_id,
        "step_title": step_title,
    }


def _append_node_issue(history_by_node: dict[str, list[dict]], node_id: str | None, entry: dict) -> None:
    normalized_node_id = str(node_id or "").strip()
    if not normalized_node_id:
        return

    node_history = history_by_node.setdefault(normalized_node_id, [])
    entry_id = str(entry.get("id") or "").strip()
    if entry_id and any(str(existing.get("id") or "").strip() == entry_id for existing in node_history):
        return

    signature = (
        str(entry.get("timestamp") or "").strip(),
        str(entry.get("severity") or "").strip(),
        str(entry.get("source") or "").strip(),
        str(entry.get("agent") or "").strip(),
        str(entry.get("message") or "").strip(),
        str(entry.get("step_id") or "").strip(),
    )
    for existing in node_history:
        existing_signature = (
            str(existing.get("timestamp") or "").strip(),
            str(existing.get("severity") or "").strip(),
            str(existing.get("source") or "").strip(),
            str(existing.get("agent") or "").strip(),
            str(existing.get("message") or "").strip(),
            str(existing.get("step_id") or "").strip(),
        )
        if existing_signature == signature:
            return

    node_history.append(entry)


def _resolve_log_occurred_at(log: dict, run: dict) -> str | None:
    occurred_at = str(log.get("occurred_at") or "").strip()
    if occurred_at:
        return occurred_at

    normalized_timestamp = str(log.get("timestamp") or "").strip()
    parsed_timestamp = _parse_datetime(normalized_timestamp)
    if parsed_timestamp is not None:
        return parsed_timestamp.isoformat()

    if normalized_timestamp.count(":") == 2:
        base_time = _parse_datetime(run.get("updated_at")) or _parse_datetime(run.get("created_at"))
        if base_time is not None:
            try:
                hour, minute, second = (int(part) for part in normalized_timestamp.split(":"))
                return base_time.replace(
                    hour=hour,
                    minute=minute,
                    second=second,
                    microsecond=0,
                ).isoformat()
            except ValueError:
                return base_time.isoformat()

    return str(run.get("updated_at") or run.get("created_at") or "").strip() or None


def _node_id_for_step(
    workflow: dict,
    run: dict,
    task: dict,
    step: dict,
    *,
    selected_node: dict | None,
) -> str | None:
    title_haystack = f"{step.get('title', '')} {step.get('message', '')}"
    agent_haystack = f"{step.get('agent', '')} {step.get('message', '')}"

    for node in workflow["nodes"]:
        agent_type = _derive_agent_type(node)
        if agent_type == "security" and any(keyword in title_haystack for keyword in ("安全", "网关")):
            return node["id"]
        if agent_type == "intent" and any(keyword in title_haystack for keyword in ("意图", "路由", "Master Bot")):
            return node["id"]
        if node["type"] == "output" and any(
            keyword in title_haystack for keyword in ("发送结果", "输出", "回传")
        ):
            return node["id"]

    if selected_node is not None:
        selected_agent_name = _agent_name_for_intent(run.get("intent"))
        task_agent = str(task.get("agent") or "").strip()
        step_agent = str(step.get("agent") or "").strip()
        step_title = str(step.get("title") or "").strip()
        if (
            step_title in {"执行节点", "执行异常", "调度异常"}
            or step_agent == selected_agent_name
            or step_agent == task_agent
        ):
            return selected_node["id"]
        if str(step.get("status") or "").strip().lower() == "failed":
            return selected_node["id"]

    return None


def _build_node_error_history(
    workflow: dict,
    task: dict,
    run: dict,
    steps: list[dict],
) -> dict[str, list[dict]]:
    selected_node = _selected_branch_node(workflow, run.get("intent"))
    history_by_node: dict[str, list[dict]] = {}

    for step in steps:
        if step.get("status") != "failed":
            continue
        node_id = _node_id_for_step(
            workflow,
            run,
            task,
            step,
            selected_node=selected_node,
        )
        _append_node_issue(
            history_by_node,
            node_id,
            _build_issue_entry(
                entry_id=f"{step['id']}-failed",
                timestamp=step.get("finished_at") or step.get("started_at") or run.get("updated_at"),
                severity="error",
                source="task_step",
                agent=str(step.get("agent") or "Workflow Engine"),
                message=str(step.get("message") or step.get("title") or "工作流节点执行失败"),
                step_id=str(step.get("id") or "") or None,
                step_title=str(step.get("title") or "") or None,
            ),
        )

    selected_node_id = str((selected_node or {}).get("id") or "").strip()
    dispatcher_messages: set[str] = set()
    raw_logs = run.get("logs", [])
    if isinstance(raw_logs, list):
        for log in raw_logs:
            if not isinstance(log, dict):
                continue
            agent = str(log.get("agent") or "").strip()
            source = str(log.get("source") or "").strip().lower()
            severity = str(log.get("type") or "warning").strip().lower()
            message = str(log.get("message") or "").strip()
            if not message or severity not in {"warning", "error"}:
                continue
            if agent != "Workflow Dispatcher" and source != "dispatcher":
                continue
            dispatcher_messages.add(message)
            _append_node_issue(
                history_by_node,
                selected_node_id,
                _build_issue_entry(
                    entry_id=str(log.get("id") or f"{selected_node_id}-dispatcher-{len(dispatcher_messages)}"),
                    timestamp=_resolve_log_occurred_at(log, run),
                    severity=severity,
                    source="dispatcher",
                    agent=agent or "Workflow Dispatcher",
                    message=message,
                ),
            )

    last_dispatch_error = str(run.get("last_dispatch_error") or "").strip()
    if last_dispatch_error and last_dispatch_error not in dispatcher_messages:
        _append_node_issue(
            history_by_node,
            selected_node_id,
            _build_issue_entry(
                entry_id=f"{run['id']}-last-dispatch-error",
                timestamp=str(run.get("updated_at") or run.get("created_at") or "").strip() or None,
                severity="error",
                source="dispatcher",
                agent="Workflow Dispatcher",
                message=last_dispatch_error,
            ),
        )

    for node_id, entries in history_by_node.items():
        history_by_node[node_id] = sorted(
            entries,
            key=_node_issue_sort_key,
            reverse=True,
        )

    return history_by_node


def _build_run_nodes(workflow: dict, task: dict, run: dict, steps: list[dict]) -> list[dict]:
    selected_node = _selected_branch_node(workflow, run.get("intent"))
    selected_execution_step = _execution_step_for_node(steps, selected_node)
    selected_execution_fallback = _execution_status_from_task(task)
    if (
        selected_execution_step is None
        and _dispatch_context_state(_run_dispatch_context(run)) in {"queued", "dispatching"}
    ):
        selected_execution_fallback = "waiting"
    selected_execution_status = _status_from_step(
        selected_execution_step,
        selected_execution_fallback,
    )
    security_step = _find_step(steps, "安全", "网关")
    route_step = _find_step(steps, "意图", "路由", "Master Bot")
    output_step = _find_step(steps, "发送结果", "输出", "回传")
    context_patch_count = _context_patch_count(steps)
    node_error_history = _build_node_error_history(workflow, task, run, steps)

    nodes: list[dict] = []
    for node in workflow["nodes"]:
        label = node["label"]
        node_type = _normalize_workflow_node_type(node.get("type"))
        agent_binding = _derive_agent_binding(node)
        agent_type = _derive_agent_type(node)
        node_state = {
            "id": node["id"],
            "type": node_type,
            "label": label,
            "status": "idle",
            "agent_id": agent_binding,
            "message": None,
            "tokens": 0,
            "started_at": run["started_at"],
            "finished_at": None,
            "latest_error": None,
            "latest_error_at": None,
            "error_count": 0,
            "error_history": [],
        }

        if node_type == "trigger":
            node_state["status"] = "completed"
            node_state["message"] = f"触发器已接收事件 ({run['trigger']})"
            node_state["finished_at"] = run["started_at"]
        elif agent_type == "security":
            if security_step:
                node_state["status"] = _status_from_step(security_step, "completed")
                node_state["message"] = security_step.get("message")
                node_state["tokens"] = security_step.get("tokens", 0)
                node_state["started_at"] = security_step.get("started_at") or run["started_at"]
                node_state["finished_at"] = security_step.get("finished_at")
            elif task["status"] == "pending":
                node_state["status"] = "waiting"
                node_state["message"] = "等待安全网关校验"
            else:
                node_state["status"] = "completed"
                node_state["message"] = "消息已通过安全网关"
                node_state["finished_at"] = run["started_at"]
        elif agent_type == "intent":
            if route_step:
                node_state["status"] = _status_from_step(route_step, "completed")
                node_state["message"] = route_step.get("message")
                node_state["tokens"] = route_step.get("tokens", 0)
                node_state["started_at"] = route_step.get("started_at") or run["started_at"]
                node_state["finished_at"] = route_step.get("finished_at")
            elif run.get("intent") and run["intent"] != "manual":
                node_state["status"] = "completed"
                node_state["message"] = f"已识别意图: {run['intent']}"
                node_state["finished_at"] = run["started_at"]
            elif task["status"] == "pending":
                node_state["status"] = "waiting"
                node_state["message"] = "等待路由决策"
            else:
                node_state["status"] = "idle"
                node_state["message"] = "尚未进入意图识别"
        elif agent_type == "conversation":
            conversation_message = _conversation_node_message(task, run)
            if conversation_message:
                node_state["status"] = "completed"
                node_state["message"] = conversation_message
                node_state["finished_at"] = run["updated_at"]
            elif task["status"] == "pending":
                node_state["status"] = "waiting"
                node_state["message"] = "等待对话澄清"
            else:
                node_state["status"] = "idle"
                node_state["message"] = "尚未进入对话接待"
        elif agent_type == "task_dispatcher":
            dispatcher_message = _task_dispatcher_node_message(task, run)
            if route_step:
                node_state["status"] = _status_from_step(route_step, "completed")
                node_state["message"] = route_step.get("message")
                node_state["tokens"] = route_step.get("tokens", 0)
                node_state["started_at"] = route_step.get("started_at") or run["started_at"]
                node_state["finished_at"] = route_step.get("finished_at")
            elif dispatcher_message:
                node_state["status"] = "completed"
                node_state["message"] = dispatcher_message
                node_state["finished_at"] = run["updated_at"]
            elif task["status"] == "pending":
                node_state["status"] = "waiting"
                node_state["message"] = "等待需求分析与任务分发"
            else:
                node_state["status"] = "idle"
                node_state["message"] = "尚未进入任务分发"
        elif node_type == "condition":
            if selected_node:
                node_state["status"] = "completed"
                node_state["message"] = f"已命中 {selected_node['label']}"
                node_state["finished_at"] = run["updated_at"]
            elif task["status"] in {"pending", "running"}:
                node_state["status"] = "waiting"
                node_state["message"] = "等待执行策略"
            else:
                node_state["status"] = "idle"
                node_state["message"] = "暂无分支命中"
        elif node_type == "agent" and selected_node and node["id"] == selected_node["id"]:
            node_state["status"] = selected_execution_status
            if selected_execution_step:
                node_state["message"] = selected_execution_step.get("message") or f"{label} 正在执行"
                node_state["tokens"] = selected_execution_step.get("tokens", task.get("tokens", 0))
                node_state["started_at"] = selected_execution_step.get("started_at") or run["started_at"]
                node_state["finished_at"] = selected_execution_step.get("finished_at")
            else:
                node_state["tokens"] = task.get("tokens", 0)
                node_state["message"] = {
                    "running": f"{label} 正在执行",
                    "completed": f"{label} 已完成执行",
                    "error": f"{label} 执行失败",
                    "waiting": f"{label} 等待调度",
                    "idle": "任务已取消",
                }[selected_execution_status]

            if context_patch_count and node_state["status"] in {"running", "completed"}:
                node_state["message"] = (
                    f"{node_state['message']}；已吸收 {context_patch_count} 条上下文补丁"
                )
        elif node_type == "agent":
            node_state["status"] = "idle"
            node_state["message"] = "当前运行未命中该分支"
        elif node_type == "parallel":
            if selected_node and selected_execution_status in {"waiting", "running", "completed", "error"}:
                node_state["status"] = "completed"
                node_state["message"] = f"已分发到分支 {selected_node['label']}"
                node_state["finished_at"] = run["updated_at"]
            elif task["status"] == "pending":
                node_state["status"] = "waiting"
                node_state["message"] = "等待并行分发"
            elif task["status"] == "failed":
                node_state["status"] = "error"
                node_state["message"] = "并行分发未完成"
            else:
                node_state["status"] = "idle"
                node_state["message"] = "等待上游触发"
        elif node_type == "tool" and selected_node and node["id"] == selected_node["id"]:
            if task["status"] == "completed":
                node_state["status"] = "completed"
                node_state["message"] = "工具调用已完成"
                node_state["finished_at"] = task.get("completed_at") or run["updated_at"]
            elif task["status"] == "failed":
                node_state["status"] = "error"
                node_state["message"] = "工具调用因上游失败而终止"
            elif selected_node and selected_execution_status == "running":
                node_state["status"] = "running"
                node_state["message"] = "工具调用执行中"
            elif selected_node and selected_execution_status == "waiting":
                node_state["status"] = "waiting"
                node_state["message"] = "等待工具调用"
            else:
                node_state["status"] = "idle"
                node_state["message"] = "等待执行"
        elif node_type == "tool":
            node_state["status"] = "idle"
            node_state["message"] = "当前运行未命中该工具"
        elif node_type == "workflow" and selected_node and node["id"] == selected_node["id"]:
            if task["status"] == "completed":
                node_state["status"] = "completed"
                node_state["message"] = "子工作流已完成"
                node_state["finished_at"] = task.get("completed_at") or run["updated_at"]
            elif task["status"] == "failed":
                node_state["status"] = "error"
                node_state["message"] = "子工作流执行失败"
            elif selected_execution_status == "running":
                node_state["status"] = "running"
                node_state["message"] = "子工作流执行中"
            elif selected_execution_status == "waiting":
                node_state["status"] = "waiting"
                node_state["message"] = "等待子工作流启动"
            else:
                node_state["status"] = "idle"
                node_state["message"] = "等待执行"
        elif node_type == "workflow":
            node_state["status"] = "idle"
            node_state["message"] = "当前运行未命中该子工作流"
        elif node_type == "transform":
            if task["status"] == "completed":
                node_state["status"] = "completed"
                node_state["message"] = "结果转换已完成"
                node_state["finished_at"] = task.get("completed_at") or run["updated_at"]
            elif task["status"] == "failed":
                node_state["status"] = "error"
                node_state["message"] = "结果转换未完成"
            elif selected_node and selected_execution_status in {"running", "waiting"}:
                node_state["status"] = "waiting"
                node_state["message"] = "等待上游结果进入转换"
            elif selected_node and selected_execution_status == "completed":
                node_state["status"] = "running"
                node_state["message"] = "正在整理中间结果"
            else:
                node_state["status"] = "idle"
                node_state["message"] = "等待执行"
        elif node_type == "merge":
            if task["status"] == "completed":
                node_state["status"] = "completed"
                node_state["message"] = "结果已合流"
                node_state["finished_at"] = task.get("completed_at") or run["updated_at"]
            elif task["status"] == "failed":
                node_state["status"] = "error"
                node_state["message"] = "上游执行失败，结果合流已终止"
            elif selected_node and selected_execution_status in {"running", "waiting"}:
                node_state["status"] = "waiting"
                node_state["message"] = "等待分支结果汇总"
            elif selected_node and selected_execution_status == "completed":
                node_state["status"] = "running"
                node_state["message"] = "分支结果已返回，准备输出"
            else:
                node_state["status"] = "idle"
                node_state["message"] = "等待上游产出"
        elif node_type == "output":
            if output_step:
                node_state["status"] = _status_from_step(output_step, "completed")
                node_state["message"] = output_step.get("message")
                node_state["tokens"] = output_step.get("tokens", 0)
                node_state["started_at"] = output_step.get("started_at") or run["started_at"]
                node_state["finished_at"] = output_step.get("finished_at")
            elif task["status"] == "completed":
                node_state["status"] = "completed"
                node_state["message"] = "结果已发送到目标渠道"
                node_state["finished_at"] = task.get("completed_at") or run["updated_at"]
            elif task["status"] == "failed":
                node_state["status"] = "error"
                node_state["message"] = "输出阶段因任务失败未执行"
            elif selected_node and selected_execution_status in {"running", "completed", "waiting"}:
                node_state["status"] = "waiting"
                node_state["message"] = "等待最终输出"
            else:
                node_state["status"] = "idle"
                node_state["message"] = "等待执行"
        else:
            node_state["status"] = "idle"
            node_state["message"] = "等待执行"

        error_history = node_error_history.get(node["id"], [])
        node_state["error_history"] = error_history
        node_state["error_count"] = len(error_history)
        if error_history:
            node_state["latest_error"] = error_history[0]["message"]
            node_state["latest_error_at"] = error_history[0]["timestamp"]
            if node_state["status"] == "error" and not str(node_state.get("message") or "").strip():
                node_state["message"] = error_history[0]["message"]

        nodes.append(node_state)
    return nodes


def _build_active_edges(workflow: dict, nodes: list[dict]) -> list[str]:
    status_by_id = {node["id"]: node["status"] for node in nodes}
    active_edges: list[str] = []
    for edge in workflow["edges"]:
        source_status = status_by_id.get(edge["source"], "idle")
        target_status = status_by_id.get(edge["target"], "idle")
        if source_status in ACTIVE_NODE_STATUSES and target_status != "idle":
            active_edges.append(edge["id"])
    return active_edges


def _current_stage(task: dict, nodes: list[dict]) -> str:
    for node in nodes:
        if node["status"] == "running":
            return node["label"]

    if task["status"] == "completed":
        return "执行完成"
    if task["status"] == "failed":
        return "执行失败"
    if task["status"] == "cancelled":
        return "已取消"

    for node in nodes:
        if node["status"] == "waiting":
            if node["type"] == "condition":
                return "等待执行策略"
            return node["label"]

    for node in reversed(nodes):
        if node["status"] in {"completed", "error"}:
            return node["label"]
    return "等待开始"


def _normalize_existing_logs(run: dict) -> list[dict]:
    raw_logs = run.get("logs", [])
    if not isinstance(raw_logs, list):
        return []
    return [store.clone(log) for log in raw_logs if isinstance(log, dict)]


def _log_sort_key(log: dict, run: dict) -> datetime:
    return _parse_datetime(_resolve_log_occurred_at(log, run)) or datetime.min.replace(tzinfo=UTC)


def _merge_logs(run: dict, derived_logs: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen_ids: set[str] = set()
    seen_signatures: set[tuple[str, str, str, str]] = set()

    for log in [*_normalize_existing_logs(run), *derived_logs]:
        if not isinstance(log, dict):
            continue

        log_id = str(log.get("id") or "").strip()
        if log_id:
            if log_id in seen_ids:
                continue
            seen_ids.add(log_id)

        signature = (
            str(log.get("occurred_at") or log.get("timestamp") or "").strip(),
            str(log.get("type") or "").strip(),
            str(log.get("agent") or "").strip(),
            str(log.get("message") or "").strip(),
        )
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        merged.append(log)

    merged.sort(key=lambda item: _log_sort_key(item, run))
    return merged


def _build_logs(task: dict, run: dict, steps: list[dict]) -> list[dict]:
    existing_dispatcher_messages = {
        str(log.get("message") or "").strip()
        for log in _normalize_existing_logs(run)
        if str(log.get("agent") or "").strip() == "Workflow Dispatcher"
    }

    logs = [
        {
            "id": f"{run['id']}-trigger",
            "timestamp": _time_only(run["created_at"]),
            "occurred_at": run["created_at"],
            "type": "info",
            "agent": "触发器",
            "message": f"收到运行触发，来源 {run['trigger']}，任务「{task['title']}」",
        }
    ]

    for step in steps:
        step_status = step.get("status", "completed")
        logs.append(
            {
                "id": step["id"],
                "timestamp": _time_only(step.get("finished_at") or step.get("started_at")),
                "occurred_at": step.get("finished_at") or step.get("started_at") or run["created_at"],
                "type": (
                    "success"
                    if step_status == "completed"
                    else "info"
                    if step_status == "running"
                    else "warning"
                    if step_status == "pending"
                    else "error"
                ),
                "agent": step.get("agent", "Workflow Engine"),
                "message": step.get("message", step.get("title", "工作流步骤更新")),
            }
        )

    warnings = run.get("warnings", [])
    if isinstance(warnings, list):
        for index, warning in enumerate(warnings):
            if not isinstance(warning, str) or not warning.strip():
                continue
            if warning in existing_dispatcher_messages:
                continue
            logs.append(
                {
                    "id": f"{run['id']}-warning-{index}",
                    "timestamp": _time_only(run.get("updated_at") or run["created_at"]),
                    "occurred_at": run.get("updated_at") or run["created_at"],
                    "type": "warning",
                    "agent": "Workflow Dispatcher",
                    "source": "dispatcher",
                    "message": warning,
                }
            )

    if task["status"] == "completed" and not _find_step(steps, "发送结果", "输出", "回传"):
        logs.append(
            {
                "id": f"{run['id']}-terminal-completed",
                "timestamp": _time_only(task.get("completed_at")),
                "occurred_at": task.get("completed_at") or run.get("updated_at") or run["created_at"],
                "type": "success",
                "agent": "输出Agent",
                "message": "任务执行完成，结果已返回到业务侧",
            }
        )
    elif task["status"] == "failed":
        logs.append(
            {
                "id": f"{run['id']}-terminal-failed",
                "timestamp": _time_only(task.get("completed_at") or run["updated_at"]),
                "occurred_at": task.get("completed_at") or run.get("updated_at") or run["created_at"],
                "type": "error",
                "agent": task["agent"],
                "message": "任务执行失败，等待人工介入或重试",
            }
        )
    elif task["status"] == "cancelled":
        logs.append(
            {
                "id": f"{run['id']}-terminal-cancelled",
                "timestamp": _time_only(task.get("completed_at") or run["updated_at"]),
                "occurred_at": task.get("completed_at") or run.get("updated_at") or run["created_at"],
                "type": "warning",
                "agent": "Workflow Engine",
                "message": "关联任务已取消，工作流运行同步标记为已取消",
            }
        )
    return _merge_logs(run, logs)


def _is_workflow_not_found(exc: HTTPException) -> bool:
    return exc.status_code == status.HTTP_404_NOT_FOUND and exc.detail == "Workflow not found"


def _refresh_run_state_without_workflow(run: dict, task: dict) -> dict:
    steps = store.clone(_ensure_task_steps_loaded(task["id"]))

    run["status"] = task["status"]
    run["updated_at"] = store.now_string()
    run["completed_at"] = (
        task.get("completed_at") or store.now_string()
        if task["status"] in TERMINAL_TASK_STATUSES
        else None
    )
    run["nodes"] = []
    run["active_edges"] = []
    run["current_stage"] = _current_stage(task, [])
    run["logs"] = _build_logs(task, run, steps)
    dispatch_context = _run_dispatch_context(run)
    if isinstance(dispatch_context, dict):
        state_machine = dispatch_context.setdefault("state_machine", {"version": "brain_fact_layer_v1"})
        state_machine["dispatch_state"] = str(dispatch_context.get("state") or "").strip() or None
        state_machine["task_status"] = str(task.get("status") or "").strip() or None
        state_machine["session_state"] = str((task.get("manager_packet") or {}).get("session_state") or "").strip() or None
    task["state_machine"] = {
        "version": "brain_fact_layer_v1",
        "dispatch_state": str((dispatch_context or {}).get("state") or "").strip() or None,
        "task_status": str(task.get("status") or "").strip() or None,
        "session_state": str((task.get("manager_packet") or {}).get("session_state") or "").strip() or None,
    }
    _sync_run_metrics(run, task, steps)
    task["brain_fact_snapshot"] = _build_brain_fact_snapshot(run=run, task=task, steps=steps)
    if isinstance(dispatch_context, dict):
        dispatch_context["brain_fact_snapshot"] = store.clone(task["brain_fact_snapshot"])
    return store.clone(run)


def _refresh_run_state(run: dict, task: dict) -> dict:
    if _is_agent_dispatch_run(run):
        return _refresh_run_state_without_workflow(run, task)
    workflow = _find_workflow(run["workflow_id"])
    steps = store.clone(_ensure_task_steps_loaded(task["id"]))
    nodes = _build_run_nodes(workflow, task, run, steps)

    run["status"] = task["status"]
    run["updated_at"] = store.now_string()
    run["completed_at"] = (
        task.get("completed_at") or store.now_string()
        if task["status"] in TERMINAL_TASK_STATUSES
        else None
    )
    run["nodes"] = nodes
    run["active_edges"] = _build_active_edges(workflow, nodes)
    run["current_stage"] = _current_stage(task, nodes)
    run["logs"] = _build_logs(task, run, steps)
    dispatch_context = _run_dispatch_context(run)
    if isinstance(dispatch_context, dict):
        state_machine = dispatch_context.setdefault("state_machine", {"version": "brain_fact_layer_v1"})
        state_machine["dispatch_state"] = str(dispatch_context.get("state") or "").strip() or None
        state_machine["task_status"] = str(task.get("status") or "").strip() or None
        state_machine["session_state"] = str((task.get("manager_packet") or {}).get("session_state") or "").strip() or None
    task["state_machine"] = {
        "version": "brain_fact_layer_v1",
        "dispatch_state": str((dispatch_context or {}).get("state") or "").strip() or None,
        "task_status": str(task.get("status") or "").strip() or None,
        "session_state": str((task.get("manager_packet") or {}).get("session_state") or "").strip() or None,
    }
    _sync_run_metrics(run, task, steps)
    task["brain_fact_snapshot"] = _build_brain_fact_snapshot(run=run, task=task, steps=steps)
    if isinstance(dispatch_context, dict):
        dispatch_context["brain_fact_snapshot"] = store.clone(task["brain_fact_snapshot"])
    return store.clone(run)


def _append_step(
    *,
    task_id: str,
    title: str,
    status: str,
    agent: str,
    message: str,
    tokens: int = 0,
) -> dict:
    steps = _ensure_task_steps_loaded(task_id)
    timestamp = store.now_string()
    step = {
        "id": f"{task_id}-{len(steps) + 1}",
        "title": title,
        "status": status,
        "agent": agent,
        "started_at": timestamp,
        "finished_at": timestamp if status in {"completed", "failed", "cancelled"} else None,
        "message": message,
        "tokens": tokens,
    }
    steps.append(step)
    return step


def _append_orchestration_steps(
    *,
    task_id: str,
    orchestration_steps: list[dict] | None,
) -> None:
    if not isinstance(orchestration_steps, list):
        return
    for item in orchestration_steps:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        message = str(item.get("message") or "").strip()
        if not title or not message:
            continue
        _append_step(
            task_id=task_id,
            title=title,
            status=str(item.get("status") or "completed").strip() or "completed",
            agent=str(item.get("agent") or "Master Bot Planner").strip() or "Master Bot Planner",
            message=message,
            tokens=int(item.get("tokens") or 0),
        )


def _task_description_lines(task: dict) -> list[str]:
    return [
        line.strip()
        for line in str(task.get("description") or "").splitlines()
        if line.strip()
    ]


def _primary_request_text(task: dict) -> str:
    for line in _task_description_lines(task):
        if not line.startswith("补充上下文:"):
            return line
    return str(task.get("description") or task.get("title") or "当前任务")


def _context_notes(task: dict) -> list[str]:
    notes: list[str] = []
    for line in _task_description_lines(task):
        if line.startswith("补充上下文:"):
            notes.append(line.split("补充上下文:", maxsplit=1)[1].strip())
    return notes


def _memory_notes(task: dict) -> list[str]:
    notes: list[str] = []
    for line in _task_description_lines(task):
        if line.startswith("记忆注入:"):
            notes.append(line.split("记忆注入:", maxsplit=1)[1].strip())
    return notes


def _truncate_text(value: str, limit: int = 20) -> str:
    cleaned = value.strip()
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit]}..."


def _output_language(task: dict) -> str:
    preferred_language = _normalize_language(
        task.get("preferred_language") or task.get("preferredLanguage")
    )
    if preferred_language:
        return preferred_language

    detected_lang = _normalize_language(task.get("detected_lang") or task.get("detectedLang"))
    if detected_lang:
        return detected_lang

    return detect_language(_primary_request_text(task))


def _knowledge_query(task: dict, intent: str) -> str:
    parts = [_primary_request_text(task), *_context_notes(task)[-2:], *_memory_notes(task)[:2]]
    if intent == "write":
        parts.append("WorkBot 项目背景 产品目标 核心特性 MVP")
    elif intent == "help":
        parts.append("开发指南补充 接入 安全网关 工作流 语言支持")
    return " ".join(part for part in parts if part).strip()


def _knowledge_hits(task: dict, intent: str) -> list[dict]:
    query = _knowledge_query(task, intent) or _primary_request_text(task)
    limit = 5 if intent == "search" else 3
    return document_search_service.search(query, intent=intent, limit=limit)


def _knowledge_label(hit: dict) -> str:
    return f"{hit['source_name']} / {hit['section']}"


def _knowledge_references(hits: list[dict], *, language: str = "zh") -> list[dict]:
    keywords_label = "关键词" if language == "zh" else "Keywords"
    excerpt_label = "摘录" if language == "zh" else "Excerpt"
    return [
        {
            "title": _knowledge_label(hit),
            "detail": (
                f"{keywords_label}: {', '.join(hit.get('matched_terms', [])[:4])}; {excerpt_label}: {hit['excerpt']}"
                if hit.get("matched_terms")
                else hit["excerpt"]
            ),
        }
        for hit in hits
    ]


def _build_search_result(task: dict, run: dict) -> dict:
    language = _output_language(task)
    request_text = _primary_request_text(task)
    context_notes = _context_notes(task)
    memory_notes = _memory_notes(task)
    knowledge_hits = _knowledge_hits(task, str(run.get("intent") or "search").lower())
    if language == "en":
        bullets = [
            f"Retrieved {len(knowledge_hits)} relevant project references for \"{_truncate_text(request_text, 24)}\".",
            *[
                f"Matched {_knowledge_label(hit)}: {hit['excerpt']}"
                for hit in knowledge_hits[:2]
            ],
            "If you need a deeper pass, follow the collaboration view logs and rerun with extra context.",
        ]
        if context_notes:
            bullets.append(f"Absorbed extra context: {_truncate_text(context_notes[-1], 28)}.")
        if memory_notes:
            bullets.append(f"Applied memory context: {_truncate_text(memory_notes[0], 28)}.")

        content_lines = [
            f"Search target: {request_text}",
            "",
            "Matched local project materials:",
        ]
        for index, hit in enumerate(knowledge_hits, start=1):
            content_lines.append(f"{index}. {_knowledge_label(hit)}")
            content_lines.append(f"   Summary: {hit['excerpt']}")
            if hit.get("matched_terms"):
                content_lines.append(f"   Keywords: {', '.join(hit['matched_terms'][:4])}")

        content_lines.extend(
            [
                "",
                "Next steps:",
                "1. Verify the matched sections for the entry path, configuration and trigger pattern.",
                "2. If the issue remains, compare the workflow logs against those excerpts to narrow the fault layer.",
                "3. If you need an SOP, convert the referenced sections directly into workflow notes or an operations checklist.",
            ]
        )
        if context_notes:
            content_lines.extend(["", f"Additional context: {context_notes[-1]}"])
        if memory_notes:
            content_lines.extend(["", "Memory hints:", *[f"- {note}" for note in memory_notes[:2]]])

        return {
            "kind": "search_report",
            "title": f"Search Summary - {_truncate_text(request_text, 16)}",
            "summary": f"Generated a grounded search summary for \"{_truncate_text(request_text, 18)}\" from local project materials",
            "content": "\n".join(content_lines),
            "bullets": bullets,
            "references": _knowledge_references(knowledge_hits, language=language),
        }

    bullets = [
        f"已围绕「{_truncate_text(request_text, 24)}」检索到当前项目目录中的 {len(knowledge_hits)} 条相关资料。",
        *[
            f"命中 {_knowledge_label(hit)}：{hit['excerpt']}"
            for hit in knowledge_hits[:2]
        ],
        "如需继续深入，可沿着协作视图中的节点日志回溯具体卡点并补充上下文后重跑。",
    ]
    if context_notes:
        bullets.append(f"已吸收补充要求：{_truncate_text(context_notes[-1], 28)}。")
    if memory_notes:
        bullets.append(f"已结合历史记忆：{_truncate_text(memory_notes[0], 28)}。")

    content_lines = [
        f"检索目标：{request_text}",
        "",
        "命中的本地项目资料：",
    ]
    for index, hit in enumerate(knowledge_hits, start=1):
        content_lines.append(f"{index}. {_knowledge_label(hit)}")
        content_lines.append(f"   摘要：{hit['excerpt']}")
        if hit.get("matched_terms"):
            content_lines.append(f"   命中词：{', '.join(hit['matched_terms'][:4])}")

    content_lines.extend(
        [
            "",
            "后续建议：",
            "1. 优先按上面命中的章节继续核对接入链路、配置项和触发方式。",
            "2. 如果仍有异常，可结合协作视图里的节点日志对照这些文档片段继续排查。",
            "3. 需要沉淀 SOP 时，可直接把这些来源章节转成工作流说明或操作清单。",
        ]
    )
    if context_notes:
        content_lines.extend(
            [
                "",
                f"补充上下文：{context_notes[-1]}",
            ]
        )
    if memory_notes:
        content_lines.extend(
            [
                "",
                "历史记忆线索：",
                *[f"- {note}" for note in memory_notes[:2]],
            ]
        )

    return {
        "kind": "search_report",
        "title": f"检索摘要 - {_truncate_text(request_text, 16)}",
        "summary": f"已基于本地开发文档生成关于「{_truncate_text(request_text, 18)}」的检索结论",
        "content": "\n".join(content_lines),
        "bullets": bullets,
        "references": _knowledge_references(knowledge_hits, language=language),
    }


def _build_write_result(task: dict, run: dict) -> dict:
    language = _output_language(task)
    request_text = _primary_request_text(task)
    context_notes = _context_notes(task)
    memory_notes = _memory_notes(task)
    knowledge_hits = _knowledge_hits(task, str(run.get("intent") or "write").lower())
    if language == "en":
        tone_hint = context_notes[-1] if context_notes else "keep it professional, clear, and ready to send"
        draft = [
            "Hello,",
            "",
            f"For \"{request_text}\", we prepared a grounded draft based on the local project guide and architecture materials in this workspace.",
            "",
            "Primary references used in this draft:",
            *[f"- {_knowledge_label(hit)}: {hit['excerpt']}" for hit in knowledge_hits],
            *(
                ["", "Memory hints:", *[f"- {note}" for note in memory_notes[:2]]]
                if memory_notes
                else []
            ),
            "",
            "Suggested wording:",
            "1. WorkBot is structured around a unified intake layer, security gateway, Master Bot dispatch, agent collaboration, and visual workflow operations.",
            "2. The current stage already provides a runnable admin console and workflow linkage, while deeper infrastructure is still being completed along the MVP roadmap.",
            f"3. The tone has been aligned with the instruction to \"{tone_hint}\", and the draft is ready for direct use or further refinement.",
            "",
            "If needed, I can also rewrite this into a more formal email, announcement, or weekly project update.",
            "",
            "Regards,",
            "WorkBot",
        ]

        return {
            "kind": "draft_message",
            "title": f"Draft Message - {_truncate_text(request_text, 16)}",
            "summary": f"Generated a grounded English draft for \"{_truncate_text(request_text, 18)}\"",
            "content": "\n".join(draft),
            "bullets": [
                "The output has been organized as a deliverable draft based on the current task context.",
                f"The draft is grounded in {len(knowledge_hits)} local project references.",
                *[
                    f"Referenced {_knowledge_label(hit)} as writing support."
                    for hit in knowledge_hits[:2]
                ],
                "If tone, audience, or format changes later, you can continue refining it through context patch.",
            ],
            "references": _knowledge_references(knowledge_hits, language=language),
        }

    tone_hint = context_notes[-1] if context_notes else "保持专业、清晰、可直接发送"
    draft = [
        "您好，",
        "",
        f"关于「{request_text}」，我们结合当前项目目录中的开发指南与架构资料整理了一版可直接使用的回复草稿。",
        "",
        "本次写作主要参考：",
        *[
            f"- {_knowledge_label(hit)}：{hit['excerpt']}"
            for hit in knowledge_hits
        ],
        *(
            [
                "",
                "历史记忆提示：",
                *[f"- {note}" for note in memory_notes[:2]],
            ]
            if memory_notes
            else []
        ),
        "",
        "建议表述如下：",
        "1. WorkBot 当前方案以统一接入层、安全网关、Master Bot 调度、Agent 协作和可视化工作流为主链路。",
        "2. 当前阶段已经具备可运行的后台与工作流联调能力，但底层仍以 MVP 路线逐步补齐真实基础设施与执行引擎。",
        f"3. 语气和措辞已按“{tone_hint}”处理，可直接发送或继续润色。",
        "",
        "如果您愿意，我也可以继续把这份内容改成更正式的邮件版、公告版或项目周报版。",
        "",
        "此致",
        "WorkBot",
    ]

    return {
        "kind": "draft_message",
        "title": f"写作草稿 - {_truncate_text(request_text, 16)}",
        "summary": f"已结合本地项目资料生成一版围绕「{_truncate_text(request_text, 18)}」的文本草稿",
        "content": "\n".join(draft),
        "bullets": [
            "输出内容已按当前任务上下文整理成可直接交付的文稿。",
            f"当前草稿已结合 {len(knowledge_hits)} 条本地资料线索做 grounding。",
            *[
                f"已引用 {_knowledge_label(hit)} 作为写作依据。"
                for hit in knowledge_hits[:2]
            ],
            "如果后续还有语气、篇幅、对象变化，可以继续通过 context patch 追加要求。",
        ],
        "references": _knowledge_references(knowledge_hits, language=language),
    }


def _build_help_result(task: dict, run: dict) -> dict:
    language = _output_language(task)
    request_text = _primary_request_text(task)
    memory_notes = _memory_notes(task)
    knowledge_hits = _knowledge_hits(task, str(run.get("intent") or "help").lower())
    if language == "en":
        return {
            "kind": "help_note",
            "title": f"Help Note - {_truncate_text(request_text, 16)}",
            "summary": "Generated an English guidance note grounded in local project materials",
            "content": "\n".join(
                [
                    f"Topic: {request_text}",
                    "",
                    "Primary references:",
                    *[f"- {_knowledge_label(hit)}: {hit['excerpt']}" for hit in knowledge_hits],
                    *(
                        ["", "Memory hints:", *[f"- {note}" for note in memory_notes[:2]]]
                        if memory_notes
                        else []
                    ),
                    "",
                    "Suggested response:",
                    "1. Start by verifying the matched sections for the current step, trigger style, and configuration.",
                    "2. Then combine permission, security, or workflow logs to identify which layer is failing.",
                    "3. If the issue is still unresolved, move to the collaboration view and continue tracing with extra context.",
                ]
            ),
            "bullets": [
                "This is a guidance-style result that can be reused as a FAQ or support response.",
                *[f"Referenced {_knowledge_label(hit)}." for hit in knowledge_hits[:2]],
                "If the user provides more detail, the same task context can continue absorbing it.",
            ],
            "references": _knowledge_references(knowledge_hits, language=language),
        }

    return {
        "kind": "help_note",
        "title": f"帮助说明 - {_truncate_text(request_text, 16)}",
        "summary": "已结合本地项目资料生成一份可直接回复用户的帮助说明",
        "content": "\n".join(
            [
                f"问题主题：{request_text}",
                "",
                "优先参考资料：",
                *[
                    f"- {_knowledge_label(hit)}：{hit['excerpt']}"
                    for hit in knowledge_hits
                ],
                *(
                    [
                        "",
                        "历史记忆线索：",
                        *[f"- {note}" for note in memory_notes[:2]],
                    ]
                    if memory_notes
                    else []
                ),
                "",
                "建议回复：",
                "1. 先按命中的章节确认当前所处步骤、触发方式和配置项。",
                "2. 再结合权限、安全或工作流日志判断问题发生在哪一层。",
                "3. 如仍无法解决，可转入协作视图继续追踪节点状态并追加上下文。",
            ]
        ),
        "bullets": [
            "这是一份偏说明型的帮助结果，适合继续转成 FAQ 或运营回复。",
            *[
                f"已参考 {_knowledge_label(hit)}。"
                for hit in knowledge_hits[:2]
            ],
            "如果用户再次补充信息，可以直接继续合并到当前任务上下文。",
        ],
        "references": _knowledge_references(knowledge_hits, language=language),
    }


def _build_task_result(task: dict, run: dict) -> dict:
    intent = str(run.get("intent") or "").lower()
    if intent == "search":
        return _build_search_result(task, run)
    if intent == "write":
        return _build_write_result(task, run)
    return _build_help_result(task, run)


def _delivery_message_for_result(task: dict, run: dict, task_result: dict) -> dict[str, str]:
    return channel_outbound_service.deliver_task_result(task, task_result, run=run)


def _delivery_message_for_failure(task: dict, run: dict, error_message: str) -> dict[str, str]:
    return channel_outbound_service.deliver_task_failure(task, error_message, run=run)


def _assistant_message_language(task: dict, content: str) -> str:
    return (
        _normalize_language(str(task.get("preferred_language") or ""))
        or _normalize_language(str(task.get("detected_lang") or ""))
        or detect_language(content)
    )


def _append_assistant_conversation_message(task: dict, content: str) -> None:
    user_key = str(task.get("user_key") or "").strip()
    session_id = str(task.get("session_id") or "").strip()
    message = str(content or "").strip()
    if not user_key or not session_id or not message:
        return

    try:
        memory_service.ingest_message(
            user_id=user_key,
            session_id=session_id,
            role="assistant",
            content=message,
            detected_lang=_assistant_message_language(task, message),
            allow_session_rollover=False,
        )
    except Exception as exc:  # pragma: no cover - defensive guard for auxiliary logging
        logger.warning("Failed to append assistant conversation message for task %s: %s", task.get("id"), exc)


def infer_task_intent(
    task: dict,
    *,
    run: dict | None = None,
    steps: list[dict] | None = None,
) -> str:
    run_intent = _normalize_intent((run or {}).get("intent"))
    if run_intent and run_intent != "manual":
        return run_intent

    result = task.get("result")
    if isinstance(result, dict):
        result_intent = RESULT_KIND_INTENT_MAP.get(str(result.get("kind") or "").strip().lower())
        if result_intent:
            return result_intent

    combined_parts = [
        str(task.get("title") or ""),
        str(task.get("description") or ""),
        str(task.get("agent") or ""),
    ]
    if steps:
        combined_parts.extend(
            f"{step.get('title', '')} {step.get('agent', '')} {step.get('message', '')}"
            for step in steps
        )

    haystack = " ".join(part for part in combined_parts if part).lower()
    if any(token in haystack for token in SEARCH_INTENT_HINTS):
        return "search"
    if any(token in haystack for token in WRITE_INTENT_HINTS):
        return "write"
    return "help"


def _resolve_tick_intent(run: dict, workflow: dict) -> str:
    if run.get("intent") and run["intent"] != "manual":
        return str(run["intent"])

    trigger_haystack = _trigger_haystack(workflow.get("trigger"))
    for candidate in ("search", "write", "help"):
        if candidate in trigger_haystack:
            return candidate

    bindings = workflow.get("agent_bindings") or [
        _derive_agent_binding(node)
        for node in workflow["nodes"]
        if node["type"] == "agent" and _derive_agent_binding(node)
    ]
    binding_types = {_resolve_agent_type(str(binding)) for binding in bindings if binding}
    if "search" in binding_types:
        return "search"
    if "write" in binding_types:
        return "write"
    return "help"


def restart_workflow_run_for_task(
    task: dict,
    *,
    intent: str | None = None,
    trigger: str = "task.retry",
) -> dict:
    existing_run = None
    existing_run_id = str(task.get("workflow_run_id") or "").strip()
    if existing_run_id:
        _cancel_scheduled_run(existing_run_id)
        try:
            existing_run = _find_run(existing_run_id)
        except HTTPException:
            existing_run = None

    existing_steps = store.clone(store.task_steps.get(str(task.get("id") or ""), []))
    resolved_intent = _normalize_intent(intent)
    if not resolved_intent or resolved_intent == "manual":
        resolved_intent = infer_task_intent(task, run=existing_run, steps=existing_steps)
    workflow_id = str(task.get("workflow_id") or (existing_run or {}).get("workflow_id") or "").strip()
    workflow = None
    if workflow_id:
        try:
            workflow = _find_workflow(workflow_id)
        except HTTPException:
            workflow = None
    if workflow is None:
        workflow = _select_workflow_for_intent(resolved_intent)

    created_at = store.now_string()
    retry_dispatch_context = _clone_requeued_dispatch_context(existing_run, queued_at=created_at)
    if retry_dispatch_context is not None and not _dispatch_context_matches_retry_target(
        retry_dispatch_context,
        workflow_id=str(workflow["id"]),
        intent=resolved_intent,
    ):
        retry_dispatch_context.pop("routeDecision", None)
        retry_dispatch_context["route_decision"] = None
    task["status"] = "pending"
    task["priority"] = str(task.get("priority") or "medium")
    task["created_at"] = created_at
    task["completed_at"] = None
    task["agent"] = _agent_name_for_intent(resolved_intent)
    task["tokens"] = 0
    task["duration"] = None
    task["result"] = None
    task["workflow_id"] = workflow["id"]

    if existing_run is None:
        return create_workflow_run_for_task(
            task=task,
            intent=resolved_intent,
            trigger=trigger,
            memory_hits=0,
            warnings=[],
            workflow_id=str(workflow["id"]),
        )

    existing_run.update(
        {
            "workflow_id": workflow["id"],
            "workflow_name": workflow["name"],
            "task_id": task["id"],
            "trigger": trigger,
            "intent": resolved_intent,
            "status": task["status"],
            "created_at": created_at,
            "updated_at": created_at,
            "started_at": created_at,
            "completed_at": None,
            "next_dispatch_at": None,
            "dispatch_failure_count": 0,
            "last_dispatch_error": None,
            "dispatcher_id": None,
            "dispatch_claimed_at": None,
            "dispatch_lease_expires_at": None,
            "current_stage": "等待执行",
            "active_edges": [],
            "nodes": [],
            "logs": [],
            "dispatch_context": _build_run_dispatch_context(
                dispatch_context=retry_dispatch_context,
                workflow=workflow,
                created_at=created_at,
                default_type="workflow_dispatch",
                default_state="queued",
            ),
            "warnings": [],
        }
    )
    task["workflow_run_id"] = existing_run["id"]
    refreshed_run = _refresh_run_state(existing_run, task)
    _publish_run_event(refreshed_run, "workflow_run.updated")
    _persist_execution_state(
        task=task,
        steps=store.task_steps.get(str(task.get("id") or ""), []),
        run=refreshed_run,
    )
    return refreshed_run


def create_workflow_run_for_task(
    *,
    task: dict,
    intent: str,
    trigger: str,
    memory_hits: int,
    warnings: list[str],
    workflow_id: str | None = None,
    dispatch_context: dict | None = None,
) -> dict:
    workflow = _find_workflow(workflow_id) if workflow_id else _select_workflow_for_intent(intent)
    created_at = store.now_string()
    run_dispatch_context = _build_run_dispatch_context(
        dispatch_context=dispatch_context,
        workflow=workflow,
        created_at=created_at,
        default_type="workflow_dispatch",
        default_state="queued",
    )
    run = {
        "id": f"run-{uuid4().hex[:10]}",
        "workflow_id": workflow["id"],
        "workflow_name": workflow["name"],
        "task_id": task["id"],
        "trigger": trigger,
        "intent": intent,
        "status": task["status"],
        "created_at": created_at,
        "updated_at": created_at,
        "started_at": created_at,
        "completed_at": task.get("completed_at"),
        "next_dispatch_at": None,
        "dispatch_failure_count": 0,
        "last_dispatch_error": None,
        "current_stage": "等待执行",
        "active_edges": [],
        "nodes": [],
        "logs": [],
        "dispatch_context": run_dispatch_context,
        "memory_hits": memory_hits,
        "warnings": list(warnings),
    }
    run_dispatch_context["run_metrics"] = _normalize_run_metrics_payload(
        {
            "tokens_total": 0,
            "duration_ms": None,
            "step_count": len(store.task_steps.get(str(task.get("id") or ""), [])),
        }
    )
    store.workflow_runs.insert(0, run)
    task["workflow_id"] = workflow["id"]
    task["workflow_run_id"] = run["id"]
    refreshed_run = _refresh_run_state(run, task)
    _publish_run_event(refreshed_run, "workflow_run.created")
    _persist_execution_state(
        task=task,
        steps=store.task_steps.get(str(task.get("id") or ""), []),
        run=refreshed_run,
    )
    if task["status"] in {"pending", "running"} and not _task_confirmation_pending(task):
        _schedule_message_auto_progress(refreshed_run["id"])
    return refreshed_run


def create_agent_dispatch_run_for_task(
    *,
    task: dict,
    intent: str,
    trigger: str,
    memory_hits: int,
    warnings: list[str],
    dispatch_context: dict | None = None,
) -> dict:
    created_at = store.now_string()
    run_dispatch_context = _build_run_dispatch_context(
        dispatch_context=dispatch_context,
        workflow=None,
        created_at=created_at,
        default_type="agent_dispatch",
        default_state="agent_queued",
    )
    run = {
        "id": f"run-{uuid4().hex[:10]}",
        "workflow_id": AGENT_DISPATCH_WORKFLOW_ID,
        "workflow_name": AGENT_DISPATCH_WORKFLOW_NAME,
        "task_id": task["id"],
        "trigger": trigger,
        "intent": intent,
        "status": task["status"],
        "created_at": created_at,
        "updated_at": created_at,
        "started_at": created_at,
        "completed_at": task.get("completed_at"),
        "next_dispatch_at": None,
        "dispatch_failure_count": 0,
        "last_dispatch_error": None,
        "current_stage": "等待执行",
        "active_edges": [],
        "nodes": [],
        "logs": [],
        "dispatch_context": run_dispatch_context,
        "memory_hits": memory_hits,
        "warnings": list(warnings),
    }
    run_dispatch_context["run_metrics"] = _normalize_run_metrics_payload(
        {
            "tokens_total": 0,
            "duration_ms": None,
            "step_count": len(store.task_steps.get(str(task.get("id") or ""), [])),
        }
    )
    store.workflow_runs.insert(0, run)
    task["workflow_id"] = AGENT_DISPATCH_WORKFLOW_ID
    task["workflow_run_id"] = run["id"]
    refreshed_run = _refresh_run_state_without_workflow(run, task)
    _publish_run_event(refreshed_run, "workflow_run.created")
    _persist_execution_state(
        task=task,
        steps=store.task_steps.get(str(task.get("id") or ""), []),
        run=refreshed_run,
    )
    return refreshed_run


def _execute_agent_task_with_locked_failures(
    *,
    task: dict,
    run: dict,
    execution_agent: dict,
) -> tuple[dict | None, dict | None]:
    try:
        task_result = agent_execution_service.execute_task(
            task=task,
            run=run,
            execution_agent=execution_agent,
        )
    except Exception as exc:
        return None, _fail_workflow_run_due_agent_execution_error_locked(
            run,
            task,
            failure_message=_normalize_agent_execution_failure_message(exc),
        )
    if not _is_valid_task_result_payload(task_result):
        return None, _fail_workflow_run_due_agent_execution_error_locked(
            run,
            task,
            failure_message="Agent 执行结果不合格，主脑已拒收并准备回退",
        )
    return task_result, None


def _preview_execution_payload(value: object, *, limit: int = 1200) -> str:
    if value is None or value == "":
        return ""
    try:
        if isinstance(value, (dict, list)):
            rendered = json.dumps(value, ensure_ascii=False, indent=2, default=str)
        else:
            rendered = str(value)
    except Exception:
        rendered = str(value)
    return _truncate_text(rendered, limit=limit)


def _fail_workflow_run_due_execution_target_error_locked(
    *,
    task: dict,
    run: dict,
    steps: list[dict],
    failure_message: str,
    failure_stage: str = "execution",
) -> dict:
    recovered_run = _attempt_fallback_recovery_locked(
        task=task,
        run=run,
        failure_stage=failure_stage,
        failure_message=failure_message,
        state="failed",
        recovery_trigger=f"fallback.{failure_stage}_failure",
    )
    if recovered_run is not None:
        return recovered_run

    timestamp = store.now_string()
    running_step = next(
        (step for step in reversed(steps) if step.get("status") == "running"),
        None,
    )
    if running_step is not None:
        running_step["status"] = "failed"
        running_step["finished_at"] = timestamp
        running_step["message"] = failure_message
    else:
        _append_step(
            task_id=task["id"],
            title="执行失败",
            status="failed",
            agent="Workflow Execution Worker",
            message=failure_message,
            tokens=0,
        )

    task["status"] = "failed"
    task["completed_at"] = timestamp
    task["duration"] = task.get("duration") or "执行失败"
    task["result"] = None
    _append_assistant_conversation_message(
        task,
        channel_outbound_service.render_task_failure_text(task, failure_message),
    )
    _mark_dispatch_context_failure(
        run,
        state="failed",
        failure_stage=failure_stage,
        failure_message=failure_message,
    )
    refreshed_run = _refresh_run_state(run, task)
    _publish_run_event(refreshed_run, "workflow_run.updated")
    _persist_execution_state(task=task, steps=steps, run=refreshed_run)
    _cancel_scheduled_run(refreshed_run["id"])
    return refreshed_run


def _execute_tool_node_locked(
    *,
    task: dict,
    run: dict,
    steps: list[dict],
    node: dict,
) -> tuple[dict | None, dict | None]:
    tool_id = _derive_tool_binding(node)
    if not tool_id:
        return None, _fail_workflow_run_due_execution_target_error_locked(
            task=task,
            run=run,
            steps=steps,
            failure_message="工具节点未绑定可执行工具，任务已终止",
            failure_stage="dispatch",
        )

    runtime_response = mcp_runtime_service.invoke_tool(
        tool_id=tool_id,
        payload=_build_tool_payload(task=task, run=run, node=node),
        trace_context={
            "workflow_id": str(run.get("workflow_id") or ""),
            "workflow_run_id": str(run.get("id") or ""),
            "task_id": str(task.get("id") or ""),
            "node_id": str(node.get("id") or ""),
            "node_type": "tool",
        },
    )
    if not runtime_response.get("ok"):
        error = runtime_response.get("error") or {}
        failure_message = (
            str(error.get("message") or "").strip()
            or f"工具 {tool_id} 执行失败"
        )
        return None, _fail_workflow_run_due_execution_target_error_locked(
            task=task,
            run=run,
            steps=steps,
            failure_message=failure_message,
            failure_stage="execution",
        )

    tool_meta = runtime_response.get("tool") or {}
    tool_name = str(tool_meta.get("name") or _execution_node_label(node, fallback=tool_id)).strip()
    preview = _preview_execution_payload(runtime_response.get("result"))
    result_mapping = _node_config_text(node, "resultMapping", "result_mapping")
    node_description = str(node.get("description") or "").strip()
    content_parts = [preview or "工具调用已完成，但本次没有返回可展示的结构化结果。"]
    if result_mapping:
        content_parts.append(f"结果映射说明：{result_mapping}")
    elif node_description:
        content_parts.append(f"节点说明：{node_description}")
    task_result = {
        "kind": "tool_execution",
        "title": f"{tool_name} 执行结果",
        "summary": f"已完成工具调用：{tool_name}",
        "content": "\n\n".join(part for part in content_parts if part),
        "bullets": [
            f"工具 ID：{tool_id}",
            f"调用 Trace：{runtime_response.get('trace_id')}",
            *([f"结果映射：{result_mapping}"] if result_mapping else []),
        ],
        "orchestration_steps": [
            {
                "title": "工具调用",
                "status": "completed",
                "agent": tool_name,
                "message": f"已调用工具 {tool_name}（{tool_id}）并回收执行结果",
                "tokens": 0,
            }
        ],
    }
    return task_result, None


def _execute_workflow_node_locked(
    *,
    task: dict,
    run: dict,
    steps: list[dict],
    node: dict,
) -> tuple[dict | None, dict | None]:
    child_workflow_id = _derive_workflow_binding(node)
    if not child_workflow_id:
        return None, _fail_workflow_run_due_execution_target_error_locked(
            task=task,
            run=run,
            steps=steps,
            failure_message="子工作流节点未绑定目标工作流，任务已终止",
            failure_stage="dispatch",
        )

    child_workflow = _find_workflow(child_workflow_id)
    parent_dispatch_context = _run_dispatch_context(run) or {}
    workflow_call_stack = parent_dispatch_context.get("workflow_call_stack")
    normalized_stack = [str(item).strip() for item in workflow_call_stack or [] if str(item).strip()]
    current_workflow_id = str(run.get("workflow_id") or "").strip()
    next_stack = [*normalized_stack, *([current_workflow_id] if current_workflow_id else [])]
    handoff_note = _node_config_text(node, "handoffNote", "handoff_note")
    node_description = str(node.get("description") or "").strip()
    if child_workflow_id in next_stack:
        return None, _fail_workflow_run_due_execution_target_error_locked(
            task=task,
            run=run,
            steps=steps,
            failure_message=f"检测到子工作流循环引用：{child_workflow_id}",
            failure_stage="dispatch",
        )

    inherited_intent = _normalize_intent(run.get("intent"))
    if inherited_intent == "manual" or _selected_branch_node(child_workflow, inherited_intent) is None:
        inherited_intent = None

    child_bundle = create_manual_workflow_run(
        child_workflow_id,
        trigger=f"workflow:{current_workflow_id or 'parent'}:{str(node.get('id') or '').strip() or 'node'}",
        intent=inherited_intent,
        task_title=f"子工作流触发 - {child_workflow['name']}",
        task_description=_append_description_text(
            task.get("description") or child_workflow.get("description"),
            *(
                [
                    f"父流程节点说明：{node_description}",
                    f"父子流程交接说明：{handoff_note}",
                ]
                if handoff_note or node_description
                else []
            ),
        ),
        trigger_title="子工作流触发",
        trigger_agent=_execution_node_label(node, fallback="子工作流节点"),
        trigger_message=(
            f"父工作流 {current_workflow_id or '-'} 已触发子工作流 {child_workflow['name']}"
            + (f"；交接说明：{handoff_note}" if handoff_note else "")
        ),
    )
    child_run_id = str(child_bundle["run"]["id"] or "")
    _cancel_scheduled_run(child_run_id)
    child_run = _find_run(child_run_id)
    child_dispatch_context = _run_dispatch_context(child_run)
    if isinstance(child_dispatch_context, dict):
        child_dispatch_context["workflow_call_stack"] = next_stack
        child_dispatch_context["parent_workflow_id"] = current_workflow_id or None
        child_dispatch_context["parent_run_id"] = str(run.get("id") or "").strip() or None
        child_dispatch_context["parent_node_id"] = str(node.get("id") or "").strip() or None

    refreshed_child_run = child_run
    for _ in range(3):
        refreshed_child_run = _advance_workflow_run_locked(
            child_run_id,
            mode="tick",
            auto_schedule=False,
        )
        if str(refreshed_child_run.get("status") or "").strip().lower() in TERMINAL_TASK_STATUSES:
            break

    child_task = _find_task(refreshed_child_run.get("task_id"))
    if child_task is None:
        return None, _fail_workflow_run_due_execution_target_error_locked(
            task=task,
            run=run,
            steps=steps,
            failure_message=f"子工作流 {child_workflow['name']} 未生成可追踪任务",
            failure_stage="execution",
        )

    child_status = str(refreshed_child_run.get("status") or "").strip().lower()
    if child_status != "completed":
        child_failure_message = str(
            (_run_dispatch_context(refreshed_child_run) or {}).get("failure_message")
            or child_task.get("duration")
            or refreshed_child_run.get("current_stage")
            or "子工作流执行失败"
        ).strip()
        return None, _fail_workflow_run_due_execution_target_error_locked(
            task=task,
            run=run,
            steps=steps,
            failure_message=f"子工作流 {child_workflow['name']} 未完成：{child_failure_message}",
            failure_stage="execution",
        )

    child_result = store.clone(child_task.get("result"))
    if _is_valid_task_result_payload(child_result):
        child_result["summary"] = f"已通过子工作流“{child_workflow['name']}”完成执行"
        orchestration_steps = child_result.get("orchestration_steps")
        if not isinstance(orchestration_steps, list):
            orchestration_steps = []
            child_result["orchestration_steps"] = orchestration_steps
        if handoff_note:
            child_result.setdefault("bullets", [])
            if isinstance(child_result["bullets"], list):
                child_result["bullets"].append(f"交接说明：{handoff_note}")
        orchestration_steps.insert(
            0,
            {
                "title": "子工作流执行",
                "status": "completed",
                "agent": _execution_node_label(node, fallback="子工作流节点"),
                "message": f"已完成子工作流 {child_workflow['name']}（run={child_run_id}）",
                "tokens": 0,
            },
        )
        return child_result, None

    fallback_result = {
        "kind": "workflow_execution",
        "title": f"{child_workflow['name']} 执行完成",
        "summary": f"子工作流 {child_workflow['name']} 已完成",
        "content": (
            f"子工作流运行 ID：{child_run_id}\n"
            f"任务 ID：{child_task['id']}\n"
            f"当前阶段：{refreshed_child_run.get('current_stage') or '执行完成'}"
            + (f"\n交接说明：{handoff_note}" if handoff_note else "")
        ),
        "orchestration_steps": [
            {
                "title": "子工作流执行",
                "status": "completed",
                "agent": _execution_node_label(node, fallback="子工作流节点"),
                "message": f"已完成子工作流 {child_workflow['name']}（run={child_run_id}）",
                "tokens": 0,
            }
        ],
    }
    return fallback_result, None


def _trigger_display_name(trigger: str) -> str:
    normalized = str(trigger or "").strip().lower()
    if normalized.startswith("webhook:"):
        return "Webhook 触发"
    if normalized.startswith("schedule"):
        return "定时触发"
    if normalized.startswith("internal"):
        return "内部触发"
    if normalized.startswith("message"):
        return "消息触发"
    if normalized == "task.retry":
        return "任务重试"
    return "手动运行"


def create_manual_workflow_run(
    workflow_id: str,
    *,
    trigger: str = "manual",
    intent: str | None = None,
    task_title: str | None = None,
    task_description: str | None = None,
    trigger_title: str | None = None,
    trigger_agent: str = "Workflow Engine",
    trigger_message: str | None = None,
) -> dict:
    workflow = _find_workflow(workflow_id)
    task_id = _next_task_id()
    created_at = store.now_string()
    resolved_intent = _normalize_intent(intent)
    resolved_trigger_title = trigger_title or _trigger_display_name(trigger)
    task = {
        "id": task_id,
        "title": task_title or f"{resolved_trigger_title} - {workflow['name']}",
        "description": task_description or workflow["description"],
        "status": "running" if resolved_intent else "pending",
        "priority": "medium",
        "created_at": created_at,
        "completed_at": None,
        "agent": _agent_name_for_intent(resolved_intent),
        "tokens": 0,
        "duration": None,
        "result": None,
    }
    store.tasks.append(task)
    store.task_steps[task_id] = [
        {
            "id": f"{task_id}-1",
            "title": resolved_trigger_title,
            "status": "completed",
            "agent": trigger_agent,
            "started_at": created_at,
            "finished_at": created_at,
            "message": trigger_message or f"已创建工作流运行，触发方式 {trigger}",
            "tokens": 0,
        }
    ]
    mark_task_steps_authoritative(task_id)
    manual_dispatch_state = "dispatched" if resolved_intent else "queued"

    if resolved_intent:
        store.task_steps[task_id].append(
            {
                "id": f"{task_id}-2",
                "title": "Master Bot 路由",
                "status": "completed",
                "agent": "Dispatcher Agent",
                "started_at": created_at,
                "finished_at": created_at,
                "message": f"已手动指定意图: {resolved_intent}",
                "tokens": 16,
            }
        )
        store.task_steps[task_id].append(
            {
                "id": f"{task_id}-3",
                "title": "执行节点",
                "status": "running",
                "agent": _agent_name_for_intent(resolved_intent),
                "started_at": created_at,
                "finished_at": None,
                "message": f"已派发到 {_agent_name_for_intent(resolved_intent)} 等待执行",
                "tokens": 48,
            }
        )
        task["tokens"] = 64
    else:
        store.task_steps[task_id].append(
            {
                "id": f"{task_id}-2",
                "title": "等待执行策略",
                "status": "running",
                "agent": "Workflow Engine",
                "started_at": created_at,
                "finished_at": None,
                "message": "等待后续上下文、路由结果或手动 tick 推进",
                "tokens": 0,
            }
        )

    run = {
        "id": f"run-{uuid4().hex[:10]}",
        "workflow_id": workflow["id"],
        "workflow_name": workflow["name"],
        "task_id": task_id,
        "trigger": trigger,
        "intent": resolved_intent or "manual",
        "status": task["status"],
        "created_at": created_at,
        "updated_at": created_at,
        "started_at": created_at,
        "completed_at": None,
        "next_dispatch_at": None,
        "dispatch_failure_count": 0,
        "last_dispatch_error": None,
        "current_stage": "等待执行策略",
        "active_edges": [],
        "nodes": [],
        "logs": [],
        "dispatch_context": _build_run_dispatch_context(
            dispatch_context={
                "type": "manual_dispatch",
                "state": manual_dispatch_state,
                "queued_at": created_at,
            },
            workflow=workflow,
            created_at=created_at,
            default_type="manual_dispatch",
            default_state=manual_dispatch_state,
        ),
    }
    store.workflow_runs.insert(0, run)
    task["workflow_id"] = workflow["id"]
    task["workflow_run_id"] = run["id"]
    refreshed_run = _refresh_run_state(run, task)
    _publish_run_event(refreshed_run, "workflow_run.created")
    _persist_execution_state(
        task=task,
        steps=store.task_steps.get(task_id, []),
        run=refreshed_run,
    )
    if task["status"] in {"pending", "running"}:
        _schedule_manual_auto_progress(refreshed_run["id"])
    return {
        "task": store.clone(task),
        "run": refreshed_run,
        "workflow": store.clone(workflow),
    }


def list_workflow_runs(
    workflow_id: str | None = None,
    task_id: str | None = None,
    *,
    scope: dict[str, str] | None = None,
) -> dict:
    database_runs = persistence_service.list_workflow_runs(workflow_id=workflow_id, task_id=task_id)
    if database_runs is not None:
        items = [_apply_stored_run_metrics(store.clone(item)) for item in database_runs]
    elif getattr(persistence_service, "enabled", False):
        items = []
    else:
        items = [_apply_stored_run_metrics(store.clone(item)) for item in store.workflow_runs]
        if workflow_id:
            items = [item for item in items if item["workflow_id"] == workflow_id]
        if task_id:
            items = [item for item in items if item.get("task_id") == task_id]
    scoped_items = [attach_scope(item) for item in items]
    if scope is not None:
        scoped_items = [item for item in scoped_items if matches_scope(item, scope)]
    return {"items": scoped_items, "total": len(scoped_items)}


def get_workflow_run(run_id: str, *, scope: dict[str, str] | None = None) -> dict:
    run = _find_run(run_id)
    task = _find_task(run.get("task_id"))
    task_id = str(run.get("task_id") or "").strip()
    if task_id:
        _refresh_task_steps_from_database(task_id)
    if task:
        payload = attach_scope(_refresh_run_state(run, task))
    else:
        payload = attach_scope(_apply_stored_run_metrics(store.clone(run)))
    if scope is not None and not matches_scope(payload, scope):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow run not found")
    return payload


def append_context_patch_to_run(run_id: str, message_text: str, trace_id: str) -> dict:
    run = _find_run(run_id)
    task = _find_task(run.get("task_id"))
    if task is not None:
        _refresh_task_steps_from_database(task["id"])
    _apply_context_patch_to_dispatch_context(
        run,
        task=task,
        message_text=message_text,
        trace_id=trace_id,
    )
    if task:
        refreshed_run = _refresh_run_state(run, task)
        _publish_run_event(refreshed_run, "workflow_run.updated")
        _persist_execution_state(
            task=task,
            steps=_ensure_task_steps_loaded(task["id"]),
            run=refreshed_run,
        )
        if task["status"] in {"pending", "running"}:
            _schedule_follow_up(refreshed_run["id"])
        else:
            _cancel_scheduled_run(refreshed_run["id"])
        return refreshed_run
    _persist_execution_state(run=run)
    return store.clone(run)


def sync_workflow_run_from_task(task: dict) -> dict | None:
    run_id = task.get("workflow_run_id")
    if not run_id:
        return None
    run = _find_run(run_id)
    _refresh_task_steps_from_database(task["id"])
    try:
        refreshed_run = _refresh_run_state(run, task)
    except HTTPException as exc:
        if not _is_workflow_not_found(exc):
            raise
        refreshed_run = _refresh_run_state_without_workflow(run, task)
    _publish_run_event(refreshed_run, "workflow_run.updated")
    _persist_execution_state(
        task=task,
        steps=_ensure_task_steps_loaded(task["id"]),
        run=refreshed_run,
    )
    if task["status"] in {"pending", "running"} and not _task_confirmation_pending(task):
        _schedule_follow_up(refreshed_run["id"])
    else:
        _cancel_scheduled_run(refreshed_run["id"])
    return refreshed_run


def fail_workflow_run_due_dispatch_failure(run_id: str, *, failure_message: str) -> dict:
    with _TICK_LOCK:
        run = _find_run(run_id)
        task = _find_task(run.get("task_id"))
        if task is not None:
            _refresh_task_steps_from_database(task["id"])
        timestamp = store.now_string()

        if task is None:
            run["status"] = "failed"
            run["updated_at"] = timestamp
            run["completed_at"] = timestamp
            _mark_dispatch_context_failure(
                run,
                state="failed",
                failure_stage="dispatch",
                failure_message=failure_message,
            )
            _publish_run_event(store.clone(run), "workflow_run.updated")
            _persist_execution_state(run=run)
            _cancel_scheduled_run(run_id)
            return store.clone(run)

        if task["status"] in TERMINAL_TASK_STATUSES:
            _cancel_scheduled_run(run_id)
            try:
                refreshed_run = _refresh_run_state(run, task)
            except HTTPException as exc:
                if not _is_workflow_not_found(exc):
                    raise
                refreshed_run = _refresh_run_state_without_workflow(run, task)
            _persist_execution_state(
                task=task,
                steps=_ensure_task_steps_loaded(task["id"]),
                run=refreshed_run,
            )
            return refreshed_run

        recovered_run = _attempt_fallback_recovery_locked(
            task=task,
            run=run,
            failure_stage="dispatch",
            failure_message=failure_message,
            state="failed",
            recovery_trigger="fallback.dispatch_failure",
        )
        if recovered_run is not None:
            return recovered_run

        steps = _ensure_task_steps_loaded(task["id"])
        running_step = next(
            (step for step in reversed(steps) if step.get("status") == "running"),
            None,
        )
        if running_step is not None:
            running_step["status"] = "failed"
            running_step["finished_at"] = timestamp
            running_step["message"] = failure_message
        else:
            _append_step(
                task_id=task["id"],
                title="调度异常",
                status="failed",
                agent="Workflow Dispatcher",
                message=failure_message,
                tokens=0,
            )

        task["status"] = "failed"
        task["completed_at"] = timestamp
        task["duration"] = task.get("duration") or "调度失败"
        task["result"] = None
        _mark_dispatch_context_failure(
            run,
            state="failed",
            failure_stage="dispatch",
            failure_message=failure_message,
        )

        try:
            refreshed_run = _refresh_run_state(run, task)
        except HTTPException as exc:
            if not _is_workflow_not_found(exc):
                raise
            refreshed_run = _refresh_run_state_without_workflow(run, task)
        _publish_run_event(refreshed_run, "workflow_run.updated")
        _persist_execution_state(task=task, steps=steps, run=refreshed_run)
        _cancel_scheduled_run(refreshed_run["id"])
        return refreshed_run


def fail_workflow_run_due_execution_timeout(run_id: str, *, failure_message: str) -> dict:
    with _TICK_LOCK:
        run = _find_run(run_id)
        task = _find_task(run.get("task_id"))
        if task is not None:
            _refresh_task_steps_from_database(task["id"])
            recovered_run = _attempt_fallback_recovery_locked(
                task=task,
                run=run,
                failure_stage="execution",
                failure_message=failure_message,
                state="execution_timeout",
                recovery_trigger="fallback.execution_timeout",
            )
            if recovered_run is not None:
                return recovered_run
        timestamp = store.now_string()

        if task is None:
            run["status"] = "failed"
            run["updated_at"] = timestamp
            run["completed_at"] = timestamp
            _mark_dispatch_context_failure(
                run,
                state="execution_timeout",
                failure_stage="execution",
                failure_message=failure_message,
            )
            _publish_run_event(store.clone(run), "workflow_run.updated")
            _persist_execution_state(run=run)
            _cancel_scheduled_run(run_id)
            return store.clone(run)

        if task["status"] in TERMINAL_TASK_STATUSES:
            _cancel_scheduled_run(run_id)
            try:
                refreshed_run = _refresh_run_state(run, task)
            except HTTPException as exc:
                if not _is_workflow_not_found(exc):
                    raise
                refreshed_run = _refresh_run_state_without_workflow(run, task)
            _persist_execution_state(
                task=task,
                steps=_ensure_task_steps_loaded(task["id"]),
                run=refreshed_run,
            )
            return refreshed_run

        steps = _ensure_task_steps_loaded(task["id"])
        running_step = next(
            (step for step in reversed(steps) if step.get("status") == "running"),
            None,
        )
        if running_step is not None:
            running_step["status"] = "failed"
            running_step["finished_at"] = timestamp
            running_step["message"] = failure_message
        else:
            _append_step(
                task_id=task["id"],
                title="执行超时",
                status="failed",
                agent="Workflow Execution Worker",
                message=failure_message,
                tokens=0,
            )

        task["status"] = "failed"
        task["completed_at"] = timestamp
        task["duration"] = task.get("duration") or "执行超时"
        task["result"] = None
        _mark_dispatch_context_failure(
            run,
            state="execution_timeout",
            failure_stage="execution",
            failure_message=failure_message,
        )

        try:
            refreshed_run = _refresh_run_state(run, task)
        except HTTPException as exc:
            if not _is_workflow_not_found(exc):
                raise
            refreshed_run = _refresh_run_state_without_workflow(run, task)
        _publish_run_event(refreshed_run, "workflow_run.updated")
        _persist_execution_state(task=task, steps=steps, run=refreshed_run)
        _cancel_scheduled_run(refreshed_run["id"])
        return refreshed_run


def _fail_workflow_run_due_agent_execution_error_locked(
    run: dict,
    task: dict | None,
    *,
    failure_message: str,
) -> dict:
    if task is not None:
        _refresh_task_steps_from_database(task["id"])
        recovered_run = _attempt_fallback_recovery_locked(
            task=task,
            run=run,
            failure_stage="execution",
            failure_message=failure_message,
            state="agent_execution_failed",
            recovery_trigger="fallback.agent_execution_failed",
        )
        if recovered_run is not None:
            return recovered_run
    timestamp = store.now_string()

    if task is None:
        run["status"] = "failed"
        run["updated_at"] = timestamp
        run["completed_at"] = timestamp
        _mark_dispatch_context_failure(
            run,
            state="agent_execution_failed",
            failure_stage="execution",
            failure_message=failure_message,
        )
        _publish_run_event(store.clone(run), "workflow_run.updated")
        _persist_execution_state(run=run)
        _cancel_scheduled_run(str(run.get("id") or ""))
        return store.clone(run)

    if task["status"] in TERMINAL_TASK_STATUSES:
        _cancel_scheduled_run(str(run.get("id") or ""))
        try:
            refreshed_run = _refresh_run_state(run, task)
        except HTTPException as exc:
            if not _is_workflow_not_found(exc):
                raise
            refreshed_run = _refresh_run_state_without_workflow(run, task)
        _persist_execution_state(
            task=task,
            steps=_ensure_task_steps_loaded(task["id"]),
            run=refreshed_run,
        )
        return refreshed_run

    steps = _ensure_task_steps_loaded(task["id"])
    running_step = next(
        (step for step in reversed(steps) if step.get("status") == "running"),
        None,
    )
    if running_step is not None:
        running_step["status"] = "failed"
        running_step["finished_at"] = timestamp
        running_step["message"] = failure_message
    else:
        _append_step(
            task_id=task["id"],
            title="Agent 执行失败",
            status="failed",
            agent="Agent Execution Worker",
            message=failure_message,
            tokens=0,
        )

    task["status"] = "failed"
    task["completed_at"] = timestamp
    task["duration"] = task.get("duration") or "Agent 执行失败"
    task["result"] = None
    _mark_dispatch_context_failure(
        run,
        state="agent_execution_failed",
        failure_stage="execution",
        failure_message=failure_message,
    )

    try:
        refreshed_run = _refresh_run_state(run, task)
    except HTTPException as exc:
        if not _is_workflow_not_found(exc):
            raise
        refreshed_run = _refresh_run_state_without_workflow(run, task)
    _publish_run_event(refreshed_run, "workflow_run.updated")
    _persist_execution_state(task=task, steps=steps, run=refreshed_run)
    _cancel_scheduled_run(refreshed_run["id"])
    return refreshed_run


def fail_workflow_run_due_agent_execution_error(run_id: str, *, failure_message: str) -> dict:
    with _TICK_LOCK:
        run = _find_run(run_id)
        task = _find_task(run.get("task_id"))
        return _fail_workflow_run_due_agent_execution_error_locked(
            run,
            task,
            failure_message=failure_message,
        )


def _fail_workflow_run_due_unavailable_agent(
    task: dict,
    run: dict,
    steps: list[dict],
    *,
    failure_message: str,
    execution_agent: dict | None = None,
) -> dict:
    recovered_run = _attempt_fallback_recovery_locked(
        task=task,
        run=run,
        failure_stage="dispatch",
        failure_message=failure_message,
        state="failed",
        recovery_trigger="fallback.executor_unavailable",
    )
    if recovered_run is not None:
        return recovered_run

    timestamp = store.now_string()
    active_step = next((step for step in reversed(steps) if step.get("status") == "running"), None)
    if active_step is not None:
        active_step["status"] = "failed"
        active_step["finished_at"] = timestamp
        active_step["message"] = failure_message
    else:
        _append_step(
            task_id=task["id"],
            title="执行异常",
            status="failed",
            agent="Dispatcher Agent",
            message=failure_message,
            tokens=0,
        )

    task["status"] = "failed"
    task["completed_at"] = timestamp
    task["duration"] = task.get("duration") or "执行Agent不可用"
    task["result"] = None
    assistant_message = channel_outbound_service.render_task_failure_text(
        task,
        f"工作流推进失败，{failure_message}",
    )
    _append_assistant_conversation_message(task, assistant_message)
    _mark_dispatch_context_failure(
        run,
        state="failed",
        failure_stage="dispatch",
        failure_message=failure_message,
    )
    _mark_execution_agent_failed(execution_agent)
    refreshed_run = _refresh_run_state(run, task)
    _publish_run_event(refreshed_run, "workflow_run.updated")
    _persist_execution_state(task=task, steps=steps, run=refreshed_run)
    _cancel_scheduled_run(refreshed_run["id"])
    return refreshed_run


def _finalize_agent_task_result_locked(
    *,
    task: dict,
    run: dict,
    steps: list[dict],
    execution_step: dict,
    task_result: dict,
    execution_agent: dict | None,
) -> dict:
    orchestration_steps = task_result.pop("orchestration_steps", None)
    assistant_message = channel_outbound_service.render_task_result_text(task, task_result)
    delivery = _delivery_message_for_result(task, run, task_result)
    delivery_message = str(delivery.get("message") or "").strip()
    result_label = (
        str(task_result.get("title") or "").strip()
        or str(task_result.get("text") or "").strip()
        or str(task_result.get("summary") or "").strip()
        or str(task_result.get("content") or "").strip()
        or "对话回复"
    )
    _append_assistant_conversation_message(task, assistant_message)
    execution_step["status"] = "completed"
    execution_step["finished_at"] = store.now_string()
    execution_step["message"] = f"{execution_step['agent']} 已完成本轮执行，产出「{result_label}」"
    _append_orchestration_steps(task_id=task["id"], orchestration_steps=orchestration_steps)

    if not _find_step(steps, "发送结果", "输出", "回传"):
        _append_step(
            task_id=task["id"],
            title="发送结果",
            status="completed",
            agent="输出Agent",
            message=delivery_message,
            tokens=12,
        )

    task["status"] = "completed"
    task["completed_at"] = store.now_string()
    task["duration"] = task.get("duration") or "自动完成"
    task["tokens"] = sum(step.get("tokens", 0) for step in steps)
    task["agent"] = execution_step["agent"]
    task["result"] = task_result
    aggregation_contract = task_result.get("aggregation_contract")
    aggregation_notes = task_result.get("aggregation_notes")
    dispatch_context = _run_dispatch_context(run)
    if isinstance(dispatch_context, dict):
        if isinstance(aggregation_contract, dict):
            dispatch_context["aggregation_contract"] = store.clone(aggregation_contract)
        if isinstance(aggregation_notes, dict):
            dispatch_context["aggregation_notes"] = store.clone(aggregation_notes)
        dispatch_context["delivery_fact_context"] = _build_delivery_fact_context(
            task=task,
            run=run,
            delivery=delivery,
            task_result=task_result,
        )
        state_machine = dispatch_context.get("state_machine")
        if not isinstance(state_machine, dict):
            state_machine = {"version": "brain_fact_layer_v1"}
            dispatch_context["state_machine"] = state_machine
        if isinstance(aggregation_contract, dict):
            state_machine["coordination_mode"] = (
                str(aggregation_contract.get("mode") or "").strip() or None
            )
            state_machine["branch_results"] = store.clone(
                aggregation_contract.get("branch_results") or []
            )
            state_machine["successful_agents"] = int(
                aggregation_contract.get("successful_agents") or 0
            )
            state_machine["failed_agents"] = int(
                aggregation_contract.get("failed_agents") or 0
            )
            state_machine["cancelled_agents"] = int(
                aggregation_contract.get("cancelled_agents") or 0
            )
        if isinstance(aggregation_notes, dict):
            state_machine["selected_branch_id"] = (
                str(aggregation_notes.get("selected_branch_id") or "").strip() or None
            )
            state_machine["selected_agent"] = (
                str(aggregation_notes.get("selected_agent") or "").strip() or None
            )
    _mark_dispatch_context_state(
        run,
        "completed",
        completed_at=task["completed_at"],
        result_kind=str(task_result.get("kind") or "").strip() or None,
    )
    _record_delivery_state(run, delivery, preserve_failure=False)
    _mark_execution_agent_succeeded(execution_agent, tokens_used=task["tokens"])
    refreshed_run = _refresh_run_state(run, task)
    _publish_run_event(refreshed_run, "workflow_run.updated")
    _persist_execution_state(task=task, steps=steps, run=refreshed_run)
    _cancel_scheduled_run(refreshed_run["id"])
    return refreshed_run


def _queue_agent_execution_locked(
    *,
    task: dict,
    run: dict,
    steps: list[dict],
    workflow: dict,
    execution_step: dict,
) -> dict | None:
    from app.services.agent_execution_worker_service import agent_execution_worker_service

    dispatch_context = _run_dispatch_context(run)
    dispatch_state = _dispatch_context_state(dispatch_context)
    if dispatch_state in {"agent_queued", "executing"}:
        return _refresh_run_state(run, task)

    execution_agent = _resolve_dispatch_execution_agent(workflow, run, run.get("intent"))
    if execution_agent is None:
        return _fail_workflow_run_due_unavailable_agent(
            task,
            run,
            steps,
            failure_message="选定工作流缺少可用的执行 Agent，任务已终止",
        )

    queued = agent_execution_worker_service.enqueue_execution(
        run_id=str(run.get("id") or ""),
        task_id=str(task.get("id") or ""),
        workflow_id=str(workflow.get("id") or ""),
        execution_agent_id=str(execution_agent.get("id") or "").strip() or None,
        step_delay=_workflow_step_delay_for_run(str(run.get("id") or "")),
        published_at=store.now_string(),
    )
    if not queued:
        return None

    execution_step["message"] = (
        f"{execution_step['agent']} 已进入 Agent 执行队列，等待 Worker 认领"
    )
    _mark_dispatch_context_state(
        run,
        "agent_queued",
        agent_execution_queued_at=store.now_string(),
        execution_agent_id=str(execution_agent.get("id") or "").strip() or None,
        execution_agent=str(execution_agent.get("name") or "").strip() or execution_step["agent"],
    )
    refreshed_run = _refresh_run_state(run, task)
    _publish_run_event(refreshed_run, "workflow_run.updated")
    _persist_execution_state(task=task, steps=steps, run=refreshed_run)
    return refreshed_run


def _sync_execute_agent_locked(
    *,
    task: dict,
    run: dict,
    steps: list[dict],
    workflow: dict,
    execution_step: dict,
) -> dict:
    execution_agent = _resolve_dispatch_execution_agent(workflow, run, run.get("intent"))
    if execution_agent is None:
        return _fail_workflow_run_due_unavailable_agent(
            task,
            run,
            steps,
            failure_message="选定工作流缺少可用的执行 Agent，任务已终止",
        )
    task_result, failure_run = _execute_agent_task_with_locked_failures(
        task=task,
        run=run,
        execution_agent=execution_agent,
    )
    if failure_run is not None:
        return failure_run
    return _finalize_agent_task_result_locked(
        task=task,
        run=run,
        steps=steps,
        execution_step=execution_step,
        task_result=task_result,
        execution_agent=execution_agent,
    )


def _refresh_terminal_workflow_run_locked(
    run_id: str,
    *,
    run: dict,
    task: dict,
    steps: list[dict],
) -> dict:
    _cancel_scheduled_run(run_id)
    try:
        refreshed_run = _refresh_run_state(run, task)
    except HTTPException as exc:
        if not _is_workflow_not_found(exc):
            raise
        refreshed_run = _refresh_run_state_without_workflow(run, task)
    _persist_execution_state(task=task, steps=steps, run=refreshed_run)
    return refreshed_run


def _dispatch_workflow_run_locked(
    *,
    task: dict,
    run: dict,
    steps: list[dict],
    workflow: dict,
    auto_schedule: bool,
) -> dict:
    if _task_confirmation_pending(task):
        return _refresh_confirmation_pending_run_locked(run=run, task=task)
    resolved_intent = _resolve_tick_intent(run, workflow)
    run["intent"] = resolved_intent
    selected_node = _selected_branch_node(workflow, resolved_intent)
    if selected_node is None or not _workflow_has_execution_target(workflow, run, resolved_intent):
        return _fail_workflow_run_due_unavailable_agent(
            task,
            run,
            steps,
            failure_message="选定工作流缺少可执行节点，任务已终止",
        )

    selected_node_type = _normalize_workflow_node_type(selected_node.get("type"))
    execution_agent = None
    execution_target_id = None
    execution_target_name = _execution_node_label(selected_node, fallback="执行节点")
    if selected_node_type == "agent":
        execution_agent = _resolve_dispatch_execution_agent(workflow, run, resolved_intent)
        if execution_agent is None:
            return _fail_workflow_run_due_unavailable_agent(
                task,
                run,
                steps,
                failure_message="选定工作流缺少可用的执行 Agent，任务已终止",
            )
        execution_target_id = str(execution_agent.get("id") or "").strip() or _derive_agent_binding(selected_node)
        execution_target_name = (
            str(execution_agent.get("name") or "").strip()
            or _execution_node_label(selected_node, fallback=_agent_name_for_intent(resolved_intent))
        )
    elif selected_node_type == "tool":
        execution_target_id = _derive_tool_binding(selected_node)
    elif selected_node_type == "workflow":
        execution_target_id = _derive_workflow_binding(selected_node)

    task["status"] = "running"
    task["agent"] = execution_target_name

    waiting_step = next((step for step in reversed(steps) if step.get("status") == "running"), None)
    if waiting_step:
        waiting_step["status"] = "completed"
        waiting_step["finished_at"] = store.now_string()
        waiting_step["message"] = (
            f"Dispatcher 已接管 dispatch context，准备派发到 "
            f"{execution_target_name}"
        )

    if not _find_step(steps, "安全", "网关"):
        _append_step(
            task_id=task["id"],
            title="安全网关",
            status="completed",
            agent="安全网关",
            message="自动执行前已完成安全校验",
            tokens=12,
        )

    if not _find_step(steps, "意图", "路由", "Master Bot"):
        _append_step(
            task_id=task["id"],
            title="Master Bot 路由",
            status="completed",
            agent="Dispatcher Agent",
            message=f"已确定执行意图: {resolved_intent}",
            tokens=18,
        )

    _append_step(
        task_id=task["id"],
        title="执行节点",
        status="running",
        agent=execution_target_name,
        message=f"已按 dispatch context 派发到 {execution_target_name} 执行",
        tokens=64,
    )
    dispatch_context = _run_dispatch_context(run)
    if isinstance(dispatch_context, dict):
        selected_node_config = _node_config(selected_node)
        dispatch_context["selected_node_id"] = str(selected_node.get("id") or "").strip() or None
        dispatch_context["selected_node_label"] = execution_target_name
        dispatch_context["selected_node_type"] = selected_node_type
        dispatch_context["selected_node_description"] = str(
            selected_node.get("description") or ""
        ).strip() or None
        dispatch_context["selected_node_config"] = selected_node_config or None
    _mark_dispatch_context_state(
        run,
        "dispatched",
        dispatched_at=store.now_string(),
        execution_agent_id=(str(execution_agent.get("id") or "").strip() or None) if execution_agent else None,
        execution_agent=execution_target_name,
        execution_target_type=selected_node_type,
        execution_target_id=execution_target_id,
        execution_target=execution_target_name,
    )
    if execution_agent is not None:
        _mark_execution_agent_started(execution_agent)
    task["tokens"] = sum(step.get("tokens", 0) for step in steps)
    refreshed_run = _refresh_run_state(run, task)
    _publish_run_event(refreshed_run, "workflow_run.updated")
    _persist_execution_state(task=task, steps=steps, run=refreshed_run)
    if auto_schedule:
        if str(run.get("trigger") or "") == "task.retry":
            _schedule_retry_follow_up(refreshed_run["id"])
        else:
            _schedule_follow_up(refreshed_run["id"])
    return refreshed_run


def _execute_running_workflow_run_locked(
    *,
    task: dict,
    run: dict,
    steps: list[dict],
    workflow: dict,
    execution_step: dict,
    allow_async_agent_queue: bool,
) -> dict:
    selected_node = _selected_branch_node(workflow, run.get("intent"))
    selected_node_type = _normalize_workflow_node_type((selected_node or {}).get("type"))

    if selected_node_type == "tool" and selected_node is not None:
        task_result, failure_run = _execute_tool_node_locked(
            task=task,
            run=run,
            steps=steps,
            node=selected_node,
        )
        if failure_run is not None:
            return failure_run
        return _finalize_agent_task_result_locked(
            task=task,
            run=run,
            steps=steps,
            execution_step=execution_step,
            task_result=task_result,
            execution_agent=None,
        )

    if selected_node_type == "workflow" and selected_node is not None:
        task_result, failure_run = _execute_workflow_node_locked(
            task=task,
            run=run,
            steps=steps,
            node=selected_node,
        )
        if failure_run is not None:
            return failure_run
        return _finalize_agent_task_result_locked(
            task=task,
            run=run,
            steps=steps,
            execution_step=execution_step,
            task_result=task_result,
            execution_agent=None,
        )

    if allow_async_agent_queue:
        queued_run = _queue_agent_execution_locked(
            task=task,
            run=run,
            steps=steps,
            workflow=workflow,
            execution_step=execution_step,
        )
        if queued_run is not None:
            return queued_run
    return _sync_execute_agent_locked(
        task=task,
        run=run,
        steps=steps,
        workflow=workflow,
        execution_step=execution_step,
    )


def _finalize_completed_execution_locked(
    *,
    task: dict,
    run: dict,
    steps: list[dict],
    workflow: dict,
) -> dict:
    task_result = task.get("result")
    if task_result is None:
        execution_agent = _resolve_dispatch_execution_agent(workflow, run, run.get("intent"))
        if execution_agent is None:
            return _fail_workflow_run_due_unavailable_agent(
                task,
                run,
                steps,
                failure_message="选定工作流缺少可用的执行 Agent，任务已终止",
            )
        task_result, failure_run = _execute_agent_task_with_locked_failures(
            task=task,
            run=run,
            execution_agent=execution_agent,
        )
        if failure_run is not None:
            return failure_run
    else:
        execution_agent = _resolve_dispatch_execution_agent(workflow, run, run.get("intent"))
    orchestration_steps = task_result.pop("orchestration_steps", None)
    assistant_message = channel_outbound_service.render_task_result_text(task, task_result)
    delivery = _delivery_message_for_result(task, run, task_result)
    delivery_message = str(delivery.get("message") or "").strip()
    _append_assistant_conversation_message(task, assistant_message)
    _append_orchestration_steps(task_id=task["id"], orchestration_steps=orchestration_steps)
    if not _find_step(steps, "发送结果", "输出", "回传"):
        _append_step(
            task_id=task["id"],
            title="发送结果",
            status="completed",
            agent="输出Agent",
            message=delivery_message,
            tokens=12,
        )
    task["status"] = "completed"
    task["completed_at"] = store.now_string()
    task["duration"] = task.get("duration") or "自动完成"
    task["tokens"] = sum(step.get("tokens", 0) for step in steps)
    task["result"] = task_result
    dispatch_context = _run_dispatch_context(run)
    if isinstance(dispatch_context, dict):
        dispatch_context["delivery_fact_context"] = _build_delivery_fact_context(
            task=task,
            run=run,
            delivery=delivery,
            task_result=task_result,
        )
    _mark_dispatch_context_state(
        run,
        "completed",
        completed_at=task["completed_at"],
        result_kind=str(task_result.get("kind") or "").strip() or None,
    )
    _record_delivery_state(run, delivery, preserve_failure=False)
    refreshed_run = _refresh_run_state(run, task)
    _publish_run_event(refreshed_run, "workflow_run.updated")
    _persist_execution_state(task=task, steps=steps, run=refreshed_run)
    _cancel_scheduled_run(refreshed_run["id"])
    return refreshed_run


def _advance_workflow_run_locked(
    run_id: str,
    *,
    mode: str,
    auto_schedule: bool = True,
) -> dict:
    run = _find_run(run_id)
    task = _find_task(run.get("task_id"))
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    _refresh_task_steps_from_database(task["id"])
    steps = _ensure_task_steps_loaded(task["id"])

    if task["status"] in TERMINAL_TASK_STATUSES:
        return _refresh_terminal_workflow_run_locked(
            run_id,
            run=run,
            task=task,
            steps=steps,
        )
    if _task_confirmation_pending(task):
        return _refresh_confirmation_pending_run_locked(run=run, task=task)

    workflow = _find_workflow(run["workflow_id"])
    selected_node = _selected_branch_node(workflow, run.get("intent"))
    execution_step = _execution_step_for_node(steps, selected_node)

    if execution_step is None:
        dispatched_run = _dispatch_workflow_run_locked(
            task=task,
            run=run,
            steps=steps,
            workflow=workflow,
            auto_schedule=(auto_schedule if mode == "tick" else False),
        )
        if mode in {"dispatch", "tick"}:
            return dispatched_run

        selected_node = _selected_branch_node(workflow, run.get("intent"))
        execution_step = _execution_step_for_node(steps, selected_node)

    if mode == "dispatch":
        return _refresh_run_state(run, task)

    if execution_step and execution_step.get("status") == "running":
        return _execute_running_workflow_run_locked(
            task=task,
            run=run,
            steps=steps,
            workflow=workflow,
            execution_step=execution_step,
            allow_async_agent_queue=(mode == "execute"),
        )

    if execution_step and execution_step.get("status") == "completed" and task["status"] != "completed":
        return _finalize_completed_execution_locked(
            task=task,
            run=run,
            steps=steps,
            workflow=workflow,
        )

    if mode != "tick":
        return _refresh_run_state(run, task)

    task["status"] = "failed"
    task["completed_at"] = store.now_string()
    task["result"] = None
    assistant_message = channel_outbound_service.render_task_failure_text(
        task,
        "工作流推进失败，缺少可执行节点",
    )
    delivery = _delivery_message_for_failure(task, run, "工作流推进失败，缺少可执行节点")
    delivery_message = str(delivery.get("message") or "").strip()
    _append_assistant_conversation_message(task, assistant_message)
    _mark_dispatch_context_failure(
        run,
        state="failed",
        failure_stage="dispatch",
        failure_message="工作流推进失败，缺少可执行节点",
    )
    dispatch_context = _run_dispatch_context(run)
    if isinstance(dispatch_context, dict):
        dispatch_context["delivery_fact_context"] = _build_delivery_fact_context(
            task=task,
            run=run,
            delivery=delivery,
        )
    _record_delivery_state(run, delivery)
    _append_step(
        task_id=task["id"],
        title="执行异常",
        status="failed",
        agent=task["agent"],
        message=delivery_message,
        tokens=0,
    )
    _mark_execution_agent_failed(
        resolve_workflow_execution_agent(
            workflow,
            run.get("intent"),
            route_seed=_execution_route_seed(
                run=run,
                workflow=workflow,
                agent_type=INTENT_AGENT_TYPE_MAP.get(run.get("intent")),
            ),
        )
    )
    refreshed_run = _refresh_run_state(run, task)
    _publish_run_event(refreshed_run, "workflow_run.updated")
    _persist_execution_state(task=task, steps=steps, run=refreshed_run)
    _cancel_scheduled_run(refreshed_run["id"])
    return refreshed_run


def dispatch_workflow_run(run_id: str) -> dict:
    with _TICK_LOCK:
        return _advance_workflow_run_locked(run_id, mode="dispatch", auto_schedule=False)


def execute_workflow_run(run_id: str) -> dict:
    with _TICK_LOCK:
        return _advance_workflow_run_locked(run_id, mode="execute", auto_schedule=False)


def tick_workflow_run(run_id: str, *, auto_schedule: bool = True) -> dict:
    with _TICK_LOCK:
        return _advance_workflow_run_locked(run_id, mode="tick", auto_schedule=auto_schedule)


def request_manual_handoff_for_workflow_run(
    run_id: str,
    *,
    operator: str | None = None,
    note: str | None = None,
) -> dict:
    with _TICK_LOCK:
        run = _find_run(run_id)
        task = _find_task(run.get("task_id"))
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        _refresh_task_steps_from_database(task["id"])
        dispatch_context = _run_dispatch_context(run)
        return _enter_manual_handoff_locked(
            task=task,
            run=run,
            failure_stage=str(dispatch_context.get("failure_stage") or "manual_review"),
            failure_message=str(note or "运行已转入人工接管，等待人工确认").strip(),
            state="manual_handoff_requested",
            reason="human_review_required",
            handoff_source="operator_request",
            operator=operator,
            note=note,
        )


def complete_agent_execution_job(run_id: str, *, execution_agent_id: str | None = None) -> dict:
    with _TICK_LOCK:
        run = _find_run(run_id)
        task = _find_task(run.get("task_id"))
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        _refresh_task_steps_from_database(task["id"])
        steps = _ensure_task_steps_loaded(task["id"])

        if task["status"] in TERMINAL_TASK_STATUSES:
            return _refresh_terminal_workflow_run_locked(
                run_id,
                run=run,
                task=task,
                steps=steps,
            )

        workflow = None if _is_agent_dispatch_run(run) else _find_workflow(run["workflow_id"])
        selected_node = _selected_branch_node(workflow, run.get("intent")) if workflow else None
        execution_step = (
            _execution_step_for_node(steps, selected_node)
            if workflow
            else next(
                (
                    step
                    for step in reversed(steps)
                    if str(step.get("title") or "").strip() == "执行节点"
                ),
                None,
            )
        )
        if execution_step is None:
            return _fail_workflow_run_due_unavailable_agent(
                task,
                run,
                steps,
                failure_message="执行节点不存在，任务已终止",
            )

        execution_agent = None
        if execution_agent_id:
            execution_agent = _find_agent_mutable(execution_agent_id)
        if execution_agent is None:
            if workflow is not None:
                execution_agent = _resolve_dispatch_execution_agent(workflow, run, run.get("intent"))
            else:
                dispatch_context = _run_dispatch_context(run)
                dispatch_execution_agent_id = _dispatch_context_execution_agent_id(dispatch_context)
                selected_agent_type = INTENT_AGENT_TYPE_MAP.get(_normalize_intent(run.get("intent")))
                if dispatch_execution_agent_id:
                    execution_agent = _resolve_agent_binding(
                        dispatch_execution_agent_id,
                        expected_type=selected_agent_type,
                        route_seed=_execution_route_seed(
                            run=run,
                            agent_type=selected_agent_type,
                        ),
                    )
                if execution_agent is None:
                    execution_agent = resolve_agent_dispatch_execution_agent(
                        run.get("intent"),
                        route_seed=_execution_route_seed(
                            run=run,
                            agent_type=selected_agent_type,
                        ),
                    )
        if execution_agent is None:
            return _fail_workflow_run_due_unavailable_agent(
                task,
                run,
                steps,
                failure_message=(
                    "Agent dispatch 缺少可用的执行 Agent，任务已终止"
                    if workflow is None
                    else "选定工作流缺少可用的执行 Agent，任务已终止"
                ),
            )

        _mark_dispatch_context_state(
            run,
            "executing",
            agent_execution_started_at=store.now_string(),
            execution_agent_id=str(execution_agent.get("id") or "").strip() or None,
            execution_agent=str(execution_agent.get("name") or "").strip() or execution_step["agent"],
        )
        execution_step["message"] = f"{execution_step['agent']} 已被 Agent Worker 认领并开始执行"
        refreshed_run = _refresh_run_state(run, task)
        _publish_run_event(refreshed_run, "workflow_run.updated")
        _persist_execution_state(task=task, steps=steps, run=refreshed_run)
        task_result, failure_run = _execute_agent_task_with_locked_failures(
            task=task,
            run=run,
            execution_agent=execution_agent,
        )
        if failure_run is not None:
            return failure_run
        return _finalize_agent_task_result_locked(
            task=task,
            run=run,
            steps=steps,
            execution_step=execution_step,
            task_result=task_result,
            execution_agent=execution_agent,
        )
