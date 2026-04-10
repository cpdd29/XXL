from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.services.store import store
from app.services.workflow_dispatch_poller_service import WorkflowDispatchPollerService
from app.services.workflow_dispatcher_service import DEFAULT_DISPATCH_FAILURE_RETRY_DELAY_SECONDS


class FakeDispatcher:
    def __init__(self, *, publish_result: bool = True, process_error: Exception | None = None) -> None:
        self.publish_result = publish_result
        self.process_error = process_error
        self.dispatcher_id = "dispatcher-test"
        self.claimed: list[str] = []
        self.published: list[tuple[str, float]] = []
        self.processed: list[tuple[str, float]] = []
        self.released: list[str] = []

    def try_acquire_schedule_slot(self, run_id: str) -> dict | None:
        self.claimed.append(run_id)
        for run in store.workflow_runs:
            if run["id"] == run_id:
                run["dispatcher_id"] = self.dispatcher_id
                return run
        return {"id": run_id, "status": "running"}

    def dispatch_tick(self, run_id: str, *, step_delay: float) -> bool:
        self.published.append((run_id, step_delay))
        return self.publish_result

    def process_tick(self, run_id: str, *, step_delay: float) -> dict:
        if self.process_error is not None:
            raise self.process_error
        self.processed.append((run_id, step_delay))
        return {"id": run_id, "status": "running"}

    def release_run_claim(self, run_id: str) -> None:
        self.released.append(run_id)


