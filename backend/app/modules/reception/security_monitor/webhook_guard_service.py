from __future__ import annotations

from collections import defaultdict, deque
from datetime import UTC, datetime
import json
from threading import Lock
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, Request, status

from app.config import get_settings
from app.platform.messaging.redis_client import redis_provider
from app.platform.persistence.persistence_service import persistence_service
from app.modules.reception.security_monitor.security_gateway_service import CONTENT_POLICY_RULES, SecurityGatewayService
from app.platform.persistence.runtime_store import store
from app.platform.observability.trace_exporter_service import trace_exporter_service


_IN_MEMORY_RATE_BUCKETS: dict[str, deque[float]] = defaultdict(deque)
_RATE_LIMIT_LOCK = Lock()
MAX_SANITIZE_DEPTH = 8
MAX_SANITIZE_LIST_ITEMS = 100
MAX_SANITIZE_DICT_ITEMS = 160
MAX_SANITIZE_STRING_LENGTH = 4000


def _now_ts() -> float:
    return datetime.now(UTC).timestamp()


def _client_identifier(request: Request) -> str:
    forwarded_for = str(request.headers.get("x-forwarded-for") or "").strip()
    if forwarded_for:
        return forwarded_for.split(",", maxsplit=1)[0].strip() or "unknown"
    if request.client is not None and request.client.host:
        return str(request.client.host)
    return "unknown"


def _rate_limit_settings() -> tuple[int, int]:
    settings = get_settings()
    max_requests = int(getattr(settings, "webhook_rate_limit_max_requests", 120) or 0)
    window_seconds = int(getattr(settings, "webhook_rate_limit_window_seconds", 60) or 0)
    return max_requests, window_seconds


def _masked_client_identifier(client_identifier: str) -> str:
    normalized = str(client_identifier or "").strip()
    if not normalized:
        return "unknown"
    segments = normalized.split(".")
    if len(segments) == 4 and all(segment.isdigit() for segment in segments):
        return ".".join([segments[0], segments[1], segments[2], "x"])
    return normalized


def _append_webhook_rate_limit_audit(
    *,
    route_key: str,
    client_identifier: str,
    max_requests: int,
    window_seconds: int,
    current_count: int,
) -> None:
    masked_client = _masked_client_identifier(client_identifier)
    trace_id = f"trace-webhook-{uuid4().hex[:12]}"
    metadata = {
        "trace": {
            "trace_id": trace_id,
            "span_id": uuid4().hex[:16],
            "parent_span_id": None,
            "operation": "webhook_rate_limit",
            "layer": "webhook_guard",
            "outcome": "blocked",
            "status_code": status.HTTP_429_TOO_MANY_REQUESTS,
            "resource": f"webhook:{route_key}",
            "client": masked_client,
            "ended_at": datetime.now(UTC).isoformat(),
        },
        "webhook_guard": {
            "route_key": route_key,
            "client_identifier": masked_client,
            "max_requests": max_requests,
            "window_seconds": window_seconds,
            "current_count": current_count,
        },
    }
    payload = {
        "id": f"audit-webhook-rate-limit-{uuid4().hex[:10]}",
        "timestamp": store.now_string(),
        "action": "Webhook 限流拦截",
        "user": masked_client,
        "resource": f"webhook:{route_key}",
        "status": "warning",
        "ip": masked_client,
        "details": (
            "Webhook rate limit exceeded"
            f" (route={route_key}, count={current_count}, limit={max_requests}, window={window_seconds}s)"
        ),
        "metadata": metadata,
    }
    store.audit_logs.insert(0, store.clone(payload))
    del store.audit_logs[200:]
    persistence_service.append_audit_log(log=payload)
    trace_exporter_service.export_audit_event(payload)


def _append_webhook_payload_size_audit(
    *,
    route_key: str,
    client_identifier: str,
    payload_size_bytes: int,
    limit_bytes: int,
) -> None:
    masked_client = _masked_client_identifier(client_identifier)
    trace_id = f"trace-webhook-{uuid4().hex[:12]}"
    metadata = {
        "trace": {
            "trace_id": trace_id,
            "span_id": uuid4().hex[:16],
            "parent_span_id": None,
            "operation": "webhook_payload_size_check",
            "layer": "webhook_guard",
            "outcome": "blocked",
            "status_code": status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "resource": f"webhook:{route_key}",
            "client": masked_client,
            "ended_at": datetime.now(UTC).isoformat(),
        },
        "webhook_guard": {
            "route_key": route_key,
            "client_identifier": masked_client,
            "payload_size_bytes": int(payload_size_bytes),
            "payload_limit_bytes": int(limit_bytes),
        },
    }
    payload = {
        "id": f"audit-webhook-payload-size-{uuid4().hex[:10]}",
        "timestamp": store.now_string(),
        "action": "Webhook 载荷超限拦截",
        "user": masked_client,
        "resource": f"webhook:{route_key}",
        "status": "warning",
        "ip": masked_client,
        "details": (
            "Webhook payload too large"
            f" (route={route_key}, size={payload_size_bytes}, limit={limit_bytes})"
        ),
        "metadata": metadata,
    }
    store.audit_logs.insert(0, store.clone(payload))
    del store.audit_logs[200:]
    persistence_service.append_audit_log(log=payload)
    trace_exporter_service.export_audit_event(payload)


