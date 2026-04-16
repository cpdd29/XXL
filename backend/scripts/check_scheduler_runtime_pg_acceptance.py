from __future__ import annotations

import argparse
import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys
from typing import Any
from uuid import uuid4

from sqlalchemy import delete


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import app.services.scheduler_guard_service as scheduler_guard_module
from app.db.models import (
    AgentExecutionJobRecord,
    TaskRecord,
    TaskStepRecord,
    WorkflowDispatchJobRecord,
    WorkflowExecutionJobRecord,
    WorkflowRunRecord,
)
from app.services.persistence_service import StatePersistenceService
from app.services.scheduler_guard_service import SchedulerGuardService
from app.services.store import InMemoryStore


DISPATCH_RUNTIME_METHODS = (
    "claim_due_workflow_dispatch_jobs",
    "claim_workflow_dispatch_job",
    "release_workflow_dispatch_job_claim",
    "delete_workflow_dispatch_job",
    "claim_due_workflow_runs",
    "claim_workflow_run",
    "release_workflow_run_claim",
)
WORKFLOW_EXECUTION_RUNTIME_METHODS = (
    "claim_due_workflow_execution_jobs",
    "claim_workflow_execution_job",
    "release_workflow_execution_job_claim",
    "delete_workflow_execution_job",
    "upsert_workflow_execution_job",
)
AGENT_EXECUTION_RUNTIME_METHODS = (
    "claim_due_agent_execution_jobs",
    "claim_agent_execution_job",
    "release_agent_execution_job_claim",
    "delete_agent_execution_job",
    "upsert_agent_execution_job",
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso_at(base: datetime, *, seconds: int = 0) -> str:
    return (base + timedelta(seconds=seconds)).isoformat()


def _empty_runtime_store() -> InMemoryStore:
    store = InMemoryStore()
    store.agents = []
    store.tasks = []
    store.task_steps = {}
    store.workflows = []
    store.workflow_runs = []
    store.users = []
    store.user_profiles = {}
    store.audit_logs = []
    store.security_rules = []
    store.system_settings = {}
    store.internal_event_deliveries = []
    store.operational_logs = []
    store.memory_sessions = {}
    return store


def _build_task(*, task_id: str, run_id: str, workflow_id: str, created_at: str) -> dict[str, Any]:
    return {
        "id": task_id,
        "title": f"Scheduler Probe {task_id}",
        "description": "scheduler runtime probe",
        "status": "running",
        "priority": "high",
        "created_at": created_at,
        "completed_at": None,
        "agent": "Scheduler Probe",
        "tokens": 0,
        "duration": None,
        "workflow_id": workflow_id,
        "workflow_run_id": run_id,
        "trace_id": f"trace:{task_id}",
        "channel": "probe",
        "session_id": f"session:{task_id}",
        "user_key": f"user:{task_id}",
        "result": None,
    }


def _build_run(
    *,
    run_id: str,
    task_id: str,
    workflow_id: str,
    created_at: str,
    next_dispatch_at: str | None,
    dispatch_state: str,
    execution_agent_id: str | None = None,
) -> dict[str, Any]:
    dispatch_context = {
        "type": "message_dispatch",
        "state": dispatch_state,
        "trace_id": f"trace:{run_id}",
    }
    if execution_agent_id:
        dispatch_context["execution_agent_id"] = execution_agent_id
    return {
        "id": run_id,
        "workflow_id": workflow_id,
        "workflow_name": "Scheduler Probe Workflow",
        "task_id": task_id,
        "trigger": "probe",
        "intent": "probe",
        "status": "running",
        "created_at": created_at,
        "updated_at": created_at,
        "started_at": created_at,
        "completed_at": None,
        "next_dispatch_at": next_dispatch_at,
        "dispatch_failure_count": 0,
        "last_dispatch_error": None,
        "dispatcher_id": None,
        "dispatch_claimed_at": None,
        "dispatch_lease_expires_at": None,
        "current_stage": "dispatch",
        "active_edges": [],
        "nodes": [],
        "logs": [],
        "dispatch_context": dispatch_context,
        "memory_hits": 0,
        "warnings": [],
    }


def _check_methods(service: object, method_names: tuple[str, ...]) -> dict[str, Any]:
    available = [name for name in method_names if callable(getattr(service, name, None))]
    missing = [name for name in method_names if name not in available]
    return {
        "available": available,
        "missing": missing,
        "count": len(available),
    }


def _cleanup_probe_rows(service: StatePersistenceService, probe_prefix: str) -> None:
    if service._session_factory is None:
        return
    with service._session_factory() as session:
        like_value = f"{probe_prefix}%"
        session.execute(delete(TaskStepRecord).where(TaskStepRecord.task_id.like(like_value)))
        session.execute(delete(AgentExecutionJobRecord).where(AgentExecutionJobRecord.run_id.like(like_value)))
        session.execute(delete(WorkflowExecutionJobRecord).where(WorkflowExecutionJobRecord.run_id.like(like_value)))
        session.execute(delete(WorkflowDispatchJobRecord).where(WorkflowDispatchJobRecord.run_id.like(like_value)))
        session.execute(delete(WorkflowRunRecord).where(WorkflowRunRecord.id.like(like_value)))
        session.execute(delete(TaskRecord).where(TaskRecord.id.like(like_value)))
        session.commit()


@contextmanager
def _silence_guard_side_effects():
    original_audit = scheduler_guard_module.append_control_plane_audit_log
    original_event = scheduler_guard_module.append_realtime_event
    scheduler_guard_module.append_control_plane_audit_log = lambda **kwargs: None
    scheduler_guard_module.append_realtime_event = lambda **kwargs: None
    try:
        yield
    finally:
        scheduler_guard_module.append_control_plane_audit_log = original_audit
        scheduler_guard_module.append_realtime_event = original_event


def _job_claim_cycle(
    *,
    service_a: StatePersistenceService,
    service_b: StatePersistenceService,
    run_id: str,
    owner_a: str,
    owner_b: str,
    owner_field: str,
    get_method_name: str,
    upsert_method_name: str,
    claim_due_method_name: str,
    claim_method_name: str,
    release_method_name: str,
    delete_method_name: str,
    upsert_kwargs: dict[str, Any],
    supports_release_claimed_at: bool,
) -> dict[str, Any]:
    now = _utc_now()
    available_at = _iso_at(now, seconds=-120)
    initial_claimed_at = _iso_at(now, seconds=-30)
    initial_lease_expires_at = _iso_at(now, seconds=60)
    stale_claimed_at = _iso_at(now, seconds=-240)
    stale_lease_expires_at = _iso_at(now, seconds=-120)
    takeover_claimed_at = _iso_at(now, seconds=10)
    takeover_lease_expires_at = _iso_at(now, seconds=120)

    upsert = getattr(service_a, upsert_method_name)
    claim_due_a = getattr(service_a, claim_due_method_name)
    claim_due_b = getattr(service_b, claim_due_method_name)
    claim_b = getattr(service_b, claim_method_name)
    release_a = getattr(service_a, release_method_name)
    release_b = getattr(service_b, release_method_name)
    get_job = getattr(service_b, get_method_name)
    delete_job = getattr(service_b, delete_method_name)

    seeded = upsert(
        run_id,
        available_at=available_at,
        queued_at=available_at,
        **upsert_kwargs,
    )
    claimed_by_a = claim_due_a(
        **{
            owner_field: owner_a,
            "claimed_at": initial_claimed_at,
            "lease_expires_at": initial_lease_expires_at,
            "due_before": _iso_at(now, seconds=0),
            "limit": 10,
        }
    )
    blocked_for_b = claim_due_b(
        **{
            owner_field: owner_b,
            "claimed_at": _iso_at(now, seconds=1),
            "lease_expires_at": _iso_at(now, seconds=90),
            "due_before": _iso_at(now, seconds=0),
            "limit": 10,
        }
    )

    upsert(
        run_id,
        available_at=available_at,
        queued_at=available_at,
        **{
            **upsert_kwargs,
            owner_field: owner_a,
            "claimed_at": stale_claimed_at,
            "lease_expires_at": stale_lease_expires_at,
        },
    )
    taken_over_by_b = claim_b(
        run_id,
        **{
            owner_field: owner_b,
            "claimed_at": takeover_claimed_at,
            "lease_expires_at": takeover_lease_expires_at,
            "due_before": _iso_at(now, seconds=0),
            "respect_existing_owner": True,
        }
    )

    invalid_release_kwargs = {owner_field: owner_a}
    valid_release_kwargs = {owner_field: owner_b}
    if supports_release_claimed_at:
        invalid_release_kwargs["claimed_at"] = stale_claimed_at
        valid_release_kwargs["claimed_at"] = takeover_claimed_at

    invalid_release = release_a(run_id, **invalid_release_kwargs)
    after_invalid_release = get_job(run_id)
    valid_release = release_b(run_id, **valid_release_kwargs)
    after_valid_release = get_job(run_id)
    deleted = delete_job(run_id)

    owner_after_invalid = None if after_invalid_release is None else after_invalid_release.get(owner_field)
    owner_after_valid = None if after_valid_release is None else after_valid_release.get(owner_field)

    return {
        "ok": bool(seeded)
        and len(claimed_by_a or []) == 1
        and len(blocked_for_b or []) == 0
        and bool(taken_over_by_b)
        and owner_after_invalid == owner_b
        and bool(valid_release)
        and owner_after_valid in {None, ""}
        and bool(deleted),
        "details": {
            "seeded": bool(seeded),
            "claimed_by_a": len(claimed_by_a or []),
            "blocked_for_b": len(blocked_for_b or []),
            "taken_over_by_b": bool(taken_over_by_b),
            "invalid_release_blocked": owner_after_invalid == owner_b,
            "owner_after_invalid_release": owner_after_invalid,
            "valid_release_cleared": bool(valid_release) and owner_after_valid in {None, ""},
            "deleted": bool(deleted),
        },
    }


def _workflow_run_claim_cycle(
    *,
    service_a: StatePersistenceService,
    service_b: StatePersistenceService,
    run_id: str,
) -> dict[str, Any]:
    now = _utc_now()
    first_claimed_at = _iso_at(now, seconds=0)
    first_lease_expires_at = _iso_at(now, seconds=60)
    second_claimed_at = _iso_at(now, seconds=5)
    second_lease_expires_at = _iso_at(now, seconds=90)

    claimed_by_a = service_a.claim_due_workflow_runs(
        dispatcher_id="probe-dispatcher-a",
        claimed_at=first_claimed_at,
        lease_expires_at=first_lease_expires_at,
        due_before=_iso_at(now, seconds=0),
        limit=10,
    )
    blocked_for_b = service_b.claim_due_workflow_runs(
        dispatcher_id="probe-dispatcher-b",
        claimed_at=second_claimed_at,
        lease_expires_at=second_lease_expires_at,
        due_before=_iso_at(now, seconds=0),
        limit=10,
    )
    invalid_release = service_b.release_workflow_run_claim(run_id, dispatcher_id="probe-dispatcher-b")
    valid_release = service_a.release_workflow_run_claim(run_id, dispatcher_id="probe-dispatcher-a")
    claimed_after_release = service_b.claim_workflow_run(
        run_id,
        dispatcher_id="probe-dispatcher-b",
        claimed_at=second_claimed_at,
        lease_expires_at=second_lease_expires_at,
        respect_existing_owner=True,
    )

    return {
        "ok": len(claimed_by_a or []) == 1
        and len(blocked_for_b or []) == 0
        and bool(valid_release)
        and bool(claimed_after_release),
        "details": {
            "claimed_by_a": len(claimed_by_a or []),
            "blocked_for_b": len(blocked_for_b or []),
            "invalid_release_blocked": invalid_release is None or str(invalid_release.get("dispatcher_id") or "") == "probe-dispatcher-a",
            "valid_release": bool(valid_release),
            "claimed_after_release": bool(claimed_after_release),
        },
    }


def _dispatch_guard_check(service: StatePersistenceService, *, probe_prefix: str) -> dict[str, Any]:
    now = _utc_now()
    run_id = f"{probe_prefix}-guard-dispatch-run"
    task_id = f"{probe_prefix}-guard-dispatch-task"
    created_at = _iso_at(now, seconds=-300)
    service.persist_execution_state(
        task=_build_task(task_id=task_id, run_id=run_id, workflow_id="workflow-dispatch", created_at=created_at),
        workflow_run=_build_run(
            run_id=run_id,
            task_id=task_id,
            workflow_id="workflow-dispatch",
            created_at=created_at,
            next_dispatch_at=_iso_at(now, seconds=-240),
            dispatch_state="queued",
        ),
    )
    service.claim_workflow_run(
        run_id,
        dispatcher_id="stale-dispatcher",
        claimed_at=_iso_at(now, seconds=-180),
        lease_expires_at=_iso_at(now, seconds=-120),
        respect_existing_owner=True,
    )
    service.upsert_workflow_dispatch_job(
        run_id,
        available_at=_iso_at(now, seconds=-240),
        queued_at=_iso_at(now, seconds=-240),
        dispatcher_id="stale-dispatcher",
        claimed_at=_iso_at(now, seconds=-180),
        lease_expires_at=_iso_at(now, seconds=-120),
    )

    with _silence_guard_side_effects():
        summary = SchedulerGuardService(persistence=service).guard_dispatch_runtime(
            now=now,
            persistence=service,
        )

    return {
        "ok": summary == {
            "reclaimed_run_claims": 1,
            "reclaimed_job_claims": 1,
            "deleted_orphan_jobs": 0,
        },
        "details": summary,
    }


def _workflow_guard_check(service: StatePersistenceService, *, probe_prefix: str) -> dict[str, Any]:
    now = _utc_now()
    stale_run_id = f"{probe_prefix}-guard-workflow-stale-run"
    stale_task_id = f"{probe_prefix}-guard-workflow-stale-task"
    orphan_run_id = f"{probe_prefix}-guard-workflow-orphan-run"
    repair_run_id = f"{probe_prefix}-guard-workflow-repair-run"
    repair_task_id = f"{probe_prefix}-guard-workflow-repair-task"
    created_at = _iso_at(now, seconds=-300)

    service.persist_execution_state(
        task=_build_task(task_id=stale_task_id, run_id=stale_run_id, workflow_id="workflow-exec", created_at=created_at),
        workflow_run=_build_run(
            run_id=stale_run_id,
            task_id=stale_task_id,
            workflow_id="workflow-exec",
            created_at=created_at,
            next_dispatch_at=None,
            dispatch_state="dispatched",
        ),
    )
    service.upsert_workflow_execution_job(
        stale_run_id,
        available_at=_iso_at(now, seconds=-200),
        queued_at=_iso_at(now, seconds=-200),
        worker_id="stale-worker",
        claimed_at=_iso_at(now, seconds=-180),
        lease_expires_at=_iso_at(now, seconds=-120),
    )
    service.upsert_workflow_execution_job(
        orphan_run_id,
        available_at=_iso_at(now, seconds=-200),
        queued_at=_iso_at(now, seconds=-200),
        worker_id="orphan-worker",
        claimed_at=_iso_at(now, seconds=-180),
        lease_expires_at=_iso_at(now, seconds=-120),
    )
    service.persist_execution_state(
        task=_build_task(task_id=repair_task_id, run_id=repair_run_id, workflow_id="workflow-exec", created_at=created_at),
        workflow_run=_build_run(
            run_id=repair_run_id,
            task_id=repair_task_id,
            workflow_id="workflow-exec",
            created_at=created_at,
            next_dispatch_at=None,
            dispatch_state="dispatched",
        ),
    )

    with _silence_guard_side_effects():
        summary = SchedulerGuardService(persistence=service).guard_workflow_execution_runtime(
            now=now,
            persistence=service,
        )

    return {
        "ok": summary == {
            "reclaimed_claims": 1,
            "deleted_orphan_jobs": 1,
            "repaired_missing_jobs": 1,
        },
        "details": summary,
    }


def _agent_guard_check(service: StatePersistenceService, *, probe_prefix: str) -> dict[str, Any]:
    now = _utc_now()
    stale_run_id = f"{probe_prefix}-guard-agent-stale-run"
    stale_task_id = f"{probe_prefix}-guard-agent-stale-task"
    orphan_run_id = f"{probe_prefix}-guard-agent-orphan-run"
    repair_run_id = f"{probe_prefix}-guard-agent-repair-run"
    repair_task_id = f"{probe_prefix}-guard-agent-repair-task"
    created_at = _iso_at(now, seconds=-300)

    service.persist_execution_state(
        task=_build_task(task_id=stale_task_id, run_id=stale_run_id, workflow_id="__agent_dispatch__", created_at=created_at),
        workflow_run=_build_run(
            run_id=stale_run_id,
            task_id=stale_task_id,
            workflow_id="__agent_dispatch__",
            created_at=created_at,
            next_dispatch_at=None,
            dispatch_state="agent_queued",
            execution_agent_id="probe-agent",
        ),
    )
    service.upsert_agent_execution_job(
        stale_run_id,
        task_id=stale_task_id,
        workflow_id="__agent_dispatch__",
        execution_agent_id="probe-agent",
        available_at=_iso_at(now, seconds=-200),
        queued_at=_iso_at(now, seconds=-200),
        worker_id="stale-agent-worker",
        claimed_at=_iso_at(now, seconds=-180),
        lease_expires_at=_iso_at(now, seconds=-120),
    )
    service.upsert_agent_execution_job(
        orphan_run_id,
        task_id=f"{probe_prefix}-missing-task",
        workflow_id="__agent_dispatch__",
        execution_agent_id="probe-agent",
        available_at=_iso_at(now, seconds=-200),
        queued_at=_iso_at(now, seconds=-200),
        worker_id="orphan-agent-worker",
        claimed_at=_iso_at(now, seconds=-180),
        lease_expires_at=_iso_at(now, seconds=-120),
    )
    service.persist_execution_state(
        task=_build_task(task_id=repair_task_id, run_id=repair_run_id, workflow_id="__agent_dispatch__", created_at=created_at),
        workflow_run=_build_run(
            run_id=repair_run_id,
            task_id=repair_task_id,
            workflow_id="__agent_dispatch__",
            created_at=created_at,
            next_dispatch_at=None,
            dispatch_state="agent_queued",
            execution_agent_id="probe-agent",
        ),
    )

    with _silence_guard_side_effects():
        summary = SchedulerGuardService(persistence=service).guard_agent_execution_runtime(
            now=now,
            persistence=service,
        )

    return {
        "ok": summary == {
            "reclaimed_claims": 1,
            "deleted_orphan_jobs": 1,
            "repaired_missing_jobs": 1,
        },
        "details": summary,
    }


def run_check(*, database_url: str, probe_prefix: str | None = None) -> dict[str, Any]:
    resolved_probe_prefix = probe_prefix or f"probe_{uuid4().hex[:12]}"
    service_a = StatePersistenceService(runtime_store=_empty_runtime_store(), database_url=database_url)
    service_b = StatePersistenceService(runtime_store=_empty_runtime_store(), database_url=database_url)

    init_a = service_a.initialize()
    init_b = service_b.initialize()

    checks: dict[str, dict[str, Any]] = {
        "service_a_initialized": {"ok": bool(init_a), "details": {"enabled": service_a.enabled}},
        "service_b_initialized": {"ok": bool(init_b), "details": {"enabled": service_b.enabled}},
    }
    if not init_a or not init_b:
        return {
            "ok": False,
            "database_url": database_url,
            "probe_prefix": resolved_probe_prefix,
            "checks": checks,
        }

    try:
        _cleanup_probe_rows(service_a, resolved_probe_prefix)

        checks["runtime_methods"] = {
            "ok": not _check_methods(service_a, DISPATCH_RUNTIME_METHODS)["missing"]
            and not _check_methods(service_a, WORKFLOW_EXECUTION_RUNTIME_METHODS)["missing"]
            and not _check_methods(service_a, AGENT_EXECUTION_RUNTIME_METHODS)["missing"],
            "details": {
                "dispatch_runtime": _check_methods(service_a, DISPATCH_RUNTIME_METHODS),
                "workflow_execution_runtime": _check_methods(service_a, WORKFLOW_EXECUTION_RUNTIME_METHODS),
                "agent_execution_runtime": _check_methods(service_a, AGENT_EXECUTION_RUNTIME_METHODS),
            },
        }

        now = _utc_now()
        dispatch_task_id = f"{resolved_probe_prefix}-dispatch-task"
        dispatch_run_id = f"{resolved_probe_prefix}-dispatch-run"
        workflow_task_id = f"{resolved_probe_prefix}-workflow-task"
        workflow_run_id = f"{resolved_probe_prefix}-workflow-run"
        agent_task_id = f"{resolved_probe_prefix}-agent-task"
        agent_run_id = f"{resolved_probe_prefix}-agent-run"
        due_run_task_id = f"{resolved_probe_prefix}-due-run-task"
        due_run_id = f"{resolved_probe_prefix}-due-run"
        reopen_task_id = f"{resolved_probe_prefix}-reopen-task"
        reopen_run_id = f"{resolved_probe_prefix}-reopen-run"

        for task_id, run_id, workflow_id, next_dispatch_at, dispatch_state, execution_agent_id in (
            (dispatch_task_id, dispatch_run_id, "workflow-dispatch", None, "queued", None),
            (workflow_task_id, workflow_run_id, "workflow-execution", None, "queued", None),
            (agent_task_id, agent_run_id, "__agent_dispatch__", None, "queued", "probe-agent"),
            (due_run_task_id, due_run_id, "workflow-due-run", _iso_at(now, seconds=-60), "queued", None),
            (reopen_task_id, reopen_run_id, "workflow-reopen", None, "queued", None),
        ):
            created_at = _iso_at(now, seconds=-90)
            service_a.persist_execution_state(
                task=_build_task(task_id=task_id, run_id=run_id, workflow_id=workflow_id, created_at=created_at),
                workflow_run=_build_run(
                    run_id=run_id,
                    task_id=task_id,
                    workflow_id=workflow_id,
                    created_at=created_at,
                    next_dispatch_at=next_dispatch_at,
                    dispatch_state=dispatch_state,
                    execution_agent_id=execution_agent_id,
                ),
            )

        checks["dispatch_job_claim_cycle"] = _job_claim_cycle(
            service_a=service_a,
            service_b=service_b,
            run_id=dispatch_run_id,
            owner_a="probe-dispatcher-a",
            owner_b="probe-dispatcher-b",
            owner_field="dispatcher_id",
            get_method_name="get_workflow_dispatch_job",
            upsert_method_name="upsert_workflow_dispatch_job",
            claim_due_method_name="claim_due_workflow_dispatch_jobs",
            claim_method_name="claim_workflow_dispatch_job",
            release_method_name="release_workflow_dispatch_job_claim",
            delete_method_name="delete_workflow_dispatch_job",
            upsert_kwargs={},
            supports_release_claimed_at=True,
        )
        checks["workflow_execution_job_claim_cycle"] = _job_claim_cycle(
            service_a=service_a,
            service_b=service_b,
            run_id=workflow_run_id,
            owner_a="probe-workflow-worker-a",
            owner_b="probe-workflow-worker-b",
            owner_field="worker_id",
            get_method_name="get_workflow_execution_job",
            upsert_method_name="upsert_workflow_execution_job",
            claim_due_method_name="claim_due_workflow_execution_jobs",
            claim_method_name="claim_workflow_execution_job",
            release_method_name="release_workflow_execution_job_claim",
            delete_method_name="delete_workflow_execution_job",
            upsert_kwargs={},
            supports_release_claimed_at=True,
        )
        checks["agent_execution_job_claim_cycle"] = _job_claim_cycle(
            service_a=service_a,
            service_b=service_b,
            run_id=agent_run_id,
            owner_a="probe-agent-worker-a",
            owner_b="probe-agent-worker-b",
            owner_field="worker_id",
            get_method_name="get_agent_execution_job",
            upsert_method_name="upsert_agent_execution_job",
            claim_due_method_name="claim_due_agent_execution_jobs",
            claim_method_name="claim_agent_execution_job",
            release_method_name="release_agent_execution_job_claim",
            delete_method_name="delete_agent_execution_job",
            upsert_kwargs={
                "task_id": agent_task_id,
                "workflow_id": "__agent_dispatch__",
                "execution_agent_id": "probe-agent",
            },
            supports_release_claimed_at=True,
        )
        checks["workflow_run_claim_cycle"] = _workflow_run_claim_cycle(
            service_a=service_a,
            service_b=service_b,
            run_id=due_run_id,
        )
        checks["dispatch_guard_runtime"] = _dispatch_guard_check(
            service=service_a,
            probe_prefix=resolved_probe_prefix,
        )
        checks["workflow_guard_runtime"] = _workflow_guard_check(
            service=service_a,
            probe_prefix=resolved_probe_prefix,
        )
        checks["agent_guard_runtime"] = _agent_guard_check(
            service=service_a,
            probe_prefix=resolved_probe_prefix,
        )

        service_a.upsert_workflow_dispatch_job(
            reopen_run_id,
            available_at=_iso_at(now, seconds=-30),
            queued_at=_iso_at(now, seconds=-30),
        )
        service_a.close()
        service_c = StatePersistenceService(runtime_store=_empty_runtime_store(), database_url=database_url)
        reopened = service_c.initialize()
        reopened_job = service_c.get_workflow_dispatch_job(reopen_run_id) if reopened else None
        checks["reopen_visibility"] = {
            "ok": bool(reopened) and bool(reopened_job),
            "details": {
                "service_c_initialized": bool(reopened),
                "reopened_job_visible": bool(reopened_job),
            },
        }
        service_c.close()
    finally:
        _cleanup_probe_rows(service_b, resolved_probe_prefix)
        service_b.close()
        service_a.close()

    return {
        "ok": all(bool(item.get("ok")) for item in checks.values()),
        "database_url": database_url,
        "probe_prefix": resolved_probe_prefix,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run scheduler runtime acceptance checks against a real database-backed persistence service."
    )
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--probe-prefix")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    payload = run_check(database_url=args.database_url, probe_prefix=args.probe_prefix)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.strict and not payload["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
