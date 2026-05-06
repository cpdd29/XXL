from __future__ import annotations

from typing import Any


CAPABILITY_SCOPE_SHARED = "shared"
CAPABILITY_SCOPE_TENANT = "tenant"
CAPABILITY_SCOPES = {
    CAPABILITY_SCOPE_SHARED,
    CAPABILITY_SCOPE_TENANT,
}
_SHARED_SCOPE_ALIASES = {
    "",
    "shared",
    "common",
    "generic",
    "global",
    "public",
    "platform",
    "通用",
}
_TENANT_SCOPE_ALIASES = {
    "tenant",
    "private",
    "dedicated",
    "specialized",
    "specialised",
    "专用",
}


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_owner_tenant_id(value: Any) -> str | None:
    normalized = normalize_text(value)
    return normalized or None


def normalize_capability_scope(
    value: Any,
    *,
    owner_tenant_id: Any = None,
    default: str = CAPABILITY_SCOPE_SHARED,
) -> str:
    normalized = normalize_text(value).lower()
    if normalized in _TENANT_SCOPE_ALIASES:
        return CAPABILITY_SCOPE_TENANT
    if normalized in _SHARED_SCOPE_ALIASES:
        return CAPABILITY_SCOPE_SHARED
    if normalize_owner_tenant_id(owner_tenant_id):
        return CAPABILITY_SCOPE_TENANT
    return default if default in CAPABILITY_SCOPES else CAPABILITY_SCOPE_SHARED


def normalize_scope_fields(
    *,
    scope: Any,
    owner_tenant_id: Any,
    default_scope: str = CAPABILITY_SCOPE_SHARED,
) -> tuple[str, str | None]:
    normalized_owner = normalize_owner_tenant_id(owner_tenant_id)
    normalized_scope = normalize_capability_scope(
        scope,
        owner_tenant_id=normalized_owner,
        default=default_scope,
    )
    if normalized_scope == CAPABILITY_SCOPE_SHARED:
        return CAPABILITY_SCOPE_SHARED, None
    return CAPABILITY_SCOPE_TENANT, normalized_owner


def extract_scope_fields(
    payload: dict[str, Any] | None,
    *,
    default_scope: str = CAPABILITY_SCOPE_SHARED,
) -> tuple[str, str | None]:
    item = payload if isinstance(payload, dict) else {}
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    config_summary = item.get("config_summary") if isinstance(item.get("config_summary"), dict) else {}
    return normalize_scope_fields(
        scope=(
            item.get("scope")
            or item.get("capability_scope")
            or metadata.get("scope")
            or metadata.get("capability_scope")
            or config_summary.get("scope")
            or config_summary.get("capability_scope")
        ),
        owner_tenant_id=(
            item.get("owner_tenant_id")
            or item.get("ownerTenantId")
            or metadata.get("owner_tenant_id")
            or metadata.get("ownerTenantId")
            or config_summary.get("owner_tenant_id")
            or config_summary.get("ownerTenantId")
        ),
        default_scope=default_scope,
    )


def apply_scope_fields(
    payload: dict[str, Any] | None,
    *,
    scope: Any = None,
    owner_tenant_id: Any = None,
    default_scope: str = CAPABILITY_SCOPE_SHARED,
) -> dict[str, Any]:
    normalized = dict(payload or {})
    resolved_scope, resolved_owner_tenant_id = normalize_scope_fields(
        scope=scope if scope is not None else normalized.get("scope"),
        owner_tenant_id=(
            owner_tenant_id if owner_tenant_id is not None else normalized.get("owner_tenant_id")
        ),
        default_scope=default_scope,
    )
    normalized["scope"] = resolved_scope
    normalized["owner_tenant_id"] = resolved_owner_tenant_id
    return normalized


def capability_visible(
    payload: dict[str, Any] | None,
    *,
    tenant_id: str | None,
    include_all_tenants: bool = False,
) -> bool:
    if include_all_tenants:
        return True
    scope, owner_tenant_id = extract_scope_fields(payload)
    if scope == CAPABILITY_SCOPE_SHARED:
        return True
    if not tenant_id:
        return False
    return owner_tenant_id == tenant_id


def matches_scope_filter(payload: dict[str, Any] | None, scope_filter: str | None) -> bool:
    raw_filter = normalize_text(scope_filter).lower()
    if not raw_filter:
        return True
    normalized_filter = normalize_capability_scope(raw_filter)
    scope, _ = extract_scope_fields(payload)
    return scope == normalized_filter


def scope_priority(
    payload: dict[str, Any] | None,
    *,
    tenant_id: str | None,
) -> tuple[int, str, str]:
    scope, owner_tenant_id = extract_scope_fields(payload)
    if scope == CAPABILITY_SCOPE_TENANT and tenant_id and owner_tenant_id == tenant_id:
        return (0, owner_tenant_id or "", normalize_text(payload.get("id") if isinstance(payload, dict) else ""))
    if scope == CAPABILITY_SCOPE_SHARED:
        return (1, "", normalize_text(payload.get("id") if isinstance(payload, dict) else ""))
    return (2, owner_tenant_id or "", normalize_text(payload.get("id") if isinstance(payload, dict) else ""))


def select_scoped_candidate(
    items: list[dict[str, Any]],
    *,
    tenant_id: str | None,
    include_all_tenants: bool = False,
) -> dict[str, Any] | None:
    visible = [
        item
        for item in items
        if capability_visible(item, tenant_id=tenant_id, include_all_tenants=include_all_tenants)
    ]
    if not visible:
        return None
    visible.sort(key=lambda item: scope_priority(item, tenant_id=tenant_id))
    return visible[0]
