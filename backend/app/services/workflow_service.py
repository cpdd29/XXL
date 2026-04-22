import logging
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException, status

from app.core.brain_payload_fields import alias_text, dispatch_context_from_run, route_decision_from_payload
from app.core.event_protocol import build_event_envelope, summarize_payload_for_bus
from app.core.event_subjects import (
    INTERNAL_EVENT_DELIVERY_COMPLETED_SUBJECT,
    INTERNAL_EVENT_DELIVERY_FAILED_SUBJECT,
    INTERNAL_EVENT_DELIVERY_REQUESTED_SUBJECT,
    INTERNAL_EVENT_DELIVERY_RETRIED_SUBJECT,
)
from app.core.event_types import MESSAGE_TYPE_EVENT, MESSAGE_TYPE_RESULT
from app.core.nats_event_bus import nats_event_bus
from app.services.persistence_service import persistence_service
from app.services.store import LEGACY_WORKFLOW_IDS, store
from app.services.webhook_guard_service import sanitize_webhook_payload
from app.services.workflow_execution_service import (
    create_manual_workflow_run,
    get_workflow_run,
    list_workflow_runs,
    request_manual_handoff_for_workflow_run,
    tick_workflow_run,
)
from app.services.workflow_runtime_snapshot_service import workflow_runtime_snapshot_service

