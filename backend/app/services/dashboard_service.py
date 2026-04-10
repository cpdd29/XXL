from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
from io import StringIO

from app.services.persistence_service import persistence_service
from app.services.store import store
from app.services.task_service import enrich_task_payload


ACTIVE_AGENT_STATUSES = {"running", "waiting"}
ACTIVE_WORKFLOW_STATUSES = {"active", "running"}
INFLIGHT_TASK_STATUSES = {"pending", "running"}
COMPLETED_TASK_STATUSES = {"completed"}
FAILED_TASK_STATUSES = {"failed"}
CHART_BUCKETS = 7
CHART_BUCKET_HOURS = 4
DEFAULT_AUDIT_LOG_LIMIT = 20
DEFAULT_REALTIME_LOG_LIMIT = 20
DEFAULT_REALTIME_PAYLOAD_LIMIT = 5
AUDIT_LOG_EXPORT_HEADERS = {
    "timestamp": "时间",
    "action": "动作",
    "user": "用户",
    "resource": "资源",
    "status": "状态",
    "ip": "IP",
    "details": "详情",
}

FAILURE_BREAKDOWN_STAGE_ORDER = ("route", "dispatch", "execution", "outbound")
FAILURE_BREAKDOWN_LABELS = {
    "route": "路由失败",
    "dispatch": "调度失败",
    "execution": "执行失败",
    "outbound": "回传失败",
}


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    normalized = str(value).strip()
    if not normalized:
        return None

    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    candidates = (
        normalized,
        normalized.replace(" ", "T"),
    )

    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except ValueError:
            continue

    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(normalized, pattern).replace(tzinfo=UTC)
            return parsed
        except ValueError:
            continue

    return None

def _load_agents() -> list[dict]:
    database_agents = persistence_service.list_agents()
    if database_agents is not None:
        return database_agents
    if getattr(persistence_service, "enabled", False):
        return []
    return store.clone(store.agents)


def _load_tasks() -> list[dict]:
    database_tasks = persistence_service.list_tasks()
    if database_tasks is not None:
        return database_tasks
    if getattr(persistence_service, "enabled", False):
        return []
    return store.clone(store.tasks)


def _load_workflows() -> list[dict]:
    database_workflows = persistence_service.list_workflows()
    if database_workflows is not None:
        return database_workflows
    if getattr(persistence_service, "enabled", False):
        return []
    return store.clone(store.workflows)


def _load_workflow_runs() -> list[dict]:
    database_runs = persistence_service.list_workflow_runs()
    if database_runs is not None:
        return database_runs
    if getattr(persistence_service, "enabled", False):
        return []
    return store.clone(store.workflow_runs)


def _load_operational_logs(*, limit: int | None = None) -> list[dict]:
    database_logs = persistence_service.list_operational_logs(limit=limit)
    if database_logs is not None:
        return database_logs
    if getattr(persistence_service, "enabled", False):
        return []
    return []


def _time_label(value: str | None) -> str:
    parsed = _parse_datetime(value)
    if parsed is None:
        return "--:--:--"
    return parsed.strftime("%H:%M:%S")


def _workflow_run_sort_key(run: dict) -> datetime:
    return (
        _parse_datetime(run.get("updated_at"))
        or _parse_datetime(run.get("created_at"))
        or datetime.min.replace(tzinfo=UTC)
    )


def _normalize_realtime_log(
    log: dict | None,
    *,
    run: dict | None = None,
    index: int = 0,
) -> dict | None:
    if not isinstance(log, dict):
        return None

    run_id = str((run or {}).get("id") or "run").strip() or "run"
    timestamp = str(log.get("timestamp") or "").strip()
    if not timestamp:
        timestamp = _time_label((run or {}).get("updated_at") or (run or {}).get("created_at"))

    message = str(log.get("message") or "").strip()
    if not message:
        fallback_stage = str((run or {}).get("current_stage") or "").strip()
        message = fallback_stage or f"工作流 {run_id} 状态更新"

    agent = str(log.get("agent") or "").strip()
    if not agent:
        agent = str((run or {}).get("workflow_name") or "Workflow Engine").strip()

    return {
        "id": str(log.get("id") or f"{run_id}-log-{index}"),
        "timestamp": timestamp,
        "type": str(log.get("type") or "info"),
        "agent": agent,
        "message": message,
    }


