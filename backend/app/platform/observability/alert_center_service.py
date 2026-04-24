from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status

from app.modules.reception.channel_ingress.registry import channel_adapter_registry
from app.platform.observability.dashboard_service import get_stats
from app.platform.persistence.persistence_service import persistence_service
from app.platform.persistence.runtime_store import store
from app.modules.organization.application.tenancy_service import attach_scope, matches_scope


ALERT_ACTION_RESOURCE = "unified_alert"
ALERT_ACTION_STATUSES = {"acknowledged", "resolved", "suppressed"}
ALERT_SUBSCRIPTIONS_KEY = "unified_alert_subscriptions"
ALERT_ESCALATION_POLICIES_KEY = "unified_alert_escalation_policies"
ALERT_SUPPORTED_CHANNELS = {"telegram", "wecom", "feishu", "dingtalk"}
ALERT_SUPPORTED_SEVERITIES = {"info", "warning", "critical"}
ALERT_AGGREGATION_WINDOW_MINUTES = 30
ALERT_DEFAULT_SUPPRESSION_MINUTES = 60
SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}


def _coerce_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        payload = model_dump(by_alias=False)
        if isinstance(payload, dict):
            return payload
    return {}


def _normalize_text(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _canonicalize_text(value: object) -> str:
    return "".join(ch.lower() for ch in str(value or "").strip() if ch.isalnum())


def _bucket_start(value: str | None, *, window_minutes: int) -> datetime:
    parsed = _parse_datetime(value) or datetime.now(UTC)
    minute = (parsed.minute // window_minutes) * window_minutes
    return parsed.replace(minute=minute, second=0, microsecond=0)


def _dedupe_key_for_alert(item: dict) -> str:
    source_type = _normalize_text(item.get("source_type")) or "runtime"
    source = _normalize_text(item.get("source")) or "runtime"
    category = _normalize_text(item.get("category")) or "runtime"
    resource = _normalize_text(item.get("resource")) or "none"
    workflow_run_id = _normalize_text(item.get("workflow_run_id")) or "none"
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    if source_type == "runtime":
        signal_key = _normalize_text(item.get("source_id")) or _normalize_text(metadata.get("key")) or "signal"
        return f"runtime|{source}|{signal_key}"
    if source_type == "audit":
        actor = _normalize_text(item.get("user_key")) or "anonymous"
        action_key = _canonicalize_text(item.get("title")) or "audit"
        return f"audit|{resource}|{category}|{action_key}|{actor}|{workflow_run_id}"
    task_id = _normalize_text(metadata.get("task_id")) or "none"
    message_key = _canonicalize_text(item.get("message")) or _canonicalize_text(item.get("title")) or "operational"
    return f"operational|{source}|{category}|{workflow_run_id}|{task_id}|{message_key}"


def _aggregate_strategy_for_alert(item: dict) -> str:
    source_type = _normalize_text(item.get("source_type")) or "runtime"
    if source_type == "runtime":
        return "signal_key_window"
    if source_type == "audit":
        return "resource_actor_window"
    return "source_object_window"


def _sort_alert_at(item: dict) -> datetime:
    return (
        _parse_datetime(item.get("updated_at"))
        or _parse_datetime(item.get("occurred_at"))
        or datetime.min.replace(tzinfo=UTC)
    )


def _severity_key(value: object) -> int:
    return SEVERITY_RANK.get(str(value or "").strip().lower(), 0)


def _parse_datetime(value: str | None) -> datetime | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _load_audit_logs() -> list[dict]:
    database_logs = persistence_service.list_audit_logs()
    if database_logs is not None:
        return database_logs
    if getattr(persistence_service, "enabled", False):
        return []
    return store.clone(store.audit_logs)


def _load_operational_logs() -> list[dict]:
    database_logs = persistence_service.list_operational_logs()
    if database_logs is not None:
        return database_logs
    if getattr(persistence_service, "enabled", False):
        return []
    return store.clone(getattr(store, "operational_logs", []))


def _read_json_setting(key: str, *, default: list[dict] | None = None) -> list[dict]:
    read_setting = getattr(persistence_service, "read_system_setting", None)
    if callable(read_setting):
        payload, authoritative = read_setting(key)
        if authoritative:
            setting_payload = payload.get("payload") if isinstance(payload, dict) else None
            return setting_payload if isinstance(setting_payload, list) else (default or [])
    get_setting = getattr(persistence_service, "get_system_setting", None)
    if callable(get_setting):
        payload = get_setting(key)
        if isinstance(payload, dict):
            setting_payload = payload.get("payload")
            if isinstance(setting_payload, list):
                return setting_payload
    runtime_value = store.system_settings.get(key)
    if isinstance(runtime_value, list):
        return store.clone(runtime_value)
    return store.clone(default or [])


def _write_json_setting(key: str, items: list[dict]) -> bool:
    store.system_settings[key] = store.clone(items)
    persist_setting = getattr(persistence_service, "persist_system_setting", None)
    if callable(persist_setting):
        return bool(persist_setting(key=key, payload=items, updated_at=store.now_string()))
    return True


def _severity_from_audit_status(status_value: str) -> str:
    normalized = str(status_value or "").strip().lower()
    if normalized == "error":
        return "critical"
    if normalized == "warning":
        return "warning"
    return "info"


def _severity_from_operational_type(type_value: str) -> str:
    normalized = str(type_value or "").strip().lower()
    if normalized in {"error", "alert"}:
        return "critical"
    if normalized == "warning":
        return "warning"
    return "info"


def _base_alert_from_audit_log(log: dict) -> dict | None:
    status_value = str(log.get("status") or "").strip().lower()
    if status_value not in {"warning", "error"}:
        return None
    if str(log.get("resource") or "").strip() == ALERT_ACTION_RESOURCE:
        return None

    metadata = log.get("metadata") if isinstance(log.get("metadata"), dict) else {}
    trace = metadata.get("trace") if isinstance(metadata.get("trace"), dict) else {}
    user_key = str(log.get("user") or "").strip() or None
    item = {
        "id": f"audit:{str(log.get('id') or '').strip()}",
        "source_type": "audit",
        "source_id": str(log.get("id") or "").strip(),
        "source": "security" if "security" in str(log.get("resource") or "").lower() else "audit",
        "severity": _severity_from_audit_status(status_value),
        "status": "open",
        "category": str(trace.get("layer") or log.get("resource") or "audit").strip() or "audit",
        "title": str(log.get("action") or "Audit alert").strip() or "Audit alert",
        "message": str(log.get("details") or log.get("action") or "").strip() or "Audit event",
        "occurred_at": str(log.get("timestamp") or store.now_string()),
        "updated_at": str(log.get("timestamp") or store.now_string()),
        "resource": str(log.get("resource") or "").strip() or None,
        "user_key": user_key,
        "trace_id": str(trace.get("trace_id") or metadata.get("trace_id") or "").strip() or None,
        "workflow_run_id": str(metadata.get("workflow_run_id") or "").strip() or None,
        "href": "/security",
        "metadata": metadata or None,
    }
    item["dedupe_key"] = _dedupe_key_for_alert(item)
    item["aggregate_strategy"] = _aggregate_strategy_for_alert(item)
    item["aggregate_window_minutes"] = ALERT_AGGREGATION_WINDOW_MINUTES
    return item


def _base_alert_from_operational_log(log: dict) -> dict | None:
    type_value = str(log.get("type") or "").strip().lower()
    if type_value not in {"warning", "error", "alert"}:
        return None
    metadata = log.get("metadata") if isinstance(log.get("metadata"), dict) else {}
    workflow_run_id = str(log.get("workflow_run_id") or "").strip() or None
    task_id = str(log.get("task_id") or "").strip() or None
    href = "/tasks"
    if task_id:
        href = f"/tasks/{task_id}"
    item = {
        "id": f"operational:{str(log.get('id') or '').strip()}",
        "source_type": "operational",
        "source_id": str(log.get("id") or "").strip(),
        "source": str(log.get("source") or "runtime").strip() or "runtime",
        "severity": _severity_from_operational_type(type_value),
        "status": "open",
        "category": str(log.get("agent") or log.get("source") or "runtime").strip() or "runtime",
        "title": str(log.get("agent") or "Runtime alert").strip() or "Runtime alert",
        "message": str(log.get("message") or "").strip() or "Operational event",
        "occurred_at": str(log.get("timestamp") or store.now_string()),
        "updated_at": str(log.get("timestamp") or store.now_string()),
        "resource": str(log.get("source") or "").strip() or None,
        "user_key": None,
        "trace_id": str(log.get("trace_id") or "").strip() or None,
        "workflow_run_id": workflow_run_id,
        "href": href,
        "metadata": metadata or None,
    }
    item["dedupe_key"] = _dedupe_key_for_alert(item)
    item["aggregate_strategy"] = _aggregate_strategy_for_alert(item)
    item["aggregate_window_minutes"] = ALERT_AGGREGATION_WINDOW_MINUTES
    return item


def _base_alert_from_prepared_alert(alert: dict) -> dict | None:
    key = str(alert.get("key") or "").strip()
    if not key:
        return None
    severity = str(alert.get("severity") or "warning").strip().lower()
    if severity not in {"info", "warning", "critical"}:
        severity = "warning"
    href = str(alert.get("href") or "/security").strip() or "/security"
    item = {
        "id": f"runtime:{key}",
        "source_type": "runtime",
        "source_id": key,
        "source": str(alert.get("source") or "runtime").strip() or "runtime",
        "severity": severity,
        "status": "open",
        "category": str(alert.get("source") or "runtime").strip() or "runtime",
        "title": str(alert.get("title") or key).strip() or key,
        "message": str(alert.get("detail") or "").strip() or str(alert.get("title") or key),
        "occurred_at": store.now_string(),
        "updated_at": store.now_string(),
        "resource": str(alert.get("source") or "").strip() or None,
        "user_key": None,
        "trace_id": None,
        "workflow_run_id": None,
        "href": href,
        "metadata": {"origin": "prepared_alert", "key": key},
    }
    item["dedupe_key"] = _dedupe_key_for_alert(item)
    item["aggregate_strategy"] = _aggregate_strategy_for_alert(item)
    item["aggregate_window_minutes"] = ALERT_AGGREGATION_WINDOW_MINUTES
    return item


def _action_state_by_alert_id() -> dict[str, dict]:
    state_map: dict[str, dict] = {}
    for log in _load_audit_logs():
        if str(log.get("resource") or "").strip() != ALERT_ACTION_RESOURCE:
            continue
        metadata = log.get("metadata") if isinstance(log.get("metadata"), dict) else {}
        alert_id = str(metadata.get("source_alert_id") or "").strip()
        dedupe_key = str(metadata.get("dedupe_key") or "").strip()
        action_status = str(metadata.get("next_status") or "").strip().lower()
        if not alert_id or action_status not in ALERT_ACTION_STATUSES:
            continue
        current = state_map.get(alert_id)
        current_ts = _parse_datetime(current.get("updated_at")) if isinstance(current, dict) else None
        next_ts = _parse_datetime(str(log.get("timestamp") or "")) or datetime.min.replace(tzinfo=UTC)
        if current is not None and current_ts is not None and current_ts >= next_ts:
            continue
        state_payload = {
            "status": action_status,
            "updated_at": str(log.get("timestamp") or store.now_string()),
            "note": str(metadata.get("note") or "").strip() or None,
            "suppress_until": str(metadata.get("suppress_until") or "").strip() or None,
        }
        state_map[alert_id] = state_payload
        if dedupe_key:
            state_map[f"dedupe:{dedupe_key}"] = store.clone(state_payload)
    return state_map


def _effective_alert_status(base_alert: dict, action_state: dict | None) -> tuple[str, str, str | None]:
    if not isinstance(action_state, dict):
        return (
            str(base_alert.get("status") or "open"),
            str(base_alert.get("updated_at") or store.now_string()),
            None,
        )
    status_value = str(action_state.get("status") or "open").strip().lower()
    updated_at = str(action_state.get("updated_at") or base_alert.get("updated_at") or store.now_string())
    suppress_until_value = str(action_state.get("suppress_until") or "").strip() or None
    if status_value == "suppressed":
        suppress_until = _parse_datetime(action_state.get("suppress_until"))
        if suppress_until is not None and suppress_until <= datetime.now(UTC):
            return "open", updated_at, suppress_until_value
    return status_value, updated_at, suppress_until_value


def _all_base_alerts(*, scope: dict[str, str] | None = None) -> list[dict]:
    items: list[dict] = []
    for log in _load_audit_logs():
        item = _base_alert_from_audit_log(log)
        if item is not None:
            items.append(item)
    for log in _load_operational_logs():
        item = _base_alert_from_operational_log(log)
        if item is not None:
            items.append(item)
    dashboard_payload = get_stats(scope=scope)
    for alert in dashboard_payload.get("prepared_alerts", []):
        item = _base_alert_from_prepared_alert(alert)
        if item is not None:
            items.append(item)
    return items


def _aggregate_alerts(items: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = {}
    for item in items:
        dedupe_key = _normalize_text(item.get("dedupe_key")) or _dedupe_key_for_alert(item)
        window_minutes = max(int(item.get("aggregate_window_minutes") or ALERT_AGGREGATION_WINDOW_MINUTES), 1)
        bucket_key = _bucket_start(item.get("occurred_at"), window_minutes=window_minutes).isoformat()
        grouped.setdefault((dedupe_key, bucket_key), []).append(item)

    alerts: list[dict] = []
    for (dedupe_key, bucket_key), group in grouped.items():
        ordered = sorted(group, key=_sort_alert_at)
        latest = store.clone(ordered[-1])
        first = ordered[0]
        aggregate_count = len(ordered)
        aggregate_strategy = _normalize_text(latest.get("aggregate_strategy")) or "source_object_window"
        window_minutes = max(int(latest.get("aggregate_window_minutes") or ALERT_AGGREGATION_WINDOW_MINUTES), 1)
        if aggregate_count > 1:
            latest["id"] = f"aggregate:{dedupe_key}:{bucket_key}"
            latest["message"] = (
                f"{str(latest.get('message') or '').strip()} "
                f"(近 {window_minutes} 分钟内累计 {aggregate_count} 次)"
            ).strip()
        latest["dedupe_key"] = dedupe_key
        latest["aggregate_count"] = aggregate_count
        latest["aggregate_strategy"] = aggregate_strategy
        latest["aggregate_window_minutes"] = window_minutes
        latest["first_occurred_at"] = str(first.get("occurred_at") or first.get("updated_at") or "")
        latest["last_occurred_at"] = str(ordered[-1].get("occurred_at") or ordered[-1].get("updated_at") or "")
        latest["occurred_at"] = latest["first_occurred_at"] or str(latest.get("occurred_at") or "")
        latest["updated_at"] = latest["last_occurred_at"] or str(latest.get("updated_at") or "")
        latest["severity"] = max(
            (str(item.get("severity") or "info").strip().lower() for item in ordered),
            key=_severity_key,
        )
        metadata = latest.get("metadata") if isinstance(latest.get("metadata"), dict) else {}
        metadata = store.clone(metadata)
        metadata["aggregate_source_ids"] = [str(item.get("source_id") or "").strip() for item in ordered if str(item.get("source_id") or "").strip()]
        metadata["aggregate_bucket_started_at"] = bucket_key
        latest["metadata"] = metadata
        alerts.append(latest)
    alerts.sort(key=_sort_alert_at, reverse=True)
    return alerts


def _normalize_alerts(*, scope: dict[str, str] | None = None) -> list[dict]:
    action_state_map = _action_state_by_alert_id()
    scoped_items: list[dict] = []
    for base_alert in _all_base_alerts(scope=scope):
        attached = attach_scope(base_alert)
        if scope is not None and not matches_scope(attached, scope):
            continue
        scoped_items.append(attached)

    alerts: list[dict] = []
    for aggregated_alert in _aggregate_alerts(scoped_items):
        alert_id = str(aggregated_alert.get("id") or "").strip()
        dedupe_key = str(aggregated_alert.get("dedupe_key") or "").strip()
        action_state = action_state_map.get(alert_id)
        if action_state is None and dedupe_key:
            action_state = action_state_map.get(f"dedupe:{dedupe_key}")
        status_value, updated_at, suppressed_until = _effective_alert_status(aggregated_alert, action_state)
        item = store.clone(aggregated_alert)
        item["status"] = status_value
        item["updated_at"] = updated_at
        item["suppressed_until"] = suppressed_until
        alerts.append(item)
    alerts.sort(key=_sort_alert_at, reverse=True)
    return alerts


def _matches_query(item: dict, *, status_filter: str | None, severity: str | None, source: str | None, search: str | None) -> bool:
    if status_filter and str(item.get("status") or "").strip().lower() != status_filter:
        return False
    if severity and str(item.get("severity") or "").strip().lower() != severity:
        return False
    if source and str(item.get("source") or "").strip().lower() != source:
        return False
    if search:
        haystack = " ".join(
            [
                str(item.get("title") or ""),
                str(item.get("message") or ""),
                str(item.get("category") or ""),
                str(item.get("resource") or ""),
            ]
        ).lower()
        if search not in haystack:
            return False
    return True


def _build_summary(items: list[dict]) -> dict:
    status_counter = Counter(str(item.get("status") or "open") for item in items)
    severity_counter = Counter(str(item.get("severity") or "info") for item in items)
    source_counter = Counter(str(item.get("source") or "unknown") for item in items)
    return {
        "total": len(items),
        "open": int(status_counter.get("open", 0)),
        "acknowledged": int(status_counter.get("acknowledged", 0)),
        "resolved": int(status_counter.get("resolved", 0)),
        "suppressed": int(status_counter.get("suppressed", 0)),
        "severity_breakdown": [
            {"key": key, "count": int(count)}
            for key, count in severity_counter.most_common()
        ],
        "source_breakdown": [
            {"key": key, "count": int(count)}
            for key, count in source_counter.most_common()
        ],
    }


def list_alerts(
    *,
    status_filter: str | None = None,
    severity: str | None = None,
    source: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
    scope: dict[str, str] | None = None,
) -> dict:
    normalized_status = str(status_filter or "").strip().lower() or None
    normalized_severity = str(severity or "").strip().lower() or None
    normalized_source = str(source or "").strip().lower() or None
    normalized_search = str(search or "").strip().lower() or None
    alerts = [
        attach_scope(item)
        for item in _normalize_alerts(scope=scope)
        if (scope is None or matches_scope(item, scope))
        and _matches_query(
            attach_scope(item),
            status_filter=normalized_status,
            severity=normalized_severity,
            source=normalized_source,
            search=normalized_search,
        )
    ]
    summary = _build_summary(alerts)
    normalized_limit = max(int(limit), 1)
    normalized_offset = max(int(offset), 0)
    paged = alerts[normalized_offset : normalized_offset + normalized_limit]
    return {"items": paged, "total": len(alerts), "summary": summary}


def get_alert(alert_id: str, *, scope: dict[str, str] | None = None) -> dict:
    normalized_alert_id = str(alert_id or "").strip()
    if not normalized_alert_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    for item in _normalize_alerts(scope=scope):
        if str(item.get("id") or "").strip() == normalized_alert_id:
            attached = attach_scope(item)
            if scope is not None and not matches_scope(attached, scope):
                break
            return attached
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")


def _append_alert_action_log(
    *,
    alert: dict,
    next_status: str,
    operator: str,
    note: str | None = None,
    duration_minutes: int | None = None,
) -> None:
    metadata: dict[str, Any] = {
        "source_alert_id": str(alert.get("id") or "").strip(),
        "dedupe_key": str(alert.get("dedupe_key") or "").strip() or None,
        "next_status": next_status,
        "source": str(alert.get("source") or "").strip() or "runtime",
    }
    if note:
        metadata["note"] = note
    if next_status == "suppressed" and duration_minutes is not None:
        suppress_until = datetime.now(UTC) + timedelta(minutes=max(int(duration_minutes), 1))
        metadata["suppress_until"] = suppress_until.isoformat()
    payload = {
        "id": f"audit-alert-{uuid4().hex[:10]}",
        "timestamp": store.now_string(),
        "action": f"alert.{next_status}",
        "user": operator,
        "resource": ALERT_ACTION_RESOURCE,
        "status": "success",
        "ip": "-",
        "details": note or f"Alert {next_status}",
        "metadata": metadata,
    }
    store.audit_logs.insert(0, store.clone(payload))
    del store.audit_logs[200:]
    persistence_service.append_audit_log(log=payload)


def update_alert_status(
    alert_id: str,
    *,
    next_status: str,
    operator: str,
    note: str | None = None,
    duration_minutes: int | None = None,
) -> dict:
    normalized_status = str(next_status or "").strip().lower()
    if normalized_status not in ALERT_ACTION_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported alert status action")
    alert = get_alert(alert_id)
    _append_alert_action_log(
        alert=alert,
        next_status=normalized_status,
        operator=operator,
        note=note,
        duration_minutes=duration_minutes,
    )
    return get_alert(alert_id)


def _normalize_subscription_scope(scope: dict[str, str] | None) -> dict[str, str]:
    if not isinstance(scope, dict):
        return {}
    normalized: dict[str, str] = {}
    for key in ("tenant_id", "project_id", "environment"):
        value = str(scope.get(key) or "").strip()
        if value:
            normalized[key] = value
    return normalized


def _normalize_severity_scope(severity_scope: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for value in severity_scope or []:
        level = str(value or "").strip().lower()
        if level in ALERT_SUPPORTED_SEVERITIES and level not in normalized:
            normalized.append(level)
    if normalized:
        return normalized
    return ["warning", "critical"]


def _normalize_subscription_item(item: dict[str, Any]) -> dict[str, Any] | None:
    subscription_id = str(item.get("id") or "").strip()
    channel = str(item.get("channel") or "").strip().lower()
    target = str(item.get("target") or "").strip()
    if not subscription_id or channel not in ALERT_SUPPORTED_CHANNELS or not target:
        return None
    created_at = str(item.get("created_at") or item.get("createdAt") or store.now_string())
    updated_at = str(item.get("updated_at") or item.get("updatedAt") or created_at)
    normalized: dict[str, Any] = {
        "id": subscription_id,
        "channel": channel,
        "target": target,
        "enabled": bool(item.get("enabled", True)),
        "severity_scope": _normalize_severity_scope(item.get("severity_scope")),
        "created_at": created_at,
        "updated_at": updated_at,
    }
    for key in ("tenant_id", "project_id", "environment"):
        value = str(item.get(key) or "").strip()
        if value:
            normalized[key] = value
    return normalized


def _scope_signature(scope: dict[str, str] | None) -> tuple[str, str, str]:
    normalized = _normalize_subscription_scope(scope)
    return (
        str(normalized.get("tenant_id") or "").strip(),
        str(normalized.get("project_id") or "").strip(),
        str(normalized.get("environment") or "").strip(),
    )


def _normalize_ordered_channels(value: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for item in value or []:
        channel = str(item or "").strip().lower()
        if channel in ALERT_SUPPORTED_CHANNELS and channel not in normalized:
            normalized.append(channel)
    return normalized


def _normalize_escalation_policy_item(item: dict[str, Any]) -> dict[str, Any] | None:
    item = _coerce_mapping(item)
    severity = str(item.get("severity") or "").strip().lower()
    if severity not in ALERT_SUPPORTED_SEVERITIES:
        return None
    send_all = bool(item.get("send_all", item.get("sendAll", True)))
    max_deliveries_raw = item.get("max_deliveries", item.get("maxDeliveries"))
    try:
        max_deliveries = int(max_deliveries_raw) if max_deliveries_raw is not None else None
    except (TypeError, ValueError):
        max_deliveries = None
    if max_deliveries is not None and max_deliveries <= 0:
        max_deliveries = None
    if send_all:
        max_deliveries = None
    suppression_raw = item.get("suppression_minutes", item.get("suppressionMinutes"))
    try:
        suppression_minutes = int(suppression_raw) if suppression_raw is not None else ALERT_DEFAULT_SUPPRESSION_MINUTES
    except (TypeError, ValueError):
        suppression_minutes = ALERT_DEFAULT_SUPPRESSION_MINUTES
    return {
        "severity": severity,
        "ordered_channels": _normalize_ordered_channels(
            item.get("ordered_channels") if isinstance(item.get("ordered_channels"), list) else item.get("orderedChannels")
        ),
        "send_all": send_all,
        "max_deliveries": max_deliveries,
        "suppression_minutes": max(1, suppression_minutes),
    }


def _normalize_escalation_policy_set(item: dict[str, Any]) -> dict[str, Any] | None:
    item = _coerce_mapping(item)
    if not item:
        return None
    policy_id = str(item.get("id") or "").strip() or f"alert-policy-{uuid4().hex[:8]}"
    created_at = str(item.get("created_at") or item.get("createdAt") or store.now_string())
    updated_at = str(item.get("updated_at") or item.get("updatedAt") or created_at)
    policies_by_severity: dict[str, dict[str, Any]] = {}
    for raw_policy in item.get("policies") or []:
        if not isinstance(raw_policy, dict):
            continue
        normalized_policy = _normalize_escalation_policy_item(raw_policy)
        if normalized_policy is None:
            continue
        policies_by_severity[normalized_policy["severity"]] = normalized_policy
    normalized: dict[str, Any] = {
        "id": policy_id,
        "policies": list(policies_by_severity.values()),
        "created_at": created_at,
        "updated_at": updated_at,
    }
    for key in ("tenant_id", "project_id", "environment"):
        value = str(item.get(key) or "").strip()
        if value:
            normalized[key] = value
    return normalized


def get_alert_escalation_policy(*, scope: dict[str, str] | None = None) -> dict:
    normalized_scope = _normalize_subscription_scope(scope)
    target_signature = _scope_signature(normalized_scope)
    for raw_item in _read_json_setting(ALERT_ESCALATION_POLICIES_KEY, default=[]):
        normalized = _normalize_escalation_policy_set(raw_item)
        if normalized is None:
            continue
        if _scope_signature(normalized) != target_signature:
            continue
        return attach_scope(normalized)
    return attach_scope(
        {
            "id": "alert-policy-default",
            **normalized_scope,
            "policies": [],
            "created_at": store.now_string(),
            "updated_at": store.now_string(),
        }
    )


def upsert_alert_escalation_policy(
    *,
    policies: list[dict[str, Any]] | None,
    scope: dict[str, str] | None = None,
) -> dict:
    normalized_scope = _normalize_subscription_scope(scope)
    normalized_policies = []
    for raw_policy in policies or []:
        normalized = _normalize_escalation_policy_item(raw_policy)
        if normalized is not None:
            normalized_policies.append(normalized)

    target_signature = _scope_signature(normalized_scope)
    items = _read_json_setting(ALERT_ESCALATION_POLICIES_KEY, default=[])
    now = store.now_string()
    matched_index = -1
    existing_created_at = now
    existing_id = f"alert-policy-{uuid4().hex[:8]}"
    for index, raw_item in enumerate(items):
        normalized_item = _normalize_escalation_policy_set(raw_item)
        if normalized_item is None:
            continue
        if _scope_signature(normalized_item) != target_signature:
            continue
        matched_index = index
        existing_created_at = str(normalized_item.get("created_at") or now)
        existing_id = str(normalized_item.get("id") or existing_id)
        break

    record = {
        "id": existing_id,
        **normalized_scope,
        "policies": normalized_policies,
        "created_at": existing_created_at,
        "updated_at": now,
    }
    if matched_index >= 0:
        items[matched_index] = record
    else:
        items.append(record)
    _write_json_setting(ALERT_ESCALATION_POLICIES_KEY, items)
    return {"ok": True, "message": "Alert escalation policy updated", "policy": attach_scope(record)}


def _policy_for_severity(policy_set: dict[str, Any] | None, *, severity: str) -> dict[str, Any] | None:
    normalized_severity = str(severity or "").strip().lower()
    if not normalized_severity:
        return None
    if not isinstance(policy_set, dict):
        return None
    for item in policy_set.get("policies") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("severity") or "").strip().lower() == normalized_severity:
            return item
    return None


def _select_subscriptions_for_alert(
    subscriptions: list[dict[str, Any]],
    *,
    policy: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    indexed = list(enumerate(subscriptions))
    normalized_policy = policy if isinstance(policy, dict) else None
    if normalized_policy is None:
        selected = [item for _, item in indexed]
        deliveries = [
            {
                "subscription_id": str(item.get("id") or ""),
                "channel": str(item.get("channel") or ""),
                "target": str(item.get("target") or ""),
                "selected": True,
                "reason": "matched_subscription",
            }
            for item in selected
        ]
        return selected, deliveries

    order_map = {
        channel: index
        for index, channel in enumerate(normalized_policy.get("ordered_channels") or [])
    }
    sorted_indexed = sorted(
        indexed,
        key=lambda pair: (
            order_map.get(str(pair[1].get("channel") or "").strip().lower(), len(order_map)),
            pair[0],
        ),
    )
    send_all = bool(normalized_policy.get("send_all", True))
    max_deliveries = normalized_policy.get("max_deliveries")
    selection_limit = None if send_all else max(1, int(max_deliveries or 1))
    selected_items: list[dict[str, Any]] = []
    deliveries: list[dict[str, Any]] = []
    for index, (_, item) in enumerate(sorted_indexed):
        is_selected = selection_limit is None or index < selection_limit
        if is_selected:
            selected_items.append(item)
        deliveries.append(
            {
                "subscription_id": str(item.get("id") or ""),
                "channel": str(item.get("channel") or ""),
                "target": str(item.get("target") or ""),
                "selected": is_selected,
                "reason": "policy_selected" if is_selected else "policy_skipped_limit",
            }
        )
    return selected_items, deliveries


def preview_alert_delivery(
    alert_id: str,
    *,
    note: str | None = None,
    scope: dict[str, str] | None = None,
) -> dict[str, Any]:
    alert = get_alert(alert_id, scope=scope)
    severity = str(alert.get("severity") or "").strip().lower()
    subscriptions = [
        item
        for item in list_alert_subscriptions(scope=scope)["items"]
        if bool(item.get("enabled"))
        and severity in {str(level).strip().lower() for level in item.get("severity_scope") or []}
    ]
    policy_set = get_alert_escalation_policy(scope=scope)
    matched_policy = _policy_for_severity(policy_set, severity=severity)
    selected_subscriptions, deliveries = _select_subscriptions_for_alert(
        subscriptions,
        policy=matched_policy,
    )
    return {
        "alert": alert,
        "matched_subscriptions": len(subscriptions),
        "selected_subscriptions": len(selected_subscriptions),
        "policy": matched_policy,
        "deliveries": deliveries,
        "text": _format_alert_delivery_text(alert, note=note),
        "subscriptions": selected_subscriptions,
    }


def list_alert_subscriptions(*, scope: dict[str, str] | None = None) -> dict:
    items: list[dict[str, Any]] = []
    for raw_item in _read_json_setting(ALERT_SUBSCRIPTIONS_KEY, default=[]):
        if not isinstance(raw_item, dict):
            continue
        normalized = _normalize_subscription_item(raw_item)
        if normalized is None:
            continue
        attached = attach_scope(normalized)
        if scope is not None and not matches_scope(attached, scope):
            continue
        items.append(attached)
    items.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return {"items": items, "total": len(items)}


def create_alert_subscription(
    *,
    channel: str,
    target: str,
    enabled: bool = True,
    severity_scope: list[str] | None = None,
    scope: dict[str, str] | None = None,
) -> dict:
    normalized_channel = str(channel or "").strip().lower()
    if normalized_channel not in ALERT_SUPPORTED_CHANNELS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid subscription channel")
    normalized_target = str(target or "").strip()
    if not normalized_target:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="target is required")

    now = store.now_string()
    item: dict[str, Any] = {
        "id": f"alert-sub-{uuid4().hex[:8]}",
        "channel": normalized_channel,
        "target": normalized_target,
        "enabled": bool(enabled),
        "severity_scope": _normalize_severity_scope(severity_scope),
        "created_at": now,
        "updated_at": now,
    }
    item.update(_normalize_subscription_scope(scope))

    items = _read_json_setting(ALERT_SUBSCRIPTIONS_KEY, default=[])
    items.append(item)
    _write_json_setting(ALERT_SUBSCRIPTIONS_KEY, items)
    return {"ok": True, "message": "Alert subscription created", "subscription": attach_scope(item)}


def update_alert_subscription(
    *,
    subscription_id: str,
    target: str | None = None,
    enabled: bool | None = None,
    severity_scope: list[str] | None = None,
    scope: dict[str, str] | None = None,
) -> dict:
    normalized_id = str(subscription_id or "").strip()
    if not normalized_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert subscription not found")
    items = _read_json_setting(ALERT_SUBSCRIPTIONS_KEY, default=[])
    matched_index = -1
    matched_item: dict[str, Any] | None = None
    for index, raw_item in enumerate(items):
        if not isinstance(raw_item, dict):
            continue
        normalized = _normalize_subscription_item(raw_item)
        if normalized is None:
            continue
        if str(normalized.get("id") or "").strip() != normalized_id:
            continue
        attached = attach_scope(normalized)
        if scope is not None and not matches_scope(attached, scope):
            break
        matched_index = index
        matched_item = normalized
        break

    if matched_index < 0 or matched_item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert subscription not found")

    if target is not None:
        normalized_target = str(target or "").strip()
        if not normalized_target:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="target is required")
        matched_item["target"] = normalized_target
    if enabled is not None:
        matched_item["enabled"] = bool(enabled)
    if severity_scope is not None:
        matched_item["severity_scope"] = _normalize_severity_scope(severity_scope)
    matched_item["updated_at"] = store.now_string()
    items[matched_index] = matched_item
    _write_json_setting(ALERT_SUBSCRIPTIONS_KEY, items)
    return {"ok": True, "message": "Alert subscription updated", "subscription": attach_scope(matched_item)}


def _format_alert_delivery_text(alert: dict, *, note: str | None = None) -> str:
    severity = str(alert.get("severity") or "warning").strip().upper()
    source = str(alert.get("source") or "runtime").strip()
    title = str(alert.get("title") or "Alert").strip()
    message = str(alert.get("message") or "").strip()
    occurred_at = str(alert.get("occurred_at") or "").strip()
    href = str(alert.get("href") or "").strip()
    lines = [
        f"[WorkBot Alert] {severity} {title}",
        f"source: {source}",
        f"occurred_at: {occurred_at}",
        f"message: {message}",
    ]
    if note:
        lines.append(f"note: {note}")
    if href:
        lines.append(f"href: {href}")
    return "\n".join(lines)


def send_alert_to_matching_subscriptions(
    alert_id: str,
    *,
    operator: str,
    note: str | None = None,
    scope: dict[str, str] | None = None,
) -> dict:
    preview = preview_alert_delivery(alert_id, note=note, scope=scope)
    alert = preview["alert"]
    subscriptions = list(preview.get("subscriptions") or [])
    text = str(preview.get("text") or "")
    matched_subscriptions = int(preview.get("matched_subscriptions") or 0)
    selected_subscriptions = int(preview.get("selected_subscriptions") or 0)
    deliveries: list[dict[str, Any]] = []
    sent = 0
    failed = 0

    for subscription in subscriptions:
        channel = str(subscription.get("channel") or "").strip().lower()
        target = str(subscription.get("target") or "").strip()
        try:
            adapter = channel_adapter_registry.get(channel)
            adapter.send_message(chat_id=target, text=text)
            deliveries.append(
                {
                    "subscription_id": str(subscription.get("id") or ""),
                    "channel": channel,
                    "target": target,
                    "status": "sent",
                    "detail": None,
                }
            )
            sent += 1
        except Exception as exc:
            deliveries.append(
                {
                    "subscription_id": str(subscription.get("id") or ""),
                    "channel": channel,
                    "target": target,
                    "status": "failed",
                    "detail": str(exc),
                }
            )
            failed += 1

    payload = {
        "id": f"audit-alert-send-{uuid4().hex[:10]}",
        "timestamp": store.now_string(),
        "action": "alert.manual_send",
        "user": operator,
        "resource": ALERT_ACTION_RESOURCE,
        "status": "success" if failed == 0 else "warning",
        "ip": "-",
        "details": f"manual_send matched={matched_subscriptions} selected={selected_subscriptions} sent={sent} failed={failed}",
        "metadata": {
            "source_alert_id": str(alert.get("id") or ""),
            "delivery_summary": {
                "matched": matched_subscriptions,
                "selected": selected_subscriptions,
                "sent": sent,
                "failed": failed,
            },
            "deliveries": deliveries,
            "selection_preview": preview.get("deliveries") or [],
            "policy": preview.get("policy"),
            "note": note,
        },
    }
    store.audit_logs.insert(0, store.clone(payload))
    del store.audit_logs[200:]
    persistence_service.append_audit_log(log=payload)

    return {
        "ok": True,
        "message": (
            f"Alert sent to {sent}/{selected_subscriptions} subscription(s)"
            if matched_subscriptions == selected_subscriptions
            else f"Alert sent to {sent}/{selected_subscriptions} selected subscription(s)"
        ),
        "alert": alert,
        "matched_subscriptions": matched_subscriptions,
        "selected_subscriptions": selected_subscriptions,
        "sent": sent,
        "failed": failed,
        "deliveries": deliveries,
    }