DEFAULT_TRIGGER = {
    "type": "message",
    "keyword": "搜索, 写作, 帮助",
    "cron": None,
    "webhook_path": None,
    "internal_event": None,
    "description": "默认消息入口，按关键词进入客户服务工作流",
    "priority": 100,
    "channels": [],
    "preferred_language": None,
    "step_delay_seconds": 0.6,
    "max_dispatch_retry": 6,
    "dispatch_retry_backoff_seconds": 2.0,
    "execution_timeout_seconds": 45.0,
    "natural_language_rule": None,
    "schedule_plan": None,
}
logger = logging.getLogger(__name__)
_INTERNAL_EVENT_DELIVERIES_BY_ID: dict[str, dict] = {}
_INTERNAL_EVENT_DELIVERIES_BY_KEY: dict[str, str] = {}
WORKFLOW_STORAGE_UNAVAILABLE_DETAIL = "Workflow configuration storage unavailable"
WORKFLOW_INTERNAL_TRIGGER_NOT_FOUND_DETAIL = "Workflow internal trigger not found"
INTERNAL_EVENT_STATUS_IGNORED = "ignored"
WORKFLOW_LIST_PRIORITY_BY_ID = {
    "mandatory-workflow-agent-security-pipeline": -4,
    "mandatory-workflow-agent-conversation-pipeline": -3,
    "mandatory-workflow-professional-agent": -2,
    "mandatory-workflow-free-agent": -1,
}


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _normalize_trigger_channels(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = value.replace("，", ",").split(",")
    elif isinstance(value, list):
        items = value
    else:
        return []

    channels: list[str] = []
    for item in items:
        normalized = str(item).strip().lower()
        if normalized and normalized not in channels:
            channels.append(normalized)
    return channels


def _normalize_trigger_priority(value: object) -> int:
    if value in {None, ""}:
        return int(DEFAULT_TRIGGER["priority"])
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(DEFAULT_TRIGGER["priority"])


def _normalize_positive_int(value: object, *, default: int) -> int:
    if value in {None, ""}:
        return default
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return default
    return normalized if normalized > 0 else default


def _normalize_positive_float(value: object, *, default: float) -> float:
    if value in {None, ""}:
        return default
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        return default
    return normalized if normalized > 0 else default


def _normalize_preferred_language(value: object) -> str | None:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    return normalized.replace("_", "-").split("-", maxsplit=1)[0]


def _normalize_trigger_cron(value: object) -> str | None:
    normalized = " ".join(str(value or "").strip().split())
    return normalized or None


def _normalize_trigger_type(value: object) -> str:
    raw_value = getattr(value, "value", value)
    normalized = str(raw_value or "").strip().lower()
    return normalized or str(DEFAULT_TRIGGER["type"])


def _normalize_webhook_path(value: object) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    normalized = "/" + normalized.strip("/")
    return normalized if normalized != "/" else None


def _normalize_internal_event(value: object) -> str | None:
    normalized = " ".join(str(value or "").strip().split()).lower()
    return normalized or None


def _resolve_internal_event_source(source: str | None, payload: dict) -> str:
    return str(source or payload.get("source") or "Internal Event Bus").strip() or "Internal Event Bus"


def _resolve_internal_event_idempotency_key(
    normalized_event: str,
    payload: dict,
    explicit_idempotency_key: str | None = None,
) -> str | None:
    candidate = str(explicit_idempotency_key or "").strip()
    if not candidate:
        for key in ("idempotencyKey", "idempotency_key", "eventId", "event_id"):
            value = str(payload.get(key) or "").strip()
            if value:
                candidate = value
                break
    if not candidate:
        mid_term_id = str(payload.get("midTermId") or payload.get("mid_term_id") or "").strip()
        long_term_id = str(payload.get("longTermId") or payload.get("long_term_id") or "").strip()
        if mid_term_id and long_term_id:
            candidate = f"{mid_term_id}:{long_term_id}"

    if not candidate:
        return None
    if candidate.startswith(f"{normalized_event}:"):
        return candidate
    return f"{normalized_event}:{candidate}"


def _cache_internal_event_delivery(delivery: dict) -> dict:
    cached_delivery = store.clone(delivery)
    _INTERNAL_EVENT_DELIVERIES_BY_ID[str(cached_delivery["id"])] = cached_delivery
    idempotency_key = str(cached_delivery.get("idempotency_key") or "").strip()
    if idempotency_key:
        _INTERNAL_EVENT_DELIVERIES_BY_KEY[idempotency_key] = str(cached_delivery["id"])
    return cached_delivery


def _evict_cached_internal_event_delivery(
    *,
    delivery_id: str | None = None,
    idempotency_key: str | None = None,
) -> None:
    normalized_delivery_id = str(delivery_id or "").strip()
    normalized_key = str(idempotency_key or "").strip()

    if not normalized_delivery_id and normalized_key:
        normalized_delivery_id = str(
            _INTERNAL_EVENT_DELIVERIES_BY_KEY.get(normalized_key) or ""
        ).strip()

    cached_delivery = None
    if normalized_delivery_id:
        cached_delivery = _INTERNAL_EVENT_DELIVERIES_BY_ID.pop(normalized_delivery_id, None)

    if not normalized_key and isinstance(cached_delivery, dict):
        normalized_key = str(cached_delivery.get("idempotency_key") or "").strip()

    if normalized_key:
        mapped_delivery_id = str(
            _INTERNAL_EVENT_DELIVERIES_BY_KEY.get(normalized_key) or ""
        ).strip()
        if not mapped_delivery_id or mapped_delivery_id == normalized_delivery_id:
            _INTERNAL_EVENT_DELIVERIES_BY_KEY.pop(normalized_key, None)

    if isinstance(cached_delivery, dict):
        cached_key = str(cached_delivery.get("idempotency_key") or "").strip()
        if cached_key and _INTERNAL_EVENT_DELIVERIES_BY_KEY.get(cached_key) == normalized_delivery_id:
            _INTERNAL_EVENT_DELIVERIES_BY_KEY.pop(cached_key, None)


def _persist_internal_event_delivery(delivery: dict) -> dict:
    upsert_delivery = getattr(persistence_service, "upsert_internal_event_delivery", None)
    if callable(upsert_delivery):
        persisted = upsert_delivery(delivery)
        if persisted is not None:
            delivery = persisted

    return _cache_internal_event_delivery(delivery)


def _publish_internal_event_delivery_event(
    delivery: dict,
    *,
    subject: str,
    event_name: str,
    message_type: str = MESSAGE_TYPE_EVENT,
    extra_payload: dict | None = None,
) -> None:
    delivery_id = str(delivery.get("id") or "").strip()
    if not delivery_id:
        return
    emitted_at = str(delivery.get("updated_at") or "").strip() or datetime.now(UTC).isoformat()
    payload = {
        "internal_event_id": delivery_id,
        "internal_event_name": str(delivery.get("event_name") or "").strip() or None,
        "status": str(delivery.get("status") or "").strip() or None,
        "attempt_count": int(delivery.get("attempt_count") or 0),
        "idempotency_key": str(delivery.get("idempotency_key") or "").strip() or None,
        "triggered_count": int(delivery.get("triggered_count") or 0),
        "triggered_workflow_ids": list(delivery.get("triggered_workflow_ids") or []),
        "triggered_run_ids": list(delivery.get("triggered_run_ids") or []),
        "triggered_task_ids": list(delivery.get("triggered_task_ids") or []),
        "last_error": str(delivery.get("last_error") or "").strip() or None,
        "updated_at": emitted_at,
    }
    if isinstance(extra_payload, dict):
        payload.update(store.clone(extra_payload))
    envelope = build_event_envelope(
        subject=subject,
        event_name=event_name,
        message_type=message_type,
        aggregate={"type": "internal_event_delivery", "id": delivery_id},
        trace={"request_id": delivery_id},
        routing={
            "partition_key": delivery_id,
            "idempotency_key": str(delivery.get("idempotency_key") or "").strip()
            or f"{event_name}:{delivery_id}",
        },
        timing={"emitted_at": emitted_at, "available_at": emitted_at},
        source={"kind": "workflow_service", "id": "internal_event_delivery"},
        target={"kind": "brain_internal_bus", "id": "internal_event_delivery"},
        payload=summarize_payload_for_bus(payload),
    )
    nats_event_bus.publish_json(subject, envelope)


def _load_database_internal_event_delivery(delivery_id: str) -> tuple[dict | None, bool]:
    normalized_delivery_id = str(delivery_id or "").strip()
    if not normalized_delivery_id or not getattr(persistence_service, "enabled", False):
        return None, False

    get_delivery = getattr(persistence_service, "get_internal_event_delivery", None)
    if callable(get_delivery):
        persisted = get_delivery(normalized_delivery_id)
        if persisted is not None:
            return persisted, True

    list_deliveries = getattr(persistence_service, "list_internal_event_deliveries", None)
    if not callable(list_deliveries):
        return None, True

    persisted_items = list_deliveries()
    if persisted_items is None:
        return None, True

    for candidate in persisted_items:
        if str(candidate.get("id") or "").strip() == normalized_delivery_id:
            return candidate, True
    return None, True


def _load_database_internal_event_delivery_by_idempotency_key(
    idempotency_key: str,
) -> tuple[dict | None, bool]:
    normalized_key = str(idempotency_key or "").strip()
    if not normalized_key or not getattr(persistence_service, "enabled", False):
        return None, False

    find_delivery = getattr(
        persistence_service,
        "find_internal_event_delivery_by_idempotency_key",
        None,
    )
    if callable(find_delivery):
        persisted = find_delivery(normalized_key)
        if persisted is not None:
            return persisted, True

    list_deliveries = getattr(persistence_service, "list_internal_event_deliveries", None)
    if not callable(list_deliveries):
        return None, True

    persisted_items = list_deliveries()
    if persisted_items is None:
        return None, True

    for candidate in persisted_items:
        if str(candidate.get("idempotency_key") or "").strip() == normalized_key:
            return candidate, True
    return None, True


def _find_internal_event_delivery_by_idempotency_key(idempotency_key: str | None) -> dict | None:
    normalized_key = str(idempotency_key or "").strip()
    if not normalized_key:
        return None

    database_delivery, database_authoritative = (
        _load_database_internal_event_delivery_by_idempotency_key(normalized_key)
    )
    if database_authoritative:
        if database_delivery is None:
            _evict_cached_internal_event_delivery(idempotency_key=normalized_key)
            return None
        return _cache_internal_event_delivery(database_delivery)

    delivery_id = _INTERNAL_EVENT_DELIVERIES_BY_KEY.get(normalized_key)
    if not delivery_id:
        return None
    cached_delivery = _INTERNAL_EVENT_DELIVERIES_BY_ID.get(delivery_id)
    if cached_delivery is None:
        return None
    return store.clone(cached_delivery)


def _get_internal_event_delivery(delivery_id: str | None) -> dict | None:
    normalized_delivery_id = str(delivery_id or "").strip()
    if not normalized_delivery_id:
        return None

    database_delivery, database_authoritative = _load_database_internal_event_delivery(
        normalized_delivery_id
    )
    if database_authoritative:
        if database_delivery is None:
            _evict_cached_internal_event_delivery(delivery_id=normalized_delivery_id)
            return None
        return _cache_internal_event_delivery(database_delivery)

    cached_delivery = _INTERNAL_EVENT_DELIVERIES_BY_ID.get(normalized_delivery_id)
    if cached_delivery is None:
        return None
    return store.clone(cached_delivery)


def _internal_event_delivery_matches(
    delivery: dict,
    *,
    status_filter: str | None = None,
    event_name: str | None = None,
) -> bool:
    normalized_status = str(status_filter or "").strip().lower()
    if normalized_status and str(delivery.get("status") or "").strip().lower() != normalized_status:
        return False

    normalized_event = _normalize_internal_event(event_name)
    if normalized_event and str(delivery.get("event_name") or "").strip().lower() != normalized_event:
        return False

    return True


def _internal_event_delivery_sort_key(delivery: dict) -> tuple[datetime, str]:
    for field in ("updated_at", "delivered_at", "created_at"):
        parsed = _parse_datetime(str(delivery.get(field) or ""))
        if parsed is not None:
            return parsed, str(delivery.get("id") or "")
    return datetime.min.replace(tzinfo=UTC), str(delivery.get("id") or "")


def _hydrate_internal_event_delivery(delivery: dict) -> dict:
    hydrated = store.clone(delivery)
    hydrated["payload"] = store.clone(hydrated.get("payload") or {})
    hydrated["attempt_count"] = int(hydrated.get("attempt_count") or 0)
    hydrated["triggered_count"] = int(hydrated.get("triggered_count") or 0)
    hydrated["triggered_workflow_ids"] = [str(item) for item in hydrated.get("triggered_workflow_ids") or []]
    hydrated["triggered_run_ids"] = [str(item) for item in hydrated.get("triggered_run_ids") or []]
    hydrated["triggered_task_ids"] = [str(item) for item in hydrated.get("triggered_task_ids") or []]

    if isinstance(hydrated.get("primary_workflow"), dict) or hydrated["triggered_workflow_ids"]:
        workflow_snapshot = (
            store.clone(hydrated["primary_workflow"])
            if isinstance(hydrated.get("primary_workflow"), dict)
            else None
        )
        try:
            hydrated["primary_workflow"] = _load_primary_workflow_for_delivery(
                hydrated,
                ignore_stale_snapshot_on_database_miss=True,
            )
        except HTTPException as exc:
            if exc.status_code == status.HTTP_404_NOT_FOUND:
                hydrated["primary_workflow"] = None
            else:
                hydrated["primary_workflow"] = workflow_snapshot
    else:
        hydrated["primary_workflow"] = None

    return hydrated


def _build_internal_event_replay_idempotency_key(delivery: dict) -> str:
    normalized_event = _normalize_internal_event(delivery.get("event_name")) or "internal-event"
    source_delivery_id = str(delivery.get("id") or uuid4().hex[:12]).strip() or uuid4().hex[:12]
    replay_suffix = uuid4().hex[:8]
    return f"{normalized_event[:96]}:replay:{source_delivery_id[:64]}:{replay_suffix}"


def _list_internal_event_deliveries(
    *,
    status_filter: str | None = None,
    event_name: str | None = None,
) -> list[dict]:
    items_by_id: dict[str, dict] = {}
    persisted_items: list[dict] | None = None
    persistence_enabled = bool(getattr(persistence_service, "enabled", False))

    list_deliveries = getattr(persistence_service, "list_internal_event_deliveries", None)
    if callable(list_deliveries):
        persisted_items = list_deliveries(status=status_filter, event_name=event_name)
        if persisted_items is not None:
            for persisted in persisted_items:
                cached = _cache_internal_event_delivery(persisted)
                items_by_id[str(cached["id"])] = cached

    if persisted_items is None:
        if persistence_enabled:
            return []
        for cached in _INTERNAL_EVENT_DELIVERIES_BY_ID.values():
            delivery = store.clone(cached)
            if not _internal_event_delivery_matches(
                delivery,
                status_filter=status_filter,
                event_name=event_name,
            ):
                continue
            items_by_id.setdefault(str(delivery["id"]), delivery)

    deliveries = [_hydrate_internal_event_delivery(item) for item in items_by_id.values()]
    deliveries.sort(key=_internal_event_delivery_sort_key, reverse=True)
    return deliveries


def _load_primary_workflow_for_delivery(
    delivery: dict,
    *,
    ignore_stale_snapshot_on_database_miss: bool = False,
) -> dict:
    workflow_snapshot = delivery.get("primary_workflow")
    snapshot_payload = (
        store.clone(workflow_snapshot)
        if isinstance(workflow_snapshot, dict) and workflow_snapshot
        else None
    )
    snapshot_workflow_id = str((snapshot_payload or {}).get("id") or "").strip()

    candidate_workflow_ids = [
        workflow_id
        for workflow_id in [snapshot_workflow_id, *(
            str(item).strip()
            for item in (delivery.get("triggered_workflow_ids") or [])
        )]
        if workflow_id
    ]
    candidate_workflow_ids = list(dict.fromkeys(candidate_workflow_ids))
    if not candidate_workflow_ids and snapshot_payload is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal event delivery missing primary workflow context",
        )

    database_authoritative_checked = False
    for workflow_id in candidate_workflow_ids:
        database_workflow, database_authoritative = _load_database_workflow(workflow_id)
        if database_authoritative:
            database_authoritative_checked = True
            if database_workflow is not None:
                return store.clone(_sync_cached_workflow(database_workflow))
            continue

    if database_authoritative_checked and ignore_stale_snapshot_on_database_miss:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    if snapshot_payload is not None:
        return snapshot_payload

    for workflow_id in candidate_workflow_ids:
        cached_workflow = _find_cached_workflow(workflow_id)
        if cached_workflow is not None:
            return store.clone(cached_workflow)

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")


