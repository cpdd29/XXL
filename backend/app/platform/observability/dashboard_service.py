from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
from io import StringIO

from app.modules.dispatch.application.task_view_service import task_view_service
from app.platform.persistence.persistence_service import persistence_service
from app.modules.reception.security_monitor.security_service import get_security_report
from app.platform.persistence.runtime_store import store
from app.modules.organization.application.tenancy_service import attach_scope, matches_scope
from app.modules.dispatch.workflow_runtime.workflow_runtime_snapshot_service import workflow_runtime_snapshot_service


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
SLA_WINDOW_HOURS = 24
HEALTHY_SUCCESS_RATE = 95.0
DEGRADED_SUCCESS_RATE = 85.0
HEALTHY_FAILURE_RATE = 5.0
DEGRADED_FAILURE_RATE = 15.0
HEALTHY_TIMEOUT_RATE = 3.0
DEGRADED_TIMEOUT_RATE = 8.0
HEALTHY_FALLBACK_RATE = 8.0
DEGRADED_FALLBACK_RATE = 20.0
HEALTHY_DELIVERY_FAILURE_RATE = 2.0
DEGRADED_DELIVERY_FAILURE_RATE = 8.0
HEALTHY_SECURITY_RISK_RATE = 3.0
DEGRADED_SECURITY_RISK_RATE = 10.0


def _project_task(task: dict, *, run: dict | None = None) -> dict:
    return task_view_service.build_task_projection(attach_scope(task), run=run)


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


def _filter_items_by_scope(items: list[dict], scope: dict[str, str] | None) -> list[dict]:
    if scope is None:
        return [attach_scope(item) for item in items]
    return [attach_scope(item) for item in items if matches_scope(item, scope)]


def _build_realtime_logs_from_audit_logs(logs: list[dict], *, limit: int) -> list[dict]:
    return [item for item, _ in _build_realtime_entries_from_audit_logs(logs, limit=limit)]


def _realtime_item_key(item: dict, *, source: str, index: int) -> str:
    item_id = str(item.get("id") or "").strip()
    if item_id:
        return item_id
    return f"{source}-{index}"


