from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status

from app.platform.contracts.event_protocol import build_event_envelope, summarize_payload_for_bus
from app.platform.messaging.nats_event_bus import nats_event_bus
from app.platform.audit.control_plane_audit_service import append_control_plane_audit_log
from app.platform.persistence.persistence_service import persistence_service
from app.platform.persistence.runtime_store import store
from app.modules.organization.application.tenancy_service import attach_scope, default_scope, matches_scope


EVENT_JOURNAL_KEY = "brain_event_journal"
EVENT_DEAD_LETTER_KEY = "brain_event_dead_letters"
MAX_EVENT_JOURNAL_ITEMS = 1000
MAX_EVENT_DEAD_LETTERS = 500


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _read_setting_items(key: str) -> list[dict[str, Any]]:
    payload, authoritative = persistence_service.read_system_setting(key)
    if authoritative:
        data = payload.get("items") if isinstance(payload, dict) else []
        return deepcopy(data) if isinstance(data, list) else []
    items = store.system_settings.get(key, {}).get("items", [])
    return deepcopy(items) if isinstance(items, list) else []


def _persist_setting_items(key: str, items: list[dict[str, Any]]) -> None:
    payload = {"items": deepcopy(items)}
    if not persistence_service.persist_system_setting(key=key, payload=payload, updated_at=_utc_now()):
        store.system_settings[key] = payload


def _upsert_event_record(item: dict[str, Any]) -> dict[str, Any]:
    items = _read_setting_items(EVENT_JOURNAL_KEY)
    event_id = str(item.get("event_id") or "").strip()
    replaced = False
    for index, existing in enumerate(items):
        if str(existing.get("event_id") or "").strip() == event_id:
            items[index] = deepcopy(item)
            replaced = True
            break
    if not replaced:
        items.insert(0, deepcopy(item))
    del items[MAX_EVENT_JOURNAL_ITEMS:]
    _persist_setting_items(EVENT_JOURNAL_KEY, items)
    return deepcopy(item)


def _append_dead_letter(item: dict[str, Any]) -> dict[str, Any]:
    items = _read_setting_items(EVENT_DEAD_LETTER_KEY)
    items.insert(0, deepcopy(item))
    del items[MAX_EVENT_DEAD_LETTERS:]
    _persist_setting_items(EVENT_DEAD_LETTER_KEY, items)
    return deepcopy(item)


def record_event_publish_attempt(subject: str, envelope: dict[str, Any]) -> dict[str, Any]:
    now = _utc_now()
    scope = default_scope()
    payload = {
        "event_id": str(envelope.get("event_id") or "").strip(),
        "tenant_id": str(envelope.get("tenant_id") or scope["tenant_id"]),
        "project_id": str(envelope.get("project_id") or scope["project_id"]),
        "environment": str(envelope.get("environment") or scope["environment"]),
        "subject": str(envelope.get("subject") or subject).strip() or subject,
        "event_name": str(envelope.get("event_name") or subject).strip() or subject,
        "event_version": str(envelope.get("event_version") or "v1").strip() or "v1",
        "message_type": str(envelope.get("message_type") or "event").strip() or "event",
        "status": "pending",
        "aggregate": deepcopy(envelope.get("aggregate") or {}),
        "trace": deepcopy(envelope.get("trace") or {}),
        "routing": deepcopy(envelope.get("routing") or {}),
        "timing": deepcopy(envelope.get("timing") or {}),
        "source": deepcopy(envelope.get("source")) if isinstance(envelope.get("source"), dict) else None,
        "target": deepcopy(envelope.get("target")) if isinstance(envelope.get("target"), dict) else None,
        "payload": summarize_payload_for_bus(envelope.get("payload") or {}),
        "publish_error": None,
        "replayed_from_event_id": None,
        "created_at": now,
        "updated_at": now,
    }
    existing = get_event(payload["event_id"])
    if existing is not None:
        payload["created_at"] = existing.get("created_at") or now
        payload["replayed_from_event_id"] = existing.get("replayed_from_event_id")
    return _upsert_event_record(attach_scope(payload))


def mark_event_published(event_id: str) -> dict[str, Any] | None:
    event = get_event(event_id)
    if event is None:
        return None
    event["status"] = "published"
    event["updated_at"] = _utc_now()
    return _upsert_event_record(event)


def mark_event_publish_failed(event_id: str, *, error: str) -> dict[str, Any] | None:
    event = get_event(event_id)
    if event is None:
        return None
    event["status"] = "failed_publish"
    event["publish_error"] = str(error or "publish failed").strip() or "publish failed"
    event["updated_at"] = _utc_now()
    saved = _upsert_event_record(event)
    _append_dead_letter(
        {
            "id": f"dead-letter-{uuid4().hex[:10]}",
            "tenant_id": saved.get("tenant_id"),
            "project_id": saved.get("project_id"),
            "environment": saved.get("environment"),
            "event_id": saved["event_id"],
            "subject": saved["subject"],
            "event_name": saved["event_name"],
            "failure_stage": "publish",
            "error": saved["publish_error"],
            "attempt_count": 1,
            "payload": deepcopy(saved.get("payload") or {}),
            "created_at": _utc_now(),
            "resolved_at": None,
        }
    )
    return saved


