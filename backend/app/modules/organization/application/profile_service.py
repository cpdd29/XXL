from __future__ import annotations

import csv
from collections import Counter
from copy import deepcopy
from datetime import UTC, datetime
import hmac
from hashlib import sha256
from io import StringIO
import re
from uuid import uuid4

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
SERVICE_REGISTRATION_STATUS_ISSUED = "issued"
SERVICE_REGISTRATION_STATUS_CONSUMED = "consumed"


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


def _normalize_channel_accounts(value: object) -> list[dict[str, str]]:
    return _normalize_platform_accounts(value)


def _normalize_preferred_language(value: object) -> str:
    normalized = _normalize_text(value).lower()
    if normalized in ALLOWED_PROFILE_LANGUAGES:
        return normalized
    prefix = normalized.split("-", 1)[0]
    if prefix in ALLOWED_PROFILE_LANGUAGES:
        return prefix
    return "zh"


def _normalize_profile_memory_list(value: object) -> list[str]:
    return _normalize_string_list(value)


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
    channel_accounts = _normalize_channel_accounts(
        profile.get("channel_accounts")
        or profile.get("channelAccounts")
        or profile.get("platform_accounts")
        or profile.get("platformAccounts")
    )
    source_channels = _normalize_source_channels(
        profile.get("source_channels")
        or profile.get("sourceChannels")
        or [account.get("platform") for account in channel_accounts]
    )
    company_name = _normalize_text(profile.get("company_name") or profile.get("companyName"))
    contact_name = _normalize_text(profile.get("contact_name") or profile.get("contactName"))
    first_seen_at = _normalize_timestamp(
        profile.get("first_seen_at"),
        profile.get("firstSeenAt"),
        profile.get("created_at"),
    )
    last_seen_at = _normalize_timestamp(
        profile.get("last_seen_at"),
        profile.get("lastSeenAt"),
        profile.get("last_active_at"),
        profile.get("lastActiveAt"),
        profile.get("updated_at"),
    )
    return {
        **deepcopy(profile),
        "id": profile_id,
        "customer_id": _normalize_text(profile.get("customer_id") or profile.get("customerId")) or profile_id,
        "tenant_id": tenant_id,
        "tenant_name": _normalize_tenant_name(
            profile.get("tenant_name") or profile.get("tenantName"),
            tenant_id=tenant_id,
        ),
        "tenant_status": _normalize_tenant_status(profile.get("tenant_status") or profile.get("tenantStatus")),
        "name": _normalize_text(profile.get("name")) or contact_name or company_name or profile_id,
        "company_name": company_name or None,
        "contact_name": contact_name or None,
        "mobile": _normalize_text(profile.get("mobile")) or None,
        "service_status": _normalize_text(profile.get("service_status") or profile.get("serviceStatus")).lower()
        or "active",
        "source_channels": source_channels,
        "channel_accounts": channel_accounts,
        "platform_accounts": channel_accounts,
        "tags": _normalize_tags(profile.get("tags")),
        "preferred_language": _normalize_preferred_language(
            profile.get("preferred_language") or profile.get("preferredLanguage")
        ),
        "first_seen_at": first_seen_at or None,
        "last_seen_at": last_seen_at or None,
        "notes": _normalize_text(profile.get("notes")) or "暂无额外备注。",
        "profile_summary": _normalize_text(profile.get("profile_summary") or profile.get("profileSummary")) or None,
        "preferences": _normalize_profile_memory_list(profile.get("preferences")),
        "business_background": _normalize_profile_memory_list(
            profile.get("business_background") or profile.get("businessBackground")
        ),
        "decision_history": _normalize_profile_memory_list(
            profile.get("decision_history") or profile.get("decisionHistory")
        ),
        "last_reception_at": _normalize_timestamp(
            profile.get("last_reception_at"),
            profile.get("lastReceptionAt"),
        )
        or None,
        "last_updated_by": _normalize_text(profile.get("last_updated_by") or profile.get("lastUpdatedBy")) or None,
        "last_active_at": _normalize_timestamp(
            profile.get("last_active_at"),
            profile.get("lastActiveAt"),
            profile.get("last_seen_at"),
            profile.get("lastSeenAt"),
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


def _sync_runtime_user(user_payload: dict[str, object]) -> dict[str, object]:
    user_id = _normalize_text(user_payload.get("id"))
    if not user_id:
        raise KeyError("User state requires id")
    normalized = deepcopy(user_payload)
    for cached_user in store.users:
        if _normalize_text(cached_user.get("id")) == user_id:
            cached_user.clear()
            cached_user.update(normalized)
            return cached_user
    store.users.append(normalized)
    return store.users[-1]


def _build_runtime_user_from_profile(profile: dict[str, object]) -> dict[str, object]:
    profile_id = _normalize_text(profile.get("id") or profile.get("user_id"))
    if not profile_id:
        raise KeyError("Profile requires id or user_id to build runtime user")

    accounts = _normalize_platform_accounts(
        profile.get("platform_accounts") or profile.get("channel_accounts")
    )
    primary_account = accounts[0] if accounts else {"platform": "external", "account_id": profile_id}
    last_login = (
        _normalize_timestamp(
            profile.get("last_login"),
            profile.get("lastLogin"),
            profile.get("last_active_at"),
            profile.get("lastActiveAt"),
            profile.get("updated_at"),
        )
        or store.now_string()
    )
    created_at = (
        _normalize_timestamp(
            profile.get("created_at"),
            profile.get("first_seen_at"),
            profile.get("firstSeenAt"),
            last_login,
        )
        or last_login
    )
    email = _normalize_text(profile.get("email")) or (
        f"{primary_account['platform']}-{primary_account['account_id']}@external.workbot.local"
    )
    return {
        "id": profile_id,
        "name": _normalize_text(profile.get("name")) or profile_id,
        "email": email,
        "role": _normalize_text(profile.get("role")).lower() or "viewer",
        "status": _normalize_text(profile.get("status")).lower() or "active",
        "last_login": last_login,
        "total_interactions": _normalize_interaction_count(profile.get("total_interactions")),
        "created_at": created_at,
    }


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


def _normalize_service_registration_entry(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {
            "status": None,
            "code_hash": None,
            "issued_at": None,
            "consumed_at": None,
        }
    status_text = _normalize_text(value.get("status")).lower()
    if status_text not in {SERVICE_REGISTRATION_STATUS_ISSUED, SERVICE_REGISTRATION_STATUS_CONSUMED}:
        status_text = None
    code_hash = _normalize_text(value.get("code_hash") or value.get("codeHash")).lower() or None
    issued_at = _normalize_text(value.get("issued_at") or value.get("issuedAt")) or None
    consumed_at = _normalize_text(value.get("consumed_at") or value.get("consumedAt")) or None
    if not code_hash:
        status_text = None
        issued_at = None
        consumed_at = None
    elif status_text is None:
        status_text = SERVICE_REGISTRATION_STATUS_CONSUMED if consumed_at else SERVICE_REGISTRATION_STATUS_ISSUED
    return {
        "status": status_text,
        "code_hash": code_hash,
        "issued_at": issued_at,
        "consumed_at": consumed_at,
    }


def _service_registration_entry_has_code(entry: dict[str, object]) -> bool:
    return bool(_normalize_text(entry.get("code_hash")))


def _merge_service_registration_history(*entries: dict[str, object]) -> list[dict[str, object]]:
    merged: list[dict[str, object]] = []
    index_by_hash: dict[str, int] = {}
    for raw_entry in entries:
        entry = _normalize_service_registration_entry(raw_entry)
        code_hash = _normalize_text(entry.get("code_hash")).lower()
        if not code_hash:
            continue
        existing_index = index_by_hash.get(code_hash)
        if existing_index is None:
            index_by_hash[code_hash] = len(merged)
            merged.append(entry)
            continue
        existing = merged[existing_index]
        existing_consumed_at = _normalize_text(existing.get("consumed_at")) or None
        entry_consumed_at = _normalize_text(entry.get("consumed_at")) or None
        if existing_consumed_at and not entry_consumed_at:
            continue
        merged[existing_index] = entry
    merged.sort(
        key=lambda item: (
            _normalize_text(item.get("consumed_at") or item.get("issued_at")) or "",
            _normalize_text(item.get("code_hash")) or "",
        ),
        reverse=True,
    )
    return merged


def _build_service_registration_state(
    *,
    current: dict[str, object] | None,
    history: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    normalized_current = _normalize_service_registration_entry(current or {})
    normalized_history = _merge_service_registration_history(*(history or []))
    if not _service_registration_entry_has_code(normalized_current):
        normalized_current = {
            "status": None,
            "code_hash": None,
            "issued_at": None,
            "consumed_at": None,
        }
    return {
        "status": normalized_current.get("status"),
        "code_hash": normalized_current.get("code_hash"),
        "issued_at": normalized_current.get("issued_at"),
        "consumed_at": normalized_current.get("consumed_at"),
        "history": normalized_history,
    }


def _normalize_service_registration_state(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return _build_service_registration_state(current=None, history=[])
    current = _normalize_service_registration_entry(value)
    history_payload = value.get("history")
    history_items = history_payload if isinstance(history_payload, list) else []
    history = [_normalize_service_registration_entry(item) for item in history_items]
    return _build_service_registration_state(current=current, history=history)


def _hash_service_registration_code(registration_code: str) -> str:
    normalized_code = _normalize_text(registration_code)
    if not normalized_code:
        return ""
    return sha256(normalized_code.encode("utf-8", errors="ignore")).hexdigest()


def _build_service_registration_code(*, tenant_id: str) -> str:
    normalized_tenant = re.sub(r"[^a-z0-9]+", "", _normalize_text(tenant_id).lower())[:6] or "tenant"
    entropy = sha256(
        f"{tenant_id}:{datetime.now(UTC).isoformat()}:{uuid4().hex}:{uuid4().hex}".encode(
            "utf-8",
            errors="ignore",
        )
    ).hexdigest().upper()
    return (
        f"SR-{normalized_tenant.upper()}-"
        f"{entropy[:6]}-{entropy[6:12]}-{entropy[12:18]}-{entropy[18:24]}"
    )


def _normalize_tenant_catalog_item(item: dict[str, object]) -> dict[str, object] | None:
    tenant_id = _normalize_text(item.get("id") or item.get("tenant_id") or item.get("tenantId"))
    if not tenant_id:
        return None
    tenant_status = _normalize_tenant_status(item.get("status") or item.get("tenant_status"))
    service_registration = _normalize_service_registration_state(
        item.get("service_registration") or item.get("serviceRegistration")
    )
    return {
        "id": tenant_id,
        "name": _normalize_tenant_name(item.get("name") or item.get("tenant_name"), tenant_id=tenant_id),
        "status": tenant_status,
        "description": _normalize_text(item.get("description")),
        "service_registration": service_registration,
    }


def _tenant_catalog_payload() -> dict[str, object] | None:
    read_setting = getattr(persistence_service, "read_system_setting", None)
    if callable(read_setting):
        persisted, authoritative = read_setting(TENANT_DIRECTORY_SETTING_KEY)
        if authoritative:
            payload = persisted.get("payload") if isinstance(persisted, dict) else None
            if isinstance(payload, dict):
                store.system_settings[TENANT_DIRECTORY_SETTING_KEY] = deepcopy(payload)
                return payload
            store.system_settings.pop(TENANT_DIRECTORY_SETTING_KEY, None)
            return None

    cached = store.system_settings.get(TENANT_DIRECTORY_SETTING_KEY)
    return deepcopy(cached) if isinstance(cached, dict) else None


def _load_tenant_catalog() -> list[dict[str, object]]:
    payload = _tenant_catalog_payload()
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


def _find_tenant_catalog_item(tenant_id: str) -> dict[str, object] | None:
    normalized_tenant_id = _normalize_text(tenant_id).lower()
    if not normalized_tenant_id:
        return None
    for item in _load_tenant_catalog():
        if _normalize_text(item.get("id")).lower() == normalized_tenant_id:
            return item
    return None


def resolve_tenant_binding(
    tenant_id: object | None,
    tenant_name: object | None = None,
) -> tuple[str | None, str | None]:
    normalized_tenant_id = _normalize_text(tenant_id) or None
    normalized_tenant_name = _normalize_text(tenant_name) or None
    catalog_items = _load_tenant_catalog()
    if not catalog_items:
        return normalized_tenant_id, normalized_tenant_name

    if normalized_tenant_id:
        exact_match = next(
            (
                item
                for item in catalog_items
                if _normalize_text(item.get("id")).lower() == normalized_tenant_id.lower()
            ),
            None,
        )
        if exact_match is not None:
            return _normalize_text(exact_match.get("id")) or normalized_tenant_id, (
                _normalize_text(exact_match.get("name")) or normalized_tenant_name
            )

    if normalized_tenant_name:
        same_name_items = [
            item
            for item in catalog_items
            if _normalize_text(item.get("name")).lower() == normalized_tenant_name.lower()
        ]
        if len(same_name_items) == 1:
            matched_item = same_name_items[0]
            return _normalize_text(matched_item.get("id")) or normalized_tenant_id, (
                _normalize_text(matched_item.get("name")) or normalized_tenant_name
            )

    if normalized_tenant_id and len(catalog_items) == 1:
        only_item = catalog_items[0]
        return _normalize_text(only_item.get("id")) or normalized_tenant_id, (
            _normalize_text(only_item.get("name")) or normalized_tenant_name
        )

    return normalized_tenant_id, normalized_tenant_name


def _resolve_profile_write_tenant(
    current_user: dict[str, object],
    requested_tenant_id: object,
) -> str:
    normalized_requested_tenant = _normalize_text(requested_tenant_id)
    actor_scope = current_user_scope(current_user)
    actor_tenant_id = _normalize_text(actor_scope.get("tenant_id")) or default_scope()["tenant_id"]
    if _can_manage_tenant_directory(current_user) or _can_view_all_tenants(current_user):
        return normalized_requested_tenant or actor_tenant_id
    if normalized_requested_tenant and normalized_requested_tenant.lower() != actor_tenant_id.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-tenant access denied for profile scope",
        )
    return actor_tenant_id


def _build_profile_patch(
    *,
    existing_profile: dict[str, object] | None,
    current_user: dict[str, object],
    profile_id: str,
    changes: dict[str, object],
) -> dict[str, object]:
    existing = deepcopy(existing_profile) if existing_profile is not None else {}
    now_iso = datetime.now(UTC).isoformat()

    tenant_id = _resolve_profile_write_tenant(
        current_user,
        changes.get("tenant_id") or changes.get("tenantId") or existing.get("tenant_id"),
    )
    tenant_catalog = _find_tenant_catalog_item(tenant_id)
    requested_tenant_name = _normalize_text(changes.get("tenant_name") or changes.get("tenantName"))
    channel_accounts_input = (
        changes.get("channel_accounts")
        if "channel_accounts" in changes
        else changes.get("channelAccounts")
    )
    platform_accounts_input = (
        changes.get("platform_accounts")
        if "platform_accounts" in changes
        else changes.get("platformAccounts")
    )
    accounts_source = (
        platform_accounts_input
        if platform_accounts_input is not None
        else channel_accounts_input
    )
    existing_accounts = existing.get("platform_accounts") or existing.get("channel_accounts")
    normalized_accounts = (
        _normalize_platform_accounts(accounts_source)
        if accounts_source is not None
        else _normalize_platform_accounts(existing_accounts)
    )

    raw_source_channels = changes.get("source_channels")
    if raw_source_channels is None and "sourceChannels" in changes:
        raw_source_channels = changes.get("sourceChannels")
    normalized_channels = (
        _normalize_source_channels(raw_source_channels)
        if raw_source_channels is not None
        else _normalize_source_channels(existing.get("source_channels") or [item["platform"] for item in normalized_accounts])
    )
    if not normalized_channels and normalized_accounts:
        normalized_channels = _normalize_source_channels([item["platform"] for item in normalized_accounts])

    preferred_language = (
        _normalize_preferred_language(changes.get("preferred_language") or changes.get("preferredLanguage"))
        if "preferred_language" in changes or "preferredLanguage" in changes
        else _normalize_preferred_language(existing.get("preferred_language"))
    )

    tags = (
        _normalize_tags(changes.get("tags"))
        if "tags" in changes
        else _normalize_tags(existing.get("tags"))
    )
    notes = (
        _normalize_text(changes.get("notes")) or "暂无额外备注。"
        if "notes" in changes
        else _normalize_text(existing.get("notes")) or "暂无额外备注。"
    )
    if "profile_summary" in changes:
        profile_summary = _normalize_text(changes.get("profile_summary")) or None
    elif "profileSummary" in changes:
        profile_summary = _normalize_text(changes.get("profileSummary")) or None
    else:
        profile_summary = _normalize_text(existing.get("profile_summary") or existing.get("profileSummary")) or None
    preferences = (
        _normalize_profile_memory_list(changes.get("preferences"))
        if "preferences" in changes
        else _normalize_profile_memory_list(existing.get("preferences"))
    )
    if "business_background" in changes:
        business_background = _normalize_profile_memory_list(changes.get("business_background"))
    elif "businessBackground" in changes:
        business_background = _normalize_profile_memory_list(changes.get("businessBackground"))
    else:
        business_background = _normalize_profile_memory_list(
            existing.get("business_background") or existing.get("businessBackground")
        )
    if "decision_history" in changes:
        decision_history = _normalize_profile_memory_list(changes.get("decision_history"))
    elif "decisionHistory" in changes:
        decision_history = _normalize_profile_memory_list(changes.get("decisionHistory"))
    else:
        decision_history = _normalize_profile_memory_list(
            existing.get("decision_history") or existing.get("decisionHistory")
        )
    created_at = (
        _normalize_timestamp(
            changes.get("created_at"),
            changes.get("createdAt"),
            existing.get("created_at"),
            changes.get("first_seen_at"),
            changes.get("firstSeenAt"),
        )
        or now_iso
    )
    first_seen_at = _normalize_timestamp(
        changes.get("first_seen_at"),
        changes.get("firstSeenAt"),
        existing.get("first_seen_at"),
        existing.get("created_at"),
    ) or created_at
    last_seen_at = _normalize_timestamp(
        changes.get("last_seen_at"),
        changes.get("lastSeenAt"),
        changes.get("last_active_at"),
        changes.get("lastActiveAt"),
        existing.get("last_seen_at"),
        existing.get("last_active_at"),
        created_at,
    )
    company_name = _normalize_text(changes.get("company_name") or changes.get("companyName")) or _normalize_text(
        existing.get("company_name")
    )
    contact_name = _normalize_text(changes.get("contact_name") or changes.get("contactName")) or _normalize_text(
        existing.get("contact_name")
    )
    service_code = _normalize_text(changes.get("service_code") or changes.get("serviceCode")) or _normalize_text(
        existing.get("service_code")
    )
    name = (
        _normalize_text(changes.get("name"))
        or contact_name
        or company_name
        or _normalize_text(existing.get("name"))
        or profile_id
    )
    email = _normalize_text(changes.get("email")) or _normalize_text(existing.get("email")) or None
    role = _normalize_text(changes.get("role")).lower() or _normalize_text(existing.get("role")).lower() or "viewer"
    profile_status = (
        _normalize_text(changes.get("status")).lower()
        or _normalize_text(existing.get("status")).lower()
        or "active"
    )
    last_login = _normalize_timestamp(
        changes.get("last_login"),
        changes.get("lastLogin"),
        existing.get("last_login"),
        existing.get("lastLogin"),
        last_seen_at,
        created_at,
    )
    total_interactions_input = (
        changes.get("total_interactions")
        if "total_interactions" in changes
        else changes.get("totalInteractions")
        if "totalInteractions" in changes
        else existing.get("total_interactions")
    )
    identity_mapping_status = (
        _normalize_text(changes.get("identity_mapping_status") or changes.get("identityMappingStatus"))
        or _normalize_text(existing.get("identity_mapping_status"))
        or _normalize_text(existing.get("identityMappingStatus"))
    )
    identity_mapping_source = (
        _normalize_text(changes.get("identity_mapping_source") or changes.get("identityMappingSource"))
        or _normalize_text(existing.get("identity_mapping_source"))
        or _normalize_text(existing.get("identityMappingSource"))
    )
    if "identity_mapping_confidence" in changes:
        identity_mapping_confidence = _normalize_confidence(changes.get("identity_mapping_confidence"))
    elif "identityMappingConfidence" in changes:
        identity_mapping_confidence = _normalize_confidence(changes.get("identityMappingConfidence"))
    else:
        identity_mapping_confidence = _normalize_confidence(
            existing.get("identity_mapping_confidence") or existing.get("identityMappingConfidence")
        )
    last_identity_sync_at = _normalize_timestamp(
        changes.get("last_identity_sync_at"),
        changes.get("lastIdentitySyncAt"),
        existing.get("last_identity_sync_at"),
        existing.get("lastIdentitySyncAt"),
        last_login,
    )
    last_reception_at = _normalize_timestamp(
        changes.get("last_reception_at"),
        changes.get("lastReceptionAt"),
        existing.get("last_reception_at"),
        existing.get("lastReceptionAt"),
    ) or None
    last_updated_by = (
        _normalize_text(changes.get("last_updated_by") or changes.get("lastUpdatedBy"))
        or _normalize_text(existing.get("last_updated_by") or existing.get("lastUpdatedBy"))
        or None
    )

    return {
        **existing,
        "id": profile_id,
        "user_id": profile_id,
        "customer_id": _normalize_text(changes.get("customer_id") or changes.get("customerId"))
        or _normalize_text(existing.get("customer_id"))
        or profile_id,
        "tenant_id": tenant_id,
        "tenant_name": requested_tenant_name
        or _normalize_text(tenant_catalog.get("name") if tenant_catalog else "")
        or _normalize_tenant_name(existing.get("tenant_name"), tenant_id=tenant_id),
        "tenant_status": _normalize_tenant_status(
            (tenant_catalog or {}).get("status") or existing.get("tenant_status")
        ),
        "name": name,
        "email": email,
        "role": role,
        "status": profile_status,
        "last_login": last_login,
        "total_interactions": _normalize_interaction_count(total_interactions_input),
        "company_name": company_name or None,
        "contact_name": contact_name or None,
        "mobile": _normalize_text(changes.get("mobile")) or _normalize_text(existing.get("mobile")) or None,
        "service_code": service_code or None,
        "service_status": _normalize_text(changes.get("service_status") or changes.get("serviceStatus")).lower()
        or _normalize_text(existing.get("service_status")).lower()
        or "active",
        "source_channels": normalized_channels,
        "channel_accounts": normalized_accounts,
        "platform_accounts": normalized_accounts,
        "tags": tags,
        "preferred_language": preferred_language,
        "first_seen_at": first_seen_at,
        "last_seen_at": last_seen_at,
        "last_active_at": last_seen_at,
        "notes": notes,
        "profile_summary": profile_summary,
        "preferences": preferences,
        "business_background": business_background,
        "decision_history": decision_history,
        "last_reception_at": last_reception_at,
        "last_updated_by": last_updated_by,
        "created_at": created_at,
        "updated_at": now_iso,
        "identity_mapping_status": identity_mapping_status or None,
        "identity_mapping_source": identity_mapping_source or None,
        "identity_mapping_confidence": identity_mapping_confidence,
        "last_identity_sync_at": last_identity_sync_at or None,
    }


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


def generate_profile_tenant_service_registration_code(
    *,
    tenant_id: str,
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

    catalog_items = _load_tenant_catalog()
    target_index = next(
        (
            index
            for index, item in enumerate(catalog_items)
            if _normalize_text(item.get("id")).lower() == normalized_tenant_id.lower()
        ),
        None,
    )
    if target_index is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    target_item = deepcopy(catalog_items[target_index])
    registration_state = _normalize_service_registration_state(target_item.get("service_registration"))
    current_entry = _normalize_service_registration_entry(registration_state)
    history_entries = [
        _normalize_service_registration_entry(item)
        for item in (
            registration_state.get("history")
            if isinstance(registration_state.get("history"), list)
            else []
        )
    ]
    replaced_pending_code = bool(
        current_entry.get("status") == SERVICE_REGISTRATION_STATUS_ISSUED
        and _normalize_text(current_entry.get("code_hash"))
    )
    if replaced_pending_code:
        history_entries = _merge_service_registration_history(*history_entries, current_entry)
    if (
        current_entry.get("status") == SERVICE_REGISTRATION_STATUS_CONSUMED
        and _normalize_text(current_entry.get("code_hash"))
    ):
        history_entries = _merge_service_registration_history(*history_entries, current_entry)

    registration_code = _build_service_registration_code(tenant_id=normalized_tenant_id)
    issued_at = datetime.now(UTC).isoformat()
    target_item["service_registration"] = _build_service_registration_state(
        current={
            "status": SERVICE_REGISTRATION_STATUS_ISSUED,
            "code_hash": _hash_service_registration_code(registration_code),
            "issued_at": issued_at,
            "consumed_at": None,
        },
        history=history_entries,
    )
    catalog_items[target_index] = target_item
    _save_tenant_catalog(catalog_items)

    tenant_item = next(
        (
            item
            for item in _build_tenant_items(_load_profiles())
            if _normalize_text(item.get("id")).lower() == normalized_tenant_id.lower()
        ),
        {
            "id": normalized_tenant_id,
            "name": _normalize_tenant_name("", tenant_id=normalized_tenant_id),
            "status": DEFAULT_TENANT_STATUS,
            "profile_count": 0,
            "description": _tenant_description(0, DEFAULT_TENANT_STATUS),
        },
    )
    _append_tenant_audit_log(
        action="服务识别码生成",
        current_user=current_user,
        tenant=tenant_item,
        details=(
            "已生成新的服务识别码，等待客户完成注册。"
            if not replaced_pending_code
            else "已生成新的服务识别码，并替换上一条尚未注册的服务识别码。"
        ),
    )
    return {
        "ok": True,
        "message": "Service registration code generated",
        "tenant_id": normalized_tenant_id,
        "registration_code": registration_code,
        "status": SERVICE_REGISTRATION_STATUS_ISSUED,
        "issued_at": issued_at,
    }


def consume_profile_tenant_service_registration_code(
    *,
    tenant_id: str,
    registration_code: str,
) -> bool:
    normalized_tenant_id = _normalize_text(tenant_id)
    normalized_code = _normalize_text(registration_code)
    if not normalized_tenant_id or not normalized_code:
        return False

    if not match_profile_tenant_service_registration_code(
        tenant_id=normalized_tenant_id,
        registration_code=normalized_code,
    ):
        return False

    catalog_items = _load_tenant_catalog()
    target_index = next(
        (
            index
            for index, item in enumerate(catalog_items)
            if _normalize_text(item.get("id")).lower() == normalized_tenant_id.lower()
        ),
        None,
    )
    if target_index is None:
        return False

    target_item = deepcopy(catalog_items[target_index])
    registration_state = _normalize_service_registration_state(target_item.get("service_registration"))
    normalized_hash = _hash_service_registration_code(normalized_code)
    current_entry = _normalize_service_registration_entry(registration_state)
    history_entries = [
        _normalize_service_registration_entry(item)
        for item in (
            registration_state.get("history")
            if isinstance(registration_state.get("history"), list)
            else []
        )
    ]
    consumed_at = datetime.now(UTC).isoformat()

    updated_current = current_entry
    current_entry_matched = _normalize_text(current_entry.get("code_hash")).lower() == normalized_hash
    if current_entry_matched:
        updated_current = {
            **current_entry,
            "status": SERVICE_REGISTRATION_STATUS_CONSUMED,
            "consumed_at": consumed_at,
        }
    else:
        next_history: list[dict[str, object]] = []
        for entry in history_entries:
            if _normalize_text(entry.get("code_hash")).lower() == normalized_hash:
                next_history.append(
                    {
                        **entry,
                        "status": SERVICE_REGISTRATION_STATUS_CONSUMED,
                        "consumed_at": consumed_at,
                    }
                )
            else:
                next_history.append(entry)
        history_entries = next_history

    if current_entry_matched:
        history_entries = _merge_service_registration_history(*history_entries, updated_current)
    else:
        history_entries = _merge_service_registration_history(*history_entries)
    target_item["service_registration"] = _build_service_registration_state(
        current=updated_current,
        history=history_entries,
    )
    catalog_items[target_index] = target_item
    _save_tenant_catalog(catalog_items)
    return True


def match_profile_tenant_service_registration_code(
    *,
    tenant_id: str,
    registration_code: str,
) -> bool:
    normalized_tenant_id = _normalize_text(tenant_id)
    normalized_code = _normalize_text(registration_code)
    if not normalized_tenant_id or not normalized_code:
        return False

    catalog_items = _load_tenant_catalog()
    target_item = next(
        (
            item
            for item in catalog_items
            if _normalize_text(item.get("id")).lower() == normalized_tenant_id.lower()
        ),
        None,
    )
    if target_item is None:
        return False

    registration_state = _normalize_service_registration_state(target_item.get("service_registration"))
    expected_hash = _hash_service_registration_code(normalized_code)
    current_entry = _normalize_service_registration_entry(registration_state)
    history_entries = [
        _normalize_service_registration_entry(item)
        for item in (
            registration_state.get("history")
            if isinstance(registration_state.get("history"), list)
            else []
        )
    ]
    candidate_entries = [current_entry, *history_entries]
    for entry in candidate_entries:
        entry_hash = _normalize_text(entry.get("code_hash")).lower()
        entry_status = _normalize_text(entry.get("status")).lower()
        if entry_status not in {SERVICE_REGISTRATION_STATUS_ISSUED, SERVICE_REGISTRATION_STATUS_CONSUMED}:
            continue
        if entry_hash and hmac.compare_digest(entry_hash, expected_hash):
            return True
    return False


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


def upsert_profile(
    *,
    current_user: dict[str, object],
    profile_id: str | None = None,
    changes: dict[str, object] | None = None,
    sync_user_state: bool = False,
) -> dict[str, object]:
    payload = dict(changes or {})
    resolved_profile_id = (
        _normalize_text(profile_id)
        or _normalize_text(payload.get("id"))
        or _normalize_text(payload.get("profile_id") or payload.get("profileId"))
        or _normalize_text(payload.get("customer_id") or payload.get("customerId"))
        or f"customer-profile-{uuid4().hex[:12]}"
    )

    existing_profile = _load_profile(resolved_profile_id)
    if existing_profile is not None:
        _enforce_profile_scope(existing_profile, current_user)

    saved_profile = _sync_profile(
        _build_profile_patch(
            existing_profile=existing_profile,
            current_user=current_user,
            profile_id=resolved_profile_id,
            changes=payload,
        )
    )
    if sync_user_state:
        synced_user = _sync_runtime_user(_build_runtime_user_from_profile(saved_profile))
        persistence_service.persist_user_state(user=synced_user, profile=saved_profile)
    else:
        persistence_service.persist_user_state(profile=saved_profile)
    _append_profile_audit_log(
        action="画像创建" if existing_profile is None else "画像更新",
        current_user=current_user,
        profile=saved_profile,
        details="已创建客户画像主档。" if existing_profile is None else "已更新客户画像主档。",
    )
    return {
        "ok": True,
        "message": "Profile created" if existing_profile is None else "Profile updated",
        "profile": _normalize_profile(saved_profile),
    }


def update_profile(
    profile_id: str,
    *,
    current_user: dict[str, object],
    changes: dict[str, object] | None = None,
) -> dict[str, object]:
    return upsert_profile(
        current_user=current_user,
        profile_id=profile_id,
        changes=changes,
    )


def delete_profile(
    profile_id: str,
    *,
    current_user: dict[str, object],
) -> dict[str, object]:
    normalized_profile_id = _normalize_text(profile_id)
    if not normalized_profile_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Profile id is required")

    existing_profile = _get_profile_or_404(normalized_profile_id)
    _enforce_profile_scope(existing_profile, current_user)

    store.user_profiles.pop(normalized_profile_id, None)
    store.users = [
        item
        for item in store.users
        if _normalize_text(item.get("id")) != normalized_profile_id
    ]
    persistence_service.delete_user_profiles(user_ids=[normalized_profile_id])
    related_cleanup = memory_service.delete_scope_data(
        tenant_id=_normalize_text(existing_profile.get("tenant_id")),
        user_ids=[normalized_profile_id],
    )
    _append_profile_audit_log(
        action="画像删除",
        current_user=current_user,
        profile=existing_profile,
        details=(
            "已删除客户画像主档。"
            f" 相关消息清理 {related_cleanup['conversation_messages_deleted']} 条。"
        ),
    )
    return {
        "ok": True,
        "message": "Profile deleted",
        "deleted_profile_id": normalized_profile_id,
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