def _internal_delivery_message(triggered_count: int, *, deduplicated: bool) -> str:
    if deduplicated:
        return "Workflow internal delivery deduplicated"
    if triggered_count > 1:
        return "Workflow internal fan-out accepted"
    return "Workflow internal trigger accepted"


def _is_internal_trigger_not_found_error(exc: Exception) -> bool:
    return (
        isinstance(exc, HTTPException)
        and exc.status_code == status.HTTP_404_NOT_FOUND
        and str(exc.detail) == WORKFLOW_INTERNAL_TRIGGER_NOT_FOUND_DETAIL
    )


def _build_internal_event_delivery_response(
    delivery: dict,
    *,
    deduplicated: bool,
) -> dict:
    triggered_workflow_ids = list(delivery.get("triggered_workflow_ids") or [])
    triggered_run_ids = list(delivery.get("triggered_run_ids") or [])
    triggered_task_ids = list(delivery.get("triggered_task_ids") or [])
    delivery_status = str(delivery.get("status") or "").strip().lower()
    if delivery_status == INTERNAL_EVENT_STATUS_IGNORED and not triggered_workflow_ids:
        workflow = None
    else:
        try:
            workflow = _load_primary_workflow_for_delivery(
                delivery,
                ignore_stale_snapshot_on_database_miss=True,
            )
        except HTTPException as exc:
            if exc.status_code == status.HTTP_404_NOT_FOUND:
                workflow = None
            else:
                raise
    run_id = triggered_run_ids[0] if triggered_run_ids else None
    task_id = triggered_task_ids[0] if triggered_task_ids else None
    if delivery_status == INTERNAL_EVENT_STATUS_IGNORED:
        message = "Workflow internal delivery closed without matching trigger"
    else:
        message = _internal_delivery_message(len(triggered_workflow_ids), deduplicated=deduplicated)
    return {
        "ok": True,
        "message": message,
        "workflow": workflow,
        "run_id": run_id,
        "task_id": task_id,
        "triggered_count": len(triggered_workflow_ids),
        "triggered_workflow_ids": triggered_workflow_ids,
        "triggered_run_ids": triggered_run_ids,
        "triggered_task_ids": triggered_task_ids,
        "internal_event_id": str(delivery.get("id") or ""),
        "internal_event_status": str(delivery.get("status") or ""),
        "internal_event_attempt_count": int(delivery.get("attempt_count") or 0),
        "deduplicated": deduplicated,
    }


def _normalize_trigger(trigger: dict | str | None) -> dict:
    normalized = store.clone(DEFAULT_TRIGGER)
    if not trigger:
        return normalized

    if isinstance(trigger, str):
        trigger_type, _, pattern = trigger.partition(".")
        normalized["type"] = _normalize_trigger_type(trigger_type or normalized["type"])
        if normalized["type"] == "schedule":
            normalized["cron"] = pattern or None
            normalized["keyword"] = None
            normalized["internal_event"] = None
        elif normalized["type"] == "webhook":
            normalized["webhook_path"] = _normalize_webhook_path(pattern)
            normalized["keyword"] = None
            normalized["internal_event"] = None
        elif normalized["type"] == "internal":
            normalized["internal_event"] = _normalize_internal_event(pattern)
            normalized["keyword"] = None
            normalized["cron"] = None
            normalized["webhook_path"] = None
        else:
            normalized["keyword"] = pattern or normalized["keyword"]
            normalized["cron"] = None
            normalized["webhook_path"] = None
            normalized["internal_event"] = None
        return normalized

    normalized["type"] = _normalize_trigger_type(trigger.get("type") or normalized["type"])
    normalized["keyword"] = trigger.get("keyword")
    normalized["cron"] = _normalize_trigger_cron(trigger.get("cron"))
    normalized["webhook_path"] = trigger.get("webhook_path")
    normalized["description"] = trigger.get("description") or normalized["description"]
    normalized["priority"] = _normalize_trigger_priority(trigger.get("priority"))
    normalized["channels"] = _normalize_trigger_channels(trigger.get("channels"))
    normalized["preferred_language"] = _normalize_preferred_language(
        trigger.get("preferred_language") or trigger.get("preferredLanguage")
    )
    normalized["step_delay_seconds"] = _normalize_positive_float(
        trigger.get("step_delay_seconds") or trigger.get("stepDelaySeconds"),
        default=float(DEFAULT_TRIGGER["step_delay_seconds"]),
    )
    normalized["max_dispatch_retry"] = _normalize_positive_int(
        trigger.get("max_dispatch_retry") or trigger.get("maxDispatchRetry"),
        default=int(DEFAULT_TRIGGER["max_dispatch_retry"]),
    )
    normalized["dispatch_retry_backoff_seconds"] = _normalize_positive_float(
        trigger.get("dispatch_retry_backoff_seconds")
        or trigger.get("dispatchRetryBackoffSeconds"),
        default=float(DEFAULT_TRIGGER["dispatch_retry_backoff_seconds"]),
    )
    normalized["execution_timeout_seconds"] = _normalize_positive_float(
        trigger.get("execution_timeout_seconds") or trigger.get("executionTimeoutSeconds"),
        default=float(DEFAULT_TRIGGER["execution_timeout_seconds"]),
    )
    normalized["natural_language_rule"] = (
        str(trigger.get("natural_language_rule") or trigger.get("naturalLanguageRule") or "").strip()
        or None
    )
    raw_schedule_plan = trigger.get("schedule_plan") or trigger.get("schedulePlan")
    normalized["schedule_plan"] = store.clone(raw_schedule_plan) if isinstance(raw_schedule_plan, dict) else None
    normalized["webhook_path"] = _normalize_webhook_path(normalized.get("webhook_path"))
    raw_internal_event = trigger.get("internal_event") or trigger.get("internalEvent")
    if normalized["type"] == "internal" and not raw_internal_event:
        raw_internal_event = trigger.get("description")
    normalized["internal_event"] = (
        _normalize_internal_event(raw_internal_event)
        if normalized["type"] == "internal"
        else None
    )
    return normalized


def _collect_agent_bindings(nodes: list[dict]) -> list[str]:
    bindings = [
        str(node["agent_id"])
        for node in nodes
        if node.get("agent_id") not in {None, ""}
    ]
    return list(dict.fromkeys(bindings))


def _next_workflow_id() -> str:
    workflows = store.clone(store.workflows)
    database_workflows = persistence_service.list_workflows()
    if database_workflows is not None:
        workflows.extend(database_workflows)

    numeric_ids = [
        int(workflow_id.rsplit("-", maxsplit=1)[-1])
        for workflow in workflows
        if (workflow_id := str(workflow.get("id") or "")).startswith("workflow-")
        and workflow_id.rsplit("-", maxsplit=1)[-1].isdigit()
    ]
    numeric_ids.extend(
        int(workflow_id.rsplit("-", maxsplit=1)[-1])
        for workflow_id in LEGACY_WORKFLOW_IDS
        if workflow_id.startswith("workflow-") and workflow_id.rsplit("-", maxsplit=1)[-1].isdigit()
    )
    return f"workflow-{max(numeric_ids, default=0) + 1}"


def _find_cached_workflow(workflow_id: str) -> dict | None:
    for workflow in store.workflows:
        if workflow["id"] == workflow_id:
            return workflow
    return None


def _sync_cached_workflow(workflow: dict) -> dict:
    workflow_id = str(workflow["id"])
    cached_workflow = _find_cached_workflow(workflow_id)
    cloned_workflow = store.clone(workflow)
    if cached_workflow is not None:
        cached_workflow.clear()
        cached_workflow.update(cloned_workflow)
        return cached_workflow

    store.workflows.append(cloned_workflow)
    return store.workflows[-1]