def list_events(
    *,
    subject: str | None = None,
    message_type: str | None = None,
    limit: int = 50,
    scope: dict[str, str] | None = None,
) -> dict[str, Any]:
    items = _read_setting_items(EVENT_JOURNAL_KEY)
    filtered: list[dict[str, Any]] = []
    normalized_subject = str(subject or "").strip()
    normalized_type = str(message_type or "").strip().lower()
    for item in items:
        attached = attach_scope(item)
        if scope is not None and not matches_scope(attached, scope):
            continue
        if normalized_subject and str(attached.get("subject") or "").strip() != normalized_subject:
            continue
        if normalized_type and str(attached.get("message_type") or "").strip().lower() != normalized_type:
            continue
        filtered.append(attached)
    return {"items": filtered[: max(1, min(limit, 200))], "total": len(filtered)}


def list_dead_letters(limit: int = 50, *, scope: dict[str, str] | None = None) -> dict[str, Any]:
    items = [attach_scope(item) for item in _read_setting_items(EVENT_DEAD_LETTER_KEY)]
    if scope is not None:
        items = [item for item in items if matches_scope(item, scope)]
    return {"items": items[: max(1, min(limit, 200))], "total": len(items)}


def get_event(event_id: str, *, scope: dict[str, str] | None = None) -> dict[str, Any] | None:
    normalized = str(event_id or "").strip()
    if not normalized:
        return None
    for item in _read_setting_items(EVENT_JOURNAL_KEY):
        if str(item.get("event_id") or "").strip() == normalized:
            attached = attach_scope(item)
            if scope is not None and not matches_scope(attached, scope):
                return None
            return attached
    return None


def replay_event(
    event_id: str,
    *,
    actor: str,
    reason: str | None = None,
    scope: dict[str, str] | None = None,
) -> dict[str, Any]:
    source_event = get_event(event_id, scope=scope)
    if source_event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    replayed_at = _utc_now()
    source_trace = source_event.get("trace") if isinstance(source_event.get("trace"), dict) else {}
    replay_envelope = build_event_envelope(
        subject=str(source_event.get("subject") or "").strip(),
        event_name=str(source_event.get("event_name") or "").strip(),
        event_version=str(source_event.get("event_version") or "v1").strip() or "v1",
        message_type=str(source_event.get("message_type") or "event").strip() or "event",
        aggregate=deepcopy(source_event.get("aggregate") or {}),
        trace={
            "trace_id": source_trace.get("trace_id") or source_trace.get("traceId"),
            "request_id": source_trace.get("request_id") or source_trace.get("requestId"),
            "parent_event_id": source_event["event_id"],
            "causation_id": source_event["event_id"],
            "correlation_id": source_trace.get("correlation_id")
            or source_trace.get("correlationId")
            or source_trace.get("trace_id")
            or source_trace.get("traceId")
            or source_event["event_id"],
        },
        routing={
            "partition_key": (source_event.get("routing") or {}).get("partition_key"),
            "idempotency_key": f"{(source_event.get('routing') or {}).get('idempotency_key') or source_event['event_id']}:replay:{replayed_at}",
        },
        timing={"emitted_at": replayed_at, "available_at": replayed_at},
        source=deepcopy(source_event.get("source") or {}),
        target=deepcopy(source_event.get("target") or {}),
        payload=deepcopy(source_event.get("payload") or {}),
    )
    replay_envelope["tenant_id"] = source_event.get("tenant_id")
    replay_envelope["project_id"] = source_event.get("project_id")
    replay_envelope["environment"] = source_event.get("environment")
    event = record_event_publish_attempt(replay_envelope["subject"], replay_envelope)
    event["status"] = "replayed"
    event["replayed_from_event_id"] = source_event["event_id"]
    event["updated_at"] = replayed_at
    _upsert_event_record(event)
    published = nats_event_bus.publish_json(replay_envelope["subject"], replay_envelope)
    append_control_plane_audit_log(
        action="event.replayed",
        user=actor,
        resource=f"event:{source_event['event_id']}",
        details=f"重放事件 {source_event['event_name']}",
        metadata={
            "source_event_id": source_event["event_id"],
            "replay_event_id": replay_envelope["event_id"],
            "published": bool(published),
            "reason": str(reason or "").strip() or None,
        },
    )
    replay_event_record = get_event(replay_envelope["event_id"]) or event
    replay_event_record["status"] = "published" if published else replay_event_record["status"]
    _upsert_event_record(replay_event_record)
    return {"source_event": source_event, "replay_event": replay_event_record, "published": bool(published)}
