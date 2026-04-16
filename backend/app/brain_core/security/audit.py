from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4


def serialize_audit_metadata(metadata: dict[str, object]) -> str:
    return json.dumps(
        metadata,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def build_trace_context(
    *,
    trace_id: str,
    user_key: str,
    auth_scope: str,
    now: datetime,
) -> dict[str, object]:
    return {
        "trace_id": trace_id,
        "span_id": uuid4().hex[:16],
        "parent_span_id": None,
        "trace_flags": "01",
        "trace_state": "workbot.security_gateway=sampled",
        "service": "workbot.security_gateway",
        "operation": "inspect",
        "user_key": user_key,
        "auth_scope": auth_scope,
        "started_at": now.isoformat(),
    }


def build_trace_event(
    trace_context: dict[str, object],
    *,
    layer: str,
    outcome: str,
    status_code: int,
    ended_at: datetime,
) -> dict[str, object]:
    trace_event = dict(trace_context)
    trace_event["layer"] = layer
    trace_event["outcome"] = outcome
    trace_event["status_code"] = status_code
    trace_event["ended_at"] = ended_at.isoformat()
    trace_event["event_span_id"] = uuid4().hex[:16]
    return trace_event


def build_audit_log_payload(
    *,
    action: str,
    user: str,
    resource: str,
    status_value: str,
    details: str,
    timestamp: str,
    metadata: dict[str, object] | None = None,
    ip: str = "-",
) -> dict[str, object]:
    details_value = details
    if isinstance(metadata, dict) and metadata:
        details_value = f"{details}; telemetry={serialize_audit_metadata(metadata)}"
    log_payload = {
        "id": f"audit-{uuid4().hex[:10]}",
        "timestamp": timestamp,
        "action": action,
        "user": user,
        "resource": resource,
        "status": status_value,
        "ip": ip,
        "details": details_value,
    }
    if isinstance(metadata, dict) and metadata:
        log_payload["metadata"] = dict(metadata)
    return log_payload
