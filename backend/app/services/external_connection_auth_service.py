from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import MutableMapping
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from fastapi import HTTPException, status

from app.config import EXTERNAL_CONNECTION_DEFAULT_SHARED_SECRET, get_settings


_NONCE_LOCK = Lock()
_SEEN_NONCES: MutableMapping[str, float] = {}


def reset_external_connection_auth_state() -> None:
    with _NONCE_LOCK:
        _SEEN_NONCES.clear()


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _parse_timestamp(value: str | None) -> datetime | None:
    normalized = _normalize_text(value)
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _signature_payload(timestamp: str, payload: dict[str, Any]) -> bytes:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{timestamp}.{body}".encode("utf-8")


def _ensure_shared_secret_is_safe(secret: str, *, environment: str) -> None:
    normalized_environment = _normalize_text(environment).lower()
    if normalized_environment in {"development", "dev", "test", "local"}:
        return
    normalized = _normalize_text(secret)
    if not normalized or hmac.compare_digest(normalized, EXTERNAL_CONNECTION_DEFAULT_SHARED_SECRET):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="External connection shared secret is not configured securely",
        )


def _consume_nonce_once(nonce: str, *, now_epoch: float, ttl_seconds: int) -> None:
    expire_before = now_epoch - float(ttl_seconds)
    with _NONCE_LOCK:
        expired_keys = [key for key, seen_at in _SEEN_NONCES.items() if seen_at <= expire_before]
        for key in expired_keys:
            _SEEN_NONCES.pop(key, None)
        if nonce in _SEEN_NONCES:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="External connection nonce replayed",
            )
        _SEEN_NONCES[nonce] = now_epoch


def verify_external_request(
    *,
    payload: dict[str, Any],
    token: str | None = None,
    timestamp: str | None = None,
    signature: str | None = None,
    nonce: str | None = None,
) -> None:
    settings = get_settings()
    secret = settings.external_connection_shared_secret
    _ensure_shared_secret_is_safe(secret, environment=settings.environment)
    normalized_token = _normalize_text(token)
    if normalized_token and hmac.compare_digest(normalized_token, secret):
        return

    normalized_signature = _normalize_text(signature).lower()
    normalized_nonce = _normalize_text(nonce)
    parsed_timestamp = _parse_timestamp(timestamp)
    if not normalized_signature or parsed_timestamp is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="External connection auth required")
    replay_nonce = normalized_nonce or f"sig:{normalized_signature}"

    age_seconds = abs((datetime.now(UTC) - parsed_timestamp).total_seconds())
    ttl_seconds = max(10, int(settings.external_connection_signature_ttl_seconds))
    if age_seconds > ttl_seconds:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="External connection signature expired")
    _consume_nonce_once(replay_nonce, now_epoch=datetime.now(UTC).timestamp(), ttl_seconds=ttl_seconds)

    expected = hmac.new(
        secret.encode("utf-8"),
        _signature_payload(parsed_timestamp.isoformat(), payload),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(normalized_signature, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="External connection signature invalid")