class FakePersistence:
    def __init__(
        self,
        runs: list[dict] | None = None,
        *,
        claimed_runs: list[dict] | None = None,
        claimed_jobs: list[dict] | None = None,
    ) -> None:
        self.runs = runs or []
        self.claimed_runs = claimed_runs
        self.claimed_jobs = claimed_jobs
        self.claim_calls: list[dict[str, object]] = []
        self.job_claim_calls: list[dict[str, object]] = []
        self.job_release_calls: list[dict[str, object]] = []
        self.job_delete_calls: list[dict[str, object]] = []
        self.database_runs: dict[str, dict] = {}

    def list_due_workflow_runs(
        self,
        *,
        due_before: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        items = list(self.runs)
        if limit is not None:
            items = items[:limit]
        return [store.clone(run) for run in items]

    def claim_due_workflow_runs(
        self,
        *,
        dispatcher_id: str,
        claimed_at: str,
        lease_expires_at: str,
        due_before: str | None = None,
        limit: int | None = None,
    ) -> list[dict] | None:
        self.claim_calls.append(
            {
                "dispatcher_id": dispatcher_id,
                "claimed_at": claimed_at,
                "lease_expires_at": lease_expires_at,
                "due_before": due_before,
                "limit": limit,
            }
        )
        if self.claimed_runs is None:
            return None
        items = list(self.claimed_runs)
        if limit is not None:
            items = items[:limit]
        return [store.clone(run) for run in items]

    def claim_due_workflow_dispatch_jobs(
        self,
        *,
        dispatcher_id: str,
        claimed_at: str,
        lease_expires_at: str,
        due_before: str | None = None,
        limit: int | None = None,
    ) -> list[dict] | None:
        self.job_claim_calls.append(
            {
                "dispatcher_id": dispatcher_id,
                "claimed_at": claimed_at,
                "lease_expires_at": lease_expires_at,
                "due_before": due_before,
                "limit": limit,
            }
        )
        if self.claimed_jobs is None:
            return None
        items = list(self.claimed_jobs)
        if limit is not None:
            items = items[:limit]
        return [store.clone(job) for job in items]

    def release_workflow_dispatch_job_claim(
        self,
        run_id: str,
        *,
        dispatcher_id: str,
        claimed_at: str | None = None,
    ) -> dict:
        self.job_release_calls.append(
            {
                "run_id": run_id,
                "dispatcher_id": dispatcher_id,
                "claimed_at": claimed_at,
            }
        )
        return {"run_id": run_id}

    def delete_workflow_dispatch_job(
        self,
        run_id: str,
        *,
        dispatcher_id: str | None = None,
        claimed_at: str | None = None,
    ) -> bool:
        self.job_delete_calls.append(
            {
                "run_id": run_id,
                "dispatcher_id": dispatcher_id,
                "claimed_at": claimed_at,
            }
        )
        return True

    def get_workflow_run(self, run_id: str) -> dict | None:
        run = self.database_runs.get(run_id)
        if run is None:
            return None
        return store.clone(run)


class RepairingFakePersistence(FakePersistence):
    def __init__(
        self,
        *,
        database_runs: list[dict],
        dispatch_jobs: list[dict] | None = None,
    ) -> None:
        super().__init__(runs=database_runs, claimed_jobs=[])
        self.database_runs = {
            str(run.get("id") or ""): store.clone(run) for run in database_runs
        }
        self.dispatch_jobs = {
            str(job.get("run_id") or ""): store.clone(job) for job in (dispatch_jobs or [])
        }
        self.upsert_calls: list[dict[str, object]] = []

    def claim_due_workflow_dispatch_jobs(
        self,
        *,
        dispatcher_id: str,
        claimed_at: str,
        lease_expires_at: str,
        due_before: str | None = None,
        limit: int | None = None,
    ) -> list[dict] | None:
        self.job_claim_calls.append(
            {
                "dispatcher_id": dispatcher_id,
                "claimed_at": claimed_at,
                "lease_expires_at": lease_expires_at,
                "due_before": due_before,
                "limit": limit,
            }
        )
        if due_before is None:
            return []

        deadline = datetime.fromisoformat(due_before)
        claimed_jobs: list[dict] = []
        for job in sorted(
            self.dispatch_jobs.values(),
            key=lambda item: (str(item.get("available_at") or ""), str(item.get("run_id") or "")),
        ):
            available_at = str(job.get("available_at") or "").strip()
            if not available_at:
                continue
            available_at_dt = datetime.fromisoformat(available_at)
            if available_at_dt > deadline:
                continue

            claimed_job = store.clone(job)
            claimed_job["dispatcher_id"] = dispatcher_id
            claimed_job["claimed_at"] = claimed_at
            claimed_job["lease_expires_at"] = lease_expires_at
            claimed_job["dispatch_claimed_at"] = claimed_at
            claimed_job["dispatch_lease_expires_at"] = lease_expires_at
            self.dispatch_jobs[str(claimed_job["run_id"])] = store.clone(claimed_job)
            claimed_jobs.append(claimed_job)
            if limit is not None and len(claimed_jobs) >= limit:
                break

        return claimed_jobs

    def get_workflow_dispatch_job(self, run_id: str) -> dict | None:
        job = self.dispatch_jobs.get(run_id)
        if job is None:
            return None
        return store.clone(job)

    def upsert_workflow_dispatch_job(
        self,
        run_id: str,
        *,
        available_at: str,
        step_delay_seconds: float | None = None,
        dispatcher_id: str | None = None,
        claimed_at: str | None = None,
        lease_expires_at: str | None = None,
        **kwargs: object,
    ) -> dict:
        payload_for_assert = {
            "run_id": run_id,
            "available_at": available_at,
            "step_delay_seconds": step_delay_seconds,
            "dispatcher_id": dispatcher_id,
            "claimed_at": claimed_at,
            "lease_expires_at": lease_expires_at,
        }
        for key in (
            "request_id",
            "correlation_id",
            "idempotency_key",
            "attempt",
            "max_attempts",
        ):
            if kwargs.get(key) is not None:
                payload_for_assert[key] = kwargs.get(key)
        self.upsert_calls.append(payload_for_assert)
        payload = _dispatch_job(
            run_id,
            available_at=available_at,
            step_delay_seconds=step_delay_seconds,
            dispatcher_id=str(dispatcher_id or ""),
            claimed_at=claimed_at,
            lease_expires_at=lease_expires_at,
        )
        self.dispatch_jobs[run_id] = store.clone(payload)
        return payload


class FakeScheduler:
    def __init__(self, *, timer_run_ids: set[str] | None = None) -> None:
        self.cancelled: list[str] = []
        self.deferred: list[tuple[str, float, float | None, str | None]] = []
        self.timer_run_ids = timer_run_ids if timer_run_ids is not None else set()

    def cancel(self, run_id: str) -> None:
        self.cancelled.append(run_id)

    def has_timer(self, run_id: str) -> bool:
        return run_id in self.timer_run_ids

    def defer(
        self,
        run_id: str,
        *,
        delay: float,
        step_delay: float | None = None,
        dispatcher_id: str | None = None,
    ) -> dict:
        self.deferred.append((run_id, delay, step_delay, dispatcher_id))
        return {"id": run_id}


def _workflow_run(
    run_id: str,
    *,
    status: str = "running",
    next_dispatch_at: str | None = None,
    dispatcher_id: str | None = None,
    dispatch_lease_expires_at: str | None = None,
) -> dict:
    created_at = "2026-04-03T15:00:00+00:00"
    return {
        "id": run_id,
        "workflow_id": "workflow-1",
        "workflow_name": "调度工作流",
        "task_id": f"task-{run_id}",
        "trigger": "message",
        "intent": "search",
        "status": status,
        "created_at": created_at,
        "updated_at": created_at,
        "started_at": created_at,
        "completed_at": None,
        "next_dispatch_at": next_dispatch_at,
        "dispatcher_id": dispatcher_id,
        "dispatch_claimed_at": created_at if dispatcher_id else None,
        "dispatch_lease_expires_at": dispatch_lease_expires_at,
        "current_stage": "执行节点",
        "active_edges": [],
        "nodes": [],
        "logs": [],
        "memory_hits": 0,
        "warnings": [],
    }


def _dispatch_job(
    run_id: str,
    *,
    available_at: str,
    step_delay_seconds: float | None = None,
    dispatcher_id: str = "dispatcher-test",
    claimed_at: str | None = "2026-04-03T15:00:00+00:00",
    lease_expires_at: str | None = "2026-04-03T15:00:30+00:00",
) -> dict:
    return {
        "run_id": run_id,
        "available_at": available_at,
        "step_delay_seconds": step_delay_seconds,
        "dispatcher_id": dispatcher_id,
        "dispatch_claimed_at": claimed_at,
        "dispatch_lease_expires_at": lease_expires_at,
        "claimed_at": claimed_at,
        "lease_expires_at": lease_expires_at,
        "created_at": "2026-04-03T14:59:59+00:00",
        "updated_at": claimed_at or "2026-04-03T14:59:59+00:00",
    }


def test_workflow_dispatch_poller_polls_scheduled_workflows(monkeypatch) -> None:
    fixed_now = datetime(2026, 4, 4, 12, 0, 30, tzinfo=UTC)
    called_at: list[datetime] = []

    monkeypatch.setattr("app.services.workflow_dispatch_poller_service._utc_now", lambda: fixed_now)
    monkeypatch.setattr(
        "app.services.workflow_service.poll_scheduled_workflows",
        lambda *, now: called_at.append(now) or {"triggered": 1},
    )

    service = WorkflowDispatchPollerService(
        dispatcher=FakeDispatcher(),
        persistence=FakePersistence(),
        scheduler=FakeScheduler(),
        poll_interval_seconds=0.1,
    )

    summary = service.poll_once()

    assert called_at == [fixed_now]
    assert summary == {
        "dispatched": 0,
        "skipped_claimed": 0,
        "skipped_scheduled": 0,
        "skipped_terminal": 0,
    }


def test_workflow_dispatch_poller_prefers_database_run_over_stale_runtime_cache(monkeypatch) -> None:
    fixed_now = datetime(2026, 4, 4, 12, 0, 30, tzinfo=UTC)
    dispatcher = FakeDispatcher()
    persistence = FakePersistence(
        claimed_jobs=[
            _dispatch_job(
                "run-db-claimed",
                available_at=(fixed_now - timedelta(seconds=1)).isoformat(),
            )
        ]
    )
    scheduler = FakeScheduler()
    service = WorkflowDispatchPollerService(
        dispatcher=dispatcher,
        persistence=persistence,
        scheduler=scheduler,
        poll_interval_seconds=0.1,
    )

    monkeypatch.setattr("app.services.workflow_dispatch_poller_service._utc_now", lambda: fixed_now)

    store.workflow_runs.insert(
        0,
        _workflow_run(
            "run-db-claimed",
            next_dispatch_at=(fixed_now - timedelta(seconds=1)).isoformat(),
        ),
    )
    persistence.database_runs["run-db-claimed"] = {
        **_workflow_run(
            "run-db-claimed",
            next_dispatch_at=(fixed_now - timedelta(seconds=1)).isoformat(),
        ),
        "dispatcher_id": "dispatcher-other",
        "dispatch_claimed_at": fixed_now.isoformat(),
        "dispatch_lease_expires_at": (fixed_now + timedelta(seconds=30)).isoformat(),
    }

    summary = service.poll_once()

    assert summary == {
        "dispatched": 0,
        "skipped_claimed": 1,
        "skipped_scheduled": 0,
        "skipped_terminal": 0,
    }
    assert dispatcher.claimed == []
    assert dispatcher.published == []
    assert persistence.job_release_calls == [
        {
            "run_id": "run-db-claimed",
            "dispatcher_id": "dispatcher-test",
            "claimed_at": "2026-04-03T15:00:00+00:00",
        }
    ]


def test_workflow_dispatch_poller_dispatches_due_store_run(monkeypatch) -> None:
    fixed_now = datetime(2026, 4, 3, 15, 0, 0, tzinfo=UTC)
    dispatcher = FakeDispatcher()
    scheduler = FakeScheduler()
    run = _workflow_run(
        "run-due",
        next_dispatch_at=(fixed_now - timedelta(seconds=1)).isoformat(),
    )
    store.workflow_runs.insert(0, run)
    monkeypatch.setattr("app.services.workflow_dispatch_poller_service._utc_now", lambda: fixed_now)

    service = WorkflowDispatchPollerService(
        dispatcher=dispatcher,
        persistence=FakePersistence(),
        scheduler=scheduler,
        poll_interval_seconds=0.1,
    )

    summary = service.poll_once(step_delay=0.75)

    assert summary == {
        "dispatched": 1,
        "skipped_claimed": 0,
        "skipped_scheduled": 0,
        "skipped_terminal": 0,
    }
    assert dispatcher.published == [("run-due", 0.75)]
    assert dispatcher.processed == []
    assert scheduler.cancelled == []


def test_workflow_dispatch_poller_falls_back_to_local_process_when_publish_fails(monkeypatch) -> None:
    fixed_now = datetime(2026, 4, 3, 15, 0, 0, tzinfo=UTC)
    dispatcher = FakeDispatcher(publish_result=False)
    scheduler = FakeScheduler()
    run = _workflow_run(
        "run-process",
        next_dispatch_at=(fixed_now - timedelta(seconds=1)).isoformat(),
    )
    store.workflow_runs.insert(0, run)
    monkeypatch.setattr("app.services.workflow_dispatch_poller_service._utc_now", lambda: fixed_now)

    service = WorkflowDispatchPollerService(
        dispatcher=dispatcher,
        persistence=FakePersistence(),
        scheduler=scheduler,
        poll_interval_seconds=0.1,
    )

    summary = service.poll_once(step_delay=0.8)

    assert summary["dispatched"] == 1
    assert summary["skipped_scheduled"] == 0
    assert dispatcher.published == [("run-process", 0.8)]
    assert dispatcher.processed == [("run-process", 0.8)]


def test_workflow_dispatch_poller_skips_database_run_with_active_lease(monkeypatch) -> None:
    fixed_now = datetime(2026, 4, 3, 15, 0, 0, tzinfo=UTC)
    dispatcher = FakeDispatcher()
    scheduler = FakeScheduler()
    run = _workflow_run(
        "run-claimed",
        next_dispatch_at=(fixed_now - timedelta(seconds=1)).isoformat(),
        dispatcher_id="dispatcher-other",
        dispatch_lease_expires_at=(fixed_now + timedelta(seconds=20)).isoformat(),
    )
    monkeypatch.setattr("app.services.workflow_dispatch_poller_service._utc_now", lambda: fixed_now)

    service = WorkflowDispatchPollerService(
        dispatcher=dispatcher,
        persistence=FakePersistence([run]),
        scheduler=scheduler,
        poll_interval_seconds=0.1,
    )

    summary = service.poll_once(step_delay=0.6)

    assert summary == {
        "dispatched": 0,
        "skipped_claimed": 1,
        "skipped_scheduled": 0,
        "skipped_terminal": 0,
    }
    assert dispatcher.claimed == []
    assert dispatcher.published == []
    assert dispatcher.processed == []


def test_workflow_dispatch_poller_processes_database_claimed_run_without_reacquiring(
    monkeypatch,
) -> None:
    fixed_now = datetime(2026, 4, 3, 15, 0, 0, tzinfo=UTC)
    dispatcher = FakeDispatcher(publish_result=False)
    scheduler = FakeScheduler()
    run = _workflow_run(
        "run-db-claimed",
        next_dispatch_at=(fixed_now - timedelta(seconds=1)).isoformat(),
        dispatcher_id="dispatcher-test",
        dispatch_lease_expires_at=(fixed_now + timedelta(seconds=20)).isoformat(),
    )
    persistence = FakePersistence(claimed_runs=[run])
    monkeypatch.setattr("app.services.workflow_dispatch_poller_service._utc_now", lambda: fixed_now)

    service = WorkflowDispatchPollerService(
        dispatcher=dispatcher,
        persistence=persistence,
        scheduler=scheduler,
        poll_interval_seconds=0.1,
    )

    summary = service.poll_once(step_delay=0.65)

    assert summary == {
        "dispatched": 1,
        "skipped_claimed": 0,
        "skipped_scheduled": 0,
        "skipped_terminal": 0,
    }
    assert dispatcher.claimed == []
    assert dispatcher.published == [("run-db-claimed", 0.65)]
    assert dispatcher.processed == [("run-db-claimed", 0.65)]
    assert persistence.claim_calls[0]["dispatcher_id"] == "dispatcher-test"
    assert persistence.claim_calls[0]["due_before"] == fixed_now.isoformat()


def test_workflow_dispatch_poller_prefers_persistent_dispatch_jobs(monkeypatch) -> None:
    fixed_now = datetime(2026, 4, 3, 15, 0, 0, tzinfo=UTC)
    dispatcher = FakeDispatcher()
    scheduler = FakeScheduler()
    run = _workflow_run(
        "run-job",
        next_dispatch_at=(fixed_now - timedelta(seconds=1)).isoformat(),
        dispatcher_id="dispatcher-test",
        dispatch_lease_expires_at=(fixed_now + timedelta(seconds=20)).isoformat(),
    )
    store.workflow_runs.insert(0, run)
    persistence = FakePersistence(
        claimed_jobs=[
            _dispatch_job(
                "run-job",
                available_at=(fixed_now - timedelta(seconds=1)).isoformat(),
                claimed_at=fixed_now.isoformat(),
                lease_expires_at=(fixed_now + timedelta(seconds=30)).isoformat(),
            )
        ]
    )
    monkeypatch.setattr("app.services.workflow_dispatch_poller_service._utc_now", lambda: fixed_now)

    service = WorkflowDispatchPollerService(
        dispatcher=dispatcher,
        persistence=persistence,
        scheduler=scheduler,
        poll_interval_seconds=0.1,
    )

    summary = service.poll_once(step_delay=0.7)

    assert summary == {
        "dispatched": 1,
        "skipped_claimed": 0,
        "skipped_scheduled": 0,
        "skipped_terminal": 0,
    }
    assert dispatcher.claimed == []
    assert dispatcher.published == [("run-job", 0.7)]
    assert persistence.job_claim_calls[0]["dispatcher_id"] == "dispatcher-test"
    assert persistence.job_claim_calls[0]["due_before"] == fixed_now.isoformat()
    assert persistence.job_delete_calls == []
    assert persistence.job_release_calls == []


def test_workflow_dispatch_poller_uses_job_specific_step_delay(monkeypatch) -> None:
    fixed_now = datetime(2026, 4, 3, 15, 0, 0, tzinfo=UTC)
    dispatcher = FakeDispatcher()
    scheduler = FakeScheduler()
    run = _workflow_run(
        "run-job-step-delay",
        next_dispatch_at=(fixed_now - timedelta(seconds=1)).isoformat(),
    )
    store.workflow_runs.insert(0, run)
    persistence = FakePersistence(
        claimed_jobs=[
            _dispatch_job(
                "run-job-step-delay",
                available_at=(fixed_now - timedelta(seconds=1)).isoformat(),
                step_delay_seconds=1.25,
                claimed_at=fixed_now.isoformat(),
                lease_expires_at=(fixed_now + timedelta(seconds=30)).isoformat(),
            )
        ]
    )
    monkeypatch.setattr("app.services.workflow_dispatch_poller_service._utc_now", lambda: fixed_now)

    service = WorkflowDispatchPollerService(
        dispatcher=dispatcher,
        persistence=persistence,
        scheduler=scheduler,
        poll_interval_seconds=0.1,
    )

    summary = service.poll_once(step_delay=0.7)

    assert summary["dispatched"] == 1
    assert dispatcher.published == [("run-job-step-delay", 1.25)]


def test_workflow_dispatch_poller_releases_persistent_dispatch_job_after_local_process(
    monkeypatch,
) -> None:
    fixed_now = datetime(2026, 4, 3, 15, 0, 0, tzinfo=UTC)
    dispatcher = FakeDispatcher(publish_result=False)
    scheduler = FakeScheduler()
    run = _workflow_run(
        "run-job-local",
        next_dispatch_at=(fixed_now - timedelta(seconds=1)).isoformat(),
        dispatcher_id="dispatcher-test",
        dispatch_lease_expires_at=(fixed_now + timedelta(seconds=20)).isoformat(),
    )
    store.workflow_runs.insert(0, run)
    persistence = FakePersistence(
        claimed_jobs=[
            _dispatch_job(
                "run-job-local",
                available_at=(fixed_now - timedelta(seconds=1)).isoformat(),
                claimed_at=fixed_now.isoformat(),
                lease_expires_at=(fixed_now + timedelta(seconds=30)).isoformat(),
            )
        ]
    )
    monkeypatch.setattr("app.services.workflow_dispatch_poller_service._utc_now", lambda: fixed_now)

    service = WorkflowDispatchPollerService(
        dispatcher=dispatcher,
        persistence=persistence,
        scheduler=scheduler,
        poll_interval_seconds=0.1,
    )

    summary = service.poll_once(step_delay=0.7)

    assert summary == {
        "dispatched": 1,
        "skipped_claimed": 0,
        "skipped_scheduled": 0,
        "skipped_terminal": 0,
    }
    assert dispatcher.published == [("run-job-local", 0.7)]
    assert dispatcher.processed == [("run-job-local", 0.7)]
    assert persistence.job_release_calls == [
        {
            "run_id": "run-job-local",
            "dispatcher_id": "dispatcher-test",
            "claimed_at": fixed_now.isoformat(),
        }
    ]
    assert persistence.job_delete_calls == []


def test_workflow_dispatch_poller_releases_persistent_dispatch_job_when_run_claim_is_blocked(
    monkeypatch,
) -> None:
    fixed_now = datetime(2026, 4, 3, 15, 0, 0, tzinfo=UTC)
    dispatcher = FakeDispatcher()
    scheduler = FakeScheduler()
    run = _workflow_run(
        "run-job-claimed",
        next_dispatch_at=(fixed_now - timedelta(seconds=1)).isoformat(),
        dispatcher_id="dispatcher-other",
        dispatch_lease_expires_at=(fixed_now + timedelta(seconds=20)).isoformat(),
    )
    store.workflow_runs.insert(0, run)
    persistence = FakePersistence(
        claimed_jobs=[
            _dispatch_job(
                "run-job-claimed",
                available_at=(fixed_now - timedelta(seconds=1)).isoformat(),
                claimed_at=fixed_now.isoformat(),
                lease_expires_at=(fixed_now + timedelta(seconds=30)).isoformat(),
            )
        ]
    )
    monkeypatch.setattr("app.services.workflow_dispatch_poller_service._utc_now", lambda: fixed_now)

    service = WorkflowDispatchPollerService(
        dispatcher=dispatcher,
        persistence=persistence,
        scheduler=scheduler,
        poll_interval_seconds=0.1,
    )

    summary = service.poll_once(step_delay=0.7)

    assert summary == {
        "dispatched": 0,
        "skipped_claimed": 1,
        "skipped_scheduled": 0,
        "skipped_terminal": 0,
    }
    assert dispatcher.published == []
    assert persistence.job_release_calls == [
        {
            "run_id": "run-job-claimed",
            "dispatcher_id": "dispatcher-test",
            "claimed_at": fixed_now.isoformat(),
        }
    ]


def test_workflow_dispatch_poller_claims_and_dispatches_due_run_even_when_job_is_missing(
    monkeypatch,
) -> None:
    fixed_now = datetime(2026, 4, 3, 15, 0, 0, tzinfo=UTC)
    dispatcher = FakeDispatcher()
    scheduler = FakeScheduler()
    due_run = _workflow_run(
        "run-orphan-due",
        next_dispatch_at=(fixed_now - timedelta(seconds=1)).isoformat(),
    )
    due_run["dispatch_context"] = {
        "protocol": {
            "request_id": "req-orphan-due",
            "correlation_id": "req-orphan-due",
            "idempotency_key": "workflow.execution.request:run-orphan-due",
            "attempt": 2,
            "max_attempts": 6,
        }
    }
    persistence = RepairingFakePersistence(database_runs=[due_run], dispatch_jobs=[])
    monkeypatch.setattr("app.services.workflow_dispatch_poller_service._utc_now", lambda: fixed_now)

    service = WorkflowDispatchPollerService(
        dispatcher=dispatcher,
        persistence=persistence,
        scheduler=scheduler,
        poll_interval_seconds=0.1,
    )

    summary = service.poll_once(step_delay=0.55)

    assert summary == {
        "dispatched": 1,
        "skipped_claimed": 0,
        "skipped_scheduled": 0,
        "skipped_terminal": 0,
    }
    assert persistence.upsert_calls == [
        {
            "run_id": "run-orphan-due",
            "available_at": due_run["next_dispatch_at"],
            "step_delay_seconds": 0.55,
            "dispatcher_id": None,
            "claimed_at": None,
            "lease_expires_at": None,
            "request_id": "req-orphan-due",
            "correlation_id": "req-orphan-due",
            "idempotency_key": "workflow.execution.request:run-orphan-due",
            "attempt": 2,
            "max_attempts": 6,
        }
    ]
    assert dispatcher.claimed == ["run-orphan-due"]
    assert dispatcher.published == [("run-orphan-due", 0.55)]
    assert persistence.job_release_calls == []
    assert persistence.job_delete_calls == []


def test_workflow_dispatch_poller_repairs_mismatched_job_and_dispatches_due_run_in_same_poll(
    monkeypatch,
) -> None:
    fixed_now = datetime(2026, 4, 3, 15, 0, 0, tzinfo=UTC)
    dispatcher = FakeDispatcher()
    scheduler = FakeScheduler()
    due_run = _workflow_run(
        "run-mismatched-due",
        next_dispatch_at=(fixed_now - timedelta(seconds=1)).isoformat(),
    )
    persistence = RepairingFakePersistence(
        database_runs=[due_run],
        dispatch_jobs=[
            _dispatch_job(
                "run-mismatched-due",
                available_at=(fixed_now + timedelta(seconds=10)).isoformat(),
                step_delay_seconds=1.4,
                claimed_at=None,
                lease_expires_at=None,
            )
        ],
    )
    monkeypatch.setattr("app.services.workflow_dispatch_poller_service._utc_now", lambda: fixed_now)

    service = WorkflowDispatchPollerService(
        dispatcher=dispatcher,
        persistence=persistence,
        scheduler=scheduler,
        poll_interval_seconds=0.1,
    )

    summary = service.poll_once(step_delay=0.8)

    assert summary == {
        "dispatched": 1,
        "skipped_claimed": 0,
        "skipped_scheduled": 0,
        "skipped_terminal": 0,
    }
    assert persistence.upsert_calls == [
        {
            "run_id": "run-mismatched-due",
            "available_at": due_run["next_dispatch_at"],
            "step_delay_seconds": 1.4,
            "dispatcher_id": None,
            "claimed_at": None,
            "lease_expires_at": None,
            "attempt": 1,
        }
    ]
    assert dispatcher.claimed == ["run-mismatched-due"]
    assert dispatcher.published == [("run-mismatched-due", 1.4)]
    assert dispatcher.processed == []
    assert persistence.job_release_calls == []
    assert persistence.job_delete_calls == []


def test_workflow_dispatch_poller_skips_run_with_existing_local_timer(monkeypatch) -> None:
    fixed_now = datetime(2026, 4, 3, 15, 0, 0, tzinfo=UTC)
    dispatcher = FakeDispatcher()
    scheduler = FakeScheduler(timer_run_ids={"run-local-timer"})
    run = _workflow_run(
        "run-local-timer",
        next_dispatch_at=(fixed_now - timedelta(seconds=1)).isoformat(),
    )
    store.workflow_runs.insert(0, run)
    monkeypatch.setattr("app.services.workflow_dispatch_poller_service._utc_now", lambda: fixed_now)

    service = WorkflowDispatchPollerService(
        dispatcher=dispatcher,
        persistence=FakePersistence(),
        scheduler=scheduler,
        poll_interval_seconds=0.1,
    )

    summary = service.poll_once(step_delay=0.75)

    assert summary == {
        "dispatched": 0,
        "skipped_claimed": 0,
        "skipped_scheduled": 1,
        "skipped_terminal": 0,
    }
    assert dispatcher.claimed == []
    assert dispatcher.published == []
    assert dispatcher.processed == []


def test_workflow_dispatch_poller_background_loop_runs_once(monkeypatch) -> None:
    dispatcher = FakeDispatcher()
    service = WorkflowDispatchPollerService(
        dispatcher=dispatcher,
        persistence=FakePersistence(),
        scheduler=FakeScheduler(),
        poll_interval_seconds=0.1,
    )
    iterations: list[str] = []

    def _poll_once(*, step_delay: float = 0.0) -> dict[str, int]:
        _ = step_delay
        iterations.append("tick")
        service._stop_event.set()
        return {
            "dispatched": 0,
            "skipped_claimed": 0,
            "skipped_scheduled": 0,
            "skipped_terminal": 0,
        }

    monkeypatch.setattr(service, "poll_once", _poll_once)

    service.start()

    thread = service._thread
    assert thread is not None
    thread.join(timeout=1.0)
    service.stop()

    assert iterations == ["tick"]


def test_workflow_dispatch_poller_defers_failed_local_process(monkeypatch) -> None:
    fixed_now = datetime(2026, 4, 3, 15, 0, 0, tzinfo=UTC)
    dispatcher = FakeDispatcher(
        publish_result=False,
        process_error=RuntimeError("local process failed"),
    )
    scheduler = FakeScheduler()
    run = _workflow_run(
        "run-failed-process",
        next_dispatch_at=(fixed_now - timedelta(seconds=1)).isoformat(),
    )
    store.workflow_runs.insert(0, run)
    monkeypatch.setattr("app.services.workflow_dispatch_poller_service._utc_now", lambda: fixed_now)

    service = WorkflowDispatchPollerService(
        dispatcher=dispatcher,
        persistence=FakePersistence(),
        scheduler=scheduler,
        poll_interval_seconds=0.1,
    )

    summary = service.poll_once(step_delay=0.75)

    assert summary == {
        "dispatched": 0,
        "skipped_claimed": 0,
        "skipped_scheduled": 0,
        "skipped_terminal": 0,
    }
    assert dispatcher.published == [("run-failed-process", 0.75)]
    assert scheduler.deferred == [
        (
            "run-failed-process",
            DEFAULT_DISPATCH_FAILURE_RETRY_DELAY_SECONDS,
            0.75,
            "dispatcher-test",
        )
    ]
    assert dispatcher.released == ["run-failed-process"]


def test_workflow_dispatch_poller_execution_publish_failure_falls_back_to_local_process(
    monkeypatch,
) -> None:
    if "dispatch_execution" not in WorkflowDispatchPollerService._poll_due_runs.__code__.co_names:
        pytest.skip("execution publish path is not enabled in this branch")

    fixed_now = datetime(2026, 4, 3, 15, 0, 0, tzinfo=UTC)

    class ExecutionDispatcher(FakeDispatcher):
        def __init__(self) -> None:
            super().__init__(publish_result=False)
            self.execution_published: list[tuple[str, float]] = []

        def dispatch_execution(self, run_id: str, *, step_delay: float) -> bool:
            self.execution_published.append((run_id, step_delay))
            return False

    dispatcher = ExecutionDispatcher()
    scheduler = FakeScheduler()
    run = _workflow_run(
        "run-execution-fallback",
        next_dispatch_at=(fixed_now - timedelta(seconds=1)).isoformat(),
    )
    store.workflow_runs.insert(0, run)
    monkeypatch.setattr("app.services.workflow_dispatch_poller_service._utc_now", lambda: fixed_now)

    service = WorkflowDispatchPollerService(
        dispatcher=dispatcher,
        persistence=FakePersistence(),
        scheduler=scheduler,
        poll_interval_seconds=0.1,
    )

    summary = service.poll_once(step_delay=0.9)

    assert summary["dispatched"] == 1
    assert dispatcher.execution_published == [("run-execution-fallback", 0.9)]
    assert dispatcher.processed == [("run-execution-fallback", 0.9)]
