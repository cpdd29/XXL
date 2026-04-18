from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.adapters.registry import channel_adapter_registry
from app.brain_core.coordinator.service import brain_coordinator_service
from app.brain_core.orchestration.service import orchestration_service
from app.brain_core.reception.service import reception_service
from app.brain_core.task_view.service import task_view_service
from app.config import get_settings
from app.schemas.messages import UnifiedMessage, channel_display_name, webhook_auth_scope
from app.services.agent_execution_worker_service import agent_execution_worker_service
from app.services.language_service import detect_language
from app.services.memory_service import memory_service
from app.services.operational_log_service import append_realtime_event
from app.services.persistence_service import persistence_service
from app.services.settings_service import get_channel_integration_runtime_settings
from app.services.security_gateway_service import security_gateway_service
from app.services.store import store
from app.services.workflow_execution_service import (
    append_context_patch_to_run,
    complete_agent_execution_job,
    create_agent_dispatch_run_for_task,
    create_workflow_run_for_task,
    fail_workflow_run_due_agent_execution_error,
    mark_task_steps_authoritative,
    sync_workflow_run_from_task,
    tick_workflow_run,
)

ACTIVE_TASKS_BY_USER: dict[str, str] = {}
LAST_MESSAGE_AT_BY_USER: dict[str, datetime] = {}
AUTHORITATIVE_TASK_STEP_CACHE: set[str] = set()
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
INTERACTION_MODES = {"chat", "task", "workflow_or_direct"}
PROFESSIONAL_CONFIRM_TIMEOUT_SECONDS = 1800


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
        return metadata_tenant_id, metadata_tenant_name or f"{metadata_tenant_id} 租户"

    channel_tenant_id, channel_tenant_name = _channel_tenant_binding(
        str(message.channel.value or "").strip().lower()
    )
    if not channel_tenant_id:
        return None, None
    return channel_tenant_id, channel_tenant_name or f"{channel_tenant_id} 租户"


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
    if str(getattr(launch_plan, "mode", "")).strip() == "agent_dispatch":
        run = create_agent_dispatch_run_for_task(
            task=task,
            intent=intent,
            trigger=entrypoint,
            memory_hits=memory_hits,
            warnings=warnings,
            dispatch_context=dispatch_context,
        )
        if bool(getattr(launch_plan, "should_queue_agent_execution", False)):
            execution_agent_id = str(getattr(launch_plan, "execution_agent_id", "") or "").strip() or None
            queued = agent_execution_worker_service.enqueue_execution(
                run_id=str(run.get("id") or ""),
                task_id=str(task.get("id") or ""),
                workflow_id=str(run.get("workflow_id") or ""),
                execution_agent_id=execution_agent_id,
                step_delay=0.0,
                published_at=store.now_string(),
            )
            if not queued:
                try:
                    run = complete_agent_execution_job(
                        str(run.get("id") or ""),
                        execution_agent_id=execution_agent_id,
                    )
                except Exception as exc:
                    run = fail_workflow_run_due_agent_execution_error(
                        str(run.get("id") or ""),
                        failure_message=f"Agent dispatch 执行失败：{exc}",
                    )
        return run

    return create_workflow_run_for_task(
        task=task,
        intent=intent,
        trigger=entrypoint,
        memory_hits=memory_hits,
        warnings=warnings,
        workflow_id=str(getattr(launch_plan, "workflow_id", "") or ""),
        dispatch_context=dispatch_context,
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


def _should_context_patch(user_key: str, received_at: datetime, message_text: str) -> str | None:
    settings = get_settings()
    active_task = _resolve_active_task_for_user(user_key)
    if active_task is None:
        return None
    task_id, last_message_at = active_task

    task = _find_task(task_id)
    if not reception_service.should_context_patch(
        active_task=task,
        last_message_at=last_message_at,
        received_at=received_at,
        message_text=message_text,
        message_debounce_seconds=settings.message_debounce_seconds,
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
    security_result = security_gateway_service.inspect(message, auth_scope=auth_scope)
    message.text = str(security_result["sanitized_text"])
    message.user_key = str(security_result["user_key"])
    message.session_id = _build_session_id(message)
    preferred_language = _resolved_preferred_language(message)
    message.detected_lang = detect_language(
        message.text,
        preferred_language=preferred_language,
    )
    _sync_message_user_profile(message, preferred_language=preferred_language)

    short_term_result = memory_service.ingest_message(
        user_id=message.user_key,
        session_id=message.session_id,
        role="user",
        content=message.text,
        detected_lang=message.detected_lang,
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
    )

    if short_term_result["distill_recommended"]:
        distill_result = memory_service.distill(
            user_id=message.user_key,
            trigger="daily",
            session_id=message.session_id,
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
    context_patch_task_id = _should_context_patch(message.user_key, received_at, message.text)
    if context_patch_task_id:
        _append_context_patch(context_patch_task_id, message, str(security_result["trace_id"]))
        LAST_MESSAGE_AT_BY_USER[message.user_key] = received_at
        context_patch_task = _find_task(context_patch_task_id)
        return task_view_service.build_context_patch_response(
            result_message="Message merged into active task context",
            entrypoint="master_bot.context_patch",
            task=context_patch_task,
            task_id=context_patch_task_id,
            intent=reception_service.infer_message_intent(message.text),
            unified_message=message.model_dump(),
            trace_id=str(security_result["trace_id"]),
            detected_lang=message.detected_lang,
            memory_hits=memory_matches["total"],
            warnings=list(security_result["warnings"]),
            interaction_mode="chat",
            reception_mode="continuation",
        )

    dispatch_plan = brain_coordinator_service.build_dispatch_plan(
        {
            "text": message.text,
            "language": message.detected_lang,
            "channel": message.channel.value,
            "user_id": message.user_key,
            "session_id": message.session_id,
            "metadata": message.metadata,
        }
    )
    intent = dispatch_plan.intent
    workflow = dispatch_plan.workflow
    route_message = dispatch_plan.route_message
    route_decision = dispatch_plan.route_decision
    interaction_mode = dispatch_plan.interaction_mode
    reception_mode = dispatch_plan.reception_mode
    agent_dispatch = dispatch_plan.agent_dispatch
    metadata = orchestration_service.prepare_message_dispatch_metadata(
        route_decision=route_decision,
        manager_packet=dispatch_plan.manager_packet,
        brain_dispatch_summary=dispatch_plan.brain_dispatch_summary,
        interaction_mode=interaction_mode,
        approval_required=_route_decision_bool(route_decision, "approval_required", "approvalRequired"),
        confirmation_status=_route_decision_field(route_decision, "confirmation_status", "confirmationStatus"),
        confirmation_required=_route_decision_bool(route_decision, "confirmation_required", "confirmationRequired"),
        clone=store.clone,
    )
    task_id = _next_task_id()
    memory_items = memory_matches["items"]
    memory_injection_summary = _memory_injection_summary(memory_items)
    execution_agent_name = dispatch_plan.execution_agent_name
    artifacts = orchestration_service.build_message_task_artifacts(
        task_id=task_id,
        message=message,
        entrypoint=entrypoint,
        entrypoint_agent=entrypoint_agent,
        trace_id=str(security_result["trace_id"]),
        preferred_language=preferred_language,
        memory_hits=memory_matches["total"],
        memory_items=memory_items,
        memory_injection_summary=memory_injection_summary,
        metadata=metadata,
        intent=intent,
        route_message=route_message,
        execution_agent_name=execution_agent_name,
        agent_dispatch=agent_dispatch,
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
    )
    route_decision = artifacts.route_decision
    manager_packet = artifacts.manager_packet
    brain_dispatch_summary = artifacts.brain_dispatch_summary
    task = artifacts.task
    dispatch_context = artifacts.dispatch_context
    store.tasks.append(task)
    store.task_steps[task_id] = list(artifacts.task_steps)
    AUTHORITATIVE_TASK_STEP_CACHE.add(task_id)
    mark_task_steps_authoritative(task_id)
    run = _launch_message_run(
        task=task,
        intent=intent,
        entrypoint=entrypoint,
        memory_hits=memory_matches["total"],
        warnings=list(security_result["warnings"]),
        dispatch_context=dispatch_context,
        launch_plan=orchestration_service.build_message_run_launch_plan(
            agent_dispatch=agent_dispatch,
            confirmation_pending=artifacts.confirmation_pending,
            workflow_id=str((workflow or {}).get("id") or ""),
            route_decision=route_decision,
        ),
    )
    ACTIVE_TASKS_BY_USER[message.user_key] = task_id
    LAST_MESSAGE_AT_BY_USER[message.user_key] = received_at
    append_realtime_event(
        agent="Dispatcher Agent",
        message=f"已为 {message.user_key} 创建任务 {task_id}",
        type_="success",
        source="message_ingestion",
        trace_id=str(security_result["trace_id"]),
        task_id=task_id,
        workflow_run_id=str(run.get("id") or "").strip() or None,
        metadata={
            "event": "task_created",
            "user_key": message.user_key,
            "intent": intent,
            "entrypoint": entrypoint,
            "manager_action": str(manager_packet.get("manager_action") or "").strip() or None,
            "session_state": str(manager_packet.get("session_state") or "").strip() or None,
            "response_contract": str(manager_packet.get("response_contract") or "").strip() or None,
        },
    )

    return task_view_service.build_task_event_response(
        result_message="Message accepted and dispatched",
        entrypoint=entrypoint,
        task=task,
        unified_message=message.model_dump(),
        run_id=str(run.get("id") or "").strip() or None,
        intent=intent,
        trace_id=str(security_result["trace_id"]),
        detected_lang=message.detected_lang,
        memory_hits=memory_matches["total"],
        warnings=list(security_result["warnings"]),
        merged_into_task_id=None,
        interaction_mode=interaction_mode,
        reception_mode=reception_mode,
    )


def ingest_channel_webhook(channel: str, payload: dict) -> dict:
    adapter = channel_adapter_registry.get(channel)
    message = adapter.parse(payload)
    return ingest_unified_message(
        message,
        auth_scope=webhook_auth_scope(channel),
        entrypoint="master_bot.dispatch",
        entrypoint_agent=f"{channel_display_name(channel)} Adapter",
    )


def ingest_telegram_webhook(payload: dict) -> dict:
    return ingest_channel_webhook("telegram", payload)


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
