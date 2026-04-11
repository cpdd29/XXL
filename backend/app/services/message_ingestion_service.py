from __future__ import annotations

from datetime import UTC, datetime

from app.adapters.registry import channel_adapter_registry
from app.config import get_settings
from app.schemas.messages import UnifiedMessage, channel_display_name, webhook_auth_scope
from app.services.language_service import detect_language
from app.services.master_bot_service import dispatch_intent, master_bot_service, target_agent_name
from app.services.agent_execution_worker_service import agent_execution_worker_service
from app.services.memory_service import memory_service
from app.services.operational_log_service import append_realtime_event
from app.services.persistence_service import persistence_service
from app.services.security_gateway_service import security_gateway_service
from app.services.store import store
from app.services.workflow_execution_service import (
    append_context_patch_to_run,
    complete_agent_execution_job,
    create_direct_agent_run_for_task,
    create_workflow_run_for_task,
    fail_workflow_run_due_agent_execution_error,
    mark_task_steps_authoritative,
)

ACTIVE_TASKS_BY_USER: dict[str, str] = {}
LAST_MESSAGE_AT_BY_USER: dict[str, datetime] = {}
AUTHORITATIVE_TASK_STEP_CACHE: set[str] = set()
MEMORY_CONTEXT_LIMIT_MIN = 5
MEMORY_CONTEXT_LIMIT_MAX = 10
DISPATCH_CONTEXT_MEMORY_LIMIT_MIN = 5
DISPATCH_CONTEXT_MEMORY_LIMIT_MAX = 10
DISPATCH_CONTEXT_TEXT_PREVIEW_LIMIT = 160
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
ALLOWED_CONTROL_PLANE_ROLES = {"admin", "operator", "viewer"}
CONTEXT_PATCH_CONTINUATION_MARKERS = (
    "补充一下",
    "补充",
    "等等",
    "等下",
    "稍等",
    "继续",
    "接着",
    "续上",
    "刚才",
    "前面",
    "上面",
    "在这个基础上",
    "基于上面",
    "顺着这个",
    "along that",
    "based on that",
    "follow up",
    "add context",
)
CONTEXT_PATCH_EDIT_MARKERS = (
    "更正式",
    "更口语",
    "更简洁",
    "更详细",
    "更具体",
    "改成",
    "改为",
    "强调",
    "突出",
    "补上",
    "加上",
    "增加",
    "去掉",
    "删掉",
    "压缩",
    "缩短",
    "展开",
    "细化",
    "中文输出",
    "英文输出",
)
CONTEXT_PATCH_NEW_TASK_MARKERS = (
    "新任务",
    "另一个任务",
    "另外一个任务",
    "换个任务",
    "换一个任务",
    "重新开一个",
    "重新来一个",
    "new task",
    "another task",
    "separate task",
)
CONTEXT_PATCH_NEW_REQUEST_MARKERS = (
    "请帮我",
    "帮我",
    "帮忙",
    "请搜索",
    "请查",
    "请写",
    "写一封",
    "写一份",
    "写个",
    "搜索",
    "检索",
    "查一下",
    "查找",
    "找一下",
    "生成",
    "总结",
    "整理",
    "翻译",
    "search ",
    "find ",
    "lookup",
    "write ",
    "draft",
    "summarize",
    "translate",
    "help me",
)
CONTEXT_PATCH_MAX_FOLLOW_UP_LENGTH = 80
INTERACTION_MODES = {"chat", "task", "workflow_or_direct"}
PROFESSIONAL_CONFIRM_TIMEOUT_SECONDS = 1800
PROFESSIONAL_CONFIRM_MARKERS = ("确认", "开始", "同意", "继续", "执行", "ok", "yes", "confirm", "proceed")
PROFESSIONAL_CANCEL_MARKERS = ("取消", "不用了", "停止", "驳回", "不执行", "cancel", "stop", "reject", "no")


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


def _find_runtime_profile_by_platform_account(*, platform: str, account_id: str) -> dict | None:
    for profile in store.user_profiles.values():
        if _profile_matches_platform_account(
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
) -> tuple[dict | None, bool]:
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

    return _find_runtime_profile_by_platform_account(platform=platform, account_id=account_id), False


