import csv
from datetime import UTC, datetime
from fastapi import HTTPException, status
from io import StringIO
from uuid import uuid4

from app.services.persistence_service import persistence_service
from app.services.store import store

ALLOWED_USER_ROLES = {"admin", "operator", "viewer"}
ALLOWED_USER_STATUSES = {"active", "inactive", "suspended"}
ALLOWED_PROFILE_LANGUAGES = {"zh", "en"}
ALLOWED_IDENTITY_MAPPING_STATUSES = {"unmapped", "auto_mapped", "manually_verified", "merged"}
ALLOWED_IDENTITY_MAPPING_SOURCES = {
    "unknown",
    "system_auto_bind",
    "manual_override",
    "import",
}
USER_EXPORT_HEADERS = {
    "id": "用户ID",
    "name": "姓名",
    "email": "邮箱",
    "role": "角色",
    "status": "状态",
    "last_login": "最后登录",
    "total_interactions": "交互次数",
    "created_at": "创建时间",
    "tags": "标签",
    "preferred_language": "偏好语言",
    "source_channels": "来源渠道",
    "platform_accounts": "平台账号",
    "notes": "备注",
}


def _find_user(user_id: str) -> dict:
    for user in store.users:
        if user["id"] == user_id:
            return user
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")


def _find_cached_user(user_id: str) -> dict | None:
    for user in store.users:
        if user["id"] == user_id:
            return user
    return None


def _sync_cached_user(user_payload: dict) -> dict:
    user_id = str(user_payload.get("id") or "").strip()
    cached_user = _find_cached_user(user_id)
    payload = store.clone(user_payload)
    if cached_user is None:
        store.users.append(payload)
        return payload

    cached_user.clear()
    cached_user.update(payload)
    return cached_user


def _find_user_mutable(user_id: str) -> dict:
    database_user, database_authoritative = _load_database_user(user_id)
    if database_authoritative:
        if database_user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return _sync_cached_user(database_user)

    cached_user = _find_cached_user(user_id)
    if cached_user is not None:
        return cached_user

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")


def _sync_cached_profile(user_id: str, profile_payload: dict) -> dict:
    payload = store.clone(profile_payload)
    store.user_profiles[user_id] = payload
    return store.user_profiles[user_id]


def _read_user(user_id: str) -> dict:
    user, _database_authoritative = _read_user_with_source(user_id)
    return user


def _read_user_or_none(user_id: str) -> dict | None:
    user, _database_authoritative = _read_user_with_source(user_id, allow_missing=True)
    return user


def _read_user_profile(user_id: str) -> dict | None:
    database_profile = persistence_service.get_user_profile(user_id)
    if database_profile is not None:
        return database_profile
    database_user, database_authoritative = _load_database_user(user_id)
    if database_authoritative:
        return None
    profile = store.user_profiles.get(user_id)
    if profile:
        return store.clone(profile)
    return None


def _load_database_user(user_id: str) -> tuple[dict | None, bool]:
    if not getattr(persistence_service, "enabled", False):
        return None, False

    database_user = persistence_service.get_user(user_id)
    if database_user is not None:
        return database_user, True

    database_users = persistence_service.list_users(search=None)
    if database_users is None:
        return None, True

    for candidate in database_users:
        if str(candidate.get("id") or "").strip() == user_id:
            return candidate, True
    return None, True


def _read_user_with_source(
    user_id: str,
    *,
    allow_missing: bool = False,
) -> tuple[dict | None, bool]:
    database_user, database_authoritative = _load_database_user(user_id)
    if database_authoritative:
        if database_user is None:
            if allow_missing:
                return None, True
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return database_user, True

    for item in store.users:
        if item["id"] == user_id:
            return store.clone(item), False

    if allow_missing:
        return None, False
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")


def _normalize_platform_accounts(profile: dict) -> list[dict]:
    accounts = profile.get("platform_accounts") or profile.get("platformAccounts") or []
    if not isinstance(accounts, list):
        return []

    normalized_accounts: list[dict] = []
    seen_accounts: set[tuple[str, str]] = set()
    for account in accounts:
        if not isinstance(account, dict):
            continue
        platform = str(account.get("platform") or "").strip().lower()
        account_id = str(account.get("account_id") or account.get("accountId") or "").strip()
        if not platform or not account_id:
            continue
        key = (platform, account_id)
        if key in seen_accounts:
            continue
        normalized_accounts.append({"platform": platform, "account_id": account_id})
        seen_accounts.add(key)
    return normalized_accounts


