from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta

from app.services.persistence_service import StatePersistenceService
from app.services.scheduler_guard_service import scheduler_guard_service
from app.services.store import InMemoryStore


def _replace_store(target: InMemoryStore, source: InMemoryStore) -> None:
    target.__dict__.clear()
    target.__dict__.update(deepcopy(source.__dict__))


def _shared_sqlite_service(
    tmp_path,
    *,
    runtime_store: InMemoryStore,
    database_name: str = "package-s-smoke.db",
) -> StatePersistenceService:
    service = StatePersistenceService(
        runtime_store=runtime_store,
        database_url=f"sqlite:///{tmp_path / database_name}",
    )
    assert service.initialize() is True
    return service


def _task(task_id: str) -> dict:
    return {
        "id": task_id,
        "title": task_id,
        "description": task_id,
        "status": "running",
        "priority": "medium",
        "created_at": "2026-04-15T11:55:00+00:00",
        "completed_at": None,
        "agent": "Master Bot",
        "tokens": 0,
        "duration": None,
        "workflow_id": "workflow-1",
        "workflow_run_id": None,
        "trace_id": None,
        "channel": None,
        "session_id": None,
        "user_key": None,
        "preferred_language": "zh",
        "detected_lang": "zh",
        "route_decision": None,
        "result": None,
    }


def _run(
    run_id: str,
    *,
    task_id: str,
    next_dispatch_at: str,
    dispatch_context: dict | None = None,
) -> dict:
    return {
        "id": run_id,
        "workflow_id": "workflow-1",
        "workflow_name": "Smoke Workflow",
        "task_id": task_id,
        "trigger": "message",
        "intent": "smoke",
        "status": "running",
        "created_at": "2026-04-15T11:50:00+00:00",
        "updated_at": "2026-04-15T11:55:00+00:00",
        "started_at": "2026-04-15T11:51:00+00:00",
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
        "dispatch_context": dispatch_context or {},
        "memory_hits": 0,
        "warnings": [],
    }


