from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.core.agent_protocol import protocol_from_dispatch_context
from app.services.control_plane_audit_service import append_control_plane_audit_log
from app.services.operational_log_service import append_realtime_event
from app.services.persistence_service import persistence_service
from app.services.store import store
from app.services.tenancy_service import entity_scope


TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled"}
TERMINAL_TASK_STATUSES = {"completed", "failed", "cancelled"}
GUARD_USER = "system:scheduler_guard"
GUARD_AGENT = "Scheduler Guard"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_datetime(value: str | None) -> datetime | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _normalize_text(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _safe_float(value: object, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_runs(persistence: Any) -> list[dict]:
    list_runs = getattr(persistence, "list_workflow_runs", None)
    if callable(list_runs):
        items = list_runs()
        if items is not None:
            return [store.clone(item) for item in items]
    if getattr(persistence, "enabled", False):
        return []
    return [store.clone(item) for item in store.workflow_runs]


def _load_tasks(persistence: Any) -> list[dict]:
    list_tasks = getattr(persistence, "list_tasks", None)
    if callable(list_tasks):
        items = list_tasks()
        if items is not None:
            return [store.clone(item) for item in items]
    if getattr(persistence, "enabled", False):
        return []
    return [store.clone(item) for item in store.tasks]


def _load_jobs(persistence: Any, method_name: str) -> list[dict]:
    loader = getattr(persistence, method_name, None)
    if callable(loader):
        items = loader()
        if items is not None:
            return [store.clone(item) for item in items]
    if getattr(persistence, "enabled", False):
        return []
    return []


def _find_cached_run(run_id: str) -> dict | None:
    for run in store.workflow_runs:
        if str(run.get("id") or "").strip() == run_id:
            return run
    return None


def _sync_cached_run(run: dict) -> dict:
    run_id = str(run.get("id") or "").strip()
    payload = store.clone(run)
    cached = _find_cached_run(run_id)
    if cached is None:
        store.workflow_runs.insert(0, payload)
        return payload
    cached.clear()
    cached.update(payload)
    return cached


def _find_cached_task(task_id: str) -> dict | None:
    for task in store.tasks:
        if str(task.get("id") or "").strip() == task_id:
            return task
    return None


def _sync_cached_task(task: dict) -> dict:
    task_id = str(task.get("id") or "").strip()
    payload = store.clone(task)
    cached = _find_cached_task(task_id)
    if cached is None:
        store.tasks.insert(0, payload)
        return payload
    cached.clear()
    cached.update(payload)
    return cached


def _dispatch_context(run: dict | None) -> dict:
    dispatch_context = (run or {}).get("dispatch_context")
    return dispatch_context if isinstance(dispatch_context, dict) else {}


def _workflow_policy(run: dict | None) -> dict:
    dispatch_context = _dispatch_context(run)
    policy = dispatch_context.get("workflow_policy")
    if not isinstance(policy, dict):
        policy = dispatch_context.get("workflowPolicy")
    return policy if isinstance(policy, dict) else {}


def _step_delay_for_run(run: dict | None) -> float:
    policy = _workflow_policy(run)
    return max(
        _safe_float(
            policy.get("step_delay_seconds") or policy.get("stepDelaySeconds"),
            default=0.0,
        ),
        0.0,
    )


def _scope_kwargs(entity: dict | None) -> dict[str, str]:
    scope = entity_scope(entity)
    return {
        "tenant_id": scope["tenant_id"],
        "project_id": scope["project_id"],
        "environment": scope["environment"],
    }


def _append_guard_audit(
    *,
    action: str,
    resource: str,
    details: str,
    metadata: dict[str, Any],
    entity: dict | None,
    severity: str = "warning",
    workflow_run_id: str | None = None,
    task_id: str | None = None,
) -> None:
    append_control_plane_audit_log(
        action=action,
        user=GUARD_USER,
        resource=resource,
        details=details,
        status_text="success",
        metadata=metadata,
        **_scope_kwargs(entity),
    )
    append_realtime_event(
        agent=GUARD_AGENT,
        message=details,
        type_=severity,
        source="scheduler_guard",
        workflow_run_id=workflow_run_id,
        task_id=task_id,
        metadata=metadata,
    )


class SchedulerGuardService:
    def __init__(self, *, persistence=None) -> None:
        self._persistence = persistence or persistence_service

    def guard_dispatch_runtime(
        self,
        *,
        now: datetime | None = None,
        persistence: Any | None = None,
    ) -> dict[str, int]:
        resolved_now = now or _utc_now()
        resolved_persistence = persistence or self._persistence
        runs = _load_runs(resolved_persistence)
        runs_by_id = {
            str(run.get("id") or "").strip(): run
            for run in runs
            if str(run.get("id") or "").strip()
        }
        jobs = _load_jobs(resolved_persistence, "list_workflow_dispatch_jobs")
        summary = {
            "reclaimed_run_claims": 0,
            "reclaimed_job_claims": 0,
            "deleted_orphan_jobs": 0,
        }

        release_run_claim = getattr(resolved_persistence, "release_workflow_run_claim", None)
        release_job_claim = getattr(resolved_persistence, "release_workflow_dispatch_job_claim", None)
        delete_job = getattr(resolved_persistence, "delete_workflow_dispatch_job", None)

        for job in jobs:
            run_id = str(job.get("run_id") or "").strip()
            run = runs_by_id.get(run_id)
            if run is None or str((run or {}).get("status") or "").strip().lower() in TERMINAL_RUN_STATUSES:
                if callable(delete_job) and run_id:
                    deleted = delete_job(
                        run_id,
                        dispatcher_id=_normalize_text(job.get("dispatcher_id")),
                        claimed_at=_normalize_text(job.get("claimed_at")),
                    )
                    if deleted:
                        summary["deleted_orphan_jobs"] += 1
                        _append_guard_audit(
                            action="scheduler.dispatch_job.deleted",
                            resource=f"workflow.dispatch_job.{run_id}",
                            details=f"Dispatch job {run_id} 已被清理，原因是关联 run 缺失或已终态。",
                            metadata={
                                "run_id": run_id,
                                "queue": "dispatch",
                                "reason": "orphan_or_terminal",
                            },
                            entity=run or {"id": run_id},
                            severity="warning",
                            workflow_run_id=run_id or None,
                        )
                continue

            owner = _normalize_text(job.get("dispatcher_id"))
            lease_expires_at = _parse_datetime(
                _normalize_text(job.get("lease_expires_at") or job.get("dispatch_lease_expires_at"))
            )
            if owner and lease_expires_at is not None and lease_expires_at <= resolved_now:
                if callable(release_job_claim):
                    released = release_job_claim(
                        run_id,
                        dispatcher_id=owner,
                        claimed_at=_normalize_text(job.get("claimed_at")),
                    )
                    if released is not None and not _normalize_text(released.get("dispatcher_id")):
                        summary["reclaimed_job_claims"] += 1
                        _append_guard_audit(
                            action="scheduler.dispatch_claim.reclaimed",
                            resource=f"workflow.dispatch_job.{run_id}",
                            details=f"Dispatch stale lease 已回收，run={run_id}，owner={owner}。",
                            metadata={
                                "run_id": run_id,
                                "queue": "dispatch",
                                "owner": owner,
                                "lease_expires_at": lease_expires_at.isoformat(),
                            },
                            entity=run,
                            severity="warning",
                            workflow_run_id=run_id,
                            task_id=_normalize_text(run.get("task_id")),
                        )

        for run in runs:
            run_id = str(run.get("id") or "").strip()
            owner = _normalize_text(run.get("dispatcher_id"))
            lease_expires_at = _parse_datetime(_normalize_text(run.get("dispatch_lease_expires_at")))
            if not run_id or not owner or lease_expires_at is None or lease_expires_at > resolved_now:
                continue
            if callable(release_run_claim):
                released = release_run_claim(
                    run_id,
                    dispatcher_id=owner,
                )
                if released is not None and not _normalize_text(released.get("dispatcher_id")):
                    summary["reclaimed_run_claims"] += 1
                    _sync_cached_run(released)
                    _append_guard_audit(
                        action="scheduler.run_claim.reclaimed",
                        resource=f"workflow.run.{run_id}",
                        details=f"Run stale dispatch claim 已回收，run={run_id}，owner={owner}。",
                        metadata={
                            "run_id": run_id,
                            "owner": owner,
                            "lease_expires_at": lease_expires_at.isoformat(),
                        },
                        entity=released,
                        severity="warning",
                        workflow_run_id=run_id,
                        task_id=_normalize_text(run.get("task_id")),
                    )

        return summary

    def guard_workflow_execution_runtime(
        self,
        *,
        now: datetime | None = None,
        persistence: Any | None = None,
    ) -> dict[str, int]:
        resolved_now = now or _utc_now()
        resolved_persistence = persistence or self._persistence
        runs = _load_runs(resolved_persistence)
        runs_by_id = {
            str(run.get("id") or "").strip(): run
            for run in runs
            if str(run.get("id") or "").strip()
        }
        jobs = _load_jobs(resolved_persistence, "list_workflow_execution_jobs")
        jobs_by_run_id = {
            str(job.get("run_id") or "").strip(): job
            for job in jobs
            if str(job.get("run_id") or "").strip()
        }
        summary = {
            "reclaimed_claims": 0,
            "deleted_orphan_jobs": 0,
            "repaired_missing_jobs": 0,
        }

        release_job_claim = getattr(resolved_persistence, "release_workflow_execution_job_claim", None)
        delete_job = getattr(resolved_persistence, "delete_workflow_execution_job", None)
        upsert_job = getattr(resolved_persistence, "upsert_workflow_execution_job", None)

        for job in jobs:
            run_id = str(job.get("run_id") or "").strip()
            run = runs_by_id.get(run_id)
            run_status = str((run or {}).get("status") or "").strip().lower()
            if run is None or run_status in TERMINAL_RUN_STATUSES:
                if callable(delete_job) and run_id:
                    deleted = delete_job(
                        run_id,
                        worker_id=_normalize_text(job.get("worker_id")),
                        claimed_at=_normalize_text(job.get("claimed_at")),
                    )
                    if deleted:
                        summary["deleted_orphan_jobs"] += 1
                        _append_guard_audit(
                            action="scheduler.workflow_execution_job.deleted",
                            resource=f"workflow.execution_job.{run_id}",
                            details=f"Workflow execution job {run_id} 已被清理，原因是关联 run 缺失或已终态。",
                            metadata={
                                "run_id": run_id,
                                "queue": "workflow_execution",
                                "reason": "orphan_or_terminal",
                            },
                            entity=run or {"id": run_id},
                            severity="warning",
                            workflow_run_id=run_id or None,
                        )
                continue

            owner = _normalize_text(job.get("worker_id"))
            lease_expires_at = _parse_datetime(_normalize_text(job.get("lease_expires_at")))
            if owner and lease_expires_at is not None and lease_expires_at <= resolved_now:
                if callable(release_job_claim):
                    released = release_job_claim(
                        run_id,
                        worker_id=owner,
                        claimed_at=_normalize_text(job.get("claimed_at")),
                    )
                    if released is not None and not _normalize_text(released.get("worker_id")):
                        summary["reclaimed_claims"] += 1
                        _append_guard_audit(
                            action="scheduler.workflow_execution_claim.reclaimed",
                            resource=f"workflow.execution_job.{run_id}",
                            details=f"Workflow execution stale lease 已回收，run={run_id}，owner={owner}。",
                            metadata={
                                "run_id": run_id,
                                "queue": "workflow_execution",
                                "owner": owner,
                                "lease_expires_at": lease_expires_at.isoformat(),
                            },
                            entity=run,
                            severity="warning",
                            workflow_run_id=run_id,
                            task_id=_normalize_text(run.get("task_id")),
                        )

        for run in runs:
            run_id = str(run.get("id") or "").strip()
            if not run_id or run_id in jobs_by_run_id:
                continue
            if str(run.get("status") or "").strip().lower() in TERMINAL_RUN_STATUSES:
                continue
            dispatch_state = str(_dispatch_context(run).get("state") or "").strip().lower()
            if dispatch_state != "dispatched":
                continue
            if not callable(upsert_job):
                continue

            available_at = (
                _normalize_text(run.get("updated_at"))
                or _normalize_text(run.get("started_at"))
                or resolved_now.isoformat()
            )
            created = upsert_job(
                run_id,
                available_at=available_at,
                queued_at=available_at,
                step_delay_seconds=_step_delay_for_run(run),
                **{
                    key: value
                    for key, value in protocol_from_dispatch_context(run).items()
                    if key not in {"available_at", "emitted_at"}
                },
            )
            if created is not None:
                summary["repaired_missing_jobs"] += 1
                _append_guard_audit(
                    action="scheduler.workflow_execution_job.repaired",
                    resource=f"workflow.execution_job.{run_id}",
                    details=f"Workflow execution job {run_id} 已自动补建，防止 dispatched run 失队列。",
                    metadata={
                        "run_id": run_id,
                        "queue": "workflow_execution",
                        "repair": "missing_job",
                    },
                    entity=run,
                    severity="warning",
                    workflow_run_id=run_id,
                    task_id=_normalize_text(run.get("task_id")),
                )

        return summary

    def guard_agent_execution_runtime(
        self,
        *,
        now: datetime | None = None,
        persistence: Any | None = None,
    ) -> dict[str, int]:
        resolved_now = now or _utc_now()
        resolved_persistence = persistence or self._persistence
        runs = _load_runs(resolved_persistence)
        tasks = _load_tasks(resolved_persistence)
        runs_by_id = {
            str(run.get("id") or "").strip(): run
            for run in runs
            if str(run.get("id") or "").strip()
        }
        tasks_by_id = {
            str(task.get("id") or "").strip(): task
            for task in tasks
            if str(task.get("id") or "").strip()
        }
        jobs = _load_jobs(resolved_persistence, "list_agent_execution_jobs")
        jobs_by_run_id = {
            str(job.get("run_id") or "").strip(): job
            for job in jobs
            if str(job.get("run_id") or "").strip()
        }
        summary = {
            "reclaimed_claims": 0,
            "deleted_orphan_jobs": 0,
            "repaired_missing_jobs": 0,
        }

        release_job_claim = getattr(resolved_persistence, "release_agent_execution_job_claim", None)
        delete_job = getattr(resolved_persistence, "delete_agent_execution_job", None)
        upsert_job = getattr(resolved_persistence, "upsert_agent_execution_job", None)

        for job in jobs:
            run_id = str(job.get("run_id") or "").strip()
            task_id = str(job.get("task_id") or "").strip()
            run = runs_by_id.get(run_id)
            task = tasks_by_id.get(task_id)
            run_status = str((run or {}).get("status") or "").strip().lower()
            task_status = str((task or {}).get("status") or "").strip().lower()
            if (
                run is None
                or task is None
                or run_status in TERMINAL_RUN_STATUSES
                or task_status in TERMINAL_TASK_STATUSES
            ):
                if callable(delete_job) and run_id:
                    deleted = delete_job(
                        run_id,
                        worker_id=_normalize_text(job.get("worker_id")),
                        claimed_at=_normalize_text(job.get("claimed_at")),
                    )
                    if deleted:
                        summary["deleted_orphan_jobs"] += 1
                        _append_guard_audit(
                            action="scheduler.agent_execution_job.deleted",
                            resource=f"workflow.agent_execution_job.{run_id}",
                            details=f"Agent execution job {run_id} 已被清理，原因是关联 task/run 缺失或已终态。",
                            metadata={
                                "run_id": run_id,
                                "task_id": task_id or None,
                                "queue": "agent_execution",
                                "reason": "orphan_or_terminal",
                            },
                            entity=run or task or {"id": run_id},
                            severity="warning",
                            workflow_run_id=run_id or None,
                            task_id=task_id or None,
                        )
                continue

            owner = _normalize_text(job.get("worker_id"))
            lease_expires_at = _parse_datetime(_normalize_text(job.get("lease_expires_at")))
            if owner and lease_expires_at is not None and lease_expires_at <= resolved_now:
                if callable(release_job_claim):
                    released = release_job_claim(
                        run_id,
                        worker_id=owner,
                        claimed_at=_normalize_text(job.get("claimed_at")),
                    )
                    if released is not None and not _normalize_text(released.get("worker_id")):
                        summary["reclaimed_claims"] += 1
                        _append_guard_audit(
                            action="scheduler.agent_execution_claim.reclaimed",
                            resource=f"workflow.agent_execution_job.{run_id}",
                            details=f"Agent execution stale lease 已回收，run={run_id}，owner={owner}。",
                            metadata={
                                "run_id": run_id,
                                "task_id": task_id,
                                "queue": "agent_execution",
                                "owner": owner,
                                "lease_expires_at": lease_expires_at.isoformat(),
                            },
                            entity=run,
                            severity="warning",
                            workflow_run_id=run_id,
                            task_id=task_id,
                        )

        for run in runs:
            run_id = str(run.get("id") or "").strip()
            if not run_id or run_id in jobs_by_run_id:
                continue
            if str(run.get("status") or "").strip().lower() in TERMINAL_RUN_STATUSES:
                continue
            dispatch_context = _dispatch_context(run)
            dispatch_state = str(dispatch_context.get("state") or "").strip().lower()
            if dispatch_state != "agent_queued":
                continue
            task_id = str(run.get("task_id") or "").strip()
            task = tasks_by_id.get(task_id)
            execution_agent_id = _normalize_text(
                dispatch_context.get("execution_agent_id") or dispatch_context.get("executionAgentId")
            )
            if not task_id or task is None or not execution_agent_id or not callable(upsert_job):
                continue

            available_at = (
                _normalize_text(
                    dispatch_context.get("agent_execution_queued_at")
                    or dispatch_context.get("agentExecutionQueuedAt")
                )
                or _normalize_text(run.get("updated_at"))
                or resolved_now.isoformat()
            )
            created = upsert_job(
                run_id,
                task_id=task_id,
                workflow_id=str(run.get("workflow_id") or "").strip(),
                execution_agent_id=execution_agent_id,
                available_at=available_at,
                queued_at=available_at,
                step_delay_seconds=_step_delay_for_run(run),
                **{
                    key: value
                    for key, value in protocol_from_dispatch_context(run).items()
                    if key not in {"available_at", "emitted_at"}
                },
            )
            if created is not None:
                summary["repaired_missing_jobs"] += 1
                _append_guard_audit(
                    action="scheduler.agent_execution_job.repaired",
                    resource=f"workflow.agent_execution_job.{run_id}",
                    details=f"Agent execution job {run_id} 已自动补建，防止 agent_queued run 失队列。",
                    metadata={
                        "run_id": run_id,
                        "task_id": task_id,
                        "queue": "agent_execution",
                        "repair": "missing_job",
                    },
                    entity=run,
                    severity="warning",
                    workflow_run_id=run_id,
                    task_id=task_id,
                )

        return summary


scheduler_guard_service = SchedulerGuardService()