def _load_database_workflow(workflow_id: str) -> tuple[dict | None, bool]:
    if not getattr(persistence_service, "enabled", False):
        return None, False

    database_workflow = persistence_service.get_workflow(workflow_id)
    if database_workflow is not None:
        return database_workflow, True

    database_workflows = persistence_service.list_workflows()
    if database_workflows is None:
        return None, True

    for candidate in database_workflows:
        if str(candidate.get("id") or "").strip() == workflow_id:
            return candidate, True
    return None, True


def _find_workflow_mutable(workflow_id: str) -> dict:
    if str(workflow_id or "").strip() in LEGACY_WORKFLOW_IDS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    database_workflow, database_authoritative = _load_database_workflow(workflow_id)
    if database_authoritative:
        if database_workflow is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
        return _sync_cached_workflow(database_workflow)

    cached_workflow = _find_cached_workflow(workflow_id)
    if cached_workflow is not None:
        return cached_workflow

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")


def _persist_workflow(workflow: dict | None) -> None:
    if workflow is None:
        return
    if bool(workflow.get("_legacy_hidden_compatibility")):
        return

    persist_workflow_state = getattr(persistence_service, "persist_workflow_state", None)
    if callable(persist_workflow_state):
        if persist_workflow_state(workflow=workflow):
            return
        if getattr(persistence_service, "enabled", False):
            return

    persistence_service.persist_runtime_state()


def _mark_workflow_running(workflow: dict) -> None:
    workflow["status"] = "running"
    workflow["updated_at"] = store.now_string()


def _workflow_run_trigger_type(run: dict) -> str:
    trigger = str(run.get("trigger") or "").strip().lower()
    if not trigger:
        return "manual"
    if trigger.startswith("api.messages") or trigger in {"message", "message_dispatch"}:
        return "message"
    if trigger.startswith("task.retry"):
        return "manual"
    if ":" in trigger:
        return trigger.split(":", maxsplit=1)[0]
    return trigger


def _workflow_run_dispatch_context(run: dict) -> dict | None:
    dispatch_context = run.get("dispatch_context")
    return dispatch_context if isinstance(dispatch_context, dict) else None


def _workflow_run_dispatch_state(run: dict) -> str | None:
    dispatch_context = _workflow_run_dispatch_context(run)
    if not isinstance(dispatch_context, dict):
        return None

    for key in ("state", "dispatch_state", "dispatchState"):
        value = str(dispatch_context.get(key) or "").strip().lower()
        if value:
            return value
    return None


def _workflow_run_dispatch_value(run: dict, *keys: str) -> str | None:
    dispatch_context = _workflow_run_dispatch_context(run)
    if not isinstance(dispatch_context, dict):
        return None

    for key in keys:
        value = str(dispatch_context.get(key) or "").strip()
        if value:
            return value
    return None


def _workflow_run_status_reason(run: dict) -> str | None:
    dispatch_state = _workflow_run_dispatch_state(run)
    failure_stage = _workflow_run_dispatch_value(run, "failure_stage", "failureStage")
    failure_message = _workflow_run_dispatch_value(run, "failure_message", "failureMessage")
    delivery_status = _workflow_run_dispatch_value(run, "delivery_status", "deliveryStatus")
    delivery_message = _workflow_run_dispatch_value(run, "delivery_message", "deliveryMessage")
    status_value = str(run.get("status") or "").strip().lower()

    if status_value == "failed" and failure_stage:
        if failure_message:
            return f"{failure_stage}: {failure_message}"
        return failure_stage
    if delivery_status == "failed":
        return delivery_message or "channel outbound failed"
    if delivery_status == "skipped":
        return delivery_message or "channel outbound skipped"
    if status_value in {"pending", "running"} and dispatch_state:
        return dispatch_state
    return None


def _workflow_run_execution_agent_id(run: dict) -> str | None:
    dispatch_context = dispatch_context_from_run(run)
    if dispatch_context is None:
        return None

    route_decision = route_decision_from_payload(dispatch_context) or {}
    return alias_text(dispatch_context, "execution_agent_id", "executionAgentId") or alias_text(
        route_decision,
        "execution_agent_id",
        "executionAgentId",
    )


def _workflow_run_policy(run: dict) -> dict:
    dispatch_context = _workflow_run_dispatch_context(run)
    if not isinstance(dispatch_context, dict):
        return {}

    policy = dispatch_context.get("workflow_policy")
    if not isinstance(policy, dict):
        policy = dispatch_context.get("workflowPolicy")
    if not isinstance(policy, dict):
        return {}

    return {
        "step_delay_seconds": _normalize_positive_float(
            policy.get("step_delay_seconds") or policy.get("stepDelaySeconds"),
            default=float(DEFAULT_TRIGGER["step_delay_seconds"]),
        ),
        "max_dispatch_retry": _normalize_positive_int(
            policy.get("max_dispatch_retry") or policy.get("maxDispatchRetry"),
            default=int(DEFAULT_TRIGGER["max_dispatch_retry"]),
        ),
        "dispatch_retry_backoff_seconds": _normalize_positive_float(
            policy.get("dispatch_retry_backoff_seconds")
            or policy.get("dispatchRetryBackoffSeconds"),
            default=float(DEFAULT_TRIGGER["dispatch_retry_backoff_seconds"]),
        ),
        "execution_timeout_seconds": _normalize_positive_float(
            policy.get("execution_timeout_seconds") or policy.get("executionTimeoutSeconds"),
            default=float(DEFAULT_TRIGGER["execution_timeout_seconds"]),
        ),
    }


def _workflow_run_has_active_claim(run: dict, *, now: datetime) -> bool:
    dispatcher_id = str(run.get("dispatcher_id") or "").strip()
    lease_expires_at = _parse_datetime(str(run.get("dispatch_lease_expires_at") or ""))
    return bool(dispatcher_id and lease_expires_at is not None and lease_expires_at > now)


def _workflow_run_claim_is_stale(run: dict, *, now: datetime) -> bool:
    dispatcher_id = str(run.get("dispatcher_id") or "").strip()
    if not dispatcher_id:
        return False

    lease_expires_at = _parse_datetime(str(run.get("dispatch_lease_expires_at") or ""))
    if lease_expires_at is None:
        return False
    return lease_expires_at <= now


def _workflow_run_execution_has_timed_out(run: dict, *, now: datetime) -> bool:
    dispatch_context = _workflow_run_dispatch_context(run) or {}
    dispatch_state = _workflow_run_dispatch_state(run)
    status_value = str(run.get("status") or "").strip().lower()
    if status_value in {"completed", "cancelled"}:
        return False
    if status_value not in {"running", "failed"} and dispatch_state not in {
        "dispatched",
        "executing",
        "running",
        "execution_timeout",
    }:
        return False

    policy = _workflow_run_policy(run)
    if not policy:
        return False
    timeout_seconds = _normalize_positive_float(
        policy.get("execution_timeout_seconds"),
        default=float(DEFAULT_TRIGGER["execution_timeout_seconds"]),
    )
    started_at = _parse_datetime(
        str(
            dispatch_context.get("dispatched_at")
            or dispatch_context.get("dispatchedAt")
            or run.get("started_at")
            or run.get("updated_at")
            or run.get("created_at")
            or ""
        )
    )
    if started_at is None:
        return False
    return started_at.timestamp() + timeout_seconds <= now.timestamp()


def _workflow_run_monitor_state(run: dict, *, now: datetime) -> str:
    status_value = str(run.get("status") or "").strip().lower()
    dispatch_state = _workflow_run_dispatch_state(run)
    if status_value == "completed":
        return status_value
    if status_value == "cancelled":
        return status_value
    if status_value == "failed" and dispatch_state == "execution_timeout":
        return "execution_timeout"
    if status_value == "failed":
        return status_value

    next_dispatch_at = _parse_datetime(str(run.get("next_dispatch_at") or ""))
    dispatch_failure_count = max(int(run.get("dispatch_failure_count") or 0), 0)
    has_active_claim = _workflow_run_has_active_claim(run, now=now)

    if _workflow_run_execution_has_timed_out(run, now=now):
        return "execution_timeout"

    if _workflow_run_claim_is_stale(run, now=now):
        return "claimed_stale"

    if has_active_claim:
        return "claimed"

    if next_dispatch_at is not None:
        if next_dispatch_at <= now and not has_active_claim:
            return "overdue"
        if dispatch_failure_count > 0:
            return "retry_waiting"
        if next_dispatch_at > now:
            return "scheduled"

    if status_value == "running" or dispatch_state in {"dispatched", "executing", "running"}:
        return "running"

    if dispatch_failure_count > 0:
        return "retry_waiting"

    if status_value == "pending" or dispatch_state == "queued":
        return "queued"

    return status_value or "queued"


