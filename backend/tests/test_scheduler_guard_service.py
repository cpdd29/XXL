from __future__ import annotations

from datetime import UTC, datetime, timedelta

import app.services.scheduler_guard_service as scheduler_guard_service_module
from app.services.scheduler_guard_service import SchedulerGuardService


def _iso_at(*, hours: int = 0, minutes: int = 0) -> str:
    return (datetime(2026, 4, 15, 12, 0, tzinfo=UTC) + timedelta(hours=hours, minutes=minutes)).isoformat()


class FakeSchedulerPersistence:
    def __init__(
        self,
        *,
        runs: list[dict] | None = None,
        tasks: list[dict] | None = None,
        dispatch_jobs: list[dict] | None = None,
        workflow_execution_jobs: list[dict] | None = None,
        agent_execution_jobs: list[dict] | None = None,
    ) -> None:
        self.enabled = True
        self.runs = {str(item.get("id") or ""): dict(item) for item in (runs or [])}
        self.tasks = {str(item.get("id") or ""): dict(item) for item in (tasks or [])}
        self.dispatch_jobs = {
            str(item.get("run_id") or ""): dict(item) for item in (dispatch_jobs or [])
        }
        self.workflow_execution_jobs = {
            str(item.get("run_id") or ""): dict(item) for item in (workflow_execution_jobs or [])
        }
        self.agent_execution_jobs = {
            str(item.get("run_id") or ""): dict(item) for item in (agent_execution_jobs or [])
        }

    def list_workflow_runs(self) -> list[dict]:
        return [dict(item) for item in self.runs.values()]

    def list_tasks(self) -> list[dict]:
        return [dict(item) for item in self.tasks.values()]

    def list_workflow_dispatch_jobs(self) -> list[dict]:
        return [dict(item) for item in self.dispatch_jobs.values()]

    def list_workflow_execution_jobs(self) -> list[dict]:
        return [dict(item) for item in self.workflow_execution_jobs.values()]

    def list_agent_execution_jobs(self) -> list[dict]:
        return [dict(item) for item in self.agent_execution_jobs.values()]

    def release_workflow_dispatch_job_claim(
        self,
        run_id: str,
        *,
        dispatcher_id: str,
        claimed_at: str | None = None,
    ) -> dict | None:
        job = self.dispatch_jobs.get(run_id)
        if job is None or str(job.get("dispatcher_id") or "") != dispatcher_id:
            return None
        if claimed_at is not None and str(job.get("claimed_at") or "") != str(claimed_at):
            return None
        job["dispatcher_id"] = None
        job["claimed_at"] = None
        job["lease_expires_at"] = None
        return dict(job)

    def release_workflow_run_claim(
        self,
        run_id: str,
        *,
        dispatcher_id: str,
    ) -> dict | None:
        run = self.runs.get(run_id)
        if run is None or str(run.get("dispatcher_id") or "") != dispatcher_id:
            return None
        run["dispatcher_id"] = None
        run["dispatch_claimed_at"] = None
        run["dispatch_lease_expires_at"] = None
        return dict(run)

    def delete_workflow_dispatch_job(
        self,
        run_id: str,
        *,
        dispatcher_id: str | None = None,
        claimed_at: str | None = None,
    ) -> bool:
        _ = (dispatcher_id, claimed_at)
        return self.dispatch_jobs.pop(run_id, None) is not None

    def release_workflow_execution_job_claim(
        self,
        run_id: str,
        *,
        worker_id: str,
        claimed_at: str | None = None,
    ) -> dict | None:
        job = self.workflow_execution_jobs.get(run_id)
        if job is None or str(job.get("worker_id") or "") != worker_id:
            return None
        if claimed_at is not None and str(job.get("claimed_at") or "") != str(claimed_at):
            return None
        job["worker_id"] = None
        job["claimed_at"] = None
        job["lease_expires_at"] = None
        return dict(job)

    def delete_workflow_execution_job(
        self,
        run_id: str,
        *,
        worker_id: str | None = None,
        claimed_at: str | None = None,
    ) -> bool:
        _ = (worker_id, claimed_at)
        return self.workflow_execution_jobs.pop(run_id, None) is not None

    def upsert_workflow_execution_job(
        self,
        run_id: str,
        *,
        available_at: str,
        queued_at: str,
        step_delay_seconds: float | None = None,
        **kwargs: object,
    ) -> dict:
        payload = {
            "run_id": run_id,
            "available_at": available_at,
            "created_at": queued_at,
            "updated_at": queued_at,
            "step_delay_seconds": step_delay_seconds,
            "worker_id": None,
            "claimed_at": None,
            "lease_expires_at": None,
        }
        payload.update(kwargs)
        self.workflow_execution_jobs[run_id] = dict(payload)
        return dict(payload)

    def release_agent_execution_job_claim(
        self,
        run_id: str,
        *,
        worker_id: str,
        claimed_at: str | None = None,
    ) -> dict | None:
        job = self.agent_execution_jobs.get(run_id)
        if job is None or str(job.get("worker_id") or "") != worker_id:
            return None
        if claimed_at is not None and str(job.get("claimed_at") or "") != str(claimed_at):
            return None
        job["worker_id"] = None
        job["claimed_at"] = None
        job["lease_expires_at"] = None
        return dict(job)

    def delete_agent_execution_job(
        self,
        run_id: str,
        *,
        worker_id: str | None = None,
        claimed_at: str | None = None,
    ) -> bool:
        _ = (worker_id, claimed_at)
        return self.agent_execution_jobs.pop(run_id, None) is not None

    def upsert_agent_execution_job(
        self,
        run_id: str,
        *,
        task_id: str,
        workflow_id: str,
        execution_agent_id: str | None,
        available_at: str,
        queued_at: str,
        step_delay_seconds: float | None = None,
        **kwargs: object,
    ) -> dict:
        payload = {
            "run_id": run_id,
            "task_id": task_id,
            "workflow_id": workflow_id,
            "execution_agent_id": execution_agent_id,
            "available_at": available_at,
            "created_at": queued_at,
            "updated_at": queued_at,
            "step_delay_seconds": step_delay_seconds,
            "worker_id": None,
            "claimed_at": None,
            "lease_expires_at": None,
        }
        payload.update(kwargs)
        self.agent_execution_jobs[run_id] = dict(payload)
        return dict(payload)