def _load_realtime_logs(*, limit: int = DEFAULT_REALTIME_LOG_LIMIT, scope: dict[str, str] | None = None) -> list[dict]:
    normalized_limit = max(1, int(limit))
    persisted_entries = [
        *_build_realtime_entries_from_operational_logs(
            _filter_items_by_scope(_load_operational_logs(limit=normalized_limit), scope),
            limit=normalized_limit,
        ),
        *_build_realtime_entries_from_runs(_filter_items_by_scope(_load_workflow_runs(), scope), limit=normalized_limit),
        *_build_realtime_entries_from_audit_logs(_filter_items_by_scope(_load_audit_logs(), scope), limit=normalized_limit),
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


def _run_metrics(run: dict | None) -> dict:
    if not isinstance(run, dict):
        return {
            "tokens_total": 0,
            "duration_ms": 0,
            "step_count": 0,
            "execution_agent_id": None,
            "execution_agent": None,
        }

    metrics = run.get("metrics")
    if not isinstance(metrics, dict):
        dispatch_context = run.get("dispatch_context")
        metrics = dispatch_context.get("run_metrics") if isinstance(dispatch_context, dict) else None
    if not isinstance(metrics, dict):
        metrics = {}

    try:
        tokens_total = max(int(metrics.get("tokens_total") or run.get("tokens_total") or 0), 0)
    except (TypeError, ValueError):
        tokens_total = 0
    try:
        duration_ms = max(int(metrics.get("duration_ms") or run.get("duration_ms") or 0), 0)
    except (TypeError, ValueError):
        duration_ms = 0
    try:
        step_count = max(int(metrics.get("step_count") or run.get("step_count") or 0), 0)
    except (TypeError, ValueError):
        step_count = 0

    execution_agent_id = (
        str(metrics.get("execution_agent_id") or run.get("execution_agent_id") or "").strip() or None
    )
    execution_agent = (
        str(metrics.get("execution_agent") or run.get("execution_agent") or "").strip() or None
    )
    return {
        "tokens_total": tokens_total,
        "duration_ms": duration_ms,
        "step_count": step_count,
        "execution_agent_id": execution_agent_id,
        "execution_agent": execution_agent,
    }


def _build_request_events(reference_at: datetime, tasks: list[dict], workflow_runs: list[dict]) -> list[dict]:
    tasks_by_id = {str(task["id"]): task for task in tasks}

    if workflow_runs:
        events: list[dict] = []
        for run in workflow_runs:
            created_at = _parse_datetime(run.get("created_at"))
            if created_at is None:
                continue
            task = tasks_by_id.get(str(run.get("task_id")))
            metrics = _run_metrics(run)
            tokens = metrics["tokens_total"] or _task_tokens(task)
            events.append(
                {
                    "created_at": created_at,
                    "tokens": tokens,
                    "duration_ms": metrics["duration_ms"],
                    "execution_agent": metrics["execution_agent"],
                    "status": str(run.get("status") or task.get("status") if task else run.get("status") or ""),
                }
            )
        if events:
            return events

    return [
        {
            "created_at": created_at,
            "tokens": _task_tokens(task),
            "duration_ms": 0,
            "execution_agent": str(task.get("agent") or "").strip() or None,
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


def _format_duration_ms(duration_ms: int) -> str:
    normalized = max(int(duration_ms), 0)
    if normalized >= 60_000:
        return f"{normalized / 60_000:.1f}m"
    if normalized >= 1_000:
        return f"{normalized / 1_000:.1f}s"
    return f"{normalized}ms"


def _build_chart_data(reference_at: datetime, events: list[dict]) -> list[dict]:
    window_start = reference_at - timedelta(hours=CHART_BUCKET_HOURS * (CHART_BUCKETS - 1))
    points = [
        {
            "time": (window_start + timedelta(hours=CHART_BUCKET_HOURS * index)).strftime("%H:%M"),
            "requests": 0,
            "tokens": 0,
            "duration_ms": 0,
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
        points[bucket_index]["duration_ms"] += int(event.get("duration_ms") or 0)

    return points


def _build_stats(
    reference_at: datetime,
    events: list[dict],
    agents: list[dict],
    workflows: list[dict],
    tasks: list[dict],
    workflow_runs: list[dict],
    sla_summary: dict,
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
    cost_summary = _build_cost_summary(workflow_runs, tasks)

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
        {
            "key": "sla_health",
            "title": "SLA 健康",
            "value": str(sla_summary.get("health_status") or "healthy"),
            "description": (
                f"成功率 {float(sla_summary.get('success_rate') or 0.0):.1f}% / "
                f"超时率 {float(sla_summary.get('timeout_rate') or 0.0):.1f}%"
            ),
            "trend_value": 0,
            "trend_positive": str(sla_summary.get("health_status") or "healthy") == "healthy",
        },
        {
            "key": "run_tokens",
            "title": "Run Token 成本",
            "value": cost_summary["total_tokens"],
            "description": f"{cost_summary['run_count']} 个 run 已累计计量",
            "trend_value": 0,
            "trend_positive": True,
        },
        {
            "key": "run_duration",
            "title": "平均执行耗时",
            "value": _format_duration_ms(cost_summary["avg_duration_ms"]),
            "description": f"总耗时 {_format_duration_ms(cost_summary['total_duration_ms'])}",
            "trend_value": 0,
            "trend_positive": True,
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


def _build_cost_summary(workflow_runs: list[dict], tasks: list[dict]) -> dict:
    run_count = len(workflow_runs)
    total_tokens = 0
    total_duration_ms = 0
    tasks_by_id = {str(task.get("id") or "").strip(): task for task in tasks}
    for run in workflow_runs:
        metrics = _run_metrics(run)
        task = tasks_by_id.get(str(run.get("task_id") or "").strip())
        total_tokens += metrics["tokens_total"] or _task_tokens(task)
        total_duration_ms += metrics["duration_ms"]

    avg_duration_ms = round(total_duration_ms / run_count) if run_count else 0
    return {
        "run_count": run_count,
        "total_tokens": total_tokens,
        "total_duration_ms": total_duration_ms,
        "avg_duration_ms": avg_duration_ms,
    }


def _build_tentacle_metrics(agents: list[dict], workflow_runs: list[dict], tasks: list[dict]) -> list[dict]:
    usage: dict[str, dict] = {}
    tasks_by_id = {str(task.get("id") or "").strip(): task for task in tasks}

    for agent in agents:
        agent_id = str(agent.get("id") or "").strip() or None
        name = str(agent.get("name") or "").strip() or (agent_id or "Unknown Agent")
        usage[name] = {
            "agent_id": agent_id,
            "name": name,
            "type": str(agent.get("type") or "default"),
            "calls": max(int(agent.get("tasks_total", 0)), 0),
            "success_calls": max(int(agent.get("tasks_completed", 0)), 0),
            "success_rate": float(agent.get("success_rate", 0.0) or 0.0),
            "tokens": max(int(agent.get("tokens_used", 0)), 0),
            "duration_ms": 0,
            "_from_agent_registry": True,
        }

    for run in workflow_runs:
        metrics = _run_metrics(run)
        execution_agent = metrics["execution_agent"]
        if not execution_agent:
            continue
        entry = usage.setdefault(
            execution_agent,
            {
                "agent_id": metrics["execution_agent_id"],
                "name": execution_agent,
                "type": "external",
                "calls": 0,
                "success_calls": 0,
                "success_rate": 0.0,
                "tokens": 0,
                "duration_ms": 0,
                "_from_agent_registry": False,
            },
        )
        entry["duration_ms"] += metrics["duration_ms"]
        task = tasks_by_id.get(str(run.get("task_id") or "").strip())
        if not bool(entry.get("_from_agent_registry")):
            entry["tokens"] += metrics["tokens_total"] or _task_tokens(task)
        if not bool(entry.get("_from_agent_registry")):
            entry["calls"] += 1
            if str(run.get("status") or "").strip().lower() == "completed":
                entry["success_calls"] += 1

    items = list(usage.values())
    for item in items:
        calls = max(int(item.get("calls") or 0), 0)
        success_calls = max(int(item.get("success_calls") or 0), 0)
        if calls > 0:
            item["success_rate"] = round((success_calls / calls) * 100, 1)
        else:
            item["success_rate"] = 0.0
        item.pop("_from_agent_registry", None)
    items.sort(key=lambda item: (-int(item["calls"]), item["name"]))
    return items


def _build_cost_distribution(workflow_runs: list[dict], tasks: list[dict]) -> list[dict]:
    usage: dict[str, dict] = {}
    total_tokens = 0
    tasks_by_id = {str(task.get("id") or "").strip(): task for task in tasks}
    for run in workflow_runs:
        metrics = _run_metrics(run)
        task = tasks_by_id.get(str(run.get("task_id") or "").strip())
        tokens = metrics["tokens_total"] or _task_tokens(task)
        label = metrics["execution_agent"] or str(run.get("workflow_name") or "Unknown").strip() or "Unknown"
        entry = usage.setdefault(
            label,
            {
                "label": label,
                "calls": 0,
                "tokens": 0,
                "duration_ms": 0,
                "share_percent": 0.0,
            },
        )
        entry["calls"] += 1
        entry["tokens"] += tokens
        entry["duration_ms"] += metrics["duration_ms"]
        total_tokens += tokens

    items = list(usage.values())
    for item in items:
        if total_tokens > 0:
            item["share_percent"] = round((item["tokens"] / total_tokens) * 100, 1)
        else:
            item["share_percent"] = 0.0
    items.sort(key=lambda item: (-int(item["tokens"]), -int(item["calls"]), item["label"]))
    return items[:8]


def _rate(value: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((value / total) * 100, 1)


def _status_from_min_rate(value: float, *, healthy_min: float, degraded_min: float) -> str:
    if value >= healthy_min:
        return "healthy"
    if value >= degraded_min:
        return "degraded"
    return "critical"


def _status_from_max_rate(value: float, *, healthy_max: float, degraded_max: float) -> str:
    if value <= healthy_max:
        return "healthy"
    if value <= degraded_max:
        return "degraded"
    return "critical"


def _merge_health_statuses(statuses: list[str]) -> str:
    if any(status == "critical" for status in statuses):
        return "critical"
    if any(status == "degraded" for status in statuses):
        return "degraded"
    return "healthy"


def _build_sla_summary(tasks: list[dict], workflow_runs: list[dict]) -> dict:
    reference_at = _reference_time(tasks, workflow_runs)
    window_start = reference_at - timedelta(hours=SLA_WINDOW_HOURS)
    runs_in_window = [
        run
        for run in workflow_runs
        if (_parse_datetime(run.get("created_at")) or reference_at) >= window_start
    ]
    total_runs = len(runs_in_window)
    completed_runs = 0
    failed_runs = 0
    timeout_runs = 0
    fallback_runs = 0
    delivery_failed_runs = 0

    for run in runs_in_window:
        status_value = str(run.get("status") or "").strip().lower()
        dispatch_context = run.get("dispatch_context")
        if not isinstance(dispatch_context, dict):
            dispatch_context = {}
        if status_value == "completed":
            completed_runs += 1
        if status_value == "failed":
            failed_runs += 1
        if str(dispatch_context.get("state") or "").strip().lower() == "execution_timeout":
            timeout_runs += 1
        fallback_history = dispatch_context.get("fallback_history")
        if isinstance(fallback_history, list) and fallback_history:
            fallback_runs += 1
        if str(dispatch_context.get("delivery_status") or "").strip().lower() == "failed":
            delivery_failed_runs += 1

    security_summary = get_security_report(window_hours=SLA_WINDOW_HOURS).get("summary", {})
    total_security_events = max(int(security_summary.get("total_events") or 0), 0)
    high_risk_events = max(int(security_summary.get("high_risk_events") or 0), 0)
    security_risk_rate = _rate(high_risk_events, total_security_events)
    success_rate = _rate(completed_runs, total_runs)
    failure_rate = _rate(failed_runs, total_runs)
    timeout_rate = _rate(timeout_runs, total_runs)
    fallback_rate = _rate(fallback_runs, total_runs)
    delivery_failure_rate = _rate(delivery_failed_runs, total_runs)

    statuses = [
        _status_from_min_rate(
            success_rate,
            healthy_min=HEALTHY_SUCCESS_RATE,
            degraded_min=DEGRADED_SUCCESS_RATE,
        ),
        _status_from_max_rate(
            failure_rate,
            healthy_max=HEALTHY_FAILURE_RATE,
            degraded_max=DEGRADED_FAILURE_RATE,
        ),
        _status_from_max_rate(
            timeout_rate,
            healthy_max=HEALTHY_TIMEOUT_RATE,
            degraded_max=DEGRADED_TIMEOUT_RATE,
        ),
        _status_from_max_rate(
            fallback_rate,
            healthy_max=HEALTHY_FALLBACK_RATE,
            degraded_max=DEGRADED_FALLBACK_RATE,
        ),
        _status_from_max_rate(
            delivery_failure_rate,
            healthy_max=HEALTHY_DELIVERY_FAILURE_RATE,
            degraded_max=DEGRADED_DELIVERY_FAILURE_RATE,
        ),
        _status_from_max_rate(
            security_risk_rate,
            healthy_max=HEALTHY_SECURITY_RISK_RATE,
            degraded_max=DEGRADED_SECURITY_RISK_RATE,
        ),
    ]
    return {
        "window_hours": SLA_WINDOW_HOURS,
        "total_runs": total_runs,
        "success_rate": success_rate,
        "failure_rate": failure_rate,
        "timeout_rate": timeout_rate,
        "fallback_rate": fallback_rate,
        "delivery_failure_rate": delivery_failure_rate,
        "security_risk_rate": security_risk_rate,
        "health_status": _merge_health_statuses(statuses),
    }


def _build_health_signals(sla_summary: dict) -> list[dict]:
    success_rate = float(sla_summary.get("success_rate") or 0.0)
    failure_rate = float(sla_summary.get("failure_rate") or 0.0)
    timeout_rate = float(sla_summary.get("timeout_rate") or 0.0)
    fallback_rate = float(sla_summary.get("fallback_rate") or 0.0)
    delivery_failure_rate = float(sla_summary.get("delivery_failure_rate") or 0.0)
    security_risk_rate = float(sla_summary.get("security_risk_rate") or 0.0)
    return [
        {
            "key": "success_rate",
            "label": "执行成功率",
            "status": _status_from_min_rate(
                success_rate,
                healthy_min=HEALTHY_SUCCESS_RATE,
                degraded_min=DEGRADED_SUCCESS_RATE,
            ),
            "value": success_rate,
            "unit": "%",
            "summary": f"成功率 {success_rate:.1f}% ，目标不低于 {HEALTHY_SUCCESS_RATE:.0f}%",
            "threshold": {
                "metric": "success_rate",
                "healthy_gte": HEALTHY_SUCCESS_RATE,
                "degraded_gte": DEGRADED_SUCCESS_RATE,
            },
        },
        {
            "key": "failure_rate",
            "label": "失败率",
            "status": _status_from_max_rate(
                failure_rate,
                healthy_max=HEALTHY_FAILURE_RATE,
                degraded_max=DEGRADED_FAILURE_RATE,
            ),
            "value": failure_rate,
            "unit": "%",
            "summary": f"失败率 {failure_rate:.1f}% ，高于 {DEGRADED_FAILURE_RATE:.0f}% 进入 critical",
            "threshold": {
                "metric": "failure_rate",
                "healthy_lte": HEALTHY_FAILURE_RATE,
                "degraded_lte": DEGRADED_FAILURE_RATE,
            },
        },
        {
            "key": "timeout_rate",
            "label": "超时率",
            "status": _status_from_max_rate(
                timeout_rate,
                healthy_max=HEALTHY_TIMEOUT_RATE,
                degraded_max=DEGRADED_TIMEOUT_RATE,
            ),
            "value": timeout_rate,
            "unit": "%",
            "summary": f"超时率 {timeout_rate:.1f}% ，反映执行链路是否堵塞",
            "threshold": {
                "metric": "timeout_rate",
                "healthy_lte": HEALTHY_TIMEOUT_RATE,
                "degraded_lte": DEGRADED_TIMEOUT_RATE,
            },
        },
        {
            "key": "fallback_rate",
            "label": "回退率",
            "status": _status_from_max_rate(
                fallback_rate,
                healthy_max=HEALTHY_FALLBACK_RATE,
                degraded_max=DEGRADED_FALLBACK_RATE,
            ),
            "value": fallback_rate,
            "unit": "%",
            "summary": f"回退率 {fallback_rate:.1f}% ，反映外接触手稳定性",
            "threshold": {
                "metric": "fallback_rate",
                "healthy_lte": HEALTHY_FALLBACK_RATE,
                "degraded_lte": DEGRADED_FALLBACK_RATE,
            },
        },
        {
            "key": "delivery_failure_rate",
            "label": "回传失败率",
            "status": _status_from_max_rate(
                delivery_failure_rate,
                healthy_max=HEALTHY_DELIVERY_FAILURE_RATE,
                degraded_max=DEGRADED_DELIVERY_FAILURE_RATE,
            ),
            "value": delivery_failure_rate,
            "unit": "%",
            "summary": f"回传失败率 {delivery_failure_rate:.1f}% ，反映 Adapter/Outbound 健康度",
            "threshold": {
                "metric": "delivery_failure_rate",
                "healthy_lte": HEALTHY_DELIVERY_FAILURE_RATE,
                "degraded_lte": DEGRADED_DELIVERY_FAILURE_RATE,
            },
        },
        {
            "key": "security_risk_rate",
            "label": "安全高风险率",
            "status": _status_from_max_rate(
                security_risk_rate,
                healthy_max=HEALTHY_SECURITY_RISK_RATE,
                degraded_max=DEGRADED_SECURITY_RISK_RATE,
            ),
            "value": security_risk_rate,
            "unit": "%",
            "summary": f"安全高风险率 {security_risk_rate:.1f}% ，反映注入/拦截压力",
            "threshold": {
                "metric": "security_risk_rate",
                "healthy_lte": HEALTHY_SECURITY_RISK_RATE,
                "degraded_lte": DEGRADED_SECURITY_RISK_RATE,
            },
        },
    ]


def _build_prepared_alerts(sla_summary: dict, health_signals: list[dict]) -> list[dict]:
    alerts: list[dict] = []
    for signal in health_signals:
        status_value = str(signal.get("status") or "").strip().lower()
        if status_value not in {"degraded", "critical"}:
            continue
        key = str(signal.get("key") or "").strip() or "signal"
        source = "security_gateway" if key == "security_risk_rate" else "workflow_runtime"
        href = (
            "/security?source=security"
            if key == "security_risk_rate"
            else f"/security?source={source}"
        )
        alerts.append(
            {
                "key": key,
                "severity": "critical" if status_value == "critical" else "warning",
                "title": f"{signal.get('label')}异常",
                "detail": str(signal.get("summary") or "").strip() or f"{key} exceeded threshold",
                "source": source,
                "href": href,
            }
        )
    if not alerts and str(sla_summary.get("health_status") or "") == "healthy":
        return []
    return alerts[:6]


def _build_failure_breakdown(tasks: list[dict], workflow_runs: list[dict]) -> list[dict]:
    run_by_id = {
        str(run.get("id") or "").strip(): run
        for run in workflow_runs
        if str(run.get("id") or "").strip()
    }
    counts = {stage: 0 for stage in FAILURE_BREAKDOWN_STAGE_ORDER}

    for task in tasks:
        run_id = str(task.get("workflow_run_id") or "").strip()
        enriched_task = _project_task(task, run=run_by_id.get(run_id))
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


def _build_brain_breakdown(tasks: list[dict], workflow_runs: list[dict]) -> list[dict]:
    run_by_id = {
        str(run.get("id") or "").strip(): run
        for run in workflow_runs
        if str(run.get("id") or "").strip()
    }

    chat_count = 0
    clarify_count = 0
    structured_result_count = 0
    multi_step_count = 0

    for task in tasks:
        run_id = str(task.get("workflow_run_id") or "").strip()
        enriched_task = _project_task(task, run=run_by_id.get(run_id))
        route_decision = enriched_task.get("route_decision") or {}
        manager_packet = enriched_task.get("manager_packet") or {}

        interaction_mode = str(
            route_decision.get("interaction_mode") or route_decision.get("interactionMode") or ""
        ).strip()
        response_contract = str(manager_packet.get("response_contract") or "").strip()
        delivery_mode = str(manager_packet.get("delivery_mode") or "").strip()
        task_shape = str(manager_packet.get("task_shape") or "").strip()

        if interaction_mode == "chat":
            chat_count += 1
        if response_contract == "clarify_first":
            clarify_count += 1
        if delivery_mode == "structured_result":
            structured_result_count += 1
        if task_shape == "multi_step":
            multi_step_count += 1

    return [
        {
            "key": "chat",
            "label": "对话接待",
            "count": chat_count,
            "hint": "主脑判定为 chat 模式",
        },
        {
            "key": "clarify",
            "label": "先澄清",
            "count": clarify_count,
            "hint": "项目经理要求先澄清再执行",
        },
        {
            "key": "structured_result",
            "label": "结构化交付",
            "count": structured_result_count,
            "hint": "交付模式为 structured_result",
        },
        {
            "key": "multi_step",
            "label": "多步编排",
            "count": multi_step_count,
            "hint": "任务形态为 multi_step",
        },
    ]


def _build_manager_queue(tasks: list[dict], workflow_runs: list[dict]) -> list[dict]:
    run_by_id = {
        str(run.get("id") or "").strip(): run
        for run in workflow_runs
        if str(run.get("id") or "").strip()
    }
    items: list[dict] = []

    for task in tasks:
        if str(task.get("status") or "").strip() not in {"pending", "running"}:
            continue

        run_id = str(task.get("workflow_run_id") or "").strip()
        enriched_task = _project_task(task, run=run_by_id.get(run_id))
        route_decision = enriched_task.get("route_decision") or {}
        manager_packet = enriched_task.get("manager_packet") or {}

        interaction_mode = str(
            route_decision.get("interaction_mode") or route_decision.get("interactionMode") or ""
        ).strip()
        response_contract = str(manager_packet.get("response_contract") or "").strip()
        task_shape = str(manager_packet.get("task_shape") or "").strip()

        should_include = (
            response_contract == "clarify_first"
            or interaction_mode == "chat"
            or task_shape == "multi_step"
        )
        if not should_include:
            continue

        items.append(
            {
                "task_id": str(enriched_task.get("id") or ""),
                "title": str(enriched_task.get("title") or ""),
                "status": str(enriched_task.get("status") or ""),
                "manager_action": str(manager_packet.get("manager_action") or "").strip() or None,
                "next_owner": str(manager_packet.get("next_owner") or "").strip() or None,
                "response_contract": response_contract or None,
                "delivery_mode": str(manager_packet.get("delivery_mode") or "").strip() or None,
                "task_shape": task_shape or None,
                "clarify_question": str(manager_packet.get("clarify_question") or "").strip() or None,
                "current_stage": str(enriched_task.get("current_stage") or "").strip() or None,
                "session_state": str(manager_packet.get("session_state") or "").strip() or None,
                "state_label": str(manager_packet.get("state_label") or "").strip() or None,
            }
        )

    items.sort(
        key=lambda item: (
            0 if item.get("response_contract") == "clarify_first" else 1,
            0 if item.get("status") == "running" else 1,
            str(item.get("task_id") or ""),
        )
    )
    return items[:6]


def _build_reply_queue(tasks: list[dict], workflow_runs: list[dict]) -> list[dict]:
    run_by_id = {
        str(run.get("id") or "").strip(): run
        for run in workflow_runs
        if str(run.get("id") or "").strip()
    }
    latest_by_session: dict[str, dict] = {}

    def sort_key(item: dict) -> tuple[int, str]:
        return (
            0 if item.get("status") == "running" else 1,
            str(item.get("task_id") or ""),
        )

    def infer_channel(enriched_task: dict, user_key: str, session_id: str) -> str | None:
        channel = str(enriched_task.get("channel") or "").strip()
        if channel:
            return channel
        if ":" in session_id:
            return session_id.split(":", maxsplit=1)[0].strip() or None
        if ":" in user_key:
            return user_key.split(":", maxsplit=1)[0].strip() or None
        return None

    for task in tasks:
        if str(task.get("status") or "").strip() not in {"pending", "running"}:
            continue

        run_id = str(task.get("workflow_run_id") or "").strip()
        enriched_task = _project_task(task, run=run_by_id.get(run_id))
        manager_packet = enriched_task.get("manager_packet") or {}
        response_contract = str(manager_packet.get("response_contract") or "").strip()
        clarify_question = str(manager_packet.get("clarify_question") or "").strip()
        if response_contract != "clarify_first" or not clarify_question:
            continue

        session_id = str(enriched_task.get("session_id") or "").strip()
        user_key = str(enriched_task.get("user_key") or "").strip()
        channel = infer_channel(enriched_task, user_key, session_id)
        user_label = user_key.split(":", maxsplit=1)[1].strip() if ":" in user_key else user_key or None
        grouping_key = session_id or user_key or str(enriched_task.get("id") or "")
        candidate = {
            "task_id": str(enriched_task.get("id") or ""),
            "title": str(enriched_task.get("title") or ""),
            "channel": channel,
            "user_label": user_label,
            "user_key": user_key or None,
            "session_id": session_id or None,
            "status": str(enriched_task.get("status") or ""),
            "clarify_question": clarify_question,
            "current_stage": str(enriched_task.get("current_stage") or "").strip() or None,
            "next_owner": str(manager_packet.get("next_owner") or "").strip() or None,
            "reception_mode": str(manager_packet.get("reception_mode") or "").strip() or None,
            "workflow_mode": str(manager_packet.get("workflow_mode") or "").strip() or None,
            "response_contract": response_contract or None,
            "confirmation_status": str(enriched_task.get("confirmation_status") or "").strip() or None,
            "session_state": str(manager_packet.get("session_state") or "").strip() or None,
            "state_label": str(manager_packet.get("state_label") or "").strip() or None,
        }

        existing = latest_by_session.get(grouping_key)
        if existing is None or sort_key(candidate) < sort_key(existing):
            latest_by_session[grouping_key] = candidate

    items = list(latest_by_session.values())
    items.sort(key=sort_key)
    return items[:6]


def _merge_runtime_prepared_alerts(
    prepared_alerts: list[dict],
    runtime_alerts: list[dict],
) -> list[dict]:
    merged = [store.clone(item) for item in prepared_alerts]
    seen_keys = {
        str(item.get("key") or "").strip()
        for item in merged
        if str(item.get("key") or "").strip()
    }

    for alert in runtime_alerts:
        key = str(alert.get("key") or "").strip()
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        merged.append(
            {
                "key": key,
                "severity": (
                    "critical"
                    if str(alert.get("severity") or "").strip().lower() == "critical"
                    else "warning"
                ),
                "title": str(alert.get("title") or key).strip() or key,
                "detail": str(alert.get("detail") or "").strip()
                or str(alert.get("title") or key).strip()
                or key,
                "source": str(alert.get("source") or "workflow_runtime").strip()
                or "workflow_runtime",
                "href": str(alert.get("href") or "").strip() or None,
            }
        )
    return merged


def get_stats(*, scope: dict[str, str] | None = None) -> dict:
    agents = _load_agents()
    tasks = _filter_items_by_scope(_load_tasks(), scope)
    workflows = _load_workflows()
    workflow_runs = _filter_items_by_scope(_load_workflow_runs(), scope)
    reference_at = _reference_time(tasks, workflow_runs)
    events = _build_request_events(reference_at, tasks, workflow_runs)
    cost_summary = _build_cost_summary(workflow_runs, tasks)
    sla_summary = _build_sla_summary(tasks, workflow_runs)
    health_signals = _build_health_signals(sla_summary)
    runtime = workflow_runtime_snapshot_service.build_snapshot(
        runs=workflow_runs,
        scope=scope,
        persistence=persistence_service,
    )
    prepared_alerts = _merge_runtime_prepared_alerts(
        _build_prepared_alerts(sla_summary, health_signals),
        list(runtime.get("recent_alerts") or []),
    )
    tentacle_metrics = _build_tentacle_metrics(agents, workflow_runs, tasks)
    cost_distribution = _build_cost_distribution(workflow_runs, tasks)
    return {
        "stats": _build_stats(reference_at, events, agents, workflows, tasks, workflow_runs, sla_summary),
        "chart_data": _build_chart_data(reference_at, events),
        "agent_statuses": _build_agent_statuses(agents),
        "cost_summary": cost_summary,
        "sla_summary": sla_summary,
        "health_signals": health_signals,
        "prepared_alerts": prepared_alerts,
        "tentacle_metrics": tentacle_metrics,
        "cost_distribution": cost_distribution,
        "failure_breakdown": _build_failure_breakdown(tasks, workflow_runs),
        "brain_breakdown": _build_brain_breakdown(tasks, workflow_runs),
        "manager_queue": _build_manager_queue(tasks, workflow_runs),
        "reply_queue": _build_reply_queue(tasks, workflow_runs),
        "realtime_logs": _load_realtime_logs(scope=scope),
        "runtime": runtime,
    }


def _prometheus_label(value: object) -> str:
    text = str(value)
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _prometheus_number(value: object) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "0"
    if number.is_integer():
        return str(int(number))
    return format(number, "g")


def export_prometheus_metrics(*, scope: dict[str, str] | None = None) -> str:
    stats = get_stats(scope=scope)
    runtime = stats.get("runtime") if isinstance(stats.get("runtime"), dict) else {}
    sla_summary = stats.get("sla_summary") if isinstance(stats.get("sla_summary"), dict) else {}
    health_signals = (
        stats.get("health_signals") if isinstance(stats.get("health_signals"), list) else []
    )
    prepared_alerts = _build_prepared_alerts(sla_summary, health_signals)
    runtime_alerts = (
        runtime.get("recent_alerts") if isinstance(runtime.get("recent_alerts"), list) else []
    )
    health_status = str(sla_summary.get("health_status") or "healthy").strip().lower()
    health_state_value = {"healthy": 2, "degraded": 1, "critical": 0}.get(health_status, 0)

    lines = [
        "# HELP workbot_runtime_queue_depth_total Total depth across runtime queues.",
        "# TYPE workbot_runtime_queue_depth_total gauge",
        f"workbot_runtime_queue_depth_total {_prometheus_number(runtime.get('total_queue_depth', 0))}",
        "# HELP workbot_runtime_queue_depth Queue depth per queue.",
        "# TYPE workbot_runtime_queue_depth gauge",
    ]

    for queue in runtime.get("queues") or []:
        queue_key = str(queue.get("key") or "unknown").strip() or "unknown"
        lines.append(
            "workbot_runtime_queue_depth"
            + f"{{queue={_prometheus_label(queue_key)}}} {_prometheus_number(queue.get('depth', 0))}"
        )

    lines.extend(
        [
            "# HELP workbot_runtime_stale_claims_total Total stale queue claims.",
            "# TYPE workbot_runtime_stale_claims_total gauge",
            f"workbot_runtime_stale_claims_total {_prometheus_number(runtime.get('stale_claims', 0))}",
            "# HELP workbot_runtime_dead_letters_total Total dead-letter runs in runtime window.",
            "# TYPE workbot_runtime_dead_letters_total gauge",
            f"workbot_runtime_dead_letters_total {_prometheus_number(runtime.get('dead_letters', 0))}",
            "# HELP workbot_sla_success_rate SLA success rate in percent.",
            "# TYPE workbot_sla_success_rate gauge",
            f"workbot_sla_success_rate {_prometheus_number(sla_summary.get('success_rate', 0.0))}",
            "# HELP workbot_sla_failure_rate SLA failure rate in percent.",
            "# TYPE workbot_sla_failure_rate gauge",
            f"workbot_sla_failure_rate {_prometheus_number(sla_summary.get('failure_rate', 0.0))}",
            "# HELP workbot_alerts_prepared_total Total prepared alerts from policy thresholds.",
            "# TYPE workbot_alerts_prepared_total gauge",
            f"workbot_alerts_prepared_total {_prometheus_number(len(prepared_alerts))}",
            "# HELP workbot_alerts_runtime_total Total runtime alerts from queue/runtime snapshot.",
            "# TYPE workbot_alerts_runtime_total gauge",
            f"workbot_alerts_runtime_total {_prometheus_number(len(runtime_alerts))}",
            "# HELP workbot_sla_health_state SLA health state (healthy=2,degraded=1,critical=0).",
            "# TYPE workbot_sla_health_state gauge",
            f"workbot_sla_health_state {_prometheus_number(health_state_value)}",
        ]
    )
    return "\n".join(lines) + "\n"


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


def _audit_log_layer(log: dict) -> str | None:
    metadata = log.get("metadata")
    if not isinstance(metadata, dict):
        return None
    trace = metadata.get("trace")
    if isinstance(trace, dict):
        layer = str(trace.get("layer") or "").strip().lower()
        if layer:
            return layer
    layer = str(metadata.get("layer") or "").strip().lower()
    return layer or None


def _filter_audit_logs(
    *,
    search: str | None = None,
    status_filter: str | None = None,
    layer: str | None = None,
    user: str | None = None,
    resource: str | None = None,
    scope: dict[str, str] | None = None,
) -> list[dict]:
    items = _filter_items_by_scope(_load_audit_logs(), scope)

    search_keyword = _normalize_keyword(search)
    status_keyword = _normalize_keyword(status_filter)
    layer_keyword = _normalize_keyword(layer)
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

    if layer_keyword is not None:
        items = [log for log in items if _audit_log_layer(log) == layer_keyword]

    if user_keyword is not None:
        items = [log for log in items if _matches_keyword(log, ("user",), user_keyword)]

    if resource_keyword is not None:
        items = [log for log in items if _matches_keyword(log, ("resource",), resource_keyword)]

    return items


def get_audit_logs(
    *,
    search: str | None = None,
    status_filter: str | None = None,
    layer: str | None = None,
    user: str | None = None,
    resource: str | None = None,
    limit: int = DEFAULT_AUDIT_LOG_LIMIT,
    offset: int = 0,
    scope: dict[str, str] | None = None,
) -> dict:
    items = _filter_audit_logs(
        search=search,
        status_filter=status_filter,
        layer=layer,
        user=user,
        resource=resource,
        scope=scope,
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
    layer: str | None = None,
    user: str | None = None,
    resource: str | None = None,
    scope: dict[str, str] | None = None,
) -> str:
    items = _filter_audit_logs(
        search=search,
        status_filter=status_filter,
        layer=layer,
        user=user,
        resource=resource,
        scope=scope,
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
