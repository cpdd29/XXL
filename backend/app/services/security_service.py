from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException, status

from app.services.agent_service import get_agent, list_agents
from app.services.persistence_service import persistence_service
from app.services.security_gateway_service import security_gateway_service
from app.services.store import store


def _load_security_rules() -> list[dict]:
    database_rules = persistence_service.list_security_rules()
    if database_rules is not None:
        return database_rules
    if getattr(persistence_service, "enabled", False):
        return []
    return store.clone(store.security_rules)


def _load_audit_logs() -> list[dict]:
    database_logs = persistence_service.list_audit_logs()
    if database_logs is not None:
        return database_logs
    if getattr(persistence_service, "enabled", False):
        return []
    return store.clone(store.audit_logs)


def _find_cached_security_rule(rule_id: str) -> dict | None:
    for rule in store.security_rules:
        if rule["id"] == rule_id:
            return rule
    return None


def _sync_cached_security_rule(rule_payload: dict) -> dict:
    rule_id = str(rule_payload.get("id") or "").strip()
    cached_rule = _find_cached_security_rule(rule_id)
    payload = store.clone(rule_payload)
    if cached_rule is None:
        store.security_rules.append(payload)
        return payload

    cached_rule.clear()
    cached_rule.update(payload)
    return cached_rule


def _load_database_security_rule(rule_id: str) -> tuple[dict | None, bool]:
    if not getattr(persistence_service, "enabled", False):
        return None, False

    database_rule = persistence_service.get_security_rule(rule_id)
    if database_rule is not None:
        return database_rule, True

    database_rules = persistence_service.list_security_rules()
    if database_rules is None:
        return None, True

    for candidate in database_rules:
        if str(candidate.get("id") or "").strip() == rule_id:
            return candidate, True
    return None, True


def _find_security_rule_mutable(rule_id: str) -> dict:
    database_rule, database_authoritative = _load_database_security_rule(rule_id)
    if database_authoritative:
        if database_rule is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Security rule not found")
        return _sync_cached_security_rule(database_rule)

    cached_rule = _find_cached_security_rule(rule_id)
    if cached_rule is not None:
        return cached_rule

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Security rule not found")


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _select_reference_logs(logs: list[dict]) -> list[dict]:
    today = datetime.now(UTC).date()
    today_logs = [
        log
        for log in logs
        if (parsed := _parse_timestamp(str(log.get("timestamp") or ""))) is not None
        and parsed.date() == today
    ]
    return today_logs or logs


def _normalize_window_hours(value: int | None) -> int:
    if value is None:
        return 24
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return 24
    return max(1, min(normalized, 24 * 30))


def _sort_logs_desc(logs: list[dict]) -> list[dict]:
    return sorted(
        logs,
        key=lambda item: _parse_timestamp(str(item.get("timestamp") or "")) or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )


def _logs_within_window(logs: list[dict], *, window_hours: int) -> list[dict]:
    cutoff = datetime.now(UTC).timestamp() - (window_hours * 3600)
    filtered: list[dict] = []
    for log in logs:
        parsed = _parse_timestamp(str(log.get("timestamp") or ""))
        if parsed is None:
            continue
        if parsed.timestamp() >= cutoff:
            filtered.append(log)
    return filtered


def _log_metadata(log: dict) -> dict:
    metadata = log.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _count_rewrite_events(logs: list[dict]) -> int:
    total = 0
    for log in logs:
        metadata = _log_metadata(log)
        rewrite_diffs = metadata.get("rewrite_diffs")
        if isinstance(rewrite_diffs, list) and rewrite_diffs:
            total += 1
            continue
        rewrite_notes = metadata.get("rewrite_notes")
        if isinstance(rewrite_notes, list) and rewrite_notes:
            total += 1
    return total


def _count_high_risk_events(logs: list[dict]) -> int:
    total = 0
    for log in logs:
        metadata = _log_metadata(log)
        assessment = metadata.get("prompt_injection_assessment")
        if isinstance(assessment, dict):
            verdict = str(assessment.get("verdict") or "").strip().lower()
            if verdict in {"block", "review"}:
                total += 1
                continue
        if str(log.get("status") or "").strip().lower() == "error":
            total += 1
    return total


def _build_breakdown(counter: Counter[str], *, total: int, limit: int = 5) -> list[dict]:
    if total <= 0:
        return []
    items: list[dict] = []
    for key, count in counter.most_common(limit):
        normalized_key = str(key or "").strip() or "unknown"
        items.append(
            {
                "key": normalized_key,
                "label": normalized_key,
                "count": int(count),
                "share": round((int(count) / total) * 100, 1),
            }
        )
    return items


SECURITY_LAYER_LABELS = {
    "rate_limit": "限流",
    "auth_scope": "认证",
    "prompt_injection": "注入检测",
    "content_policy_rewrite": "脱敏改写",
    "security_pass": "审计放行",
    "active_cooldown": "处罚冷却",
    "active_ban": "处罚封禁",
    "unknown": "未知",
}

