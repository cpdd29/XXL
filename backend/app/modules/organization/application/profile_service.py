from __future__ import annotations

import csv
from collections import Counter
from copy import deepcopy
from datetime import UTC, datetime
from io import StringIO
import re

from fastapi import HTTPException, status

from app.modules.organization.application.memory_service import memory_service
from app.platform.persistence.persistence_service import persistence_service
from app.platform.persistence.runtime_store import store
from app.modules.organization.application.tenancy_service import current_user_scope, default_scope


ALLOWED_PROFILE_LANGUAGES = {"zh", "en"}
ROOT_PROFILE_SCOPE_ROLES = {"super_admin"}
TENANT_MANAGEMENT_ROLES = {"admin", "super_admin", "operator"}
DEFAULT_TENANT_NAME = "默认租户"
UNASSIGNED_TENANT_NAME = "未绑定租户"
DEFAULT_TENANT_STATUS = "active"
TENANT_DIRECTORY_SETTING_KEY = "profile_tenants"
PROFILE_EXPORT_HEADERS = {
    "tenant_id": "租户ID",
    "tenant_name": "租户名称",
    "id": "画像ID",
    "name": "人员名称",
    "source_channels": "来源渠道",
    "platform_accounts": "平台账号",
    "tags": "标签",
    "preferred_language": "语言偏好",
    "last_active_at": "最近活跃",
    "total_interactions": "累计交互次数",
    "notes": "备注",
}


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _normalize_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    seen: set[str] = set()
    for raw in value:
        normalized = _normalize_text(raw)
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        items.append(normalized)
    return items


def _normalize_tags(value: object) -> list[str]:
    return _normalize_string_list(value)