def _workflow_run_next_action(monitor_state: str) -> str:
    if monitor_state in {"completed", "failed", "cancelled"}:
        return "none"
    if monitor_state == "execution_timeout":
        return "investigate_timeout"
    if monitor_state == "scheduled":
        return "wait_for_schedule"
    if monitor_state == "retry_waiting":
        return "retry_dispatch"
    if monitor_state == "claimed_stale":
        return "reclaim_dispatch"
    if monitor_state in {"queued", "overdue"}:
        return "dispatch"
    if monitor_state == "claimed":
        return "await_dispatch"
    if monitor_state == "running":
        return "await_worker"
    return "none"


def _attach_run_monitor(run: dict, *, now: datetime | None = None) -> dict:
    monitor_now = now or datetime.now(UTC)
    enriched = store.clone(run)
    warnings = enriched.get("warnings")
    normalized_warnings = (
        [str(item).strip() for item in warnings if str(item).strip()]
        if isinstance(warnings, list)
        else []
    )
    next_dispatch_at = str(enriched.get("next_dispatch_at") or "").strip() or None
    next_dispatch_at_value = _parse_datetime(next_dispatch_at) if next_dispatch_at else None
    monitor_state = _workflow_run_monitor_state(enriched, now=monitor_now)

    enriched["monitor"] = {
        "trigger_type": _workflow_run_trigger_type(enriched),
        "dispatch_state": _workflow_run_dispatch_state(enriched),
        "monitor_state": monitor_state,
        "next_action": _workflow_run_next_action(monitor_state),
        "next_dispatch_at": next_dispatch_at,
        "is_overdue": bool(next_dispatch_at_value is not None and next_dispatch_at_value <= monitor_now),
        "dispatcher_id": str(enriched.get("dispatcher_id") or "").strip() or None,
        "dispatch_claimed_at": str(enriched.get("dispatch_claimed_at") or "").strip() or None,
        "dispatch_lease_expires_at": str(enriched.get("dispatch_lease_expires_at") or "").strip()
        or None,
        "dispatch_failure_count": max(int(enriched.get("dispatch_failure_count") or 0), 0),
        "last_dispatch_error": str(enriched.get("last_dispatch_error") or "").strip() or None,
        "execution_agent_id": _workflow_run_execution_agent_id(enriched),
        "warning_count": len(normalized_warnings),
        "latest_warning": normalized_warnings[-1] if normalized_warnings else None,
    }
    enriched["failure_stage"] = _workflow_run_dispatch_value(enriched, "failure_stage", "failureStage")
    enriched["failure_message"] = _workflow_run_dispatch_value(enriched, "failure_message", "failureMessage")
    enriched["delivery_status"] = _workflow_run_dispatch_value(enriched, "delivery_status", "deliveryStatus")
    enriched["delivery_message"] = _workflow_run_dispatch_value(enriched, "delivery_message", "deliveryMessage")
    enriched["status_reason"] = _workflow_run_status_reason(enriched)
    return enriched


def _run_is_unhealthy(run: dict) -> bool:
    monitor = run.get("monitor")
    if not isinstance(monitor, dict):
        return False
    return str(monitor.get("monitor_state") or "") in {
        "failed",
        "retry_waiting",
        "overdue",
        "claimed_stale",
        "execution_timeout",
    }


def _build_workflow_monitor_stats(items: list[dict]) -> dict:
    stats = {
        "total": len(items),
        "queued": 0,
        "scheduled": 0,
        "claimed": 0,
        "claimed_stale": 0,
        "running": 0,
        "retry_waiting": 0,
        "overdue": 0,
        "execution_timeout": 0,
        "failed": 0,
        "completed": 0,
        "cancelled": 0,
        "unhealthy": 0,
    }

    for item in items:
        monitor = item.get("monitor")
        if not isinstance(monitor, dict):
            continue

        state = str(monitor.get("monitor_state") or "").strip()
        if state in stats:
            stats[state] += 1
        if state in {"failed", "retry_waiting", "overdue", "claimed_stale", "execution_timeout"}:
            stats["unhealthy"] += 1

    return stats


def _build_workflow_monitor_alerts(stats: dict) -> list[str]:
    alerts: list[str] = []
    if int(stats.get("overdue") or 0) > 0:
        alerts.append(
            f"{int(stats['overdue'])} 个运行已超过计划调度时间，等待 dispatcher 拉起"
        )
    if int(stats.get("retry_waiting") or 0) > 0:
        alerts.append(
            f"{int(stats['retry_waiting'])} 个运行处于失败重试等待态，需要关注调度链路"
        )
    if int(stats.get("claimed_stale") or 0) > 0:
        alerts.append(
            f"{int(stats['claimed_stale'])} 个运行存在过期 claim，建议检查 dispatcher 存活与 lease 回收"
        )
    if int(stats.get("execution_timeout") or 0) > 0:
        alerts.append(
            f"{int(stats['execution_timeout'])} 个运行已触发执行超时，需要排查执行链路或放宽超时策略"
        )
    if int(stats.get("failed") or 0) > 0:
        alerts.append(f"{int(stats['failed'])} 个运行已经失败，可进入运行历史排查")
    return alerts


def _load_workflows() -> list[dict]:
    database_workflows = persistence_service.list_workflows()
    if database_workflows is not None:
        store.workflows = [store.clone(workflow) for workflow in database_workflows]
        return store.workflows
    if getattr(persistence_service, "enabled", False):
        return []
    return store.clone(store.workflows)


def _load_workflows_for_trigger_selection(*, unavailable_mode: str) -> list[dict]:
    database_workflows = persistence_service.list_workflows()
    if database_workflows is not None:
        store.workflows = [store.clone(workflow) for workflow in database_workflows]
        return store.workflows

    if getattr(persistence_service, "enabled", False):
        if unavailable_mode == "raise":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=WORKFLOW_STORAGE_UNAVAILABLE_DETAIL,
            )
        if unavailable_mode == "empty":
            return []

    return store.clone(store.workflows)


def _parse_cron_value(
    raw_value: str,
    *,
    minimum: int,
    maximum: int,
    sunday_alias: bool = False,
) -> int:
    value = int(raw_value)
    if sunday_alias and value == 7:
        value = 0
    if value < minimum or value > maximum:
        raise ValueError(f"Cron value {raw_value} is out of range")
    return value


def _expand_cron_token(
    token: str,
    *,
    minimum: int,
    maximum: int,
    sunday_alias: bool = False,
) -> set[int]:
    normalized = str(token or "").strip()
    if not normalized:
        raise ValueError("Cron token is empty")

    step = 1
    base = normalized
    if "/" in normalized:
        base, step_raw = normalized.split("/", maxsplit=1)
        step = int(step_raw)
        if step <= 0:
            raise ValueError("Cron step must be positive")

    if base == "*":
        start = minimum
        end = maximum
    elif "-" in base:
        start_raw, end_raw = base.split("-", maxsplit=1)
        start = _parse_cron_value(
            start_raw,
            minimum=minimum,
            maximum=maximum,
            sunday_alias=sunday_alias,
        )
        end = _parse_cron_value(
            end_raw,
            minimum=minimum,
            maximum=maximum,
            sunday_alias=sunday_alias,
        )
        if start > end:
            raise ValueError("Cron range start must be <= end")
    else:
        start = _parse_cron_value(
            base,
            minimum=minimum,
            maximum=maximum,
            sunday_alias=sunday_alias,
        )
        end = maximum if "/" in normalized else start

    return set(range(start, end + 1, step))


def _cron_field_matches(
    expression: str,
    value: int,
    *,
    minimum: int,
    maximum: int,
    sunday_alias: bool = False,
) -> bool:
    candidates: set[int] = set()
    for token in str(expression or "").split(","):
        candidates.update(
            _expand_cron_token(
                token,
                minimum=minimum,
                maximum=maximum,
                sunday_alias=sunday_alias,
            )
        )
    return value in candidates


def _cron_matches(expression: str, when: datetime) -> bool | None:
    fields = str(expression or "").split()
    if len(fields) != 5:
        return None

    minute_field, hour_field, day_field, month_field, weekday_field = fields
    cron_weekday = (when.weekday() + 1) % 7

    try:
        minute_matches = _cron_field_matches(
            minute_field,
            when.minute,
            minimum=0,
            maximum=59,
        )
        hour_matches = _cron_field_matches(
            hour_field,
            when.hour,
            minimum=0,
            maximum=23,
        )
        month_matches = _cron_field_matches(
            month_field,
            when.month,
            minimum=1,
            maximum=12,
        )
        day_matches = _cron_field_matches(
            day_field,
            when.day,
            minimum=1,
            maximum=31,
        )
        weekday_matches = _cron_field_matches(
            weekday_field,
            cron_weekday,
            minimum=0,
            maximum=6,
            sunday_alias=True,
        )
    except ValueError:
        return None

    day_is_wildcard = day_field == "*"
    weekday_is_wildcard = weekday_field == "*"
    if day_is_wildcard and weekday_is_wildcard:
        calendar_matches = True
    elif day_is_wildcard:
        calendar_matches = weekday_matches
    elif weekday_is_wildcard:
        calendar_matches = day_matches
    else:
        calendar_matches = day_matches or weekday_matches

    return minute_matches and hour_matches and month_matches and calendar_matches