def _realtime_sort_at(
    timestamp: str | None,
    *,
    run: dict | None = None,
    reference_at: datetime | None = None,
) -> datetime:
    parsed = _parse_datetime(timestamp)
    if parsed is not None:
        return parsed

    normalized = str(timestamp or "").strip()
    if normalized.count(":") == 2:
        base_time = (
            _parse_datetime((run or {}).get("updated_at"))
            or _parse_datetime((run or {}).get("created_at"))
            or reference_at
        )
        if base_time is not None:
            try:
                hour, minute, second = (int(part) for part in normalized.split(":"))
                return base_time.replace(
                    hour=hour,
                    minute=minute,
                    second=second,
                    microsecond=0,
                )
            except ValueError:
                pass

    return (
        _parse_datetime((run or {}).get("updated_at"))
        or _parse_datetime((run or {}).get("created_at"))
        or datetime.min.replace(tzinfo=UTC)
    )


def _build_realtime_entries_from_runs(
    runs: list[dict],
    *,
    limit: int,
) -> list[tuple[dict, datetime]]:
    items: list[tuple[dict, datetime]] = []
    ordered_runs = sorted(runs, key=_workflow_run_sort_key, reverse=True)
    for run in ordered_runs:
        logs = run.get("logs")
        if not isinstance(logs, list) or not logs:
            continue

        for index, log in enumerate(reversed(logs)):
            normalized = _normalize_realtime_log(log, run=run, index=index)
            if normalized is None:
                continue
            items.append((normalized, _realtime_sort_at(normalized.get("timestamp"), run=run)))
            if len(items) >= limit:
                return items
    return items


def _build_realtime_logs_from_runs(runs: list[dict], *, limit: int) -> list[dict]:
    return [item for item, _ in _build_realtime_entries_from_runs(runs, limit=limit)]


def _normalize_operational_log_as_realtime(log: dict | None) -> dict | None:
    if not isinstance(log, dict):
        return None

    message = str(log.get("message") or "").strip()
    if not message:
        return None

    agent = str(log.get("agent") or "").strip() or str(log.get("source") or "Runtime").strip()
    return {
        "id": str(log.get("id") or ""),
        "timestamp": _time_label(log.get("timestamp")),
        "type": str(log.get("type") or "info"),
        "agent": agent or "Runtime",
        "message": message,
    }


def _build_realtime_entries_from_operational_logs(
    logs: list[dict],
    *,
    limit: int,
) -> list[tuple[dict, datetime]]:
    items: list[tuple[dict, datetime]] = []
    for log in logs[:limit]:
        normalized = _normalize_operational_log_as_realtime(log)
        if normalized is None:
            continue
        items.append((normalized, _realtime_sort_at(log.get("timestamp"))))
        if len(items) >= limit:
            break
    return items


def _normalize_audit_log_as_realtime(log: dict | None) -> dict | None:
    if not isinstance(log, dict):
        return None

    status_value = str(log.get("status") or "").strip().lower()
    type_value = (
        "error"
        if status_value in {"error", "failed", "failure"}
        else "warning"
        if status_value == "warning"
        else "success"
        if status_value == "success"
        else "info"
    )
    message = str(log.get("details") or log.get("action") or "").strip()
    if not message:
        return None

    source = str(log.get("resource") or log.get("user") or "Audit").strip()
    return {
        "id": str(log.get("id") or ""),
        "timestamp": _time_label(log.get("timestamp")),
        "type": type_value,
        "agent": source or "Audit",
        "message": message,
    }


def _build_realtime_entries_from_audit_logs(
    logs: list[dict],
    *,
    limit: int,
) -> list[tuple[dict, datetime]]:
    items: list[tuple[dict, datetime]] = []
    for log in logs[:limit]:
        normalized = _normalize_audit_log_as_realtime(log)
        if normalized is None:
            continue
        items.append((normalized, _realtime_sort_at(log.get("timestamp"))))
        if len(items) >= limit:
            break
    return items


def _build_realtime_logs_from_audit_logs(logs: list[dict], *, limit: int) -> list[dict]:
    return [item for item, _ in _build_realtime_entries_from_audit_logs(logs, limit=limit)]