def _normalize_source_channels(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    channels: list[str] = []
    seen: set[str] = set()
    for raw in value:
        normalized = _normalize_text(raw).lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        channels.append(normalized)
    return channels


def _normalize_platform_accounts(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    accounts: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw in value:
        if not isinstance(raw, dict):
            continue
        platform = _normalize_text(raw.get("platform")).lower()
        account_id = _normalize_text(raw.get("account_id") or raw.get("accountId"))
        if not platform or not account_id:
            continue
        key = (platform, account_id)
        if key in seen:
            continue
        seen.add(key)
        accounts.append({"platform": platform, "account_id": account_id})
    return accounts


def _normalize_preferred_language(value: object) -> str:
    normalized = _normalize_text(value).lower()
    if normalized in ALLOWED_PROFILE_LANGUAGES:
        return normalized
    prefix = normalized.split("-", 1)[0]
    if prefix in ALLOWED_PROFILE_LANGUAGES:
        return prefix
    return "zh"


def _normalize_tenant_id(value: object) -> str:
    return _normalize_text(value)


def _normalize_tenant_name(value: object, *, tenant_id: str) -> str:
    normalized = _normalize_text(value)
    if normalized:
        return normalized
    if not tenant_id:
        return UNASSIGNED_TENANT_NAME
    if tenant_id == default_scope()["tenant_id"]:
        return DEFAULT_TENANT_NAME
    return f"{tenant_id} 租户"


def _normalize_tenant_status(value: object) -> str:
    normalized = _normalize_text(value).lower()
    return normalized or DEFAULT_TENANT_STATUS


def _normalize_timestamp(*values: object) -> str:
    for value in values:
        normalized = _normalize_text(value)
        if normalized:
            return normalized
    return ""


def _normalize_interaction_count(value: object) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _normalize_confidence(value: object) -> float:
    try:
        normalized = float(value or 0.0)
    except (TypeError, ValueError):
        normalized = 0.0
    if normalized < 0:
        return 0.0
    if normalized > 1:
        return 1.0
    return round(normalized, 4)


def _interaction_summary(profile: dict[str, object]) -> str:
    total = _normalize_interaction_count(profile.get("total_interactions"))
    last_active = _normalize_text(profile.get("last_active_at") or profile.get("last_login"))
    if total <= 0 and not last_active:
        return "尚未记录有效交互。"
    if total <= 0:
        return f"最近活跃于 {last_active}。"
    if not last_active:
        return f"累计交互 {total} 次。"
    return f"最近活跃于 {last_active}，累计交互 {total} 次。"


def _normalize_profile(profile: dict[str, object]) -> dict[str, object]:
    profile_id = _normalize_text(
        profile.get("id") or profile.get("profile_id") or profile.get("profileId") or profile.get("user_id")
    )
    if not profile_id:
        raise KeyError("Profile requires id or user_id")

    tenant_id = _normalize_tenant_id(profile.get("tenant_id") or profile.get("tenantId"))
    return {
        **deepcopy(profile),
        "id": profile_id,
        "tenant_id": tenant_id,
        "tenant_name": _normalize_tenant_name(
            profile.get("tenant_name") or profile.get("tenantName"),
            tenant_id=tenant_id,
        ),
        "tenant_status": _normalize_tenant_status(profile.get("tenant_status") or profile.get("tenantStatus")),
        "name": _normalize_text(profile.get("name")) or profile_id,
        "source_channels": _normalize_source_channels(
            profile.get("source_channels") or profile.get("sourceChannels")
        ),
        "platform_accounts": _normalize_platform_accounts(
            profile.get("platform_accounts") or profile.get("platformAccounts")
        ),
        "tags": _normalize_tags(profile.get("tags")),
        "preferred_language": _normalize_preferred_language(
            profile.get("preferred_language") or profile.get("preferredLanguage")
        ),
        "notes": _normalize_text(profile.get("notes")) or "暂无额外备注。",
        "last_active_at": _normalize_timestamp(
            profile.get("last_active_at"),
            profile.get("lastActiveAt"),
            profile.get("last_login"),
            profile.get("updated_at"),
            profile.get("created_at"),
        ),
        "total_interactions": _normalize_interaction_count(profile.get("total_interactions")),
        "created_at": _normalize_timestamp(profile.get("created_at")),
        "identity_mapping_status": _normalize_text(
            profile.get("identity_mapping_status") or profile.get("identityMappingStatus")
        )
        or ("auto_mapped" if _normalize_platform_accounts(profile.get("platform_accounts") or profile.get("platformAccounts")) else "unmapped"),
        "identity_mapping_source": _normalize_text(
            profile.get("identity_mapping_source") or profile.get("identityMappingSource")
        )
        or "unknown",
        "identity_mapping_confidence": _normalize_confidence(
            profile.get("identity_mapping_confidence") or profile.get("identityMappingConfidence")
        ),
        "last_identity_sync_at": _normalize_timestamp(
            profile.get("last_identity_sync_at"),
            profile.get("lastIdentitySyncAt"),
            profile.get("updated_at"),
        )
        or None,
        "interaction_summary": _interaction_summary(profile),
    }


def _load_runtime_profiles() -> list[dict[str, object]]:
    return [
        _normalize_profile(profile)
        for profile in store.user_profiles.values()
        if isinstance(profile, dict)
        and not bool(profile.get("exclude_from_profiles") or profile.get("excludeFromProfiles"))
    ]


def _load_profiles() -> list[dict[str, object]]:
    database_profiles = getattr(persistence_service, "list_user_profiles", lambda: None)()
    if database_profiles is not None:
        normalized_items = [
            _normalize_profile(profile)
            for profile in database_profiles
            if isinstance(profile, dict)
            and not bool(profile.get("exclude_from_profiles") or profile.get("excludeFromProfiles"))
        ]
        for item in normalized_items:
            store.user_profiles[str(item["id"])] = deepcopy(item)
        return normalized_items
    if getattr(persistence_service, "enabled", False):
        return []
    return _load_runtime_profiles()


def _load_profile(profile_id: str) -> dict[str, object] | None:
    database_profile = persistence_service.get_user_profile(profile_id)
    if isinstance(database_profile, dict):
        if bool(database_profile.get("exclude_from_profiles") or database_profile.get("excludeFromProfiles")):
            return None
        normalized = _normalize_profile(database_profile)
        store.user_profiles[profile_id] = deepcopy(normalized)
        return normalized
    if getattr(persistence_service, "enabled", False):
        return None
    runtime_profile = store.user_profiles.get(profile_id)
    if isinstance(runtime_profile, dict):
        if bool(runtime_profile.get("exclude_from_profiles") or runtime_profile.get("excludeFromProfiles")):
            return None
        return _normalize_profile(runtime_profile)
    return None


def _sync_profile(profile: dict[str, object]) -> dict[str, object]:
    normalized = _normalize_profile(profile)
    store.user_profiles[str(normalized["id"])] = deepcopy(normalized)
    return store.user_profiles[str(normalized["id"])]


def _can_view_all_tenants(current_user: dict[str, object]) -> bool:
    role = _normalize_text(current_user.get("role")).lower()
    if role in ROOT_PROFILE_SCOPE_ROLES:
        return True
    actor_profile = _load_profile(_normalize_text(current_user.get("id")))
    if role == "admin" and actor_profile is None:
        return True
    return any(
        bool(source.get(key))
        for source in (current_user, actor_profile or {})
        for key in ("platform_admin", "platformAdmin", "is_platform_admin", "isPlatformAdmin")
    )


def _can_manage_tenant_directory(current_user: dict[str, object]) -> bool:
    role = _normalize_text(current_user.get("role")).lower()
    return role in TENANT_MANAGEMENT_ROLES or _can_view_all_tenants(current_user)


def _resolve_requested_tenant(
    current_user: dict[str, object],
    *,
    tenant_id: str | None = None,
    management_view: bool = False,
) -> str | None:
    normalized_requested_tenant = _normalize_text(tenant_id).lower()
    user_scope = current_user_scope(current_user)
    current_tenant_id = _normalize_text(user_scope.get("tenant_id")) or default_scope()["tenant_id"]

    if management_view and _can_manage_tenant_directory(current_user):
        if not normalized_requested_tenant or normalized_requested_tenant == "all":
            return None
        return normalized_requested_tenant

    if _can_view_all_tenants(current_user):
        if not normalized_requested_tenant or normalized_requested_tenant == "all":
            return None
        return normalized_requested_tenant

    if normalized_requested_tenant and normalized_requested_tenant not in {"all", current_tenant_id.lower()}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-tenant access denied for profile scope",
        )
    return current_tenant_id


def _filter_profiles_for_scope(
    profiles: list[dict[str, object]],
    current_user: dict[str, object],
    *,
    tenant_id: str | None = None,
    management_view: bool = False,
) -> tuple[list[dict[str, object]], str | None]:
    resolved_tenant = _resolve_requested_tenant(
        current_user,
        tenant_id=tenant_id,
        management_view=management_view,
    )
    if resolved_tenant is None:
        return profiles, None
    return [
        profile
        for profile in profiles
        if _normalize_text(profile.get("tenant_id")).lower() == resolved_tenant.lower()
    ], resolved_tenant


def _profile_matches_search(profile: dict[str, object], search: str) -> bool:
    keyword = _normalize_text(search).lower()
    if not keyword:
        return True

    haystacks = [
        _normalize_text(profile.get("id")).lower(),
        _normalize_text(profile.get("name")).lower(),
        _normalize_text(profile.get("tenant_name")).lower(),
        _normalize_text(profile.get("notes")).lower(),
    ]
    haystacks.extend(channel.lower() for channel in _normalize_source_channels(profile.get("source_channels")))
    haystacks.extend(tag.lower() for tag in _normalize_tags(profile.get("tags")))
    haystacks.extend(
        f"{account['platform']}:{account['account_id']}".lower()
        for account in _normalize_platform_accounts(profile.get("platform_accounts"))
    )
    haystacks.extend(
        account["account_id"].lower()
        for account in _normalize_platform_accounts(profile.get("platform_accounts"))
    )
    return any(keyword in haystack for haystack in haystacks if haystack)


def _sort_profiles(items: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        items,
        key=lambda item: (
            _normalize_text(item.get("tenant_name")).lower(),
            -_sort_timestamp_key(item.get("last_active_at"))[0],
            -_sort_timestamp_key(item.get("last_active_at"))[1],
            -_normalize_interaction_count(item.get("total_interactions")),
            _normalize_text(item.get("name")).lower(),
        ),
    )


def _load_audit_logs() -> list[dict[str, object]]:
    database_logs = persistence_service.list_audit_logs()
    if database_logs is not None:
        return [deepcopy(item) for item in database_logs]
    if getattr(persistence_service, "enabled", False):
        return []
    return deepcopy(store.audit_logs)


def _load_recent_conversation_messages(profile_id: str, *, limit: int = 6) -> list[dict[str, object]]:
    database_messages = persistence_service.list_conversation_messages(user_id=profile_id, limit=limit)
    return [deepcopy(item) for item in (database_messages or [])]


def _profile_activity_candidates(profile: dict[str, object]) -> set[str]:
    email = _normalize_text(profile.get("email")).lower()
    name = _normalize_text(profile.get("name")).lower()
    platform_accounts = _normalize_platform_accounts(profile.get("platform_accounts"))
    candidates = {
        _normalize_text(profile.get("id")).lower(),
        email,
        name,
        *{account["account_id"].lower() for account in platform_accounts},
    }
    return {item for item in candidates if item}


def _matches_profile_audit_log(log: dict[str, object], profile: dict[str, object]) -> bool:
    candidates = _profile_activity_candidates(profile)
    log_user = _normalize_text(log.get("user")).lower()
    log_details = _normalize_text(log.get("details")).lower()
    return any(candidate in log_user or candidate in log_details for candidate in candidates)


def _activity_type_from_status(status_text: str) -> str:
    normalized = status_text.lower()
    if normalized in {"error", "failed", "danger"}:
        return "warning"
    if normalized in {"warning", "warn"}:
        return "warning"
    if normalized in {"success", "ok"}:
        return "success"
    return "info"


def _build_profile_activity_items(profile: dict[str, object]) -> list[dict[str, object]]:
    profile_id = _normalize_text(profile.get("id"))
    items: list[dict[str, object]] = [
        {
            "id": f"{profile_id}-created",
            "timestamp": _normalize_text(profile.get("created_at")),
            "type": "success",
            "title": "画像创建",
            "description": "画像已被纳入租户画像库，可用于后续记忆与任务关联。",
            "source": "profile",
        },
        {
            "id": f"{profile_id}-tenant",
            "timestamp": _normalize_text(profile.get("last_active_at") or profile.get("created_at")),
            "type": "info",
            "title": "租户归属确认",
            "description": f"当前归属租户：{_normalize_text(profile.get('tenant_name'))}。",
            "source": "tenancy",
        },
        {
            "id": f"{profile_id}-language",
            "timestamp": _normalize_text(profile.get("last_active_at") or profile.get("created_at")),
            "type": "info",
            "title": "语言偏好",
            "description": f"当前语言偏好：{_normalize_text(profile.get('preferred_language')).upper()}。",
            "source": "profile",
        },
        {
            "id": f"{profile_id}-interactions",
            "timestamp": _normalize_text(profile.get("last_active_at") or profile.get("created_at")),
            "type": "success",
            "title": "交互统计",
            "description": f"累计交互 {_normalize_interaction_count(profile.get('total_interactions'))} 次。",
            "source": "analytics",
        },
    ]

    for index, channel in enumerate(_normalize_source_channels(profile.get("source_channels"))):
        items.append(
            {
                "id": f"{profile_id}-channel-{index}",
                "timestamp": _normalize_text(profile.get("last_active_at") or profile.get("created_at")),
                "type": "success",
                "title": "来源渠道",
                "description": f"画像已记录来源渠道 {channel}。",
                "source": "integration",
            }
        )

    for index, account in enumerate(_normalize_platform_accounts(profile.get("platform_accounts"))):
        items.append(
            {
                "id": f"{profile_id}-account-{index}",
                "timestamp": _normalize_text(profile.get("last_identity_sync_at") or profile.get("last_active_at") or profile.get("created_at")),
                "type": "info",
                "title": "平台账号绑定",
                "description": f"已绑定 {account['platform']} 账号 {account['account_id']}。",
                "source": "identity",
            }
        )

    return items


def _build_audit_activity_items(profile: dict[str, object]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for log in _load_audit_logs():
        if not _matches_profile_audit_log(log, profile):
            continue
        items.append(
            {
                "id": f"audit-{_normalize_text(log.get('id'))}",
                "timestamp": _normalize_text(log.get("timestamp")),
                "type": _activity_type_from_status(_normalize_text(log.get("status"))),
                "title": _normalize_text(log.get("action")) or "审计事件",
                "description": _normalize_text(log.get("details")) or "记录了一条画像相关审计事件。",
                "source": "audit",
            }
        )
    return items


def _build_message_activity_items(profile: dict[str, object]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for message in _load_recent_conversation_messages(_normalize_text(profile.get("id"))):
        role = _normalize_text(message.get("role")) or "user"
        title = "系统回复" if role == "assistant" else "画像相关消息"
        content = _normalize_text(message.get("content"))
        snippet = content[:60] + ("..." if len(content) > 60 else "")
        items.append(
            {
                "id": f"message-{_normalize_text(message.get('id'))}",
                "timestamp": _normalize_text(message.get("created_at")),
                "type": "info" if role == "assistant" else "success",
                "title": title,
                "description": snippet or "记录了一条会话消息。",
                "source": "conversation",
            }
        )
    return items


def _parse_timestamp(value: object) -> datetime:
    normalized = _normalize_text(value)
    if not normalized:
        return datetime.min.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(normalized, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return datetime.min.replace(tzinfo=UTC)


def _sort_timestamp_key(value: object) -> tuple[int, float]:
    parsed = _parse_timestamp(value)
    if parsed == datetime.min.replace(tzinfo=UTC):
        return (0, 0.0)
    return (1, parsed.timestamp())


def _get_profile_or_404(profile_id: str) -> dict[str, object]:
    profile = _load_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile


def _enforce_profile_scope(profile: dict[str, object], current_user: dict[str, object]) -> None:
    allowed_tenant = _resolve_requested_tenant(current_user)
    if allowed_tenant is None:
        return
    profile_tenant = _normalize_text(profile.get("tenant_id"))
    if profile_tenant.lower() != allowed_tenant.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-tenant access denied for profile scope",
        )


def _append_profile_audit_log(
    *,
    action: str,
    current_user: dict[str, object],
    profile: dict[str, object],
    details: str,
    status_text: str = "success",
) -> None:
    log_payload = {
        "id": f"audit-profile-{datetime.now(UTC).timestamp()}",
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        "action": action,
        "user": _normalize_text(current_user.get("email") or current_user.get("id") or "system"),
        "resource": "人员画像",
        "status": status_text,
        "ip": "-",
        "details": f"{details}（画像 {profile['id']} / 租户 {profile['tenant_id']}）",
    }
    store.audit_logs.insert(0, deepcopy(log_payload))
    persistence_service.append_audit_log(log=log_payload)


def _tenant_description(profile_count: int, status_text: str) -> str:
    status_label = "启用中" if status_text == "active" else status_text
    return f"{status_label}，当前 {profile_count} 条画像。"


def _normalize_tenant_catalog_item(item: dict[str, object]) -> dict[str, object] | None:
    tenant_id = _normalize_text(item.get("id") or item.get("tenant_id") or item.get("tenantId"))
    if not tenant_id:
        return None
    tenant_status = _normalize_tenant_status(item.get("status") or item.get("tenant_status"))
    return {
        "id": tenant_id,
        "name": _normalize_tenant_name(item.get("name") or item.get("tenant_name"), tenant_id=tenant_id),
        "status": tenant_status,
        "description": _normalize_text(item.get("description")),
    }


def _load_tenant_catalog() -> list[dict[str, object]]:
    payload = store.system_settings.get(TENANT_DIRECTORY_SETTING_KEY)
    items = payload.get("items") if isinstance(payload, dict) else []
    if not isinstance(items, list):
        return []

    normalized_items: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for raw_item in items:
        if not isinstance(raw_item, dict):
            continue
        normalized = _normalize_tenant_catalog_item(raw_item)
        if normalized is None:
            continue
        normalized_id = _normalize_text(normalized.get("id")).lower()
        if normalized_id in seen_ids:
            continue
        seen_ids.add(normalized_id)
        normalized_items.append(normalized)
    return normalized_items


def _save_tenant_catalog(items: list[dict[str, object]]) -> None:
    normalized_items = []
    seen_ids: set[str] = set()
    for item in items:
        normalized = _normalize_tenant_catalog_item(item)
        if normalized is None:
            continue
        normalized_id = _normalize_text(normalized.get("id")).lower()
        if normalized_id in seen_ids:
            continue
        seen_ids.add(normalized_id)
        normalized_items.append(normalized)

    payload = {
        "items": normalized_items,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    store.system_settings[TENANT_DIRECTORY_SETTING_KEY] = deepcopy(payload)
    persistence_service.persist_system_setting(
        key=TENANT_DIRECTORY_SETTING_KEY,
        payload=payload,
        updated_at=payload["updated_at"],
    )


def _generate_tenant_id(name: str, existing_items: list[dict[str, object]]) -> str:
    normalized_name = _normalize_text(name).lower()
    base = re.sub(r"[^a-z0-9]+", "-", normalized_name).strip("-")
    existing_ids = {
        _normalize_text(item.get("id")).lower()
        for item in existing_items
        if _normalize_text(item.get("id"))
    }

    if base and base not in {"all", default_scope()["tenant_id"].lower()}:
        candidate_base = f"tenant-{base}"
    else:
        candidate_base = f"tenant-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"

    candidate_base = candidate_base[:48].rstrip("-") or "tenant"
    candidate = candidate_base
    suffix = 2
    while candidate.lower() in existing_ids or candidate.lower() == "all":
        candidate = f"{candidate_base[:44].rstrip('-') or 'tenant'}-{suffix}"
        suffix += 1
    return candidate


def _build_tenant_items(profiles: list[dict[str, object]]) -> list[dict[str, object]]:
    profile_counter: Counter[str] = Counter()

    for profile in profiles:
        tenant_id = _normalize_text(profile.get("tenant_id"))
        if not tenant_id:
            continue
        normalized_key = tenant_id.lower()
        profile_counter[normalized_key] += 1

    merged: dict[str, dict[str, object]] = {}

    for catalog_item in _load_tenant_catalog():
        tenant_id = _normalize_text(catalog_item.get("id"))
        if not tenant_id:
            continue
        normalized_key = tenant_id.lower()
        merged[normalized_key] = {
            "id": tenant_id,
            "name": _normalize_text(catalog_item.get("name")) or _normalize_tenant_name("", tenant_id=tenant_id),
            "status": _normalize_tenant_status(catalog_item.get("status")),
            "description": _normalize_text(catalog_item.get("description")),
            "profile_count": profile_counter.get(normalized_key, 0),
        }

    items = []
    for item in merged.values():
        tenant_status = _normalize_tenant_status(item.get("status"))
        profile_count = _normalize_interaction_count(item.get("profile_count"))
        description = _normalize_text(item.get("description")) or _tenant_description(profile_count, tenant_status)
        items.append(
            {
                "id": _normalize_text(item.get("id")),
                "name": _normalize_tenant_name(item.get("name"), tenant_id=_normalize_text(item.get("id"))),
                "status": tenant_status,
                "profile_count": profile_count,
                "description": description,
            }
        )

    return sorted(items, key=lambda item: (_normalize_text(item.get("name")).lower(), _normalize_text(item.get("id")).lower()))


def _append_tenant_audit_log(
    *,
    action: str,
    current_user: dict[str, object],
    tenant: dict[str, object],
    details: str,
    status_text: str = "success",
) -> None:
    log_payload = {
        "id": f"audit-tenant-{datetime.now(UTC).timestamp()}",
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        "action": action,
        "user": _normalize_text(current_user.get("email") or current_user.get("id") or "system"),
        "resource": "租户管理",
        "status": status_text,
        "ip": "-",
        "details": f"{details}（租户 {tenant['id']} / {tenant['name']}）",
    }
    store.audit_logs.insert(0, deepcopy(log_payload))
    persistence_service.append_audit_log(log=log_payload)


def list_profile_tenants(
    current_user: dict[str, object],
    *,
    management_view: bool = False,
) -> dict[str, object]:
    items = _build_tenant_items(_load_profiles())
    if management_view and _can_manage_tenant_directory(current_user):
        scope = current_user_scope(current_user)
        tenant_id = _normalize_text(scope.get("tenant_id"))
        default_tenant_id = next(
            (
                item["id"]
                for item in items
                if _normalize_text(item.get("id")).lower() == tenant_id.lower()
            ),
            items[0]["id"] if items else None,
        )
        return {
            "items": items,
            "total": len(items),
            "can_view_all_tenants": True,
            "default_tenant_id": default_tenant_id,
        }

    if _can_view_all_tenants(current_user):
        return {
            "items": items,
            "total": len(items),
            "can_view_all_tenants": True,
            "default_tenant_id": None,
        }

    scope = current_user_scope(current_user)
    tenant_id = _normalize_text(scope.get("tenant_id"))
    tenant_item = next(
        (item for item in items if _normalize_text(item.get("id")).lower() == tenant_id.lower()),
        None,
    )
    if tenant_item is None:
        if not tenant_id or tenant_id == default_scope()["tenant_id"]:
            return {
                "items": [],
                "total": 0,
                "can_view_all_tenants": False,
                "default_tenant_id": None,
            }
        tenant_item = {
            "id": tenant_id,
            "name": _normalize_tenant_name("", tenant_id=tenant_id),
            "status": DEFAULT_TENANT_STATUS,
            "profile_count": 0,
            "description": _tenant_description(0, DEFAULT_TENANT_STATUS),
        }
    return {
        "items": [tenant_item],
        "total": 1,
        "can_view_all_tenants": False,
        "default_tenant_id": tenant_id,
    }


def create_profile_tenant(
    *,
    current_user: dict[str, object],
    name: str,
    description: str = "",
) -> dict[str, object]:
    if not _can_manage_tenant_directory(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant management requires platform scope",
        )

    normalized_name = _normalize_text(name)
    if not normalized_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant name is required")

    existing_items = _build_tenant_items(_load_profiles())
    normalized_description = _normalize_text(description)
    normalized_tenant_id = _generate_tenant_id(normalized_name, existing_items)

    catalog_items = _load_tenant_catalog()
    created_tenant = {
        "id": normalized_tenant_id,
        "name": normalized_name,
        "status": DEFAULT_TENANT_STATUS,
        "description": normalized_description,
    }
    catalog_items.append(created_tenant)
    _save_tenant_catalog(catalog_items)

    tenant_item = next(
        item
        for item in _build_tenant_items(_load_profiles())
        if _normalize_text(item.get("id")).lower() == normalized_tenant_id.lower()
    )
    _append_tenant_audit_log(
        action="租户新增",
        current_user=current_user,
        tenant=tenant_item,
        details="已创建新的租户目录项。",
    )
    return {
        "ok": True,
        "message": "Tenant created",
        "tenant": tenant_item,
        "deleted_tenant_id": None,
    }


def delete_profile_tenant(
    tenant_id: str,
    *,
    current_user: dict[str, object],
) -> dict[str, object]:
    if not _can_manage_tenant_directory(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant management requires platform scope",
        )

    normalized_tenant_id = _normalize_text(tenant_id)
    if not normalized_tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant id is required")

    items = _build_tenant_items(_load_profiles())
    target_tenant = next(
        (item for item in items if _normalize_text(item.get("id")).lower() == normalized_tenant_id.lower()),
        None,
    )
    tenant_profiles = [
        profile
        for profile in _load_profiles()
        if _normalize_text(profile.get("tenant_id")).lower() == normalized_tenant_id.lower()
    ]
    if target_tenant is None:
        if not tenant_profiles:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
        sample_profile = tenant_profiles[0]
        target_tenant = {
            "id": normalized_tenant_id,
            "name": _normalize_text(sample_profile.get("tenant_name"))
            or _normalize_tenant_name("", tenant_id=normalized_tenant_id),
            "status": _normalize_tenant_status(sample_profile.get("tenant_status")),
            "profile_count": len(tenant_profiles),
            "description": _tenant_description(
                len(tenant_profiles),
                _normalize_tenant_status(sample_profile.get("tenant_status")),
            ),
        }

    linked_profile_ids: list[str] = []
    seen_profile_ids: set[str] = set()
    for profile in tenant_profiles:
        profile_id = _normalize_text(profile.get("id"))
        if not profile_id or profile_id in seen_profile_ids:
            continue
        seen_profile_ids.add(profile_id)
        linked_profile_ids.append(profile_id)

    for profile_id in linked_profile_ids:
        store.user_profiles.pop(profile_id, None)

    deleted_profile_count = persistence_service.delete_user_profiles(user_ids=linked_profile_ids)
    related_cleanup = memory_service.delete_scope_data(
        tenant_id=normalized_tenant_id,
        user_ids=linked_profile_ids,
    )

    catalog_items = [
        item
        for item in _load_tenant_catalog()
        if _normalize_text(item.get("id")).lower() != normalized_tenant_id.lower()
    ]
    _save_tenant_catalog(catalog_items)
    _append_tenant_audit_log(
        action="租户删除",
        current_user=current_user,
        tenant=target_tenant,
        details=(
            f"已删除租户目录项，并级联清理 {len(linked_profile_ids)} 份画像。"
            f" 已删除画像持久化 {deleted_profile_count} 条，相关消息 {related_cleanup['conversation_messages_deleted']} 条。"
        ),
    )
    return {
        "ok": True,
        "message": "Tenant deleted",
        "tenant": None,
        "deleted_tenant_id": normalized_tenant_id,
    }


def list_profiles(
    *,
    current_user: dict[str, object],
    tenant_id: str | None = None,
    search: str | None = None,
    management_view: bool = False,
) -> dict[str, object]:
    profiles, applied_tenant_id = _filter_profiles_for_scope(
        _load_profiles(),
        current_user,
        tenant_id=tenant_id,
        management_view=management_view,
    )
    if search:
        profiles = [profile for profile in profiles if _profile_matches_search(profile, search)]
    items = _sort_profiles(profiles)
    return {
        "items": items,
        "total": len(items),
        "applied_tenant_id": applied_tenant_id,
        "can_view_all_tenants": _can_view_all_tenants(current_user),
    }


def get_profile(profile_id: str, *, current_user: dict[str, object]) -> dict[str, object]:
    profile = _get_profile_or_404(profile_id)
    _enforce_profile_scope(profile, current_user)
    return profile


def get_profile_activity(profile_id: str, *, current_user: dict[str, object]) -> dict[str, object]:
    profile = get_profile(profile_id, current_user=current_user)
    items = _build_profile_activity_items(profile)
    items.extend(_build_audit_activity_items(profile))
    items.extend(_build_message_activity_items(profile))
    items.sort(key=lambda item: _parse_timestamp(item.get("timestamp")), reverse=True)
    return {"items": items, "total": len(items)}


def update_profile(
    profile_id: str,
    *,
    current_user: dict[str, object],
    tags: list[str],
    notes: str,
    preferred_language: str,
) -> dict[str, object]:
    profile = _get_profile_or_404(profile_id)
    _enforce_profile_scope(profile, current_user)
    profile.update(
        {
            "tags": _normalize_tags(tags),
            "notes": _normalize_text(notes) or "暂无额外备注。",
            "preferred_language": _normalize_preferred_language(preferred_language),
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )
    saved_profile = _sync_profile(profile)
    persistence_service.persist_user_state(profile=saved_profile)
    _append_profile_audit_log(
        action="画像更新",
        current_user=current_user,
        profile=saved_profile,
        details="已更新标签、备注与语言偏好。",
    )
    return {
        "ok": True,
        "message": "Profile updated",
        "profile": _normalize_profile(saved_profile),
    }


def export_profiles_csv(
    *,
    current_user: dict[str, object],
    tenant_id: str | None = None,
    search: str | None = None,
) -> tuple[str, str]:
    listed = list_profiles(current_user=current_user, tenant_id=tenant_id, search=search)
    buffer = StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(PROFILE_EXPORT_HEADERS.values())

    for item in listed["items"]:
        writer.writerow(
            [
                _normalize_text(item.get("tenant_id")),
                _normalize_text(item.get("tenant_name")),
                _normalize_text(item.get("id")),
                _normalize_text(item.get("name")),
                " | ".join(_normalize_source_channels(item.get("source_channels"))),
                " | ".join(
                    f"{account['platform']}:{account['account_id']}"
                    for account in _normalize_platform_accounts(item.get("platform_accounts"))
                ),
                " | ".join(_normalize_tags(item.get("tags"))),
                _normalize_preferred_language(item.get("preferred_language")),
                _normalize_text(item.get("last_active_at")),
                _normalize_interaction_count(item.get("total_interactions")),
                _normalize_text(item.get("notes")),
            ]
        )

    export_tenant = _normalize_text(listed.get("applied_tenant_id") or tenant_id) or "all"
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    filename = f"workbot-profiles-{export_tenant}-{timestamp}.csv"
    return "\ufeff" + buffer.getvalue(), filename