SECURITY_INCIDENT_REVIEW_RESOURCE = "security_incident_review"
SECURITY_INCIDENT_REVIEW_ACTIONS = {"reviewed", "false_positive", "note"}
SECURITY_PENALTY_RESOURCE = "security_penalty"
SECURITY_RULE_RESOURCE = "security_rule"
SECURITY_ALERT_SUBSCRIPTIONS_KEY = "security_alert_subscriptions"


def _incident_layer_key(log: dict) -> str:
    metadata = _log_metadata(log)
    trace = metadata.get("trace")
    if isinstance(trace, dict):
        layer = str(trace.get("layer") or "").strip()
        if layer:
            return layer
    layer = str(metadata.get("layer") or "").strip()
    if layer:
        return layer
    action = str(log.get("action") or "").strip().lower()
    if "认证" in action or "auth" in action:
        return "auth_scope"
    if "prompt" in action or "注入" in action:
        return "prompt_injection"
    if "rate" in action or "限流" in action:
        return "rate_limit"
    if "改写" in action or "脱敏" in action:
        return "content_policy_rewrite"
    return "unknown"


def _incident_verdict(log: dict) -> str | None:
    metadata = _log_metadata(log)
    assessment = metadata.get("prompt_injection_assessment")
    if isinstance(assessment, dict):
        verdict = str(assessment.get("verdict") or "").strip()
        if verdict:
            return verdict
    return None


def _incident_rule_label(log: dict) -> str | None:
    metadata = _log_metadata(log)
    rewrite_diffs = metadata.get("rewrite_diffs")
    if isinstance(rewrite_diffs, list) and rewrite_diffs:
        first = rewrite_diffs[0]
        if isinstance(first, dict):
            label = str(first.get("label") or first.get("rule_label") or "").strip()
            if label:
                return label
    action = str(log.get("action") or "").strip()
    return action or None


def _build_recent_incident(log: dict) -> dict:
    layer_key = _incident_layer_key(log)
    return {
        **store.clone(log),
        "layer": SECURITY_LAYER_LABELS.get(layer_key, layer_key),
        "verdict": _incident_verdict(log),
        "rule_label": _incident_rule_label(log),
        "entity_refs": _extract_entity_refs(log),
    }


def _build_security_rule_snapshot(rule: dict) -> dict:
    return {
        "id": str(rule.get("id") or "").strip(),
        "name": str(rule.get("name") or "").strip(),
        "description": str(rule.get("description") or "").strip(),
        "type": str(rule.get("type") or "").strip() or "alert",
        "enabled": bool(rule.get("enabled")),
        "hit_count": max(int(rule.get("hit_count") or 0), 0),
        "last_triggered": str(rule.get("last_triggered") or "").strip(),
    }


def _metadata_id(metadata: dict, *keys: str) -> str | None:
    for key in keys:
        value = str(metadata.get(key) or "").strip()
        if value:
            return value
    return None


def _extract_entity_refs(log: dict) -> list[dict]:
    metadata = _log_metadata(log)
    refs: list[dict] = []
    task_id = _metadata_id(metadata, "task_id", "taskId")
    run_id = _metadata_id(metadata, "workflow_run_id", "workflowRunId", "run_id", "runId")
    workflow_id = _metadata_id(metadata, "workflow_id", "workflowId")
    user_key = _metadata_id(metadata, "user_key", "userKey")
    channel = _metadata_id(metadata, "channel", "platform")

    if task_id:
        refs.append(
            {
                "type": "task",
                "id": task_id,
                "label": f"任务 {task_id}",
                "href": f"/tasks/{task_id}",
            }
        )
        refs.append(
            {
                "type": "collaboration",
                "id": task_id,
                "label": f"协作 {task_id}",
                "href": f"/collaboration?taskId={task_id}",
            }
        )
    if run_id:
        refs.append(
            {
                "type": "run",
                "id": run_id,
                "label": f"运行 {run_id}",
                "href": f"/workflow?runId={run_id}",
            }
        )
    if workflow_id:
        refs.append(
            {
                "type": "workflow",
                "id": workflow_id,
                "label": f"工作流 {workflow_id}",
                "href": f"/workflow?workflowId={workflow_id}",
            }
        )
    if user_key:
        refs.append(
            {
                "type": "user",
                "id": user_key,
                "label": user_key,
                "href": f"/security?user={user_key}",
            }
        )
    if channel:
        refs.append(
            {
                "type": "channel",
                "id": channel,
                "label": channel,
                "href": f"/security?channel={channel}",
            }
        )
    return refs


def _normalize_rule_type(value: object) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in {"filter", "block", "alert"} else "alert"