def _realtime_item_key(item: dict, *, source: str, index: int) -> str:
    item_id = str(item.get("id") or "").strip()
    if item_id:
        return item_id
    return f"{source}-{index}"


def _load_realtime_logs(*, limit: int = DEFAULT_REALTIME_LOG_LIMIT) -> list[dict]:
    normalized_limit = max(1, int(limit))
    persisted_entries = [
        *_build_realtime_entries_from_operational_logs(
            _load_operational_logs(limit=normalized_limit),
            limit=normalized_limit,
        ),
        *_build_realtime_entries_from_runs(_load_workflow_runs(), limit=normalized_limit),
        *_build_realtime_entries_from_audit_logs(_load_audit_logs(), limit=normalized_limit),
    ]
    persisted_entries.sort(key=lambda entry: entry[1], reverse=True)
    runtime_reference_at = max((sort_at for _, sort_at in persisted_entries), default=None)
    runtime_entries = [
        (
            normalized,
            _realtime_sort_at(
                normalized.get("timestamp"),
                reference_at=runtime_reference_at,
            ),
        )
        for index, item in enumerate(store.realtime_logs)
        if (normalized := _normalize_realtime_log(item, index=index)) is not None
    ]

    merged_entries: dict[str, tuple[dict, datetime]] = {}
    for index, (item, sort_at) in enumerate(persisted_entries):
        merged_entries[_realtime_item_key(item, source="persisted", index=index)] = (item, sort_at)

    for index, (item, sort_at) in enumerate(runtime_entries):
        merged_entries.setdefault(
            _realtime_item_key(item, source="runtime", index=index),
            (item, sort_at),
        )

    ordered_entries = list(merged_entries.values())
    ordered_entries.sort(key=lambda entry: entry[1], reverse=True)
    return [item for item, _ in ordered_entries[:normalized_limit]]


def _reference_time(tasks: list[dict], workflow_runs: list[dict]) -> datetime:
    candidates = [
        timestamp
        for timestamp in (
            *(_parse_datetime(task.get("created_at")) for task in tasks),
            *(_parse_datetime(run.get("created_at")) for run in workflow_runs),
            *(_parse_datetime(task.get("completed_at")) for task in tasks),
        )
        if timestamp is not None
    ]
    return max(candidates, default=datetime.now(UTC))


def _task_tokens(task: dict | None) -> int:
    if not task:
        return 0
    try:
        return max(0, int(task.get("tokens") or 0))
    except (TypeError, ValueError):
        return 0


def _build_request_events(reference_at: datetime, tasks: list[dict], workflow_runs: list[dict]) -> list[dict]:
    tasks_by_id = {str(task["id"]): task for task in tasks}

    if workflow_runs:
        events: list[dict] = []
        for run in workflow_runs:
            created_at = _parse_datetime(run.get("created_at"))
            if created_at is None:
                continue
            task = tasks_by_id.get(str(run.get("task_id")))
            events.append(
                {
                    "created_at": created_at,
                    "tokens": _task_tokens(task),
                    "status": str(run.get("status") or task.get("status") if task else run.get("status") or ""),
                }
            )
        if events:
            return events

    return [
        {
            "created_at": created_at,
            "tokens": _task_tokens(task),
            "status": str(task.get("status") or ""),
        }
        for task in tasks
        if (created_at := _parse_datetime(task.get("created_at"))) is not None
    ]


def _percent(value: int, total: int) -> int:
    if total <= 0:
        return 0
    return round((value / total) * 100)


def _change_percent(current: int, previous: int) -> tuple[int, bool]:
    if previous <= 0:
        return (current * 100 if current > 0 else 0, current >= previous)

    delta = current - previous
    return (round(abs(delta) / previous * 100), delta >= 0)