def test_guard_dispatch_runtime_reclaims_stale_claims_and_emits_audit(monkeypatch) -> None:
    now = datetime(2026, 4, 15, 12, 0, tzinfo=UTC)
    persistence = FakeSchedulerPersistence(
        runs=[
            {
                "id": "run-dispatch-stale",
                "task_id": "task-dispatch-stale",
                "status": "running",
                "dispatcher_id": "dispatcher-a",
                "dispatch_claimed_at": _iso_at(minutes=-15),
                "dispatch_lease_expires_at": _iso_at(minutes=-5),
                "dispatch_context": {},
            }
        ],
        dispatch_jobs=[
            {
                "run_id": "run-dispatch-stale",
                "dispatcher_id": "dispatcher-a",
                "claimed_at": _iso_at(minutes=-15),
                "lease_expires_at": _iso_at(minutes=-5),
                "available_at": _iso_at(minutes=-20),
            }
        ],
    )
    audits: list[dict] = []
    events: list[dict] = []

    monkeypatch.setattr(
        scheduler_guard_service_module,
        "append_control_plane_audit_log",
        lambda **kwargs: audits.append(kwargs),
    )
    monkeypatch.setattr(
        scheduler_guard_service_module,
        "append_realtime_event",
        lambda **kwargs: events.append(kwargs),
    )

    summary = SchedulerGuardService(persistence=persistence).guard_dispatch_runtime(
        now=now,
        persistence=persistence,
    )

    assert summary == {
        "reclaimed_run_claims": 1,
        "reclaimed_job_claims": 1,
        "deleted_orphan_jobs": 0,
    }
    assert persistence.runs["run-dispatch-stale"]["dispatcher_id"] is None
    assert persistence.dispatch_jobs["run-dispatch-stale"]["dispatcher_id"] is None
    assert {item["action"] for item in audits} == {
        "scheduler.dispatch_claim.reclaimed",
        "scheduler.run_claim.reclaimed",
    }
    assert len(events) == 2