def _rule_history_entry_from_audit_log(log: dict) -> dict | None:
    if str(log.get("resource") or "").strip() != SECURITY_RULE_RESOURCE:
        return None
    metadata = _log_metadata(log)
    snapshot = metadata.get("rule_snapshot")
    if not isinstance(snapshot, dict):
        return None
    rule_id = str(metadata.get("rule_id") or snapshot.get("id") or "").strip()
    version_id = str(metadata.get("version_id") or log.get("id") or "").strip()
    action = str(metadata.get("rule_action") or "").strip() or "updated"
    if not rule_id or not version_id:
        return None
    return {
        "id": version_id,
        "rule_id": rule_id,
        "timestamp": str(log.get("timestamp") or ""),
        "action": action,
        "operator": str(metadata.get("operator") or log.get("user") or "").strip() or "system",
        "snapshot": _build_security_rule_snapshot(snapshot),
        "note": str(metadata.get("note") or "").strip(),
    }


def _penalty_history_entry_from_audit_log(log: dict) -> dict | None:
    if str(log.get("resource") or "").strip() != SECURITY_PENALTY_RESOURCE:
        return None
    metadata = _log_metadata(log)
    penalty = metadata.get("penalty") or metadata.get("released_penalty")
    if not isinstance(penalty, dict):
        return None
    user_key = str(metadata.get("target_user_key") or penalty.get("user_key") or "").strip()
    if not user_key:
        return None
    return {
        "id": str(log.get("id") or ""),
        "timestamp": str(log.get("timestamp") or ""),
        "user_key": user_key,
        "action": str(metadata.get("penalty_action") or log.get("action") or "").strip(),
        "level": str(penalty.get("level") or "").strip() or "cooldown",
        "detail": str(penalty.get("detail") or "").strip(),
        "status_code": int(penalty.get("status_code") or status.HTTP_429_TOO_MANY_REQUESTS),
        "until": str(penalty.get("until") or "").strip() or None,
        "operator": str(metadata.get("operator") or log.get("user") or "").strip() or "system",
        "note": str(metadata.get("note") or "").strip(),
        "source": "audit_log",
    }


def _load_incident_by_id(incident_id: str) -> dict | None:
    normalized_incident_id = str(incident_id or "").strip()
    if not normalized_incident_id:
        return None
    for log in _sort_logs_desc(_load_audit_logs()):
        if str(log.get("id") or "").strip() == normalized_incident_id:
            return log
    return None


def _append_security_rule_audit_log(
    *,
    action: str,
    rule: dict,
    operator: str,
    note: str = "",
) -> dict:
    payload = {
        "id": f"audit-{uuid4().hex[:10]}",
        "timestamp": store.now_string(),
        "action": f"Security rule {action}",
        "user": operator,
        "resource": SECURITY_RULE_RESOURCE,
        "status": "success",
        "ip": "-",
        "details": f"Security rule {rule['id']} {action}",
        "metadata": {
            "version_id": f"rule-version-{uuid4().hex[:10]}",
            "rule_id": str(rule["id"]),
            "rule_action": action,
            "operator": operator,
            "note": note,
            "rule_snapshot": _build_security_rule_snapshot(rule),
        },
    }
    store.audit_logs.insert(0, payload)
    del store.audit_logs[200:]
    persistence_service.append_audit_log(log=payload)
    return payload


def _load_rule_history(rule_id: str) -> list[dict]:
    items: list[dict] = []
    normalized_rule_id = str(rule_id or "").strip()
    for log in _sort_logs_desc(_load_audit_logs()):
        item = _rule_history_entry_from_audit_log(log)
        if item is None:
            continue
        if normalized_rule_id and item["rule_id"] != normalized_rule_id:
            continue
        items.append(item)
    return items


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


def _load_security_subject_states() -> list[dict]:
    list_states = getattr(persistence_service, "list_security_subject_states", None)
    if callable(list_states):
        database_states = list_states()
        if database_states is not None:
            return database_states
    if getattr(persistence_service, "enabled", False):
        return []
    return []


def _read_security_subject_state(user_key: str) -> tuple[dict | None, bool]:
    read_state = getattr(persistence_service, "read_security_subject_state", None)
    if callable(read_state):
        return read_state(user_key)

    get_state = getattr(persistence_service, "get_security_subject_state", None)
    if not callable(get_state):
        return None, False

    state = get_state(user_key)
    if state is not None:
        return state, True
    if getattr(persistence_service, "enabled", False):
        return None, True
    return None, False


def _normalize_penalty_payload(penalty: object, *, now: datetime) -> dict | None:
    if not isinstance(penalty, dict):
        return None
    until = _parse_timestamp(str(penalty.get("until") or ""))
    if until is None or until <= now:
        return None

    try:
        status_code = int(penalty.get("status_code") or status.HTTP_429_TOO_MANY_REQUESTS)
    except (TypeError, ValueError):
        status_code = status.HTTP_429_TOO_MANY_REQUESTS

    return {
        "level": str(penalty.get("level") or "").strip() or "cooldown",
        "detail": str(penalty.get("detail") or "").strip() or "Security policy blocked this user",
        "status_code": status_code,
        "until": until.isoformat(),
    }


