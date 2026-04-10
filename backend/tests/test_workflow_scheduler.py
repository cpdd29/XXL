from __future__ import annotations

from datetime import UTC, datetime, timedelta

import app.services.workflow_scheduler_service as scheduler_module
from app.services.store import store
from app.services.workflow_dispatcher_service import workflow_dispatcher_service
from app.services.workflow_scheduler_service import (
    SCHEDULED_CLAIM_LEASE_BUFFER_SECONDS,
    WorkflowSchedulerService,
)


class FakeTimer:
    def __init__(self, delay: float, callback, args: tuple[str, float]) -> None:
        self.delay = delay
        self.callback = callback
        self.args = args
        self.daemon = False
        self.started = False
        self.cancelled = False

    def start(self) -> None:
        self.started = True

    def cancel(self) -> None:
        self.cancelled = True


class FakePersistence:
    def __init__(self) -> None:
        self.enabled = False
        self.persist_calls = 0
        self.execution_persisted_run_ids: list[str] = []
        self.database_runs: dict[str, dict] = {}

    def persist_runtime_state(self) -> bool:
        self.persist_calls += 1
        return True

    def persist_execution_state(self, *, workflow_run: dict | None = None, **_: object) -> bool:
        if workflow_run is not None:
            self.execution_persisted_run_ids.append(str(workflow_run["id"]))
            return True
        return False

    def get_workflow_run(self, run_id: str) -> dict | None:
        run = self.database_runs.get(run_id)
        if run is None:
            return None
        return store.clone(run)

    def list_workflow_runs(self) -> list[dict]:
        return [store.clone(run) for run in self.database_runs.values()]


class FakeQueuePersistence(FakePersistence):
    def __init__(self) -> None:
        super().__init__()
        self.enabled = True
        self.jobs: list[dict[str, object]] = []
        self.deleted_run_ids: list[str] = []

    def upsert_workflow_dispatch_job(
        self,
        run_id: str,
        *,
        available_at: str,
        step_delay_seconds: float | None = None,
        dispatcher_id: str | None = None,
        claimed_at: str | None = None,
        lease_expires_at: str | None = None,
    ) -> dict:
        job = {
            "run_id": run_id,
            "available_at": available_at,
            "step_delay_seconds": step_delay_seconds,
            "dispatcher_id": dispatcher_id,
            "claimed_at": claimed_at,
            "lease_expires_at": lease_expires_at,
        }
        self.jobs.append(job)
        return job

    def delete_workflow_dispatch_job(self, run_id: str) -> bool:
        self.deleted_run_ids.append(run_id)
        return True


def test_scheduler_schedule_starts_timer_and_persists_next_dispatch_at(monkeypatch) -> None:
    fixed_now = datetime(2026, 4, 3, 14, 0, 0, tzinfo=UTC)
    persistence = FakePersistence()
    run = {
        "id": "run-1",
        "status": "running",
        "next_dispatch_at": None,
        "dispatch_lease_expires_at": (fixed_now + timedelta(seconds=30)).isoformat(),
    }

    monkeypatch.setattr(scheduler_module, "_utc_now", lambda: fixed_now)
    monkeypatch.setattr(scheduler_module, "Timer", FakeTimer)
    monkeypatch.setattr(
        workflow_dispatcher_service,
        "try_acquire_schedule_slot",
        lambda run_id: run,
    )

    service = WorkflowSchedulerService(persistence=persistence)
    service.schedule("run-1", delay=0.5, step_delay=0.75)

    timer = service._timers["run-1"]
    assert isinstance(timer, FakeTimer)
    assert timer.started is True
    assert timer.daemon is True
    assert run["next_dispatch_at"] == (fixed_now + timedelta(seconds=0.5)).isoformat()
    assert run["dispatch_lease_expires_at"] == (
        fixed_now
        + timedelta(seconds=0.5 + SCHEDULED_CLAIM_LEASE_BUFFER_SECONDS)
    ).isoformat()
    assert persistence.execution_persisted_run_ids == ["run-1"]
    assert persistence.persist_calls == 0


def test_scheduler_schedule_extends_claim_lease_past_next_dispatch_at(monkeypatch) -> None:
    fixed_now = datetime(2026, 4, 3, 14, 0, 0, tzinfo=UTC)
    persistence = FakePersistence()
    run = {
        "id": "run-long-delay",
        "status": "running",
        "next_dispatch_at": None,
        "dispatch_lease_expires_at": (fixed_now + timedelta(seconds=30)).isoformat(),
    }

    monkeypatch.setattr(scheduler_module, "_utc_now", lambda: fixed_now)
    monkeypatch.setattr(scheduler_module, "Timer", FakeTimer)
    monkeypatch.setattr(
        workflow_dispatcher_service,
        "try_acquire_schedule_slot",
        lambda run_id: run,
    )

    service = WorkflowSchedulerService(persistence=persistence)
    service.schedule("run-long-delay", delay=45.0, step_delay=0.75)

    assert run["next_dispatch_at"] == (fixed_now + timedelta(seconds=45)).isoformat()
    assert run["dispatch_lease_expires_at"] == (
        fixed_now
        + timedelta(seconds=45 + SCHEDULED_CLAIM_LEASE_BUFFER_SECONDS)
    ).isoformat()
    assert persistence.execution_persisted_run_ids == ["run-long-delay"]
    assert persistence.persist_calls == 0


