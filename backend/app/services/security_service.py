from collections import Counter
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException, status

from app.services.security_gateway_service import security_gateway_service
from app.services.persistence_service import persistence_service
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
            store.clone(log)
            for log in report_logs
            if str(log.get("status") or "").strip().lower() in {"warning", "error"}
        ][:8],
    }


def update_security_rule(rule_id: str, enabled: bool) -> dict:
    rule = _find_security_rule_mutable(rule_id)
    rule["enabled"] = enabled
    persistence_service.persist_security_rule_state(rule=rule)
    return {"ok": True, "message": "Security rule updated", "rule": store.clone(rule)}
