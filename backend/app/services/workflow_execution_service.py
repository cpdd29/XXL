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
from app.services.mandatory_agent_registry_service import (
    get_mandatory_agent_projection,
    list_mandatory_agent_projections,
)
from app.services.tenancy_service import attach_scope, matches_scope
from app.services.agent_service import is_agent_routable, routing_priority
from app.services.channel_outbound_service import channel_outbound_service
from app.services.document_search_service import document_search_service
from app.services.language_service import detect_language
from app.services.mandatory_workflow_registry_service import (
    CONVERSATION_AGENT_PIPELINE_WORKFLOW_ID,
    FOUNDATION_BRAIN_WORKFLOW_ID,
    FREE_AGENT_WORKFLOW_ID,
    GENERAL_ASSISTANT_AGENT_PIPELINE_WORKFLOW_ID,
    PROFESSIONAL_AGENT_WORKFLOW_ID,
    REQUIREMENT_DISPATCH_AGENT_PIPELINE_WORKFLOW_ID,
    SECURITY_AGENT_PIPELINE_WORKFLOW_ID,
)
from app.services.memory_service import memory_service
from app.services.mcp_runtime_service import mcp_runtime_service
from app.services.mandatory_workflow_module_registry_service import foundation_workflow_module_specs
from app.services.persistence_service import persistence_service
from app.services.trace_exporter_service import trace_exporter_service
from app.services.workflow_scheduler_service import workflow_scheduler_service
from app.services.workflow_realtime_service import workflow_realtime_service
from app.services.store import LEGACY_WORKFLOW_IDS as REMOVED_WORKFLOW_IDS, store

LABEL_AGENT_TYPE_MAP = {
    "安全检测": "security",
    "意图识别": "intent",
    "对话 Agent": "conversation",
    "万事通 Agent": "default",
    "需求分析任务分发 Agent": "task_dispatcher",
    "搜索 Agent": "search",
    "写作 Agent": "write",
    "发送结果": "output",
}
KNOWN_AGENT_TYPES = {"security", "intent", "conversation", "task_dispatcher", "search", "write", "output", "default"}
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
LIGHT_CLOSED_LOOP_TRIGGER_CAPABILITIES = {
    "web_search",
    "live_information_lookup",
    "information_retrieval",
    "weather_lookup",
    "task_status_lookup",
    "task_listing",
    "pdf_processing",
    "document_conversion",
    "schedule_intent_detection",
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
    "default": ("万事通", "答疑", "查询"),
    "task_dispatcher": ("分发", "路由", "执行意图"),
    "search": ("搜索", "检索", "知识库"),
    "write": ("写作", "回复", "生成"),
    "output": ("发送结果", "输出", "回传"),
}
ACTIVE_NODE_STATUSES = {"completed", "running", "waiting", "error"}
TERMINAL_TASK_STATUSES = {"completed", "failed", "cancelled"}
FOUNDATION_MODULE_WORKFLOW_IDS = {
    str(spec.get("id") or "").strip()
    for spec in foundation_workflow_module_specs()
    if str(spec.get("id") or "").strip()
}
LEGACY_ROUTE_DISABLED_WORKFLOW_IDS = set(REMOVED_WORKFLOW_IDS)
ROUTE_SELECTION_FALLBACK_WORKFLOW_IDS = (
    FOUNDATION_BRAIN_WORKFLOW_ID,
)
SEQUENTIAL_WORKFLOW_IDS = {
    FOUNDATION_BRAIN_WORKFLOW_ID,
    CONVERSATION_AGENT_PIPELINE_WORKFLOW_ID,
    GENERAL_ASSISTANT_AGENT_PIPELINE_WORKFLOW_ID,
    REQUIREMENT_DISPATCH_AGENT_PIPELINE_WORKFLOW_ID,
    SECURITY_AGENT_PIPELINE_WORKFLOW_ID,
    FREE_AGENT_WORKFLOW_ID,
    PROFESSIONAL_AGENT_WORKFLOW_ID,
    *FOUNDATION_MODULE_WORKFLOW_IDS,
}
PROFESSIONAL_DELIVERY_NOTE_EXPORT_WORKFLOW_ID = PROFESSIONAL_AGENT_WORKFLOW_ID
PROFESSIONAL_DELIVERY_NOTE_EXPORT_WORKFLOW_NAME = "专业agent工作流"
PROFESSIONAL_DELIVERY_NOTE_EXPORT_SCENARIO_ID = "professional_agent_workflow"
PROFESSIONAL_DELIVERY_NOTE_HINTS = (
    "送货单",
    "送货单号",
    "发货单",
    "delivery note",
    "delivery order",
    "已出路由",
)
PROFESSIONAL_EXPORT_HINTS = ("导出", "pdf", "export")
PROFESSIONAL_CUSTOMER_DELIVERY_HINTS = (
    "发送给客户",
    "发给客户",
    "发送客户",
    "给客户",
    "send to customer",
    "customer",
)
PROFESSIONAL_SYSTEM_NAVIGATION_HINTS = (
    "http://121.12.144.243",
    "登录",
    "网址",
    "页面",
    "列表",
    "路由",
)


def _is_legacy_route_disabled_workflow_id(value: object) -> bool:
    return str(value or "").strip() in LEGACY_ROUTE_DISABLED_WORKFLOW_IDS


def _is_foundation_module_workflow_id(value: object) -> bool:
    return str(value or "").strip() in FOUNDATION_MODULE_WORKFLOW_IDS


def _preferred_route_selection_workflow(workflows: list[dict]) -> dict | None:
    for workflow_id in ROUTE_SELECTION_FALLBACK_WORKFLOW_IDS:
        for workflow in workflows:
            if str(workflow.get("id") or "").strip() == workflow_id:
                return workflow
    return workflows[0] if workflows else None


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
AGENT_FATAL_FAILURE_USER_MESSAGE = "当前系统出错请立即联系管理员处理！"
AGENT_FATAL_RISK_TITLE = "风险与安全"
_TICK_LOCK = Lock()
logger = logging.getLogger(__name__)
AUTHORITATIVE_TASK_STEP_CACHE: set[str] = set()
SECURITY_PIPELINE_OUTPUT_NODE_ID = "7"
SECURITY_PIPELINE_NODE_ID_TO_NEXT: dict[str, str] = {
    "2": "3",
    "3": "4",
    "4": "5",
    "5": "6",
    "6": "7",
}
SECURITY_PIPELINE_NODE_ID_TO_LABEL: dict[str, str] = {
    "2": "限流",
    "3": "认证 / RBAC 权限校验",
    "4": "Prompt Injection 双检",
    "5": "内容策略 / 数据脱敏改写",
    "6": "审计追踪",
    "7": "安全结果输出",
}
SECURITY_PIPELINE_NODE_ID_TO_LAYER: dict[str, str] = {
    "2": "rate_limit",
    "3": "auth_rbac",
    "4": "prompt_injection",
    "5": "content_policy_rewrite",
    "6": "audit_trace",
}
SECURITY_PIPELINE_GATE_BLOCK_OUTPUT_NODE_IDS = {"2", "3", "4"}


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


def _should_eager_start_in_local_fallback() -> bool:
    return not getattr(persistence_service, "enabled", False)


def _is_security_agent_pipeline_workflow(
    *,
    workflow: dict | None = None,
    run: dict | None = None,
) -> bool:
    workflow_id = str((workflow or {}).get("id") or (run or {}).get("workflow_id") or "").strip()
    return workflow_id == SECURITY_AGENT_PIPELINE_WORKFLOW_ID


def _is_professional_agent_workflow(
    *,
    workflow: dict | None = None,
    run: dict | None = None,
) -> bool:
    workflow_id = str((workflow or {}).get("id") or (run or {}).get("workflow_id") or "").strip()
    return workflow_id == PROFESSIONAL_AGENT_WORKFLOW_ID


def _is_free_agent_workflow(
    *,
    workflow: dict | None = None,
    run: dict | None = None,
) -> bool:
    workflow_id = str((workflow or {}).get("id") or (run or {}).get("workflow_id") or "").strip()
    return workflow_id == FREE_AGENT_WORKFLOW_ID


def _normalize_security_pipeline_layer(value: object) -> str | None:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    if normalized in {"auth_scope_rbac", "auth_rbac"}:
        return "auth_rbac"
    if normalized in {"content_policy_rewrite", "content_policy"}:
        return "content_policy_rewrite"
    if normalized in {"security_pass", "allow"}:
        return None
    return normalized


def _security_pipeline_runtime_input(run: dict) -> dict[str, Any]:
    dispatch_context = _ensure_run_dispatch_context(run)
    payload = dispatch_context.get("internal_event_payload")
    payload = payload if isinstance(payload, dict) else {}
    request_context = payload.get("request_context") or payload.get("requestContext")
    request_context = request_context if isinstance(request_context, dict) else {}
    security_context = payload.get("security_context") or payload.get("securityContext")
    security_context = security_context if isinstance(security_context, dict) else {}
    tenant_context = payload.get("tenant_context") or payload.get("tenantContext")
    tenant_context = tenant_context if isinstance(tenant_context, dict) else {}

    text = (
        alias_text(payload, "normalized_message", "normalizedMessage", "text", "message", "input", "query")
        or alias_text(
            dispatch_context,
            "normalized_message",
            "normalizedMessage",
            "message_preview",
            "messagePreview",
        )
        or alias_text(request_context, "message_text", "messageText", "text", "input")
        or ""
    )
    auth_scope = (
        alias_text(payload, "auth_scope", "authScope")
        or alias_text(security_context, "auth_scope", "authScope")
        or alias_text(dispatch_context, "auth_scope", "authScope")
        or "messages:ingest"
    )
    user_key = (
        alias_text(payload, "user_key", "userKey")
        or alias_text(security_context, "user_key", "userKey")
        or (
            f"{str(request_context.get('channel') or '').strip()}:{str(request_context.get('platform_user_id') or request_context.get('platformUserId') or '').strip()}"
            if str(request_context.get("channel") or "").strip()
            and str(request_context.get("platform_user_id") or request_context.get("platformUserId") or "").strip()
            else None
        )
        or f"internal:{str(dispatch_context.get('internal_event_id') or run.get('id') or 'security-pipeline').strip()}"
    )
    return {
        "payload": store.clone(payload),
        "request_context": store.clone(request_context),
        "security_context": store.clone(security_context),
        "tenant_context": store.clone(tenant_context),
        "text": str(text or ""),
        "auth_scope": str(auth_scope or "messages:ingest"),
        "user_key": str(user_key or ""),
    }


def _security_pipeline_snapshot_candidate(candidate: object) -> dict[str, Any] | None:
    if not isinstance(candidate, dict):
        return None
    if "allowed" not in candidate and not isinstance(candidate.get("security_verdict"), dict):
        return None
    return store.clone(candidate)


def _apply_security_pipeline_snapshot_to_dispatch_context(
    *,
    run: dict,
    snapshot: dict[str, Any],
    runtime_input: dict[str, Any],
) -> None:
    dispatch_context = _ensure_run_dispatch_context(run)
    dispatch_context["security_pipeline_snapshot"] = store.clone(snapshot)
    dispatch_context["trace_id"] = str(snapshot.get("trace_id") or "").strip() or None
    dispatch_context["audit_trace_id"] = str(snapshot.get("audit_trace_id") or "").strip() or None
    dispatch_context["auth_scope"] = str(snapshot.get("auth_scope") or runtime_input.get("auth_scope") or "").strip() or None
    dispatch_context["normalized_message"] = str(runtime_input.get("text") or "").strip()
    if runtime_input["request_context"]:
        dispatch_context["request_context"] = store.clone(runtime_input["request_context"])
    if runtime_input["tenant_context"]:
        dispatch_context["tenant_context"] = store.clone(runtime_input["tenant_context"])

    security_context = (
        store.clone(runtime_input["security_context"])
        if isinstance(runtime_input.get("security_context"), dict)
        else {}
    )
    security_context.update(
        {
            "trace_id": str(snapshot.get("trace_id") or "").strip() or None,
            "audit_trace_id": str(snapshot.get("audit_trace_id") or "").strip() or None,
            "auth_scope": str(snapshot.get("auth_scope") or runtime_input.get("auth_scope") or "").strip() or None,
            "user_key": str(snapshot.get("user_key") or runtime_input.get("user_key") or "").strip() or None,
            "allowed": bool(snapshot.get("allowed")),
            "allowed_message": str(snapshot.get("allowed_message") or "").strip() or None,
            "sanitized_text": str(snapshot.get("sanitized_text") or runtime_input.get("text") or "").strip(),
            "warning_count": int(snapshot.get("warning_count") or len(snapshot.get("warnings") or [])),
            "rewrite_diffs_count": int(
                snapshot.get("rewrite_diffs_count") or len(snapshot.get("rewrite_diffs") or [])
            ),
            "prompt_injection_assessment": store.clone(
                snapshot.get("prompt_injection_assessment") or {}
            ),
            "security_verdict": store.clone(snapshot.get("security_verdict") or {}),
            "detail": str(snapshot.get("detail") or "").strip() or None,
        }
    )
    dispatch_context["security_context"] = security_context


def _ensure_security_pipeline_snapshot(run: dict) -> dict[str, Any]:
    runtime_input = _security_pipeline_runtime_input(run)
    dispatch_context = _ensure_run_dispatch_context(run)
    payload = runtime_input.get("payload")
    payload = payload if isinstance(payload, dict) else {}

    snapshot = _security_pipeline_snapshot_candidate(dispatch_context.get("security_pipeline_snapshot"))
    if snapshot is None:
        snapshot = _security_pipeline_snapshot_candidate(payload.get("security_pipeline_snapshot"))
    if snapshot is None:
        snapshot = _security_pipeline_snapshot_candidate(payload.get("security_snapshot"))
    if snapshot is None:
        snapshot = _security_pipeline_snapshot_candidate(payload.get("security_result"))
    if snapshot is None:
        from app.services.security_gateway_service import security_gateway_service

        snapshot = security_gateway_service.inspect_text_entrypoint_snapshot(
            text=str(runtime_input.get("text") or ""),
            user_key=str(runtime_input.get("user_key") or ""),
            auth_scope=str(runtime_input.get("auth_scope") or "messages:ingest"),
        )

    _apply_security_pipeline_snapshot_to_dispatch_context(
        run=run,
        snapshot=snapshot,
        runtime_input=runtime_input,
    )
    return snapshot


def _security_pipeline_blocked_layer(snapshot: dict[str, Any]) -> str | None:
    security_verdict = snapshot.get("security_verdict")
    if isinstance(security_verdict, dict):
        blocked_layer = _normalize_security_pipeline_layer(security_verdict.get("layer"))
        if blocked_layer:
            return blocked_layer
    trace = snapshot.get("trace")
    if isinstance(trace, dict):
        blocked_layer = _normalize_security_pipeline_layer(trace.get("layer"))
        if blocked_layer:
            return blocked_layer
    return None


def _execute_security_pipeline_condition_node(
    *,
    run: dict,
    node: dict,
) -> tuple[dict[str, Any], str, str | None]:
    snapshot = _ensure_security_pipeline_snapshot(run)
    node_id = str(node.get("id") or "").strip()
    current_layer = SECURITY_PIPELINE_NODE_ID_TO_LAYER.get(node_id)
    next_node_id = SECURITY_PIPELINE_NODE_ID_TO_NEXT.get(node_id)
    blocked_layer = _security_pipeline_blocked_layer(snapshot)
    is_blocked_here = bool(blocked_layer and blocked_layer == current_layer)
    if is_blocked_here and node_id in SECURITY_PIPELINE_GATE_BLOCK_OUTPUT_NODE_IDS:
        next_node_id = SECURITY_PIPELINE_OUTPUT_NODE_ID

    next_label = SECURITY_PIPELINE_NODE_ID_TO_LABEL.get(str(next_node_id or "").strip())
    label = _execution_node_label(node, fallback="安全条件节点")
    if is_blocked_here:
        message = f"{label} 已拦截请求，进入 安全结果输出"
    elif next_label:
        message = f"{label} 已放行，进入 {next_label}"
    else:
        message = f"{label} 已完成判断"

    return (
        {
            "gate": current_layer,
            "allowed": not is_blocked_here,
            "blocked_layer": blocked_layer,
            "next_node_id": next_node_id,
            "audit_trace_id": str(snapshot.get("audit_trace_id") or "").strip() or None,
            "security_verdict": store.clone(snapshot.get("security_verdict") or {}),
        },
        message,
        next_node_id,
    )


