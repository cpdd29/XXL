from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, WebSocket, WebSocketException, status
from starlette.requests import HTTPConnection

from app.services.auth_service import authenticate_access_token


ROLE_PERMISSIONS: dict[str, set[str]] = {
    "super_admin": {"*"},
    "admin": {"*"},
    "operator": {
        "dashboard:read",
        "logs:read",
        "collaboration:read",
        "tasks:read",
        "tasks:write",
        "agents:read",
        "agents:reload",
        "agents:heartbeat",
        "users:read",
        "users:write",
        "users:block",
        "workflows:read",
        "workflows:write",
        "security:read",
        "security:manage",
        "security:rules:write",
        "security:penalties:read",
        "security:penalties:release",
        "memory:read",
        "memory:write",
        "settings:read",
        "settings:write",
    },
    "power_user": {
        "dashboard:read",
        "collaboration:read",
        "tasks:read",
        "tasks:write",
        "agents:read",
        "agents:heartbeat",
        "workflows:read",
        "workflows:write",
        "memory:read",
        "memory:write",
        "settings:read",
    },
    "viewer": {
        "dashboard:read",
        "logs:read",
        "collaboration:read",
        "tasks:read",
        "agents:read",
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
    if permission.startswith("security:") and "security:manage" in allowed:
        return True
    return False


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