def _schedule_slot(value: datetime | None = None) -> datetime:
    reference = value or datetime.now(UTC)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)
    return reference.astimezone(UTC).replace(second=0, microsecond=0)


def _schedule_slot_label(scheduled_for: datetime) -> str:
    return scheduled_for.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _schedule_slot_trigger(scheduled_for: datetime) -> str:
    return f"schedule:{scheduled_for.astimezone(UTC).isoformat()}"


def _schedule_task_title(workflow: dict, scheduled_for: datetime) -> str:
    return f"定时触发 - {workflow['name']} - {_schedule_slot_label(scheduled_for)}"


def _schedule_context_lines(cron: str | None, scheduled_for: datetime) -> list[str]:
    lines = [f"调度时间: {_schedule_slot_label(scheduled_for)}"]
    if cron:
        lines.append(f"Cron 表达式: {cron}")
    return lines


def _schedule_task_description(workflow: dict, cron: str | None, scheduled_for: datetime) -> str:
    base_description = str(workflow.get("description") or "").strip()
    lines = [base_description, *_schedule_context_lines(cron, scheduled_for)]
    return "\n".join(line for line in lines if line)


def _workflow_has_schedule_run(workflow_id: str, slot_trigger: str) -> bool:
    runs = list_workflow_runs(workflow_id=workflow_id)
    return any(str(run.get("trigger") or "").strip() == slot_trigger for run in runs["items"])


def _webhook_task_title(workflow: dict, payload: dict | None) -> str:
    sanitized_payload = sanitize_webhook_payload(payload or {})
    title_hint = str(
        (sanitized_payload or {}).get("title") or (sanitized_payload or {}).get("event") or ""
    ).strip()
    if title_hint:
        return f"Webhook 触发 - {workflow['name']} - {title_hint[:48]}"
    return f"Webhook 触发 - {workflow['name']}"


def _webhook_context_lines(trigger_path: str, payload: dict | None) -> list[str]:
    lines = [f"Webhook 路径: {trigger_path.strip('/')}"]
    sanitized_payload = sanitize_webhook_payload(payload)
    if not isinstance(sanitized_payload, dict):
        lines.append("Payload: 空请求体")
        return lines

    event_name = str(sanitized_payload.get("event") or sanitized_payload.get("type") or "").strip()
    if event_name:
        lines.append(f"Webhook 事件: {event_name[:120]}")

    field_names = [str(key).strip() for key in sanitized_payload if str(key).strip()]
    if field_names:
        lines.append(f"Payload 字段: {', '.join(field_names[:8])}")
    else:
        lines.append("Payload 字段: (empty object)")
    return lines


def _webhook_task_description(workflow: dict, trigger_path: str, payload: dict | None) -> str:
    base_description = str(workflow.get("description") or "").strip()
    lines = [base_description, *_webhook_context_lines(trigger_path, payload)]
    return "\n".join(line for line in lines if line)


def _internal_task_title(
    workflow: dict,
    event_name: str,
    payload: dict | None,
    source: str | None = None,
) -> str:
    title_hint = str(
        (payload or {}).get("title") or source or (payload or {}).get("source") or ""
    ).strip()
    if title_hint:
        return f"内部触发 - {workflow['name']} - {title_hint[:48]}"
    return f"内部触发 - {workflow['name']} - {event_name[:48]}"


def _internal_context_lines(
    event_name: str,
    payload: dict | None,
    source: str | None = None,
) -> list[str]:
    lines = [f"内部事件: {event_name}"]
    source_label = str(source or (payload or {}).get("source") or "").strip()
    if source_label:
        lines.append(f"事件来源: {source_label[:120]}")

    if not isinstance(payload, dict):
        lines.append("Payload: 空请求体")
        return lines

    field_names = [
        str(key).strip()
        for key in payload
        if str(key).strip() and str(key).strip() != "source"
    ]
    if field_names:
        lines.append(f"Payload 字段: {', '.join(field_names[:8])}")
    else:
        lines.append("Payload 字段: (empty object)")
    return lines


def _internal_task_description(
    workflow: dict,
    event_name: str,
    payload: dict | None,
    source: str | None = None,
) -> str:
    base_description = str(workflow.get("description") or "").strip()
    lines = [base_description, *_internal_context_lines(event_name, payload, source)]
    return "\n".join(line for line in lines if line)


def _select_workflow_for_webhook(trigger_path: str) -> tuple[dict, str]:
    normalized_path = _normalize_webhook_path(trigger_path)
    if not normalized_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow webhook not found")

    matched_workflow: dict | None = None
    matched_priority: int | None = None
    matched_index: int | None = None

    for index, workflow in enumerate(
        _load_workflows_for_trigger_selection(unavailable_mode="raise")
    ):
        if str(workflow.get("status") or "").lower() not in {"active", "running"}:
            continue

        trigger = _normalize_trigger(workflow.get("trigger"))
        if str(trigger.get("type") or "").strip().lower() != "webhook":
            continue
        if _normalize_webhook_path(trigger.get("webhook_path")) != normalized_path:
            continue

        priority = _normalize_trigger_priority(trigger.get("priority"))
        if (
            matched_workflow is None
            or priority > int(matched_priority or 0)
            or (
                priority == matched_priority
                and index < int(matched_index or index + 1)
            )
        ):
            matched_workflow = workflow
            matched_priority = priority
            matched_index = index

    if matched_workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow webhook not found")

    return _sync_cached_workflow(matched_workflow), normalized_path


def _select_workflows_for_internal_event(event_name: str) -> tuple[list[dict], str]:
    normalized_event = _normalize_internal_event(event_name)
    if not normalized_event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=WORKFLOW_INTERNAL_TRIGGER_NOT_FOUND_DETAIL,
        )

    matches: list[tuple[int, int, dict]] = []

    for index, workflow in enumerate(
        _load_workflows_for_trigger_selection(unavailable_mode="raise")
    ):
        if str(workflow.get("status") or "").lower() not in {"active", "running"}:
            continue

        trigger = _normalize_trigger(workflow.get("trigger"))
        if str(trigger.get("type") or "").strip().lower() != "internal":
            continue
        if _normalize_internal_event(trigger.get("internal_event")) != normalized_event:
            continue

        priority = _normalize_trigger_priority(trigger.get("priority"))
        matches.append((priority, index, workflow))

    if not matches:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=WORKFLOW_INTERNAL_TRIGGER_NOT_FOUND_DETAIL,
        )

    matches.sort(key=lambda item: (-item[0], item[1]))
    return [
        _sync_cached_workflow(workflow)
        for _, _, workflow in matches
    ], normalized_event


def has_internal_event_subscribers(event_name: str) -> bool:
    try:
        workflows, _ = _select_workflows_for_internal_event(event_name)
    except Exception as exc:
        if _is_internal_trigger_not_found_error(exc):
            return False
        raise
    return bool(workflows)


def list_workflows() -> dict:
    database_workflows = persistence_service.list_workflows()
    if database_workflows is not None:
        items = database_workflows
    elif getattr(persistence_service, "enabled", False):
        items = []
    else:
        items = store.clone(store.workflows)
    items = [
        workflow
        for workflow in items
        if str(workflow.get("id") or "").strip() not in LEGACY_WORKFLOW_IDS
    ]
    items = sorted(
        items,
        key=lambda workflow: (
            WORKFLOW_LIST_PRIORITY_BY_ID.get(str(workflow.get("id") or "").strip(), 100),
            str(workflow.get("name") or "").strip(),
        ),
    )
    return {"items": items, "total": len(items)}


def create_workflow(payload: dict) -> dict:
    workflow_id = _next_workflow_id()
    workflow = {
        "id": workflow_id,
        "name": payload["name"],
        "description": payload["description"],
        "version": payload["version"],
        "status": payload["status"],
        "updated_at": store.now_string(),
        "node_count": len(payload["nodes"]),
        "edge_count": len(payload["edges"]),
        "nodes": payload["nodes"],
        "edges": payload["edges"],
        "trigger": _normalize_trigger(payload.get("trigger")),
        "agent_bindings": _collect_agent_bindings(payload["nodes"]),
    }
    store.workflows.append(workflow)
    _persist_workflow(workflow)
    return {"ok": True, "message": "Workflow created", "workflow": store.clone(workflow)}