def _execute_security_pipeline_transform_node(
    *,
    run: dict,
    node: dict,
) -> tuple[dict[str, Any], str] | None:
    if not _is_security_agent_pipeline_workflow(run=run):
        return None

    snapshot = _ensure_security_pipeline_snapshot(run)
    node_id = str(node.get("id") or "").strip()
    if node_id == "5":
        rewrite_diffs = store.clone(snapshot.get("rewrite_diffs") or [])
        allowed_message = str(
            snapshot.get("allowed_message") or snapshot.get("sanitized_text") or ""
        ).strip() or None
        if rewrite_diffs:
            message = "已完成内容策略 / 数据脱敏改写，产出安全文本"
        else:
            message = "已完成内容策略校验，无需额外改写"
        return (
            {
                "allowed": bool(snapshot.get("allowed")),
                "allowed_message": allowed_message,
                "sanitized_text": str(snapshot.get("sanitized_text") or "").strip(),
                "warnings": store.clone(snapshot.get("warnings") or []),
                "warning_count": int(snapshot.get("warning_count") or 0),
                "rewrite_diffs": rewrite_diffs,
                "rewrite_diffs_count": int(snapshot.get("rewrite_diffs_count") or len(rewrite_diffs)),
            },
            message,
        )

    if node_id == "6":
        return (
            {
                "audit_trace_id": str(snapshot.get("audit_trace_id") or "").strip() or None,
                "trace": store.clone(snapshot.get("trace") or {}),
                "security_verdict": store.clone(snapshot.get("security_verdict") or {}),
            },
            "已完成审计追踪，保留安全证据并准备输出",
        )

    return None


def _build_security_pipeline_output_result(task: dict, run: dict, node: dict) -> dict[str, Any]:
    del task
    snapshot = _ensure_security_pipeline_snapshot(run)
    dispatch_context = _ensure_run_dispatch_context(run)
    security_context = dispatch_context.get("security_context")
    security_context = security_context if isinstance(security_context, dict) else {}
    security_verdict = store.clone(snapshot.get("security_verdict") or {})
    allowed = bool(snapshot.get("allowed"))
    label = _execution_node_label(node, fallback="安全结果输出")
    allowed_message = str(
        snapshot.get("allowed_message") or snapshot.get("sanitized_text") or ""
    ).strip() or None
    blocked_detail = str(
        snapshot.get("detail") or (security_verdict.get("detail") if isinstance(security_verdict, dict) else "")
    ).strip()
    if allowed:
        summary = "安全链路已放行请求"
        content = allowed_message or "安全链路已完成放行。"
    else:
        summary = "安全链路已拦截请求"
        content = blocked_detail or "安全链路已完成拦截。"

    return {
        "kind": "security_review",
        "title": label,
        "summary": summary,
        "content": content,
        "text": content,
        "allowed": allowed,
        "allowed_message": allowed_message if allowed else None,
        "security_verdict": security_verdict,
        "security_context": store.clone(security_context),
        "rewrite_diffs_count": int(snapshot.get("rewrite_diffs_count") or 0),
        "warning_count": int(snapshot.get("warning_count") or 0),
        "audit_trace_id": str(snapshot.get("audit_trace_id") or "").strip() or None,
        "trace_id": str(snapshot.get("trace_id") or "").strip() or None,
        "auth_scope": str(snapshot.get("auth_scope") or "").strip() or None,
        "prompt_injection_assessment": store.clone(snapshot.get("prompt_injection_assessment") or {}),
        "rewrite_diffs": store.clone(snapshot.get("rewrite_diffs") or []),
        "warnings": store.clone(snapshot.get("warnings") or []),
        "status_code": int(snapshot.get("status_code") or (status.HTTP_200_OK if allowed else status.HTTP_403_FORBIDDEN)),
        "detail": blocked_detail or None,
    }


def _eager_progress_workflow_run(
    run_id: str,
    *,
    follow_up_scheduler,
) -> dict:
    run = _find_run(run_id)
    workflow = _find_workflow(str(run.get("workflow_id") or ""))
    max_iterations = max(len(workflow.get("nodes") or []) * 6, 6)
    latest_run = run

    for _ in range(max_iterations):
        if str(latest_run.get("status") or "").strip().lower() in TERMINAL_TASK_STATUSES:
            break
        latest_run = tick_workflow_run(run_id, auto_schedule=False)
        if _task_confirmation_pending(_find_task(str(latest_run.get("task_id") or ""))):
            break

    if (
        str(latest_run.get("status") or "").strip().lower() not in TERMINAL_TASK_STATUSES
        and not _task_confirmation_pending(_find_task(str(latest_run.get("task_id") or "")))
    ):
        follow_up_scheduler(run_id)

    return latest_run


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


def _ensure_runtime_workflow_placeholder(*, run: dict, task: dict | None = None) -> dict | None:
    workflow_id = str(run.get("workflow_id") or (task or {}).get("workflow_id") or "").strip()
    if not workflow_id:
        return None
    try:
        return _find_workflow(workflow_id)
    except HTTPException as exc:
        if exc.status_code != status.HTTP_404_NOT_FOUND or exc.detail != "Workflow not found":
            raise
        if getattr(persistence_service, "enabled", False):
            raise

    workflow_name = (
        str(run.get("workflow_name") or "").strip()
        or str((task or {}).get("workflow_name") or "").strip()
        or workflow_id
    )
    placeholder = {
        "id": workflow_id,
        "name": workflow_name,
        "description": str((task or {}).get("description") or "").strip() or workflow_name,
        "version": "runtime-placeholder",
        "status": "active",
        "updated_at": store.now_string(),
        "node_count": 0,
        "edge_count": 0,
        "trigger": {"type": str(run.get("trigger") or "manual").strip() or "manual"},
        "nodes": [],
        "edges": [],
    }
    store.workflows.append(placeholder)
    return _find_cached_workflow(workflow_id)


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
    if getattr(persistence_service, "enabled", False):
        for projection in list_mandatory_agent_projections(existing_agents=list(merged.values())):
            agent_id = str(projection.get("id") or "").strip()
            if not agent_id or agent_id in merged:
                continue
            merged[agent_id] = store.clone(projection)

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
            projection = None
            if getattr(persistence_service, "enabled", False):
                existing = next(
                    (
                        agent
                        for agent in store.agents
                        if str(agent.get("id") or "").strip() == normalized_agent_id
                    ),
                    None,
                )
                projection = get_mandatory_agent_projection(
                    normalized_agent_id,
                    existing=existing,
                )
            if projection is None:
                return None
            payload = store.clone(projection)
            for agent in store.agents:
                if str(agent.get("id") or "") != normalized_agent_id:
                    continue
                agent.clear()
                agent.update(payload)
                return agent

            store.agents.append(payload)
            return payload
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
    direct_binding = _normalize_node_binding(
        node.get("workflow_id")
        or node.get("workflowId")
        or node.get("sub_workflow_id")
        or node.get("subWorkflowId")
        or node.get("target_workflow_id")
        or node.get("targetWorkflowId")
    )
    if direct_binding:
        return direct_binding
    return _node_config_text(
        node,
        "workflowId",
        "workflow_id",
        "subWorkflowId",
        "sub_workflow_id",
        "targetWorkflowId",
        "target_workflow_id",
    )


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


def _node_config_list(node: dict | None, *keys: str) -> list[str]:
    config = _node_config(node)
    for key in keys:
        value = config.get(key)
        if isinstance(value, list):
            normalized = [str(item).strip() for item in value if str(item).strip()]
            if normalized:
                return normalized
            continue
        if value in {None, ""}:
            continue
        normalized = str(value).strip()
        if normalized:
            return [normalized]
    return []


def _normalize_condition_fact_token(value: object) -> str | None:
    raw = str(value or "").strip().lower()
    if not raw:
        return None

    normalized = "".join(char if char.isalnum() else "_" for char in raw)
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    normalized = normalized.strip("_")
    return normalized or None


def _sync_selected_node_context(
    run: dict,
    *,
    node: dict | None,
    label_override: str | None = None,
) -> None:
    if not isinstance(node, dict):
        return

    dispatch_context = _ensure_run_dispatch_context(run)
    dispatch_context["selected_node_id"] = str(node.get("id") or "").strip() or None
    dispatch_context["selected_node_label"] = (
        str(label_override or "").strip() or _execution_node_label(node, fallback="执行节点")
    )
    dispatch_context["selected_node_type"] = _normalize_workflow_node_type(node.get("type"))
    dispatch_context["selected_node_description"] = str(node.get("description") or "").strip() or None
    selected_node_config = _node_config(node)
    dispatch_context["selected_node_config"] = selected_node_config or None


def _append_description_text(base_text: str | None, *extra_lines: str | None) -> str | None:
    parts = [str(base_text or "").strip()]
    parts.extend(str(line or "").strip() for line in extra_lines)
    normalized = [part for part in parts if part]
    return "\n".join(normalized) if normalized else None


def _workflow_parent_result_summary_line(task: dict | None) -> str | None:
    if not isinstance(task, dict):
        return None
    current_result = task.get("result")
    if not isinstance(current_result, dict):
        return None
    preview = _normalize_free_text(
        alias_text(current_result, "summary", "title", "text", "content") or ""
    )
    if not preview:
        return None
    return f"父流程当前结果摘要：{_truncate_text(preview, 180)}"


def _workflow_upstream_result(
    *,
    task: dict | None = None,
    run: dict | None = None,
) -> dict[str, Any] | None:
    task_result = (task or {}).get("result") if isinstance(task, dict) else None
    if _is_valid_task_result_payload(task_result):
        return store.clone(task_result)

    dispatch_context = _run_dispatch_context(run)
    if not isinstance(dispatch_context, dict):
        return None

    workflow_return = dispatch_context.get("workflow_return") or dispatch_context.get("workflowReturn")
    if isinstance(workflow_return, dict):
        for key in ("return_payload", "returnPayload"):
            candidate = workflow_return.get(key)
            if _is_valid_task_result_payload(candidate):
                return store.clone(candidate)

    internal_event_payload = (
        dispatch_context.get("internal_event_payload") or dispatch_context.get("internalEventPayload")
    )
    if isinstance(internal_event_payload, dict):
        for key in (
            "final_result_payload",
            "finalResultPayload",
            "upstream_result",
            "upstreamResult",
        ):
            candidate = internal_event_payload.get(key)
            if _is_valid_task_result_payload(candidate):
                return store.clone(candidate)

    return None


def _workflow_child_input_payload(task: dict, run: dict) -> dict[str, Any] | None:
    result_payload = _workflow_upstream_result(task=task, run=run)
    if not _is_valid_task_result_payload(result_payload):
        return None

    preview_text = (
        str(result_payload.get("summary") or "").strip()
        or str(result_payload.get("text") or "").strip()
        or str(result_payload.get("content") or "").strip()
        or str(result_payload.get("title") or "").strip()
    ) or None
    handoff_target = alias_text(result_payload, "handoff_target", "handoffTarget")
    conversation_stage = alias_text(result_payload, "conversation_stage", "conversationStage")
    result_status = (
        alias_text(result_payload, "result_status", "resultStatus")
        or str(task.get("status") or run.get("status") or "completed").strip().lower()
    )
    if result_status not in TERMINAL_TASK_STATUSES:
        result_status = "completed"

    source_workflow_id = str(run.get("workflow_id") or "").strip() or None
    source_run_id = str(run.get("id") or "").strip() or None
    return {
        "input_source": "final_result",
        "inputSource": "final_result",
        "upstream_result": store.clone(result_payload),
        "upstreamResult": store.clone(result_payload),
        "final_result_payload": store.clone(result_payload),
        "finalResultPayload": store.clone(result_payload),
        "final_result_text": preview_text,
        "finalResultText": preview_text,
        "handoff_target": handoff_target,
        "handoffTarget": handoff_target,
        "conversation_stage": conversation_stage,
        "conversationStage": conversation_stage,
        "result_status": result_status,
        "resultStatus": result_status,
        "source_workflow_id": source_workflow_id,
        "sourceWorkflowId": source_workflow_id,
        "source_run_id": source_run_id,
        "sourceRunId": source_run_id,
    }


def _normalize_free_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _contains_any_text_hint(text: str, hints: tuple[str, ...]) -> bool:
    return any(hint in text for hint in hints if hint)


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


def _workflow_relation_type(node: dict | None) -> str:
    normalized = str((node or {}).get("type") or "").strip().lower()
    if normalized == "trigger_workflow":
        return "trigger_workflow"
    return "sub_workflow"


def _build_workflow_trigger_payload(*, task: dict, run: dict, node: dict) -> dict[str, object]:
    request_text = _primary_request_text(task)
    base_payload: dict[str, object] = {
        "input": request_text,
        "query": request_text,
        "text": request_text,
        "task_id": str(task.get("id") or ""),
        "workflow_run_id": str(run.get("id") or ""),
        "workflow_id": str(run.get("workflow_id") or ""),
        "workflow_name": str(run.get("workflow_name") or ""),
        "node_id": str(node.get("id") or ""),
        "node_label": _execution_node_label(node, fallback="工作流节点"),
        "intent": str(run.get("intent") or ""),
        "trigger": str(run.get("trigger") or ""),
    }
    payload_template = _node_config_text(node, "triggerPayload", "trigger_payload")
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
        "input": rendered_text,
        "query": rendered_text,
        "text": rendered_text,
        "payload_template": payload_template,
    }


def _workflow_trigger_payload_preview(trigger_payload: dict[str, object]) -> str | None:
    if not trigger_payload:
        return None
    preview = _preview_execution_payload(trigger_payload, limit=220)
    return preview or None


def _workflow_child_trigger(
    *,
    relation_type: str,
    parent_workflow_id: str | None,
    parent_node_id: str | None,
) -> str:
    prefix = "trigger_workflow" if relation_type == "trigger_workflow" else "workflow"
    return (
        f"{prefix}:"
        f"{str(parent_workflow_id or '').strip() or 'parent'}:"
        f"{str(parent_node_id or '').strip() or 'node'}"
    )


def _append_workflow_relation_to_run(
    run: dict,
    *,
    relation_type: str,
    source_node: dict,
    target_workflow: dict,
    target_run: dict,
    target_task: dict | None,
    handoff_note: str | None = None,
    trigger_payload: dict[str, object] | None = None,
    execution_instance_key: str | None = None,
    source_attempt: int | None = None,
) -> None:
    dispatch_context = _ensure_run_dispatch_context(run)
    relations = dispatch_context.setdefault("workflow_relations", [])
    if not isinstance(relations, list):
        relations = []
        dispatch_context["workflow_relations"] = relations

    normalized_execution_instance_key = str(execution_instance_key or "").strip() or None
    relation_id = (
        f"{relation_type}:{str(source_node.get('id') or '').strip()}:"
        f"{normalized_execution_instance_key or str(target_run.get('id') or '').strip()}"
    )
    relation_payload = {
        "id": relation_id,
        "relation_type": relation_type,
        "source_node_id": str(source_node.get("id") or "").strip() or None,
        "source_node_label": _execution_node_label(source_node, fallback="工作流节点"),
        "source_attempt": max(int(source_attempt or 0), 0) or None,
        "execution_instance_key": normalized_execution_instance_key,
        "target_workflow_id": str(target_workflow.get("id") or "").strip(),
        "target_workflow_name": str(target_workflow.get("name") or "").strip() or None,
        "target_run_id": str(target_run.get("id") or "").strip() or None,
        "target_task_id": str((target_task or {}).get("id") or "").strip() or None,
        "target_status": str(target_run.get("status") or "").strip() or None,
        "trigger": str(target_run.get("trigger") or "").strip() or None,
        "handoff_note": str(handoff_note or "").strip() or None,
        "payload_preview": _workflow_trigger_payload_preview(trigger_payload or {}),
        "created_at": str(target_run.get("created_at") or store.now_string()).strip(),
        "updated_at": store.now_string(),
    }

    existing_index = next(
        (
            index
            for index, item in enumerate(relations)
            if isinstance(item, dict) and str(item.get("id") or "").strip() == relation_id
        ),
        None,
    )
    if existing_index is None:
        relations.append(relation_payload)
        return
    relations[existing_index] = relation_payload