def _build_chart_data(reference_at: datetime, events: list[dict]) -> list[dict]:
    window_start = reference_at - timedelta(hours=CHART_BUCKET_HOURS * (CHART_BUCKETS - 1))
    points = [
        {
            "time": (window_start + timedelta(hours=CHART_BUCKET_HOURS * index)).strftime("%H:%M"),
            "requests": 0,
            "tokens": 0,
        }
        for index in range(CHART_BUCKETS)
    ]

    for event in events:
        created_at = event["created_at"]
        if created_at < window_start or created_at > reference_at:
            continue

        bucket_index = int((created_at - window_start).total_seconds() // (CHART_BUCKET_HOURS * 3600))
        bucket_index = min(max(bucket_index, 0), CHART_BUCKETS - 1)
        points[bucket_index]["requests"] += 1
        points[bucket_index]["tokens"] += int(event["tokens"])

    return points


def _build_stats(
    reference_at: datetime,
    events: list[dict],
    agents: list[dict],
    workflows: list[dict],
    tasks: list[dict],
) -> list[dict]:
    enabled_agents = [agent for agent in agents if bool(agent.get("enabled", True))]
    active_agents = [agent for agent in enabled_agents if agent.get("status") in ACTIVE_AGENT_STATUSES]
    running_agents = [agent for agent in enabled_agents if agent.get("status") == "running"]
    idle_agents = [agent for agent in enabled_agents if agent.get("status") == "idle"]

    active_workflows = [workflow for workflow in workflows if workflow.get("status") in ACTIVE_WORKFLOW_STATUSES]
    draft_workflows = [workflow for workflow in workflows if workflow.get("status") == "draft"]

    pending_tasks = [task for task in tasks if task.get("status") == "pending"]
    running_tasks = [task for task in tasks if task.get("status") == "running"]

    last_24h_start = reference_at - timedelta(hours=24)
    last_12h_start = reference_at - timedelta(hours=12)

    recent_events = [event for event in events if event["created_at"] >= last_24h_start]
    current_window_events = [event for event in events if event["created_at"] >= last_12h_start]
    previous_window_events = [
        event for event in events if last_24h_start <= event["created_at"] < last_12h_start
    ]
    completed_recent = [event for event in recent_events if event["status"] in COMPLETED_TASK_STATUSES]
    failed_recent = [event for event in recent_events if event["status"] in FAILED_TASK_STATUSES]
    today_runs_trend_value, today_runs_trend_positive = _change_percent(
        len(current_window_events),
        len(previous_window_events),
    )

    return [
        {
            "key": "active_agents",
            "title": "活跃 Agent",
            "value": len(active_agents),
            "description": f"{len(running_agents)} 个运行中，{len(idle_agents)} 个待机",
            "trend_value": _percent(len(active_agents), len(enabled_agents)),
            "trend_positive": len(active_agents) >= max(1, len(enabled_agents) // 2),
        },
        {
            "key": "workflows",
            "title": "工作流",
            "value": len(workflows),
            "description": f"活跃 {len(active_workflows)} 个，草稿 {len(draft_workflows)} 个",
            "trend_value": _percent(len(active_workflows), len(workflows)),
            "trend_positive": len(active_workflows) >= len(draft_workflows),
        },
        {
            "key": "pending_tasks",
            "title": "待处理任务",
            "value": len(pending_tasks) + len(running_tasks),
            "description": f"运行中 {len(running_tasks)} 个，排队中 {len(pending_tasks)} 个",
            "trend_value": _percent(len(running_tasks), max(1, len(pending_tasks) + len(running_tasks))),
            "trend_positive": len(pending_tasks) == 0,
        },
        {
            "key": "today_runs",
            "title": "今日执行",
            "value": len(recent_events),
            "description": f"近 24h 完成 {len(completed_recent)} 个，失败 {len(failed_recent)} 个",
            "trend_value": today_runs_trend_value,
            "trend_positive": today_runs_trend_positive,
        },
    ]


def _build_agent_statuses(agents: list[dict]) -> list[dict]:
    return [
        {
            "id": str(agent["id"]),
            "name": str(agent["name"]),
            "type": str(agent["type"]),
            "status": str(agent["status"]),
            "tasks_completed": int(agent.get("tasks_completed", 0)),
            "avg_response_time": str(agent.get("avg_response_time") or "--"),
        }
        for agent in agents
    ]


def _build_failure_breakdown(tasks: list[dict], workflow_runs: list[dict]) -> list[dict]:
    run_by_id = {
        str(run.get("id") or "").strip(): run
        for run in workflow_runs
        if str(run.get("id") or "").strip()
    }
    counts = {stage: 0 for stage in FAILURE_BREAKDOWN_STAGE_ORDER}

    for task in tasks:
        run_id = str(task.get("workflow_run_id") or "").strip()
        enriched_task = enrich_task_payload(task, run=run_by_id.get(run_id))
        failure_stage = str(enriched_task.get("failure_stage") or "").strip().lower()
        if failure_stage in counts:
            counts[failure_stage] += 1

    return [
        {
            "stage": stage,
            "label": FAILURE_BREAKDOWN_LABELS[stage],
            "count": counts[stage],
        }
        for stage in FAILURE_BREAKDOWN_STAGE_ORDER
    ]


def get_stats() -> dict:
    agents = _load_agents()
    tasks = _load_tasks()
    workflows = _load_workflows()
    workflow_runs = _load_workflow_runs()
    reference_at = _reference_time(tasks, workflow_runs)
    events = _build_request_events(reference_at, tasks, workflow_runs)
    return {
        "stats": _build_stats(reference_at, events, agents, workflows, tasks),
        "chart_data": _build_chart_data(reference_at, events),
        "agent_statuses": _build_agent_statuses(agents),
        "failure_breakdown": _build_failure_breakdown(tasks, workflow_runs),
        "realtime_logs": _load_realtime_logs(),
    }


def _load_audit_logs() -> list[dict]:
    database_logs = persistence_service.list_audit_logs()
    if database_logs is not None:
        return database_logs
    if getattr(persistence_service, "enabled", False):
        return []
    return store.clone(store.audit_logs)


def _normalize_keyword(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _matches_keyword(log: dict, fields: tuple[str, ...], keyword: str | None) -> bool:
    if keyword is None:
        return True
    return any(keyword in str(log.get(field) or "").lower() for field in fields)


def _filter_audit_logs(
    *,
    search: str | None = None,
    status_filter: str | None = None,
    user: str | None = None,
    resource: str | None = None,
) -> list[dict]:
    items = _load_audit_logs()

    search_keyword = _normalize_keyword(search)
    status_keyword = _normalize_keyword(status_filter)
    user_keyword = _normalize_keyword(user)
    resource_keyword = _normalize_keyword(resource)

    if search_keyword is not None:
        items = [
            log
            for log in items
            if _matches_keyword(
                log,
                ("action", "user", "resource", "status", "ip", "details"),
                search_keyword,
            )
        ]

    if status_keyword is not None:
        items = [log for log in items if str(log.get("status") or "").lower() == status_keyword]

    if user_keyword is not None:
        items = [log for log in items if _matches_keyword(log, ("user",), user_keyword)]

    if resource_keyword is not None:
        items = [log for log in items if _matches_keyword(log, ("resource",), resource_keyword)]

    return items


def get_audit_logs(
    *,
    search: str | None = None,
    status_filter: str | None = None,
    user: str | None = None,
    resource: str | None = None,
    limit: int = DEFAULT_AUDIT_LOG_LIMIT,
    offset: int = 0,
) -> dict:
    items = _filter_audit_logs(
        search=search,
        status_filter=status_filter,
        user=user,
        resource=resource,
    )
    total = len(items)
    normalized_limit = max(1, int(limit))
    normalized_offset = max(0, int(offset))
    paginated_items = items[normalized_offset : normalized_offset + normalized_limit]

    return {
        "items": paginated_items,
        "total": total,
        "limit": normalized_limit,
        "offset": normalized_offset,
        "has_more": normalized_offset + len(paginated_items) < total,
    }


def export_audit_logs_csv(
    *,
    search: str | None = None,
    status_filter: str | None = None,
    user: str | None = None,
    resource: str | None = None,
) -> str:
    items = _filter_audit_logs(
        search=search,
        status_filter=status_filter,
        user=user,
        resource=resource,
    )

    buffer = StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(AUDIT_LOG_EXPORT_HEADERS.values())
    for item in items:
        writer.writerow(
            [
                str(item.get("timestamp") or ""),
                str(item.get("action") or ""),
                str(item.get("user") or ""),
                str(item.get("resource") or ""),
                str(item.get("status") or ""),
                str(item.get("ip") or ""),
                str(item.get("details") or ""),
            ]
        )
    return "\ufeff" + buffer.getvalue()


def next_realtime_payload() -> dict:
    return {
        "type": "heartbeat",
        "timestamp": store.now_string(),
        "items": _load_realtime_logs(limit=DEFAULT_REALTIME_PAYLOAD_LIMIT),
    }