def _append_security_audit_log(
    *,
    action: str,
    user: str,
    status_value: str,
    details: str,
    metadata: dict | None = None,
) -> None:
    payload = {
        "id": f"audit-{uuid4().hex[:10]}",
        "timestamp": store.now_string(),
        "action": action,
        "user": user,
        "resource": "security_penalty",
        "status": status_value,
        "ip": "-",
        "details": details,
    }
    if isinstance(metadata, dict) and metadata:
        payload["metadata"] = store.clone(metadata)
    store.audit_logs.insert(0, payload)
    del store.audit_logs[200:]
    persistence_service.append_audit_log(log=payload)


def _build_security_incident_review_from_audit_log(log: dict) -> dict | None:
    if str(log.get("resource") or "").strip() != SECURITY_INCIDENT_REVIEW_RESOURCE:
        return None
    metadata = _log_metadata(log)
    incident_id = str(metadata.get("incident_id") or "").strip()
    review_action = str(metadata.get("review_action") or "").strip().lower()
    if not incident_id or review_action not in SECURITY_INCIDENT_REVIEW_ACTIONS:
        return None
    return {
        "id": str(metadata.get("review_id") or log.get("id") or "").strip(),
        "timestamp": str(log.get("timestamp") or ""),
        "incident_id": incident_id,
        "action": review_action,
        "note": str(metadata.get("note") or "").strip(),
        "reviewer": str(metadata.get("reviewer") or log.get("user") or "").strip() or "system",
        "source": "audit_log",
    }


def _append_security_incident_review_audit_log(
    *,
    incident_id: str,
    review_action: str,
    note: str,
    reviewer: str,
) -> dict:
    review_id = f"incident-review-{uuid4().hex[:10]}"
    payload = {
        "id": f"audit-{uuid4().hex[:10]}",
        "timestamp": store.now_string(),
        "action": f"Security incident review:{review_action}",
        "user": reviewer,
        "resource": SECURITY_INCIDENT_REVIEW_RESOURCE,
        "status": "success",
        "ip": "-",
        "details": f"Security incident {incident_id} marked as {review_action}",
        "metadata": {
            "review_id": review_id,
            "incident_id": incident_id,
            "review_action": review_action,
            "note": note,
            "reviewer": reviewer,
        },
    }
    store.audit_logs.insert(0, payload)
    del store.audit_logs[200:]
    persistence_service.append_audit_log(log=payload)
    return _build_security_incident_review_from_audit_log(payload) or {
        "id": review_id,
        "timestamp": str(payload["timestamp"]),
        "incident_id": incident_id,
        "action": review_action,
        "note": note,
        "reviewer": reviewer,
        "source": "audit_log",
    }


def list_active_security_penalties() -> dict:
    now = datetime.now(UTC)
    penalties: list[dict] = []
    subject_states = _load_security_subject_states()
    if subject_states:
        for state in subject_states:
            penalty = _normalize_penalty_payload(state.get("active_penalty"), now=now)
            if penalty is None:
                continue
            penalties.append(
                {
                    "user_key": str(state.get("user_key") or "").strip(),
                    "level": penalty["level"],
                    "detail": penalty["detail"],
                    "status_code": penalty["status_code"],
                    "until": penalty["until"],
                    "updated_at": str(state.get("updated_at") or ""),
                }
            )
    elif not getattr(persistence_service, "enabled", False):
        for item in security_gateway_service.list_runtime_active_penalties(now=now):
            penalty = _normalize_penalty_payload(item, now=now)
            if penalty is None:
                continue
            penalties.append(
                {
                    "user_key": str(item.get("user_key") or "").strip(),
                    "level": penalty["level"],
                    "detail": penalty["detail"],
                    "status_code": penalty["status_code"],
                    "until": penalty["until"],
                    "updated_at": penalty["until"],
                }
            )

    penalties.sort(key=lambda item: str(item.get("until") or ""), reverse=True)
    return {
        "items": penalties,
        "total": len(penalties),
    }


def list_security_penalty_history(*, user_key: str | None = None) -> dict:
    normalized_user_key = str(user_key or "").strip()
    items: list[dict] = []
    for log in _sort_logs_desc(_load_audit_logs()):
        item = _penalty_history_entry_from_audit_log(log)
        if item is None:
            continue
        if normalized_user_key and item["user_key"] != normalized_user_key:
            continue
        items.append(item)
    return {"items": items, "total": len(items)}