def _build_workflow_result_handoff_payloads(
    *,
    result: dict[str, Any],
    source_run: dict | None,
    source_task: dict | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized_result = store.clone(result)
    handoff_target = alias_text(normalized_result, "handoff_target", "handoffTarget")
    conversation_stage = alias_text(normalized_result, "conversation_stage", "conversationStage")
    result_status = (
        alias_text(normalized_result, "result_status", "resultStatus")
        or str((source_task or {}).get("status") or (source_run or {}).get("status") or "completed").strip().lower()
    )
    preview_text = (
        str(normalized_result.get("summary") or "").strip()
        or str(normalized_result.get("text") or "").strip()
        or str(normalized_result.get("content") or "").strip()
        or str(normalized_result.get("title") or "").strip()
    ) or None
    source_workflow_id = str((source_run or {}).get("workflow_id") or "").strip() or None
    source_run_id = str((source_run or {}).get("id") or "").strip() or None
    payload_snapshot = store.clone(normalized_result)

    internal_event_payload = {
        "input_source": "final_result",
        "inputSource": "final_result",
        "upstream_result": store.clone(payload_snapshot),
        "upstreamResult": store.clone(payload_snapshot),
        "final_result_payload": store.clone(payload_snapshot),
        "finalResultPayload": store.clone(payload_snapshot),
        "final_result_text": preview_text,
        "finalResultText": preview_text,
        "handoff_target": handoff_target,
        "handoffTarget": handoff_target,
        "conversation_stage": conversation_stage,
        "conversationStage": conversation_stage,
        "result_status": result_status,
        "resultStatus": result_status,
        "source_workflow_id": source_workflow_id,
        "sourceWorkflowId": source_workflow_id,
        "source_run_id": source_run_id,
        "sourceRunId": source_run_id,
    }
    workflow_return = {
        "input_source": "final_result",
        "inputSource": "final_result",
        "handoff_target": handoff_target,
        "handoffTarget": handoff_target,
        "conversation_stage": conversation_stage,
        "conversationStage": conversation_stage,
        "result_status": result_status,
        "resultStatus": result_status,
        "return_payload": store.clone(payload_snapshot),
        "returnPayload": store.clone(payload_snapshot),
        "summary": preview_text,
        "source_workflow_id": source_workflow_id,
        "sourceWorkflowId": source_workflow_id,
        "source_run_id": source_run_id,
        "sourceRunId": source_run_id,
    }
    return internal_event_payload, workflow_return


def _promote_child_workflow_result_to_parent_run(
    *,
    parent_run: dict,
    child_run: dict,
    child_task: dict,
    child_result: dict[str, Any],
) -> None:
    parent_dispatch_context = _ensure_run_dispatch_context(parent_run)
    internal_event_payload, workflow_return = _build_workflow_result_handoff_payloads(
        result=child_result,
        source_run=child_run,
        source_task=child_task,
    )
    parent_dispatch_context["internal_event_payload"] = store.clone(internal_event_payload)
    parent_dispatch_context["input_source"] = "final_result"
    parent_dispatch_context["inputSource"] = "final_result"
    parent_dispatch_context["workflow_return"] = workflow_return
    parent_dispatch_context["workflowReturn"] = store.clone(workflow_return)

    parent_route_decision = _dispatch_context_route_decision(parent_dispatch_context)
    if isinstance(parent_route_decision, dict):
        handoff_target = alias_text(workflow_return, "handoff_target", "handoffTarget")
        conversation_stage = alias_text(workflow_return, "conversation_stage", "conversationStage")
        parent_route_decision["handoff_target"] = handoff_target
        parent_route_decision["handoffTarget"] = handoff_target
        parent_route_decision["conversation_stage"] = conversation_stage
        parent_route_decision["conversationStage"] = conversation_stage


def _inherit_child_dispatch_context_to_parent_run(*, parent_run: dict, child_run: dict) -> None:
    parent_dispatch_context = _ensure_run_dispatch_context(parent_run)
    child_dispatch_context = _run_dispatch_context(child_run)
    if not isinstance(child_dispatch_context, dict):
        return

    professional_selection = child_dispatch_context.get("professional_workflow_selection")
    if isinstance(professional_selection, dict):
        parent_dispatch_context["professional_workflow_selection"] = store.clone(professional_selection)
        parent_route_decision = _dispatch_context_route_decision(parent_dispatch_context)
        if isinstance(parent_route_decision, dict):
            workflow_id = str(professional_selection.get("workflow_id") or "").strip() or None
            workflow_name = str(professional_selection.get("workflow_name") or "").strip() or None
            scenario_id = str(professional_selection.get("scenario_id") or "").strip() or None
            route_reason = str(professional_selection.get("route_reason_summary") or "").strip() or None
            parent_route_decision["specialized_workflow_id"] = workflow_id
            parent_route_decision["specializedWorkflowId"] = workflow_id
            parent_route_decision["specialized_workflow_name"] = workflow_name
            parent_route_decision["specializedWorkflowName"] = workflow_name
            parent_route_decision["specialized_workflow_selector"] = scenario_id
            parent_route_decision["specializedWorkflowSelector"] = scenario_id
            if route_reason:
                parent_route_decision["route_reason_summary"] = route_reason
                parent_route_decision["routeReasonSummary"] = route_reason

    for key in ("acceptance", "outbound_review"):
        value = child_dispatch_context.get(key)
        if isinstance(value, dict):
            parent_dispatch_context[key] = store.clone(value)


def _sync_parent_workflow_relation_from_child_run(
    *,
    run: dict,
    task: dict | None,
) -> None:
    dispatch_context = _run_dispatch_context(run)
    parent_run_id = _workflow_parent_run_id(dispatch_context)
    if not parent_run_id:
        return

    child_run_id = str(run.get("id") or "").strip()
    if not child_run_id:
        return

    try:
        parent_run = _find_run(parent_run_id)
    except HTTPException:
        return

    parent_dispatch_context = _run_dispatch_context(parent_run)
    if not isinstance(parent_dispatch_context, dict):
        return

    relations = parent_dispatch_context.get("workflow_relations")
    if not isinstance(relations, list):
        return

    child_status = str(run.get("status") or "").strip() or None
    child_task_id = str((task or {}).get("id") or run.get("task_id") or "").strip() or None
    timestamp = store.now_string()
    updated = False

    for relation in relations:
        if not isinstance(relation, dict):
            continue
        target_run_id = str(relation.get("target_run_id") or relation.get("targetRunId") or "").strip()
        if target_run_id != child_run_id:
            continue
        relation["target_status"] = child_status
        relation["updated_at"] = timestamp
        if child_task_id:
            relation["target_task_id"] = child_task_id
        updated = True

    if not updated:
        return

    parent_task = _find_task(parent_run.get("task_id"))
    if parent_task is not None:
        _persist_execution_state(
            task=parent_task,
            steps=_ensure_task_steps_loaded(parent_task["id"]),
            run=parent_run,
        )
    else:
        _persist_execution_state(run=parent_run)
    _publish_run_event(parent_run, "workflow_run.updated")


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
    context["parent_workflow_id"] = alias_text(context, "parent_workflow_id", "parentWorkflowId")
    context["parent_workflow_name"] = alias_text(context, "parent_workflow_name", "parentWorkflowName")
    context["parent_run_id"] = alias_text(context, "parent_run_id", "parentRunId")
    context["parent_node_id"] = alias_text(context, "parent_node_id", "parentNodeId")
    context["parent_node_label"] = alias_text(context, "parent_node_label", "parentNodeLabel")
    context["workflow_relation_type"] = _normalize_workflow_relation_type(
        alias_text(context, "workflow_relation_type", "workflowRelationType")
    )
    raw_workflow_relations = context.get("workflow_relations") or context.get("workflowRelations")
    if isinstance(raw_workflow_relations, list):
        context["workflow_relations"] = [
            store.clone(item)
            for item in raw_workflow_relations
            if isinstance(item, dict)
        ]
    raw_trigger_payload = context.get("trigger_payload") or context.get("triggerPayload")
    context["trigger_payload"] = store.clone(raw_trigger_payload) if isinstance(raw_trigger_payload, dict) else None
    raw_call_stack = context.get("workflow_call_stack") or context.get("workflowCallStack")
    if isinstance(raw_call_stack, list):
        context["workflow_call_stack"] = [
            item
            for item in (str(entry).strip() for entry in raw_call_stack)
            if item
        ]
    _normalize_dispatch_fallback_policy_mode_for_write(context)
    context["workflow_policy"] = _workflow_policy_from_workflow(workflow)
    workflow_id = str((workflow or {}).get("id") or "").strip()
    if workflow_id in SEQUENTIAL_WORKFLOW_IDS or isinstance((workflow or {}).get("nodes"), list):
        context["execution_engine"] = "graph_v2"
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
    if normalized in {"sub_workflow", "trigger_workflow"}:
        # Keep nested/triggered workflow nodes on the shared execution branch
        # while preserving their runtime semantics through relation metadata.
        return "workflow"
    return normalized or "agent"


def _normalize_workflow_relation_type(value: object) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized == "trigger_workflow":
        return "trigger_workflow"
    if normalized in {"workflow", "sub_workflow"}:
        return "sub_workflow"
    return None


def _workflow_relation_type_from_node(node: dict | None) -> str | None:
    return _normalize_workflow_relation_type((node or {}).get("type"))


def _workflow_relation_type_from_dispatch_context(dispatch_context: dict | None) -> str | None:
    return _normalize_workflow_relation_type(
        alias_text(dispatch_context, "workflow_relation_type", "workflowRelationType")
    )


def _workflow_parent_workflow_id(dispatch_context: dict | None) -> str | None:
    return alias_text(dispatch_context, "parent_workflow_id", "parentWorkflowId")


def _workflow_parent_run_id(dispatch_context: dict | None) -> str | None:
    return alias_text(dispatch_context, "parent_run_id", "parentRunId")


def _workflow_parent_node_id(dispatch_context: dict | None) -> str | None:
    return alias_text(dispatch_context, "parent_node_id", "parentNodeId")


def _workflow_node_message_catalog(node: dict | None) -> dict[str, str]:
    if _workflow_relation_type_from_node(node) == "trigger_workflow":
        return {
            "step_title": "触发工作流",
            "completed": "触发工作流已发起",
            "failed": "触发工作流执行失败",
            "running": "触发工作流触发中",
            "waiting": "等待触发目标工作流",
            "idle_selected": "等待执行",
            "idle_unselected": "当前运行未命中该触发工作流",
        }
    return {
        "step_title": "子工作流执行",
        "completed": "子工作流已完成",
        "failed": "子工作流执行失败",
        "running": "子工作流执行中",
        "waiting": "等待子工作流启动",
        "idle_selected": "等待执行",
        "idle_unselected": "当前运行未命中该子工作流",
    }


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
    workflows = [
        workflow
        for workflow in workflows
        if not _is_legacy_route_disabled_workflow_id(workflow.get("id"))
    ]
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
    preferred_workflow = _preferred_route_selection_workflow(workflows)
    if preferred_workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return preferred_workflow


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
        if _is_legacy_route_disabled_workflow_id(workflow.get("id")):
            continue
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


def _step_node_id(step: dict | None) -> str | None:
    if not isinstance(step, dict):
        return None
    normalized = str(step.get("node_id") or "").strip()
    if normalized:
        return normalized
    metadata = step.get("metadata")
    if isinstance(metadata, dict):
        normalized = str(metadata.get("node_id") or "").strip()
        if normalized:
            return normalized
    return None


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


def _append_node_step(
    *,
    task_id: str,
    node: dict,
    status: str,
    agent: str,
    message: str,
    tokens: int = 0,
    title: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict:
    step = _append_step(
        task_id=task_id,
        title=title or _execution_node_label(node, fallback="执行节点"),
        status=status,
        agent=agent,
        message=message,
        tokens=tokens,
    )
    node_id = str(node.get("id") or "").strip()
    node_type = _normalize_workflow_node_type(node.get("type"))
    node_label = _execution_node_label(node, fallback="执行节点")
    step["node_id"] = node_id
    step["node_type"] = node_type
    step["node_label"] = node_label
    merged_metadata = dict(step.get("metadata") or {})
    merged_metadata.update(
        {
            "node_id": node_id,
            "node_type": node_type,
            "node_label": node_label,
        }
    )
    if isinstance(metadata, dict):
        merged_metadata.update(metadata)
    step["metadata"] = merged_metadata
    return step


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


def resolve_named_execution_agent(
    binding: str | None,
    *,
    expected_type: str | None = None,
    route_seed: str | None = None,
) -> dict | None:
    return _resolve_agent_binding(binding, expected_type=expected_type, route_seed=route_seed)


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


def _ensure_run_dispatch_context(run: dict) -> dict:
    dispatch_context = _run_dispatch_context(run)
    if isinstance(dispatch_context, dict):
        return dispatch_context

    timestamp = store.now_string()
    created_context = {
        "type": "agent_dispatch" if _is_agent_dispatch_run(run) else "message_dispatch",
        "state": str(run.get("status") or "").strip() or "queued",
        "queued_at": timestamp,
        "updated_at": timestamp,
        "state_machine": {"version": "brain_fact_layer_v1"},
    }
    run["dispatch_context"] = created_context
    return created_context


def _workflow_uses_sequential_execution(
    workflow: dict | None,
    *,
    run: dict | None = None,
) -> bool:
    if not isinstance(workflow, dict):
        return False
    dispatch_context = _run_dispatch_context(run)
    engine = ""
    if isinstance(dispatch_context, dict):
        engine = str(
            dispatch_context.get("execution_engine") or dispatch_context.get("executionEngine") or ""
        ).strip().lower()
    if engine:
        return engine == "graph_v2"
    workflow_id = str(workflow.get("id") or "").strip()
    if workflow_id in SEQUENTIAL_WORKFLOW_IDS:
        return True

    # The workflow canvas is the source of truth. Any persisted workflow that still
    # carries a visible graph definition must execute through graph_v2 instead of
    # falling back to the older intent-dispatch shortcut path.
    nodes = workflow.get("nodes")
    return isinstance(nodes, list) and len(nodes) > 0


def _workflow_graph_state(run: dict | None) -> dict[str, Any] | None:
    dispatch_context = _run_dispatch_context(run)
    if not isinstance(dispatch_context, dict):
        return None
    graph_state = dispatch_context.get("graph_state") or dispatch_context.get("graphState")
    return graph_state if isinstance(graph_state, dict) else None


def _workflow_nodes_by_id(workflow: dict | None) -> dict[str, dict]:
    nodes = (workflow or {}).get("nodes") or []
    return {
        str(node.get("id") or "").strip(): node
        for node in nodes
        if isinstance(node, dict) and str(node.get("id") or "").strip()
    }


def _workflow_outgoing_edges(workflow: dict | None, node_id: str | None) -> list[dict]:
    normalized_node_id = str(node_id or "").strip()
    if not normalized_node_id:
        return []
    return [
        edge
        for edge in ((workflow or {}).get("edges") or [])
        if isinstance(edge, dict) and str(edge.get("source") or "").strip() == normalized_node_id
    ]


def _workflow_trigger_node(workflow: dict | None) -> dict | None:
    nodes = (workflow or {}).get("nodes") or []
    for node in nodes:
        if _normalize_workflow_node_type(node.get("type")) == "trigger":
            return node
    return nodes[0] if nodes else None


def _graph_state_node_entry(graph_state: dict[str, Any], node: dict) -> dict[str, Any]:
    node_states = graph_state.setdefault("node_states", {})
    node_id = str(node.get("id") or "").strip()
    entry = node_states.get(node_id)
    if not isinstance(entry, dict):
        entry = {
            "id": node_id,
            "type": _normalize_workflow_node_type(node.get("type")),
            "label": _execution_node_label(node, fallback="执行节点"),
            "agent_id": _derive_agent_binding(node),
            "status": "idle",
            "message": None,
            "tokens": 0,
            "started_at": None,
            "finished_at": None,
            "result": None,
            "attempt": 0,
            "execution_instance_key": None,
            "child_run_id": None,
            "child_run_status": None,
        }
        node_states[node_id] = entry
    return entry


def _graph_state_last_completed_node_id(graph_state: dict[str, Any] | None) -> str | None:
    if not isinstance(graph_state, dict):
        return None
    completed = graph_state.get("completed_node_ids")
    if not isinstance(completed, list) or not completed:
        return None
    normalized = [str(item).strip() for item in completed if str(item).strip()]
    return normalized[-1] if normalized else None


def _graph_state_selected_edge_ids(graph_state: dict[str, Any] | None) -> list[str]:
    if not isinstance(graph_state, dict):
        return []
    selected = graph_state.get("selected_edge_ids")
    if not isinstance(selected, list):
        return []
    return [item for item in (str(edge_id).strip() for edge_id in selected) if item]


def _graph_node_execution_instance(graph_state: dict[str, Any], node: dict) -> tuple[str | None, int]:
    entry = _graph_state_node_entry(graph_state, node)
    attempt = max(int(entry.get("attempt") or 0), 0)
    execution_instance_key = str(entry.get("execution_instance_key") or "").strip()
    if not execution_instance_key and attempt > 0:
        run_id = str(graph_state.get("run_id") or "").strip() or "run"
        node_id = str(node.get("id") or "").strip() or "node"
        execution_instance_key = f"{run_id}:{node_id}:{attempt}"
        entry["execution_instance_key"] = execution_instance_key
    return execution_instance_key or None, attempt


def _graph_selected_node(workflow: dict | None, run: dict | None) -> dict | None:
    graph_state = _workflow_graph_state(run)
    if isinstance(graph_state, dict):
        nodes_by_id = _workflow_nodes_by_id(workflow)
        current_node_id = str(graph_state.get("current_node_id") or "").strip()
        if current_node_id and current_node_id in nodes_by_id:
            return nodes_by_id[current_node_id]
        last_completed_node_id = _graph_state_last_completed_node_id(graph_state)
        if last_completed_node_id and last_completed_node_id in nodes_by_id:
            return nodes_by_id[last_completed_node_id]
    return _selected_branch_node(workflow or {}, (run or {}).get("intent"))


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


def _build_agent_fatal_risk_payload(*, detail: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "kind": "help_note",
        "title": AGENT_FATAL_RISK_TITLE,
        "summary": AGENT_FATAL_FAILURE_USER_MESSAGE,
        "content": AGENT_FATAL_FAILURE_USER_MESSAGE,
        "text": AGENT_FATAL_FAILURE_USER_MESSAGE,
        "bullets": [],
    }
    normalized_detail = str(detail or "").strip()
    if normalized_detail:
        payload["detail"] = normalized_detail
    return payload


def _record_agent_fatal_risk_context(run: dict, *, detail: str | None = None) -> None:
    dispatch_context = _ensure_run_dispatch_context(run)
    dispatch_context["risk_and_safety"] = _build_agent_fatal_risk_payload(detail=detail)


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


def _professional_workflow_selection_from_run(run: dict | None) -> dict[str, Any] | None:
    dispatch_context = _run_dispatch_context(run)
    if not isinstance(dispatch_context, dict):
        return None
    selection = dispatch_context.get("professional_workflow_selection")
    return selection if isinstance(selection, dict) else None


def _infer_professional_workflow_selection(task: dict, run: dict) -> dict[str, Any] | None:
    existing_selection = _professional_workflow_selection_from_run(run)
    if isinstance(existing_selection, dict):
        workflow_id = str(existing_selection.get("workflow_id") or "").strip()
        if workflow_id:
            return store.clone(existing_selection)

    dispatch_context = _run_dispatch_context(run) or {}
    route_decision = _dispatch_context_route_decision(dispatch_context) or route_decision_from_task(task) or {}
    workflow_mode = str(alias_text(route_decision, "workflow_mode", "workflowMode") or "").strip().lower()
    if workflow_mode != "professional_workflow":
        return None

    request_candidates = (
        _primary_request_text(task),
        alias_text(dispatch_context, "message_preview", "messagePreview"),
    )
    request_parts: list[str] = []
    seen_parts: set[str] = set()
    for candidate in request_candidates:
        normalized_candidate = _normalize_free_text(candidate)
        if not normalized_candidate:
            continue
        lowered_candidate = normalized_candidate.lower()
        if lowered_candidate in seen_parts:
            continue
        seen_parts.add(lowered_candidate)
        request_parts.append(lowered_candidate)
    request_text = " ".join(request_parts).strip()
    if not request_text:
        return None

    required_capabilities = _route_decision_required_capabilities(route_decision)
    has_delivery_note_hint = _contains_any_text_hint(request_text, PROFESSIONAL_DELIVERY_NOTE_HINTS)
    has_export_hint = _contains_any_text_hint(request_text, PROFESSIONAL_EXPORT_HINTS)
    has_customer_delivery_hint = _contains_any_text_hint(request_text, PROFESSIONAL_CUSTOMER_DELIVERY_HINTS)
    has_system_navigation_hint = _contains_any_text_hint(request_text, PROFESSIONAL_SYSTEM_NAVIGATION_HINTS)
    capability_match = (
        "document_export" in required_capabilities
        and "notification_delivery" in required_capabilities
        and (
            "enterprise_system_access" in required_capabilities
            or "order_data_access" in required_capabilities
            or has_system_navigation_hint
        )
    )
    if not has_export_hint:
        return None
    if not (has_delivery_note_hint or has_system_navigation_hint):
        return None
    if not (has_customer_delivery_hint or "notification_delivery" in required_capabilities):
        return None

    return {
        "scenario_id": PROFESSIONAL_DELIVERY_NOTE_EXPORT_SCENARIO_ID,
        "workflow_id": PROFESSIONAL_DELIVERY_NOTE_EXPORT_WORKFLOW_ID,
        "workflow_name": PROFESSIONAL_DELIVERY_NOTE_EXPORT_WORKFLOW_NAME,
        "route_reason_summary": (
            f"已识别专业场景：{PROFESSIONAL_DELIVERY_NOTE_EXPORT_WORKFLOW_NAME}，"
            "下一执行单元切换为显式专业子工作流。"
        ),
        "matched_capabilities": sorted(required_capabilities),
        "matched_hints": [
            hint
            for hint, matched in (
                ("delivery_note", has_delivery_note_hint),
                ("system_navigation", has_system_navigation_hint),
                ("document_export", has_export_hint),
                ("customer_delivery", has_customer_delivery_hint),
            )
            if matched
        ],
    }


def _apply_professional_workflow_selection(
    *,
    task: dict,
    run: dict,
    route_decision: dict[str, Any],
    manager_packet: dict[str, Any],
    selection: dict[str, Any],
) -> None:
    dispatch_context = _run_dispatch_context(run)
    if not isinstance(dispatch_context, dict):
        return

    selection_payload = store.clone(selection)
    dispatch_context["professional_workflow_selection"] = selection_payload
    dispatch_context["execution_target_type"] = "workflow"
    dispatch_context["execution_target_id"] = str(selection.get("workflow_id") or "").strip() or None
    dispatch_context["execution_target"] = str(selection.get("workflow_name") or "").strip() or None

    route_reason = str(selection.get("route_reason_summary") or "").strip()
    workflow_id = str(selection.get("workflow_id") or "").strip() or None
    workflow_name = str(selection.get("workflow_name") or "").strip() or None
    scenario_id = str(selection.get("scenario_id") or "").strip() or None
    runtime_tool_id = str(selection.get("runtime_tool_id") or "").strip() or None
    route_decision["specialized_workflow_id"] = workflow_id
    route_decision["specializedWorkflowId"] = workflow_id
    route_decision["specialized_workflow_name"] = workflow_name
    route_decision["specializedWorkflowName"] = workflow_name
    route_decision["specialized_workflow_selector"] = scenario_id
    route_decision["specializedWorkflowSelector"] = scenario_id
    route_decision["route_reason_summary"] = route_reason
    route_decision["routeReasonSummary"] = route_reason
    if runtime_tool_id:
        route_decision["runtime_tool_id"] = runtime_tool_id
        route_decision["runtimeToolId"] = runtime_tool_id

    manager_packet["manager_action"] = "handoff_to_professional_subworkflow"
    manager_packet["managerAction"] = "handoff_to_professional_subworkflow"
    manager_packet["next_owner"] = workflow_name
    manager_packet["nextOwner"] = workflow_name
    manager_packet["handoff_summary"] = (
        f"professional_subworkflow={workflow_id}; scenario={scenario_id}; route={route_reason}"
    )
    manager_packet["handoffSummary"] = manager_packet["handoff_summary"]

    brain_dispatch_summary = dispatch_context.get("brain_dispatch_summary")
    if isinstance(brain_dispatch_summary, dict):
        brain_dispatch_summary["executionAgent"] = workflow_name
        brain_dispatch_summary["nextOwner"] = workflow_name
        brain_dispatch_summary["managerAction"] = "handoff_to_professional_subworkflow"
        brain_dispatch_summary["routeReasonSummary"] = route_reason
        brain_dispatch_summary["summaryLine"] = (
            f"项目经理 handoff_to_professional_subworkflow -> 专业子流程 {workflow_name}"
        )

    task["route_decision"] = route_decision
    task["manager_packet"] = manager_packet


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
    professional_selection = _professional_workflow_selection_from_run(run) or {}
    route_reason = str(
        route_decision.get("route_reason_summary") or route_decision.get("routeReasonSummary") or ""
    ).strip()
    if not route_reason:
        route_reason = str(professional_selection.get("route_reason_summary") or "").strip()
    if route_reason:
        return route_reason
    normalized_intent = str(run.get("intent") or "").strip().lower()
    if normalized_intent and normalized_intent != "manual":
        return f"已完成需求分析，并选定执行意图: {normalized_intent}"
    return None


def _execution_step_for_node(steps: list[dict], node: dict | None) -> dict | None:
    if not node:
        return None

    node_id = str(node.get("id") or "").strip()
    if node_id:
        for step in reversed(steps):
            if _step_node_id(step) == node_id:
                return step

    agent_type = _derive_agent_type(node)
    agent_markers = [str(node.get("label") or "").strip()]
    generic_agent_name = {
        "default": "万事通 Agent",
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
    professional_selection = _professional_workflow_selection_from_run(run) or {}
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
            "specialized_workflow_id": str(
                professional_selection.get("workflow_id")
                or route_decision.get("specialized_workflow_id")
                or route_decision.get("specializedWorkflowId")
                or ""
            ).strip()
            or None,
            "specialized_workflow_name": str(
                professional_selection.get("workflow_name")
                or route_decision.get("specialized_workflow_name")
                or route_decision.get("specializedWorkflowName")
                or ""
            ).strip()
            or None,
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
    explicit_node_id = _step_node_id(step)
    if explicit_node_id:
        return explicit_node_id

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
    selected_node = _graph_selected_node(workflow, run)
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


def _graph_node_default_message(node: dict, status: str) -> str:
    label = _execution_node_label(node, fallback="执行节点")
    return {
        "completed": f"{label} 已完成",
        "running": f"{label} 正在执行",
        "waiting": f"{label} 等待执行",
        "error": f"{label} 执行失败",
    }.get(status, "等待执行")


def _build_graph_run_nodes(workflow: dict, task: dict, run: dict, steps: list[dict]) -> list[dict]:
    graph_state = _workflow_graph_state(run) or {}
    node_states = graph_state.get("node_states")
    if not isinstance(node_states, dict):
        node_states = {}
    current_node_id = str(graph_state.get("current_node_id") or "").strip()
    label_counts: dict[str, int] = {}
    for workflow_node in workflow["nodes"]:
        workflow_node_label = _execution_node_label(workflow_node, fallback="执行节点")
        label_counts[workflow_node_label] = label_counts.get(workflow_node_label, 0) + 1

    def latest_step_for_node(node: dict) -> dict | None:
        node_id = str(node.get("id") or "").strip()
        node_label = _execution_node_label(node, fallback="执行节点")
        node_type = _normalize_workflow_node_type(node.get("type"))
        for step in reversed(steps):
            if _step_node_id(step) == node_id:
                return step

        if label_counts.get(node_label, 0) > 1:
            return None

        for step in reversed(steps):
            step_title = str(step.get("title") or "").strip()
            step_agent = str(step.get("agent") or "").strip()
            if step_title == node_label or step_agent == node_label:
                return step
            if node_type == "condition" and step_title == "执行节点" and node_label in str(step.get("message") or ""):
                return step
            if node_type == "workflow" and "子工作流执行" in step_title and node_label in str(step.get("agent") or ""):
                return step
        return None

    node_error_history = _build_node_error_history(workflow, task, run, steps)

    nodes: list[dict] = []
    for node in workflow["nodes"]:
        node_id = str(node.get("id") or "").strip()
        label = _execution_node_label(node, fallback="执行节点")
        node_type = _normalize_workflow_node_type(node.get("type"))
        agent_binding = _derive_agent_binding(node)
        entry = node_states.get(node_id) if isinstance(node_states.get(node_id), dict) else {}
        step_entry = latest_step_for_node(node)
        status = str(entry.get("status") or "").strip() or ("waiting" if node_id == current_node_id else "idle")
        if node_type == "trigger" and status == "idle":
            status = "completed"
        if step_entry is not None:
            status = _status_from_step(step_entry, status)
        node_state = {
            "id": node_id,
            "type": node_type,
            "label": label,
            "status": status or "idle",
            "agent_id": agent_binding,
            "message": (
                str((step_entry or {}).get("message") or "").strip()
                or str(entry.get("message") or "").strip()
                or _graph_node_default_message(node, status or "idle")
            ),
            "tokens": int((step_entry or {}).get("tokens") or entry.get("tokens") or 0),
            "started_at": str((step_entry or {}).get("started_at") or entry.get("started_at") or run["started_at"]),
            "finished_at": (step_entry or {}).get("finished_at") or entry.get("finished_at"),
            "latest_error": None,
            "latest_error_at": None,
            "error_count": 0,
            "error_history": [],
            "attempt": max(int(entry.get("attempt") or 0), 0),
            "execution_instance_key": str(entry.get("execution_instance_key") or "").strip() or None,
        }

        error_history = node_error_history.get(node_id, [])
        node_state["error_history"] = error_history
        node_state["error_count"] = len(error_history)
        if error_history:
            node_state["latest_error"] = error_history[0]["message"]
            node_state["latest_error_at"] = error_history[0]["timestamp"]
            if node_state["status"] == "error" and not str(node_state.get("message") or "").strip():
                node_state["message"] = error_history[0]["message"]

        nodes.append(node_state)
    return nodes


def _build_run_nodes(workflow: dict, task: dict, run: dict, steps: list[dict]) -> list[dict]:
    if _workflow_uses_sequential_execution(workflow, run=run) and _workflow_graph_state(run) is not None:
        return _build_graph_run_nodes(workflow, task, run, steps)

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
            "attempt": 0,
            "execution_instance_key": None,
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


def _terminal_stage_for_task(task: dict) -> str | None:
    status = str(task.get("status") or "").strip().lower()
    if status == "completed":
        return "执行完成"
    if status == "failed":
        return "执行失败"
    if status == "cancelled":
        return "已取消"
    return None


def _runtime_stage_from_nodes(nodes: list[dict]) -> str | None:
    for node in nodes:
        if node["status"] == "running":
            return node["label"]

    for node in nodes:
        if node["status"] == "waiting":
            if node["type"] == "condition":
                return "等待执行策略"
            return node["label"]
    return None


def _reconcile_terminal_graph_nodes(
    *,
    task: dict,
    run: dict,
    nodes: list[dict],
) -> list[dict]:
    task_status = str(task.get("status") or "").strip().lower()
    if task_status not in TERMINAL_TASK_STATUSES:
        return nodes

    graph_state = _workflow_graph_state(run) or {}
    current_node_id = str(graph_state.get("current_node_id") or "").strip()
    completed_node_ids = {
        str(node_id).strip()
        for node_id in (graph_state.get("completed_node_ids") or [])
        if str(node_id).strip()
    }
    finished_at = (
        str(task.get("completed_at") or "").strip()
        or str(run.get("completed_at") or "").strip()
        or str(run.get("updated_at") or "").strip()
        or store.now_string()
    )

    reconciled: list[dict] = []
    for node in nodes:
        normalized = store.clone(node)
        node_id = str(normalized.get("id") or "").strip()
        status = str(normalized.get("status") or "").strip().lower()
        if status not in {"running", "waiting"}:
            reconciled.append(normalized)
            continue

        if task_status == "completed":
            if node_id in completed_node_ids:
                normalized["status"] = "completed"
                normalized["finished_at"] = normalized.get("finished_at") or finished_at
            else:
                normalized["status"] = "idle"
        elif task_status == "failed":
            if node_id and node_id == current_node_id:
                normalized["status"] = "error"
                normalized["finished_at"] = finished_at
            else:
                normalized["status"] = "idle"
        else:
            normalized["status"] = "idle"

        reconciled.append(normalized)

    return reconciled


def _last_completed_node_projection(
    *,
    task: dict,
    run: dict,
    nodes: list[dict],
) -> tuple[str | None, str | None]:
    graph_state = _workflow_graph_state(run)
    nodes_by_id = {
        str(node.get("id") or "").strip(): node
        for node in nodes
        if str(node.get("id") or "").strip()
    }
    last_completed_node_id = _graph_state_last_completed_node_id(graph_state)
    if last_completed_node_id and last_completed_node_id in nodes_by_id:
        node = nodes_by_id[last_completed_node_id]
        return last_completed_node_id, str(node.get("label") or "").strip() or None

    for node in reversed(nodes):
        if node["status"] in {"completed", "error"}:
            return str(node.get("id") or "").strip() or None, str(node.get("label") or "").strip() or None

    terminal_stage = _terminal_stage_for_task(task)
    return None, terminal_stage


def _run_stage_projection(*, task: dict, run: dict, nodes: list[dict]) -> dict[str, Any]:
    runtime_stage = _runtime_stage_from_nodes(nodes)
    final_stage = _terminal_stage_for_task(task)
    last_completed_node_id, last_completed_node = _last_completed_node_projection(
        task=task,
        run=run,
        nodes=nodes,
    )
    current_stage = final_stage or runtime_stage or last_completed_node or "等待开始"
    return {
        "current_stage": current_stage,
        "runtime_stage": runtime_stage,
        "final_stage": final_stage,
        "last_completed_node": last_completed_node,
        "last_completed_node_id": last_completed_node_id,
    }


def _build_active_edges(workflow: dict, nodes: list[dict], *, run: dict | None = None) -> list[str]:
    if run is not None and _workflow_uses_sequential_execution(workflow, run=run):
        graph_state = _workflow_graph_state(run)
        selected_edge_ids = _graph_state_selected_edge_ids(graph_state)
        if selected_edge_ids or graph_state is not None:
            valid_edge_ids = {
                str(edge.get("id") or "").strip()
                for edge in workflow.get("edges") or []
                if isinstance(edge, dict) and str(edge.get("id") or "").strip()
            }
            return [edge_id for edge_id in selected_edge_ids if edge_id in valid_edge_ids]

    status_by_id = {node["id"]: node["status"] for node in nodes}
    active_edges: list[str] = []
    for edge in workflow["edges"]:
        source_status = status_by_id.get(edge["source"], "idle")
        target_status = status_by_id.get(edge["target"], "idle")
        if source_status in ACTIVE_NODE_STATUSES and target_status != "idle":
            active_edges.append(edge["id"])
    return active_edges


def _current_stage(task: dict, nodes: list[dict]) -> str:
    terminal_stage = _terminal_stage_for_task(task)
    if terminal_stage:
        return terminal_stage

    runtime_stage = _runtime_stage_from_nodes(nodes)
    if runtime_stage:
        return runtime_stage

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
    stage_projection = _run_stage_projection(task=task, run=run, nodes=[])
    run["current_stage"] = stage_projection["current_stage"]
    run["runtime_stage"] = stage_projection["runtime_stage"]
    run["final_stage"] = stage_projection["final_stage"]
    run["last_completed_node"] = stage_projection["last_completed_node"]
    run["last_completed_node_id"] = stage_projection["last_completed_node_id"]
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
    _sync_parent_workflow_relation_from_child_run(run=run, task=task)
    return store.clone(run)


def _refresh_run_state(run: dict, task: dict) -> dict:
    if _is_agent_dispatch_run(run):
        return _refresh_run_state_without_workflow(run, task)
    workflow = _ensure_runtime_workflow_placeholder(run=run, task=task)
    if workflow is None:
        return _refresh_run_state_without_workflow(run, task)
    steps = store.clone(_ensure_task_steps_loaded(task["id"]))
    nodes = _build_run_nodes(workflow, task, run, steps)
    if _workflow_uses_sequential_execution(workflow, run=run) and _workflow_graph_state(run) is not None:
        nodes = _reconcile_terminal_graph_nodes(task=task, run=run, nodes=nodes)

    run["status"] = task["status"]
    run["updated_at"] = store.now_string()
    run["completed_at"] = (
        task.get("completed_at") or store.now_string()
        if task["status"] in TERMINAL_TASK_STATUSES
        else None
    )
    run["nodes"] = nodes
    run["active_edges"] = _build_active_edges(workflow, nodes, run=run)
    stage_projection = _run_stage_projection(task=task, run=run, nodes=nodes)
    run["current_stage"] = stage_projection["current_stage"]
    run["runtime_stage"] = stage_projection["runtime_stage"]
    run["final_stage"] = stage_projection["final_stage"]
    run["last_completed_node"] = stage_projection["last_completed_node"]
    run["last_completed_node_id"] = stage_projection["last_completed_node_id"]
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
    _sync_parent_workflow_relation_from_child_run(run=run, task=task)
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


def _is_internal_child_workflow_run(run: dict) -> bool:
    dispatch_context = _run_dispatch_context(run) or {}
    return bool(
        str(dispatch_context.get("parent_run_id") or dispatch_context.get("parentRunId") or "").strip()
    )


def _delivery_message_for_result(task: dict, run: dict, task_result: dict) -> dict[str, str]:
    if _is_internal_child_workflow_run(run):
        return {
            "status": "skipped",
            "message": "子工作流结果已回传父流程，不单独执行渠道回传",
        }
    return channel_outbound_service.deliver_task_result(task, task_result, run=run)


def _delivery_message_for_failure(task: dict, run: dict, error_message: str) -> dict[str, str]:
    if _is_internal_child_workflow_run(run):
        return {
            "status": "skipped",
            "message": "子工作流失败已回传父流程，不单独执行渠道回传",
        }
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


def _append_visible_assistant_conversation_message(task: dict, run: dict | None, content: str) -> None:
    if isinstance(run, dict) and _is_internal_child_workflow_run(run):
        return
    _append_assistant_conversation_message(task, content)


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
            failure_message=AGENT_FATAL_FAILURE_USER_MESSAGE,
            technical_detail=_normalize_agent_execution_failure_message(exc),
        )
    if not _is_valid_task_result_payload(task_result):
        return None, _fail_workflow_run_due_agent_execution_error_locked(
            run,
            task,
            failure_message=AGENT_FATAL_FAILURE_USER_MESSAGE,
            technical_detail="Agent 执行结果不合格，主脑已拒收并终止任务",
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
    _append_visible_assistant_conversation_message(
        task,
        run,
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
    relation_type = _workflow_relation_type(node)
    parent_dispatch_context = _run_dispatch_context(run) or {}
    graph_state = _workflow_graph_state(run)
    node_entry = _graph_state_node_entry(graph_state, node) if isinstance(graph_state, dict) else None
    execution_instance_key = None
    source_attempt = None
    if isinstance(graph_state, dict):
        execution_instance_key, source_attempt = _graph_node_execution_instance(graph_state, node)
    workflow_call_stack = parent_dispatch_context.get("workflow_call_stack")
    normalized_stack = [str(item).strip() for item in workflow_call_stack or [] if str(item).strip()]
    current_workflow_id = str(run.get("workflow_id") or "").strip()
    next_stack = [*normalized_stack, *([current_workflow_id] if current_workflow_id else [])]
    handoff_note = _node_config_text(node, "handoffNote", "handoff_note")
    node_description = str(node.get("description") or "").strip()
    trigger_payload = (
        _build_workflow_trigger_payload(task=task, run=run, node=node)
        if relation_type == "trigger_workflow"
        else None
    )
    parent_route_decision = _dispatch_context_route_decision(parent_dispatch_context)
    parent_manager_packet = _manager_packet_for_run(task, run)
    parent_request_context = parent_dispatch_context.get("request_context") or parent_dispatch_context.get(
        "requestContext"
    )
    parent_security_context = parent_dispatch_context.get("security_context") or parent_dispatch_context.get(
        "securityContext"
    )
    parent_tenant_context = parent_dispatch_context.get("tenant_context") or parent_dispatch_context.get(
        "tenantContext"
    )
    child_input_payload = _workflow_child_input_payload(task, run)
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

    child_run = None
    child_task = None
    if node_entry is not None:
        existing_child_run_id = str(node_entry.get("child_run_id") or "").strip()
        if existing_child_run_id:
            try:
                child_run = _find_run(existing_child_run_id)
            except HTTPException:
                node_entry["child_run_id"] = None
                node_entry["child_run_status"] = None
                child_run = None
        if child_run is not None:
            child_task = _find_task(child_run.get("task_id"))

    if child_run is None:
        child_bundle = create_manual_workflow_run(
            child_workflow_id,
            trigger=_workflow_child_trigger(
                relation_type=relation_type,
                parent_workflow_id=current_workflow_id or None,
                parent_node_id=str(node.get("id") or "").strip() or None,
            ),
            intent=inherited_intent,
            task_title=(
                f"触发工作流 - {child_workflow['name']}"
                if relation_type == "trigger_workflow"
                else f"子工作流触发 - {child_workflow['name']}"
            ),
            task_description=_append_description_text(
                task.get("description") or child_workflow.get("description"),
                *(
                    [
                        f"父流程节点说明：{node_description}",
                        (
                            f"触发说明：{handoff_note}"
                            if relation_type == "trigger_workflow"
                            else f"父子流程交接说明：{handoff_note}"
                        ),
                        (
                            f"触发参数：{_workflow_trigger_payload_preview(trigger_payload or {})}"
                            if relation_type == "trigger_workflow"
                            and _workflow_trigger_payload_preview(trigger_payload or {})
                            else None
                        ),
                        _workflow_parent_result_summary_line(task),
                    ]
                    if handoff_note or node_description
                    or (relation_type == "trigger_workflow" and trigger_payload)
                    or _workflow_parent_result_summary_line(task)
                    else []
                ),
            ),
            trigger_title="触发工作流" if relation_type == "trigger_workflow" else "子工作流触发",
            trigger_agent=_execution_node_label(node, fallback="子工作流节点"),
            trigger_message=(
                f"父工作流 {current_workflow_id or '-'} 已"
                + ("触发工作流" if relation_type == "trigger_workflow" else "触发子工作流")
                + f" {child_workflow['name']}"
                + (f"；交接说明：{handoff_note}" if handoff_note else "")
            ),
            preferred_language=_normalize_language(
                str(task.get("preferred_language") or task.get("preferredLanguage") or "")
            ),
            detected_lang=_normalize_language(
                str(task.get("detected_lang") or task.get("detectedLang") or "")
            ),
            dispatch_context={
                "route_decision": store.clone(parent_route_decision) if isinstance(parent_route_decision, dict) else None,
                "manager_packet": store.clone(parent_manager_packet) if isinstance(parent_manager_packet, dict) else None,
                "message_preview": alias_text(parent_dispatch_context, "message_preview", "messagePreview"),
                "request_context": store.clone(parent_request_context) if isinstance(parent_request_context, dict) else None,
                "security_context": store.clone(parent_security_context)
                if isinstance(parent_security_context, dict)
                else None,
                "tenant_context": store.clone(parent_tenant_context) if isinstance(parent_tenant_context, dict) else None,
                "professional_workflow_selection": store.clone(
                    parent_dispatch_context.get("professional_workflow_selection")
                )
                if isinstance(parent_dispatch_context.get("professional_workflow_selection"), dict)
                else None,
                "workflow_call_stack": next_stack,
                "parent_workflow_id": current_workflow_id or None,
                "parent_workflow_name": str(run.get("workflow_name") or "").strip() or None,
                "parent_run_id": str(run.get("id") or "").strip() or None,
                "parent_node_id": str(node.get("id") or "").strip() or None,
                "parent_node_label": _execution_node_label(node, fallback="工作流节点"),
                "parent_node_execution_key": execution_instance_key,
                "parent_node_attempt": source_attempt,
                "workflow_relation_type": relation_type,
                "trigger_payload": store.clone(trigger_payload) if trigger_payload else None,
                "internal_event_payload": store.clone(child_input_payload) if child_input_payload else None,
                "workflow_return": (
                    {
                        "input_source": child_input_payload.get("input_source"),
                        "inputSource": child_input_payload.get("inputSource"),
                        "return_payload": store.clone(child_input_payload.get("upstream_result")),
                        "returnPayload": store.clone(child_input_payload.get("upstream_result")),
                        "summary": child_input_payload.get("final_result_text"),
                        "handoff_target": child_input_payload.get("handoff_target"),
                        "handoffTarget": child_input_payload.get("handoffTarget"),
                        "conversation_stage": child_input_payload.get("conversation_stage"),
                        "conversationStage": child_input_payload.get("conversationStage"),
                        "result_status": child_input_payload.get("result_status"),
                        "resultStatus": child_input_payload.get("resultStatus"),
                        "source_workflow_id": child_input_payload.get("source_workflow_id"),
                        "sourceWorkflowId": child_input_payload.get("sourceWorkflowId"),
                        "source_run_id": child_input_payload.get("source_run_id"),
                        "sourceRunId": child_input_payload.get("sourceRunId"),
                    }
                    if child_input_payload
                    else None
                ),
            },
            eager_start=False,
            auto_schedule=False,
        )
        child_run = _find_run(str(child_bundle["run"]["id"] or ""))
        child_task = _find_task(child_bundle["task"]["id"])
        if node_entry is not None and child_run is not None:
            node_entry["child_run_id"] = str(child_run.get("id") or "").strip() or None
            node_entry["child_run_status"] = str(child_run.get("status") or "").strip() or None

    child_run_id = str((child_run or {}).get("id") or "")
    _append_workflow_relation_to_run(
        run,
        relation_type=relation_type,
        source_node=node,
        target_workflow=child_workflow,
        target_run=child_run,
        target_task=child_task,
        handoff_note=handoff_note,
        trigger_payload=trigger_payload,
        execution_instance_key=execution_instance_key,
        source_attempt=source_attempt,
    )

    if relation_type == "trigger_workflow":
        trigger_result = {
            "kind": "workflow_trigger",
            "title": f"已触发工作流 {child_workflow['name']}",
            "summary": f"已触发工作流“{child_workflow['name']}”，父流程继续推进",
            "content": (
                f"目标工作流：{child_workflow['name']}\n"
                f"工作流 ID：{child_workflow_id}\n"
                f"运行 ID：{child_run_id}\n"
                f"当前状态：{str(child_run.get('status') or 'pending')}"
                + (f"\n触发说明：{handoff_note}" if handoff_note else "")
            ),
            "bullets": [
                f"来源节点：{_execution_node_label(node, fallback='触发工作流节点')}",
                f"目标运行：{child_run_id}",
                f"当前状态：{str(child_run.get('status') or 'pending')}",
                *(
                    [f"触发参数：{_workflow_trigger_payload_preview(trigger_payload or {})}"]
                    if _workflow_trigger_payload_preview(trigger_payload or {})
                    else []
                ),
            ],
            "orchestration_steps": [
                {
                    "title": "触发工作流",
                    "status": "completed",
                    "agent": _execution_node_label(node, fallback="触发工作流节点"),
                    "message": f"已触发工作流 {child_workflow['name']}（run={child_run_id}）",
                    "tokens": 0,
                }
            ],
        }
        return trigger_result, None

    refreshed_child_run = child_run
    child_status = str((refreshed_child_run or {}).get("status") or "").strip().lower()
    if child_status not in TERMINAL_TASK_STATUSES:
        _cancel_scheduled_run(child_run_id)
        max_child_ticks = max(len(child_workflow.get("nodes") or []) * 4, 8)
        for _ in range(max_child_ticks):
            refreshed_child_run = _advance_workflow_run_locked(
                child_run_id,
                mode="tick",
                auto_schedule=False,
            )
            if str(refreshed_child_run.get("status") or "").strip().lower() in TERMINAL_TASK_STATUSES:
                break

    child_task = _find_task(refreshed_child_run.get("task_id"))
    if node_entry is not None:
        node_entry["child_run_id"] = str(refreshed_child_run.get("id") or "").strip() or None
        node_entry["child_run_status"] = str(refreshed_child_run.get("status") or "").strip() or None
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
        _append_workflow_relation_to_run(
            run,
            relation_type=relation_type,
            source_node=node,
            target_workflow=child_workflow,
            target_run=refreshed_child_run,
            target_task=child_task,
            handoff_note=handoff_note,
            trigger_payload=trigger_payload,
            execution_instance_key=execution_instance_key,
            source_attempt=source_attempt,
        )
        return None, _fail_workflow_run_due_execution_target_error_locked(
            task=task,
            run=run,
            steps=steps,
            failure_message=f"子工作流 {child_workflow['name']} 未完成：{child_failure_message}",
            failure_stage="execution",
        )

    _inherit_child_dispatch_context_to_parent_run(parent_run=run, child_run=refreshed_child_run)
    _append_workflow_relation_to_run(
        run,
        relation_type=relation_type,
        source_node=node,
        target_workflow=child_workflow,
        target_run=refreshed_child_run,
        target_task=child_task,
        handoff_note=handoff_note,
        trigger_payload=trigger_payload,
        execution_instance_key=execution_instance_key,
        source_attempt=source_attempt,
    )

    child_result = store.clone(child_task.get("result"))
    if _is_valid_task_result_payload(child_result):
        if not _is_foundation_module_workflow_id(child_workflow.get("id")):
            child_result["summary"] = f"已通过子工作流“{child_workflow['name']}”完成执行"
        orchestration_steps = child_result.get("orchestration_steps")
        if not isinstance(orchestration_steps, list):
            orchestration_steps = []
            child_result["orchestration_steps"] = orchestration_steps
        if handoff_note and not _is_foundation_module_workflow_id(child_workflow.get("id")):
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
        _promote_child_workflow_result_to_parent_run(
            parent_run=run,
            child_run=refreshed_child_run,
            child_task=child_task,
            child_result=child_result,
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
    _promote_child_workflow_result_to_parent_run(
        parent_run=run,
        child_run=refreshed_child_run,
        child_task=child_task,
        child_result=fallback_result,
    )
    return fallback_result, None


def _close_graph_waiting_step(steps: list[dict], *, next_label: str) -> None:
    waiting_step = next(
        (
            step
            for step in reversed(steps)
            if step.get("status") == "running" and _step_node_id(step) is None
        ),
        None,
    )
    if waiting_step is None:
        return
    waiting_step["status"] = "completed"
    waiting_step["finished_at"] = store.now_string()
    waiting_step["message"] = f"真实工作流图执行已启动，进入节点 {next_label}"


def _ensure_sequential_graph_state(run: dict, workflow: dict) -> dict[str, Any]:
    dispatch_context = _run_dispatch_context(run)
    if not isinstance(dispatch_context, dict):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Dispatch context missing")

    graph_state = _workflow_graph_state(run)
    workflow_id = str(workflow.get("id") or "").strip()
    if isinstance(graph_state, dict) and str(graph_state.get("workflow_id") or "").strip() == workflow_id:
        return graph_state

    graph_state = {
        "version": "workflow_graph.v2",
        "run_id": str(run.get("id") or "").strip() or None,
        "workflow_id": workflow_id,
        "started_at": store.now_string(),
        "current_node_id": None,
        "completed_node_ids": [],
        "selected_edge_ids": [],
        "execution_order": [],
        "node_states": {},
        "node_results": {},
    }
    trigger_node = _workflow_trigger_node(workflow)
    if trigger_node is not None:
        trigger_entry = _graph_state_node_entry(graph_state, trigger_node)
        trigger_entry.update(
            {
                "status": "completed",
                "message": f"触发器已接收事件 ({run.get('trigger') or 'manual'})",
                "started_at": str(run.get("started_at") or store.now_string()),
                "finished_at": str(run.get("started_at") or store.now_string()),
            }
        )
        graph_state["completed_node_ids"].append(str(trigger_node.get("id") or "").strip())
        graph_state["execution_order"].append(str(trigger_node.get("id") or "").strip())
        next_node_id, edge_id = _graph_next_node_after(
            workflow=workflow,
            node=trigger_node,
            task=None,
            run=run,
            graph_state=graph_state,
        )
        graph_state["current_node_id"] = next_node_id
        if edge_id:
            graph_state["selected_edge_ids"].append(edge_id)
    dispatch_context["graph_state"] = graph_state
    return graph_state


def _route_decision_required_capabilities(route_decision: dict[str, Any]) -> set[str]:
    raw_capabilities = route_decision.get("required_capabilities") or route_decision.get("requiredCapabilities")
    if not isinstance(raw_capabilities, list):
        return set()
    return {
        str(item).strip().lower()
        for item in raw_capabilities
        if str(item).strip()
    }


def _task_has_light_closed_loop_payload(task: dict, route_decision: dict[str, Any]) -> bool:
    schedule_plan = route_decision.get("schedule_plan") or route_decision.get("schedulePlan")
    return bool(
        task.get("file_path")
        or task.get("filePath")
        or task.get("document_text")
        or task.get("documentText")
        or (isinstance(schedule_plan, dict) and schedule_plan)
    )


def _graph_condition_facts(task: dict, run: dict, graph_state: dict[str, Any]) -> dict[str, bool]:
    del graph_state
    dispatch_context = _run_dispatch_context(run) or {}
    route_decision = _dispatch_context_route_decision(dispatch_context) or route_decision_from_task(task) or {}
    manager_packet = _manager_packet_for_run(task, run)
    professional_selection = _professional_workflow_selection_from_run(run) or {}
    inferred_professional_selection = _infer_professional_workflow_selection(task, run) or {}
    current_result = task.get("result")
    current_result = current_result if isinstance(current_result, dict) else {}
    fallback_contract = current_result.get("fallback_contract")
    fallback_contract = fallback_contract if isinstance(fallback_contract, dict) else {}
    acceptance = dispatch_context.get("acceptance")
    acceptance = acceptance if isinstance(acceptance, dict) else {}
    internal_event_payload = dispatch_context.get("internal_event_payload")
    internal_event_payload = internal_event_payload if isinstance(internal_event_payload, dict) else {}
    workflow_return = dispatch_context.get("workflow_return") or dispatch_context.get("workflowReturn")
    workflow_return = workflow_return if isinstance(workflow_return, dict) else {}
    request_context = dispatch_context.get("request_context") or dispatch_context.get("requestContext")
    request_context = request_context if isinstance(request_context, dict) else {}
    input_source = str(
        alias_text(
            internal_event_payload,
            "input_source",
            "inputSource",
        )
        or alias_text(workflow_return, "input_source", "inputSource")
        or alias_text(dispatch_context, "input_source", "inputSource")
        or ""
    ).strip().lower()
    requirement_type = str(
        alias_text(
            internal_event_payload,
            "requirement_type",
            "requirementType",
        )
        or alias_text(dispatch_context, "requirement_type", "requirementType")
        or ""
    ).strip().lower()
    query_scope = str(
        alias_text(
            internal_event_payload,
            "query_scope",
            "queryScope",
        )
        or alias_text(dispatch_context, "query_scope", "queryScope")
        or alias_text(route_decision, "query_scope", "queryScope")
        or ""
    ).strip().lower()
    professional_query_flag = alias_bool(
        internal_event_payload,
        "professional_query",
        "professionalQuery",
    )
    if professional_query_flag is None:
        professional_query_flag = alias_bool(
            dispatch_context,
            "professional_query",
            "professionalQuery",
        )
    if professional_query_flag is None:
        professional_query_flag = alias_bool(
            route_decision,
            "professional_query",
            "professionalQuery",
        )
    has_upstream_result = any(
        internal_event_payload.get(key) not in (None, "")
        for key in (
            "upstream_result",
            "upstreamResult",
            "final_result_payload",
            "finalResultPayload",
            "final_result_text",
            "finalResultText",
        )
    )
    if not has_upstream_result:
        has_upstream_result = any(
            workflow_return.get(key) not in (None, "")
            for key in (
                "return_payload",
                "returnPayload",
                "summary",
                "text",
                "content",
            )
        )
    channel_input = input_source in {"channel", "channel_input", "message", "ingress"} or (
        not input_source and bool(str(request_context.get("channel") or "").strip()) and not has_upstream_result
    )
    query_request = requirement_type in {"query", "search", "lookup"} or _normalize_intent(run.get("intent")) in {
        "search",
        "help",
    }
    workflow_mode = str(alias_text(route_decision, "workflow_mode", "workflowMode") or "").strip().lower()
    professional_query = (
        bool(professional_query_flag)
        if professional_query_flag is not None
        else query_scope in {"professional", "domain", "internal_knowledge", "professional_query"}
        or workflow_mode == "professional_workflow"
    )
    confirmation_status = str(
        route_decision.get("confirmation_status") or route_decision.get("confirmationStatus") or ""
    ).strip().lower()
    clarify_required = bool(manager_packet.get("clarify_required"))
    required_capabilities = _route_decision_required_capabilities(route_decision)
    light_closed_loop_candidate = workflow_mode == "free_workflow" and bool(
        required_capabilities & LIGHT_CLOSED_LOOP_TRIGGER_CAPABILITIES
        or _task_has_light_closed_loop_payload(task, route_decision)
    )
    fallback_resolution = str(alias_text(fallback_contract, "resolution") or "").strip().lower()
    light_closed_loop_completed = light_closed_loop_candidate and _is_valid_task_result_payload(current_result) and (
        fallback_resolution not in {"skill_failure", "terminal_failure"}
    )
    accepted = bool(acceptance.get("accepted"))
    outbound_safe = bool(acceptance.get("outbound_safe", accepted))
    specialized_workflow_id = str(
        professional_selection.get("workflow_id")
        or inferred_professional_selection.get("workflow_id")
        or route_decision.get("specialized_workflow_id")
        or route_decision.get("specializedWorkflowId")
        or ""
    ).strip()
    handoff_target = str(
        alias_text(workflow_return, "handoff_target", "handoffTarget")
        or alias_text(internal_event_payload, "handoff_target", "handoffTarget")
        or alias_text(current_result, "handoff_target", "handoffTarget")
        or ""
    ).strip().lower()
    conversation_stage = str(
        alias_text(workflow_return, "conversation_stage", "conversationStage")
        or alias_text(internal_event_payload, "conversation_stage", "conversationStage")
        or alias_text(current_result, "conversation_stage", "conversationStage")
        or ""
    ).strip().lower()
    result_status = str(
        alias_text(workflow_return, "result_status", "resultStatus")
        or alias_text(internal_event_payload, "result_status", "resultStatus")
        or alias_text(current_result, "result_status", "resultStatus")
        or task.get("status")
        or ""
    ).strip().lower()

    facts = {
        "allow": True,
        "rewrite": False,
        "block": False,
        "channel_input": channel_input,
        "final_result_input": has_upstream_result or input_source in {"final_result", "upstream_result", "downstream"},
        "chat": workflow_mode == "chat",
        "free_workflow": workflow_mode == "free_workflow",
        "professional_workflow": workflow_mode == "professional_workflow",
        "light_closed_loop_candidate": light_closed_loop_candidate,
        "goal_complete": not clarify_required,
        "scope_clear": not clarify_required,
        "confirmation_ready": confirmation_status != "pending",
        "light_closed_loop_completed": light_closed_loop_completed,
        "professional_sub_workflow_selected": bool(specialized_workflow_id),
        "delivery_note_export_workflow": specialized_workflow_id
        == PROFESSIONAL_DELIVERY_NOTE_EXPORT_WORKFLOW_ID,
        "accepted": accepted,
        "outbound_safe": outbound_safe,
        "query_request": query_request,
        "professional_query": professional_query,
        "task_dispatch_request": not query_request,
        "search": _normalize_intent(run.get("intent")) == "search",
        "write": _normalize_intent(run.get("intent")) == "write",
        "help": _normalize_intent(run.get("intent")) == "help",
        "has_workflow_return": bool(workflow_return or has_upstream_result),
        "has_handoff_target": bool(handoff_target),
        "has_conversation_stage": bool(conversation_stage),
        "result_status_completed": result_status == "completed",
        "result_status_failed": result_status == "failed",
        "result_status_cancelled": result_status == "cancelled",
    }
    handoff_target_token = _normalize_condition_fact_token(handoff_target)
    if handoff_target_token:
        facts[f"handoff_target_{handoff_target_token}"] = True
    conversation_stage_token = _normalize_condition_fact_token(conversation_stage)
    if conversation_stage_token:
        facts[f"conversation_stage_{conversation_stage_token}"] = True
    return facts


def _evaluate_condition_expression(expression: str | None, *, facts: dict[str, bool]) -> bool | None:
    normalized = str(expression or "").strip()
    if not normalized:
        return None
    tokens = (
        normalized.replace("(", " ")
        .replace(")", " ")
        .replace("&&", " && ")
        .replace("||", " || ")
        .split()
    )
    result: bool | None = None
    operator: str | None = None
    for token in tokens:
        if token in {"&&", "||"}:
            operator = token
            continue
        value = bool(facts.get(token.strip().lower(), False))
        if result is None:
            result = value
            continue
        if operator == "&&":
            result = result and value
        elif operator == "||":
            result = result or value
        else:
            result = value
    return result


def _graph_next_node_after(
    *,
    workflow: dict,
    node: dict,
    task: dict | None,
    run: dict,
    graph_state: dict[str, Any],
) -> tuple[str | None, str | None]:
    outgoing_edges = _workflow_outgoing_edges(workflow, str(node.get("id") or "").strip())
    if not outgoing_edges:
        return None, None

    nodes_by_id = _workflow_nodes_by_id(workflow)
    node_type = _normalize_workflow_node_type(node.get("type"))
    if node_type == "condition":
        expression = _node_config_text(node, "expression")
        facts = _graph_condition_facts(task or {}, run, graph_state)
        expression_result = _evaluate_condition_expression(expression, facts=facts)
        if expression_result is not None:
            preferred_handle = "true" if expression_result else "false"
            for edge in outgoing_edges:
                if str(edge.get("source_handle") or "").strip().lower() == preferred_handle:
                    return str(edge.get("target") or "").strip() or None, str(edge.get("id") or "").strip() or None

    dispatch_context = _run_dispatch_context(run) or {}
    route_decision = _dispatch_context_route_decision(dispatch_context) or route_decision_from_task(task) or {}
    workflow_mode = str(alias_text(route_decision, "workflow_mode", "workflowMode") or "").strip().lower()
    intent = _normalize_intent(run.get("intent"))
    default_route: tuple[str | None, str | None] | None = None
    for edge in outgoing_edges:
        target_node = nodes_by_id.get(str(edge.get("target") or "").strip())
        if target_node is None:
            continue
        target_node_id = str(target_node.get("id") or "").strip() or None
        edge_id = str(edge.get("id") or "").strip() or None
        route_workflow_modes = {
            item.strip().lower()
            for item in _node_config_list(target_node, "routeWorkflowModes", "route_workflow_modes")
            if item.strip()
        }
        if workflow_mode and workflow_mode in route_workflow_modes:
            return target_node_id, edge_id

        route_intents = {
            item.strip().lower()
            for item in _node_config_list(target_node, "routeIntents", "route_intents")
            if item.strip()
        }
        if intent and intent in route_intents:
            return target_node_id, edge_id

        if default_route is None and alias_bool(_node_config(target_node), "routeDefault", "route_default"):
            default_route = (target_node_id, edge_id)

    if default_route is not None:
        return default_route

    selected_agent_type = INTENT_AGENT_TYPE_MAP.get(intent) or intent
    if selected_agent_type:
        for edge in outgoing_edges:
            target_node = nodes_by_id.get(str(edge.get("target") or "").strip())
            if target_node is None:
                continue
            if _derive_agent_type(target_node) == selected_agent_type:
                return str(target_node.get("id") or "").strip() or None, str(edge.get("id") or "").strip() or None

    first_edge = outgoing_edges[0]
    return str(first_edge.get("target") or "").strip() or None, str(first_edge.get("id") or "").strip() or None


def _mark_graph_node_running(graph_state: dict[str, Any], node: dict, step: dict) -> None:
    entry = _graph_state_node_entry(graph_state, node)
    node_id = str(node.get("id") or "").strip() or "node"
    run_id = str(graph_state.get("run_id") or "").strip() or "run"
    attempt = max(int(entry.get("attempt") or 0), 0) + 1
    entry.update(
        {
            "status": "running",
            "message": str(step.get("message") or "").strip() or _graph_node_default_message(node, "running"),
            "tokens": int(step.get("tokens") or 0),
            "started_at": str(step.get("started_at") or store.now_string()),
            "finished_at": None,
            "attempt": attempt,
            "execution_instance_key": f"{run_id}:{node_id}:{attempt}",
        }
    )
    if _normalize_workflow_node_type(node.get("type")) == "workflow":
        entry["child_run_id"] = None
        entry["child_run_status"] = None
    execution_order = graph_state.setdefault("execution_order", [])
    if not execution_order or execution_order[-1] != node_id:
        execution_order.append(node_id)


def _mark_graph_node_completed(
    graph_state: dict[str, Any],
    node: dict,
    *,
    message: str,
    tokens: int,
    started_at: str | None,
    result: object = None,
) -> None:
    entry = _graph_state_node_entry(graph_state, node)
    entry.update(
        {
            "status": "completed",
            "message": message,
            "tokens": max(int(tokens), 0),
            "started_at": started_at or entry.get("started_at") or store.now_string(),
            "finished_at": store.now_string(),
            "result": store.clone(result) if result is not None else entry.get("result"),
            "child_run_status": entry.get("child_run_status"),
        }
    )
    node_id = str(node.get("id") or "").strip()
    completed = graph_state.setdefault("completed_node_ids", [])
    if node_id not in completed:
        completed.append(node_id)
    if result is not None:
        graph_state.setdefault("node_results", {})[node_id] = store.clone(result)


def _mark_graph_node_error(graph_state: dict[str, Any], node: dict, *, message: str) -> None:
    entry = _graph_state_node_entry(graph_state, node)
    entry.update(
        {
            "status": "error",
            "message": message,
            "finished_at": store.now_string(),
            "child_run_status": entry.get("child_run_status"),
        }
    )


def _graph_step_agent_name(node: dict) -> str:
    label = _execution_node_label(node, fallback="执行节点")
    node_type = _normalize_workflow_node_type(node.get("type"))
    if node_type in {"condition", "transform", "output", "workflow", "tool"}:
        return label
    return label


def _graph_result_label(task_result: dict) -> str:
    return (
        str(task_result.get("title") or "").strip()
        or str(task_result.get("text") or "").strip()
        or str(task_result.get("summary") or "").strip()
        or str(task_result.get("content") or "").strip()
        or "对话回复"
    )


def _execute_internal_graph_agent_node(
    *,
    task: dict,
    run: dict,
    node: dict,
) -> tuple[dict[str, Any], str]:
    dispatch_context = _run_dispatch_context(run) or {}
    route_decision = _dispatch_context_route_decision(dispatch_context) or route_decision_from_task(task) or {}
    manager_packet = _manager_packet_for_run(task, run)
    agent_type = _derive_agent_type(node) or str(_derive_agent_binding(node) or "").strip().lower()
    node_label = _execution_node_label(node, fallback="执行节点")

    if agent_type == "security_guardian":
        warnings = [str(item).strip() for item in run.get("warnings") or [] if str(item).strip()]
        message = "已完成入站安全闸门校验，消息允许进入主脑编排"
        if warnings:
            message = f"{message}；附带处理: {', '.join(warnings[:2])}"
        return {"decision": "allow", "warnings": warnings}, message

    if agent_type == "security":
        approval_required = bool(
            route_decision.get("approval_required")
            if isinstance(route_decision.get("approval_required"), bool)
            else route_decision.get("approvalRequired")
        )
        confirmation_status = str(
            route_decision.get("confirmation_status") or route_decision.get("confirmationStatus") or ""
        ).strip()
        if approval_required or confirmation_status == "pending":
            message = "已完成风险评审，当前请求需要保持受控推进或等待确认"
        else:
            message = "已完成风险评审，未发现需要阻断的额外风险"
        return {
            "approval_required": approval_required,
            "confirmation_status": confirmation_status or None,
        }, message

    if agent_type == "conversation":
        if "专业流程确认" in node_label:
            workflow_mode = str(alias_text(route_decision, "workflow_mode", "workflowMode") or "").strip().lower()
            current_result = task.get("result")
            current_result = current_result if isinstance(current_result, dict) else {}
            prior_summary = (
                str(current_result.get("summary") or "").strip()
                or str(current_result.get("text") or "").strip()
                or str(current_result.get("content") or "").strip()
            )
            if workflow_mode != "professional_workflow":
                route_decision["workflow_mode"] = "professional_workflow"
                route_decision["workflowMode"] = "professional_workflow"
            route_decision["confirmation_required"] = True
            route_decision["confirmationRequired"] = True
            route_decision["confirmation_status"] = "pending"
            route_decision["confirmationStatus"] = "pending"
            confirm_text = (
                prior_summary
                or "已识别当前请求需要升级到专业流程。请确认是否继续进入专业流程，我会在你确认后继续推进。"
            )
            if "专业流程" not in confirm_text:
                confirm_text = f"已识别当前请求需要升级到专业流程。{confirm_text}"
            message = "已向用户发起专业流程确认，等待确认后继续推进"
            return {
                "kind": "chat_reply",
                "title": "专业流程确认",
                "summary": confirm_text,
                "content": confirm_text,
                "text": confirm_text,
                "bullets": [],
                "references": [],
                "execution_trace": [],
            }, message

        conversation_agent = _resolve_agent_binding(
            _derive_agent_binding(node) or "conversation",
            expected_type="conversation",
            route_seed=_execution_route_seed(
                run=run,
                workflow=None,
                agent_type="conversation",
            ),
        )
        if conversation_agent is not None:
            try:
                conversation_result = agent_execution_service.execute_task(
                    task=task,
                    run=run,
                    execution_agent=conversation_agent,
                )
            except Exception:
                conversation_result = None
            if _is_valid_task_result_payload(conversation_result):
                result_label = _graph_result_label(conversation_result)
                message = f"Conversation Agent 已完成接待回复，产出「{result_label}」"
                return conversation_result, message

        clarify_required = bool(manager_packet.get("clarify_required"))
        clarify_question = str(manager_packet.get("clarify_question") or "").strip()
        handoff_summary = str(manager_packet.get("handoff_summary") or "").strip()
        if clarify_required:
            message = clarify_question or "当前需求仍需进一步澄清后才能继续"
        else:
            message = handoff_summary or "已完成需求澄清，并整理出结构化 handoff summary"
        return {
            "clarify_required": clarify_required,
            "clarify_question": clarify_question or None,
            "handoff_summary": handoff_summary or None,
        }, message

    if agent_type == "task_dispatcher":
        professional_selection = _infer_professional_workflow_selection(task, run)
        if professional_selection is not None:
            _apply_professional_workflow_selection(
                task=task,
                run=run,
                route_decision=route_decision,
                manager_packet=manager_packet,
                selection=professional_selection,
            )
            route_reason = str(professional_selection.get("route_reason_summary") or "").strip()
            workflow_name = str(professional_selection.get("workflow_name") or "").strip()
            message = route_reason or f"已完成派工，下一执行单元: {workflow_name}"
            return {
                "execution_target_type": "workflow",
                "execution_target": workflow_name or None,
                "execution_target_id": str(professional_selection.get("workflow_id") or "").strip() or None,
                "route_reason_summary": route_reason or None,
                "professional_workflow_selection": store.clone(professional_selection),
            }, message

        route_reason = str(
            route_decision.get("route_reason_summary") or route_decision.get("routeReasonSummary") or ""
        ).strip()
        execution_agent_name = str(
            route_decision.get("execution_agent") or route_decision.get("executionAgent") or ""
        ).strip()
        message = route_reason or f"已完成派工，下一执行单元: {execution_agent_name or '外接触手执行层'}"
        return {
            "execution_agent": execution_agent_name or None,
            "route_reason_summary": route_reason or None,
        }, message

    message = f"{_execution_node_label(node, fallback='执行节点')} 已完成内部执行"
    return {"agent_type": agent_type or None}, message


def _execute_graph_transform_node(
    *,
    task: dict,
    run: dict,
    node: dict,
) -> tuple[dict[str, Any], str]:
    security_pipeline_result = _execute_security_pipeline_transform_node(run=run, node=node)
    if security_pipeline_result is not None:
        return security_pipeline_result

    dispatch_context = _run_dispatch_context(run) or {}
    route_decision = _dispatch_context_route_decision(dispatch_context) or route_decision_from_task(task) or {}
    manager_packet = _manager_packet_for_run(task, run)
    label = _execution_node_label(node, fallback="转换节点")

    if "规划" in label:
        route_reason = str(
            route_decision.get("route_reason_summary") or route_decision.get("routeReasonSummary") or ""
        ).strip()
        current_owner = str(manager_packet.get("next_owner") or "").strip()
        message = route_reason or "已生成 route_decision、manager_packet 和 execution_plan"
        return {
            "route_reason_summary": route_reason or None,
            "current_owner": current_owner or None,
        }, message

    if "验收" in label:
        current_result = _graph_current_or_upstream_result(task, run)
        accepted = _is_valid_task_result_payload(current_result)
        acceptance = {
            "accepted": accepted,
            "outbound_safe": accepted,
            "result_kind": str((current_result or {}).get("kind") or "").strip() or None
            if isinstance(current_result, dict)
            else None,
        }
        dispatch_context["acceptance"] = acceptance
        message = "已完成执行结果验收，准备进入出站复核" if accepted else "验收未通过，已转向人工接管路径"
        return acceptance, message

    if "复核" in label:
        outbound_review = {
            "passed": True,
            "reviewed_at": store.now_string(),
        }
        dispatch_context["outbound_review"] = outbound_review
        current_result = _graph_current_or_upstream_result(task, run)
        if isinstance(current_result, dict):
            preserved_result = store.clone(current_result)
            assert isinstance(preserved_result, dict)
            preserved_result["outbound_review"] = store.clone(outbound_review)
            return preserved_result, "已完成出站安全复核，准备统一回传"
        return {"outbound_review": outbound_review}, "已完成出站安全复核，准备统一回传"

    note = _node_config_text(node, "transform_note") or label
    return {"transform_note": note}, f"{label} 已完成结果整理"


def _workflow_result_payload_snapshot(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: store.clone(value)
        for key, value in result.items()
        if key not in {"return_payload", "returnPayload"}
    }


def _graph_current_or_upstream_result(task: dict, run: dict) -> dict[str, Any] | None:
    return _workflow_upstream_result(task=task, run=run)


def _apply_output_node_contract_to_result(
    *,
    task: dict,
    run: dict,
    node: dict,
    result: dict[str, Any],
) -> dict[str, Any]:
    normalized_result = store.clone(result)
    handoff_target = _node_config_text(node, "handoffTarget", "handoff_target")
    conversation_stage = _node_config_text(node, "conversationStage", "conversation_stage")
    existing_handoff_target = alias_text(normalized_result, "handoff_target", "handoffTarget")
    existing_conversation_stage = alias_text(
        normalized_result,
        "conversation_stage",
        "conversationStage",
    )

    resolved_handoff_target = existing_handoff_target or handoff_target
    resolved_conversation_stage = existing_conversation_stage or conversation_stage
    result_status = (
        alias_text(normalized_result, "result_status", "resultStatus")
        or str(task.get("status") or run.get("status") or "completed").strip().lower()
    )
    if result_status not in TERMINAL_TASK_STATUSES:
        result_status = "completed"

    if resolved_handoff_target:
        normalized_result["handoff_target"] = resolved_handoff_target
        normalized_result["handoffTarget"] = resolved_handoff_target
    if resolved_conversation_stage:
        normalized_result["conversation_stage"] = resolved_conversation_stage
        normalized_result["conversationStage"] = resolved_conversation_stage

    normalized_result["result_status"] = result_status
    normalized_result["resultStatus"] = result_status
    normalized_result["output_node_id"] = str(node.get("id") or "").strip() or None
    normalized_result["outputNodeId"] = normalized_result["output_node_id"]
    normalized_result["output_node_label"] = _execution_node_label(node, fallback="输出节点")
    normalized_result["outputNodeLabel"] = normalized_result["output_node_label"]

    if "return_payload" not in normalized_result and "returnPayload" not in normalized_result:
        payload_snapshot = _workflow_result_payload_snapshot(normalized_result)
        normalized_result["return_payload"] = payload_snapshot
        normalized_result["returnPayload"] = store.clone(payload_snapshot)

    return normalized_result


def _build_graph_output_result(task: dict, run: dict, node: dict) -> dict[str, Any]:
    if _is_security_agent_pipeline_workflow(run=run):
        return _build_security_pipeline_output_result(task, run, node)

    manager_packet = _manager_packet_for_run(task, run)
    label = _execution_node_label(node, fallback="输出节点")
    current_result = _graph_current_or_upstream_result(task, run)
    result: dict[str, Any]
    if _is_professional_agent_workflow(run=run):
        summary = "专业工作流接口已通过，当前为占位链路"
        content = (
            "已按“专业工作流 -> 专业工作流下发任务 -> 找寻专业工作流 -> 执行专业工作流 -> 返回进程”完成占位轮转。"
            "当前仅保留接口，暂时默认通过，后续在这里挂接具体专业事件。"
        )
        result = {
            "kind": "help_note",
            "title": "专业agent工作流",
            "summary": summary,
            "content": content,
            "text": f"{summary}\n\n{content}",
            "bullets": ["当前仅保留专业工作流接口，暂时默认通过。"],
            "references": [],
        }
    elif _is_free_agent_workflow(run=run):
        summary = "自由工作流接口已通过，当前为占位链路"
        content = (
            "已按“自由工作流 -> 自由工作流下发任务 -> 在外接触手库中找寻对应的角色来 -> 执行自由工作流 -> 返回进程”完成占位轮转。"
            "当前仅保留接口，暂时默认通过，后续在这里挂接具体自由事件。"
        )
        result = {
            "kind": "help_note",
            "title": "自由agent工作流",
            "summary": summary,
            "content": content,
            "text": f"{summary}\n\n{content}",
            "bullets": ["当前仅保留自由工作流接口，暂时默认通过。"],
            "references": [],
        }
    elif "统一回传" in label and _is_valid_task_result_payload(current_result):
        result = store.clone(current_result)
    elif "澄清" in label or "确认" in label:
        if _is_valid_task_result_payload(current_result):
            result = store.clone(current_result)
        else:
            language = _output_language(task)
            fallback_text = (
                "I am here. Tell me what you want to move forward and I will continue from there."
                if language == "en"
                else "我在。你直接说你想了解或推进什么，我马上接着处理。"
            )
            result = {
                "kind": "chat_reply",
                "title": "对话接待回复",
                "summary": fallback_text,
                "content": fallback_text,
                "text": fallback_text,
                "bullets": [],
                "references": [],
            }
    elif "人工接管" in label or "部分完成" in label:
        summary = "当前自动链路已暂停，等待人工接管或补件"
        content = (
            str((current_result or {}).get("summary") or "").strip()
            if isinstance(current_result, dict)
            else ""
        ) or "当前结果尚不足以自动闭环，系统已转入人工接管。"
        result = {
            "kind": "help_note",
            "title": "已转人工接管",
            "summary": summary,
            "content": content,
            "text": f"{summary}\n\n{content}",
            "bullets": [],
        }
    elif "安全" in label:
        message = "当前请求未通过安全校验，系统已阻断后续自动执行。"
        result = {
            "kind": "help_note",
            "title": "请求已阻断",
            "summary": message,
            "content": message,
            "text": message,
            "bullets": [],
        }
    elif _is_valid_task_result_payload(current_result):
        result = store.clone(current_result)
    else:
        result = _build_help_result(task, run)
    return _apply_output_node_contract_to_result(task=task, run=run, node=node, result=result)


def _refresh_sequential_progress_locked(
    *,
    task: dict,
    run: dict,
    steps: list[dict],
    auto_schedule: bool,
) -> dict:
    task["tokens"] = sum(max(int(step.get("tokens") or 0), 0) for step in steps)
    refreshed_run = _refresh_run_state(run, task)
    _publish_run_event(refreshed_run, "workflow_run.updated")
    _persist_execution_state(task=task, steps=steps, run=refreshed_run)
    if auto_schedule and task["status"] in {"pending", "running"} and not _task_confirmation_pending(task):
        _schedule_follow_up(refreshed_run["id"])
    return refreshed_run


def _advance_sequential_workflow_run_locked(
    *,
    task: dict,
    run: dict,
    steps: list[dict],
    workflow: dict,
    mode: str,
    auto_schedule: bool,
) -> dict:
    resolved_intent = _resolve_tick_intent(run, workflow)
    run["intent"] = resolved_intent
    graph_state = _ensure_sequential_graph_state(run, workflow)
    nodes_by_id = _workflow_nodes_by_id(workflow)
    max_iterations = 1 if mode in {"dispatch", "execute"} else max(len(nodes_by_id) * 6, 12)

    for _ in range(max_iterations):
        current_node_id = str(graph_state.get("current_node_id") or "").strip()
        if not current_node_id:
            if _is_valid_task_result_payload(task.get("result")):
                final_step = next((step for step in reversed(steps) if _step_node_id(step)), None)
                if final_step is not None:
                    return _finalize_agent_task_result_locked(
                        task=task,
                        run=run,
                        steps=steps,
                        execution_step=final_step,
                        task_result=store.clone(task["result"]),
                        execution_agent=None,
                    )
            return _refresh_sequential_progress_locked(
                task=task,
                run=run,
                steps=steps,
                auto_schedule=auto_schedule,
            )

        node = nodes_by_id.get(current_node_id)
        if node is None:
            return _fail_workflow_run_due_execution_target_error_locked(
                task=task,
                run=run,
                steps=steps,
                failure_message=f"工作流节点 {current_node_id} 不存在，任务已终止",
                failure_stage="dispatch",
            )

        running_step = _execution_step_for_node(steps, node)
        if running_step is None or running_step.get("status") != "running":
            _close_graph_waiting_step(steps, next_label=_execution_node_label(node, fallback="执行节点"))
            running_step = _append_node_step(
                task_id=task["id"],
                node=node,
                status="running",
                agent=_graph_step_agent_name(node),
                message=f"{_execution_node_label(node, fallback='执行节点')} 开始执行",
                tokens=64 if _normalize_workflow_node_type(node.get("type")) == "agent" else 0,
            )
            task["status"] = "running"
            task["agent"] = running_step["agent"]
            _mark_graph_node_running(graph_state, node, running_step)
            _mark_dispatch_context_state(
                run,
                "executing",
                current_node_id=current_node_id,
                current_node_label=_execution_node_label(node, fallback="执行节点"),
            )
            _sync_selected_node_context(run, node=node)
            if mode == "dispatch":
                return _refresh_sequential_progress_locked(
                    task=task,
                    run=run,
                    steps=steps,
                    auto_schedule=auto_schedule,
                )

        node_type = _normalize_workflow_node_type(node.get("type"))
        task_result: dict[str, Any] | None = None
        execution_agent = None

        if node_type == "agent":
            agent_type = _derive_agent_type(node) or str(_derive_agent_binding(node) or "").strip().lower()
            agent_binding = _derive_agent_binding(node)
            if agent_type in {"search", "write", "help", "conversation"} or agent_binding == "general_assistant":
                expected_agent_type = agent_type if agent_type in {"search", "write", "conversation"} else None
                route_seed = _execution_route_seed(
                    run=run,
                    workflow=workflow,
                    agent_type=expected_agent_type,
                )
                dispatch_execution_agent_id = _dispatch_context_execution_agent_id(_run_dispatch_context(run))
                execution_agent = (
                    _resolve_agent_binding(
                        dispatch_execution_agent_id,
                        expected_type=expected_agent_type,
                        route_seed=route_seed,
                    )
                    if dispatch_execution_agent_id
                    else None
                )
                if execution_agent is None:
                    execution_agent = _resolve_agent_binding(
                        _derive_agent_binding(node),
                        expected_type=expected_agent_type,
                        route_seed=route_seed,
                    )
                if execution_agent is None:
                    if agent_type == "conversation":
                        internal_result, message = _execute_internal_graph_agent_node(task=task, run=run, node=node)
                        task_result = internal_result
                        running_step["status"] = "completed"
                        running_step["finished_at"] = store.now_string()
                        running_step["message"] = message
                        _mark_graph_node_completed(
                            graph_state,
                            node,
                            message=message,
                            tokens=int(running_step.get("tokens") or 0),
                            started_at=running_step.get("started_at"),
                            result=internal_result,
                        )
                        execution_agent = None
                    else:
                        return _fail_workflow_run_due_unavailable_agent(
                            task,
                            run,
                            steps,
                            failure_message="选定工作流缺少可用的执行 Agent，任务已终止",
                        )
                else:
                    _mark_execution_agent_started(execution_agent)
                    task_result, failure_run = _execute_agent_task_with_locked_failures(
                        task=task,
                        run=run,
                        execution_agent=execution_agent,
                    )
                    if failure_run is not None:
                        _mark_graph_node_error(
                            graph_state,
                            node,
                            message=str(running_step.get("message") or "Agent 执行失败"),
                        )
                        return failure_run
            else:
                internal_result, message = _execute_internal_graph_agent_node(task=task, run=run, node=node)
                task_result = internal_result
                running_step["status"] = "completed"
                running_step["finished_at"] = store.now_string()
                running_step["message"] = message
                _mark_graph_node_completed(
                    graph_state,
                    node,
                    message=message,
                    tokens=int(running_step.get("tokens") or 0),
                    started_at=running_step.get("started_at"),
                    result=internal_result,
                )

        elif node_type == "tool":
            task_result, failure_run = _execute_tool_node_locked(
                task=task,
                run=run,
                steps=steps,
                node=node,
            )
            if failure_run is not None:
                _mark_graph_node_error(graph_state, node, message="工具节点执行失败")
                return failure_run

        elif node_type == "workflow":
            task_result, failure_run = _execute_workflow_node_locked(
                task=task,
                run=run,
                steps=steps,
                node=node,
            )
            if failure_run is not None:
                _mark_graph_node_error(graph_state, node, message="子工作流执行失败")
                return failure_run

        elif node_type == "condition":
            if _is_security_agent_pipeline_workflow(workflow=workflow):
                task_result, message, next_node_id = _execute_security_pipeline_condition_node(
                    run=run,
                    node=node,
                )
                edge_id = None
            else:
                next_node_id, edge_id = _graph_next_node_after(
                    workflow=workflow,
                    node=node,
                    task=task,
                    run=run,
                    graph_state=graph_state,
                )
                next_node = nodes_by_id.get(next_node_id or "")
                message = (
                    f"条件已完成判断，进入 {next_node['label']}"
                    if next_node is not None
                    else "条件已完成判断，但未找到后续节点"
                )
                task_result = {"next_node_id": next_node_id, "edge_id": edge_id}
            running_step["status"] = "completed"
            running_step["finished_at"] = store.now_string()
            running_step["message"] = message
            _mark_graph_node_completed(
                graph_state,
                node,
                message=message,
                tokens=0,
                started_at=running_step.get("started_at"),
                result=task_result,
            )
            graph_state["current_node_id"] = next_node_id
            if edge_id:
                selected_edges = graph_state.setdefault("selected_edge_ids", [])
                if edge_id not in selected_edges:
                    selected_edges.append(edge_id)
            if mode == "execute":
                return _refresh_sequential_progress_locked(
                    task=task,
                    run=run,
                    steps=steps,
                    auto_schedule=auto_schedule,
                )
            continue

        elif node_type == "transform":
            transform_result, message = _execute_graph_transform_node(task=task, run=run, node=node)
            task_result = transform_result
            running_step["status"] = "completed"
            running_step["finished_at"] = store.now_string()
            running_step["message"] = message
            _mark_graph_node_completed(
                graph_state,
                node,
                message=message,
                tokens=0,
                started_at=running_step.get("started_at"),
                result=transform_result,
            )

        elif node_type == "output":
            output_result = _build_graph_output_result(task, run, node)
            delivery_message = (
                str(output_result.get("summary") or "").strip()
                or str(output_result.get("title") or "").strip()
                or f"{node['label']} 已完成回传"
            )
            running_step["status"] = "completed"
            running_step["finished_at"] = store.now_string()
            running_step["message"] = delivery_message
            _mark_graph_node_completed(
                graph_state,
                node,
                message=delivery_message,
                tokens=0,
                started_at=running_step.get("started_at"),
                result=output_result,
            )
            task["result"] = store.clone(output_result)
            graph_state["current_node_id"] = None
            return _finalize_agent_task_result_locked(
                task=task,
                run=run,
                steps=steps,
                execution_step=running_step,
                task_result=output_result,
                execution_agent=None,
                append_output_step=False,
            )

        else:
            message = f"{_execution_node_label(node, fallback='执行节点')} 已完成"
            running_step["status"] = "completed"
            running_step["finished_at"] = store.now_string()
            running_step["message"] = message
            _mark_graph_node_completed(
                graph_state,
                node,
                message=message,
                tokens=0,
                started_at=running_step.get("started_at"),
            )

        if task_result is not None and running_step.get("status") == "running":
            result_label = _graph_result_label(task_result)
            completion_message = f"{running_step['agent']} 已完成本轮执行，产出「{result_label}」"
            running_step["status"] = "completed"
            running_step["finished_at"] = store.now_string()
            running_step["message"] = completion_message
            _mark_graph_node_completed(
                graph_state,
                node,
                message=completion_message,
                tokens=int(running_step.get("tokens") or 0),
                started_at=running_step.get("started_at"),
                result=task_result,
            )
            task["result"] = store.clone(task_result)

        next_node_id, edge_id = _graph_next_node_after(
            workflow=workflow,
            node=node,
            task=task,
            run=run,
            graph_state=graph_state,
        )
        graph_state["current_node_id"] = next_node_id
        if edge_id:
            selected_edges = graph_state.setdefault("selected_edge_ids", [])
            if edge_id not in selected_edges:
                selected_edges.append(edge_id)

        if next_node_id:
            if mode == "execute":
                return _refresh_sequential_progress_locked(
                    task=task,
                    run=run,
                    steps=steps,
                    auto_schedule=auto_schedule,
                )
            continue

        if _is_valid_task_result_payload(task_result):
            return _finalize_agent_task_result_locked(
                task=task,
                run=run,
                steps=steps,
                execution_step=running_step,
                task_result=task_result,
                execution_agent=execution_agent,
            )

        if isinstance(task_result, dict):
            return _finalize_sequential_leaf_result_locked(
                task=task,
                run=run,
                steps=steps,
                execution_step=running_step,
                task_result=task_result,
                execution_agent=execution_agent,
            )

        return _refresh_sequential_progress_locked(
            task=task,
            run=run,
            steps=steps,
            auto_schedule=auto_schedule,
        )

    return _refresh_sequential_progress_locked(
        task=task,
        run=run,
        steps=steps,
        auto_schedule=auto_schedule,
    )


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
    preferred_language: str | None = None,
    detected_lang: str | None = None,
    dispatch_context: dict | None = None,
    eager_start: bool = False,
    auto_schedule: bool = True,
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
        "preferred_language": preferred_language,
        "detected_lang": detected_lang,
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
                **(store.clone(dispatch_context) if isinstance(dispatch_context, dict) else {}),
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
    if auto_schedule and task["status"] in {"pending", "running"}:
        if eager_start and _should_eager_start_in_local_fallback():
            refreshed_run = _eager_progress_workflow_run(
                refreshed_run["id"],
                follow_up_scheduler=_schedule_manual_auto_progress,
            )
        else:
            _schedule_manual_auto_progress(refreshed_run["id"])
    return {
        "task": store.clone(task),
        "run": store.clone(refreshed_run),
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
    technical_detail: str | None = None,
) -> dict:
    normalized_failure_message = str(failure_message or "").strip() or AGENT_FATAL_FAILURE_USER_MESSAGE
    normalized_technical_detail = str(technical_detail or "").strip() or None
    if task is not None:
        _refresh_task_steps_from_database(task["id"])
    timestamp = store.now_string()

    if task is None:
        run["status"] = "failed"
        run["updated_at"] = timestamp
        run["completed_at"] = timestamp
        _record_agent_fatal_risk_context(run, detail=normalized_technical_detail)
        _mark_dispatch_context_failure(
            run,
            state="agent_execution_failed",
            failure_stage="execution",
            failure_message=normalized_failure_message,
            technical_detail=normalized_technical_detail,
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
        running_step["message"] = normalized_failure_message
    else:
        _append_step(
            task_id=task["id"],
            title="Agent 执行失败",
            status="failed",
            agent="Agent Execution Worker",
            message=normalized_failure_message,
            tokens=0,
        )

    task["status"] = "failed"
    task["completed_at"] = timestamp
    task["duration"] = task.get("duration") or "Agent 执行失败"
    task["result"] = _build_agent_fatal_risk_payload(detail=normalized_technical_detail)
    assistant_message = channel_outbound_service.render_task_failure_text(task, normalized_failure_message)
    delivery = _delivery_message_for_failure(task, run, normalized_failure_message)
    _append_visible_assistant_conversation_message(task, run, assistant_message)
    _record_agent_fatal_risk_context(run, detail=normalized_technical_detail)
    dispatch_context = _ensure_run_dispatch_context(run)
    dispatch_context["delivery_fact_context"] = _build_delivery_fact_context(
        task=task,
        run=run,
        delivery=delivery,
        task_result=task.get("result"),
    )
    _record_delivery_state(run, delivery)
    _mark_dispatch_context_failure(
        run,
        state="agent_execution_failed",
        failure_stage="execution",
        failure_message=normalized_failure_message,
        technical_detail=normalized_technical_detail,
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
            failure_message=AGENT_FATAL_FAILURE_USER_MESSAGE,
            technical_detail=failure_message,
        )


def _fail_workflow_run_due_unavailable_agent(
    task: dict,
    run: dict,
    steps: list[dict],
    *,
    failure_message: str,
    execution_agent: dict | None = None,
) -> dict:
    normalized_technical_detail = str(failure_message or "").strip() or "执行 Agent 不可用"
    normalized_failure_message = AGENT_FATAL_FAILURE_USER_MESSAGE

    timestamp = store.now_string()
    active_step = next((step for step in reversed(steps) if step.get("status") == "running"), None)
    if active_step is not None:
        active_step["status"] = "failed"
        active_step["finished_at"] = timestamp
        active_step["message"] = normalized_failure_message
    else:
        _append_step(
            task_id=task["id"],
            title="执行异常",
            status="failed",
            agent="Dispatcher Agent",
            message=normalized_failure_message,
            tokens=0,
        )

    task["status"] = "failed"
    task["completed_at"] = timestamp
    task["duration"] = task.get("duration") or "执行Agent不可用"
    task["result"] = _build_agent_fatal_risk_payload(detail=normalized_technical_detail)
    assistant_message = channel_outbound_service.render_task_failure_text(task, normalized_failure_message)
    delivery = _delivery_message_for_failure(task, run, normalized_failure_message)
    _append_visible_assistant_conversation_message(task, run, assistant_message)
    _record_agent_fatal_risk_context(run, detail=normalized_technical_detail)
    dispatch_context = _ensure_run_dispatch_context(run)
    dispatch_context["delivery_fact_context"] = _build_delivery_fact_context(
        task=task,
        run=run,
        delivery=delivery,
        task_result=task.get("result"),
    )
    _record_delivery_state(run, delivery)
    _mark_dispatch_context_failure(
        run,
        state="failed",
        failure_stage="dispatch",
        failure_message=normalized_failure_message,
        technical_detail=normalized_technical_detail,
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
    append_output_step: bool = True,
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
    _append_visible_assistant_conversation_message(task, run, assistant_message)
    execution_step["status"] = "completed"
    execution_step["finished_at"] = store.now_string()
    execution_step["message"] = f"{execution_step['agent']} 已完成本轮执行，产出「{result_label}」"
    _append_orchestration_steps(task_id=task["id"], orchestration_steps=orchestration_steps)

    if append_output_step and not _find_step(steps, "发送结果", "输出", "回传"):
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


def _finalize_sequential_leaf_result_locked(
    *,
    task: dict,
    run: dict,
    steps: list[dict],
    execution_step: dict,
    task_result: dict,
    execution_agent: dict | None,
) -> dict:
    orchestration_steps = task_result.pop("orchestration_steps", None)
    result_label = _graph_result_label(task_result)
    execution_step["status"] = "completed"
    execution_step["finished_at"] = store.now_string()
    execution_step["message"] = f"{execution_step['agent']} 已完成本轮执行，产出「{result_label}」"
    _append_orchestration_steps(task_id=task["id"], orchestration_steps=orchestration_steps)

    task["status"] = "completed"
    task["completed_at"] = store.now_string()
    task["duration"] = task.get("duration") or "自动完成"
    task["tokens"] = sum(step.get("tokens", 0) for step in steps)
    task["agent"] = execution_step["agent"]
    task["result"] = task_result

    _mark_dispatch_context_state(
        run,
        "completed",
        completed_at=task["completed_at"],
        result_kind=str(task_result.get("kind") or "").strip() or None,
    )
    if execution_agent is not None:
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
    _sync_selected_node_context(run, node=selected_node, label_override=execution_target_name)
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
    _append_visible_assistant_conversation_message(task, run, assistant_message)
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
    if _workflow_uses_sequential_execution(workflow, run=run):
        return _advance_sequential_workflow_run_locked(
            task=task,
            run=run,
            steps=steps,
            workflow=workflow,
            mode=mode,
            auto_schedule=auto_schedule,
        )

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
    _append_visible_assistant_conversation_message(task, run, assistant_message)
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
        if workflow is not None and _workflow_uses_sequential_execution(workflow, run=run):
            return _advance_workflow_run_locked(
                str(run.get("id") or ""),
                mode="tick",
                auto_schedule=False,
            )
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
