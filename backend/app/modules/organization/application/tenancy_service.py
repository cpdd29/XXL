from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import HTTPException, status

from app.config import get_settings
from app.platform.persistence.runtime_store import store


ROOT_SCOPE_ROLES = {"admin", "super_admin", "operator"}
DEFAULT_TENANT_ID = "default"
DEFAULT_PROJECT_ID = "default"


def _normalize_text(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def default_scope() -> dict[str, str]:
    return {
        "tenant_id": DEFAULT_TENANT_ID,
        "project_id": DEFAULT_PROJECT_ID,
        "environment": str(get_settings().environment or "development").strip() or "development",
    }


def current_user_scope(current_user: dict[str, Any]) -> dict[str, str]:
    resolved = default_scope()
    user_id = str(current_user.get("id") or "").strip()
    profile = store.user_profiles.get(user_id) if user_id else None
    if isinstance(profile, dict):
        for key in ("tenant_id", "project_id", "environment"):
            value = _normalize_text(profile.get(key) or profile.get(key.replace("_id", "Id")))
            if value is not None:
                resolved[key] = value
    return resolved


def resolve_scope(
    *,
    current_user: dict[str, Any],
    tenant_id: str | None = None,
    project_id: str | None = None,
    environment: str | None = None,
) -> dict[str, str]:
    scope = current_user_scope(current_user)
    role = str(current_user.get("role") or "").strip().lower()
    requested = {
        "tenant_id": _normalize_text(tenant_id),
        "project_id": _normalize_text(project_id),
        "environment": _normalize_text(environment),
    }
    if role in ROOT_SCOPE_ROLES:
        for key, value in requested.items():
            if value is not None:
                scope[key] = value
        return scope
    for key, value in requested.items():
        if value is not None and value != scope[key]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Cross-scope access denied for {key}",
            )
    return scope


def entity_scope(entity: dict[str, Any] | None) -> dict[str, str]:
    scope = default_scope()
    payload = entity if isinstance(entity, dict) else {}
    for key in ("tenant_id", "project_id", "environment"):
        direct = _normalize_text(payload.get(key) or payload.get(key.replace("_id", "Id")))
        if direct is not None:
            scope[key] = direct
    dispatch_context = payload.get("dispatch_context") if isinstance(payload.get("dispatch_context"), dict) else {}
    nested_scope = dispatch_context.get("scope") if isinstance(dispatch_context.get("scope"), dict) else {}
    for key in ("tenant_id", "project_id", "environment"):
        nested = _normalize_text(nested_scope.get(key) or nested_scope.get(key.replace("_id", "Id")))
        if nested is not None:
            scope[key] = nested
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    metadata_scope = metadata.get("scope") if isinstance(metadata.get("scope"), dict) else {}
    for key in ("tenant_id", "project_id", "environment"):
        nested = _normalize_text(metadata_scope.get(key) or metadata_scope.get(key.replace("_id", "Id")))
        if nested is not None:
            scope[key] = nested
    return scope


def attach_scope(entity: dict[str, Any] | None, *, scope: dict[str, str] | None = None) -> dict[str, Any]:
    payload = deepcopy(entity) if isinstance(entity, dict) else {}
    resolved = scope or entity_scope(payload)
    payload["tenant_id"] = resolved["tenant_id"]
    payload["project_id"] = resolved["project_id"]
    payload["environment"] = resolved["environment"]
    return payload


def matches_scope(entity: dict[str, Any] | None, scope: dict[str, str]) -> bool:
    resolved = entity_scope(entity)
    return (
        resolved["tenant_id"] == scope["tenant_id"]
        and resolved["project_id"] == scope["project_id"]
        and resolved["environment"] == scope["environment"]
    )
