from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.modules.reception.schemas.intake_console import (
    IntakeActiveTaskPreview,
    IntakeAdmissionEvent,
    IntakeConsoleOverviewResponse,
    IntakeHermesEvent,
    IntakeKnowledgeHitPreview,
    IntakeReceptionSession,
    IntakeSecurityEvent,
    IntakeTraceDetailResponse,
    IntakeTraceLogEntry,
    IntakeStatusSummary,
)
from app.platform.persistence.persistence_service import persistence_service
from app.platform.persistence.runtime_store import store


INTAKE_OVERVIEW_LOG_LIMIT = 300
INTAKE_ADMISSION_EVENT_LIMIT = 40
INTAKE_SECURITY_EVENT_LIMIT = 30
INTAKE_HERMES_EVENT_LIMIT = 30
INTAKE_RECEPTION_SESSION_LIMIT = 12
INTAKE_STATUSES = {"passed", "pending_verification", "rejected", "security_blocked"}
RECEPTION_SESSION_STATES = {"serving", "replied", "failed"}


def _parse_datetime(value: object) -> datetime:
    normalized = str(value or "").strip()
    if not normalized:
        return datetime.min.replace(tzinfo=UTC)
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)


def _load_operational_logs(*, limit: int) -> list[dict[str, Any]]:
    database_logs = persistence_service.list_operational_logs(limit=limit)
    if database_logs is not None:
        return database_logs
    return store.clone(getattr(store, "operational_logs", []))[:limit]


def _matches_filters(
    log: dict[str, Any],
    *,
    tenant_id: str | None,
    channel: str | None,
) -> bool:
    metadata = _log_metadata(log)
    if tenant_id:
        candidate = _metadata_text(metadata, "tenant_id", "tenantId")
        if candidate != tenant_id:
            return False
    if channel:
        candidate = _metadata_text(metadata, "channel")
        if str(candidate or "").strip().lower() != channel:
            return False
    return True