def test_scheduler_schedule_prefers_persistent_dispatch_job_over_local_timer(monkeypatch) -> None:
    fixed_now = datetime(2026, 4, 3, 14, 0, 0, tzinfo=UTC)
    persistence = FakeQueuePersistence()
    run = {
        "id": "run-queue",
        "status": "running",
        "next_dispatch_at": None,
        "dispatcher_id": workflow_dispatcher_service.dispatcher_id,
        "dispatch_claimed_at": fixed_now.isoformat(),
        "dispatch_lease_expires_at": (fixed_now + timedelta(seconds=30)).isoformat(),
    }

    monkeypatch.setattr(scheduler_module, "_utc_now", lambda: fixed_now)
    monkeypatch.setattr(scheduler_module, "Timer", FakeTimer)
    monkeypatch.setattr(
        workflow_dispatcher_service,
        "try_acquire_schedule_slot",
        lambda run_id: run,
    )

    service = WorkflowSchedulerService(persistence=persistence)
    service.schedule("run-queue", delay=1.5, step_delay=0.75)

    assert service._timers == {}
    assert run["next_dispatch_at"] == "2026-04-03T14:00:01.500000+00:00"
    assert persistence.jobs == [
        {
            "run_id": "run-queue",
            "available_at": "2026-04-03T14:00:01.500000+00:00",
            "step_delay_seconds": 0.75,
            "dispatcher_id": workflow_dispatcher_service.dispatcher_id,
            "claimed_at": fixed_now.isoformat(),
            "lease_expires_at": (
                fixed_now
                + timedelta(seconds=1.5 + SCHEDULED_CLAIM_LEASE_BUFFER_SECONDS)
            ).isoformat(),
        }
    ]
    assert persistence.execution_persisted_run_ids == ["run-queue"]
    assert persistence.persist_calls == 0


def test_scheduler_schedule_skips_when_claim_cannot_be_acquired(monkeypatch) -> None:
    monkeypatch.setattr(scheduler_module, "Timer", FakeTimer)
    released: list[str] = []
    store.workflow_runs.insert(
        0,
        {
            "id": "run-2",
            "status": "running",
            "dispatcher_id": "dispatcher-other",
            "next_dispatch_at": "2026-04-03T14:00:01+00:00",
        },
    )
    monkeypatch.setattr(
        workflow_dispatcher_service,
        "try_acquire_schedule_slot",
        lambda run_id: None,
    )
    monkeypatch.setattr(
        workflow_dispatcher_service,
        "release_run_claim",
        lambda run_id: released.append(run_id) or None,
    )

    service = WorkflowSchedulerService()
    service.schedule("run-2", delay=0.5, step_delay=0.75)

    assert service._timers == {}
    assert released == ["run-2"]
    assert store.workflow_runs[0]["next_dispatch_at"] == "2026-04-03T14:00:01+00:00"


def test_scheduler_cancel_releases_claim_and_clears_local_next_dispatch_at(monkeypatch) -> None:
    persistence = FakePersistence()
    released: list[str] = []
    monkeypatch.setattr(
        workflow_dispatcher_service,
        "release_run_claim",
        lambda run_id: released.append(run_id) or None,
    )

    run = {
        "id": "run-3",
        "status": "running",
        "dispatcher_id": workflow_dispatcher_service.dispatcher_id,
        "next_dispatch_at": "2026-04-03T14:00:01+00:00",
    }
    store.workflow_runs.insert(0, run)
    service = WorkflowSchedulerService(persistence=persistence)
    timer = FakeTimer(0.5, lambda *_: None, ("run-3", 0.75))
    service._timers["run-3"] = timer

    service.cancel("run-3")

    assert timer.cancelled is True
    assert released == ["run-3"]
    assert run["next_dispatch_at"] is None
    assert persistence.execution_persisted_run_ids == ["run-3"]
    assert persistence.persist_calls == 0