def create_manual_security_penalty(
    *,
    user_key: str,
    level: str,
    detail: str,
    duration_seconds: int,
    status_code: int,
    note: str,
    operator_user: str,
) -> dict:
    normalized_user_key = str(user_key or "").strip()
    normalized_level = str(level or "").strip().lower()
    normalized_detail = str(detail or "").strip()
    normalized_note = str(note or "").strip()
    if not normalized_user_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="user_key is required")
    if normalized_level not in {"cooldown", "ban"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid penalty level")
    if not normalized_detail:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="detail is required")
    try:
        normalized_duration = max(int(duration_seconds), 1)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="duration_seconds is required")
    try:
        normalized_status_code = int(status_code)
    except (TypeError, ValueError):
        normalized_status_code = status.HTTP_429_TOO_MANY_REQUESTS

    now = datetime.now(UTC)
    penalty = security_gateway_service._apply_penalty(  # noqa: SLF001 - local trusted-zone write
        normalized_user_key,
        now,
        level=normalized_level,
        detail=normalized_detail,
        duration_seconds=normalized_duration,
        status_code=normalized_status_code,
    )
    penalty_payload = {
        "user_key": normalized_user_key,
        "level": str(penalty["level"]),
        "detail": str(penalty["detail"]),
        "status_code": int(penalty["status_code"]),
        "until": str(penalty["until"]),
        "updated_at": now.isoformat(),
    }
    _append_security_audit_log(
        action="安全处罚创建",
        user=operator_user,
        status_value="success",
        details=f"Created {normalized_level} penalty for {normalized_user_key}",
        metadata={
            "target_user_key": normalized_user_key,
            "penalty_action": "manual_create",
            "operator": operator_user,
            "note": normalized_note,
            "penalty": store.clone(penalty_payload),
        },
    )
    return {
        "ok": True,
        "message": "Security penalty created",
        "user_key": normalized_user_key,
        "penalty": penalty_payload,
        "released_penalty": penalty_payload,
    }


def release_active_security_penalty(
    user_key: str,
    *,
    operator_user: str,
) -> dict:
    normalized_user_key = str(user_key or "").strip()
    if not normalized_user_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="user_key is required")

    subject_state, database_authoritative = _read_security_subject_state(normalized_user_key)
    released_updated_at = ""
    now = datetime.now(UTC)
    if database_authoritative:
        if subject_state is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Security penalty not found")

        active_penalty = _normalize_penalty_payload(subject_state.get("active_penalty"), now=now)
        if active_penalty is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Security penalty not found")

        updated_state = {
            "user_key": normalized_user_key,
            "rate_request_timestamps": [],
            "incident_timestamps": [],
            "active_penalty": None,
            "updated_at": now.isoformat(),
        }
        if not persistence_service.upsert_security_subject_state(updated_state):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to release security penalty",
            )
        released_updated_at = str(subject_state.get("updated_at") or "")
    else:
        active_penalty = next(
            (
                item
                for item in list_active_security_penalties()["items"]
                if str(item.get("user_key") or "").strip() == normalized_user_key
            ),
            None,
        )
        if active_penalty is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Security penalty not found")
        released_updated_at = str(active_penalty.get("updated_at") or "")

    security_gateway_service.clear_subject_state(normalized_user_key)

    _append_security_audit_log(
        action="安全处罚解除",
        user=operator_user,
        status_value="success",
        details=f"Released {active_penalty['level']} penalty for {normalized_user_key}",
        metadata={
            "target_user_key": normalized_user_key,
            "released_penalty": store.clone(active_penalty),
            "operator": operator_user,
            "reset_counters": True,
        },
    )

    return {
        "ok": True,
        "message": "Security penalty released",
        "user_key": normalized_user_key,
        "released_penalty": {
            "user_key": normalized_user_key,
            "level": active_penalty["level"],
            "detail": active_penalty["detail"],
            "status_code": active_penalty["status_code"],
            "until": active_penalty["until"],
            "updated_at": released_updated_at,
        },
    }


def list_security_rules() -> dict:
    items = _load_security_rules()
    logs = _select_reference_logs(_load_audit_logs())
    enabled_count = sum(1 for rule in items if rule["enabled"])
    summary = {
        "today_events": len(logs),
        "blocked_threats": sum(1 for log in logs if str(log.get("status") or "").lower() == "error"),
        "alert_notifications": sum(
            1 for log in logs if str(log.get("status") or "").lower() == "warning"
        ),
        "active_rules": enabled_count,
    }
    return {
        "summary": summary,
        "items": items,
        "total": len(items),
    }


def get_security_rule(rule_id: str) -> dict:
    rule = _find_security_rule_mutable(rule_id)
    return store.clone(rule)


