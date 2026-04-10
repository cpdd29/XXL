from __future__ import annotations

import base64
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import hmac
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient


BACKEND_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import get_settings
from app.core.nats_event_bus import reset_nats_event_bus_state
from app.services.memory_service import reset_memory_store
from app.services.message_ingestion_service import reset_message_ingestion_state
from app.services.security_gateway_service import reset_security_gateway_state
from app.services.store import store
from app.services.internal_event_delivery_poller_service import reset_internal_event_delivery_poller_state
from app.services.workflow_dispatch_poller_service import reset_workflow_dispatch_poller_state
from app.services.workflow_realtime_service import reset_workflow_realtime_state
from app.services.workflow_recovery_service import reset_workflow_recovery_state
from app.services.workflow_scheduler_service import reset_workflow_scheduler_state
from app.services.webhook_guard_service import reset_webhook_guard_state
from app.services.workflow_service import reset_internal_event_delivery_state


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _encode_jwt(payload: dict[str, object], secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    header_segment = _base64url_encode(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    payload_segment = _base64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signing_input = f"{header_segment}.{payload_segment}".encode("utf-8")
    signature_segment = _base64url_encode(
        hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    )
    return f"{header_segment}.{payload_segment}.{signature_segment}"


def _upsert_runtime_user(user: dict[str, object]) -> None:
    for index, item in enumerate(store.users):
        if item["id"] == user["id"]:
            store.users[index] = deepcopy(user)
            return
    store.users.append(deepcopy(user))


def _extract_path(url: str) -> str:
    parsed = urlsplit(url)
    return parsed.path or str(url)


def _normalize_headers(headers: dict | None) -> dict[str, str]:
    if headers is None:
        return {}
    return {str(key): str(value) for key, value in dict(headers).items()}


def _should_inject_auth(path: str, headers: dict[str, str]) -> bool:
    if headers.get("x-test-no-auth") == "1":
        return False
    if "Authorization" in headers or "authorization" in headers:
        return False
    if not path.startswith("/api/"):
        return False
    if path.startswith("/api/auth"):
        return False
    if path == "/api/messages/ingest":
        return False
    if path.startswith("/api/webhooks"):
        return False
    return True


@pytest.fixture(autouse=True)
def reset_runtime_state() -> None:
    snapshot = deepcopy(store.__dict__)
    reset_nats_event_bus_state()
    reset_internal_event_delivery_poller_state()
    reset_workflow_dispatch_poller_state()
    reset_workflow_realtime_state()
    reset_workflow_recovery_state()
    reset_workflow_scheduler_state()
    reset_internal_event_delivery_state()
    reset_memory_store()
    reset_message_ingestion_state()
    reset_security_gateway_state()
    reset_webhook_guard_state()
    yield
    store.__dict__.clear()
    store.__dict__.update(deepcopy(snapshot))
    reset_nats_event_bus_state()
    reset_internal_event_delivery_poller_state()
    reset_workflow_dispatch_poller_state()
    reset_workflow_realtime_state()
    reset_workflow_recovery_state()
    reset_workflow_scheduler_state()
    reset_internal_event_delivery_state()
    reset_memory_store()
    reset_message_ingestion_state()
    reset_security_gateway_state()
    reset_webhook_guard_state()


@pytest.fixture
def access_token_factory():
    def factory(
        *,
        role: str = "admin",
        user_id: str | None = None,
        email: str | None = None,
        status: str = "active",
    ) -> str:
        settings = get_settings()
        resolved_user_id = user_id or f"test-{role}-user"
        resolved_email = email or f"{resolved_user_id}@example.test"
        _upsert_runtime_user(
            {
                "id": resolved_user_id,
                "name": f"Test {role.title()}",
                "email": resolved_email,
                "role": role,
                "status": status,
                "last_login": "",
                "total_interactions": 0,
                "created_at": "2026-04-04",
            }
        )
        now = int(datetime.now(UTC).timestamp())
        return _encode_jwt(
            {
                "sub": resolved_user_id,
                "email": resolved_email,
                "role": role,
                "iat": now,
                "type": "access",
                "exp": now + settings.auth_access_token_ttl_seconds,
            },
            settings.auth_jwt_secret,
        )

    return factory


@pytest.fixture
def auth_headers_factory(access_token_factory):
    def factory(
        *,
        role: str = "admin",
        user_id: str | None = None,
        email: str | None = None,
        status: str = "active",
    ) -> dict[str, str]:
        token = access_token_factory(role=role, user_id=user_id, email=email, status=status)
        return {"Authorization": f"Bearer {token}"}

    return factory


@pytest.fixture
def auth_headers(auth_headers_factory) -> dict[str, str]:
    return auth_headers_factory()


@pytest.fixture
def viewer_auth_headers(auth_headers_factory) -> dict[str, str]:
    return auth_headers_factory(role="viewer")


@pytest.fixture
def auth_token(access_token_factory) -> str:
    return access_token_factory()


@pytest.fixture(autouse=True)
def inject_control_plane_auth(monkeypatch: pytest.MonkeyPatch, auth_headers: dict[str, str]) -> None:
    original_request = TestClient.request
    original_websocket_connect = TestClient.websocket_connect

    def request_with_auth(self, method, url, *args, **kwargs):
        headers = _normalize_headers(kwargs.get("headers"))
        if _should_inject_auth(_extract_path(str(url)), headers):
            headers = {**headers, **auth_headers}
        headers.pop("x-test-no-auth", None)
        kwargs["headers"] = headers
        return original_request(self, method, url, *args, **kwargs)

    def websocket_connect_with_auth(self, url, *args, **kwargs):
        headers = _normalize_headers(kwargs.get("headers"))
        if _should_inject_auth(_extract_path(str(url)), headers):
            headers = {**headers, **auth_headers}
        headers.pop("x-test-no-auth", None)
        kwargs["headers"] = headers
        return original_websocket_connect(self, url, *args, **kwargs)

    monkeypatch.setattr(TestClient, "request", request_with_auth)
    monkeypatch.setattr(TestClient, "websocket_connect", websocket_connect_with_auth)