def update_workflow(workflow_id: str, payload: dict) -> dict:
    workflow = _find_workflow_mutable(workflow_id)
    workflow.update(
        {
            "name": payload["name"],
            "description": payload["description"],
            "version": payload["version"],
            "status": payload["status"],
            "updated_at": store.now_string(),
            "node_count": len(payload["nodes"]),
            "edge_count": len(payload["edges"]),
            "nodes": payload["nodes"],
            "edges": payload["edges"],
            "trigger": _normalize_trigger(payload.get("trigger") or workflow.get("trigger")),
            "agent_bindings": _collect_agent_bindings(payload["nodes"]),
        }
    )
    _persist_workflow(workflow)
    return {"ok": True, "message": "Workflow updated", "workflow": store.clone(workflow)}


def run_workflow(workflow_id: str, payload: dict | None = None) -> dict:
    payload = payload or {}
    workflow = _find_workflow_mutable(workflow_id)
    run_bundle = create_manual_workflow_run(
        workflow_id,
        trigger=payload.get("trigger", "manual"),
        intent=payload.get("intent"),
        eager_start=True,
    )
    _mark_workflow_running(workflow)
    _persist_workflow(workflow)
    return {
        "ok": True,
        "message": "Workflow started",
        "workflow": store.clone(workflow),
        "run_id": run_bundle["run"]["id"],
        "task_id": run_bundle["task"]["id"],
    }


def trigger_workflow_webhook(trigger_path: str, payload: dict | None = None) -> dict:
    workflow, normalized_path = _select_workflow_for_webhook(trigger_path)
    payload = payload or {}
    run_bundle = create_manual_workflow_run(
        workflow["id"],
        trigger=f"webhook:{normalized_path}",
        task_title=_webhook_task_title(workflow, payload),
        task_description=_webhook_task_description(workflow, normalized_path, payload),
        trigger_title="Webhook 触发",
        trigger_agent="Webhook Adapter",
        trigger_message=f"已接收 webhook 触发 {normalized_path}，触发上下文摘要已注入任务描述",
    )
    _mark_workflow_running(workflow)
    _persist_workflow(workflow)
    return {
        "ok": True,
        "message": "Workflow webhook accepted",
        "workflow": store.clone(workflow),
        "run_id": run_bundle["run"]["id"],
        "task_id": run_bundle["task"]["id"],
    }


def trigger_workflow_schedule(
    workflow_id: str,
    *,
    scheduled_for: datetime | str,
    cron: str | None = None,
) -> dict:
    if isinstance(scheduled_for, str):
        parsed_schedule = _parse_datetime(scheduled_for)
    else:
        parsed_schedule = scheduled_for
    if parsed_schedule is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid schedule slot")

    normalized_schedule = _schedule_slot(parsed_schedule)
    workflow = _find_workflow_mutable(workflow_id)
    run_bundle = create_manual_workflow_run(
        workflow["id"],
        trigger=_schedule_slot_trigger(normalized_schedule),
        task_title=_schedule_task_title(workflow, normalized_schedule),
        task_description=_schedule_task_description(workflow, cron, normalized_schedule),
        trigger_title="定时触发",
        trigger_agent="Schedule Trigger",
        trigger_message=(
            f"已命中定时表达式 {cron or '(未设置)'}，"
            f"调度窗口为 {_schedule_slot_label(normalized_schedule)}"
        ),
    )
    _mark_workflow_running(workflow)
    _persist_workflow(workflow)
    return {
        "ok": True,
        "message": "Workflow schedule accepted",
        "workflow": store.clone(workflow),
        "run_id": run_bundle["run"]["id"],
        "task_id": run_bundle["task"]["id"],
    }


def trigger_workflow_internal(
    event_name: str,
    payload: dict | None = None,
    *,
    source: str | None = None,
    idempotency_key: str | None = None,
    delivery_id: str | None = None,
) -> dict:
    normalized_event = _normalize_internal_event(event_name)
    if normalized_event is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=WORKFLOW_INTERNAL_TRIGGER_NOT_FOUND_DETAIL,
        )

    payload = store.clone(payload or {})
    resolved_source = _resolve_internal_event_source(source, payload)
    resolved_idempotency_key = _resolve_internal_event_idempotency_key(
        normalized_event,
        payload,
        idempotency_key,
    )
    existing_delivery = _get_internal_event_delivery(delivery_id)
    if existing_delivery is None:
        existing_delivery = _find_internal_event_delivery_by_idempotency_key(resolved_idempotency_key)
    if existing_delivery is not None:
        persisted_key = str(existing_delivery.get("idempotency_key") or "").strip()
        if persisted_key:
            resolved_idempotency_key = persisted_key
    if existing_delivery is not None and str(existing_delivery.get("status") or "") == "delivered":
        return _build_internal_event_delivery_response(existing_delivery, deduplicated=True)

    now_iso = datetime.now(UTC).isoformat()
    delivery = store.clone(existing_delivery or {})
    delivery_id = str(delivery.get("id") or f"evt-{uuid4().hex[:12]}")
    delivery.update(
        {
            "id": delivery_id,
            "event_name": normalized_event,
            "source": resolved_source,
            "payload": payload,
            "idempotency_key": resolved_idempotency_key,
            "status": "pending",
            "attempt_count": int(delivery.get("attempt_count") or 0) + 1,
            "last_error": None,
            "created_at": str(delivery.get("created_at") or now_iso),
            "updated_at": now_iso,
            "delivered_at": delivery.get("delivered_at"),
            "triggered_count": int(delivery.get("triggered_count") or 0),
            "triggered_workflow_ids": list(delivery.get("triggered_workflow_ids") or []),
            "triggered_run_ids": list(delivery.get("triggered_run_ids") or []),
            "triggered_task_ids": list(delivery.get("triggered_task_ids") or []),
            "primary_workflow": store.clone(delivery.get("primary_workflow"))
            if isinstance(delivery.get("primary_workflow"), dict)
            else None,
        }
    )
    delivery = _persist_internal_event_delivery(delivery)
    _publish_internal_event_delivery_event(
        delivery,
        subject=INTERNAL_EVENT_DELIVERY_REQUESTED_SUBJECT,
        event_name="brain.internal_event.delivery.requested",
    )

    triggered_workflow_ids = list(delivery.get("triggered_workflow_ids") or [])
    triggered_run_ids = list(delivery.get("triggered_run_ids") or [])
    triggered_task_ids = list(delivery.get("triggered_task_ids") or [])
    primary_workflow = (
        store.clone(delivery.get("primary_workflow"))
        if isinstance(delivery.get("primary_workflow"), dict)
        else None
    )

    try:
        workflows, normalized_event = _select_workflows_for_internal_event(normalized_event)

        for workflow in workflows:
            workflow_id = str(workflow["id"])
            if workflow_id in triggered_workflow_ids:
                continue

            run_bundle = create_manual_workflow_run(
                workflow["id"],
                trigger=f"internal:{normalized_event}",
                task_title=_internal_task_title(workflow, normalized_event, payload, resolved_source),
                task_description=_internal_task_description(
                    workflow,
                    normalized_event,
                    payload,
                    resolved_source,
                ),
                trigger_title="内部触发",
                trigger_agent=resolved_source,
                trigger_message=(
                    f"已接收内部事件 {normalized_event}，"
                    "触发上下文摘要已注入任务描述"
                ),
                dispatch_context={
                    "internal_event_name": normalized_event,
                    "internal_event_source": resolved_source,
                    "internal_event_payload": store.clone(payload),
                    "internal_event_id": delivery_id,
                    "internal_event_status": "pending",
                },
                eager_start=True,
            )
            _mark_workflow_running(workflow)
            _persist_workflow(workflow)
            triggered_workflow_ids.append(workflow_id)
            triggered_run_ids.append(str(run_bundle["run"]["id"]))
            triggered_task_ids.append(str(run_bundle["task"]["id"]))
            if primary_workflow is None:
                primary_workflow = store.clone(workflow)

        if primary_workflow is None and triggered_workflow_ids:
            primary_workflow = _load_primary_workflow_for_delivery(
                {
                    "triggered_workflow_ids": triggered_workflow_ids,
                    "primary_workflow": delivery.get("primary_workflow"),
                }
            )

        delivery.update(
            {
                "event_name": normalized_event,
                "status": "delivered",
                "updated_at": datetime.now(UTC).isoformat(),
                "delivered_at": datetime.now(UTC).isoformat(),
                "triggered_count": len(triggered_workflow_ids),
                "triggered_workflow_ids": triggered_workflow_ids,
                "triggered_run_ids": triggered_run_ids,
                "triggered_task_ids": triggered_task_ids,
                "primary_workflow": store.clone(primary_workflow) if primary_workflow else None,
            }
        )
        delivery = _persist_internal_event_delivery(delivery)
        _publish_internal_event_delivery_event(
            delivery,
            subject=INTERNAL_EVENT_DELIVERY_COMPLETED_SUBJECT,
            event_name="brain.internal_event.delivery.completed",
            message_type=MESSAGE_TYPE_RESULT,
        )
        return _build_internal_event_delivery_response(delivery, deduplicated=False)
    except Exception as exc:
        if _is_internal_trigger_not_found_error(exc):
            delivery.update(
                {
                    "event_name": normalized_event,
                    "status": INTERNAL_EVENT_STATUS_IGNORED,
                    "updated_at": datetime.now(UTC).isoformat(),
                    "last_error": WORKFLOW_INTERNAL_TRIGGER_NOT_FOUND_DETAIL,
                    "triggered_count": len(triggered_workflow_ids),
                    "triggered_workflow_ids": triggered_workflow_ids,
                    "triggered_run_ids": triggered_run_ids,
                    "triggered_task_ids": triggered_task_ids,
                    "primary_workflow": store.clone(primary_workflow) if primary_workflow else None,
                }
            )
            delivery = _persist_internal_event_delivery(delivery)
            raise
        delivery.update(
            {
                "event_name": normalized_event,
                "status": "failed",
                "updated_at": datetime.now(UTC).isoformat(),
                "last_error": (
                    str(exc.detail)
                    if isinstance(exc, HTTPException)
                    else str(exc)
                ),
                "triggered_count": len(triggered_workflow_ids),
                "triggered_workflow_ids": triggered_workflow_ids,
                "triggered_run_ids": triggered_run_ids,
                "triggered_task_ids": triggered_task_ids,
                "primary_workflow": store.clone(primary_workflow) if primary_workflow else None,
            }
        )
        delivery = _persist_internal_event_delivery(delivery)
        _publish_internal_event_delivery_event(
            delivery,
            subject=INTERNAL_EVENT_DELIVERY_FAILED_SUBJECT,
            event_name="brain.internal_event.delivery.failed",
        )
        raise