def _normalize_profile_tags(tags: object) -> list[str]:
    if not isinstance(tags, list):
        return []

    normalized_tags: list[str] = []
    seen_tags: set[str] = set()
    for tag in tags:
        normalized = str(tag).strip()
        if not normalized or normalized in seen_tags:
            continue
        normalized_tags.append(normalized)
        seen_tags.add(normalized)
    return normalized_tags


def _normalize_preferred_language(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in ALLOWED_PROFILE_LANGUAGES:
        return normalized
    prefix = normalized.split("-", 1)[0]
    if prefix in ALLOWED_PROFILE_LANGUAGES:
        return prefix
    return "zh"


def _normalize_mapping_status(value: object, *, has_accounts: bool) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in ALLOWED_IDENTITY_MAPPING_STATUSES:
        return normalized
    return "auto_mapped" if has_accounts else "unmapped"


def _normalize_mapping_source(value: object, *, status_text: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in ALLOWED_IDENTITY_MAPPING_SOURCES:
        return normalized
    if status_text == "manually_verified":
        return "manual_override"
    if status_text in {"auto_mapped", "merged"}:
        return "system_auto_bind"
    return "unknown"


def _normalize_mapping_confidence(value: object, *, status_text: str) -> float:
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        normalized = None
    if normalized is None:
        if status_text == "manually_verified":
            return 1.0
        if status_text in {"auto_mapped", "merged"}:
            return 0.85
        return 0.0
    if normalized < 0:
        return 0.0
    if normalized > 1:
        return 1.0
    return round(normalized, 4)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_user_profile(profile: dict, *, user: dict | None = None) -> dict:
    user_payload = user or {}
    source_channels = profile.get("source_channels") or profile.get("sourceChannels") or []
    if not isinstance(source_channels, list):
        source_channels = []

    normalized_role = str(profile.get("role") or user_payload.get("role") or "viewer").strip()
    if normalized_role not in ALLOWED_USER_ROLES:
        normalized_role = "viewer"

    normalized_status = str(profile.get("status") or user_payload.get("status") or "active").strip()
    if normalized_status not in ALLOWED_USER_STATUSES:
        normalized_status = "active"

    platform_accounts = _normalize_platform_accounts(profile)
    mapping_status = _normalize_mapping_status(
        profile.get("identity_mapping_status") or profile.get("identityMappingStatus"),
        has_accounts=bool(platform_accounts),
    )
    mapping_source = _normalize_mapping_source(
        profile.get("identity_mapping_source") or profile.get("identityMappingSource"),
        status_text=mapping_status,
    )
    mapping_confidence = _normalize_mapping_confidence(
        profile.get("identity_mapping_confidence") or profile.get("identityMappingConfidence"),
        status_text=mapping_status,
    )
    last_identity_sync_at = str(
        profile.get("last_identity_sync_at")
        or profile.get("lastIdentitySyncAt")
        or profile.get("updated_at")
        or user_payload.get("last_login")
        or ""
    ).strip() or None

    return {
        **user_payload,
        **profile,
        "id": str(profile.get("id") or profile.get("user_id") or user_payload.get("id") or ""),
        "name": str(profile.get("name") or user_payload.get("name") or ""),
        "email": str(profile.get("email") or user_payload.get("email") or ""),
        "role": normalized_role,
        "status": normalized_status,
        "last_login": str(profile.get("last_login") or user_payload.get("last_login") or ""),
        "total_interactions": int(
            profile.get("total_interactions") or user_payload.get("total_interactions") or 0
        ),
        "created_at": str(profile.get("created_at") or user_payload.get("created_at") or ""),
        "tags": _normalize_profile_tags(profile.get("tags") or []),
        "notes": str(profile.get("notes") or "").strip() or "暂无额外备注。",
        "preferred_language": _normalize_preferred_language(profile.get("preferred_language") or "zh"),
        "source_channels": [
            str(channel).strip().lower()
            for channel in source_channels
            if str(channel).strip()
        ],
        "platform_accounts": platform_accounts,
        "identity_mapping_status": mapping_status,
        "identity_mapping_source": mapping_source,
        "identity_mapping_confidence": mapping_confidence,
        "last_identity_sync_at": last_identity_sync_at,
    }


def _build_profile_payload_from_user(user: dict) -> dict:
    return _normalize_user_profile(
        {
            "id": str(user.get("id") or ""),
            "name": str(user.get("name") or ""),
            "email": str(user.get("email") or ""),
            "role": str(user.get("role") or "viewer"),
            "status": str(user.get("status") or "active"),
            "last_login": str(user.get("last_login") or ""),
            "total_interactions": int(user.get("total_interactions") or 0),
            "created_at": str(user.get("created_at") or ""),
            "tags": [],
            "notes": "暂无额外备注。",
            "preferred_language": "zh",
            "source_channels": [],
            "platform_accounts": [],
            "identity_mapping_status": "unmapped",
            "identity_mapping_source": "unknown",
            "identity_mapping_confidence": 0.0,
            "last_identity_sync_at": None,
        },
        user=user,
    )


def _ensure_user_profile_for_update(user_id: str, *, user: dict) -> dict:
    database_profile = persistence_service.get_user_profile(user_id)
    if database_profile is not None:
        profile = _sync_cached_profile(user_id, database_profile)
        normalized_profile = _normalize_user_profile(profile, user=user)
        profile.clear()
        profile.update(normalized_profile)
        return profile

    if getattr(persistence_service, "enabled", False):
        return _sync_cached_profile(user_id, _build_profile_payload_from_user(user))

    profile = store.user_profiles.get(user_id)
    if profile is None:
        return _sync_cached_profile(user_id, _build_profile_payload_from_user(user))

    normalized_profile = _normalize_user_profile(profile, user=user)
    profile.clear()
    profile.update(normalized_profile)
    return profile


def _build_activity_timestamp(base_date: str, suffix: str) -> str:
    if " " in base_date:
        return base_date
    return f"{base_date} {suffix}"


def _parse_activity_timestamp(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        parsed = None
    if parsed is not None:
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return datetime.min.replace(tzinfo=UTC)


def _load_audit_logs() -> list[dict]:
    database_logs = persistence_service.list_audit_logs()
    if database_logs is not None:
        return database_logs
    if getattr(persistence_service, "enabled", False):
        return []
    return store.clone(store.audit_logs)


def _load_recent_conversation_messages(user_id: str, *, limit: int = 4) -> list[dict]:
    database_messages = persistence_service.list_conversation_messages(user_id=user_id, limit=limit)
    return database_messages or []


def _activity_user_candidates(user_id: str, profile: dict) -> set[str]:
    email = str(profile.get("email") or "").lower()
    email_prefix = email.split("@", 1)[0] if "@" in email else email
    name = str(profile.get("name") or "").lower()
    candidates = {email, email_prefix, name}
    if len(user_id) >= 3:
        candidates.add(user_id.lower())
    return {candidate for candidate in candidates if candidate}


def _matches_user_audit_log(log: dict, *, user_id: str, profile: dict) -> bool:
    log_user = str(log.get("user") or "").lower()
    log_details = str(log.get("details") or "").lower()
    exact_candidates = {user_id.lower()}
    if log_user in exact_candidates:
        return True
    return any(candidate in log_user or candidate in log_details for candidate in _activity_user_candidates(user_id, profile))


def _activity_type_from_status(status_text: str) -> str:
    normalized = status_text.lower()
    if normalized in {"error", "failed", "danger"}:
        return "warning"
    if normalized in {"warning", "warn"}:
        return "warning"
    if normalized in {"success", "ok"}:
        return "success"
    return "info"


def _build_profile_activity_items(user_id: str, profile: dict) -> list[dict]:
    role_label = {
        "admin": "管理员",
        "operator": "运维员",
        "viewer": "查看者",
    }.get(profile["role"], profile["role"])
    status_label = {
        "active": "活跃",
        "inactive": "不活跃",
        "suspended": "已停用",
    }.get(profile["status"], profile["status"])

    items = [
        {
            "id": f"{user_id}-login",
            "timestamp": profile["last_login"],
            "type": "success",
            "title": "最近登录",
            "description": f"{profile['name']} 最近一次登录系统，当前角色为 {role_label}",
            "source": "auth",
        },
        {
            "id": f"{user_id}-status",
            "timestamp": profile["last_login"],
            "type": "warning" if profile["status"] == "suspended" else "info",
            "title": "账户状态同步",
            "description": f"账户当前状态为 {status_label}",
            "source": "user-center",
        },
        {
            "id": f"{user_id}-interactions",
            "timestamp": profile["last_login"],
            "type": "info",
            "title": "交互统计更新",
            "description": f"累计交互次数已达到 {profile['total_interactions']} 次",
            "source": "analytics",
        },
        {
            "id": f"{user_id}-role",
            "timestamp": _build_activity_timestamp(profile["created_at"], "10:00"),
            "type": "info",
            "title": "角色分配",
            "description": f"账号初始化角色为 {role_label}",
            "source": "rbac",
        },
        {
            "id": f"{user_id}-created",
            "timestamp": _build_activity_timestamp(profile["created_at"], "09:00"),
            "type": "success",
            "title": "账户创建",
            "description": "账号已完成初始化并接入 WorkBot 管理台",
            "source": "system",
        },
    ]

    for index, channel in enumerate(profile["source_channels"]):
        items.append(
            {
                "id": f"{user_id}-channel-{index}",
                "timestamp": _build_activity_timestamp(profile["created_at"], f"{11 + index:02d}:00"),
                "type": "success",
                "title": "渠道接入",
                "description": f"已绑定 {channel} 作为用户触达或接入渠道",
                "source": "integration",
            }
        )

    for index, account in enumerate(profile.get("platform_accounts") or []):
        if not isinstance(account, dict):
            continue
        platform = str(account.get("platform") or "").strip()
        account_id = str(account.get("account_id") or account.get("accountId") or "").strip()
        if not platform or not account_id:
            continue
        items.append(
            {
                "id": f"{user_id}-platform-account-{index}",
                "timestamp": _build_activity_timestamp(profile["created_at"], f"{13 + index:02d}:30"),
                "type": "info",
                "title": "平台账号绑定",
                "description": f"已绑定 {platform} 账号 {account_id}",
                "source": "identity",
            }
        )

    return items


def _build_audit_activity_items(user_id: str, profile: dict) -> list[dict]:
    items: list[dict] = []
    for log in _load_audit_logs():
        if not _matches_user_audit_log(log, user_id=user_id, profile=profile):
            continue
        items.append(
            {
                "id": f"audit-{log['id']}",
                "timestamp": log["timestamp"],
                "type": _activity_type_from_status(str(log.get("status") or "")),
                "title": str(log.get("action") or "审计事件"),
                "description": str(log.get("details") or "记录了一条用户相关的审计事件"),
                "source": "audit",
            }
        )
    return items


def _build_message_activity_items(user_id: str) -> list[dict]:
    items: list[dict] = []
    for message in _load_recent_conversation_messages(user_id):
        role = str(message.get("role") or "user")
        title = "系统回复" if role == "assistant" else "用户消息"
        content = str(message.get("content") or "").strip()
        snippet = content[:60] + ("..." if len(content) > 60 else "")
        items.append(
            {
                "id": f"message-{message['id']}",
                "timestamp": str(message.get("created_at") or ""),
                "type": "info" if role == "assistant" else "success",
                "title": title,
                "description": snippet or "记录了一条会话消息",
                "source": "conversation",
            }
        )
    return items


def _append_user_audit_log(*, action: str, user: dict, details: str, status_text: str = "success") -> None:
    log_payload = {
        "id": f"audit-user-{uuid4().hex}",
        "timestamp": store.now_string(),
        "action": action,
        "user": str(user.get("email") or user.get("id") or "system"),
        "resource": "用户管理",
        "status": status_text,
        "ip": "-",
        "details": details,
    }
    store.audit_logs.insert(0, store.clone(log_payload))
    persistence_service.append_audit_log(log=log_payload)


def _user_matches_search(user: dict, search: str) -> bool:
    keyword = search.strip().lower()
    if not keyword:
        return True

    if keyword in str(user.get("id") or "").lower():
        return True
    if keyword in str(user.get("name") or "").lower():
        return True
    if keyword in str(user.get("email") or "").lower():
        return True

    profile = _read_user_profile(str(user.get("id") or ""))
    if profile is None:
        return False

    for channel in profile.get("source_channels") or []:
        if keyword in str(channel).lower():
            return True

    for account in profile.get("platform_accounts") or profile.get("platformAccounts") or []:
        if not isinstance(account, dict):
            continue
        platform = str(account.get("platform") or "").lower()
        account_id = str(account.get("account_id") or account.get("accountId") or "").lower()
        if keyword in platform or keyword in account_id:
            return True

    return False


def _normalize_user_list_filter(value: str | None) -> str | None:
    normalized = str(value or "").strip().lower()
    if not normalized or normalized == "all":
        return None
    return normalized


def list_users(
    search: str | None = None,
    *,
    role_filter: str | None = None,
    status_filter: str | None = None,
) -> dict:
    items = persistence_service.list_users(search=None)
    if items is None:
        if getattr(persistence_service, "enabled", False):
            items = []
        else:
            items = store.clone(store.users)

    normalized_role_filter = _normalize_user_list_filter(role_filter)
    if normalized_role_filter is not None:
        items = [
            user
            for user in items
            if str(user.get("role") or "").strip().lower() == normalized_role_filter
        ]

    normalized_status_filter = _normalize_user_list_filter(status_filter)
    if normalized_status_filter is not None:
        items = [
            user
            for user in items
            if str(user.get("status") or "").strip().lower() == normalized_status_filter
        ]

    if search:
        items = [user for user in items if _user_matches_search(user, search)]
    return {"items": items, "total": len(items)}


def export_users_csv(
    *,
    search: str | None = None,
    role_filter: str | None = None,
    status_filter: str | None = None,
) -> str:
    listed = list_users(
        search=search,
        role_filter=role_filter,
        status_filter=status_filter,
    )
    buffer = StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(USER_EXPORT_HEADERS.values())

    for item in listed["items"]:
        profile = get_user_profile(str(item.get("id") or ""))
        platform_accounts = [
            f"{str(account.get('platform') or '').strip()}:{str(account.get('account_id') or account.get('accountId') or '').strip()}"
            for account in profile.get("platform_accounts") or profile.get("platformAccounts") or []
            if isinstance(account, dict)
            and str(account.get("platform") or "").strip()
            and str(account.get("account_id") or account.get("accountId") or "").strip()
        ]
        writer.writerow(
            [
                str(item.get("id") or ""),
                str(item.get("name") or ""),
                str(item.get("email") or ""),
                str(item.get("role") or ""),
                str(item.get("status") or ""),
                str(item.get("last_login") or ""),
                str(item.get("total_interactions") or 0),
                str(item.get("created_at") or ""),
                " | ".join(str(tag).strip() for tag in profile.get("tags") or [] if str(tag).strip()),
                str(profile.get("preferred_language") or ""),
                " | ".join(
                    str(channel).strip()
                    for channel in profile.get("source_channels") or []
                    if str(channel).strip()
                ),
                " | ".join(platform_accounts),
                str(profile.get("notes") or ""),
            ]
        )

    return "\ufeff" + buffer.getvalue()


def get_user_profile(user_id: str) -> dict:
    user, user_from_database = _read_user_with_source(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    profile = persistence_service.get_user_profile(user_id)
    if profile:
        return _normalize_user_profile(profile, user=user)

    if not user_from_database:
        runtime_profile = store.user_profiles.get(user_id)
        if runtime_profile:
            return _normalize_user_profile(store.clone(runtime_profile), user=user)

    fallback = {
        **user,
        "tags": ["未分组"],
        "notes": "暂无额外备注。",
        "preferred_language": "zh",
        "source_channels": ["dingtalk"],
        "platform_accounts": [],
    }
    return _normalize_user_profile(store.clone(fallback), user=user)


def get_user_activity(user_id: str) -> dict:
    profile = get_user_profile(user_id)
    items = _build_profile_activity_items(user_id, profile)
    items.extend(_build_audit_activity_items(user_id, profile))
    items.extend(_build_message_activity_items(user_id))
    items.sort(key=lambda item: _parse_activity_timestamp(str(item.get("timestamp") or "")), reverse=True)
    return {"items": items, "total": len(items)}


def update_user_profile(
    user_id: str,
    *,
    tags: list[str],
    notes: str,
    preferred_language: str,
) -> dict:
    user = _find_user_mutable(user_id)
    profile = _ensure_user_profile_for_update(user_id, user=user)
    profile.update(
        {
            "id": str(user.get("id") or ""),
            "name": str(user.get("name") or ""),
            "email": str(user.get("email") or ""),
            "role": str(user.get("role") or "viewer"),
            "status": str(user.get("status") or "active"),
            "last_login": str(user.get("last_login") or ""),
            "total_interactions": int(user.get("total_interactions") or 0),
            "created_at": str(user.get("created_at") or ""),
            "tags": _normalize_profile_tags(tags),
            "notes": str(notes or "").strip() or "暂无额外备注。",
            "preferred_language": _normalize_preferred_language(preferred_language),
        }
    )
    normalized_profile = _normalize_user_profile(profile, user=user)
    profile.clear()
    profile.update(normalized_profile)
    persistence_service.persist_user_state(user=user, profile=profile)
    _append_user_audit_log(
        action="画像更新",
        user=profile,
        details="用户画像已更新，标签、备注和语言偏好已同步。",
    )
    return {"ok": True, "message": "User profile updated", "user": store.clone(profile)}


def _normalize_binding_identifiers(*, platform: str, account_id: str) -> tuple[str, str]:
    normalized_platform = str(platform or "").strip().lower()
    normalized_account_id = str(account_id or "").strip()
    if not normalized_platform:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="platform is required",
        )
    if not normalized_account_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="account_id is required",
        )
    return normalized_platform, normalized_account_id


def _resolve_profile_id(profile: dict, *, fallback_user_id: str | None = None) -> str:
    resolved = (
        str(profile.get("id") or "").strip()
        or str(profile.get("user_id") or "").strip()
        or str(fallback_user_id or "").strip()
    )
    return resolved


def _find_profile_owner_by_platform_account(
    *,
    platform: str,
    account_id: str,
) -> str | None:
    find_profile = getattr(persistence_service, "find_user_profile_by_platform_account", None)
    if callable(find_profile):
        profile = find_profile(platform=platform, account_id=account_id)
        if isinstance(profile, dict):
            profile_id = _resolve_profile_id(profile)
            if profile_id:
                return profile_id

    if getattr(persistence_service, "enabled", False):
        return None

    for user_id, profile in store.user_profiles.items():
        accounts = _normalize_platform_accounts(profile if isinstance(profile, dict) else {})
        for account in accounts:
            if (
                str(account.get("platform") or "").strip().lower() == platform
                and str(account.get("account_id") or "").strip() == account_id
            ):
                resolved_profile_id = _resolve_profile_id(
                    profile if isinstance(profile, dict) else {},
                    fallback_user_id=str(user_id),
                )
                return resolved_profile_id or str(user_id)
    return None


def bind_user_platform_account(
    user_id: str,
    *,
    platform: str,
    account_id: str,
    confidence: float | None = None,
    source: str | None = None,
) -> dict:
    user = _find_user_mutable(user_id)
    profile = _ensure_user_profile_for_update(user_id, user=user)
    normalized_platform, normalized_account_id = _normalize_binding_identifiers(
        platform=platform,
        account_id=account_id,
    )
    existing_owner = _find_profile_owner_by_platform_account(
        platform=normalized_platform,
        account_id=normalized_account_id,
    )
    if existing_owner and existing_owner != str(user_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Platform account already bound to user {existing_owner}",
        )

    accounts = _normalize_platform_accounts(profile)
    binding = {"platform": normalized_platform, "account_id": normalized_account_id}
    if binding not in accounts:
        accounts.append(binding)

    channels = [
        str(channel).strip().lower()
        for channel in (profile.get("source_channels") or profile.get("sourceChannels") or [])
        if str(channel).strip()
    ]
    if normalized_platform not in channels:
        channels.append(normalized_platform)

    mapping_source = _normalize_mapping_source(source, status_text="manually_verified")
    profile.update(
        {
            "platform_accounts": accounts,
            "source_channels": channels,
            "identity_mapping_status": "manually_verified",
            "identity_mapping_source": mapping_source,
            "identity_mapping_confidence": _normalize_mapping_confidence(
                confidence,
                status_text="manually_verified",
            ),
            "last_identity_sync_at": _now_iso(),
        }
    )
    normalized_profile = _normalize_user_profile(profile, user=user)
    profile.clear()
    profile.update(normalized_profile)
    persistence_service.persist_user_state(user=user, profile=profile)
    _append_user_audit_log(
        action="账号绑定",
        user=profile,
        details=f"手动绑定 {normalized_platform} 账号 {normalized_account_id}",
    )
    return {"ok": True, "message": "User platform account bound", "user": store.clone(profile)}


def unbind_user_platform_account(
    user_id: str,
    *,
    platform: str,
    account_id: str,
) -> dict:
    user = _find_user_mutable(user_id)
    profile = _ensure_user_profile_for_update(user_id, user=user)
    normalized_platform, normalized_account_id = _normalize_binding_identifiers(
        platform=platform,
        account_id=account_id,
    )
    accounts = _normalize_platform_accounts(profile)
    filtered_accounts = [
        account
        for account in accounts
        if not (
            str(account.get("platform") or "").strip().lower() == normalized_platform
            and str(account.get("account_id") or "").strip() == normalized_account_id
        )
    ]
    if len(filtered_accounts) == len(accounts):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform account not found")

    channels = [
        str(channel).strip().lower()
        for channel in (profile.get("source_channels") or profile.get("sourceChannels") or [])
        if str(channel).strip()
    ]
    channel_has_remaining_account = any(
        str(account.get("platform") or "").strip().lower() == normalized_platform
        for account in filtered_accounts
    )
    if not channel_has_remaining_account:
        channels = [channel for channel in channels if channel != normalized_platform]

    mapping_status = "manually_verified" if filtered_accounts else "unmapped"
    profile.update(
        {
            "platform_accounts": filtered_accounts,
            "source_channels": channels,
            "identity_mapping_status": mapping_status,
            "identity_mapping_source": "manual_override" if filtered_accounts else "unknown",
            "identity_mapping_confidence": _normalize_mapping_confidence(
                1.0 if filtered_accounts else 0.0,
                status_text=mapping_status,
            ),
            "last_identity_sync_at": _now_iso(),
        }
    )
    normalized_profile = _normalize_user_profile(profile, user=user)
    profile.clear()
    profile.update(normalized_profile)
    persistence_service.persist_user_state(user=user, profile=profile)
    _append_user_audit_log(
        action="账号解绑",
        user=profile,
        details=f"手动解绑 {normalized_platform} 账号 {normalized_account_id}",
        status_text="warning",
    )
    return {"ok": True, "message": "User platform account unbound", "user": store.clone(profile)}


def update_user_role(user_id: str, role: str) -> dict:
    user = _find_user_mutable(user_id)
    previous_role = user["role"]
    user["role"] = role
    profile = _ensure_user_profile_for_update(user_id, user=user)
    if profile:
        profile["role"] = role
    persistence_service.persist_user_state(user=user, profile=profile)
    _append_user_audit_log(
        action="角色变更",
        user=profile or user,
        details=f"用户角色已从 {previous_role} 更新为 {role}",
    )
    return {"ok": True, "message": "User role updated", "user": store.clone(profile or user)}


def block_user(user_id: str) -> dict:
    user = _find_user_mutable(user_id)
    user["status"] = "suspended"
    profile = _ensure_user_profile_for_update(user_id, user=user)
    if profile:
        profile["status"] = "suspended"
    persistence_service.persist_user_state(user=user, profile=profile)
    _append_user_audit_log(
        action="账户停用",
        user=profile or user,
        details="账户已被手动停用，等待后续解封或复核",
        status_text="warning",
    )
    return {"ok": True, "message": "User blocked", "user": store.clone(profile or user)}