def _payload_size_limit() -> int:
    settings = get_settings()
    try:
        normalized = int(getattr(settings, "webhook_max_payload_bytes", 0) or 0)
    except (TypeError, ValueError):
        return 0
    return max(normalized, 0)


def _payload_size_bytes(payload: Any) -> int:
    try:
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
    except Exception:
        serialized = str(payload)
    return len(serialized.encode("utf-8", errors="ignore"))


def enforce_webhook_payload_size(
    *,
    request: Request,
    route_key: str,
    payload: Any,
) -> None:
    limit_bytes = _payload_size_limit()
    if limit_bytes <= 0:
        return

    payload_size = _payload_size_bytes(payload)
    if payload_size <= limit_bytes:
        return

    client_key = _client_identifier(request)
    _append_webhook_payload_size_audit(
        route_key=route_key,
        client_identifier=client_key,
        payload_size_bytes=payload_size,
        limit_bytes=limit_bytes,
    )
    raise HTTPException(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        detail="Webhook payload too large",
    )


def enforce_webhook_rate_limit(*, request: Request, route_key: str) -> None:
    max_requests, window_seconds = _rate_limit_settings()
    if max_requests <= 0 or window_seconds <= 0:
        return

    client_key = _client_identifier(request)
    bucket_key = f"webhook:{route_key}:{client_key}"
    now_ts = _now_ts()
    window_start = now_ts - float(window_seconds)

    client = redis_provider.get_client()
    if client is not None:
        try:
            client.zremrangebyscore(bucket_key, 0, window_start)
            current_count = int(client.zcard(bucket_key) or 0)
            if current_count >= max_requests:
                _append_webhook_rate_limit_audit(
                    route_key=route_key,
                    client_identifier=client_key,
                    max_requests=max_requests,
                    window_seconds=window_seconds,
                    current_count=current_count,
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Webhook rate limit exceeded",
                )
            client.zadd(bucket_key, {f"{now_ts}:{uuid4().hex[:8]}": now_ts})
            client.expire(bucket_key, window_seconds)
            return
        except HTTPException:
            raise
        except Exception:
            pass

    with _RATE_LIMIT_LOCK:
        bucket = _IN_MEMORY_RATE_BUCKETS[bucket_key]
        while bucket and bucket[0] <= window_start:
            bucket.popleft()
        if len(bucket) >= max_requests:
            _append_webhook_rate_limit_audit(
                route_key=route_key,
                client_identifier=client_key,
                max_requests=max_requests,
                window_seconds=window_seconds,
                current_count=len(bucket),
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Webhook rate limit exceeded",
            )
        bucket.append(now_ts)


def sanitize_webhook_payload(payload: Any, *, _depth: int = 0) -> Any:
    if _depth > MAX_SANITIZE_DEPTH:
        return "[TRUNCATED_DEPTH]"
    if isinstance(payload, str):
        rewritten = payload[:MAX_SANITIZE_STRING_LENGTH]
        for rule in CONTENT_POLICY_RULES:
            rewritten, _ = SecurityGatewayService._apply_content_rule(rewritten, rule)
        if len(payload) > MAX_SANITIZE_STRING_LENGTH:
            rewritten = f"{rewritten}[TRUNCATED]"
        return rewritten
    if isinstance(payload, list):
        items = [
            sanitize_webhook_payload(item, _depth=_depth + 1)
            for item in payload[:MAX_SANITIZE_LIST_ITEMS]
        ]
        if len(payload) > MAX_SANITIZE_LIST_ITEMS:
            items.append("[TRUNCATED_LIST_ITEMS]")
        return items
    if isinstance(payload, dict):
        sanitized: dict[str, Any] = {}
        for index, (key, value) in enumerate(payload.items()):
            if index >= MAX_SANITIZE_DICT_ITEMS:
                sanitized["__truncated__"] = "[TRUNCATED_DICT_ITEMS]"
                break
            sanitized[str(key)] = sanitize_webhook_payload(value, _depth=_depth + 1)
        return sanitized
    return payload


def reset_webhook_guard_state() -> None:
    with _RATE_LIMIT_LOCK:
        _IN_MEMORY_RATE_BUCKETS.clear()
    client = redis_provider.get_client()
    if client is None:
        return
    try:
        keys = list(client.scan_iter(match="webhook:*"))
        if keys:
            client.delete(*keys)
    except Exception:
        pass