def test_guard_workflow_execution_runtime_repairs_and_cleans_jobs(monkeypatch) -> None:
    now = datetime(2026, 4, 15, 12, 0, tzinfo=UTC)
    persistence = FakeSchedulerPersistence(
        runs=[
            {
                "id": "run-workflow-stale",
                "task_id": "task-1",
                "status": "running",
                "dispatch_context": {},
            },
            {
                "id": "run-workflow-repair",
                "task_id": "task-2",
                "workflow_id": "workflow-1",
                "status": "running",
                "updated_at": _iso_at(minutes=-1),
                "started_at": _iso_at(minutes=-3),
                "dispatch_context": {
                    "state": "dispatched",
                    "workflow_policy": {"step_delay_seconds": 1.25},
                    "protocol": {"request_id": "req-workflow-repair", "attempt": 2},
                },
            },
            {
                "id": "run-workflow-terminal",
                "task_id": "task-3",
                "status": "completed",
                "dispatch_context": {},
            },
        ],
        workflow_execution_jobs=[
            {
                "run_id": "run-workflow-stale",
                "worker_id": "worker-a",
                "claimed_at": _iso_at(minutes=-10),
                "lease_expires_at": _iso_at(minutes=-2),
                "available_at": _iso_at(minutes=-10),
            },
            {
                "run_id": "run-workflow-terminal",
                "worker_id": "worker-a",
                "claimed_at": _iso_at(minutes=-10),
                "lease_expires_at": _iso_at(minutes=-2),
                "available_at": _iso_at(minutes=-10),
            },
        ],
    )
    audits: list[dict] = []
    events: list[dict] = []

    monkeypatch.setattr(
        scheduler_guard_service_module,
        "append_control_plane_audit_log",
        lambda **kwargs: audits.append(kwargs),
    )
    monkeypatch.setattr(
        scheduler_guard_service_module,
        "append_realtime_event",
        lambda **kwargs: events.append(kwargs),
    )

    summary = SchedulerGuardService(persistence=persistence).guard_workflow_execution_runtime(
        now=now,
        persistence=persistence,
    )

    assert summary == {
        "reclaimed_claims": 1,
        "deleted_orphan_jobs": 1,
        "repaired_missing_jobs": 1,
    }
    repaired_job = persistence.workflow_execution_jobs["run-workflow-repair"]
    assert repaired_job["request_id"] == "req-workflow-repair"
    assert repaired_job["attempt"] == 2
    assert repaired_job["step_delay_seconds"] == 1.25
    assert "run-workflow-terminal" not in persistence.workflow_execution_jobs
    assert len(audits) == 3
    assert len(events) == 3


def test_guard_agent_execution_runtime_repairs_and_cleans_jobs(monkeypatch) -> None:
    now = datetime(2026, 4, 15, 12, 0, tzinfo=UTC)
    persistence = FakeSchedulerPersistence(
        tasks=[
            {"id": "task-agent-live", "status": "running"},
            {"id": "task-agent-repair", "status": "running"},
            {"id": "task-agent-terminal", "status": "completed"},
        ],
        runs=[
            {
                "id": "run-agent-stale",
                "task_id": "task-agent-live",
                "workflow_id": "workflow-1",
                "status": "running",
                "dispatch_context": {},
            },
            {
                "id": "run-agent-repair",
                "task_id": "task-agent-repair",
                "workflow_id": "workflow-1",
                "status": "running",
                "updated_at": _iso_at(minutes=-1),
                "dispatch_context": {
                    "state": "agent_queued",
                    "execution_agent_id": "agent-writer",
                    "workflowPolicy": {"stepDelaySeconds": 0.75},
                    "protocol": {"request_id": "req-agent-repair", "attempt": 3},
                },
            },
            {
                "id": "run-agent-terminal",
                "task_id": "task-agent-terminal",
                "workflow_id": "workflow-1",
                "status": "running",
                "dispatch_context": {},
            },
        ],
        agent_execution_jobs=[
            {
                "run_id": "run-agent-stale",
                "task_id": "task-agent-live",
                "workflow_id": "workflow-1",
                "execution_agent_id": "agent-search",
                "worker_id": "agent-worker-a",
                "claimed_at": _iso_at(minutes=-10),
                "lease_expires_at": _iso_at(minutes=-2),
                "available_at": _iso_at(minutes=-10),
            },
            {
                "run_id": "run-agent-terminal",
                "task_id": "task-agent-terminal",
                "workflow_id": "workflow-1",
                "execution_agent_id": "agent-search",
                "worker_id": "agent-worker-a",
                "claimed_at": _iso_at(minutes=-10),
                "lease_expires_at": _iso_at(minutes=-2),
                "available_at": _iso_at(minutes=-10),
            },
        ],
    )
    audits: list[dict] = []
    events: list[dict] = []

    monkeypatch.setattr(
        scheduler_guard_service_module,
        "append_control_plane_audit_log",
        lambda **kwargs: audits.append(kwargs),
    )
    monkeypatch.setattr(
        scheduler_guard_service_module,
        "append_realtime_event",
        lambda **kwargs: events.append(kwargs),
    )

    summary = SchedulerGuardService(persistence=persistence).guard_agent_execution_runtime(
        now=now,
        persistence=persistence,
    )

    assert summary == {
        "reclaimed_claims": 1,
        "deleted_orphan_jobs": 1,
        "repaired_missing_jobs": 1,
    }
    repaired_job = persistence.agent_execution_jobs["run-agent-repair"]
    assert repaired_job["task_id"] == "task-agent-repair"
    assert repaired_job["execution_agent_id"] == "agent-writer"
    assert repaired_job["request_id"] == "req-agent-repair"
    assert repaired_job["attempt"] == 3
    assert repaired_job["step_delay_seconds"] == 0.75
    assert "run-agent-terminal" not in persistence.agent_execution_jobs
    assert len(audits) == 3
    assert len(events) == 3
