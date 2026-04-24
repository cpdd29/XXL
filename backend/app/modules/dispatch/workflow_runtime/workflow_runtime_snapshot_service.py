from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.platform.persistence.persistence_service import persistence_service
from app.platform.persistence.runtime_store import store
from app.modules.organization.application.tenancy_service import attach_scope, matches_scope


DEFAULT_ALERT_LIMIT = 6
QUEUE_DEFINITIONS = (
    {
        "key": "dispatch",
        "label": "调度队列",
        "owner_field": "dispatcher_id",
        "lease_field": "dispatch_lease_expires_at",
    },
    {
        "key": "workflow_execution",
        "label": "工作流执行队列",
        "owner_field": "worker_id",
        "lease_field": "lease_expires_at",
    },
    {
        "key": "agent_execution",
        "label": "Agent 执行队列",
        "owner_field": "worker_id",
        "lease_field": "lease_expires_at",
    },
)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _safe_int(value: object, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _job_protocol(job: dict[str, Any]) -> dict[str, Any]:
    protocol = job.get("protocol")
    return protocol if isinstance(protocol, dict) else {}


def _run_dispatch_context(run: dict[str, Any]) -> dict[str, Any]:
    dispatch_context = run.get("dispatch_context")
    return dispatch_context if isinstance(dispatch_context, dict) else {}


def _run_protocol(run: dict[str, Any]) -> dict[str, Any]:
    protocol = _run_dispatch_context(run).get("protocol")
    return protocol if isinstance(protocol, dict) else {}


def _run_monitor_state(run: dict[str, Any], *, now: datetime) -> str:
    monitor = run.get("monitor")
    if isinstance(monitor, dict):
        state = str(
            monitor.get("monitor_state")
            or monitor.get("monitorState")
            or ""
        ).strip()
        if state:
            return state

    status_value = str(run.get("status") or "").strip().lower()
    next_dispatch_at = _parse_datetime(str(run.get("next_dispatch_at") or ""))
    dispatch_failure_count = max(_safe_int(run.get("dispatch_failure_count"), default=0), 0)
    dispatcher_id = str(run.get("dispatcher_id") or "").strip()
    lease_expires_at = _parse_datetime(str(run.get("dispatch_lease_expires_at") or ""))

    if status_value in {"completed", "cancelled", "failed"}:
        return status_value
    if dispatcher_id and lease_expires_at is not None and lease_expires_at <= now:
        return "claimed_stale"
    if dispatcher_id and lease_expires_at is not None and lease_expires_at > now:
        return "claimed"
    if next_dispatch_at is not None and dispatch_failure_count > 0:
        return "retry_waiting"
    if next_dispatch_at is not None and next_dispatch_at > now:
        return "scheduled"
    if next_dispatch_at is not None and next_dispatch_at <= now:
        return "overdue"
    if status_value == "running":
        return "running"
    if status_value == "pending":
        return "queued"
    return status_value or "queued"


def _run_is_retry_waiting(run: dict[str, Any], *, now: datetime) -> bool:
    return _run_monitor_state(run, now=now) == "retry_waiting"


def _run_is_dead_lettered(run: dict[str, Any]) -> bool:
    protocol = _run_protocol(run)
    if bool(protocol.get("dead_letter")):
        return True
    dispatch_state = str(_run_dispatch_context(run).get("state") or "").strip().lower()
    return dispatch_state == "dead_letter"


def _run_claim_is_stale(run: dict[str, Any], *, now: datetime) -> bool:
    dispatcher_id = str(run.get("dispatcher_id") or "").strip()
    lease_expires_at = _parse_datetime(str(run.get("dispatch_lease_expires_at") or ""))
    return bool(dispatcher_id and lease_expires_at is not None and lease_expires_at <= now)


def _run_timestamp(run: dict[str, Any], *fields: str) -> str | None:
    for field in fields:
        value = str(run.get(field) or "").strip()
        if value:
            return value
    return None


def _alert_href(run_id: str | None) -> str:
    return "/tasks"


class WorkflowRuntimeSnapshotService:
    def __init__(self, *, runtime_store: Any = None) -> None:
        self._runtime_store = runtime_store or store
        self._persistence = persistence_service

    def build_snapshot(
        self,
        *,
        runs: list[dict[str, Any]] | None = None,
        workflow_id: str | None = None,
        task_id: str | None = None,
        scope: dict[str, str] | None = None,
        now: datetime | None = None,
        alert_limit: int = DEFAULT_ALERT_LIMIT,
        persistence: Any | None = None,
    ) -> dict[str, Any]:
        resolved_now = now or datetime.now(UTC)
        persistence_impl = persistence or self._persistence
        resolved_runs = self._resolve_runs(
            runs=runs,
            workflow_id=workflow_id,
            task_id=task_id,
            scope=scope,
            persistence=persistence_impl,
        )
        run_by_id = {
            str(run.get("id") or "").strip(): store.clone(run)
            for run in resolved_runs
            if str(run.get("id") or "").strip()
        }
        run_ids = set(run_by_id)
        include_all_jobs = workflow_id is None and task_id is None and scope is None

        dispatch_jobs = self._filter_jobs(
            self._load_job_list(persistence_impl, "list_workflow_dispatch_jobs"),
            run_ids=run_ids,
            include_all=include_all_jobs,
        )
        workflow_execution_jobs = self._filter_jobs(
            self._load_job_list(persistence_impl, "list_workflow_execution_jobs"),
            run_ids=run_ids,
            include_all=include_all_jobs,
        )
        agent_execution_jobs = self._filter_jobs(
            self._load_job_list(persistence_impl, "list_agent_execution_jobs"),
            run_ids=run_ids,
            include_all=include_all_jobs,
            workflow_id=workflow_id,
        )

        queues = [
            self._summarize_queue(
                dispatch_jobs,
                queue_key="dispatch",
                queue_label="调度队列",
                owner_field="dispatcher_id",
                lease_field="dispatch_lease_expires_at",
                now=resolved_now,
            ),
            self._summarize_queue(
                workflow_execution_jobs,
                queue_key="workflow_execution",
                queue_label="工作流执行队列",
                owner_field="worker_id",
                lease_field="lease_expires_at",
                now=resolved_now,
            ),
            self._summarize_queue(
                agent_execution_jobs,
                queue_key="agent_execution",
                queue_label="Agent 执行队列",
                owner_field="worker_id",
                lease_field="lease_expires_at",
                now=resolved_now,
            ),
        ]

        retry_run_ids = {
            str(run.get("id") or "").strip()
            for run in resolved_runs
            if str(run.get("id") or "").strip() and _run_is_retry_waiting(run, now=resolved_now)
        }
        retry_run_ids.update(
            self._retry_job_run_ids(dispatch_jobs, workflow_execution_jobs, agent_execution_jobs)
        )
        dead_letter_run_ids = {
            str(run.get("id") or "").strip()
            for run in resolved_runs
            if str(run.get("id") or "").strip() and _run_is_dead_lettered(run)
        }
        dead_letter_run_ids.update(
            self._dead_letter_job_run_ids(dispatch_jobs, workflow_execution_jobs, agent_execution_jobs)
        )

        recent_alerts = self._build_recent_alerts(
            runs=resolved_runs,
            run_by_id=run_by_id,
            dispatch_jobs=dispatch_jobs,
            workflow_execution_jobs=workflow_execution_jobs,
            agent_execution_jobs=agent_execution_jobs,
            now=resolved_now,
            limit=max(1, int(alert_limit or DEFAULT_ALERT_LIMIT)),
        )

        return {
            "timestamp": resolved_now.isoformat(),
            "total_queue_depth": sum(int(queue["depth"]) for queue in queues),
            "dispatch_queue_depth": int(queues[0]["depth"]),
            "workflow_execution_queue_depth": int(queues[1]["depth"]),
            "agent_execution_queue_depth": int(queues[2]["depth"]),
            "active_dispatch_leases": int(queues[0]["active_leases"]),
            "active_workflow_execution_leases": int(queues[1]["active_leases"]),
            "active_agent_execution_leases": int(queues[2]["active_leases"]),
            "stale_claims": sum(int(queue["stale_claims"]) for queue in queues),
            "retry_scheduled": len({run_id for run_id in retry_run_ids if run_id}),
            "dead_letters": len({run_id for run_id in dead_letter_run_ids if run_id}),
            "queues": queues,
            "recent_alerts": recent_alerts,
        }

    def _resolve_runs(
        self,
        *,
        runs: list[dict[str, Any]] | None,
        workflow_id: str | None,
        task_id: str | None,
        scope: dict[str, str] | None,
        persistence: Any,
    ) -> list[dict[str, Any]]:
        if runs is None:
            items = self._load_runs(persistence)
        else:
            items = [attach_scope(store.clone(item)) for item in runs]

        filtered: list[dict[str, Any]] = []
        for item in items:
            if workflow_id is not None and str(item.get("workflow_id") or "").strip() != workflow_id:
                continue
            if task_id is not None and str(item.get("task_id") or "").strip() != task_id:
                continue
            if scope is not None and not matches_scope(item, scope):
                continue
            filtered.append(item)
        return filtered

    def _load_runs(self, persistence: Any) -> list[dict[str, Any]]:
        list_runs = getattr(persistence, "list_workflow_runs", None)
        if callable(list_runs):
            items = list_runs()
            if items is not None:
                return [attach_scope(item) for item in items]
        if getattr(persistence, "enabled", False):
            return []
        return [attach_scope(item) for item in store.clone(self._runtime_store.workflow_runs)]

    def _load_job_list(self, persistence: Any, method_name: str) -> list[dict[str, Any]]:
        method = getattr(persistence, method_name, None)
        if callable(method):
            items = method()
            if items is not None:
                return [store.clone(item) for item in items]
        if getattr(persistence, "enabled", False):
            return []
        return []

    @staticmethod
    def _filter_jobs(
        jobs: list[dict[str, Any]],
        *,
        run_ids: set[str],
        include_all: bool,
        workflow_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if include_all:
            return [store.clone(item) for item in jobs]

        filtered: list[dict[str, Any]] = []
        for item in jobs:
            run_id = str(item.get("run_id") or "").strip()
            job_workflow_id = str(item.get("workflow_id") or "").strip()
            if run_id and run_id in run_ids:
                filtered.append(store.clone(item))
                continue
            if workflow_id and job_workflow_id == workflow_id:
                filtered.append(store.clone(item))
        return filtered

    @staticmethod
    def _summarize_queue(
        jobs: list[dict[str, Any]],
        *,
        queue_key: str,
        queue_label: str,
        owner_field: str,
        lease_field: str,
        now: datetime,
    ) -> dict[str, Any]:
        summary = {
            "key": queue_key,
            "label": queue_label,
            "depth": len(jobs),
            "ready": 0,
            "delayed": 0,
            "active_leases": 0,
            "stale_claims": 0,
            "retry_scheduled": 0,
            "dead_letters": 0,
        }

        for job in jobs:
            available_at = _parse_datetime(str(job.get("available_at") or ""))
            owner = str(job.get(owner_field) or "").strip()
            lease_expires_at = _parse_datetime(str(job.get(lease_field) or ""))
            protocol = _job_protocol(job)
            attempt = max(_safe_int(protocol.get("attempt") or job.get("attempt"), default=1), 1)
            dead_letter = bool(protocol.get("dead_letter") or job.get("dead_letter"))

            if available_at is not None and available_at > now:
                summary["delayed"] += 1
            else:
                summary["ready"] += 1

            if owner:
                if lease_expires_at is not None and lease_expires_at > now:
                    summary["active_leases"] += 1
                else:
                    summary["stale_claims"] += 1

            if attempt > 1 and not dead_letter:
                summary["retry_scheduled"] += 1
            if dead_letter:
                summary["dead_letters"] += 1

        return summary

    @staticmethod
    def _retry_job_run_ids(*job_groups: list[dict[str, Any]]) -> set[str]:
        run_ids: set[str] = set()
        for jobs in job_groups:
            for job in jobs:
                protocol = _job_protocol(job)
                run_id = str(job.get("run_id") or "").strip()
                attempt = max(_safe_int(protocol.get("attempt") or job.get("attempt"), default=1), 1)
                if run_id and attempt > 1 and not bool(protocol.get("dead_letter") or job.get("dead_letter")):
                    run_ids.add(run_id)
        return run_ids

    @staticmethod
    def _dead_letter_job_run_ids(*job_groups: list[dict[str, Any]]) -> set[str]:
        run_ids: set[str] = set()
        for jobs in job_groups:
            for job in jobs:
                protocol = _job_protocol(job)
                run_id = str(job.get("run_id") or "").strip()
                if run_id and bool(protocol.get("dead_letter") or job.get("dead_letter")):
                    run_ids.add(run_id)
        return run_ids

    def _build_recent_alerts(
        self,
        *,
        runs: list[dict[str, Any]],
        run_by_id: dict[str, dict[str, Any]],
        dispatch_jobs: list[dict[str, Any]],
        workflow_execution_jobs: list[dict[str, Any]],
        agent_execution_jobs: list[dict[str, Any]],
        now: datetime,
        limit: int,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        items.extend(self._build_retry_run_alerts(runs, now=now))
        items.extend(self._build_dead_letter_run_alerts(runs))
        items.extend(
            self._build_stale_job_alerts(
                dispatch_jobs,
                run_by_id=run_by_id,
                queue_key="dispatch",
                queue_label="调度队列",
                owner_field="dispatcher_id",
                lease_field="dispatch_lease_expires_at",
                now=now,
            )
        )
        items.extend(
            self._build_stale_job_alerts(
                workflow_execution_jobs,
                run_by_id=run_by_id,
                queue_key="workflow_execution",
                queue_label="工作流执行队列",
                owner_field="worker_id",
                lease_field="lease_expires_at",
                now=now,
            )
        )
        items.extend(
            self._build_stale_job_alerts(
                agent_execution_jobs,
                run_by_id=run_by_id,
                queue_key="agent_execution",
                queue_label="Agent 执行队列",
                owner_field="worker_id",
                lease_field="lease_expires_at",
                now=now,
            )
        )
        if not dispatch_jobs:
            items.extend(self._build_stale_run_alerts(runs, now=now))
        items.extend(
            self._build_retry_job_alerts(
                dispatch_jobs,
                run_by_id=run_by_id,
                queue_key="dispatch",
                queue_label="调度队列",
            )
        )
        items.extend(
            self._build_retry_job_alerts(
                workflow_execution_jobs,
                run_by_id=run_by_id,
                queue_key="workflow_execution",
                queue_label="工作流执行队列",
            )
        )
        items.extend(
            self._build_retry_job_alerts(
                agent_execution_jobs,
                run_by_id=run_by_id,
                queue_key="agent_execution",
                queue_label="Agent 执行队列",
            )
        )

        ordered = sorted(
            items,
            key=lambda item: item["_sort_at"],
            reverse=True,
        )
        deduped: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        for item in ordered:
            key = str(item.get("key") or "").strip()
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            deduped.append({k: v for k, v in item.items() if k != "_sort_at"})
            if len(deduped) >= limit:
                break
        return deduped

    @staticmethod
    def _build_retry_run_alerts(runs: list[dict[str, Any]], *, now: datetime) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for run in runs:
            if not _run_is_retry_waiting(run, now=now):
                continue
            run_id = str(run.get("id") or "").strip()
            if not run_id:
                continue
            protocol = _run_protocol(run)
            attempt = max(
                _safe_int(protocol.get("attempt") or run.get("dispatch_failure_count"), default=1),
                1,
            )
            next_dispatch_at = str(run.get("next_dispatch_at") or "").strip() or None
            last_error = (
                str(run.get("last_dispatch_error") or protocol.get("last_error") or "").strip() or None
            )
            detail = f"运行 {run_id} 正在等待第 {attempt} 次重试"
            if next_dispatch_at:
                detail += f"，下次拉起时间 {next_dispatch_at}"
            if last_error:
                detail += f"。最近错误：{last_error}"
            updated_at = _run_timestamp(run, "updated_at", "created_at") or now.isoformat()
            items.append(
                {
                    "key": f"retry:{run_id}",
                    "severity": "warning",
                    "title": "运行进入重试等待",
                    "detail": detail,
                    "source": "workflow_runtime",
                    "href": _alert_href(run_id),
                    "workflow_run_id": run_id,
                    "task_id": str(run.get("task_id") or "").strip() or None,
                    "updated_at": updated_at,
                    "_sort_at": _parse_datetime(next_dispatch_at or updated_at) or now,
                }
            )
        return items

    @staticmethod
    def _build_dead_letter_run_alerts(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for run in runs:
            if not _run_is_dead_lettered(run):
                continue
            run_id = str(run.get("id") or "").strip()
            if not run_id:
                continue
            protocol = _run_protocol(run)
            reason = (
                str(
                    protocol.get("dead_letter_reason")
                    or protocol.get("last_error")
                    or run.get("failure_message")
                    or ""
                ).strip()
                or "未提供原因"
            )
            updated_at = _run_timestamp(run, "updated_at", "completed_at", "created_at") or datetime.now(
                UTC
            ).isoformat()
            items.append(
                {
                    "key": f"dead_letter:{run_id}",
                    "severity": "critical",
                    "title": "运行进入死信",
                    "detail": f"运行 {run_id} 已进入死信队列。原因：{reason}",
                    "source": "workflow_runtime",
                    "href": _alert_href(run_id),
                    "workflow_run_id": run_id,
                    "task_id": str(run.get("task_id") or "").strip() or None,
                    "updated_at": updated_at,
                    "_sort_at": _parse_datetime(updated_at) or datetime.now(UTC),
                }
            )
        return items

    @staticmethod
    def _build_stale_job_alerts(
        jobs: list[dict[str, Any]],
        *,
        run_by_id: dict[str, dict[str, Any]],
        queue_key: str,
        queue_label: str,
        owner_field: str,
        lease_field: str,
        now: datetime,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for job in jobs:
            owner = str(job.get(owner_field) or "").strip()
            if not owner:
                continue
            lease_expires_at = _parse_datetime(str(job.get(lease_field) or ""))
            if lease_expires_at is not None and lease_expires_at > now:
                continue
            run_id = str(job.get("run_id") or "").strip() or None
            run = run_by_id.get(run_id or "")
            task_id = str((run or {}).get("task_id") or job.get("task_id") or "").strip() or None
            updated_at = (
                str(job.get(lease_field) or job.get("updated_at") or job.get("claimed_at") or "").strip()
                or now.isoformat()
            )
            detail = f"{queue_label} 中的 run {run_id or 'unknown'} claim 已过期，当前 owner={owner}"
            if lease_expires_at is None:
                detail += "，且缺少 lease 截止时间"
            items.append(
                {
                    "key": f"stale:{queue_key}:{run_id or owner}",
                    "severity": "critical",
                    "title": f"{queue_label} 出现过期认领",
                    "detail": detail,
                    "source": f"{queue_key}_queue",
                    "href": _alert_href(run_id),
                    "workflow_run_id": run_id,
                    "task_id": task_id,
                    "updated_at": updated_at,
                    "_sort_at": _parse_datetime(updated_at) or now,
                }
            )
        return items

    @staticmethod
    def _build_stale_run_alerts(runs: list[dict[str, Any]], *, now: datetime) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for run in runs:
            if not _run_claim_is_stale(run, now=now):
                continue
            run_id = str(run.get("id") or "").strip()
            if not run_id:
                continue
            lease_expires_at = str(run.get("dispatch_lease_expires_at") or "").strip()
            dispatcher_id = str(run.get("dispatcher_id") or "").strip() or "unknown"
            updated_at = _run_timestamp(run, "updated_at", "created_at") or now.isoformat()
            detail = f"运行 {run_id} 的 dispatch claim 已过期，dispatcher={dispatcher_id}"
            if lease_expires_at:
                detail += f"，lease 截止 {lease_expires_at}"
            items.append(
                {
                    "key": f"stale:dispatch:{run_id}",
                    "severity": "critical",
                    "title": "调度 claim 需要回收",
                    "detail": detail,
                    "source": "dispatch_queue",
                    "href": _alert_href(run_id),
                    "workflow_run_id": run_id,
                    "task_id": str(run.get("task_id") or "").strip() or None,
                    "updated_at": updated_at,
                    "_sort_at": _parse_datetime(lease_expires_at or updated_at) or now,
                }
            )
        return items

    @staticmethod
    def _build_retry_job_alerts(
        jobs: list[dict[str, Any]],
        *,
        run_by_id: dict[str, dict[str, Any]],
        queue_key: str,
        queue_label: str,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for job in jobs:
            protocol = _job_protocol(job)
            attempt = max(_safe_int(protocol.get("attempt") or job.get("attempt"), default=1), 1)
            if attempt <= 1 or bool(protocol.get("dead_letter") or job.get("dead_letter")):
                continue
            run_id = str(job.get("run_id") or "").strip()
            if not run_id:
                continue
            run = run_by_id.get(run_id)
            updated_at = (
                str(job.get("updated_at") or job.get("available_at") or "").strip()
                or datetime.now(UTC).isoformat()
            )
            last_error = str(protocol.get("last_error") or job.get("last_error") or "").strip() or None
            detail = f"{queue_label} 中的 run {run_id} 已进入第 {attempt} 次重试"
            if last_error:
                detail += f"。最近错误：{last_error}"
            items.append(
                {
                    "key": f"retry:{run_id}",
                    "severity": "warning",
                    "title": "队列中存在重试任务",
                    "detail": detail,
                    "source": f"{queue_key}_queue",
                    "href": _alert_href(run_id),
                    "workflow_run_id": run_id,
                    "task_id": str((run or {}).get("task_id") or job.get("task_id") or "").strip() or None,
                    "updated_at": updated_at,
                    "_sort_at": _parse_datetime(updated_at) or datetime.now(UTC),
                }
            )
        return items


workflow_runtime_snapshot_service = WorkflowRuntimeSnapshotService()
