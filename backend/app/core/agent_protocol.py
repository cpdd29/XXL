from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


PROTOCOL_SPEC_VERSION = "agentbus.v1"
DEFAULT_MAX_ATTEMPTS = 3
PROTOCOL_CONTEXT_KEY = "protocol"
METADATA_KEYS = {
    "spec_version",
    "message_id",
    "message_type",
    "message_name",
    "request_id",
    "correlation_id",
    "causation_id",
    "idempotency_key",
    "attempt",
    "max_attempts",
    "emitted_at",
    "available_at",
    "deadline_at",
    "dead_letter",
    "dead_letter_reason",
    "source",
    "target",
    "payload",
    "protocol",
}


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_text(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _normalize_int(value: object, *, default: int, minimum: int = 1) -> int:
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        resolved = default
    return max(resolved, minimum)


def _normalize_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    return normalized in {"1", "true", "yes", "y", "on"}


def _context(source: dict | None) -> dict:
    if not isinstance(source, dict):
        return {}
    dispatch_context = source.get("dispatch_context")
    if isinstance(dispatch_context, dict):
        return dispatch_context
    return source


def protocol_from_dispatch_context(source: dict | None) -> dict[str, Any]:
    dispatch_context = _context(source)
    protocol = dispatch_context.get(PROTOCOL_CONTEXT_KEY)
    if not isinstance(protocol, dict):
        protocol = {}
    request_id = _normalize_text(protocol.get("request_id"))
    if request_id is None:
        request_id = (
            _normalize_text(dispatch_context.get("request_id"))
            or _normalize_text(dispatch_context.get("trace_id"))
            or _normalize_text(dispatch_context.get("message_id"))
        )
    correlation_id = _normalize_text(protocol.get("correlation_id")) or request_id
    raw_max_attempts = protocol.get("max_attempts")
    return {
        "spec_version": _normalize_text(protocol.get("spec_version")) or PROTOCOL_SPEC_VERSION,
        "message_id": _normalize_text(protocol.get("message_id")),
        "message_type": _normalize_text(protocol.get("message_type")),
        "message_name": _normalize_text(protocol.get("message_name")),
        "request_id": request_id,
        "correlation_id": correlation_id,
        "causation_id": _normalize_text(protocol.get("causation_id")),
        "idempotency_key": _normalize_text(protocol.get("idempotency_key")),
        "attempt": _normalize_int(protocol.get("attempt"), default=1),
        "max_attempts": (
            _normalize_int(raw_max_attempts, default=DEFAULT_MAX_ATTEMPTS)
            if raw_max_attempts not in (None, "")
            else None
        ),
        "emitted_at": _normalize_text(protocol.get("emitted_at")),
        "available_at": _normalize_text(protocol.get("available_at")),
        "deadline_at": _normalize_text(protocol.get("deadline_at")),
        "dead_letter": _normalize_bool(protocol.get("dead_letter")),
        "dead_letter_reason": _normalize_text(protocol.get("dead_letter_reason")),
        "source": deepcopy(protocol.get("source")) if isinstance(protocol.get("source"), dict) else None,
        "target": deepcopy(protocol.get("target")) if isinstance(protocol.get("target"), dict) else None,
        "last_error": _normalize_text(protocol.get("last_error")),
    }


def protocol_from_message(message: dict | None) -> dict[str, Any]:
    if not isinstance(message, dict):
        return protocol_from_dispatch_context({})
    nested_protocol = message.get("protocol")
    protocol = nested_protocol if isinstance(nested_protocol, dict) else {}
    return {
        "spec_version": _normalize_text(message.get("spec_version") or protocol.get("spec_version"))
        or PROTOCOL_SPEC_VERSION,
        "message_id": _normalize_text(message.get("message_id") or protocol.get("message_id")),
        "message_type": _normalize_text(message.get("message_type") or protocol.get("message_type")),
        "message_name": _normalize_text(message.get("message_name") or protocol.get("message_name")),
        "request_id": _normalize_text(message.get("request_id") or protocol.get("request_id")),
        "correlation_id": _normalize_text(
            message.get("correlation_id") or protocol.get("correlation_id")
        ),
        "causation_id": _normalize_text(message.get("causation_id") or protocol.get("causation_id")),
        "idempotency_key": _normalize_text(
            message.get("idempotency_key") or protocol.get("idempotency_key")
        ),
        "attempt": _normalize_int(
            message.get("attempt") if message.get("attempt") is not None else protocol.get("attempt"),
            default=1,
        ),
        "max_attempts": _normalize_int(
            message.get("max_attempts")
            if message.get("max_attempts") is not None
            else protocol.get("max_attempts"),
            default=DEFAULT_MAX_ATTEMPTS,
        ),
        "emitted_at": _normalize_text(message.get("emitted_at") or protocol.get("emitted_at")),
        "available_at": _normalize_text(message.get("available_at") or protocol.get("available_at")),
        "deadline_at": _normalize_text(message.get("deadline_at") or protocol.get("deadline_at")),
        "dead_letter": _normalize_bool(
            message.get("dead_letter") if "dead_letter" in message else protocol.get("dead_letter")
        ),
        "dead_letter_reason": _normalize_text(
            message.get("dead_letter_reason") or protocol.get("dead_letter_reason")
        ),
        "source": deepcopy(message.get("source") or protocol.get("source"))
        if isinstance(message.get("source") or protocol.get("source"), dict)
        else None,
        "target": deepcopy(message.get("target") or protocol.get("target"))
        if isinstance(message.get("target") or protocol.get("target"), dict)
        else None,
        "last_error": _normalize_text(message.get("last_error") or protocol.get("last_error")),
    }


def payload_from_message(message: dict | None) -> dict[str, Any]:
    if not isinstance(message, dict):
        return {}
    payload = deepcopy(message.get("payload")) if isinstance(message.get("payload"), dict) else {}
    for key, value in message.items():
        if key in METADATA_KEYS or key in payload:
            continue
        payload[key] = deepcopy(value)
    return payload


def apply_protocol_to_run(run: dict | None, protocol: dict | None) -> dict[str, Any] | None:
    if not isinstance(run, dict) or not isinstance(protocol, dict):
        return None
    dispatch_context = run.get("dispatch_context")
    if not isinstance(dispatch_context, dict):
        dispatch_context = {}
        run["dispatch_context"] = dispatch_context
    normalized_protocol = deepcopy(protocol)
    dispatch_context[PROTOCOL_CONTEXT_KEY] = normalized_protocol
    return normalized_protocol


def build_protocol_envelope(
    *,
    message_name: str,
    message_type: str,
    payload: dict[str, Any],
    protocol: dict[str, Any] | None = None,
    dispatch_context: dict[str, Any] | None = None,
    run_id: str | None = None,
    default_max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    attempt: int | None = None,
    emitted_at: str | None = None,
    available_at: str | None = None,
    deadline_at: str | None = None,
    source: dict[str, Any] | None = None,
    target: dict[str, Any] | None = None,
    dead_letter: bool | None = None,
    dead_letter_reason: str | None = None,
    last_error: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    base_protocol = protocol_from_dispatch_context(dispatch_context)
    if isinstance(protocol, dict):
        base_protocol.update({key: deepcopy(value) for key, value in protocol.items() if value is not None})

    emitted = _normalize_text(emitted_at) or _normalize_text(available_at) or utc_now_iso()
    available = _normalize_text(available_at) or emitted
    raw_attempt = attempt if attempt is not None else base_protocol.get("attempt")
    resolved_attempt = _normalize_int(raw_attempt, default=1)
    raw_max_attempts = base_protocol.get("max_attempts")
    resolved_max_attempts = (
        _normalize_int(raw_max_attempts, default=default_max_attempts)
        if raw_max_attempts not in (None, "")
        else max(default_max_attempts, 1)
    )
    resolved_request_id = (
        _normalize_text(base_protocol.get("request_id"))
        or _normalize_text(run_id)
        or f"req_{uuid4().hex}"
    )
    previous_message_id = _normalize_text(base_protocol.get("message_id"))
    resolved_protocol = {
        "spec_version": PROTOCOL_SPEC_VERSION,
        "message_id": f"msg_{uuid4().hex}",
        "message_type": message_type,
        "message_name": message_name,
        "request_id": resolved_request_id,
        "correlation_id": previous_message_id or resolved_request_id,
        "causation_id": previous_message_id,
        "idempotency_key": _normalize_text(base_protocol.get("idempotency_key"))
        or f"{message_name}:{_normalize_text(run_id) or resolved_request_id}",
        "attempt": resolved_attempt,
        "max_attempts": resolved_max_attempts,
        "emitted_at": emitted,
        "available_at": available,
        "deadline_at": _normalize_text(deadline_at) or _normalize_text(base_protocol.get("deadline_at")),
        "dead_letter": bool(dead_letter) if dead_letter is not None else False,
        "dead_letter_reason": _normalize_text(dead_letter_reason),
        "source": deepcopy(source) if isinstance(source, dict) else deepcopy(base_protocol.get("source")),
        "target": deepcopy(target) if isinstance(target, dict) else deepcopy(base_protocol.get("target")),
        "last_error": _normalize_text(last_error) or _normalize_text(base_protocol.get("last_error")),
    }
    envelope = {
        "spec_version": resolved_protocol["spec_version"],
        "message_id": resolved_protocol["message_id"],
        "message_type": resolved_protocol["message_type"],
        "message_name": resolved_protocol["message_name"],
        "request_id": resolved_protocol["request_id"],
        "correlation_id": resolved_protocol["correlation_id"],
        "causation_id": resolved_protocol["causation_id"],
        "idempotency_key": resolved_protocol["idempotency_key"],
        "attempt": resolved_protocol["attempt"],
        "max_attempts": resolved_protocol["max_attempts"],
        "emitted_at": resolved_protocol["emitted_at"],
        "available_at": resolved_protocol["available_at"],
        "deadline_at": resolved_protocol["deadline_at"],
        "dead_letter": resolved_protocol["dead_letter"],
        "dead_letter_reason": resolved_protocol["dead_letter_reason"],
        "source": deepcopy(resolved_protocol["source"]),
        "target": deepcopy(resolved_protocol["target"]),
        "last_error": resolved_protocol["last_error"],
        "payload": deepcopy(payload),
        "protocol": deepcopy(resolved_protocol),
    }
    envelope.update(deepcopy(payload))
    return envelope, resolved_protocol