def _load_profile_index() -> dict[str, dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    list_profiles = getattr(persistence_service, "list_user_profiles", None)
    if callable(list_profiles):
        for profile in list_profiles() or []:
            if not isinstance(profile, dict):
                continue
            profile_id = str(profile.get("id") or "").strip()
            if profile_id:
                items[profile_id] = profile
    for profile_id, profile in store.user_profiles.items():
        if not isinstance(profile, dict):
            continue
        normalized_profile_id = str(profile_id or profile.get("id") or "").strip()
        if normalized_profile_id:
            items[normalized_profile_id] = profile
    return items


def _metadata_text(metadata: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = str(metadata.get(key) or "").strip()
        if value:
            return value
    return None


def _metadata_int(metadata: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = metadata.get(key)
        if value in {None, ""}:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def _log_agent(log: dict[str, Any]) -> str:
    return str(log.get("agent") or "").strip()


def _resolve_person_name(
    *,
    metadata: dict[str, Any],
    profile_index: dict[str, dict[str, Any]],
) -> str | None:
    direct_name = _metadata_text(
        metadata,
        "person_name",
        "personName",
        "display_name",
        "displayName",
        "contact_name",
        "contactName",
        "name",
    )
    if direct_name:
        return direct_name

    profile_id = _metadata_text(
        metadata,
        "profile_id",
        "profileId",
        "user_profile_id",
        "userProfileId",
    )
    if not profile_id:
        return None

    profile = profile_index.get(profile_id)
    if not isinstance(profile, dict):
        return None

    return _metadata_text(
        profile,
        "name",
        "contact_name",
        "contactName",
        "display_name",
        "displayName",
    )


def _log_metadata(log: dict[str, Any]) -> dict[str, Any]:
    metadata = log.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _knowledge_hits_preview(metadata: dict[str, Any]) -> list[IntakeKnowledgeHitPreview]:
    raw_items = metadata.get("knowledge_hits_preview") or metadata.get("knowledgeHitsPreview")
    if not isinstance(raw_items, list):
        return []

    items: list[IntakeKnowledgeHitPreview] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        title = str(raw_item.get("title") or "").strip()
        if not title:
            continue
        score_value = raw_item.get("score")
        score: float | None = None
        if score_value not in {None, ""}:
            try:
                score = float(score_value)
            except (TypeError, ValueError):
                score = None
        items.append(
            IntakeKnowledgeHitPreview(
                title=title,
                source=str(raw_item.get("source") or "").strip() or None,
                summary=str(raw_item.get("summary") or "").strip() or None,
                scope=str(raw_item.get("scope") or "").strip() or None,
                score=score,
            )
        )
    return items


def _active_task_preview_from_metadata(metadata: dict[str, Any]) -> IntakeActiveTaskPreview | None:
    raw_context = metadata.get("active_task_context") or metadata.get("activeTaskContext")
    if isinstance(raw_context, dict):
        task_id = _metadata_text(raw_context, "task_id", "taskId")
        if task_id:
            return IntakeActiveTaskPreview(
                task_id=task_id,
                title=_metadata_text(raw_context, "title"),
                status=_metadata_text(raw_context, "status"),
                summary=_metadata_text(raw_context, "summary"),
                updated_at=_metadata_text(raw_context, "updated_at", "updatedAt"),
            )

    task_id = _metadata_text(metadata, "active_task_id", "activeTaskId")
    if not task_id:
        return None
    return IntakeActiveTaskPreview(task_id=task_id)


def _active_task_preview(session_logs: list[dict[str, Any]]) -> IntakeActiveTaskPreview | None:
    for log in session_logs:
        preview = _active_task_preview_from_metadata(_log_metadata(log))
        if preview is not None:
            return preview
    return None


def _find_trace_task_created_log(trace_logs: list[dict[str, Any]]) -> dict[str, Any] | None:
    for log in trace_logs:
        metadata = _log_metadata(log)
        if _metadata_text(metadata, "event") != "task_created_from_hermes":
            continue
        if str(log.get("task_id") or "").strip():
            return log
    return None


def _active_task_preview_from_trace_logs(trace_logs: list[dict[str, Any]]) -> IntakeActiveTaskPreview | None:
    task_log = _find_trace_task_created_log(trace_logs)
    if task_log is None:
        return None
    task_id = str(task_log.get("task_id") or "").strip()
    if not task_id:
        return None
    task = persistence_service.get_task(task_id)
    if isinstance(task, dict):
        return IntakeActiveTaskPreview(
            task_id=task_id,
            title=_metadata_text(task, "title"),
            status=_metadata_text(task, "status"),
            summary=_metadata_text(task, "description"),
            updated_at=_metadata_text(task, "updated_at", "updatedAt", "created_at", "createdAt"),
        )
    return IntakeActiveTaskPreview(task_id=task_id)


def _normalized_task_signal(metadata: dict[str, Any], trace_logs: list[dict[str, Any]]) -> str | None:
    interaction_mode = _metadata_text(metadata, "interaction_mode", "interactionMode")
    if interaction_mode == "task":
        return "dispatch_task"

    task_signal = _metadata_text(metadata, "task_signal", "taskSignal")
    if task_signal:
        return task_signal

    task_log = _find_trace_task_created_log(trace_logs)
    if task_log is None:
        return None
    task_metadata = _log_metadata(task_log)
    task_signal = _metadata_text(task_metadata, "task_signal", "taskSignal")
    if task_signal:
        return task_signal
    if _metadata_text(task_metadata, "interaction_mode", "interactionMode") == "task":
        return "dispatch_task"
    return None


def _is_intake_admission_log(log: dict[str, Any]) -> bool:
    metadata = _log_metadata(log)
    status = str(metadata.get("intake_status") or "").strip()
    return (
        str(metadata.get("intake_event_kind") or "").strip() == "admission"
        and status in INTAKE_STATUSES
    )


def _is_reception_session_log(log: dict[str, Any]) -> bool:
    metadata = _log_metadata(log)
    state = str(metadata.get("reception_session_state") or "").strip()
    return (
        str(metadata.get("intake_event_kind") or "").strip() == "session"
        and str(metadata.get("agent_role") or "").strip() == "hermes_reception"
        and state in RECEPTION_SESSION_STATES
    )


def _is_hermes_output_security_block_log(log: dict[str, Any]) -> bool:
    if not _is_intake_admission_log(log):
        return False
    metadata = _log_metadata(log)
    return (
        str(metadata.get("intake_status") or "").strip() == "security_blocked"
        and _log_agent(log) == "Hermes 回传安全监听"
    )


def _build_admission_event(
    log: dict[str, Any],
    *,
    profile_index: dict[str, dict[str, Any]],
) -> IntakeAdmissionEvent | None:
    metadata = _log_metadata(log)
    status = str(metadata.get("intake_status") or "").strip()
    if status not in INTAKE_STATUSES:
        return None

    missing_fields = metadata.get("missing_fields")
    return IntakeAdmissionEvent(
        id=str(log.get("id") or ""),
        timestamp=str(log.get("timestamp") or ""),
        status=status,
        agent=str(log.get("agent") or "接入层"),
        message=str(log.get("message") or ""),
        tenant_id=_metadata_text(metadata, "tenant_id", "tenantId"),
        tenant_name=_metadata_text(metadata, "tenant_name", "tenantName"),
        profile_id=_metadata_text(metadata, "profile_id", "profileId", "user_profile_id", "userProfileId"),
        customer_id=_metadata_text(metadata, "customer_id", "customerId"),
        person_name=_resolve_person_name(metadata=metadata, profile_index=profile_index),
        channel=_metadata_text(metadata, "channel"),
        platform_user_id=_metadata_text(metadata, "platform_user_id", "platformUserId"),
        service_code=_metadata_text(metadata, "service_code", "serviceCode"),
        session_id=_metadata_text(metadata, "session_id", "sessionId"),
        trace_id=str(log.get("trace_id") or "").strip() or None,
        missing_fields=[
            str(item).strip()
            for item in (missing_fields if isinstance(missing_fields, list) else [])
            if str(item).strip()
        ],
        reason=_metadata_text(metadata, "reason", "detail"),
    )


def _session_key(metadata: dict[str, Any], log: dict[str, Any]) -> str:
    return (
        _metadata_text(metadata, "session_id", "sessionId")
        or _metadata_text(metadata, "channel")
        and (
            f"{_metadata_text(metadata, 'channel')}:{_metadata_text(metadata, 'platform_user_id', 'platformUserId') or 'anonymous'}"
        )
        or str(log.get("trace_id") or "").strip()
        or str(log.get("id") or "").strip()
    )


def _session_key_from_log(log: dict[str, Any]) -> str:
    return _session_key(_log_metadata(log), log)


def _latest_session_metadata_text(
    session_logs: list[dict[str, Any]],
    *keys: str,
) -> str | None:
    for log in session_logs:
        value = _metadata_text(_log_metadata(log), *keys)
        if value:
            return value
    return None


def _latest_input_admission_log(admission_logs: list[dict[str, Any]]) -> dict[str, Any] | None:
    for log in admission_logs:
        if _is_hermes_output_security_block_log(log):
            continue
        return log
    return None


def _derive_input_security_status(admission_logs: list[dict[str, Any]]) -> str | None:
    log = _latest_input_admission_log(admission_logs)
    if log is None:
        return None
    return _metadata_text(_log_metadata(log), "intake_status")


def _derive_output_security_status(
    *,
    state: str,
    metadata: dict[str, Any],
) -> str | None:
    if state == "serving":
        return "listening"
    if state == "replied":
        return "passed"
    if _metadata_text(metadata, "event") == "hermes_result_blocked":
        return "blocked"
    if state == "failed":
        return "failed"
    return None


def _derive_current_stage(
    *,
    state: str,
    metadata: dict[str, Any],
) -> str:
    if state == "serving":
        return "Hermes 接待中"
    if state == "failed":
        event = _metadata_text(metadata, "event")
        if event == "hermes_result_blocked":
            return "输出安全阻断"
        if event == "hermes_reception_failed":
            return "Hermes 调用失败"
        return "接待异常"

    interaction_mode = _metadata_text(metadata, "interaction_mode", "interactionMode")
    if interaction_mode == "continuation":
        return "并入当前任务"
    if interaction_mode == "task":
        return "已转任务"
    return "接待回复完成"


def _trace_logs_by_id(logs: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    items: dict[str, list[dict[str, Any]]] = {}
    for log in logs:
        trace_id = str(log.get("trace_id") or "").strip()
        if not trace_id:
            continue
        items.setdefault(trace_id, []).append(log)
    return items


def _find_security_gateway_block_log(trace_logs: list[dict[str, Any]]) -> dict[str, Any] | None:
    for log in trace_logs:
        metadata = _log_metadata(log)
        if str(log.get("source") or "").strip() != "security_gateway":
            continue
        if _metadata_text(metadata, "event") != "message_blocked":
            continue
        return log
    return None


def _find_hermes_block_session_log(trace_logs: list[dict[str, Any]]) -> dict[str, Any] | None:
    for log in trace_logs:
        if not _is_reception_session_log(log):
            continue
        if _metadata_text(_log_metadata(log), "event") == "hermes_result_blocked":
            return log
    return None


def _resolved_security_rule_name(
    *,
    metadata: dict[str, Any],
    gateway_metadata: dict[str, Any],
) -> str | None:
    return _metadata_text(
        metadata,
        "security_rule_name",
        "securityRuleName",
    ) or _metadata_text(
        gateway_metadata,
        "rule_name",
        "ruleName",
    )


def _resolved_security_status_code(
    *,
    metadata: dict[str, Any],
    gateway_metadata: dict[str, Any],
) -> int | None:
    status_code = _metadata_int(metadata, "status_code", "statusCode") or _metadata_int(
        gateway_metadata,
        "status_code",
        "statusCode",
    )
    return status_code or None


def _resolved_output_block_layer(
    *,
    metadata: dict[str, Any],
    gateway_metadata: dict[str, Any],
) -> str | None:
    return (
        _metadata_text(metadata, "security_layer")
        or _metadata_text(gateway_metadata, "layer")
        or ("hermes_result_guard" if _metadata_text(metadata, "event") == "hermes_result_blocked" else None)
    )


def _build_security_event(
    log: dict[str, Any],
    *,
    trace_logs: list[dict[str, Any]],
    profile_index: dict[str, dict[str, Any]],
) -> IntakeSecurityEvent | None:
    metadata = _log_metadata(log)
    status = _metadata_text(metadata, "intake_status")
    if status != "security_blocked":
        return None

    gateway_log = _find_security_gateway_block_log(trace_logs)
    gateway_metadata = _log_metadata(gateway_log or {})
    hermes_block_log = _find_hermes_block_session_log(trace_logs)
    hermes_block_metadata = _log_metadata(hermes_block_log or {})
    block_stage = "Hermes 输出" if _log_agent(log) == "Hermes 回传安全监听" else "渠道输入"

    return IntakeSecurityEvent(
        id=str(log.get("id") or ""),
        timestamp=str(log.get("timestamp") or ""),
        status="security_blocked",
        agent=_log_agent(log) or "安全监听层",
        message=str(log.get("message") or ""),
        block_stage=block_stage,
        security_layer=_resolved_output_block_layer(metadata=metadata, gateway_metadata=gateway_metadata)
        if block_stage == "Hermes 输出"
        else (_metadata_text(metadata, "security_layer") or _metadata_text(gateway_metadata, "layer")),
        security_rule_name=_resolved_security_rule_name(
            metadata=metadata,
            gateway_metadata=gateway_metadata,
        ),
        status_code=_resolved_security_status_code(
            metadata=metadata,
            gateway_metadata=gateway_metadata,
        ),
        tenant_id=_metadata_text(metadata, "tenant_id", "tenantId"),
        tenant_name=_metadata_text(metadata, "tenant_name", "tenantName"),
        profile_id=_metadata_text(metadata, "profile_id", "profileId", "user_profile_id", "userProfileId"),
        customer_id=_metadata_text(metadata, "customer_id", "customerId"),
        person_name=_resolve_person_name(metadata=metadata, profile_index=profile_index),
        channel=_metadata_text(metadata, "channel"),
        platform_user_id=_metadata_text(metadata, "platform_user_id", "platformUserId"),
        service_code=_metadata_text(metadata, "service_code", "serviceCode"),
        session_id=_metadata_text(metadata, "session_id", "sessionId"),
        trace_id=str(log.get("trace_id") or "").strip() or None,
        reason=(
            _metadata_text(metadata, "reason", "detail")
            or _metadata_text(hermes_block_metadata, "reason", "detail")
            or _metadata_text(gateway_metadata, "detail")
        ),
    )


def _build_hermes_event(
    log: dict[str, Any],
    *,
    session_logs: list[dict[str, Any]],
    admission_logs: list[dict[str, Any]],
    trace_logs: list[dict[str, Any]],
    profile_index: dict[str, dict[str, Any]],
) -> IntakeHermesEvent | None:
    metadata = _log_metadata(log)
    input_admission_log = _latest_input_admission_log(admission_logs)
    input_metadata = _log_metadata(input_admission_log or {})
    state = str(metadata.get("reception_session_state") or "").strip()
    if state not in RECEPTION_SESSION_STATES:
        return None
    gateway_metadata = _log_metadata(_find_security_gateway_block_log(trace_logs) or {})

    return IntakeHermesEvent(
        id=str(log.get("id") or ""),
        timestamp=str(log.get("timestamp") or ""),
        state=state,
        agent=_log_agent(log) or "Hermes Reception Agent",
        message=str(log.get("message") or ""),
        current_stage=_derive_current_stage(state=state, metadata=metadata),
        interaction_mode=_metadata_text(metadata, "interaction_mode", "interactionMode"),
        task_signal=_normalized_task_signal(metadata, trace_logs),
        protocol_mode=_metadata_text(metadata, "protocol_mode", "protocolMode"),
        reply_preview=_metadata_text(metadata, "reply_preview", "replyPreview"),
        output_security_status=_derive_output_security_status(state=state, metadata=metadata),
        output_block_layer=(
            _resolved_output_block_layer(metadata=metadata, gateway_metadata=gateway_metadata)
            if _metadata_text(metadata, "event") == "hermes_result_blocked"
            else None
        ),
        output_block_rule_name=(
            _resolved_security_rule_name(metadata=metadata, gateway_metadata=gateway_metadata)
            if _metadata_text(metadata, "event") == "hermes_result_blocked"
            else None
        ),
        output_block_status_code=(
            _resolved_security_status_code(metadata=metadata, gateway_metadata=gateway_metadata)
            if _metadata_text(metadata, "event") == "hermes_result_blocked"
            else None
        ),
        active_task_id=(
            _metadata_text(metadata, "active_task_id", "activeTaskId")
            or _latest_session_metadata_text(session_logs, "active_task_id", "activeTaskId")
            or str((_find_trace_task_created_log(trace_logs) or {}).get("task_id") or "").strip()
        ),
        active_task=_active_task_preview(session_logs) or _active_task_preview_from_trace_logs(trace_logs),
        tenant_id=_metadata_text(metadata, "tenant_id", "tenantId")
        or _metadata_text(input_metadata, "tenant_id", "tenantId"),
        tenant_name=_metadata_text(metadata, "tenant_name", "tenantName")
        or _metadata_text(input_metadata, "tenant_name", "tenantName"),
        profile_id=_metadata_text(metadata, "profile_id", "profileId", "user_profile_id", "userProfileId")
        or _metadata_text(input_metadata, "profile_id", "profileId", "user_profile_id", "userProfileId"),
        customer_id=_metadata_text(metadata, "customer_id", "customerId")
        or _metadata_text(input_metadata, "customer_id", "customerId"),
        person_name=_resolve_person_name(metadata=metadata, profile_index=profile_index)
        or _resolve_person_name(metadata=input_metadata, profile_index=profile_index),
        channel=_metadata_text(metadata, "channel") or _metadata_text(input_metadata, "channel"),
        platform_user_id=_metadata_text(metadata, "platform_user_id", "platformUserId")
        or _metadata_text(input_metadata, "platform_user_id", "platformUserId"),
        service_code=_metadata_text(metadata, "service_code", "serviceCode")
        or _metadata_text(input_metadata, "service_code", "serviceCode"),
        session_id=_metadata_text(metadata, "session_id", "sessionId")
        or _metadata_text(input_metadata, "session_id", "sessionId"),
        trace_id=str(log.get("trace_id") or "").strip() or None,
        reason=_metadata_text(metadata, "reason", "detail"),
        knowledge_hit_count=_metadata_int(metadata, "knowledge_hit_count", "knowledgeHitCount"),
        knowledge_tenant_hits=_metadata_int(metadata, "knowledge_tenant_hits", "knowledgeTenantHits"),
        knowledge_shared_hits=_metadata_int(metadata, "knowledge_shared_hits", "knowledgeSharedHits"),
        knowledge_hits_preview=_knowledge_hits_preview(metadata),
    )


def _build_reception_session(
    session_logs: list[dict[str, Any]],
    admission_logs: list[dict[str, Any]],
    *,
    trace_logs: list[dict[str, Any]],
    profile_index: dict[str, dict[str, Any]],
) -> IntakeReceptionSession | None:
    if not session_logs:
        return None

    log = session_logs[0]
    metadata = _log_metadata(log)
    input_admission_log = _latest_input_admission_log(admission_logs)
    input_metadata = _log_metadata(input_admission_log or {})
    state = str(metadata.get("reception_session_state") or "").strip()
    if state not in RECEPTION_SESSION_STATES:
        return None
    gateway_metadata = _log_metadata(_find_security_gateway_block_log(trace_logs) or {})

    return IntakeReceptionSession(
        session_key=_session_key(metadata, log),
        updated_at=str(log.get("timestamp") or ""),
        state=state,
        agent=str(log.get("agent") or "Hermes Reception Agent"),
        latest_message=str(log.get("message") or ""),
        tenant_id=_metadata_text(metadata, "tenant_id", "tenantId")
        or _metadata_text(input_metadata, "tenant_id", "tenantId"),
        tenant_name=_metadata_text(metadata, "tenant_name", "tenantName")
        or _metadata_text(input_metadata, "tenant_name", "tenantName"),
        profile_id=_metadata_text(metadata, "profile_id", "profileId", "user_profile_id", "userProfileId")
        or _metadata_text(input_metadata, "profile_id", "profileId", "user_profile_id", "userProfileId"),
        customer_id=_metadata_text(metadata, "customer_id", "customerId")
        or _metadata_text(input_metadata, "customer_id", "customerId"),
        person_name=_resolve_person_name(metadata=metadata, profile_index=profile_index)
        or _resolve_person_name(metadata=input_metadata, profile_index=profile_index),
        channel=_metadata_text(metadata, "channel") or _metadata_text(input_metadata, "channel"),
        platform_user_id=_metadata_text(metadata, "platform_user_id", "platformUserId")
        or _metadata_text(input_metadata, "platform_user_id", "platformUserId"),
        service_code=_metadata_text(metadata, "service_code", "serviceCode")
        or _metadata_text(input_metadata, "service_code", "serviceCode"),
        session_id=_metadata_text(metadata, "session_id", "sessionId")
        or _metadata_text(input_metadata, "session_id", "sessionId"),
        trace_id=str(log.get("trace_id") or "").strip() or None,
        current_stage=_derive_current_stage(state=state, metadata=metadata),
        active_task_id=(
            _latest_session_metadata_text(session_logs, "active_task_id", "activeTaskId")
            or str((_find_trace_task_created_log(trace_logs) or {}).get("task_id") or "").strip()
            or None
        ),
        active_task=_active_task_preview(session_logs) or _active_task_preview_from_trace_logs(trace_logs),
        last_interaction_mode=(
            _metadata_text(metadata, "interaction_mode", "interactionMode") if state == "replied" else None
        ),
        last_task_signal=_normalized_task_signal(metadata, trace_logs) if state == "replied" else None,
        last_input_security_status=_derive_input_security_status(admission_logs) or "passed",
        last_output_security_status=_derive_output_security_status(state=state, metadata=metadata),
        output_block_reason=(
            _metadata_text(metadata, "reason", "detail")
            if _metadata_text(metadata, "event") == "hermes_result_blocked"
            else None
        ),
        output_block_layer=(
            _resolved_output_block_layer(metadata=metadata, gateway_metadata=gateway_metadata)
            if _metadata_text(metadata, "event") == "hermes_result_blocked"
            else None
        ),
        output_block_rule_name=(
            _resolved_security_rule_name(metadata=metadata, gateway_metadata=gateway_metadata)
            if _metadata_text(metadata, "event") == "hermes_result_blocked"
            else None
        ),
        output_block_status_code=(
            _resolved_security_status_code(metadata=metadata, gateway_metadata=gateway_metadata)
            if _metadata_text(metadata, "event") == "hermes_result_blocked"
            else None
        ),
        reply_preview=_metadata_text(metadata, "reply_preview", "replyPreview") if state == "replied" else None,
        protocol_mode=_metadata_text(metadata, "protocol_mode", "protocolMode") if state == "replied" else None,
        knowledge_hit_count=_metadata_int(metadata, "knowledge_hit_count", "knowledgeHitCount"),
        knowledge_tenant_hits=_metadata_int(metadata, "knowledge_tenant_hits", "knowledgeTenantHits"),
        knowledge_shared_hits=_metadata_int(metadata, "knowledge_shared_hits", "knowledgeSharedHits"),
        knowledge_hits_preview=_knowledge_hits_preview(metadata),
    )


def _normalize_channel_filter(channel: str | None) -> str | None:
    normalized = str(channel or "").strip().lower()
    return normalized or None


def get_intake_console_overview(
    *,
    tenant_id: str | None = None,
    channel: str | None = None,
) -> IntakeConsoleOverviewResponse:
    normalized_tenant_id = str(tenant_id or "").strip() or None
    normalized_channel = _normalize_channel_filter(channel)
    logs = sorted(
        _load_operational_logs(limit=INTAKE_OVERVIEW_LOG_LIMIT),
        key=lambda item: _parse_datetime(item.get("timestamp")),
        reverse=True,
    )
    profile_index = _load_profile_index()
    filtered_logs = [
        log
        for log in logs
        if _matches_filters(
            log,
            tenant_id=normalized_tenant_id,
            channel=normalized_channel,
        )
    ]
    trace_logs_index = _trace_logs_by_id(logs)

    summary = IntakeStatusSummary()
    admission_events: list[IntakeAdmissionEvent] = []
    admission_logs_by_session: dict[str, list[dict[str, Any]]] = {}
    session_logs_by_session: dict[str, list[dict[str, Any]]] = {}
    for log in filtered_logs:
        event = _build_admission_event(log, profile_index=profile_index)
        if event is not None:
            setattr(summary, event.status, getattr(summary, event.status) + 1)
            if len(admission_events) < INTAKE_ADMISSION_EVENT_LIMIT:
                admission_events.append(event)
            admission_logs_by_session.setdefault(_session_key_from_log(log), []).append(log)
        if _is_reception_session_log(log):
            session_logs_by_session.setdefault(_session_key_from_log(log), []).append(log)

    security_events: list[IntakeSecurityEvent] = []
    for log in filtered_logs:
        event = _build_security_event(
            log,
            trace_logs=trace_logs_index.get(str(log.get("trace_id") or "").strip(), []),
            profile_index=profile_index,
        )
        if event is None:
            continue
        security_events.append(event)
        if len(security_events) >= INTAKE_SECURITY_EVENT_LIMIT:
            break

    hermes_events: list[IntakeHermesEvent] = []
    for log in filtered_logs:
        if not _is_reception_session_log(log):
            continue
        session_key = _session_key_from_log(log)
        event = _build_hermes_event(
            log,
            session_logs=session_logs_by_session.get(session_key, []),
            admission_logs=admission_logs_by_session.get(session_key, []),
            trace_logs=trace_logs_index.get(str(log.get("trace_id") or "").strip(), []),
            profile_index=profile_index,
        )
        if event is None:
            continue
        hermes_events.append(event)
        if len(hermes_events) >= INTAKE_HERMES_EVENT_LIMIT:
            break

    reception_sessions: list[IntakeReceptionSession] = []
    seen_session_keys: set[str] = set()
    for log in filtered_logs:
        if not _is_reception_session_log(log):
            continue
        session_key = _session_key_from_log(log)
        if session_key in seen_session_keys:
            continue
        session = _build_reception_session(
            session_logs_by_session.get(session_key, []),
            admission_logs_by_session.get(session_key, []),
            trace_logs=trace_logs_index.get(str(log.get("trace_id") or "").strip(), []),
            profile_index=profile_index,
        )
        if session is None:
            continue
        seen_session_keys.add(session_key)
        reception_sessions.append(session)
        if len(reception_sessions) >= INTAKE_RECEPTION_SESSION_LIMIT:
            break

    active_session_count = sum(1 for item in reception_sessions if item.state == "serving")
    return IntakeConsoleOverviewResponse(
        summary=summary,
        admission_events=admission_events,
        security_events=security_events,
        hermes_events=hermes_events,
        reception_sessions=reception_sessions,
        active_session_count=active_session_count,
        updated_at=store.now_string(),
    )


def get_intake_trace_detail(trace_id: str) -> IntakeTraceDetailResponse:
    normalized_trace_id = str(trace_id or "").strip()
    if not normalized_trace_id:
        return IntakeTraceDetailResponse(trace_id="")

    logs = [
        log
        for log in _load_operational_logs(limit=INTAKE_OVERVIEW_LOG_LIMIT)
        if str(log.get("trace_id") or "").strip() == normalized_trace_id
    ]
    logs.sort(key=lambda item: _parse_datetime(item.get("timestamp")), reverse=True)

    tenant_id = None
    tenant_name = None
    profile_id = None
    customer_id = None
    person_name = None
    channel = None
    platform_user_id = None
    service_code = None
    session_id = None

    profile_index = _load_profile_index()
    items: list[IntakeTraceLogEntry] = []
    for log in logs:
        metadata = _log_metadata(log)
        tenant_id = tenant_id or _metadata_text(metadata, "tenant_id", "tenantId")
        tenant_name = tenant_name or _metadata_text(metadata, "tenant_name", "tenantName")
        profile_id = profile_id or _metadata_text(
            metadata,
            "profile_id",
            "profileId",
            "user_profile_id",
            "userProfileId",
        )
        customer_id = customer_id or _metadata_text(metadata, "customer_id", "customerId")
        person_name = person_name or _resolve_person_name(metadata=metadata, profile_index=profile_index)
        channel = channel or _metadata_text(metadata, "channel")
        platform_user_id = platform_user_id or _metadata_text(metadata, "platform_user_id", "platformUserId")
        service_code = service_code or _metadata_text(metadata, "service_code", "serviceCode")
        session_id = session_id or _metadata_text(metadata, "session_id", "sessionId")

        items.append(
            IntakeTraceLogEntry(
                id=str(log.get("id") or ""),
                timestamp=str(log.get("timestamp") or ""),
                type=str(log.get("type") or ""),
                agent=str(log.get("agent") or ""),
                message=str(log.get("message") or ""),
                source=str(log.get("source") or ""),
                trace_id=str(log.get("trace_id") or "").strip() or None,
                task_id=str(log.get("task_id") or "").strip() or None,
                workflow_run_id=str(log.get("workflow_run_id") or "").strip() or None,
                metadata=store.clone(metadata) if metadata else None,
            )
        )

    return IntakeTraceDetailResponse(
        trace_id=normalized_trace_id,
        tenant_id=tenant_id,
        tenant_name=tenant_name,
        profile_id=profile_id,
        customer_id=customer_id,
        person_name=person_name,
        channel=channel,
        platform_user_id=platform_user_id,
        service_code=service_code,
        session_id=session_id,
        items=items,
    )