def test_multi_instance_scheduler_guard_smoke(tmp_path) -> None:
    seeded_store = InMemoryStore()
    seeded_store.tasks = [_task("task-smoke-dispatch"), _task("task-smoke-agent")]
    seeded_store.workflow_runs = [
        _run(
            "run-smoke-dispatch",
            task_id="task-smoke-dispatch",
            next_dispatch_at="2026-04-15T11:55:00+00:00",
            dispatch_context={},
        ),
        _run(
            "run-smoke-execution",
            task_id="task-smoke-dispatch",
            next_dispatch_at="2026-04-15T11:55:00+00:00",
            dispatch_context={
                "state": "dispatched",
                "workflow_policy": {"step_delay_seconds": 0.6},
                "protocol": {"request_id": "req-smoke-execution", "attempt": 2},
            },
        ),
        _run(
            "run-smoke-agent",
            task_id="task-smoke-agent",
            next_dispatch_at="2026-04-15T11:55:00+00:00",
            dispatch_context={
                "state": "agent_queued",
                "execution_agent_id": "agent-smoke",
                "workflowPolicy": {"stepDelaySeconds": 0.8},
                "protocol": {"request_id": "req-smoke-agent", "attempt": 1},
            },
        ),
    ]

    service_a = _shared_sqlite_service(tmp_path, runtime_store=seeded_store)
    service_b_runtime = InMemoryStore()
    _replace_store(service_b_runtime, seeded_store)
    service_b = _shared_sqlite_service(tmp_path, runtime_store=service_b_runtime)

    try:
        now = datetime(2026, 4, 15, 12, 0, tzinfo=UTC)
        stale_claimed_at = (now - timedelta(minutes=10)).isoformat()
        stale_lease_expires_at = (now - timedelta(minutes=2)).isoformat()
        active_lease_expires_at = (now + timedelta(minutes=2)).isoformat()

        first_dispatch_claim = service_a.claim_due_workflow_runs(
            dispatcher_id="dispatcher-a",
            claimed_at=now.isoformat(),
            lease_expires_at=active_lease_expires_at,
            due_before=now.isoformat(),
            limit=10,
        )
        second_dispatch_claim = service_b.claim_due_workflow_runs(
            dispatcher_id="dispatcher-b",
            claimed_at=now.isoformat(),
            lease_expires_at=active_lease_expires_at,
            due_before=now.isoformat(),
            limit=10,
        )

        assert [item["id"] for item in first_dispatch_claim or []] == [
            "run-smoke-dispatch",
            "run-smoke-execution",
            "run-smoke-agent",
        ]
        assert second_dispatch_claim == []

        stale_run = service_a.get_workflow_run("run-smoke-dispatch")
        assert stale_run is not None
        stale_run["dispatcher_id"] = "dispatcher-a"
        stale_run["dispatch_claimed_at"] = stale_claimed_at
        stale_run["dispatch_lease_expires_at"] = stale_lease_expires_at
        assert service_a.persist_execution_state(workflow_run=stale_run) is True
        assert service_a.upsert_workflow_dispatch_job(
            "run-smoke-dispatch",
            available_at="2026-04-15T11:55:00+00:00",
            queued_at="2026-04-15T11:55:00+00:00",
            dispatcher_id="dispatcher-a",
            claimed_at=stale_claimed_at,
            lease_expires_at=stale_lease_expires_at,
        )

        dispatch_guard_summary = scheduler_guard_service.guard_dispatch_runtime(
            now=now,
            persistence=service_a,
        )
        reclaimed_dispatch = service_b.claim_due_workflow_runs(
            dispatcher_id="dispatcher-b",
            claimed_at=now.isoformat(),
            lease_expires_at=active_lease_expires_at,
            due_before=now.isoformat(),
            limit=10,
        )

        assert dispatch_guard_summary["reclaimed_run_claims"] >= 1
        assert dispatch_guard_summary["reclaimed_job_claims"] >= 1
        assert any(item["id"] == "run-smoke-dispatch" for item in reclaimed_dispatch or [])

        workflow_guard_summary = scheduler_guard_service.guard_workflow_execution_runtime(
            now=now,
            persistence=service_a,
        )
        first_execution_claim = service_a.claim_due_workflow_execution_jobs(
            worker_id="worker-a",
            claimed_at=now.isoformat(),
            lease_expires_at=active_lease_expires_at,
            due_before=now.isoformat(),
            limit=10,
        )
        second_execution_claim = service_b.claim_due_workflow_execution_jobs(
            worker_id="worker-b",
            claimed_at=now.isoformat(),
            lease_expires_at=active_lease_expires_at,
            due_before=now.isoformat(),
            limit=10,
        )

        assert workflow_guard_summary["repaired_missing_jobs"] >= 1
        assert [item["run_id"] for item in first_execution_claim or []] == ["run-smoke-execution"]
        assert second_execution_claim == []

        claimed_execution_job = service_a.get_workflow_execution_job("run-smoke-execution")
        assert claimed_execution_job is not None
        assert service_a.upsert_workflow_execution_job(
            "run-smoke-execution",
            available_at=claimed_execution_job["available_at"],
            queued_at=claimed_execution_job["created_at"],
            step_delay_seconds=claimed_execution_job.get("step_delay_seconds"),
            worker_id="worker-a",
            claimed_at=stale_claimed_at,
            lease_expires_at=stale_lease_expires_at,
            request_id=claimed_execution_job.get("request_id"),
            attempt=claimed_execution_job.get("attempt"),
            max_attempts=claimed_execution_job.get("max_attempts"),
        )

        workflow_reclaim_summary = scheduler_guard_service.guard_workflow_execution_runtime(
            now=now,
            persistence=service_a,
        )
        reclaimed_execution = service_b.claim_due_workflow_execution_jobs(
            worker_id="worker-b",
            claimed_at=now.isoformat(),
            lease_expires_at=active_lease_expires_at,
            due_before=now.isoformat(),
            limit=10,
        )

        assert workflow_reclaim_summary["reclaimed_claims"] >= 1
        assert [item["run_id"] for item in reclaimed_execution or []] == ["run-smoke-execution"]

        agent_guard_summary = scheduler_guard_service.guard_agent_execution_runtime(
            now=now,
            persistence=service_a,
        )
        first_agent_claim = service_a.claim_due_agent_execution_jobs(
            worker_id="agent-worker-a",
            claimed_at=now.isoformat(),
            lease_expires_at=active_lease_expires_at,
            due_before=now.isoformat(),
            limit=10,
        )
        second_agent_claim = service_b.claim_due_agent_execution_jobs(
            worker_id="agent-worker-b",
            claimed_at=now.isoformat(),
            lease_expires_at=active_lease_expires_at,
            due_before=now.isoformat(),
            limit=10,
        )

        assert agent_guard_summary["repaired_missing_jobs"] >= 1
        assert [item["run_id"] for item in first_agent_claim or []] == ["run-smoke-agent"]
        assert second_agent_claim == []

        claimed_agent_job = service_a.get_agent_execution_job("run-smoke-agent")
        assert claimed_agent_job is not None
        assert service_a.upsert_agent_execution_job(
            "run-smoke-agent",
            task_id=claimed_agent_job["task_id"],
            workflow_id=claimed_agent_job["workflow_id"],
            execution_agent_id=claimed_agent_job.get("execution_agent_id"),
            available_at=claimed_agent_job["available_at"],
            queued_at=claimed_agent_job["created_at"],
            step_delay_seconds=claimed_agent_job.get("step_delay_seconds"),
            worker_id="agent-worker-a",
            claimed_at=stale_claimed_at,
            lease_expires_at=stale_lease_expires_at,
            request_id=claimed_agent_job.get("request_id"),
            attempt=claimed_agent_job.get("attempt"),
            max_attempts=claimed_agent_job.get("max_attempts"),
        )

        agent_reclaim_summary = scheduler_guard_service.guard_agent_execution_runtime(
            now=now,
            persistence=service_a,
        )
        reclaimed_agent = service_b.claim_due_agent_execution_jobs(
            worker_id="agent-worker-b",
            claimed_at=now.isoformat(),
            lease_expires_at=active_lease_expires_at,
            due_before=now.isoformat(),
            limit=10,
        )

        assert agent_reclaim_summary["reclaimed_claims"] >= 1
        assert [item["run_id"] for item in reclaimed_agent or []] == ["run-smoke-agent"]
    finally:
        service_a.close()
        service_b.close()
