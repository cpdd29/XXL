from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, WebSocket, WebSocketException, status
from starlette.requests import HTTPConnection

from app.services.auth_service import authenticate_access_token


ROLE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "super_admin": {
        "label": "超级管理员",
        "tier": "root",
        "description": "拥有主脑全部权限，可直接治理本地真源与安全策略。",
    },
    "admin": {
        "label": "管理员",
        "tier": "root",
        "description": "拥有主脑全部权限，可直接治理本地真源与安全策略。",
    },
    "operator": {
        "label": "运维员",
        "tier": "operations",
        "description": "负责主脑运维、审批放行、安全治理和外接能力治理。",
    },
    "power_user": {
        "label": "高级调度员",
        "tier": "dispatch",
        "description": "负责业务调度和任务推进，但不能改安全与高敏配置。",
    },
    "viewer": {
        "label": "只读观察员",
        "tier": "read_only",
        "description": "只能查看主脑状态、审计和运行结果，不能修改真源。",
    },
    "user": {
        "label": "普通用户",
        "tier": "limited",
        "description": "只能访问与自身任务相关的基础能力。",
    },
    "blocked": {
        "label": "已封禁用户",
        "tier": "blocked",
        "description": "已被封禁，无法继续操作控制面。",
    },
}

PERMISSION_GROUPS: dict[str, dict[str, Any]] = {
    "read_only": {
        "label": "只读",
        "permissions": {
            "approvals:read",
            "alerts:read",
            "dashboard:read",
            "external:read",
            "events:read",
            "logs:read",
            "audit:read",
            "collaboration:read",
            "tasks:read",
            "agents:read",
            "tool_sources:read",
            "users:read",
            "workflows:read",
            "security:read",
            "security:penalties:read",
            "memory:read",
            "settings:read",
        },
    },
    "dispatch": {
        "label": "调度",
        "permissions": {
            "approvals:write",
            "alerts:write",
            "events:write",
            "external:write",
            "tasks:write",
            "agents:heartbeat",
            "workflows:run:create",
            "workflows:run:tick",
            "workflows:handoff",
            "memory:write",
        },
    },
    "config": {
        "label": "配置",
        "permissions": {
            "agents:reload",
            "tool_sources:scan",
            "users:profile:write",
            "users:identity:bind",
            "users:role:write",
            "settings:general:write",
            "settings:agent-api:write",
            "settings:channel-integrations:write",
            "workflows:definition:write",
            "workflows:trigger:internal",
            "workflows:delivery:retry",
            "workflows:delivery:replay",
        },
    },
    "security": {
        "label": "安全",
        "permissions": {
            "security:incidents:review",
            "security:penalties:manual:create",
            "security:penalties:release",
            "security:rules:write",
            "security:subscriptions:write",
            "settings:security-policy:write",
            "users:block",
        },
    },
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "super_admin": {"*"},
    "admin": {"*"},
    "operator": {
        "approvals:read",
        "approvals:write",
        "alerts:read",
        "alerts:write",
        "dashboard:read",
        "external:read",
        "events:read",
        "external:write",
        "events:write",
        "logs:read",
        "audit:read",
        "collaboration:read",
        "tasks:read",
        "tasks:write",
        "agents:read",
        "agents:reload",
        "agents:heartbeat",
        "tool_sources:read",
        "tool_sources:scan",
        "users:read",
        "users:write",
        "users:profile:write",
        "users:identity:bind",
        "users:role:write",
        "users:block",
        "workflows:read",
        "workflows:write",
        "workflows:definition:write",
        "workflows:run:create",
        "workflows:run:tick",
        "workflows:trigger:internal",
        "workflows:delivery:retry",
        "workflows:delivery:replay",
        "workflows:handoff",
        "security:read",
        "security:manage",
        "security:incidents:review",
        "security:rules:write",
        "security:penalties:read",
        "security:penalties:manual:create",
        "security:penalties:release",
        "security:subscriptions:write",
        "memory:read",
        "memory:write",
        "settings:read",
        "settings:write",
        "settings:general:write",
        "settings:security-policy:write",
        "settings:agent-api:write",
        "settings:channel-integrations:write",
    },
    "power_user": {
        "approvals:read",
        "alerts:read",
        "dashboard:read",
        "collaboration:read",
        "tasks:read",
        "tasks:write",
        "agents:read",
        "agents:heartbeat",
        "tool_sources:read",
        "workflows:read",
        "workflows:write",
        "workflows:run:create",
        "workflows:run:tick",
        "memory:read",
        "memory:write",
        "settings:read",
    },
    "viewer": {
        "approvals:read",
        "alerts:read",
        "dashboard:read",
        "external:read",
        "events:read",
        "logs:read",
        "audit:read",
        "collaboration:read",
        "tasks:read",
        "agents:read",
        "tool_sources:read",
        "users:read",
        "workflows:read",
        "security:read",
        "memory:read",
        "settings:read",
    },
    "user": {
        "tasks:read",
        "tasks:write",
        "memory:read",
        "memory:write",
    },
    "blocked": set(),
}


