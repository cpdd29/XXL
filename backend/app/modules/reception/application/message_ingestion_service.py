from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from threading import Event, Lock
from typing import Any

from fastapi import HTTPException

from app.modules.reception.channel_ingress.registry import channel_adapter_registry
from app.modules.reception.application.orchestration_service import orchestration_service
from app.modules.reception.application.reception_service import reception_service
from app.modules.dispatch.application.task_view_service import task_view_service
from app.config import get_settings
from app.modules.dispatch.execution_support.language_service import detect_language
from app.modules.knowledge.application import (
    knowledge_injection_service,
    knowledge_retrieval_log_service,
    knowledge_retrieval_service,
)
from app.modules.knowledge.schemas import KnowledgeRetrievalRequest
from app.modules.organization.application.memory_service import memory_service
from app.modules.organization.application import profile_service as organization_profile_service
from app.modules.organization.application.tenancy_service import default_scope
from app.modules.organization.customer_profile.writeback_service import customer_profile_writeback_service
from app.modules.reception.schemas.messages import UnifiedMessage, channel_display_name, webhook_auth_scope
from app.platform.observability.operational_log_service import append_realtime_event
from app.platform.persistence.persistence_service import persistence_service
from app.platform.config.settings_service import get_channel_integration_runtime_settings
from app.modules.reception.security_monitor.security_gateway_service import security_gateway_service
from app.modules.reception.agent_entry.hermes_reception_agent_service import hermes_reception_agent_service
from app.modules.reception.outbound.channel_outbound_service import channel_outbound_service
from app.modules.reception.customer_access import customer_access_service
from app.modules.reception.shared_files import reception_shared_files_service
from app.modules.reception.channel_ingress.wecom import encode_wecom_delivery_target
from app.platform.persistence.runtime_store import store
from app.modules.dispatch.requirement_dispatch_agent.service import dispatch_requirement_task
from app.modules.dispatch.workflow_runtime.workflow_execution_service import (
    append_context_patch_to_run,
    create_workflow_run_for_task,
    mark_task_steps_authoritative,
    sync_workflow_run_from_task,
    tick_workflow_run,
)

SECURITY_ATTACK_RESPONSE = "检测到输入包含攻击或注入风险，请重新输入"
CHAT_HANDOFF_RESPONSE = ""
TASK_HANDOFF_RESPONSE = ""
TASK_COMPLETED_RESPONSE = "任务已完成"
HERMES_REPLY_BLOCKED_RESPONSE = "检测到回复内容存在风险，已被安全策略拦截"
HERMES_REPLY_FALLBACK_RESPONSE = "当前接待智能体暂时不可用，请稍后再试"
WEBHOOK_MESSAGE_DEDUP_TTL_SECONDS = 300
WEBHOOK_MESSAGE_DEDUP_WAIT_SECONDS = 30.0

ACTIVE_TASKS_BY_USER: dict[str, str] = {}
LAST_MESSAGE_AT_BY_USER: dict[str, datetime] = {}
AUTHORITATIVE_TASK_STEP_CACHE: set[str] = set()
RECENT_WEBHOOK_RESULT_BY_MESSAGE: dict[str, dict[str, Any]] = {}
INFLIGHT_WEBHOOK_MESSAGE_EVENTS: dict[str, Event] = {}
WEBHOOK_MESSAGE_DEDUP_LOCK = Lock()
MEMORY_CONTEXT_LIMIT_MIN = 5
MEMORY_CONTEXT_LIMIT_MAX = 10
DISPATCH_CONTEXT_MEMORY_LIMIT_MIN = 5
DISPATCH_CONTEXT_MEMORY_LIMIT_MAX = 10
DISPATCH_CONTEXT_TEXT_PREVIEW_LIMIT = 160
MEMORY_INJECTION_TYPE_WHITELIST = {
    "session_summary",
    "preferences",
    "decisions",
    "task_result",
    "event",
}
FACT_LAYER_STATE_MACHINE_VERSION = "brain_fact_layer_v1"
PROFILE_ID_METADATA_KEYS = (
    "user_profile_id",
    "userProfileId",
    "profile_id",
    "profileId",
    "internal_user_id",
    "internalUserId",
    "crm_user_id",
    "crmUserId",
)
PROFILE_NAME_METADATA_KEYS = (
    "display_name",
    "displayName",
    "name",
    "username",
    "full_name",
    "fullName",
)
PROFILE_EMAIL_METADATA_KEYS = ("email", "mail")
PROFILE_TENANT_ID_METADATA_KEYS = ("tenant_id", "tenantId")
PROFILE_TENANT_NAME_METADATA_KEYS = ("tenant_name", "tenantName")
ALLOWED_CONTROL_PLANE_ROLES = {"admin", "operator", "viewer"}
INTERACTION_MODES = {"continuation", "chat", "task", "workflow_or_direct"}
PROFESSIONAL_CONFIRM_TIMEOUT_SECONDS = 1800
CONTEXT_PATCH_TASK_STATUSES = {"pending", "running", "completed"}

logger = logging.getLogger(__name__)


def _text(value: object) -> str:
    return str(value or "").strip()


def _webhook_message_dedup_key(message: UnifiedMessage) -> str | None:
    message_id = str(message.message_id or "").strip()
    if not message_id:
        return None
    return f"{message.channel.value}:{message_id}"


def _prune_webhook_result_cache(now: datetime | None = None) -> None:
    current = now or datetime.now(UTC)
    expired_keys = [
        key
        for key, item in RECENT_WEBHOOK_RESULT_BY_MESSAGE.items()
        if not isinstance(item, dict)
        or not isinstance(item.get("expires_at"), datetime)
        or item["expires_at"] <= current
    ]
    for key in expired_keys:
        RECENT_WEBHOOK_RESULT_BY_MESSAGE.pop(key, None)


def _ingest_webhook_message_once(
    message: UnifiedMessage,
    *,
    channel: str,
    entrypoint: str,
    entrypoint_agent: str,
) -> dict[str, Any]:
    dedup_key = _webhook_message_dedup_key(message)
    if not dedup_key:
        return ingest_unified_message(
            message,
            auth_scope=webhook_auth_scope(channel),
            entrypoint=entrypoint,
            entrypoint_agent=entrypoint_agent,
        )

    owner = False
    wait_event: Event | None = None
    while True:
        with WEBHOOK_MESSAGE_DEDUP_LOCK:
            _prune_webhook_result_cache()
            cached = RECENT_WEBHOOK_RESULT_BY_MESSAGE.get(dedup_key)
            if isinstance(cached, dict) and isinstance(cached.get("result"), dict):
                logger.info("Webhook duplicate skipped by cache: %s", dedup_key)
                return store.clone(cached["result"])

            wait_event = INFLIGHT_WEBHOOK_MESSAGE_EVENTS.get(dedup_key)
            if wait_event is None:
                wait_event = Event()
                INFLIGHT_WEBHOOK_MESSAGE_EVENTS[dedup_key] = wait_event
                owner = True
                break

        if wait_event.wait(timeout=WEBHOOK_MESSAGE_DEDUP_WAIT_SECONDS):
            continue

        logger.warning("Webhook duplicate wait timed out, retrying ownership: %s", dedup_key)

    result: dict[str, Any] | None = None
    try:
        result = ingest_unified_message(
            message,
            auth_scope=webhook_auth_scope(channel),
            entrypoint=entrypoint,
            entrypoint_agent=entrypoint_agent,
        )
    finally:
        with WEBHOOK_MESSAGE_DEDUP_LOCK:
            event = INFLIGHT_WEBHOOK_MESSAGE_EVENTS.pop(dedup_key, None)
            if owner and event is not None:
                if isinstance(result, dict):
                    RECENT_WEBHOOK_RESULT_BY_MESSAGE[dedup_key] = {
                        "result": store.clone(result),
                        "expires_at": datetime.now(UTC) + timedelta(seconds=WEBHOOK_MESSAGE_DEDUP_TTL_SECONDS),
                    }
                event.set()

    if result is None:
        raise RuntimeError("Webhook ingestion returned no result")
    return result


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


def _parse_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.now(UTC)


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


def _find_task(task_id: str) -> dict | None:
    database_task, database_authoritative = _load_database_task(task_id)
    if database_authoritative:
        if database_task is None:
            return None
        return _sync_cached_task(database_task)

    return _find_cached_task(task_id)


def _find_cached_task(task_id: str) -> dict | None:
    for task in store.tasks:
        if task["id"] == task_id:
            return task
    return None


def _find_loaded_run(run_id: str | None) -> dict | None:
    normalized_run_id = str(run_id or "").strip()
    if not normalized_run_id:
        return None
    for run in store.workflow_runs:
        if str(run.get("id") or "").strip() == normalized_run_id:
            return run
    database_run = persistence_service.get_workflow_run(normalized_run_id)
    if database_run is None:
        return None
    payload = store.clone(database_run)
    store.workflow_runs.insert(0, payload)
    return payload


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


def _refresh_task_steps_from_database(task_id: str) -> list[dict] | None:
    database_steps = persistence_service.get_task_steps(task_id)
    if database_steps is None and getattr(persistence_service, "enabled", False):
        store.task_steps[task_id] = []
        AUTHORITATIVE_TASK_STEP_CACHE.add(task_id)
        return store.task_steps[task_id]
    if database_steps is None:
        return None
    store.task_steps[task_id] = store.clone(database_steps)
    AUTHORITATIVE_TASK_STEP_CACHE.add(task_id)
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
            AUTHORITATIVE_TASK_STEP_CACHE.add(task_id)
            return store.task_steps[task_id]
        store.task_steps[task_id] = []
        AUTHORITATIVE_TASK_STEP_CACHE.add(task_id)
        return store.task_steps[task_id]

    database_steps = persistence_service.get_task_steps(task_id)
    if database_steps is not None:
        store.task_steps[task_id] = store.clone(database_steps)
        return store.task_steps[task_id]

    return store.task_steps.setdefault(task_id, [])


def _load_tasks_for_bootstrap() -> list[dict]:
    database_tasks = persistence_service.list_tasks()
    if database_tasks is not None:
        return database_tasks
    if getattr(persistence_service, "enabled", False):
        return []
    return store.clone(store.tasks)


def _load_task_steps(task_id: str) -> list[dict]:
    database_steps = persistence_service.get_task_steps(task_id)
    if database_steps is not None:
        return database_steps
    if getattr(persistence_service, "enabled", False):
        return []
    return store.clone(store.task_steps.get(task_id, []))


def _latest_message_at_for_task(task: dict) -> datetime:
    latest = _parse_datetime(task.get("created_at"))
    task_id = str(task.get("id") or "")
    for step in _load_task_steps(task_id):
        if step.get("title") != "上下文追加":
            continue
        candidate = _parse_datetime(step.get("finished_at") or step.get("started_at"))
        if candidate > latest:
            latest = candidate
    return latest


def _truncate_text(value: str, limit: int = 36) -> str:
    cleaned = value.strip()
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit]}..."


def _normalize_language(value: object) -> str | None:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    normalized = normalized.replace("_", "-").split("-", maxsplit=1)[0]
    if normalized in {"zh", "en"}:
        return normalized
    return None


def _metadata_preferred_language(metadata: dict) -> str | None:
    return _normalize_language(
        metadata.get("preferred_language") or metadata.get("preferredLanguage")
    )


def _metadata_platform_language(metadata: dict) -> str | None:
    return _normalize_language(metadata.get("language_code") or metadata.get("languageCode"))


def _metadata_text(metadata: dict, *keys: str) -> str | None:
    for key in keys:
        value = str(metadata.get(key) or "").strip()
        if value:
            return value
    return None


def _metadata_profile_id(metadata: dict) -> str | None:
    return _metadata_text(metadata, *PROFILE_ID_METADATA_KEYS)


def _metadata_tenant_id(metadata: dict) -> str | None:
    return _metadata_text(metadata, *PROFILE_TENANT_ID_METADATA_KEYS)


def _metadata_tenant_name(metadata: dict) -> str | None:
    return _metadata_text(metadata, *PROFILE_TENANT_NAME_METADATA_KEYS)