def get_security_report(*, window_hours: int = 24) -> dict:
    normalized_window_hours = _normalize_window_hours(window_hours)
    rules = _load_security_rules()
    all_logs = _load_audit_logs()
    report_logs = _logs_within_window(all_logs, window_hours=normalized_window_hours)
    if not report_logs:
        report_logs = _select_reference_logs(all_logs)
    report_logs = _sort_logs_desc(report_logs)

    total_logs = len(report_logs)
    unique_users = {
        str(log.get("user") or "").strip()
        for log in report_logs
        if str(log.get("user") or "").strip()
    }
    status_counter = Counter(str(log.get("status") or "unknown").strip().lower() or "unknown" for log in report_logs)
    layer_counter = Counter(_incident_layer_key(log) for log in report_logs)
    resource_counter = Counter(str(log.get("resource") or "unknown").strip() or "unknown" for log in report_logs)
    action_counter = Counter(str(log.get("action") or "unknown").strip() or "unknown" for log in report_logs)
    top_rules = sorted(
        [
            {
                "key": str(rule.get("id") or "").strip() or "unknown",
                "label": str(rule.get("name") or "").strip() or "未命名规则",
                "count": max(int(rule.get("hit_count") or 0), 0),
            }
            for rule in rules
        ],
        key=lambda item: (item["count"], item["label"]),
        reverse=True,
    )[:5]
    rule_total = sum(item["count"] for item in top_rules) or 1

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "window_hours": normalized_window_hours,
        "summary": {
            "total_events": total_logs,
            "blocked_threats": status_counter.get("error", 0),
            "alert_notifications": status_counter.get("warning", 0),
            "active_rules": sum(1 for rule in rules if bool(rule.get("enabled"))),
            "unique_users": len(unique_users),
            "rewrite_events": _count_rewrite_events(report_logs),
            "high_risk_events": _count_high_risk_events(report_logs),
        },
        "status_breakdown": _build_breakdown(status_counter, total=total_logs, limit=3),
        "gateway_layer_breakdown": [
            {
                **item,
                "label": SECURITY_LAYER_LABELS.get(item["key"], item["label"]),
            }
            for item in _build_breakdown(layer_counter, total=total_logs, limit=6)
        ],
        "top_resources": _build_breakdown(resource_counter, total=total_logs),
        "top_actions": _build_breakdown(action_counter, total=total_logs),
        "top_rules": [
            {
                **item,
                "share": round((item["count"] / rule_total) * 100, 1),
            }
            for item in top_rules
        ],
        "recent_incidents": [
            _build_recent_incident(log)
            for log in report_logs
            if str(log.get("status") or "").strip().lower() in {"warning", "error"}
        ][:8],
    }


def list_security_incident_reviews(*, incident_id: str | None = None) -> dict:
    normalized_incident_id = str(incident_id or "").strip()
    items: list[dict] = []
    for log in _sort_logs_desc(_load_audit_logs()):
        item = _build_security_incident_review_from_audit_log(log)
        if item is None:
            continue
        if normalized_incident_id and item["incident_id"] != normalized_incident_id:
            continue
        items.append(item)
    return {"items": items, "total": len(items)}


def create_security_incident_review(
    *,
    incident_id: str,
    action: str,
    note: str,
    reviewer: str,
) -> dict:
    normalized_incident_id = str(incident_id or "").strip()
    normalized_action = str(action or "").strip().lower()
    normalized_note = str(note or "").strip()
    normalized_reviewer = str(reviewer or "").strip() or "system"
    if not normalized_incident_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="incident_id is required")
    if normalized_action not in SECURITY_INCIDENT_REVIEW_ACTIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid review action")

    review = _append_security_incident_review_audit_log(
        incident_id=normalized_incident_id,
        review_action=normalized_action,
        note=normalized_note,
        reviewer=normalized_reviewer,
    )
    return {
        "ok": True,
        "message": "Security incident review created",
        "review": review,
    }


def create_security_rule(
    *,
    name: str,
    description: str,
    rule_type: str,
    enabled: bool,
    operator_user: str,
) -> dict:
    normalized_name = str(name or "").strip()
    normalized_description = str(description or "").strip()
    if not normalized_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name is required")
    rule = {
        "id": f"rule-{uuid4().hex[:8]}",
        "name": normalized_name,
        "description": normalized_description,
        "type": _normalize_rule_type(rule_type),
        "enabled": bool(enabled),
        "hit_count": 0,
        "last_triggered": "从未",
    }
    store.security_rules.insert(0, store.clone(rule))
    persistence_service.persist_security_rule_state(rule=rule)
    _append_security_rule_audit_log(action="created", rule=rule, operator=operator_user)
    return {"ok": True, "message": "Security rule created", "rule": store.clone(rule)}


def list_security_rule_versions(rule_id: str) -> dict:
    items = _load_rule_history(rule_id)
    return {"items": items, "total": len(items)}


def get_security_rule_hit_details(rule_id: str) -> dict:
    rule = _find_security_rule_mutable(rule_id)
    rule_name = str(rule.get("name") or "").strip().lower()
    items: list[dict] = []
    for log in _sort_logs_desc(_load_audit_logs()):
        rule_label = str(_incident_rule_label(log) or "").strip().lower()
        action = str(log.get("action") or "").strip().lower()
        if not rule_name or (rule_name not in rule_label and rule_name not in action):
            continue
        items.append(
            {
                **_build_recent_incident(log),
            }
        )

    summary = {
        "total_hits": len(items),
        "warning_hits": sum(1 for item in items if str(item.get("status") or "") == "warning"),
        "error_hits": sum(1 for item in items if str(item.get("status") or "") == "error"),
        "latest_hit_at": str(items[0].get("timestamp") or "") if items else None,
    }
    return {"rule": store.clone(rule), "summary": summary, "items": items[:50], "total": len(items)}


