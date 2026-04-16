from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import json
from typing import Any
from uuid import uuid4

from app.core.event_types import (
    BRAIN_EVENT_SPEC_VERSION,
    EVENT_VERSION_V1,
    MESSAGE_TYPES,
    MESSAGE_TYPE_EVENT,
)


EVENT_PROTOCOL_KEYS = {
    "event_id",
    "event_name",
    "event_version",
    "message_type",
    "subject",
    "aggregate",
    "trace",
    "routing",
    "timing",
    "source",
    "target",
    "payload",
}

BUS_PAYLOAD_MAX_BYTES = 16 * 1024
BUS_SUMMARY_MAX_STRING_LENGTH = 280
BUS_SUMMARY_MAX_LIST_ITEMS = 10
BUS_SUMMARY_MAX_DICT_KEYS = 20
BUS_REDACTED_KEYS = {
    "manager_packet",
    "managerpacket",
    "memory",
    "memory_injection",
    "memoryinjection",
    "memory_hits_detail",
    "memoryhitsdetail",
    "audit",
    "context_patch_audit",
    "contextpatchaudit",
    "route_decision",
    "routedecision",
}

RUN_SUMMARY_FIELDS = (
    "id",
    "workflow_id",
    "workflow_name",
    "task_id",
    "trigger",
    "intent",
    "status",
    "created_at",
    "updated_at",
    "started_at",
    "completed_at",
    "current_stage",
    "failure_stage",
    "failure_message",
    "delivery_status",
    "delivery_message",
    "status_reason",
)
TASK_SUMMARY_FIELDS = (
    "id",
    "title",
    "status",
    "priority",
    "workflow_id",
    "workflow_run_id",
    "created_at",
    "updated_at",
    "completed_at",
    "current_stage",
    "failure_stage",
    "failure_message",
    "delivery_status",
    "delivery_message",
    "status_reason",
)
STEP_SUMMARY_FIELDS = (
    "id",
    "task_id",
    "run_id",
    "workflow_run_id",
    "node_id",
    "type",
    "agent",
    "label",
    "title",
    "status",
    "created_at",
    "updated_at",
    "completed_at",
    "started_at",
)
DISPATCH_CONTEXT_SAFE_FIELDS = (
    "type",
    "state",
    "queued_at",
    "updated_at",
    "entrypoint",
    "entrypoint_agent",
    "trace_id",
    "channel",
    "detected_lang",
    "preferred_language",
    "memory_hits",
    "dispatched_at",
    "execution_agent_id",
    "execution_agent",
    "completed_at",
    "failed_at",
    "failure_stage",
    "failure_message",
    "delivery_status",
    "delivery_message",
    "delivery_completed_at",
    "delivery_failed_at",
    "result_kind",
    "context_patch_count",
    "last_context_patch_at",
)


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _text(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _dict(value: object) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _message_type(value: object) -> str:
    normalized = _text(value) or MESSAGE_TYPE_EVENT
    if normalized not in MESSAGE_TYPES:
        return MESSAGE_TYPE_EVENT
    return normalized


def _normalized_key(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _camelized_aliases(key: str) -> set[str]:
    normalized = _normalized_key(key)
    parts = [part for part in normalized.split("_") if part]
    if not parts:
        return {normalized}
    camel = parts[0] + "".join(part.capitalize() for part in parts[1:])
    return {normalized, camel.lower()}


def _get_field(value: dict[str, Any], key: str) -> Any:
    aliases = _camelized_aliases(key)
    for candidate_key, candidate_value in value.items():
        if _normalized_key(candidate_key) in aliases:
            return candidate_value
    return None


def _trim_text(value: object) -> str:
    text = str(value or "")
    if len(text) <= BUS_SUMMARY_MAX_STRING_LENGTH:
        return text
    return f"{text[: BUS_SUMMARY_MAX_STRING_LENGTH - 1]}…"


def _redacted_summary(kind: str, value: object) -> dict[str, Any]:
    item_count = None
    if isinstance(value, (dict, list)):
        item_count = len(value)
    return {
        "summary_only": True,
        "redacted": True,
        "kind": kind,
        "item_count": item_count,
    }


def _summary_scalar(value: object) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _trim_text(value)
    return _trim_text(value)


def _looks_like_run(value: dict[str, Any]) -> bool:
    return bool(
        _get_field(value, "workflow_id") is not None
        and (
            _get_field(value, "nodes") is not None
            or _get_field(value, "logs") is not None
            or _get_field(value, "dispatch_context") is not None
            or _get_field(value, "current_stage") is not None
            or _get_field(value, "workflow_name") is not None
            or _get_field(value, "active_edges") is not None
        )
    )


def _looks_like_task(value: dict[str, Any]) -> bool:
    return bool(
        _get_field(value, "title") is not None
        and (
            _get_field(value, "priority") is not None
            or _get_field(value, "workflow_run_id") is not None
            or _get_field(value, "current_stage") is not None
        )
    )


def _looks_like_step(value: dict[str, Any]) -> bool:
    return bool(
        _get_field(value, "node_id") is not None
        or (
            _get_field(value, "agent") is not None
            and (
                _get_field(value, "label") is not None
                or _get_field(value, "title") is not None
                or _get_field(value, "started_at") is not None
            )
        )
    )


def _build_entity_summary(
    value: dict[str, Any],
    *,
    kind: str,
    fields: tuple[str, ...],
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "summary_only": True,
        "summary_kind": kind,
    }
    for field in fields:
        field_value = _get_field(value, field)
        if field_value is not None:
            summary[field] = _summary_scalar(field_value)
    if kind == "workflow_run":
        summary["node_count"] = len(_get_field(value, "nodes") or [])
        summary["log_count"] = len(_get_field(value, "logs") or [])
        summary["active_edge_count"] = len(_get_field(value, "active_edges") or [])
        dispatch_context = _get_field(value, "dispatch_context")
        if isinstance(dispatch_context, dict):
            summary["dispatch_context"] = _build_dispatch_context_summary(dispatch_context)
        monitor = _get_field(value, "monitor")
        if isinstance(monitor, dict):
            summary["monitor"] = {
                "summary_only": True,
                "summary_kind": "workflow_monitor",
                "status": _summary_scalar(_get_field(monitor, "status")),
                "updated_at": _summary_scalar(_get_field(monitor, "updated_at")),
            }
    return summary


def _build_dispatch_context_summary(value: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "summary_only": True,
        "summary_kind": "dispatch_context",
    }
    for field in DISPATCH_CONTEXT_SAFE_FIELDS:
        field_value = _get_field(value, field)
        if field_value is not None:
            summary[field] = _summary_scalar(field_value)
    for key in ("manager_packet", "route_decision", "memory", "audit", "context_patch_audit"):
        field_value = _get_field(value, key)
        if field_value is not None:
            summary[key] = _redacted_summary(_normalized_key(key), field_value)
    return summary


def _sanitize_sequence(value: list[Any], *, depth: int, parent_key: str | None) -> list[Any]:
    items = value[:BUS_SUMMARY_MAX_LIST_ITEMS]
    return [
        _sanitize_bus_value(
            item,
            depth=depth + 1,
            parent_key=parent_key,
        )
        for item in items
    ]


def _sanitize_mapping(
    value: dict[str, Any],
    *,
    depth: int,
    parent_key: str | None,
) -> dict[str, Any]:
    normalized_parent = _normalized_key(parent_key)
    if normalized_parent == "dispatch_context":
        return _build_dispatch_context_summary(value)
    if normalized_parent == "run" or _looks_like_run(value):
        return _build_entity_summary(value, kind="workflow_run", fields=RUN_SUMMARY_FIELDS)
    if normalized_parent == "task" or _looks_like_task(value):
        return _build_entity_summary(value, kind="task", fields=TASK_SUMMARY_FIELDS)
    if normalized_parent == "step" or _looks_like_step(value):
        return _build_entity_summary(value, kind="step", fields=STEP_SUMMARY_FIELDS)

    summary: dict[str, Any] = {}
    for index, (key, item) in enumerate(value.items()):
        if index >= BUS_SUMMARY_MAX_DICT_KEYS:
            summary["_truncated_keys"] = len(value) - BUS_SUMMARY_MAX_DICT_KEYS
            break
        normalized_key = _normalized_key(key)
        if normalized_key in BUS_REDACTED_KEYS:
            summary[str(key)] = _redacted_summary(normalized_key, item)
            continue
        summary[str(key)] = _sanitize_bus_value(item, depth=depth + 1, parent_key=str(key))
    return summary


def _sanitize_bus_value(value: Any, *, depth: int = 0, parent_key: str | None = None) -> Any:
    normalized_parent = _normalized_key(parent_key)
    if normalized_parent in BUS_REDACTED_KEYS:
        return _redacted_summary(normalized_parent, value)
    if depth >= 4:
        return _summary_scalar(value if not isinstance(value, (dict, list)) else f"<{type(value).__name__}>")
    if isinstance(value, dict):
        return _sanitize_mapping(value, depth=depth, parent_key=parent_key)
    if isinstance(value, list):
        return _sanitize_sequence(value, depth=depth, parent_key=parent_key)
    return _summary_scalar(value)


def summarize_payload_for_bus(payload: dict[str, Any], *, max_bytes: int = BUS_PAYLOAD_MAX_BYTES) -> dict[str, Any]:
    summarized = _sanitize_mapping(deepcopy(payload), depth=0, parent_key=None)
    encoded = json.dumps(summarized, ensure_ascii=False).encode("utf-8")
    if len(encoded) <= max_bytes:
        return summarized

    compact = deepcopy(summarized)
    for key in ("items", "run", "task", "step", "payload"):
        value = compact.get(key)
        if value is None:
            continue
        compact[key] = _redacted_summary(_normalized_key(key), value)
    compact["_payload_truncated"] = True
    compact["_payload_size_bytes"] = len(encoded)
    return compact


def _event_name_from_payload(subject: str, payload: dict[str, Any]) -> str:
    return (
        _text(payload.get("event_name"))
        or _text(payload.get("eventName"))
        or _text(payload.get("type"))
        or subject
    ) or subject


def _aggregate_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    aggregate = _dict(payload.get("aggregate"))
    if aggregate:
        aggregate_type = _text(aggregate.get("type"))
        aggregate_id = _text(aggregate.get("id"))
        return {
            "type": aggregate_type,
            "id": aggregate_id,
        }
    return {
        "type": (
            _text(payload.get("aggregate_type"))
            or _text(payload.get("aggregateType"))
            or "event"
        ),
        "id": (
            _text(payload.get("aggregate_id"))
            or _text(payload.get("aggregateId"))
            or _text(payload.get("run_id"))
            or _text(payload.get("runId"))
            or _text(payload.get("task_id"))
            or _text(payload.get("taskId"))
            or _text(payload.get("workflow_id"))
            or _text(payload.get("workflowId"))
            or _text(payload.get("request_id"))
            or _text(payload.get("requestId"))
        ),
    }


def _trace_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    trace = _dict(payload.get("trace"))
    if trace:
        return {
            "trace_id": _text(trace.get("trace_id") or trace.get("traceId")),
            "request_id": _text(trace.get("request_id") or trace.get("requestId")),
            "parent_event_id": _text(trace.get("parent_event_id") or trace.get("parentEventId")),
            "causation_id": _text(trace.get("causation_id") or trace.get("causationId")),
            "correlation_id": _text(trace.get("correlation_id") or trace.get("correlationId")),
        }
    return {
        "trace_id": _text(payload.get("trace_id") or payload.get("traceId")),
        "request_id": (
            _text(payload.get("request_id"))
            or _text(payload.get("requestId"))
            or _text(payload.get("message_id"))
            or _text(payload.get("messageId"))
        ),
        "parent_event_id": _text(payload.get("parent_event_id") or payload.get("parentEventId")),
        "causation_id": _text(payload.get("causation_id") or payload.get("causationId")),
        "correlation_id": _text(payload.get("correlation_id") or payload.get("correlationId")),
    }


def _routing_from_payload(subject: str, payload: dict[str, Any], aggregate: dict[str, Any]) -> dict[str, Any]:
    routing = _dict(payload.get("routing"))
    if routing:
        return {
            "partition_key": _text(routing.get("partition_key") or routing.get("partitionKey")),
            "idempotency_key": _text(routing.get("idempotency_key") or routing.get("idempotencyKey")),
        }
    aggregate_id = _text(aggregate.get("id"))
    event_name = _event_name_from_payload(subject, payload)
    return {
        "partition_key": (
            _text(payload.get("partition_key"))
            or _text(payload.get("partitionKey"))
            or _text(payload.get("workflow_id"))
            or _text(payload.get("workflowId"))
            or aggregate_id
        ),
        "idempotency_key": (
            _text(payload.get("idempotency_key"))
            or _text(payload.get("idempotencyKey"))
            or f"{event_name}:{aggregate_id or subject}"
        ),
    }


def _timing_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    timing = _dict(payload.get("timing"))
    emitted_at = (
        _text(timing.get("emitted_at") or timing.get("emittedAt"))
        or _text(payload.get("timestamp"))
        or _text(payload.get("emitted_at"))
        or _text(payload.get("emittedAt"))
        or utc_now_iso()
    )
    return {
        "emitted_at": emitted_at,
        "available_at": (
            _text(timing.get("available_at") or timing.get("availableAt"))
            or _text(payload.get("available_at"))
            or _text(payload.get("availableAt"))
            or emitted_at
        ),
        "expires_at": (
            _text(timing.get("expires_at") or timing.get("expiresAt"))
            or _text(payload.get("expires_at"))
            or _text(payload.get("expiresAt"))
        ),
        "lease_until": (
            _text(timing.get("lease_until") or timing.get("leaseUntil"))
            or _text(payload.get("lease_until"))
            or _text(payload.get("leaseUntil"))
        ),
    }


def _source_from_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    source = _dict(payload.get("source"))
    if not source:
        return None
    return {
        "kind": _text(source.get("kind")),
        "id": _text(source.get("id")),
    }


def _target_from_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    target = _dict(payload.get("target"))
    if not target:
        return None
    return {
        "kind": _text(target.get("kind")),
        "id": _text(target.get("id")),
    }


def is_event_envelope(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    return EVENT_PROTOCOL_KEYS.issubset(set(payload.keys()))


def is_legacy_agent_protocol_envelope(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    spec_version = _text(payload.get("spec_version") or payload.get("specVersion"))
    if spec_version != "agentbus.v1":
        return False
    return isinstance(payload.get("payload"), dict) and bool(
        _text(payload.get("message_name") or payload.get("messageName"))
    )


def build_event_envelope(
    *,
    subject: str,
    event_name: str,
    payload: dict[str, Any],
    message_type: str = MESSAGE_TYPE_EVENT,
    aggregate: dict[str, Any] | None = None,
    trace: dict[str, Any] | None = None,
    routing: dict[str, Any] | None = None,
    timing: dict[str, Any] | None = None,
    source: dict[str, Any] | None = None,
    target: dict[str, Any] | None = None,
    event_id: str | None = None,
    event_version: str = EVENT_VERSION_V1,
) -> dict[str, Any]:
    normalized_aggregate = {
        "type": _text((aggregate or {}).get("type")) or "event",
        "id": _text((aggregate or {}).get("id")),
    }
    normalized_trace = {
        "trace_id": _text((trace or {}).get("trace_id") or (trace or {}).get("traceId")),
        "request_id": _text((trace or {}).get("request_id") or (trace or {}).get("requestId")),
        "parent_event_id": _text(
            (trace or {}).get("parent_event_id") or (trace or {}).get("parentEventId")
        ),
        "causation_id": _text((trace or {}).get("causation_id") or (trace or {}).get("causationId")),
        "correlation_id": _text(
            (trace or {}).get("correlation_id") or (trace or {}).get("correlationId")
        ),
    }
    normalized_timing = {
        "emitted_at": _text((timing or {}).get("emitted_at") or (timing or {}).get("emittedAt")) or utc_now_iso(),
        "available_at": _text((timing or {}).get("available_at") or (timing or {}).get("availableAt")),
        "expires_at": _text((timing or {}).get("expires_at") or (timing or {}).get("expiresAt")),
        "lease_until": _text((timing or {}).get("lease_until") or (timing or {}).get("leaseUntil")),
    }
    if normalized_timing["available_at"] is None:
        normalized_timing["available_at"] = normalized_timing["emitted_at"]
    normalized_routing = {
        "partition_key": _text((routing or {}).get("partition_key") or (routing or {}).get("partitionKey")),
        "idempotency_key": _text((routing or {}).get("idempotency_key") or (routing or {}).get("idempotencyKey")),
    }
    if normalized_routing["idempotency_key"] is None:
        normalized_routing["idempotency_key"] = (
            f"{event_name}:{normalized_aggregate['id'] or normalized_timing['emitted_at']}"
        )
    return {
        "event_id": _text(event_id) or f"evt_{uuid4().hex}",
        "event_name": _text(event_name) or subject,
        "event_version": _text(event_version) or EVENT_VERSION_V1,
        "message_type": _message_type(message_type),
        "subject": _text(subject) or "",
        "aggregate": normalized_aggregate,
        "trace": normalized_trace,
        "routing": normalized_routing,
        "timing": normalized_timing,
        "source": {
            "kind": _text((source or {}).get("kind")),
            "id": _text((source or {}).get("id")),
        }
        if isinstance(source, dict)
        else None,
        "target": {
            "kind": _text((target or {}).get("kind")),
            "id": _text((target or {}).get("id")),
        }
        if isinstance(target, dict)
        else None,
        "payload": deepcopy(payload),
    }


def normalize_event_envelope(subject: str, payload: dict[str, Any]) -> dict[str, Any]:
    if is_legacy_agent_protocol_envelope(payload):
        return deepcopy(payload)

    if is_event_envelope(payload):
        normalized = deepcopy(payload)
        normalized["event_id"] = _text(normalized.get("event_id")) or f"evt_{uuid4().hex}"
        normalized["event_name"] = _text(normalized.get("event_name")) or subject
        normalized["event_version"] = _text(normalized.get("event_version")) or EVENT_VERSION_V1
        normalized["message_type"] = _message_type(normalized.get("message_type"))
        normalized["subject"] = _text(normalized.get("subject")) or subject
        normalized["aggregate"] = _aggregate_from_payload(normalized)
        normalized["trace"] = _trace_from_payload(normalized)
        normalized["routing"] = _routing_from_payload(subject, normalized, normalized["aggregate"])
        normalized["timing"] = _timing_from_payload(normalized)
        normalized["source"] = _source_from_payload(normalized)
        normalized["target"] = _target_from_payload(normalized)
        normalized["payload"] = deepcopy(normalized.get("payload")) if isinstance(normalized.get("payload"), dict) else {}
        return normalized

    legacy_payload = deepcopy(payload)
    aggregate = _aggregate_from_payload(legacy_payload)
    normalized = build_event_envelope(
        subject=subject,
        event_name=_event_name_from_payload(subject, legacy_payload),
        message_type=_message_type(
            legacy_payload.get("message_type") or legacy_payload.get("messageType")
        ),
        aggregate=aggregate,
        trace=_trace_from_payload(legacy_payload),
        routing=_routing_from_payload(subject, legacy_payload, aggregate),
        timing=_timing_from_payload(legacy_payload),
        source=_source_from_payload(legacy_payload),
        target=_target_from_payload(legacy_payload),
        payload=legacy_payload,
    )
    for key, value in legacy_payload.items():
        if key not in normalized:
            normalized[key] = value
    normalized["spec_version"] = BRAIN_EVENT_SPEC_VERSION
    return normalized


def validate_event_envelope(subject: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_event_envelope(subject, payload)
    if is_legacy_agent_protocol_envelope(normalized):
        return normalized
    if not _text(normalized.get("subject")):
        raise ValueError("Event subject is required")
    if not _text(normalized.get("event_name")):
        raise ValueError("Event name is required")
    if not _text(normalized.get("event_id")):
        raise ValueError("Event id is required")
    if normalized.get("message_type") not in MESSAGE_TYPES:
        raise ValueError("Invalid event message_type")
    aggregate = normalized.get("aggregate")
    if not isinstance(aggregate, dict) or not _text(aggregate.get("type")):
        raise ValueError("Event aggregate.type is required")
    timing = normalized.get("timing")
    if not isinstance(timing, dict) or not _text(timing.get("emitted_at")):
        raise ValueError("Event timing.emitted_at is required")
    routing = normalized.get("routing")
    if not isinstance(routing, dict) or not _text(routing.get("idempotency_key")):
        raise ValueError("Event routing.idempotency_key is required")
    return normalized