def _normalize_tenant_binding_value(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _channel_tenant_binding(channel: str) -> tuple[str | None, str | None]:
    settings = get_channel_integration_runtime_settings()
    if not isinstance(settings, dict):
        return None, None

    channel_settings = settings.get(channel)
    if not isinstance(channel_settings, dict):
        return None, None

    candidate_sources = [channel_settings]
    for key in ("tenant_binding", "tenantBinding", "tenant"):
        nested = channel_settings.get(key)
        if isinstance(nested, dict):
            candidate_sources.append(nested)

    for source in candidate_sources:
        tenant_id = _normalize_tenant_binding_value(
            source.get("tenant_id") or source.get("tenantId") or source.get("id")
        )
        if not tenant_id:
            continue
        tenant_name = _normalize_tenant_binding_value(
            source.get("tenant_name") or source.get("tenantName") or source.get("name")
        )
        return tenant_id, tenant_name
    return None, None


def _resolved_message_tenant_binding(message: UnifiedMessage) -> tuple[str | None, str | None]:
    metadata = message.metadata if isinstance(message.metadata, dict) else {}
    metadata_tenant_id = _metadata_tenant_id(metadata)
    metadata_tenant_name = _metadata_tenant_name(metadata)
    if metadata_tenant_id:
        resolved_tenant_id, resolved_tenant_name = organization_profile_service.resolve_tenant_binding(
            metadata_tenant_id,
            metadata_tenant_name,
        )
        if not resolved_tenant_id:
            return None, None
        return resolved_tenant_id, resolved_tenant_name or f"{resolved_tenant_id} 租户"

    channel_tenant_id, channel_tenant_name = _channel_tenant_binding(
        str(message.channel.value or "").strip().lower()
    )
    resolved_tenant_id, resolved_tenant_name = organization_profile_service.resolve_tenant_binding(
        channel_tenant_id,
        channel_tenant_name,
    )
    if not resolved_tenant_id:
        return None, None
    return resolved_tenant_id, resolved_tenant_name or f"{resolved_tenant_id} 租户"


def _memory_scope_for_message(*, tenant_id: str | None) -> dict[str, str]:
    scope = default_scope()
    if tenant_id:
        scope["tenant_id"] = tenant_id
    return scope


def _write_hermes_memory_writeback(
    *,
    message: UnifiedMessage,
    hermes_result: dict[str, Any],
) -> tuple[int, list[str]]:
    results = _apply_hermes_memory_writeback(
        hermes_result=hermes_result,
        message=message,
        trace_id="legacy",
    )
    saved_count = sum(1 for item in results if bool(item.get("applied")))
    warnings = [
        f"Hermes 回写第 {index} 项失败：{item.get('error')}"
        for index, item in enumerate(results, start=1)
        if str(item.get("error") or "").strip()
    ]
    return saved_count, warnings


def _profile_preferred_language(profile: dict | None) -> str | None:
    if not isinstance(profile, dict):
        return None
    return _normalize_language(
        profile.get("preferred_language") or profile.get("preferredLanguage")
    )


def _load_user_profile_with_source(profile_key: str) -> tuple[dict | None, bool]:
    normalized_key = str(profile_key or "").strip()
    if not normalized_key:
        return None, False

    persisted_profile = persistence_service.get_user_profile(normalized_key)
    if persisted_profile is not None:
        profile_id = str(persisted_profile.get("id") or normalized_key).strip()
        if profile_id:
            store.user_profiles[profile_id] = store.clone(persisted_profile)
        return persisted_profile, True

    database_user, database_authoritative = _load_database_user(normalized_key)
    if database_authoritative and database_user is None:
        return None, True

    runtime_profile = store.user_profiles.get(normalized_key)
    if runtime_profile is not None:
        return runtime_profile, False
    if database_authoritative:
        return None, True
    return None, False


def _load_user_profile(profile_key: str) -> dict | None:
    profile, _ = _load_user_profile_with_source(profile_key)
    return profile


def _profile_matches_platform_account(
    profile: dict | None,
    *,
    platform: str,
    account_id: str,
) -> bool:
    if not isinstance(profile, dict):
        return False

    accounts = profile.get("platform_accounts") or profile.get("platformAccounts") or []
    if not isinstance(accounts, list):
        return False

    normalized_platform = platform.strip().lower()
    normalized_account_id = account_id.strip()
    if not normalized_platform or not normalized_account_id:
        return False

    for account in accounts:
        if not isinstance(account, dict):
            continue
        account_platform = str(account.get("platform") or "").strip().lower()
        profile_account_id = str(
            account.get("account_id") or account.get("accountId") or ""
        ).strip()
        if account_platform == normalized_platform and profile_account_id == normalized_account_id:
            return True
    return False


def _profile_matches_tenant(profile: dict | None, *, tenant_id: str | None) -> bool:
    if not tenant_id:
        return True
    profile_tenant_id = _profile_tenant_id(profile)
    return bool(profile_tenant_id) and profile_tenant_id == tenant_id


def _profile_tenant_id(profile: dict | None) -> str | None:
    if not isinstance(profile, dict):
        return None
    normalized = str(profile.get("tenant_id") or profile.get("tenantId") or "").strip()
    return normalized or None


def _find_runtime_profile_by_platform_account(
    *,
    platform: str,
    account_id: str,
    tenant_id: str | None = None,
) -> dict | None:
    for profile in store.user_profiles.values():
        if _profile_matches_tenant(profile, tenant_id=tenant_id) and _profile_matches_platform_account(
            profile,
            platform=platform,
            account_id=account_id,
        ):
            return profile
    return None


def _find_profile_by_platform_account_with_source(
    *,
    platform: str,
    account_id: str,
    tenant_id: str | None = None,
) -> tuple[dict | None, bool]:
    persisted_profile = None
    list_profiles = getattr(persistence_service, "list_user_profiles", None)
    if callable(list_profiles):
        persisted_profiles = list_profiles() or []
        for candidate in persisted_profiles:
            if not _profile_matches_tenant(candidate, tenant_id=tenant_id):
                continue
            if _profile_matches_platform_account(
                candidate,
                platform=platform,
                account_id=account_id,
            ):
                persisted_profile = candidate
                break
    elif tenant_id is None:
        persisted_profile = persistence_service.find_user_profile_by_platform_account(
            platform=platform,
            account_id=account_id,
        )
    if persisted_profile is not None:
        profile_id = str(persisted_profile.get("id") or "").strip()
        if profile_id:
            store.user_profiles[profile_id] = store.clone(persisted_profile)
        return persisted_profile, True

    if getattr(persistence_service, "enabled", False):
        return None, True

    return _find_runtime_profile_by_platform_account(
        platform=platform,
        account_id=account_id,
        tenant_id=tenant_id,
    ), False


def _find_profile_by_platform_account(
    *,
    platform: str,
    account_id: str,
    tenant_id: str | None = None,
) -> dict | None:
    profile, _ = _find_profile_by_platform_account_with_source(
        platform=platform,
        account_id=account_id,
        tenant_id=tenant_id,
    )
    return profile


def _message_metadata(message: UnifiedMessage) -> dict[str, Any]:
    return message.metadata if isinstance(message.metadata, dict) else {}


def _resolve_intake_person_name(message: UnifiedMessage) -> str | None:
    metadata = _message_metadata(message)
    direct_name = _metadata_text(
        metadata,
        *PROFILE_NAME_METADATA_KEYS,
        "contact_name",
        "contactName",
    )
    if direct_name:
        return direct_name

    profile_id = _metadata_profile_id(metadata)
    if profile_id:
        profile = _load_user_profile(profile_id)
        resolved = _metadata_text(
            profile or {},
            *PROFILE_NAME_METADATA_KEYS,
            "contact_name",
            "contactName",
        )
        if resolved:
            return resolved

    normalized_channel = str(message.channel.value or "").strip().lower()
    platform_user_id = str(message.platform_user_id or "").strip()
    if not normalized_channel or not platform_user_id:
        return None

    tenant_id, _ = _resolved_message_tenant_binding(message)
    profile = _find_profile_by_platform_account(
        platform=normalized_channel,
        account_id=platform_user_id,
        tenant_id=tenant_id,
    )
    return _metadata_text(
        profile or {},
        *PROFILE_NAME_METADATA_KEYS,
        "contact_name",
        "contactName",
    )


def _intake_event_metadata_base(message: UnifiedMessage) -> dict[str, Any]:
    metadata = _message_metadata(message)
    tenant_id, tenant_name = _resolved_message_tenant_binding(message)
    return {
        "domain": "intake",
        "channel": str(message.channel.value or "").strip() or None,
        "platform_user_id": str(message.platform_user_id or "").strip() or None,
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        "profile_id": _metadata_profile_id(metadata),
        "customer_id": _metadata_text(metadata, "customer_id", "customerId"),
        "service_code": _metadata_text(metadata, "service_code", "serviceCode"),
        "session_id": str(message.session_id or "").strip() or None,
        "message_id": str(message.message_id or "").strip() or None,
        "person_name": _resolve_intake_person_name(message),
    }


def _safe_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _append_intake_admission_event(
    *,
    message: UnifiedMessage,
    status: str,
    agent: str,
    text: str,
    trace_id: str | None,
    type_: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    payload = _intake_event_metadata_base(message)
    payload.update(
        {
            "intake_event_kind": "admission",
            "intake_status": status,
        }
    )
    if isinstance(metadata, dict):
        payload.update(store.clone(metadata))
    append_realtime_event(
        agent=agent,
        message=text,
        type_=type_,
        source="message_ingestion",
        trace_id=trace_id,
        metadata=payload,
    )


def _append_reception_session_event(
    *,
    message: UnifiedMessage,
    state: str,
    text: str,
    trace_id: str | None,
    type_: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    payload = _intake_event_metadata_base(message)
    payload.update(
        {
            "intake_event_kind": "session",
            "agent_role": "hermes_reception",
            "reception_session_state": state,
        }
    )
    if isinstance(metadata, dict):
        payload.update(store.clone(metadata))
    append_realtime_event(
        agent="Hermes Reception Agent",
        message=text,
        type_=type_,
        source="message_ingestion",
        trace_id=trace_id,
        metadata=payload,
    )


def _knowledge_context_event_metadata(message: UnifiedMessage, *, preview_limit: int = 3) -> dict[str, Any]:
    metadata = _message_metadata(message)
    retrieval = metadata.get("knowledge_retrieval")
    knowledge_hits = metadata.get("knowledge_hits") or metadata.get("knowledgeHits")
    if not isinstance(retrieval, dict) and not isinstance(knowledge_hits, list):
        return {}

    preview_items: list[dict[str, Any]] = []
    if isinstance(knowledge_hits, list):
        for raw_item in knowledge_hits[:preview_limit]:
            if not isinstance(raw_item, dict):
                continue
            preview_items.append(
                {
                    "title": str(raw_item.get("title") or "").strip() or "未命名知识片段",
                    "source": str(raw_item.get("source") or "").strip() or None,
                    "summary": str(raw_item.get("summary") or "").strip() or None,
                    "scope": _metadata_text(
                        raw_item.get("metadata") if isinstance(raw_item.get("metadata"), dict) else {},
                        "scope",
                    ),
                    "score": (
                        raw_item.get("metadata", {}).get("score")
                        if isinstance(raw_item.get("metadata"), dict)
                        else None
                    ),
                }
            )

    total = 0
    tenant_hits = 0
    shared_hits = 0
    if isinstance(retrieval, dict):
        total = _safe_int(retrieval.get("total"))
        tenant_hits = _safe_int(retrieval.get("tenant_hits") or retrieval.get("tenantHits"))
        shared_hits = _safe_int(retrieval.get("shared_hits") or retrieval.get("sharedHits"))

    if total <= 0 and preview_items:
        total = len(preview_items)

    if total <= 0:
        return {}

    return {
        "knowledge_hit_count": total,
        "knowledge_tenant_hits": tenant_hits,
        "knowledge_shared_hits": shared_hits,
        "knowledge_hits_preview": preview_items,
    }


def _active_task_context_event_metadata(message: UnifiedMessage) -> dict[str, Any]:
    metadata = _message_metadata(message)
    task_context = metadata.get("active_task_context") or metadata.get("activeTaskContext")
    if not isinstance(task_context, dict):
        task_id = _text(metadata.get("task_id") or metadata.get("taskId"))
        if not task_id:
            return {}
        return {"active_task_id": task_id}

    task_id = _text(task_context.get("task_id") or task_context.get("taskId"))
    if not task_id:
        return {}

    return {
        "active_task_id": task_id,
        "active_task_context": {
            "task_id": task_id,
            "title": _text(task_context.get("title")) or None,
            "status": _text(task_context.get("status")) or None,
            "summary": _text(task_context.get("summary")) or None,
            "updated_at": _text(task_context.get("updated_at") or task_context.get("updatedAt")) or None,
        },
    }


def _user_profile_preferred_language(message: UnifiedMessage) -> str | None:
    profile_keys = [
        _metadata_profile_id(message.metadata),
        str(message.user_key or "").strip(),
        str(message.platform_user_id or "").strip(),
    ]
    seen_keys: set[str] = set()

    for profile_key in profile_keys:
        if not profile_key or profile_key in seen_keys:
            continue
        seen_keys.add(profile_key)

        profile = _load_user_profile(profile_key)
        language = _profile_preferred_language(profile)
        if language:
            return language

    normalized_channel = str(message.channel.value or "").strip().lower()
    platform_user_id = str(message.platform_user_id or "").strip()
    if not normalized_channel or not platform_user_id:
        return None

    profile = _find_profile_by_platform_account(
        platform=normalized_channel,
        account_id=platform_user_id,
    )
    language = _profile_preferred_language(profile)
    if language:
        return language

    return None


def _resolved_preferred_language(message: UnifiedMessage) -> str | None:
    return (
        _metadata_preferred_language(message.metadata)
        or _user_profile_preferred_language(message)
        or _metadata_platform_language(message.metadata)
    )


def _merge_source_channels(profile: dict, channel: str) -> list[str]:
    source_channels = [
        str(item).strip().lower()
        for item in (profile.get("source_channels") or [])
        if str(item).strip()
    ]
    if channel and channel not in source_channels:
        source_channels.append(channel)
    return source_channels


def _merge_platform_accounts(profile: dict, *, channel: str, account_id: str) -> list[dict[str, str]]:
    merged_accounts: list[dict[str, str]] = []
    seen_accounts: set[tuple[str, str]] = set()

    for account in profile.get("platform_accounts") or profile.get("platformAccounts") or []:
        if not isinstance(account, dict):
            continue
        platform = str(account.get("platform") or "").strip().lower()
        profile_account_id = str(
            account.get("account_id") or account.get("accountId") or ""
        ).strip()
        if not platform or not profile_account_id:
            continue
        key = (platform, profile_account_id)
        if key in seen_accounts:
            continue
        merged_accounts.append({"platform": platform, "account_id": profile_account_id})
        seen_accounts.add(key)

    if channel and account_id and (channel, account_id) not in seen_accounts:
        merged_accounts.append({"platform": channel, "account_id": account_id})

    return merged_accounts


def _runtime_profile_supplement(profile: dict) -> dict:
    source_channels = [
        str(item).strip().lower()
        for item in (profile.get("source_channels") or profile.get("sourceChannels") or [])
        if str(item).strip()
    ]
    platform_accounts = _merge_platform_accounts(profile, channel="", account_id="")

    supplement: dict[str, object] = {}
    preferred_language = _profile_preferred_language(profile)
    if preferred_language:
        supplement["preferred_language"] = preferred_language
    if source_channels:
        supplement["source_channels"] = source_channels
    if platform_accounts:
        supplement["platform_accounts"] = platform_accounts
    return supplement


def _normalize_control_plane_role(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in ALLOWED_CONTROL_PLANE_ROLES:
        return normalized
    return "viewer"


def _find_runtime_user(user_id: str) -> dict | None:
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        return None
    for user in store.users:
        if str(user.get("id") or "").strip() == normalized_user_id:
            return user
    return None


def _load_database_user(user_id: str) -> tuple[dict | None, bool]:
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id or not getattr(persistence_service, "enabled", False):
        return None, False

    database_user = persistence_service.get_user(normalized_user_id)
    if database_user is not None:
        return database_user, True

    database_users = persistence_service.list_users(search=None)
    if database_users is None:
        return None, True

    for candidate in database_users:
        if str(candidate.get("id") or "").strip() == normalized_user_id:
            return candidate, True
    return None, True


def _load_existing_user(user_id: str) -> dict | None:
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        return None

    database_user, database_authoritative = _load_database_user(normalized_user_id)
    if database_authoritative:
        if database_user is None:
            return None
        runtime_user = _find_runtime_user(normalized_user_id)
        payload = store.clone(database_user)
        if runtime_user is None:
            store.users.append(payload)
            return store.users[-1]

        runtime_user.clear()
        runtime_user.update(payload)
        return runtime_user

    return _find_runtime_user(normalized_user_id)


def _sync_message_user_profile(
    message: UnifiedMessage,
    *,
    preferred_language: str | None,
) -> None:
    normalized_channel = str(message.channel.value or "").strip().lower()
    platform_user_id = str(message.platform_user_id or "").strip()
    if not normalized_channel or not platform_user_id:
        return

    explicit_profile_id = _metadata_profile_id(message.metadata)
    message_tenant_id, message_tenant_name = _resolved_message_tenant_binding(message)
    # Only tenant-bound messages are allowed to mutate user/profile state.
    if not message_tenant_id:
        return

    existing_profile = None
    profile_from_database = False
    if explicit_profile_id:
        existing_profile, profile_from_database = _load_user_profile_with_source(explicit_profile_id)
        existing_profile_tenant_id = _profile_tenant_id(existing_profile)
        if existing_profile_tenant_id and existing_profile_tenant_id != message_tenant_id:
            return
    if existing_profile is None:
        existing_profile, profile_from_database = _find_profile_by_platform_account_with_source(
            platform=normalized_channel,
            account_id=platform_user_id,
            tenant_id=message_tenant_id,
        )

    profile_id = (
        explicit_profile_id
        or str((existing_profile or {}).get("id") or (existing_profile or {}).get("user_id") or "").strip()
        or str(message.user_key or "").strip()
    )
    if not profile_id:
        return

    existing_user = _load_existing_user(profile_id)
    database_user, database_user_authoritative = _load_database_user(profile_id)
    existing_user_payload = store.clone(existing_user) if isinstance(existing_user, dict) else {}
    profile = store.clone(existing_profile) if isinstance(existing_profile, dict) else {}
    if database_user_authoritative and database_user is not None and not profile_from_database:
        profile = _runtime_profile_supplement(profile)
    authoritative_profile = profile if profile_from_database else {}
    resolved_tenant_id = (
        str(authoritative_profile.get("tenant_id") or "").strip()
        or str(profile.get("tenant_id") or "").strip()
        or message_tenant_id
    )
    if not resolved_tenant_id:
        return
    resolved_tenant_name = (
        str(authoritative_profile.get("tenant_name") or "").strip()
        or str(profile.get("tenant_name") or "").strip()
        or message_tenant_name
        or f"{resolved_tenant_id} 租户"
    )
    fallback_created_at = (str(message.received_at or "").strip() or store.now_string()).split(
        "T",
        maxsplit=1,
    )[0]
    fallback_email = f"{normalized_channel}-{platform_user_id}@external.workbot.local"
    tags = [
        str(tag).strip()
        for tag in profile.get("tags") or []
        if str(tag).strip()
    ]
    for tag in ("自动映射", f"{channel_display_name(message.channel.value)}接入"):
        if tag not in tags:
            tags.append(tag)

    updated_profile = {
        **profile,
        "id": profile_id,
        "user_id": profile_id,
        "tenant_id": resolved_tenant_id,
        "tenant_name": resolved_tenant_name,
        "tenant_status": "active",
        "name": (
            str(authoritative_profile.get("name") or "").strip()
            or str(existing_user_payload.get("name") or "").strip()
            or str(profile.get("name") or "").strip()
            or _metadata_text(message.metadata, *PROFILE_NAME_METADATA_KEYS)
            or platform_user_id
        ),
        "email": (
            str(authoritative_profile.get("email") or "").strip()
            or str(existing_user_payload.get("email") or "").strip()
            or str(profile.get("email") or "").strip()
            or _metadata_text(message.metadata, *PROFILE_EMAIL_METADATA_KEYS)
            or fallback_email
        ),
        "role": _normalize_control_plane_role(
            authoritative_profile.get("role")
            or existing_user_payload.get("role")
            or profile.get("role")
        ),
        "status": (
            str(authoritative_profile.get("status") or "").strip()
            or str(existing_user_payload.get("status") or "").strip()
            or str(profile.get("status") or "").strip()
            or "active"
        ),
        "last_login": str(message.received_at or store.now_string()),
        "total_interactions": int(
            authoritative_profile.get("total_interactions")
            or existing_user_payload.get("total_interactions")
            or profile.get("total_interactions")
            or 0
        )
        + 1,
        "created_at": (
            str(authoritative_profile.get("created_at") or "").strip()
            or str(existing_user_payload.get("created_at") or "").strip()
            or str(profile.get("created_at") or "").strip()
            or fallback_created_at
        ),
        "tags": tags,
        "notes": (
            str(profile.get("notes") or "").strip()
            or "由渠道消息接入自动创建或更新。"
        ),
        "preferred_language": (
            _profile_preferred_language(profile)
            or preferred_language
            or message.detected_lang
            or "zh"
        ),
        "source_channels": _merge_source_channels(profile, normalized_channel),
        "platform_accounts": _merge_platform_accounts(
            profile,
            channel=normalized_channel,
            account_id=platform_user_id,
        ),
        "last_active_at": str(message.received_at or store.now_string()),
    }
    updated_user = {
        **existing_user_payload,
        "id": profile_id,
        "name": str(updated_profile["name"]),
        "email": str(updated_profile["email"]),
        "role": _normalize_control_plane_role(updated_profile["role"]),
        "status": str(updated_profile["status"] or "active"),
        "last_login": str(updated_profile["last_login"]),
        "total_interactions": int(updated_profile["total_interactions"]),
        "created_at": str(updated_profile["created_at"]),
    }

    runtime_user = _find_runtime_user(profile_id)
    if runtime_user is None:
        store.users.append(updated_user)
    else:
        runtime_user.update(updated_user)
    store.user_profiles[profile_id] = updated_profile
    persistence_service.persist_user_state(user=updated_user, profile=updated_profile)


def _attach_reception_knowledge_context(
    message: UnifiedMessage,
    *,
    trace_id: str,
) -> tuple[int, str | None]:
    tenant_id, _ = _resolved_message_tenant_binding(message)
    query = str(message.text or "").strip()
    if not tenant_id or not query:
        return 0, None

    metadata = message.metadata if isinstance(message.metadata, dict) else {}
    try:
        request = KnowledgeRetrievalRequest(
            tenant_id=tenant_id,
            query=query,
            scene="reception",
            metadata={
                **dict(metadata),
                "trace_id": trace_id,
                "channel": message.channel.value,
                "user_key": message.user_key,
                "request_source": "reception.message_ingestion",
            },
        )
        retrieval = knowledge_retrieval_service.retrieve(request)
        injected_metadata = knowledge_injection_service.inject_hits_into_metadata(
            metadata=metadata,
            retrieval=retrieval,
        )
        message.metadata = injected_metadata
        retrieval_log = knowledge_retrieval_log_service.build_log(
            request=request,
            response=retrieval,
            request_source="reception.message_ingestion",
            trace_id=trace_id,
            metadata={
                "channel": message.channel.value,
                "user_key": message.user_key,
            },
        )
        knowledge_retrieval_log_service.append_log(retrieval_log)
    except Exception as exc:
        append_realtime_event(
            agent="Knowledge Retrieval",
            message=f"接待前知识检索失败：{exc}",
            type_="warning",
            source="message_ingestion",
            trace_id=trace_id,
            metadata={
                "event": "knowledge_retrieval_failed",
                "tenant_id": tenant_id,
                "channel": message.channel.value,
                "user_key": message.user_key,
                "reason": str(exc),
            },
        )
        return 0, str(exc)

    if retrieval.total > 0:
        append_realtime_event(
            agent="Knowledge Retrieval",
            message=f"接待前命中 {retrieval.total} 条知识片段",
            type_="success",
            source="message_ingestion",
            trace_id=trace_id,
            metadata={
                "event": "knowledge_retrieval_attached",
                "tenant_id": tenant_id,
                "channel": message.channel.value,
                "user_key": message.user_key,
                "tenant_hits": retrieval.tenant_hits,
                "shared_hits": retrieval.shared_hits,
                **_knowledge_context_event_metadata(message),
            },
        )
    return retrieval.total, None


def _memory_context_lines(memory_items: list[dict]) -> list[str]:
    filtered_items, _ = _filter_memory_items_for_injection(memory_items)
    limit = _dynamic_memory_window(
        memory_items=filtered_items,
        min_limit=MEMORY_CONTEXT_LIMIT_MIN,
        max_limit=MEMORY_CONTEXT_LIMIT_MAX,
    )
    return [
        f"记忆注入: {str(item.get('memory_text') or '').strip()}"
        for item in filtered_items[:limit]
        if str(item.get("memory_text") or "").strip()
    ]


def _memory_step_message(memory_items: list[dict]) -> str:
    filtered_items, blocked_items = _filter_memory_items_for_injection(memory_items)
    if not filtered_items:
        return "未命中长期记忆，按当前请求直接执行"

    previews = [
        _truncate_text(str(item.get("memory_text") or ""), 28)
        for item in filtered_items[:2]
        if str(item.get("memory_text") or "").strip()
    ]
    if previews:
        suffix = f"；拦截 {len(blocked_items)} 条非白名单记忆" if blocked_items else ""
        return f"已注入 {len(filtered_items)} 条长期记忆：{'；'.join(previews)}{suffix}"
    return f"已注入 {len(filtered_items)} 条长期记忆"


def _filter_memory_items_for_injection(memory_items: list[dict]) -> tuple[list[dict], list[dict]]:
    allowed: list[dict] = []
    blocked: list[dict] = []
    for item in memory_items:
        memory_type = str(item.get("memory_type") or "session_summary").strip().lower()
        if memory_type in MEMORY_INJECTION_TYPE_WHITELIST:
            allowed.append(item)
        else:
            blocked.append(item)
    return allowed, blocked


def _memory_injection_summary(memory_items: list[dict]) -> dict[str, Any]:
    allowed_items, blocked_items = _filter_memory_items_for_injection(memory_items)
    source_counts: dict[str, int] = {}
    for item in allowed_items:
        memory_type = str(item.get("memory_type") or "session_summary").strip().lower() or "session_summary"
        source_counts[memory_type] = source_counts.get(memory_type, 0) + 1
    return {
        "boundary": "long_term_read_only",
        "whitelist_types": sorted(MEMORY_INJECTION_TYPE_WHITELIST),
        "total_hits": len(memory_items),
        "injected_hits": len(allowed_items),
        "blocked_hits": len(blocked_items),
        "source_counts": source_counts,
        "sources": [
            {
                "memory_id": str(item.get("memory_id") or "").strip() or None,
                "source_mid_term_id": str(item.get("source_mid_term_id") or "").strip() or None,
                "memory_type": str(item.get("memory_type") or "").strip() or None,
                "score": item.get("score"),
                "summary": _truncate_text(str(item.get("summary") or item.get("memory_text") or ""), 80),
            }
            for item in allowed_items
        ],
        "blocked_sources": [
            {
                "memory_id": str(item.get("memory_id") or "").strip() or None,
                "memory_type": str(item.get("memory_type") or "").strip() or None,
            }
            for item in blocked_items
        ],
    }


def _dispatch_context_memory_items(memory_items: list[dict]) -> list[dict]:
    filtered_items, _ = _filter_memory_items_for_injection(memory_items)
    limit = _dynamic_memory_window(
        memory_items=filtered_items,
        min_limit=DISPATCH_CONTEXT_MEMORY_LIMIT_MIN,
        max_limit=DISPATCH_CONTEXT_MEMORY_LIMIT_MAX,
    )
    items: list[dict] = []
    for item in filtered_items[:limit]:
        items.append(
            {
                "memory_id": str(item.get("memory_id") or "").strip() or None,
                "source_mid_term_id": str(item.get("source_mid_term_id") or "").strip() or None,
                "memory_type": str(item.get("memory_type") or "").strip() or None,
                "summary": _truncate_text(str(item.get("summary") or item.get("memory_text") or ""), 80),
                "keywords": [
                    str(keyword).strip()
                    for keyword in (item.get("keywords") or [])
                    if str(keyword).strip()
                ][:6],
                "score": item.get("score"),
                "matched_terms": [
                    str(term).strip()
                    for term in (item.get("matched_terms") or [])
                    if str(term).strip()
                ][:6],
                "rerank_score": item.get("rerank_score"),
            }
        )
    return items


def _dynamic_memory_window(
    *,
    memory_items: list[dict],
    min_limit: int,
    max_limit: int,
) -> int:
    if not memory_items:
        return 0
    normalized_min = max(1, int(min_limit))
    normalized_max = max(normalized_min, int(max_limit))
    return min(len(memory_items), max(normalized_min, min(normalized_max, len(memory_items))))


def _build_channel_delivery_binding(message: UnifiedMessage) -> dict | None:
    raw_payload = message.raw_payload if isinstance(message.raw_payload, dict) else {}
    metadata = message.metadata if isinstance(message.metadata, dict) else {}
    channel = message.channel.value
    chat_id = str(message.chat_id or "").strip()

    if channel == "dingtalk":
        session_webhook = str(
            metadata.get("session_webhook")
            or raw_payload.get("sessionWebhook")
            or raw_payload.get("session_webhook")
            or ""
        ).strip()
        corp_id = str(
            metadata.get("corp_id")
            or raw_payload.get("corpId")
            or raw_payload.get("corp_id")
            or raw_payload.get("chatbotCorpId")
            or raw_payload.get("senderCorpId")
            or ""
        ).strip()
        conversation_id = str(
            raw_payload.get("conversationId")
            or chat_id
            or ""
        ).strip()
        target_id = session_webhook or conversation_id
        if not target_id:
            return None
        return {
            "channel": channel,
            "target_id": target_id,
            "target_type": "session_webhook_url" if session_webhook else "conversation_id",
            "session_webhook": session_webhook or None,
            "conversation_id": conversation_id or None,
            "conversation_type": str(metadata.get("conversation_type") or "").strip() or None,
            "robot_code": str(metadata.get("robot_code") or "").strip() or None,
            "corp_id": corp_id or None,
            "platform_user_id": str(message.platform_user_id or "").strip() or None,
            "session_id": str(message.session_id or "").strip() or None,
        }

    if channel == "wecom":
        tenant_id = str(metadata.get("tenant_id") or metadata.get("tenantId") or "").strip()
        context_token = str(metadata.get("context_token") or metadata.get("contextToken") or "").strip()
        platform_user_id = str(message.platform_user_id or "").strip()
        if tenant_id and context_token and platform_user_id:
            target_id = encode_wecom_delivery_target(
                {
                    "tenant_id": tenant_id,
                    "user_id": platform_user_id,
                    "context_token": context_token,
                }
            )
            return {
                "channel": channel,
                "target_id": target_id,
                "target_type": "ilink_context",
                "platform_user_id": platform_user_id,
                "tenant_id": tenant_id,
                "session_id": str(message.session_id or "").strip() or None,
            }

    if chat_id:
        return {
            "channel": channel,
            "target_id": chat_id,
            "target_type": "chat_id",
            "platform_user_id": str(message.platform_user_id or "").strip() or None,
            "session_id": str(message.session_id or "").strip() or None,
        }
    return None


def _build_session_id(message: UnifiedMessage) -> str:
    if message.session_id:
        return message.session_id
    metadata_session_id = message.metadata.get("session_id")
    if isinstance(metadata_session_id, str) and metadata_session_id.strip():
        return metadata_session_id
    return f"{message.channel.value}:{message.chat_id}"


def _should_handoff_to_reception_agent(
    *,
    interaction_mode: str | None,
    manager_packet: dict[str, Any] | None,
) -> bool:
    normalized_interaction_mode = str(interaction_mode or "").strip().lower()
    manager_action = str((manager_packet or {}).get("manager_action") or "").strip().lower()
    return normalized_interaction_mode == "chat" or manager_action in {"clarify_request", "reception_reply"}


def _finalize_reception_reply_text(
    *,
    text: str,
    user_key: str,
    auth_scope: str,
) -> str:
    outbound_result = security_gateway_service.inspect_text_entrypoint_snapshot(
        text=text,
        user_key=f"outbound:{user_key}",
        auth_scope=auth_scope,
        direction="output",
    )
    if not bool(outbound_result.get("allowed")):
        return HERMES_REPLY_BLOCKED_RESPONSE
    return str(outbound_result.get("sanitized_text") or text).strip() or HERMES_REPLY_BLOCKED_RESPONSE


def _resolve_hermes_writeback_subject(
    *,
    scope: str,
    tenant_id: str | None,
    customer_id: str | None,
    task_id: str | None,
    explicit_subject_id: str | None,
) -> tuple[str | None, str | None]:
    normalized_scope = str(scope or "").strip().lower()
    normalized_subject_id = str(explicit_subject_id or "").strip() or None
    if normalized_scope == "tenant":
        return "tenant", normalized_subject_id or tenant_id
    if normalized_scope == "task_summary":
        return "task_summary", normalized_subject_id or task_id
    if normalized_scope == "customer":
        return "customer", normalized_subject_id or customer_id
    return None, None


def _apply_hermes_memory_writeback(
    *,
    hermes_result: dict[str, Any],
    message: UnifiedMessage,
    trace_id: str,
) -> list[dict[str, Any]]:
    distillation_memory_types = {
        "session_summary",
        "user_preference",
        "agent_decision",
        "task_result",
        "event_digest",
    }
    raw_items = hermes_result.get("memory_writeback")
    if not isinstance(raw_items, list):
        return []

    metadata = message.metadata if isinstance(message.metadata, dict) else {}
    tenant_id = _metadata_tenant_id(metadata)
    customer_id = str(metadata.get("customer_id") or message.platform_user_id or "").strip() or None
    task_id = str(metadata.get("task_id") or metadata.get("taskId") or "").strip() or None
    memory_scope = _memory_scope_for_message(tenant_id=tenant_id)
    results: list[dict[str, Any]] = []

    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        scope = str(raw_item.get("scope") or "").strip().lower() or "customer"
        memory_type = str(raw_item.get("memory_type") or raw_item.get("memoryType") or "").strip() or "business_fact"
        summary = str(raw_item.get("summary") or "").strip()
        title = str(raw_item.get("title") or "").strip() or None
        explicit_subject_id = str(raw_item.get("subject_id") or raw_item.get("subjectId") or "").strip() or None
        result_entry = {
            "scope": scope,
            "memory_type": memory_type,
            "subject_id": explicit_subject_id,
            "title": title,
            "summary": summary,
            "applied": False,
            "memory_id": None,
            "error": None,
        }
        if not summary:
            result_entry["error"] = "summary is required"
            results.append(result_entry)
            continue

        subject_type, resolved_subject_id = _resolve_hermes_writeback_subject(
            scope=scope,
            tenant_id=tenant_id,
            customer_id=customer_id,
            task_id=task_id,
            explicit_subject_id=explicit_subject_id,
        )
        result_entry["subject_id"] = resolved_subject_id
        if subject_type is None or resolved_subject_id is None:
            result_entry["error"] = "unable to resolve writeback subject"
            results.append(result_entry)
            continue

        try:
            write_result = memory_service.write_long_term_memory(
                memory_type=memory_type,
                content=summary,
                summary=summary,
                title=title,
                scope=memory_scope,
                subject_type=subject_type,
                subject_id=resolved_subject_id,
                importance=raw_item.get("importance"),
                source="hermes_protocol_writeback",
                write_source="distillation" if memory_type in distillation_memory_types else "brain_internal",
                memory_scope="tenant",
            )
        except Exception as exc:
            logger.warning(
                "Hermes memory_writeback skipped: trace_id=%s scope=%s memory_type=%s error=%s",
                trace_id,
                scope,
                memory_type,
                exc,
            )
            result_entry["error"] = str(exc)
            results.append(result_entry)
            continue

        result_entry["applied"] = True
        result_entry["memory_id"] = str(write_result.get("memory_id") or "").strip() or None
        results.append(result_entry)

    return results


def _build_hermes_protocol_summary(
    *,
    hermes_result: dict[str, Any],
    writeback_results: list[dict[str, Any]],
) -> dict[str, Any] | None:
    protocol_mode = str(hermes_result.get("protocol_mode") or "").strip() or None
    interaction_mode = str(hermes_result.get("interaction_mode") or "").strip() or None
    task_signal = _normalized_hermes_task_signal(hermes_result) or None
    request_id = str(hermes_result.get("request_id") or "").strip() or None
    binding_id = str(hermes_result.get("binding_id") or "").strip() or None
    safety_signal = str(hermes_result.get("safety_signal") or "").strip() or None
    confidence = hermes_result.get("confidence")
    requirement_payload = (
        store.clone(hermes_result.get("requirement_payload"))
        if isinstance(hermes_result.get("requirement_payload"), dict)
        else None
    )
    attachments = _hermes_attachments(hermes_result)
    if not any((protocol_mode, interaction_mode, task_signal, request_id, binding_id, safety_signal, writeback_results, requirement_payload, attachments)):
        return None
    return {
        "request_id": request_id,
        "binding_id": binding_id,
        "protocol_mode": protocol_mode,
        "interaction_mode": interaction_mode,
        "task_signal": task_signal,
        "safety_signal": safety_signal,
        "confidence": confidence,
        "requirement_payload": requirement_payload,
        "memory_writeback": store.clone(writeback_results),
        "attachments": store.clone(attachments),
    }


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
    persistence_service.persist_runtime_state()


def _apply_orchestration_follow_up_plan(
    follow_up_plan: Any,
    *,
    task: dict,
    steps: list[dict] | None = None,
    message_text: str | None = None,
    trace_id: str | None = None,
) -> str | None:
    run_id = str(getattr(follow_up_plan, "run_id", "") or "").strip() or None
    if bool(getattr(follow_up_plan, "should_sync_run_from_task", False)):
        refreshed_run = sync_workflow_run_from_task(task)
        return str((refreshed_run or {}).get("id") or run_id or "").strip() or None
    if bool(getattr(follow_up_plan, "should_tick_run", False)):
        if run_id is None:
            _persist_execution_state(task=task, steps=steps)
            return None
        refreshed_run = tick_workflow_run(run_id)
        return str(refreshed_run.get("id") or "").strip() or run_id
    if bool(getattr(follow_up_plan, "should_append_patch_to_run", False)):
        if run_id is not None and message_text is not None and trace_id is not None:
            append_context_patch_to_run(run_id, message_text, trace_id)
        return run_id
    if bool(getattr(follow_up_plan, "should_persist_task_steps", False)) or (run_id is None and steps is not None):
        _persist_execution_state(task=task, steps=steps)
    return run_id


def _launch_message_run(
    *,
    task: dict,
    intent: str,
    entrypoint: str,
    memory_hits: int,
    warnings: list[str],
    dispatch_context: dict[str, Any],
    launch_plan: Any,
) -> dict:
    launch_mode = str(getattr(launch_plan, "mode", "") or "").strip() or "workflow_run"
    if launch_mode != "workflow_run":
        raise ValueError("Message ingress launch plan must use workflow_run mode")
    workflow_id = (
        str(getattr(launch_plan, "workflow_id", "") or "").strip()
        or str(task.get("workflow_id") or "").strip()
        or str((task.get("route_decision") or {}).get("workflow_id") or "").strip()
        or str((task.get("route_decision") or {}).get("workflowId") or "").strip()
    )
    if not workflow_id or workflow_id in {"__agent_dispatch__", "__direct_agent_fallback__"}:
        raise ValueError("Message ingress must launch a real workflow run")
    return create_workflow_run_for_task(
        task=task,
        intent=intent,
        trigger=entrypoint,
        memory_hits=memory_hits,
        warnings=warnings,
        workflow_id=workflow_id,
        dispatch_context=dispatch_context,
    )


def _build_safe_ingest_response(
    *,
    message: UnifiedMessage,
    security_result: dict[str, Any],
    entrypoint: str,
) -> dict:
    return task_view_service.build_ingest_response(
        result_message="",
        entrypoint=entrypoint,
        unified_message=message.model_dump(),
        ok=True,
        task_id=None,
        run_id=None,
        intent=None,
        trace_id=str(security_result.get("trace_id") or "").strip() or None,
        detected_lang=message.detected_lang,
        memory_hits=0,
        warnings=list(security_result.get("warnings") or []),
        merged_into_task_id=None,
        interaction_mode="chat",
        reception_mode="continuation",
        route_decision={
            "workflow_mode": "dialogue_workflow",
            "interaction_mode": "chat",
            "reception_mode": "continuation",
        },
    )


def _normalize_interaction_mode(value: object) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in INTERACTION_MODES:
        return normalized
    return None


def _resolve_interaction_mode(route_decision: dict | None) -> str:
    if isinstance(route_decision, dict):
        mode = _normalize_interaction_mode(
            route_decision.get("interaction_mode") or route_decision.get("interactionMode")
        )
        if mode:
            return mode
    return "workflow_or_direct"


def _route_decision_field(route_decision: dict | None, *keys: str) -> str | None:
    if not isinstance(route_decision, dict):
        return None
    for key in keys:
        value = str(route_decision.get(key) or "").strip()
        if value:
            return value
    return None


def _route_decision_bool(route_decision: dict | None, *keys: str) -> bool:
    if not isinstance(route_decision, dict):
        return False
    for key in keys:
        value = route_decision.get(key)
        if isinstance(value, bool):
            return value
    return False


def _active_task_context_payload(task_id: str | None) -> dict[str, Any] | None:
    normalized_task_id = str(task_id or "").strip()
    if not normalized_task_id:
        return None

    task = _find_task(normalized_task_id)
    if task is None:
        return None

    summary = _truncate_text(
        str(task.get("description") or task.get("result") or task.get("title") or "").strip(),
        240,
    )
    updated_at = _latest_message_at_for_task(task).isoformat()
    return {
        "task_id": normalized_task_id,
        "title": str(task.get("title") or "").strip() or None,
        "status": str(task.get("status") or "").strip() or None,
        "summary": summary or None,
        "updated_at": updated_at,
    }


def _attach_active_task_context(message: UnifiedMessage) -> str | None:
    if not isinstance(message.metadata, dict):
        message.metadata = {}

    existing_task_id = _text(message.metadata.get("task_id") or message.metadata.get("taskId"))
    if existing_task_id:
        task_context = _active_task_context_payload(existing_task_id)
        if task_context is not None:
            message.metadata["active_task_context"] = task_context
        return existing_task_id or None

    active_task = _resolve_active_task_for_user(message.user_key or "")
    if active_task is None:
        return None

    task_id, _last_message_at = active_task
    task_context = _active_task_context_payload(task_id)
    if task_context is None:
        return None

    message.metadata["task_id"] = task_id
    message.metadata["taskId"] = task_id
    message.metadata["active_task_context"] = task_context
    return task_id


def _hermes_interaction_mode(hermes_result: dict[str, Any]) -> str:
    normalized = str(hermes_result.get("interaction_mode") or "").strip().lower()
    if normalized in {"continuation", "chat", "task"}:
        return normalized

    task_signal = str(hermes_result.get("task_signal") or "").strip().lower()
    if task_signal in {"dispatch_task", "handoff_human"}:
        return "task"
    return "chat"


def _normalized_hermes_task_signal(hermes_result: dict[str, Any]) -> str:
    task_signal = str(hermes_result.get("task_signal") or "").strip().lower()
    interaction_mode = str(hermes_result.get("interaction_mode") or "").strip().lower()
    if task_signal == "handoff_human":
        return "dispatch_task"
    if task_signal == "dispatch_task":
        return "dispatch_task"
    if interaction_mode == "task":
        return "dispatch_task"
    if task_signal == "stay_in_reception":
        return "stay_in_reception"
    return ""


def _hermes_requirement_payload(hermes_result: dict[str, Any]) -> dict[str, Any] | None:
    payload = hermes_result.get("requirement_payload")
    if isinstance(payload, dict):
        return store.clone(payload)
    payload = hermes_result.get("requirementPayload")
    if isinstance(payload, dict):
        return store.clone(payload)
    return None


def _hermes_requirement_summary(hermes_result: dict[str, Any]) -> str:
    payload = _hermes_requirement_payload(hermes_result)
    if isinstance(payload, dict):
        for key in ("summary", "details", "category", "urgency"):
            value = str(payload.get(key) or "").strip()
            if value:
                return value
    return str(hermes_result.get("reply_text") or "").strip()


def _hermes_requirement_description(hermes_result: dict[str, Any]) -> str:
    payload = _hermes_requirement_payload(hermes_result)
    if isinstance(payload, dict):
        summary = str(payload.get("summary") or "").strip()
        details = str(payload.get("details") or "").strip()
        if summary and details and details != summary:
            return f"{summary}\n\n{details}"
        if summary:
            return summary
        if details:
            return details
    return _hermes_requirement_summary(hermes_result)


def _hermes_attachments(hermes_result: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = hermes_result.get("attachments") or hermes_result.get("artifacts")
    if not isinstance(raw_items, list):
        return []
    items: list[dict[str, Any]] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        file_path = str(raw_item.get("file_path") or raw_item.get("filePath") or "").strip()
        file_name = str(raw_item.get("file_name") or raw_item.get("fileName") or "").strip()
        if not file_path or not file_name:
            continue
        items.append(
            {
                "title": str(raw_item.get("title") or file_name).strip() or file_name,
                "file_name": file_name,
                "file_path": file_path,
                "mime_type": str(raw_item.get("mime_type") or raw_item.get("mimeType") or "").strip() or "application/octet-stream",
                "kind": str(raw_item.get("kind") or "").strip() or None,
                "format": str(raw_item.get("format") or "").strip() or None,
                "size_bytes": raw_item.get("size_bytes") if isinstance(raw_item.get("size_bytes"), int) else raw_item.get("sizeBytes"),
            }
        )
    return items


def _request_base_url_from_message(message: UnifiedMessage) -> str | None:
    metadata = message.metadata if isinstance(message.metadata, dict) else {}
    return _metadata_text(metadata, "request_base_url", "requestBaseUrl")


def _append_attachment_links(reply_text: str, attachments: list[dict[str, Any]]) -> str:
    if not attachments:
        return reply_text
    lines = [str(reply_text or "").strip(), "", "附件下载："]
    for index, item in enumerate(attachments, start=1):
        title = str(item.get("title") or item.get("file_name") or f"附件{index}").strip()
        download_url = str(item.get("download_url") or item.get("downloadUrl") or item.get("download_path") or "").strip()
        if not download_url:
            continue
        lines.append(f"{index}. {title}: {download_url}")
    return "\n".join(lines).strip()


def _register_hermes_attachments(
    *,
    message: UnifiedMessage,
    hermes_result: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    attachments = _hermes_attachments(hermes_result)
    if not attachments:
        return [], []
    metadata = message.metadata if isinstance(message.metadata, dict) else {}
    tenant_id = _metadata_text(metadata, "tenant_id", "tenantId")
    customer_id = _metadata_text(metadata, "customer_id", "customerId") or str(message.platform_user_id or "").strip() or None
    request_base_url = _request_base_url_from_message(message)
    return reception_shared_files_service.register_attachments(
        attachments=attachments,
        tenant_id=tenant_id,
        customer_id=customer_id,
        request_base_url=request_base_url,
    )


def _inspect_hermes_result_payload(
    *,
    message: UnifiedMessage,
    hermes_result: dict[str, Any],
    auth_scope: str,
    parent_trace_id: str | None,
) -> tuple[bool, dict[str, Any], dict[str, Any] | None]:
    sanitized_result = store.clone(hermes_result)

    def _inspect_text(value: str, *, suffix: str, trace_id: str | None) -> tuple[bool, dict[str, Any] | str]:
        try:
            inspection = security_gateway_service.inspect_text_entrypoint_snapshot(
                text=value,
                user_key=f"hermes:{message.user_key}:{suffix}",
                auth_scope=auth_scope,
                direction="output",
                trace_id=trace_id,
            )
        except TypeError:
            inspection = security_gateway_service.inspect_text_entrypoint_snapshot(
                text=value,
                user_key=f"hermes:{message.user_key}:{suffix}",
                auth_scope=auth_scope,
                direction="output",
            )
        if not bool(inspection.get("allowed")):
            detail = str(inspection.get("detail") or "Security policy blocked Hermes result").strip()
            security_verdict = inspection.get("security_verdict")
            verdict_payload = security_verdict if isinstance(security_verdict, dict) else {}
            return False, {
                "detail": detail,
                "trace_id": str(inspection.get("trace_id") or "").strip() or None,
                "status_code": int(inspection.get("status_code") or 403),
                "security_layer": _metadata_text(verdict_payload, "layer"),
                "security_rule_name": _metadata_text(verdict_payload, "rule_name", "ruleName"),
            }
        return True, str(inspection.get("sanitized_text") or value).strip()

    reply_text = str(sanitized_result.get("reply_text") or "").strip()
    if reply_text:
        allowed, reply_or_detail = _inspect_text(
            reply_text,
            suffix="reply_text",
            trace_id=parent_trace_id,
        )
        if not allowed:
            block_payload = reply_or_detail if isinstance(reply_or_detail, dict) else {}
            detail = str(block_payload.get("detail") or "Security policy blocked Hermes result").strip()
            return False, sanitized_result, {
                **block_payload,
                "detail": f"reply_text: {detail}",
            }
        sanitized_result["reply_text"] = reply_or_detail

    requirement_payload = _hermes_requirement_payload(sanitized_result)
    if isinstance(requirement_payload, dict):
        sanitized_requirement = store.clone(requirement_payload)
        for field in ("summary", "details"):
            raw_value = str(sanitized_requirement.get(field) or "").strip()
            if not raw_value:
                continue
            allowed, sanitized_or_detail = _inspect_text(
                raw_value,
                suffix=f"requirement_{field}",
                trace_id=parent_trace_id,
            )
            if not allowed:
                block_payload = sanitized_or_detail if isinstance(sanitized_or_detail, dict) else {}
                detail = str(block_payload.get("detail") or "Security policy blocked Hermes result").strip()
                return False, sanitized_result, {
                    **block_payload,
                    "detail": f"requirement_payload.{field}: {detail}",
                }
            sanitized_requirement[field] = sanitized_or_detail
        sanitized_result["requirement_payload"] = sanitized_requirement

    return True, sanitized_result, None


def _build_hermes_task_dispatch_metadata(
    *,
    hermes_result: dict[str, Any],
    clone: Any,
) -> Any:
    interaction_mode = "task"
    task_signal = _normalized_hermes_task_signal(hermes_result) or "dispatch_task"
    intent = str(hermes_result.get("intent") or "reception_task").strip() or "reception_task"
    summary = _hermes_requirement_summary(hermes_result)
    route_decision = {
        "intent": intent,
        "interaction_mode": interaction_mode,
        "interactionMode": interaction_mode,
        "reception_mode": "task_handoff",
        "receptionMode": "task_handoff",
        "workflow_mode": "task_handoff",
        "workflowMode": "task_handoff",
        "execution_scope": "pending_dispatch",
        "executionScope": "pending_dispatch",
        "routing_strategy": "hermes_reception_result",
        "routingStrategy": "hermes_reception_result",
        "hermes_task_signal": task_signal,
        "hermesTaskSignal": task_signal,
        "route_rationale": {
            "route_reason_summary": summary or "Hermes 将当前会话识别为需求任务。",
        },
    }
    manager_packet = {
        "manager_role": "reception_manager",
        "manager_action": "handoff_to_dispatch_queue",
        "next_owner": "需求分发 Agent",
        "delivery_mode": "pending_dispatch",
        "response_contract": "task_intake_record",
        "clarify_required": False,
        "clarify_question": str(hermes_result.get("clarify_question") or "").strip() or None,
        "handoff_summary": summary or None,
        "session_state": "pending_dispatch",
        "state_label": "待分发",
    }
    brain_dispatch_summary = {
        "intent": intent,
        "dispatch_mode": "pending_dispatch",
        "dispatch_type": "hermes_task_intake",
        "workflow_mode": "task_handoff",
        "interaction_mode": interaction_mode,
        "reception_mode": "task_handoff",
        "execution_agent": "需求分发 Agent",
        "manager_action": manager_packet["manager_action"],
        "next_owner": manager_packet["next_owner"],
        "delivery_mode": manager_packet["delivery_mode"],
        "response_contract": manager_packet["response_contract"],
        "summary_line": summary or "Hermes 已识别需求并交还平台建任务。",
        "session_state": manager_packet["session_state"],
        "state_label": manager_packet["state_label"],
    }
    return orchestration_service.prepare_message_dispatch_metadata(
        route_decision=route_decision,
        manager_packet=manager_packet,
        brain_dispatch_summary=brain_dispatch_summary,
        interaction_mode=interaction_mode,
        approval_required=False,
        confirmation_status=None,
        confirmation_required=False,
        clone=clone,
    )


def _create_task_from_hermes_result(
    *,
    message: UnifiedMessage,
    hermes_result: dict[str, Any],
    entrypoint: str,
    entrypoint_agent: str,
    trace_id: str,
    preferred_language: str | None,
    memory_matches: dict[str, Any],
    security_result: dict[str, Any],
    message_tenant_id: str | None,
    message_tenant_name: str | None,
    security_context: dict[str, Any],
) -> dict[str, Any]:
    task_id = _next_task_id()
    memory_items = memory_matches["items"]
    memory_injection_summary = _memory_injection_summary(memory_items)
    metadata = _build_hermes_task_dispatch_metadata(
        hermes_result=hermes_result,
        clone=store.clone,
    )
    requirement_summary = _hermes_requirement_summary(hermes_result)
    requirement_description = _hermes_requirement_description(hermes_result)
    execution_agent_name = "需求分发 Agent"
    artifacts = orchestration_service.build_message_task_artifacts(
        task_id=task_id,
        message=message,
        entrypoint=entrypoint,
        entrypoint_agent=entrypoint_agent,
        trace_id=trace_id,
        preferred_language=preferred_language,
        memory_hits=memory_matches["total"],
        memory_items=memory_items,
        memory_injection_summary=memory_injection_summary,
        metadata=metadata,
        intent=str(hermes_result.get("intent") or "reception_task").strip() or "reception_task",
        route_message=requirement_summary,
        execution_agent_name=execution_agent_name,
        agent_dispatch=False,
        state_machine_version=FACT_LAYER_STATE_MACHINE_VERSION,
        warnings=list(security_result["warnings"]),
        truncate_text=_truncate_text,
        dispatch_context_memory_items=_dispatch_context_memory_items,
        build_channel_delivery_binding=_build_channel_delivery_binding,
        preview_limit=DISPATCH_CONTEXT_TEXT_PREVIEW_LIMIT,
        now_string=store.now_string,
        clone=store.clone,
        memory_context_lines=_memory_context_lines,
        memory_step_message=_memory_step_message,
        tenant_id=message_tenant_id,
        tenant_name=message_tenant_name,
        security_context=security_context,
    )
    task = artifacts.task
    route_decision = artifacts.route_decision
    manager_packet = artifacts.manager_packet
    task["title"] = _truncate_text(requirement_summary or "接待需求登记", 80)
    task["description"] = requirement_description or str(task.get("description") or "")
    task["workflow_run_id"] = None
    task["workflowRunId"] = None
    task["requirement_payload"] = _hermes_requirement_payload(hermes_result)
    task["status"] = "pending"
    state_machine = task.get("state_machine")
    if isinstance(state_machine, dict):
        state_machine["task_status"] = "pending"
        state_machine["session_state"] = str(manager_packet.get("session_state") or "pending_dispatch")

    store.tasks.append(task)
    store.task_steps[task_id] = list(artifacts.task_steps)
    AUTHORITATIVE_TASK_STEP_CACHE.add(task_id)
    mark_task_steps_authoritative(task_id)
    _persist_execution_state(task=task, steps=artifacts.task_steps)
    try:
        dispatch_result = dispatch_requirement_task(task_id, trigger="hermes_task_created")
        dispatched_task = dispatch_result.get("task")
        if isinstance(dispatched_task, dict):
            task = dispatched_task
    except Exception as exc:  # pragma: no cover - defensive runtime path
        logger.warning("Requirement dispatch failed for task %s: %s", task_id, exc)
        append_realtime_event(
            agent="需求分发 Agent",
            message=f"任务 {task_id} 已创建，但需求下发暂未完成",
            type_="warning",
            source="message_ingestion",
            trace_id=trace_id,
            task_id=task_id,
            metadata={
                "event": "requirement_dispatch_failed",
                "error": str(exc),
            },
        )

    append_realtime_event(
        agent="Dispatcher Agent",
        message=f"已根据 Hermes 结果创建任务 {task_id}",
        type_="success",
        source="message_ingestion",
        trace_id=trace_id,
        task_id=task_id,
        metadata={
            "event": "task_created_from_hermes",
            "user_key": message.user_key,
            "interaction_mode": "task",
            "task_signal": _normalized_hermes_task_signal(hermes_result) or None,
            "manager_action": str(manager_packet.get("manager_action") or "").strip() or None,
            "summary": requirement_summary or None,
        },
    )
    ACTIVE_TASKS_BY_USER[message.user_key] = task_id
    return task_view_service.build_task_event_response(
        result_message=str(hermes_result.get("reply_text") or ""),
        entrypoint=entrypoint,
        task=task,
        unified_message=message.model_dump(),
        run_id=None,
        intent=str(hermes_result.get("intent") or "reception_task").strip() or "reception_task",
        trace_id=trace_id,
        detected_lang=message.detected_lang,
        memory_hits=memory_matches["total"],
        warnings=list(security_result["warnings"]),
        merged_into_task_id=None,
        interaction_mode="task",
        reception_mode="task_handoff",
    )


def _is_professional_confirmation_pending(task: dict) -> bool:
    return reception_service.is_professional_confirmation_pending(task)


def _confirmation_action(message_text: str) -> str | None:
    return reception_service.confirmation_action(message_text)


def _append_confirmation_step(task_id: str, *, title: str, message: str, status_value: str = "completed") -> None:
    steps = _ensure_task_steps_loaded(task_id)
    steps.append(
        orchestration_service.build_confirmation_step(
            task_id=task_id,
            existing_step_count=len(steps),
            title=title,
            message=message,
            status_value=status_value,
            now_string=store.now_string,
        )
    )
    AUTHORITATIVE_TASK_STEP_CACHE.add(task_id)
    mark_task_steps_authoritative(task_id)


def _handle_professional_confirmation_reply(
    message: UnifiedMessage,
    *,
    received_at: datetime,
    security_result: dict[str, object],
) -> dict | None:
    active_task = _resolve_active_task_for_user(message.user_key)
    if active_task is None:
        return None

    task_id, _ = active_task
    task = _find_task(task_id)
    if task is None or not _is_professional_confirmation_pending(task):
        return None

    action = _confirmation_action(message.text)
    if action is None:
        return None
    transition = reception_service.build_confirmation_transition(
        task=task,
        action=action,
        now_string=store.now_string,
    )

    run = _find_loaded_run(task.get("workflow_run_id"))
    orchestration_service.apply_confirmation_transition(
        task=task,
        run=run,
        action=action,
        transition=transition,
        now_string=store.now_string,
    )

    _append_confirmation_step(
        task_id,
        title=transition.step_title,
        message=transition.step_message,
        status_value=transition.step_status,
    )
    follow_up_plan = orchestration_service.build_confirmation_follow_up_plan(
        task=task,
        action=action,
    )
    response_run_id = _apply_orchestration_follow_up_plan(
        follow_up_plan,
        task=task,
        steps=_ensure_task_steps_loaded(task_id),
    )

    LAST_MESSAGE_AT_BY_USER[message.user_key] = received_at
    return task_view_service.build_task_event_response(
        result_message=transition.response_message,
        entrypoint="master_bot.confirmation",
        task=task,
        unified_message=message.model_dump(),
        run_id=response_run_id,
        intent=_task_route_intent(task),
        trace_id=str(security_result["trace_id"]),
        detected_lang=message.detected_lang,
        memory_hits=0,
        warnings=list(security_result["warnings"]),
        merged_into_task_id=task_id,
    )


def _task_route_intent(task: dict | None) -> str | None:
    return reception_service.infer_task_intent(task)


def _task_status(task: dict | None) -> str:
    return str((task or {}).get("status") or "").strip().lower()


def _find_latest_task_for_user(user_key: str) -> dict | None:
    latest_task: dict | None = None
    latest_message_at: datetime | None = None
    normalized_user_key = str(user_key or "").strip()
    if not normalized_user_key:
        return None

    for candidate in _load_tasks_for_bootstrap():
        task_id = str(candidate.get("id") or "").strip()
        if not task_id or str(candidate.get("user_key") or "").strip() != normalized_user_key:
            continue

        task = _find_task(task_id) or _sync_cached_task(candidate)
        candidate_message_at = _latest_message_at_for_task(task)
        if latest_message_at is None or candidate_message_at > latest_message_at:
            latest_task = task
            latest_message_at = candidate_message_at

    return latest_task


def _find_latest_context_patch_task_for_user(user_key: str) -> dict | None:
    latest_task = _find_latest_task_for_user(user_key)
    if _task_status(latest_task) not in CONTEXT_PATCH_TASK_STATUSES:
        return None
    return latest_task


def _resolve_context_patch_task_for_user(user_key: str) -> tuple[str, datetime] | None:
    normalized_user_key = str(user_key or "").strip()
    if not normalized_user_key:
        return None

    task_id = ACTIVE_TASKS_BY_USER.get(normalized_user_key)
    last_message_at = LAST_MESSAGE_AT_BY_USER.get(normalized_user_key)
    if task_id and last_message_at:
        task = _find_task(task_id)
        if _task_status(task) in CONTEXT_PATCH_TASK_STATUSES:
            latest_message_at = _latest_message_at_for_task(task)
            if latest_message_at > last_message_at:
                last_message_at = latest_message_at
                LAST_MESSAGE_AT_BY_USER[normalized_user_key] = latest_message_at
            ACTIVE_TASKS_BY_USER[normalized_user_key] = task_id
            return task_id, last_message_at

    latest_task = _find_latest_context_patch_task_for_user(normalized_user_key)
    if latest_task is None:
        ACTIVE_TASKS_BY_USER.pop(normalized_user_key, None)
        LAST_MESSAGE_AT_BY_USER.pop(normalized_user_key, None)
        return None

    latest_task_id = str(latest_task.get("id") or "").strip()
    if not latest_task_id:
        return None

    latest_message_at = _latest_message_at_for_task(latest_task)
    ACTIVE_TASKS_BY_USER[normalized_user_key] = latest_task_id
    LAST_MESSAGE_AT_BY_USER[normalized_user_key] = latest_message_at
    return latest_task_id, latest_message_at


def _should_context_patch(user_key: str, received_at: datetime, message_text: str) -> str | None:
    settings = get_settings()
    context_patch_task = _resolve_context_patch_task_for_user(user_key)
    if context_patch_task is None:
        return None
    task_id, last_message_at = context_patch_task

    task = _find_task(task_id)
    if task is None or _task_status(task) not in CONTEXT_PATCH_TASK_STATUSES:
        return None
    if (received_at - last_message_at).total_seconds() > float(settings.message_debounce_seconds):
        return None
    if not reception_service.should_merge_into_active_task(
        active_task=task,
        message_text=message_text,
    ):
        return None
    return task_id


def _resolve_active_task_for_user(user_key: str) -> tuple[str, datetime] | None:
    find_latest_active_task = getattr(persistence_service, "find_latest_active_task_for_user", None)
    active_task = reception_service.resolve_active_task_reference(
        user_key=user_key,
        active_tasks_by_user=ACTIVE_TASKS_BY_USER,
        last_message_at_by_user=LAST_MESSAGE_AT_BY_USER,
        find_task=_find_task,
        latest_message_at_for_task=_latest_message_at_for_task,
        find_latest_active_task_for_user=find_latest_active_task if callable(find_latest_active_task) else None,
    )
    if active_task is None:
        return None
    return active_task.task_id, active_task.last_message_at


def _append_context_patch(task_id: str, message: UnifiedMessage, trace_id: str) -> None:
    task = _find_task(task_id)
    if task is None:
        return

    _refresh_task_steps_from_database(task_id)
    plan = reception_service.build_context_patch_plan(
        task=task,
        message_text=message.text,
        trace_id=trace_id,
        channel=message.channel.value,
        user_key=message.user_key,
        preview_limit=DISPATCH_CONTEXT_TEXT_PREVIEW_LIMIT,
        truncate_text=_truncate_text,
        state_machine_version=FACT_LAYER_STATE_MACHINE_VERSION,
        now_string=store.now_string,
    )
    applied_patch = orchestration_service.apply_context_patch_plan(
        task=task,
        plan=plan,
    )

    steps = _ensure_task_steps_loaded(task_id)
    steps.append(
        orchestration_service.build_context_patch_step(
            task_id=task_id,
            existing_step_count=len(steps),
            step_entry=applied_patch["step_entry"],
        )
    )
    follow_up_plan = orchestration_service.build_context_patch_follow_up_plan(task=task)
    workflow_run_id = _apply_orchestration_follow_up_plan(
        follow_up_plan,
        task=task,
        steps=steps,
        message_text=message.text,
        trace_id=trace_id,
    )
    append_realtime_event(
        agent="Dispatcher Agent",
        message=f"任务 {task_id} 已吸收追加上下文",
        type_="info",
        source="message_ingestion",
        trace_id=trace_id,
        task_id=task_id,
        workflow_run_id=workflow_run_id,
        metadata=applied_patch["realtime_metadata"],
    )


def ingest_unified_message(
    message: UnifiedMessage,
    *,
    auth_scope: str = "messages:ingest",
    entrypoint: str = "master_bot.dispatch",
    entrypoint_agent: str = "Unified Message API",
) -> dict:
    settings = get_settings()
    security_result = security_gateway_service.inspect_text_entrypoint_snapshot(
        text=message.text,
        user_key=f"{message.channel.value}:{message.platform_user_id}",
        auth_scope=auth_scope,
        direction="input",
    )
    message.user_key = str(security_result["user_key"])
    message.session_id = _build_session_id(message)
    if not bool(security_result.get("allowed")):
        trace_id = str(security_result.get("trace_id") or "").strip() or None
        _append_intake_admission_event(
            message=message,
            status="security_blocked",
            agent="安全监听层",
            text="渠道消息被安全监听阻断",
            trace_id=trace_id,
            type_="error",
            metadata={
                "reason": str(security_result.get("detail") or "").strip() or None,
                "security_layer": _metadata_text(
                    security_result.get("security_verdict") or {},
                    "layer",
                ),
                "status_code": int(security_result.get("status_code") or 403),
            },
        )
        raise HTTPException(
            status_code=int(security_result.get("status_code") or 403),
            detail=str(security_result.get("detail") or "Security policy blocked this request"),
        )
    original_message_text = str(message.text)
    sanitized_message_text = str(security_result["sanitized_text"])
    try:
        # 客户准入需要读取原始身份字段，避免手机号等关键字段被安全脱敏后无法完成绑定。
        message.text = original_message_text
        admission_result = customer_access_service.admit_message(message)
    finally:
        message.text = sanitized_message_text
    if admission_result.status != "bound":
        reply_text = str(admission_result.reply_message or "").strip() or "当前无法接入平台接待。"
        _append_intake_admission_event(
            message=message,
            status=admission_result.status,
            agent="客户准入层",
            text=(
                "客户准入待补充"
                if admission_result.status == "pending_verification"
                else "客户准入已拒绝"
            ),
            trace_id=str(security_result["trace_id"]),
            type_="warning" if admission_result.status == "pending_verification" else "error",
            metadata={
                "missing_fields": list(admission_result.missing_fields),
                "reason": reply_text,
            },
        )
        if auth_scope.startswith("webhook:"):
            channel_outbound_service.deliver_reception_reply(
                message=message,
                text=reply_text,
                trace_id=str(security_result["trace_id"]),
                channel_delivery_binding=_build_channel_delivery_binding(message),
            )
        return task_view_service.build_ingest_response(
            result_message=reply_text,
            entrypoint="master_bot.customer_access",
            unified_message=message.model_dump(),
            ok=admission_result.status != "rejected",
            trace_id=str(security_result["trace_id"]),
            detected_lang=message.detected_lang,
            memory_hits=0,
            warnings=list(security_result["warnings"]),
            interaction_mode="chat",
            reception_mode="customer_access",
        )
    _append_intake_admission_event(
        message=message,
        status="passed",
        agent="客户准入层",
        text="客户准入通过，已完成服务绑定" if _text(admission_result.reply_message) else "客户准入通过，已进入 Hermes 接待",
        trace_id=str(security_result["trace_id"]),
        type_="success",
        metadata={
            "profile_id": admission_result.profile_id,
            "customer_id": admission_result.customer_id,
            "service_code": admission_result.service_code,
            "reply_message": _truncate_text(_text(admission_result.reply_message), 120) or None,
        },
    )
    bound_reply_text = str(admission_result.reply_message or "").strip()
    if bound_reply_text:
        if auth_scope.startswith("webhook:"):
            channel_outbound_service.deliver_reception_reply(
                message=message,
                text=bound_reply_text,
                trace_id=str(security_result["trace_id"]),
                channel_delivery_binding=_build_channel_delivery_binding(message),
            )
        LAST_MESSAGE_AT_BY_USER[message.user_key] = _parse_datetime(message.received_at)
        return task_view_service.build_ingest_response(
            result_message=bound_reply_text,
            entrypoint="master_bot.customer_access",
            unified_message=message.model_dump(),
            ok=True,
            trace_id=str(security_result["trace_id"]),
            detected_lang=message.detected_lang,
            memory_hits=0,
            warnings=list(security_result["warnings"]),
            interaction_mode="chat",
            reception_mode="customer_access",
        )
    preferred_language = _resolved_preferred_language(message)
    message.detected_lang = detect_language(
        message.text,
        preferred_language=preferred_language,
    )
    message_tenant_id, message_tenant_name = _resolved_message_tenant_binding(message)
    memory_scope = _memory_scope_for_message(tenant_id=message_tenant_id)
    security_context = {
        "trace_id": str(security_result.get("trace_id") or "").strip() or None,
        "auth_scope": auth_scope,
        "warning_count": len(security_result.get("warnings") or []),
        "prompt_injection_assessment": store.clone(
            security_result.get("prompt_injection_assessment") or {}
        ),
        "rewrite_diffs_count": len(security_result.get("rewrite_diffs") or []),
    }
    _sync_message_user_profile(message, preferred_language=preferred_language)

    short_term_result = memory_service.ingest_message(
        user_id=message.user_key,
        session_id=message.session_id,
        role="user",
        content=message.text,
        detected_lang=message.detected_lang,
        scope=memory_scope,
    )
    if short_term_result["auto_distilled_sessions"]:
        security_result["warnings"].append(
            f"Auto-distilled {len(short_term_result['auto_distilled_sessions'])} previous session(s) into mid/long-term memory"
        )
    if short_term_result.get("auto_weekly_distilled"):
        security_result["warnings"].append(
            "Auto-distilled the current session into mid/long-term memory on weekly cadence"
        )
    memory_matches = memory_service.retrieve(
        user_id=message.user_key,
        query=message.text,
        limit=settings.memory_retrieve_limit,
        scope=memory_scope,
    )

    if short_term_result["distill_recommended"]:
        distill_result = memory_service.distill(
            user_id=message.user_key,
            trigger="daily",
            session_id=message.session_id,
            scope=memory_scope,
        )
        if distill_result["created"]:
            security_result["warnings"].append("Short-term memory distilled into mid/long-term layers")

    received_at = _parse_datetime(message.received_at)
    confirmation_result = _handle_professional_confirmation_reply(
        message,
        received_at=received_at,
        security_result=security_result,
    )
    if confirmation_result is not None:
        return confirmation_result
    active_task_id = _attach_active_task_context(message)
    _, knowledge_warning = _attach_reception_knowledge_context(
        message,
        trace_id=str(security_result["trace_id"]),
    )
    if knowledge_warning:
        security_result["warnings"].append(f"Knowledge retrieval failed: {knowledge_warning}")
    hermes_result: dict[str, Any] | None = None
    hermes_protocol_summary: dict[str, Any] | None = None
    interaction_mode = "chat"
    reception_mode = "chat"
    reply_text = ""
    route_decision: dict[str, Any] | None = None

    _append_reception_session_event(
        message=message,
        state="serving",
        text="Hermes 正在接待当前客户",
        trace_id=str(security_result["trace_id"]),
        type_="info",
        metadata={
            **({"active_task_id": active_task_id} if active_task_id else {}),
            **_active_task_context_event_metadata(message),
            **_knowledge_context_event_metadata(message),
        },
    )
    try:
        hermes_result = hermes_reception_agent_service.reply(
            message=message,
        )
    except Exception as exc:
        logger.exception(
            "Hermes reception failed during message ingestion: user_key=%s channel=%s",
            message.user_key,
            message.channel.value,
        )
        _append_reception_session_event(
            message=message,
            state="failed",
            text=f"Hermes 接待调用失败：{exc}",
            trace_id=str(security_result["trace_id"]),
            type_="warning",
            metadata={
                "event": "hermes_reception_failed",
                "user_key": message.user_key,
                "reason": str(exc),
                **_active_task_context_event_metadata(message),
                **_knowledge_context_event_metadata(message),
            },
        )
        reply_text = HERMES_REPLY_FALLBACK_RESPONSE
        hermes_result = None

    if hermes_result is None:
        if auth_scope.startswith("webhook:") and reply_text:
            channel_outbound_service.deliver_reception_reply(
                message=message,
                text=reply_text,
                trace_id=str(security_result["trace_id"]),
                channel_delivery_binding=_build_channel_delivery_binding(message),
            )
        LAST_MESSAGE_AT_BY_USER[message.user_key] = received_at
        return task_view_service.build_ingest_response(
            result_message=reply_text,
            entrypoint="master_bot.reception",
            unified_message=message.model_dump(),
            trace_id=str(security_result["trace_id"]),
            detected_lang=message.detected_lang,
            memory_hits=memory_matches["total"],
            warnings=list(security_result["warnings"]),
            interaction_mode="chat",
            reception_mode="chat",
        )

    allowed_result, hermes_result, blocked_reason = _inspect_hermes_result_payload(
        message=message,
        hermes_result=hermes_result,
        auth_scope=auth_scope,
        parent_trace_id=str(security_result["trace_id"]),
    )
    if not allowed_result:
        blocked_reason = blocked_reason if isinstance(blocked_reason, dict) else {}
        blocked_detail = str(blocked_reason.get("detail") or "").strip() or "Hermes result blocked by security policy"
        security_result["warnings"].append(f"Hermes result blocked: {blocked_detail}")
        _append_intake_admission_event(
            message=message,
            status="security_blocked",
            agent="Hermes 回传安全监听",
            text="Hermes 回传结果被安全监听阻断",
            trace_id=str(security_result["trace_id"]),
            type_="error",
            metadata={
                "reason": blocked_detail,
                "security_layer": _metadata_text(blocked_reason, "security_layer"),
                "security_rule_name": _metadata_text(blocked_reason, "security_rule_name", "securityRuleName"),
                "status_code": _safe_int(blocked_reason.get("status_code")) or 403,
            },
        )
        _append_reception_session_event(
            message=message,
            state="failed",
            text="Hermes 回传结果被安全监听阻断",
            trace_id=str(security_result["trace_id"]),
            type_="warning",
            metadata={
                "event": "hermes_result_blocked",
                "reason": blocked_detail,
                "security_layer": _metadata_text(blocked_reason, "security_layer"),
                "security_rule_name": _metadata_text(blocked_reason, "security_rule_name", "securityRuleName"),
                "status_code": _safe_int(blocked_reason.get("status_code")) or 403,
                **_active_task_context_event_metadata(message),
                **_knowledge_context_event_metadata(message),
            },
        )
        LAST_MESSAGE_AT_BY_USER[message.user_key] = received_at
        return task_view_service.build_ingest_response(
            result_message="",
            entrypoint="master_bot.reception",
            unified_message=message.model_dump(),
            trace_id=str(security_result["trace_id"]),
            detected_lang=message.detected_lang,
            memory_hits=memory_matches["total"],
            warnings=list(security_result["warnings"]),
            interaction_mode="chat",
            reception_mode="blocked",
        )

    interaction_mode = _hermes_interaction_mode(hermes_result)
    reply_text = str(hermes_result.get("reply_text") or "").strip()
    registered_attachments, attachment_errors = _register_hermes_attachments(
        message=message,
        hermes_result=hermes_result,
    )
    if attachment_errors:
        for error in attachment_errors:
            security_result["warnings"].append(f"Hermes attachment skipped: {error}")
    if registered_attachments:
        hermes_result["attachments"] = store.clone(registered_attachments)
        reply_text = _append_attachment_links(reply_text, registered_attachments)
        hermes_result["reply_text"] = reply_text
        security_result["warnings"].append(f"Hermes attachments linked: {len(registered_attachments)}")
    if interaction_mode == "continuation":
        reception_mode = "continuation"
    elif interaction_mode == "task":
        reception_mode = "task_handoff"
    else:
        reception_mode = "chat"

    if hermes_result.get("memory_writeback"):
        security_result["warnings"].append(
            "Platform-managed memory mode: Hermes memory_writeback disabled by design"
        )

    hermes_protocol_summary = _build_hermes_protocol_summary(
        hermes_result=hermes_result,
        writeback_results=[],
    )
    task_signal = _normalized_hermes_task_signal(hermes_result)
    if task_signal:
        security_result["warnings"].append(f"Hermes task_signal={task_signal}")
    clarify_question = str(hermes_result.get("clarify_question") or "").strip()
    route_decision = {
        "interaction_mode": interaction_mode,
        "interactionMode": interaction_mode,
        "reception_mode": reception_mode,
        "receptionMode": reception_mode,
        "hermes_task_signal": task_signal or None,
        "hermesTaskSignal": task_signal or None,
        "hermes_clarify_question": clarify_question or None,
        "hermesClarifyQuestion": clarify_question or None,
    }
    _append_reception_session_event(
        message=message,
        state="replied",
        text=f"Hermes 已生成回复：{_truncate_text(reply_text, 40)}",
        trace_id=str(security_result["trace_id"]),
        type_="success",
        metadata={
            **_active_task_context_event_metadata(message),
            "interaction_mode": interaction_mode,
            "task_signal": task_signal or None,
            "attachment_count": len(registered_attachments),
            "protocol_mode": str(hermes_result.get("protocol_mode") or "").strip() or None,
            "reply_preview": _truncate_text(reply_text, 120),
            **_knowledge_context_event_metadata(message),
        },
    )
    try:
        writeback_result = customer_profile_writeback_service.apply_reception_writeback(
            message=message,
            hermes_result=hermes_result,
            interaction_mode=interaction_mode,
        )
        if writeback_result is not None and writeback_result.updated_fields:
            security_result["warnings"].append(
                "Profile writeback updated: " + ", ".join(writeback_result.updated_fields)
            )
    except Exception as exc:
        logger.warning(
            "Customer profile writeback skipped: profile_id=%s trace_id=%s error=%s",
            _metadata_text(message.metadata if isinstance(message.metadata, dict) else {}, *PROFILE_ID_METADATA_KEYS),
            str(security_result["trace_id"]),
            exc,
        )
        security_result["warnings"].append("Customer profile writeback skipped")

    if interaction_mode == "continuation" and active_task_id:
        _append_context_patch(active_task_id, message, str(security_result["trace_id"]))
        if auth_scope.startswith("webhook:") and reply_text:
            channel_outbound_service.deliver_reception_reply(
                message=message,
                text=reply_text,
                trace_id=str(security_result["trace_id"]),
                channel_delivery_binding=_build_channel_delivery_binding(message),
            )
        LAST_MESSAGE_AT_BY_USER[message.user_key] = received_at
        context_patch_task = _find_task(active_task_id)
        if context_patch_task is not None:
            return task_view_service.build_task_event_response(
                result_message=reply_text,
                entrypoint="master_bot.reception",
                task=context_patch_task,
                unified_message=message.model_dump(),
                run_id=str(context_patch_task.get("workflow_run_id") or context_patch_task.get("workflowRunId") or "").strip() or None,
                intent=str(hermes_result.get("intent") or "").strip() or None,
                trace_id=str(security_result["trace_id"]),
                detected_lang=message.detected_lang,
                memory_hits=memory_matches["total"],
                warnings=list(security_result["warnings"]),
                merged_into_task_id=active_task_id,
                interaction_mode="continuation",
                reception_mode="continuation",
                include_task_route_decision=False,
            )

    if interaction_mode == "task":
        if auth_scope.startswith("webhook:") and reply_text:
            channel_outbound_service.deliver_reception_reply(
                message=message,
                text=reply_text,
                trace_id=str(security_result["trace_id"]),
                channel_delivery_binding=_build_channel_delivery_binding(message),
            )
        LAST_MESSAGE_AT_BY_USER[message.user_key] = received_at
        return _create_task_from_hermes_result(
            message=message,
            hermes_result=hermes_result,
            entrypoint="master_bot.reception",
            entrypoint_agent=entrypoint_agent,
            trace_id=str(security_result["trace_id"]),
            preferred_language=preferred_language,
            memory_matches=memory_matches,
            security_result=security_result,
            message_tenant_id=message_tenant_id,
            message_tenant_name=message_tenant_name,
            security_context=security_context,
        )

    if interaction_mode == "continuation" and not active_task_id:
        security_result["warnings"].append("Hermes requested continuation but no active task was resolved")

    if auth_scope.startswith("webhook:") and reply_text:
        channel_outbound_service.deliver_reception_reply(
            message=message,
            text=reply_text,
            trace_id=str(security_result["trace_id"]),
            channel_delivery_binding=_build_channel_delivery_binding(message),
        )

    LAST_MESSAGE_AT_BY_USER[message.user_key] = received_at
    return task_view_service.build_ingest_response(
        result_message=reply_text,
        entrypoint="master_bot.reception",
        unified_message=message.model_dump(),
        trace_id=str(security_result["trace_id"]),
        detected_lang=message.detected_lang,
        memory_hits=memory_matches["total"],
        warnings=list(security_result["warnings"]),
        intent=str(hermes_result.get("intent") or "").strip() or None,
        interaction_mode=interaction_mode,
        reception_mode=reception_mode,
        route_decision=route_decision,
        hermes_protocol=hermes_protocol_summary,
    )


def ingest_channel_webhook(channel: str, payload: dict, *, request_base_url: str | None = None) -> dict:
    adapter = channel_adapter_registry.get(channel)
    message = adapter.parse(payload)
    if not isinstance(message.metadata, dict):
        message.metadata = {}
    if request_base_url:
        normalized_base = str(request_base_url).strip().rstrip("/")
        if normalized_base:
            message.metadata["request_base_url"] = normalized_base
            message.metadata["requestBaseUrl"] = normalized_base
    return _ingest_webhook_message_once(
        message,
        channel=channel,
        entrypoint="master_bot.dispatch",
        entrypoint_agent=f"{channel_display_name(channel)} Adapter",
    )


def ingest_telegram_webhook(payload: dict, *, request_base_url: str | None = None) -> dict:
    return ingest_channel_webhook("telegram", payload, request_base_url=request_base_url)


def bootstrap_message_ingestion_state() -> dict[str, int]:
    ACTIVE_TASKS_BY_USER.clear()
    LAST_MESSAGE_AT_BY_USER.clear()
    AUTHORITATIVE_TASK_STEP_CACHE.clear()
    restored_users: set[str] = set()

    for task in _load_tasks_for_bootstrap():
        if str(task.get("status") or "") not in {"pending", "running"}:
            continue

        task_id = str(task.get("id") or "").strip()
        user_key = str(task.get("user_key") or "").strip()
        if not task_id or not user_key:
            continue

        latest_message_at = _latest_message_at_for_task(task)
        known_message_at = LAST_MESSAGE_AT_BY_USER.get(user_key)
        if known_message_at is not None and known_message_at >= latest_message_at:
            continue

        ACTIVE_TASKS_BY_USER[user_key] = task_id
        LAST_MESSAGE_AT_BY_USER[user_key] = latest_message_at
        restored_users.add(user_key)

    return {
        "active_tasks": len(ACTIVE_TASKS_BY_USER),
        "restored": len(restored_users),
    }


def reset_message_ingestion_state() -> None:
    ACTIVE_TASKS_BY_USER.clear()
    LAST_MESSAGE_AT_BY_USER.clear()
    AUTHORITATIVE_TASK_STEP_CACHE.clear()
    RECENT_WEBHOOK_RESULT_BY_MESSAGE.clear()
    for event in INFLIGHT_WEBHOOK_MESSAGE_EVENTS.values():
        event.set()
    INFLIGHT_WEBHOOK_MESSAGE_EVENTS.clear()