def rollback_security_rule(
    *,
    rule_id: str,
    version_id: str,
    operator_user: str,
) -> dict:
    versions = _load_rule_history(rule_id)
    target = next((item for item in versions if item["id"] == str(version_id or "").strip()), None)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Security rule version not found")
    snapshot = store.clone(target["snapshot"])
    rule = _find_security_rule_mutable(rule_id)
    rule.clear()
    rule.update(snapshot)
    persistence_service.persist_security_rule_state(rule=rule)
    _append_security_rule_audit_log(
        action="rollback",
        rule=rule,
        operator=operator_user,
        note=f"rollback_to={version_id}",
    )
    return {"ok": True, "message": "Security rule rolled back", "rule": store.clone(rule)}


def list_security_user_risk_profiles() -> dict:
    profiles: dict[str, dict] = {}
    reviews_by_incident = {
        item["incident_id"]: item
        for item in list_security_incident_reviews().get("items", [])
    }
    for log in _sort_logs_desc(_load_audit_logs()):
        user_key = str(log.get("user") or "").strip()
        if not user_key:
            continue
        profile = profiles.setdefault(
            user_key,
            {
                "key": user_key,
                "label": user_key,
                "event_count": 0,
                "blocked_count": 0,
                "warning_count": 0,
                "review_pending": 0,
                "false_positive_count": 0,
                "latest_event_at": None,
                "risk_score": 0,
                "entity_refs": _extract_entity_refs(log),
            },
        )
        profile["event_count"] += 1
        status_value = str(log.get("status") or "").strip().lower()
        if status_value == "error":
            profile["blocked_count"] += 1
            profile["risk_score"] += 5
        elif status_value == "warning":
            profile["warning_count"] += 1
            profile["risk_score"] += 2
        incident_review = reviews_by_incident.get(str(log.get("id") or ""))
        if incident_review is None and status_value in {"warning", "error"}:
            profile["review_pending"] += 1
        if incident_review is not None and incident_review["action"] == "false_positive":
            profile["false_positive_count"] += 1
            profile["risk_score"] = max(profile["risk_score"] - 2, 0)
        if profile["latest_event_at"] is None:
            profile["latest_event_at"] = str(log.get("timestamp") or "")
    items = sorted(
        profiles.values(),
        key=lambda item: (int(item["risk_score"]), int(item["event_count"])),
        reverse=True,
    )
    return {"items": items[:20], "total": len(items)}


def list_security_channel_risk_profiles() -> dict:
    profiles: dict[str, dict] = {}
    for log in _sort_logs_desc(_load_audit_logs()):
        metadata = _log_metadata(log)
        channel = str(metadata.get("channel") or metadata.get("platform") or log.get("resource") or "").strip()
        if not channel:
            continue
        profile = profiles.setdefault(
            channel,
            {
                "key": channel,
                "label": channel,
                "event_count": 0,
                "blocked_count": 0,
                "warning_count": 0,
                "review_pending": 0,
                "false_positive_count": 0,
                "latest_event_at": None,
                "risk_score": 0,
                "entity_refs": _extract_entity_refs(log),
            },
        )
        profile["event_count"] += 1
        status_value = str(log.get("status") or "").strip().lower()
        if status_value == "error":
            profile["blocked_count"] += 1
            profile["risk_score"] += 5
        elif status_value == "warning":
            profile["warning_count"] += 1
            profile["risk_score"] += 2
        if status_value in {"warning", "error"}:
            profile["review_pending"] += 1
        if profile["latest_event_at"] is None:
            profile["latest_event_at"] = str(log.get("timestamp") or "")
    items = sorted(
        profiles.values(),
        key=lambda item: (int(item["risk_score"]), int(item["event_count"])),
        reverse=True,
    )
    return {"items": items[:20], "total": len(items)}


def get_security_risk_trends(*, days: int = 7) -> dict:
    normalized_days = max(1, min(int(days), 30))
    today = datetime.now(UTC).date()
    bucket_keys = [(today - timedelta(days=offset)).isoformat() for offset in range(normalized_days - 1, -1, -1)]
    buckets = {
        key: {
            "bucket": key,
            "total_events": 0,
            "blocked_events": 0,
            "warning_events": 0,
            "false_positive_events": 0,
            "review_events": 0,
        }
        for key in bucket_keys
    }
    reviews = list_security_incident_reviews().get("items", [])
    false_positive_ids = {item["incident_id"] for item in reviews if item["action"] == "false_positive"}
    reviewed_ids = {item["incident_id"] for item in reviews}
    for log in _load_audit_logs():
        parsed = _parse_timestamp(str(log.get("timestamp") or ""))
        if parsed is None:
            continue
        bucket = parsed.date().isoformat()
        if bucket not in buckets:
            continue
        status_value = str(log.get("status") or "").strip().lower()
        buckets[bucket]["total_events"] += 1
        if status_value == "error":
            buckets[bucket]["blocked_events"] += 1
        if status_value == "warning":
            buckets[bucket]["warning_events"] += 1
        incident_id = str(log.get("id") or "")
        if incident_id in false_positive_ids:
            buckets[bucket]["false_positive_events"] += 1
        if incident_id in reviewed_ids:
            buckets[bucket]["review_events"] += 1
    points = [buckets[key] for key in bucket_keys]
    return {"points": points, "total": len(points)}