def _find_profile_by_platform_account(*, platform: str, account_id: str) -> dict | None:
    profile, _ = _find_profile_by_platform_account_with_source(
        platform=platform,
        account_id=account_id,
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
    existing_profile = None
    profile_from_database = False
    if explicit_profile_id:
        existing_profile, profile_from_database = _load_user_profile_with_source(explicit_profile_id)
    if existing_profile is None:
        existing_profile, profile_from_database = _find_profile_by_platform_account_with_source(
            platform=normalized_channel,
            account_id=platform_user_id,
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
    limit = _dynamic_memory_window(
        memory_items=memory_items,
        min_limit=MEMORY_CONTEXT_LIMIT_MIN,
        max_limit=MEMORY_CONTEXT_LIMIT_MAX,
    )
    return [
        f"记忆注入: {str(item.get('memory_text') or '').strip()}"
        for item in memory_items[:limit]
        if str(item.get("memory_text") or "").strip()
    ]


def _memory_step_message(memory_items: list[dict]) -> str:
    if not memory_items:
        return "未命中长期记忆，按当前请求直接执行"

    previews = [
        _truncate_text(str(item.get("memory_text") or ""), 28)
        for item in memory_items[:2]
        if str(item.get("memory_text") or "").strip()
    ]
    if previews:
        return f"已命中 {len(memory_items)} 条长期记忆：{'；'.join(previews)}"
    return f"已命中 {len(memory_items)} 条长期记忆"


def _dispatch_context_memory_items(memory_items: list[dict]) -> list[dict]:
    limit = _dynamic_memory_window(
        memory_items=memory_items,
        min_limit=DISPATCH_CONTEXT_MEMORY_LIMIT_MIN,
        max_limit=DISPATCH_CONTEXT_MEMORY_LIMIT_MAX,
    )
    items: list[dict] = []
    for item in memory_items[:limit]:
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


def _build_message_dispatch_context(
    *,
    message: UnifiedMessage,
    entrypoint: str,
    entrypoint_agent: str,
    trace_id: str,
    preferred_language: str | None,
    memory_hits: int,
    memory_items: list[dict],
    route_decision: dict,
    interaction_mode: str,
) -> dict:
    reception_mode = str(
        route_decision.get("reception_mode") or route_decision.get("receptionMode") or ""
    ).strip() or None
    dispatch_context = {
        "type": "message_dispatch",
        "state": "queued",
        "queued_at": store.now_string(),
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
        "message_preview": _truncate_text(message.text, DISPATCH_CONTEXT_TEXT_PREVIEW_LIMIT),
        "memory_hits": memory_hits,
        "memory_items": _dispatch_context_memory_items(memory_items),
        "interaction_mode": interaction_mode,
        "interactionMode": interaction_mode,
        "reception_mode": reception_mode,
        "receptionMode": reception_mode,
        "route_decision": store.clone(route_decision),
    }
    channel_delivery = _build_channel_delivery_binding(message)
    if channel_delivery is not None:
        dispatch_context["channel_delivery"] = channel_delivery
    return dispatch_context


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


def _normalize_message_text(text: str | None) -> str:
    return " ".join(str(text or "").strip().lower().split())


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


def _route_decision_payload(route_decision: dict | None, *keys: str):
    if not isinstance(route_decision, dict):
        return None
    for key in keys:
        if key in route_decision:
            return route_decision.get(key)
    return None


def _is_professional_confirmation_pending(task: dict) -> bool:
    route_decision = task.get("route_decision") or task.get("routeDecision")
    workflow_mode = _route_decision_field(route_decision, "workflow_mode", "workflowMode")
    confirmation_required = _route_decision_bool(route_decision, "confirmation_required", "confirmationRequired")
    confirmation_status = _route_decision_field(route_decision, "confirmation_status", "confirmationStatus")
    return (
        str(workflow_mode or "").strip().lower() == "professional_workflow"
        and confirmation_required
        and str(confirmation_status or "").strip().lower() == "pending"
        and str(task.get("status") or "").strip().lower() == "pending"
    )


def _confirmation_action(message_text: str) -> str | None:
    normalized = _normalize_message_text(message_text)
    if not normalized:
        return None
    if any(marker in normalized for marker in PROFESSIONAL_CONFIRM_MARKERS):
        return "confirm"
    if any(marker in normalized for marker in PROFESSIONAL_CANCEL_MARKERS):
        return "cancel"
    return None


def _task_route_intent(task: dict | None) -> str | None:
    if not isinstance(task, dict):
        return None

    route_decision = task.get("route_decision") or task.get("routeDecision")
    if isinstance(route_decision, dict):
        intent = str(route_decision.get("intent") or "").strip().lower()
        if intent in {"search", "write", "help"}:
            return intent

    inferred_intent = dispatch_intent(
        "\n".join(
            part
            for part in (
                str(task.get("title") or "").strip(),
                str(task.get("description") or "").strip(),
            )
            if part
        )
    )
    if inferred_intent in {"search", "write", "help"}:
        return inferred_intent
    return None


def _message_has_marker(message_text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in message_text for marker in markers)


def _looks_like_follow_up_instruction(message_text: str) -> bool:
    if len(message_text) > CONTEXT_PATCH_MAX_FOLLOW_UP_LENGTH:
        return False
    return _message_has_marker(message_text, CONTEXT_PATCH_EDIT_MARKERS)


def _looks_like_new_request(message_text: str) -> bool:
    return _message_has_marker(message_text, CONTEXT_PATCH_NEW_REQUEST_MARKERS)


def _should_merge_into_active_task(task: dict, message_text: str) -> bool:
    normalized_message = _normalize_message_text(message_text)
    if not normalized_message:
        return False

    if _message_has_marker(normalized_message, CONTEXT_PATCH_NEW_TASK_MARKERS):
        return False

    if _message_has_marker(normalized_message, CONTEXT_PATCH_CONTINUATION_MARKERS):
        return True

    if _looks_like_follow_up_instruction(normalized_message):
        return True

    active_intent = _task_route_intent(task)
    incoming_intent = dispatch_intent(normalized_message)
    if active_intent and incoming_intent != active_intent and _looks_like_new_request(normalized_message):
        return False

    if _looks_like_new_request(normalized_message):
        return False

    return False


def _should_context_patch(user_key: str, received_at: datetime, message_text: str) -> str | None:
    settings = get_settings()
    active_task = _resolve_active_task_for_user(user_key)
    if active_task is None:
        return None
    task_id, last_message_at = active_task

    task = _find_task(task_id)
    if task is None or task["status"] not in {"pending", "running"}:
        return None

    if (received_at - last_message_at).total_seconds() > settings.message_debounce_seconds:
        return None

    if not _should_merge_into_active_task(task, message_text):
        return None
    return task_id


def _resolve_active_task_for_user(user_key: str) -> tuple[str, datetime] | None:
    normalized_user_key = str(user_key or "").strip()
    if not normalized_user_key:
        return None

    task_id = ACTIVE_TASKS_BY_USER.get(normalized_user_key)
    last_message_at = LAST_MESSAGE_AT_BY_USER.get(normalized_user_key)
    if task_id and last_message_at:
        task = _find_task(task_id)
        if task is not None and task["status"] in {"pending", "running"}:
            latest_message_at = _latest_message_at_for_task(task)
            if latest_message_at > last_message_at:
                last_message_at = latest_message_at
                LAST_MESSAGE_AT_BY_USER[normalized_user_key] = latest_message_at
            ACTIVE_TASKS_BY_USER[normalized_user_key] = task_id
            return task_id, last_message_at

    ACTIVE_TASKS_BY_USER.pop(normalized_user_key, None)
    LAST_MESSAGE_AT_BY_USER.pop(normalized_user_key, None)

    find_latest_active_task = getattr(persistence_service, "find_latest_active_task_for_user", None)
    if not callable(find_latest_active_task):
        return None

    latest_task = find_latest_active_task(normalized_user_key)
    if latest_task is None:
        return None

    latest_task_id = str(latest_task.get("id") or "").strip()
    if not latest_task_id:
        return None

    task = _find_task(latest_task_id)
    if task is None or task["status"] not in {"pending", "running"}:
        return None

    latest_message_at = _latest_message_at_for_task(task)
    ACTIVE_TASKS_BY_USER[normalized_user_key] = latest_task_id
    LAST_MESSAGE_AT_BY_USER[normalized_user_key] = latest_message_at
    return latest_task_id, latest_message_at


def _append_context_patch(task_id: str, message: UnifiedMessage, trace_id: str) -> None:
    task = _find_task(task_id)
    if task is None:
        return

    _refresh_task_steps_from_database(task_id)
    task["description"] = f"{task['description']}\n补充上下文: {message.text}"
    task["updated_at"] = store.now_string()
    task["tokens"] = task.get("tokens", 0) + max(12, len(message.text) // 2)

    steps = _ensure_task_steps_loaded(task_id)
    steps.append(
        {
            "id": f"{task_id}-ctx-{len(steps) + 1}",
            "title": "上下文追加",
            "status": "completed",
            "agent": "Dispatcher Agent",
            "started_at": store.now_string(),
            "finished_at": store.now_string(),
            "message": f"收到用户补充消息，已注入当前任务上下文 (trace={trace_id})",
            "tokens": 0,
        }
    )
    if task.get("workflow_run_id"):
        append_context_patch_to_run(task["workflow_run_id"], message.text, trace_id)
    else:
        _persist_execution_state(task=task, steps=steps)
    append_realtime_event(
        agent="Dispatcher Agent",
        message=f"任务 {task_id} 已吸收追加上下文",
        type_="info",
        source="message_ingestion",
        trace_id=trace_id,
        task_id=task_id,
        workflow_run_id=str(task.get("workflow_run_id") or "").strip() or None,
        metadata={"event": "context_patch_absorbed", "user_key": message.user_key},
    )


def _create_task_steps(
    *,
    task_id: str,
    entrypoint_agent: str,
    memory_items: list[dict],
    trace_id: str,
    warnings: list[str],
    route_message: str,
    execution_agent_name: str,
    direct_agent_dispatch: bool = False,
) -> list[dict]:
    warning_suffix = f"，附带处理: {', '.join(warnings)}" if warnings else ""
    final_step_title = "执行节点" if direct_agent_dispatch else "等待调度"
    final_step_agent = execution_agent_name if direct_agent_dispatch else "Workflow Dispatcher"
    final_step_message = (
        f"已直达 {execution_agent_name}，等待 Agent Worker 执行"
        if direct_agent_dispatch
        else f"已生成 dispatch context，等待派发到 {execution_agent_name}"
    )
    return [
        {
            "id": f"{task_id}-1",
            "title": "接入层标准化",
            "status": "completed",
            "agent": entrypoint_agent,
            "started_at": store.now_string(),
            "finished_at": store.now_string(),
            "message": f"渠道负载已标准化为 UnifiedMessage (trace={trace_id})",
            "tokens": 0,
        },
        {
            "id": f"{task_id}-2",
            "title": "安全网关",
            "status": "completed",
            "agent": "安全网关",
            "started_at": store.now_string(),
            "finished_at": store.now_string(),
            "message": f"消息已通过五层安全检查{warning_suffix}",
            "tokens": 0,
        },
        {
            "id": f"{task_id}-3",
            "title": "长期记忆检索",
            "status": "completed",
            "agent": "Memory Service",
            "started_at": store.now_string(),
            "finished_at": store.now_string(),
            "message": _memory_step_message(memory_items),
            "tokens": 0,
        },
        {
            "id": f"{task_id}-4",
            "title": "Master Bot 路由",
            "status": "completed",
            "agent": "Dispatcher Agent",
            "started_at": store.now_string(),
            "finished_at": store.now_string(),
            "message": route_message,
            "tokens": 0,
        },
        {
            "id": f"{task_id}-5",
            "title": final_step_title,
            "status": "running",
            "agent": final_step_agent,
            "started_at": store.now_string(),
            "finished_at": None,
            "message": final_step_message,
            "tokens": 0,
        },
    ]


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
    context_patch_task_id = _should_context_patch(message.user_key, received_at, message.text)
    if context_patch_task_id:
        _append_context_patch(context_patch_task_id, message, str(security_result["trace_id"]))
        LAST_MESSAGE_AT_BY_USER[message.user_key] = received_at
        return {
            "ok": True,
            "message": "Message merged into active task context",
            "entrypoint": "master_bot.context_patch",
            "task_id": context_patch_task_id,
            "intent": dispatch_intent(message.text),
            "unified_message": message.model_dump(),
            "trace_id": security_result["trace_id"],
            "detected_lang": message.detected_lang,
            "memory_hits": memory_matches["total"],
            "warnings": security_result["warnings"],
            "merged_into_task_id": context_patch_task_id,
            "interaction_mode": "chat",
            "reception_mode": "continuation",
            "route_decision": None,
        }

    route_result = master_bot_service.route_message(
        text=message.text,
        channel=message.channel.value,
        detected_lang=message.detected_lang,
    )
    intent = str(route_result["intent"])
    workflow = route_result["workflow"]
    route_message = str(route_result["route_message"])
    route_decision = route_result["route_decision"]
    interaction_mode = _resolve_interaction_mode(route_decision)
    route_decision["interaction_mode"] = interaction_mode
    route_decision["interactionMode"] = interaction_mode
    reception_mode = str(
        route_decision.get("reception_mode") or route_decision.get("receptionMode") or ""
    ).strip() or None
    direct_agent_dispatch = workflow is None
    task_id = _next_task_id()
    memory_items = memory_matches["items"]
    execution_agent_name = str(
        route_decision.get("execution_agent")
        or route_decision.get("executionAgent")
        or target_agent_name(intent)
    ).strip() or target_agent_name(intent)
    dispatch_context = _build_message_dispatch_context(
        message=message,
        entrypoint=entrypoint,
        entrypoint_agent=entrypoint_agent,
        trace_id=str(security_result["trace_id"]),
        preferred_language=preferred_language,
        memory_hits=memory_matches["total"],
        memory_items=memory_items,
        route_decision=route_decision,
        interaction_mode=interaction_mode,
    )
    task_description_lines = [message.text, *_memory_context_lines(memory_items)]

    task = {
        "id": task_id,
        "title": f"渠道消息任务 - {intent}",
        "description": "\n".join(task_description_lines),
        "status": "running",
        "priority": "medium",
        "created_at": store.now_string(),
        "completed_at": None,
        "agent": target_agent_name(intent),
        "tokens": 0,
        "duration": None,
        "channel": message.channel.value,
        "user_key": message.user_key,
        "session_id": message.session_id,
        "trace_id": security_result["trace_id"],
        "preferred_language": preferred_language,
        "detected_lang": message.detected_lang,
        "confirmation_status": _route_decision_field(route_decision, "confirmation_status", "confirmationStatus"),
        "approval_status": _route_decision_field(route_decision, "approval_status", "approvalStatus"),
        "approval_required": _route_decision_bool(route_decision, "approval_required", "approvalRequired"),
        "audit_id": _route_decision_field(route_decision, "audit_id", "auditId"),
        "idempotency_key": _route_decision_field(route_decision, "idempotency_key", "idempotencyKey"),
        "execution_scope": _route_decision_field(route_decision, "execution_scope", "executionScope"),
        "schedule_plan": _route_decision_payload(route_decision, "schedule_plan", "schedulePlan"),
        "route_decision": route_decision,
        "result": None,
    }
    store.tasks.append(task)
    store.task_steps[task_id] = _create_task_steps(
        task_id=task_id,
        entrypoint_agent=entrypoint_agent,
        memory_items=memory_items,
        trace_id=str(security_result["trace_id"]),
        warnings=list(security_result["warnings"]),
        route_message=route_message,
        execution_agent_name=execution_agent_name,
        direct_agent_dispatch=direct_agent_dispatch,
    )
    AUTHORITATIVE_TASK_STEP_CACHE.add(task_id)
    mark_task_steps_authoritative(task_id)
    if direct_agent_dispatch:
        run = create_direct_agent_run_for_task(
            task=task,
            intent=intent,
            trigger=entrypoint,
            memory_hits=memory_matches["total"],
            warnings=list(security_result["warnings"]),
            dispatch_context=dispatch_context,
        )
        queued = agent_execution_worker_service.enqueue_execution(
            run_id=str(run.get("id") or ""),
            task_id=task_id,
            workflow_id=str(run.get("workflow_id") or ""),
            execution_agent_id=route_decision.get("execution_agent_id")
            or route_decision.get("executionAgentId"),
            step_delay=0.0,
            published_at=store.now_string(),
        )
        if not queued:
            try:
                run = complete_agent_execution_job(
                    str(run.get("id") or ""),
                    execution_agent_id=route_decision.get("execution_agent_id")
                    or route_decision.get("executionAgentId"),
                )
            except Exception as exc:
                run = fail_workflow_run_due_agent_execution_error(
                    str(run.get("id") or ""),
                    failure_message=f"Direct Agent fallback 执行失败：{exc}",
                )
    else:
        run = create_workflow_run_for_task(
            task=task,
            intent=intent,
            trigger=entrypoint,
            memory_hits=memory_matches["total"],
            warnings=list(security_result["warnings"]),
            workflow_id=str(workflow["id"]),
            dispatch_context=dispatch_context,
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
        },
    )

    return {
        "ok": True,
        "message": "Message accepted and dispatched",
        "entrypoint": entrypoint,
        "task_id": task_id,
        "intent": intent,
        "unified_message": message.model_dump(),
        "trace_id": security_result["trace_id"],
        "detected_lang": message.detected_lang,
        "memory_hits": memory_matches["total"],
        "warnings": security_result["warnings"],
        "merged_into_task_id": None,
        "interaction_mode": interaction_mode,
        "reception_mode": reception_mode,
        "run_id": run["id"],
        "route_decision": route_decision,
    }


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