def test_scheduler_cancel_deletes_persistent_dispatch_job(monkeypatch) -> None:
    persistence = FakeQueuePersistence()
    released: list[str] = []
    monkeypatch.setattr(
        workflow_dispatcher_service,
        "release_run_claim",
        lambda run_id: released.append(run_id) or None,
    )

    run = {
        "id": "run-queue-cancel",
        "status": "running",
        "dispatcher_id": workflow_dispatcher_service.dispatcher_id,
        "next_dispatch_at": "2026-04-03T14:00:01+00:00",
    }
    persistence.database_runs["run-queue-cancel"] = store.clone(run)
    store.workflow_runs.insert(0, run)

    service = WorkflowSchedulerService(persistence=persistence)
    service.cancel("run-queue-cancel")

    assert released == ["run-queue-cancel"]
    assert run["next_dispatch_at"] is None
    assert persistence.deleted_run_ids == ["run-queue-cancel"]
    assert persistence.execution_persisted_run_ids == ["run-queue-cancel"]


def test_scheduler_cancel_prefers_database_run_over_stale_runtime_cache(monkeypatch) -> None:
    persistence = FakePersistence()
    released: list[str] = []
    monkeypatch.setattr(
        workflow_dispatcher_service,
        "release_run_claim",
        lambda run_id: released.append(run_id) or None,
    )

    persistence.database_runs["run-stale-scheduler"] = {
        "id": "run-stale-scheduler",
        "status": "running",
        "dispatcher_id": workflow_dispatcher_service.dispatcher_id,
        "next_dispatch_at": "2026-04-03T14:00:04+00:00",
    }
    store.workflow_runs.insert(
        0,
        {
            "id": "run-stale-scheduler",
            "status": "running",
            "dispatcher_id": "dispatcher-other",
            "next_dispatch_at": "2026-04-03T14:00:04+00:00",
        },
    )

    service = WorkflowSchedulerService(persistence=persistence)
    service.cancel("run-stale-scheduler")

    assert released == ["run-stale-scheduler"]
    assert store.workflow_runs[0]["dispatcher_id"] == workflow_dispatcher_service.dispatcher_id
    assert store.workflow_runs[0]["next_dispatch_at"] is None
    assert persistence.execution_persisted_run_ids == ["run-stale-scheduler"]


def test_scheduler_cancel_ignores_stale_runtime_run_when_database_run_is_missing(monkeypatch) -> None:
    persistence = FakePersistence()
    persistence.enabled = True
    released: list[str] = []
    monkeypatch.setattr(
        workflow_dispatcher_service,
        "release_run_claim",
        lambda run_id: released.append(run_id) or None,
    )

    store.workflow_runs.insert(
        0,
        {
            "id": "run-runtime-only-scheduler",
            "status": "running",
            "dispatcher_id": workflow_dispatcher_service.dispatcher_id,
            "next_dispatch_at": "2026-04-03T14:00:04+00:00",
        },
    )

    service = WorkflowSchedulerService(persistence=persistence)
    service.cancel("run-runtime-only-scheduler")

    assert released == ["run-runtime-only-scheduler"]
    assert store.workflow_runs[0]["next_dispatch_at"] == "2026-04-03T14:00:04+00:00"
    assert persistence.execution_persisted_run_ids == []
    assert persistence.persist_calls == 0


def test_scheduler_reset_releases_all_claims_and_clears_scheduled_times(monkeypatch) -> None:
    persistence = FakePersistence()
    released: list[str] = []
    monkeypatch.setattr(
        workflow_dispatcher_service,
        "release_run_claim",
        lambda run_id: released.append(run_id) or None,
    )

    first_run = {
        "id": "run-4",
        "status": "running",
        "dispatcher_id": workflow_dispatcher_service.dispatcher_id,
        "next_dispatch_at": "2026-04-03T14:00:01+00:00",
    }
    second_run = {
        "id": "run-5",
        "status": "running",
        "dispatcher_id": workflow_dispatcher_service.dispatcher_id,
        "next_dispatch_at": "2026-04-03T14:00:02+00:00",
    }
    store.workflow_runs.insert(0, second_run)
    store.workflow_runs.insert(0, first_run)

    service = WorkflowSchedulerService(persistence=persistence)
    first = FakeTimer(0.5, lambda *_: None, ("run-4", 0.75))
    second = FakeTimer(0.5, lambda *_: None, ("run-5", 0.75))
    service._timers["run-4"] = first
    service._timers["run-5"] = second

    service.reset()

    assert service._timers == {}
    assert first.cancelled is True
    assert second.cancelled is True
    assert released == ["run-4", "run-5"]
    assert first_run["next_dispatch_at"] is None
    assert second_run["next_dispatch_at"] is None
    assert persistence.execution_persisted_run_ids == ["run-4", "run-5"]
    assert persistence.persist_calls == 0