def list_security_alert_subscriptions() -> dict:
    items = _read_json_setting(SECURITY_ALERT_SUBSCRIPTIONS_KEY, default=[])
    return {"items": items, "total": len(items)}


def create_security_alert_subscription(
    *,
    channel: str,
    target: str,
    enabled: bool,
    severity_scope: list[str],
) -> dict:
    normalized_target = str(target or "").strip()
    normalized_channel = str(channel or "").strip().lower()
    if normalized_channel not in {"email", "webhook", "nats"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid subscription channel")
    if not normalized_target:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="target is required")
    now = store.now_string()
    item = {
        "id": f"security-sub-{uuid4().hex[:8]}",
        "channel": normalized_channel,
        "target": normalized_target,
        "enabled": bool(enabled),
        "severity_scope": [str(value).strip().lower() for value in severity_scope if str(value).strip()] or ["warning", "error"],
        "created_at": now,
        "updated_at": now,
    }
    items = list_security_alert_subscriptions()["items"]
    items.append(item)
    _write_json_setting(SECURITY_ALERT_SUBSCRIPTIONS_KEY, items)
    return {"ok": True, "message": "Security alert subscription created", "subscription": item}


def update_security_alert_subscription(
    *,
    subscription_id: str,
    target: str | None = None,
    enabled: bool | None = None,
    severity_scope: list[str] | None = None,
) -> dict:
    items = list_security_alert_subscriptions()["items"]
    normalized_id = str(subscription_id or "").strip()
    item = next((candidate for candidate in items if str(candidate.get("id") or "").strip() == normalized_id), None)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Security alert subscription not found")
    if target is not None:
        normalized_target = str(target).strip()
        if not normalized_target:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="target is required")
        item["target"] = normalized_target
    if enabled is not None:
        item["enabled"] = bool(enabled)
    if severity_scope is not None:
        item["severity_scope"] = [
            str(value).strip().lower() for value in severity_scope if str(value).strip()
        ] or ["warning", "error"]
    item["updated_at"] = store.now_string()
    _write_json_setting(SECURITY_ALERT_SUBSCRIPTIONS_KEY, items)
    return {"ok": True, "message": "Security alert subscription updated", "subscription": item}


def export_security_report(*, period: str = "daily") -> dict:
    normalized_period = str(period or "daily").strip().lower()
    if normalized_period not in {"daily", "weekly"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid export period")
    window_hours = 24 if normalized_period == "daily" else 24 * 7
    report = get_security_report(window_hours=window_hours)
    trends = get_security_risk_trends(days=1 if normalized_period == "daily" else 7)
    summary = report["summary"]
    content = "\n".join(
        [
            f"# Security {normalized_period.title()} Report",
            f"- generated_at: {report['generated_at']}",
            f"- window_hours: {report['window_hours']}",
            f"- total_events: {summary['total_events']}",
            f"- blocked_threats: {summary['blocked_threats']}",
            f"- alert_notifications: {summary['alert_notifications']}",
            f"- rewrite_events: {summary['rewrite_events']}",
            f"- high_risk_events: {summary['high_risk_events']}",
            "",
            "## Trend",
            *[
                (
                    f"- {point['bucket']}: total={point['total_events']}, "
                    f"blocked={point['blocked_events']}, warning={point['warning_events']}, "
                    f"false_positive={point['false_positive_events']}, reviewed={point['review_events']}"
                )
                for point in trends["points"]
            ],
        ]
    )
    return {
        "generated_at": report["generated_at"],
        "period": normalized_period,
        "content_type": "markdown",
        "content": content,
        "summary": summary,
    }


def update_security_rule(
    rule_id: str,
    enabled: bool | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    rule_type: str | None = None,
    operator_user: str = "system",
) -> dict:
    rule = _find_security_rule_mutable(rule_id)
    if enabled is not None:
        rule["enabled"] = bool(enabled)
    if name is not None:
        normalized_name = str(name).strip()
        if not normalized_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name is required")
        rule["name"] = normalized_name
    if description is not None:
        rule["description"] = str(description).strip()
    if rule_type is not None:
        rule["type"] = _normalize_rule_type(rule_type)
    persistence_service.persist_security_rule_state(rule=rule)
    _append_security_rule_audit_log(action="updated", rule=rule, operator=operator_user)
    return {"ok": True, "message": "Security rule updated", "rule": store.clone(rule)}


def get_security_guardian() -> dict:
    agents_payload = list_agents()
    for agent in agents_payload.get("items", []):
        if str(agent.get("type") or "").strip().lower() == "security":
            return get_agent(str(agent.get("id") or "").strip())
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Security guardian not found")