def poll_scheduled_workflows(*, now: datetime | None = None) -> dict:
    scheduled_for = _schedule_slot(now)
    summary = {
        "triggered": 0,
        "skipped_existing": 0,
        "skipped_not_due": 0,
        "skipped_recently_updated": 0,
        "invalid_cron": 0,
    }

    for workflow in _load_workflows_for_trigger_selection(unavailable_mode="empty"):
        if str(workflow.get("status") or "").strip().lower() not in {"active", "running"}:
            continue

        trigger = _normalize_trigger(workflow.get("trigger"))
        if str(trigger.get("type") or "").strip().lower() != "schedule":
            continue

        cron = _normalize_trigger_cron(trigger.get("cron"))
        if not cron:
            summary["invalid_cron"] += 1
            continue

        matches = _cron_matches(cron, scheduled_for)
        if matches is None:
            summary["invalid_cron"] += 1
            continue
        if not matches:
            summary["skipped_not_due"] += 1
            continue

        updated_at = _parse_datetime(str(workflow.get("updated_at") or ""))
        if updated_at is not None and updated_at >= scheduled_for:
            summary["skipped_recently_updated"] += 1
            continue

        slot_trigger = _schedule_slot_trigger(scheduled_for)
        if _workflow_has_schedule_run(str(workflow["id"]), slot_trigger):
            summary["skipped_existing"] += 1
            continue

        try:
            trigger_workflow_schedule(
                str(workflow["id"]),
                scheduled_for=scheduled_for,
                cron=cron,
            )
            summary["triggered"] += 1
        except HTTPException:
            raise
        except Exception as exc:  # pragma: no cover - defensive guard for background poller
            logger.warning("Failed to trigger scheduled workflow %s: %s", workflow.get("id"), exc)

    return summary


def list_internal_event_deliveries(
    *,
    status_filter: str | None = None,
    event_name: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    resolved_limit = max(1, min(int(limit or 50), 200))
    resolved_offset = max(int(offset or 0), 0)
    deliveries = _list_internal_event_deliveries(
        status_filter=status_filter,
        event_name=event_name,
    )
    return {
        "items": deliveries[resolved_offset : resolved_offset + resolved_limit],
        "total": len(deliveries),
    }


def get_internal_event_delivery(delivery_id: str) -> dict:
    delivery = _get_internal_event_delivery(delivery_id)
    if delivery is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Internal event delivery not found",
        )
    return _hydrate_internal_event_delivery(delivery)


def retry_internal_event_delivery(delivery_id: str) -> dict:
    delivery = get_internal_event_delivery(delivery_id)
    try:
        action = trigger_workflow_internal(
            delivery["event_name"],
            delivery.get("payload"),
            source=delivery.get("source"),
            idempotency_key=delivery.get("idempotency_key"),
            delivery_id=delivery["id"],
        )
    except HTTPException as exc:
        latest_delivery = _get_internal_event_delivery(delivery["id"]) or delivery
        if not _is_internal_trigger_not_found_error(exc):
            raise
        if str(latest_delivery.get("status") or "").strip().lower() != INTERNAL_EVENT_STATUS_IGNORED:
            raise
        action = _build_internal_event_delivery_response(latest_delivery, deduplicated=False)
    latest_delivery = _get_internal_event_delivery(delivery["id"]) or delivery
    action["delivery"] = _hydrate_internal_event_delivery(latest_delivery)
    _publish_internal_event_delivery_event(
        latest_delivery,
        subject=INTERNAL_EVENT_DELIVERY_RETRIED_SUBJECT,
        event_name="brain.internal_event.delivery.retried",
        message_type=MESSAGE_TYPE_RESULT,
        extra_payload={"retry_delivery_id": str(delivery.get("id") or "").strip() or None},
    )
    return action


def replay_internal_event_delivery(delivery_id: str) -> dict:
    source_delivery = get_internal_event_delivery(delivery_id)
    replay_action = trigger_workflow_internal(
        source_delivery["event_name"],
        source_delivery.get("payload"),
        source=source_delivery.get("source"),
        idempotency_key=_build_internal_event_replay_idempotency_key(source_delivery),
    )
    latest_delivery = _get_internal_event_delivery(replay_action["internal_event_id"])
    if latest_delivery is not None:
        replay_action["delivery"] = _hydrate_internal_event_delivery(latest_delivery)
    replay_action["replayed_from_delivery_id"] = source_delivery["id"]
    triggered_count = int(replay_action.get("triggered_count") or 0)
    replay_action["message"] = (
        "Internal event delivery replay fan-out accepted"
        if triggered_count > 1
        else "Internal event delivery replay accepted"
    )
    return replay_action


def list_runs(workflow_id: str | None = None, task_id: str | None = None, *, scope: dict[str, str] | None = None) -> dict:
    payload = list_workflow_runs(workflow_id=workflow_id, task_id=task_id, scope=scope)
    monitor_now = datetime.now(UTC)
    items = [_attach_run_monitor(item, now=monitor_now) for item in payload["items"]]
    return {"items": items, "total": len(items)}


def get_run(run_id: str, *, scope: dict[str, str] | None = None) -> dict:
    return _attach_run_monitor(get_workflow_run(run_id, scope=scope))


def tick_run(run_id: str) -> dict:
    return _attach_run_monitor(tick_workflow_run(run_id))


def request_manual_handoff(run_id: str, *, operator: str | None = None, note: str | None = None) -> dict:
    return _attach_run_monitor(
        request_manual_handoff_for_workflow_run(
            run_id,
            operator=operator,
            note=note,
        )
    )


def get_workflow_monitor(
    workflow_id: str,
    *,
    task_id: str | None = None,
    limit: int = 20,
    unhealthy_only: bool = False,
) -> dict:
    workflow = store.clone(_find_workflow_mutable(workflow_id))
    payload = list_workflow_runs(workflow_id=workflow_id, task_id=task_id)
    monitor_now = datetime.now(UTC)
    monitored_items = [_attach_run_monitor(item, now=monitor_now) for item in payload["items"]]
    stats = _build_workflow_monitor_stats(monitored_items)
    runtime = workflow_runtime_snapshot_service.build_snapshot(
        runs=monitored_items,
        workflow_id=workflow_id,
        task_id=task_id,
        now=monitor_now,
        persistence=persistence_service,
    )

    items = monitored_items
    if unhealthy_only:
        items = [item for item in monitored_items if _run_is_unhealthy(item)]

    resolved_limit = max(1, min(int(limit or 20), 100))
    return {
        "workflow_id": workflow_id,
        "timestamp": monitor_now.isoformat(),
        "workflow": workflow,
        "stats": stats,
        "items": items[:resolved_limit],
        "alerts": _build_workflow_monitor_alerts(stats),
        "runtime": runtime,
    }


def reset_internal_event_delivery_state() -> None:
    _INTERNAL_EVENT_DELIVERIES_BY_ID.clear()
    _INTERNAL_EVENT_DELIVERIES_BY_KEY.clear()