def test_scheduler_cancel_does_not_clear_foreign_owned_next_dispatch_at(monkeypatch) -> None:
    persistence = FakePersistence()
    monkeypatch.setattr(
        workflow_dispatcher_service,
        "release_run_claim",
        lambda run_id: None,
    )

    run = {
        "id": "run-6",
        "status": "running",
        "dispatcher_id": "dispatcher-other",
        "next_dispatch_at": "2026-04-03T14:00:03+00:00",
    }
    store.workflow_runs.insert(0, run)

    service = WorkflowSchedulerService(persistence=persistence)
    service.cancel("run-6")

    assert run["next_dispatch_at"] == "2026-04-03T14:00:03+00:00"
    assert persistence.persist_calls == 0


def test_scheduler_defer_persists_backoff_without_local_timer(monkeypatch) -> None:
    fixed_now = datetime(2026, 4, 3, 14, 0, 0, tzinfo=UTC)
    persistence = FakePersistence()
    run = {
        "id": "run-7",
        "status": "running",
        "dispatcher_id": "dispatcher-a",
        "next_dispatch_at": "2026-04-03T13:59:59+00:00",
    }
    store.workflow_runs.insert(0, run)

    monkeypatch.setattr(scheduler_module, "_utc_now", lambda: fixed_now)

    service = WorkflowSchedulerService(persistence=persistence)
    timer = FakeTimer(0.5, lambda *_: None, ("run-7", 0.75))
    service._timers["run-7"] = timer

    deferred = service.defer("run-7", delay=2.5, dispatcher_id="dispatcher-a")

    assert deferred is run
    assert timer.cancelled is True
    assert service._timers == {}
    assert run["next_dispatch_at"] == "2026-04-03T14:00:02.500000+00:00"
    assert persistence.execution_persisted_run_ids == ["run-7"]
    assert persistence.persist_calls == 0


def test_scheduler_defer_updates_persistent_dispatch_job(monkeypatch) -> None:
    fixed_now = datetime(2026, 4, 3, 14, 0, 0, tzinfo=UTC)
    persistence = FakeQueuePersistence()
    run = {
        "id": "run-queue-defer",
        "status": "running",
        "dispatcher_id": "dispatcher-a",
        "next_dispatch_at": "2026-04-03T13:59:59+00:00",
    }
    persistence.database_runs["run-queue-defer"] = store.clone(run)
    store.workflow_runs.insert(0, run)

    monkeypatch.setattr(scheduler_module, "_utc_now", lambda: fixed_now)

    service = WorkflowSchedulerService(persistence=persistence)
    deferred = service.defer(
        "run-queue-defer",
        delay=2.5,
        step_delay=0.8,
        dispatcher_id="dispatcher-a",
    )

    assert deferred is run
    assert run["next_dispatch_at"] == "2026-04-03T14:00:02.500000+00:00"
    assert persistence.jobs == [
        {
            "run_id": "run-queue-defer",
            "available_at": "2026-04-03T14:00:02.500000+00:00",
            "step_delay_seconds": 0.8,
            "dispatcher_id": None,
            "claimed_at": None,
            "lease_expires_at": None,
        }
    ]
    assert persistence.execution_persisted_run_ids == ["run-queue-defer"]


def test_scheduler_defer_ignores_stale_runtime_run_when_database_run_is_missing() -> None:
    persistence = FakePersistence()
    persistence.enabled = True
    store.workflow_runs.insert(
        0,
        {
            "id": "run-runtime-only-defer",
            "status": "running",
            "dispatcher_id": "dispatcher-a",
            "next_dispatch_at": "2026-04-03T14:00:01+00:00",
        },
    )

    service = WorkflowSchedulerService(persistence=persistence)
    deferred = service.defer(
        "run-runtime-only-defer",
        delay=2.5,
        dispatcher_id="dispatcher-a",
    )

    assert deferred is None
    assert store.workflow_runs[0]["next_dispatch_at"] == "2026-04-03T14:00:01+00:00"
    assert persistence.execution_persisted_run_ids == []
    assert persistence.persist_calls == 0


def test_scheduler_defer_skips_foreign_owned_run(monkeypatch) -> None:
    fixed_now = datetime(2026, 4, 3, 14, 0, 0, tzinfo=UTC)
    persistence = FakePersistence()
    run = {
        "id": "run-8",
        "status": "running",
        "dispatcher_id": "dispatcher-other",
        "next_dispatch_at": "2026-04-03T14:00:03+00:00",
    }
    store.workflow_runs.insert(0, run)

    monkeypatch.setattr(scheduler_module, "_utc_now", lambda: fixed_now)

    service = WorkflowSchedulerService(persistence=persistence)

    deferred = service.defer("run-8", delay=2.5, dispatcher_id="dispatcher-a")

    assert deferred is run
    assert run["next_dispatch_at"] == "2026-04-03T14:00:03+00:00"
    assert persistence.persist_calls == 0