def _extract_bearer_token(value: str | None) -> str | None:
    if not value:
        return None
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer":
        return None
    normalized = token.strip()
    return normalized or None


def _extract_connection_token(connection: HTTPConnection | WebSocket) -> str | None:
    header_token = _extract_bearer_token(connection.headers.get("authorization"))
    if header_token is not None:
        return header_token

    for key in ("token", "access_token"):
        query_token = connection.query_params.get(key)
        if query_token:
            normalized = query_token.strip()
            if normalized:
                return normalized
    return None


def _has_permission(role: str, permission: str) -> bool:
    allowed = ROLE_PERMISSIONS.get(role, set())
    if "*" in allowed or permission in allowed:
        return True
    return False


def list_permissions_for_role(role: str) -> list[str]:
    allowed = ROLE_PERMISSIONS.get(role, set())
    if "*" in allowed:
        return ["*"]
    return sorted(allowed)


def get_role_summary(role: str) -> dict[str, Any]:
    summary = ROLE_DEFINITIONS.get(role, ROLE_DEFINITIONS["blocked"])
    return {
        "key": role,
        "label": summary["label"],
        "tier": summary["tier"],
        "description": summary["description"],
    }


def build_permission_groups(role: str) -> list[dict[str, Any]]:
    granted = set(list_permissions_for_role(role))
    if "*" in granted:
        return [
            {
                "key": key,
                "label": item["label"],
                "permissions": sorted(item["permissions"]),
            }
            for key, item in PERMISSION_GROUPS.items()
        ]

    groups: list[dict[str, Any]] = []
    for key, item in PERMISSION_GROUPS.items():
        matched_permissions = sorted(permission for permission in item["permissions"] if permission in granted)
        if not matched_permissions:
            continue
        groups.append(
            {
                "key": key,
                "label": item["label"],
                "permissions": matched_permissions,
            }
        )
    return groups


def require_authenticated_user(connection: HTTPConnection) -> dict[str, Any]:
    cached_user = getattr(connection.state, "current_user", None)
    if cached_user is not None:
        return cached_user

    token = _extract_connection_token(connection)
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    current_user = authenticate_access_token(token)
    connection.state.current_user = current_user
    return current_user


def require_permission(permission: str) -> Callable[[HTTPConnection], dict[str, Any]]:
    def dependency(connection: HTTPConnection) -> dict[str, Any]:
        current_user = getattr(connection.state, "current_user", None) or require_authenticated_user(
            connection
        )
        role = str(current_user.get("role") or "")
        if not _has_permission(role, permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
        return current_user

    return dependency


def authenticate_websocket(
    websocket: WebSocket,
    *,
    permission: str | None = None,
) -> dict[str, Any]:
    token = _extract_connection_token(websocket)
    if token is None:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Missing bearer token",
        )

    try:
        current_user = authenticate_access_token(token)
    except HTTPException as exc:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason=str(exc.detail),
        ) from exc

    role = str(current_user.get("role") or "")
    if permission is not None and not _has_permission(role, permission):
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Permission denied",
        )

    websocket.state.current_user = current_user
    return current_user
