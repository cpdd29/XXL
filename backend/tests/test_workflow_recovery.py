from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

import app.services.workflow_recovery_service as recovery_module
from app.services.store import store
from app.services.workflow_dispatcher_service import DEFAULT_DISPATCH_FAILURE_RETRY_DELAY_SECONDS
from app.services.workflow_recovery_service import (
    ORPHANED_RUN_WARNING,
    RECOVERY_WARNING,
    WorkflowRecoveryService,
)


class FakeScheduler:
    def __init__(self, *, scheduled_run_ids: set[str] | None = None) -> None:
        self.scheduled: list[tuple[str, float, float]] = []
        self.cancelled: list[str] = []
        self.deferred: list[tuple[str, float, float | None, str | None]] = []
        self._scheduled_run_ids = scheduled_run_ids if scheduled_run_ids is not None else set()

    def schedule(self, run_id: str, *, delay: float, step_delay: float) -> None:
        self.scheduled.append((run_id, delay, step_delay))
        self._scheduled_run_ids.add(run_id)

    def cancel(self, run_id: str) -> None:
        self.cancelled.append(run_id)
        self._scheduled_run_ids.discard(run_id)

    def has_timer(self, run_id: str) -> bool:
        return run_id in self._scheduled_run_ids

    def defer(
        self,
        run_id: str,
        *,
        delay: float,
        step_delay: float | None = None,
        dispatcher_id: str | None = None,
    ) -> dict:
        self.deferred.append((run_id, delay, step_delay, dispatcher_id))
        self._scheduled_run_ids.discard(run_id)
        return {"id": run_id}


class FakePersistence:
    def __init__(self, *, claimed_due_runs: list[dict] | None = None) -> None:
        self.persist_calls = 0
        self.execution_persisted_run_ids: list[str] = []
        self.claimed_due_runs = claimed_due_runs
        self.claim_calls: list[dict[str, object]] = []
        self.database_runs: dict[str, dict] = {}
        self.database_tasks: dict[str, dict] = {}

    def persist_runtime_state(self) -> bool:
        self.persist_calls += 1
        return True

    def persist_execution_state(self, *, workflow_run: dict | None = None, **_: object) -> bool:
        if workflow_run is not None:
            self.execution_persisted_run_ids.append(str(workflow_run["id"]))
            return True
        return False

    def claim_due_workflow_runs(
        self,
        *,
        dispatcher_id: str,
        claimed_at: str,
        lease_expires_at: str,
        before: str | None = None,
        limit: int | None = None,
    ) -> list[dict] | None:
        self.claim_calls.append(
            {
                "dispatcher_id": dispatcher_id,
                "claimed_at": claimed_at,
                "lease_expires_at": lease_expires_at,
                "before": before,
                "limit": limit,
            }
        )
        if self.claimed_due_runs is None:
            return None
        items = list(self.claimed_due_runs)
        if limit is not None:
            items = items[:limit]
        return [store.clone(run) for run in items]

    def get_workflow_run(self, run_id: str) -> dict | None:
        run = self.database_runs.get(run_id)
        if run is None:
            return None
        return store.clone(run)

    def get_task(self, task_id: str) -> dict | None:
        task = self.database_tasks.get(task_id)
        if task is None:
            return None
        return store.clone(task)


class FakeDispatcher:
    def __init__(
        self,
        *,
        claimed_run_ids: set[str] | None = None,
        dispatch_success: bool = False,
        process_error: Exception | None = None,
    ) -> None:
        self.claimed_run_ids = claimed_run_ids if claimed_run_ids is not None else set()
        self.dispatch_success = dispatch_success
        self.process_error = process_error
        self.dispatcher_id = "dispatcher-test"
        self.attempts: list[str] = []
        self.dispatched: list[tuple[str, float]] = []
        self.processed: list[tuple[str, float]] = []
        self.released: list[str] = []

    def try_acquire_schedule_slot(self, run_id: str) -> dict | None:
        self.attempts.append(run_id)
        if run_id not in self.claimed_run_ids:
            return None
        for run in store.workflow_runs:
            if run["id"] == run_id:
                run["dispatcher_id"] = "dispatcher-test"
                return run
        return {"id": run_id}

    def dispatch_tick(self, run_id: str, *, step_delay: float) -> bool:
        self.dispatched.append((run_id, step_delay))
        return self.dispatch_success

    def process_tick(self, run_id: str, *, step_delay: float) -> dict:
        if self.process_error is not None:
            raise self.process_error
        self.processed.append((run_id, step_delay))
        return {"id": run_id, "status": "running"}

    def release_run_claim(self, run_id: str) -> None:
        self.released.append(run_id)


def _running_task(*, task_id: str, run_id: str) -> dict:
    created_at = store.now_string()
    return {
        "id": task_id,
        "title": "恢复中的工作流任务",
        "description": "服务重启后继续推进当前工作流",
        "status": "running",
        "priority": "high",
        "created_at": created_at,
        "completed_at": None,
        "agent": "搜索Agent",
        "tokens": 64,
        "duration": None,
        "workflow_id": "workflow-1",
        "workflow_run_id": run_id,
        "result": None,
    }


def _workflow_run(
    *,
    run_id: str,
    task_id: str,
    status: str = "running",
    next_dispatch_at: str | None = None,
) -> dict:
    created_at = store.now_string()
    return {
        "id": run_id,
        "workflow_id": "workflow-1",
        "workflow_name": "客户服务工作流",
        "task_id": task_id,
        "trigger": "message",
        "intent": "search",
        "status": status,
        "created_at": created_at,
        "updated_at": created_at,
        "started_at": created_at,
        "completed_at": None,
        "next_dispatch_at": next_dispatch_at,
        "current_stage": "等待恢复",
        "active_edges": [],
        "nodes": [],
        "logs": [],
        "memory_hits": 1,
        "warnings": [],
    }


def test_workflow_recovery_service_reschedules_non_terminal_runs() -> None:
    scheduler = FakeScheduler()
    persistence = FakePersistence()
    dispatcher = FakeDispatcher(claimed_run_ids={"run-recover"})
    service = WorkflowRecoveryService(
        scheduler=scheduler,
        persistence=persistence,
        dispatcher=dispatcher,
    )

    task = _running_task(task_id="task-recover", run_id="run-recover")
    store.tasks.insert(0, task)
    store.task_steps["task-recover"] = [
        {
            "id": "task-recover-1",
            "title": "执行节点",
            "status": "running",
            "agent": "搜索Agent",
            "started_at": task["created_at"],
            "finished_at": None,
            "message": "正在恢复搜索执行",
            "tokens": 64,
        }
    ]
    store.workflow_runs.insert(0, _workflow_run(run_id="run-recover", task_id="task-recover"))

    summary = service.bootstrap(delay=0.25, step_delay=0.8)

    assert summary == {
        "recovered": 1,
        "skipped_claimed": 0,
        "skipped_terminal": 0,
        "skipped_orphaned": 0,
    }
    assert scheduler.scheduled == [("run-recover", 0.25, 0.8)]
    assert RECOVERY_WARNING in store.workflow_runs[0]["warnings"]
    assert store.workflow_runs[0]["status"] == "running"
    assert persistence.execution_persisted_run_ids == ["run-recover"]
    assert persistence.persist_calls == 0


def test_workflow_recovery_service_skips_terminal_and_orphaned_runs() -> None:
    scheduler = FakeScheduler()
    persistence = FakePersistence()
    dispatcher = FakeDispatcher(claimed_run_ids={"run-orphaned", "run-done"})
    service = WorkflowRecoveryService(
        scheduler=scheduler,
        persistence=persistence,
        dispatcher=dispatcher,
    )

    completed_task = _running_task(task_id="task-done", run_id="run-done")
    completed_task["status"] = "completed"
    completed_task["completed_at"] = store.now_string()
    store.tasks.insert(0, completed_task)
    store.workflow_runs.insert(0, _workflow_run(run_id="run-orphaned", task_id="task-missing"))
    store.workflow_runs.insert(0, _workflow_run(run_id="run-done", task_id="task-done", status="completed"))

    summary = service.bootstrap()

    assert summary == {
        "recovered": 0,
        "skipped_claimed": 0,
        "skipped_terminal": 1,
        "skipped_orphaned": 1,
    }
    assert scheduler.scheduled == []
    assert set(scheduler.cancelled) == {"run-done", "run-orphaned"}
    orphaned_run = next(run for run in store.workflow_runs if run["id"] == "run-orphaned")
    assert ORPHANED_RUN_WARNING in orphaned_run["warnings"]
    assert persistence.execution_persisted_run_ids == ["run-orphaned"]
    assert persistence.persist_calls == 0


def test_workflow_recovery_service_is_idempotent_within_same_process() -> None:
    scheduler = FakeScheduler()
    persistence = FakePersistence()
    dispatcher = FakeDispatcher(claimed_run_ids={"run-once"})
    service = WorkflowRecoveryService(
        scheduler=scheduler,
        persistence=persistence,
        dispatcher=dispatcher,
    )

    task = _running_task(task_id="task-once", run_id="run-once")
    store.tasks.insert(0, task)
    store.task_steps["task-once"] = [
        {
            "id": "task-once-1",
            "title": "执行节点",
            "status": "running",
            "agent": "搜索Agent",
            "started_at": task["created_at"],
            "finished_at": None,
            "message": "等待恢复",
            "tokens": 64,
        }
    ]
    store.workflow_runs.insert(0, _workflow_run(run_id="run-once", task_id="task-once"))

    first = service.bootstrap()
    second = service.bootstrap()

    assert first["recovered"] == 1
    assert second["recovered"] == 0
    assert scheduler.scheduled == [("run-once", 0.2, 0.6)]
    assert persistence.execution_persisted_run_ids == ["run-once"]
    assert persistence.persist_calls == 0


def test_workflow_recovery_service_skips_runs_claimed_by_other_dispatcher() -> None:
    scheduler = FakeScheduler()
    persistence = FakePersistence()
    dispatcher = FakeDispatcher(claimed_run_ids=set())
    service = WorkflowRecoveryService(
        scheduler=scheduler,
        persistence=persistence,
        dispatcher=dispatcher,
    )

    task = _running_task(task_id="task-claimed", run_id="run-claimed")
    store.tasks.insert(0, task)
    store.task_steps["task-claimed"] = [
        {
            "id": "task-claimed-1",
            "title": "执行节点",
            "status": "running",
            "agent": "搜索Agent",
            "started_at": task["created_at"],
            "finished_at": None,
            "message": "等待恢复",
            "tokens": 64,
        }
    ]
    run = _workflow_run(run_id="run-claimed", task_id="task-claimed")
    run["dispatcher_id"] = "dispatcher-other"
    store.workflow_runs.insert(0, run)

    summary = service.bootstrap()

    assert summary == {
        "recovered": 0,
        "skipped_claimed": 1,
        "skipped_terminal": 0,
        "skipped_orphaned": 0,
    }
    assert scheduler.scheduled == []
    assert persistence.persist_calls == 0
    assert persistence.execution_persisted_run_ids == []


def test_workflow_recovery_service_prefers_database_claim_state_over_stale_runtime_cache() -> None:
    scheduler = FakeScheduler()
    persistence = FakePersistence()
    dispatcher = FakeDispatcher(claimed_run_ids={"run-db-claimed"})
    service = WorkflowRecoveryService(
        scheduler=scheduler,
        persistence=persistence,
        dispatcher=dispatcher,
    )

    store.tasks.insert(0, _running_task(task_id="task-db-claimed", run_id="run-db-claimed"))
    store.workflow_runs.insert(0, _workflow_run(run_id="run-db-claimed", task_id="task-db-claimed"))
    persistence.database_runs["run-db-claimed"] = {
        **_workflow_run(run_id="run-db-claimed", task_id="task-db-claimed"),
        "dispatcher_id": "dispatcher-other",
        "dispatch_claimed_at": "2026-04-03T14:00:00+00:00",
        "dispatch_lease_expires_at": (datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
    }

    summary = service.bootstrap()

    assert summary == {
        "recovered": 0,
        "skipped_claimed": 1,
        "skipped_terminal": 0,
        "skipped_orphaned": 0,
    }
    assert scheduler.scheduled == []
    assert dispatcher.attempts == []
    assert store.workflow_runs[0]["dispatcher_id"] == "dispatcher-other"
    assert persistence.execution_persisted_run_ids == []


def test_workflow_recovery_service_fail_closed_when_database_candidate_read_returns_none() -> None:
    class FailingReadPersistence(FakePersistence):
        def __init__(self) -> None:
            super().__init__()
            self.enabled = True

        def list_workflow_runs(self) -> list[dict] | None:
            return None

    scheduler = FakeScheduler()
    persistence = FailingReadPersistence()
    dispatcher = FakeDispatcher(claimed_run_ids={"run-runtime-only-recovery"})
    service = WorkflowRecoveryService(
        scheduler=scheduler,
        persistence=persistence,
        dispatcher=dispatcher,
    )

    task = _running_task(
        task_id="task-runtime-only-recovery",
        run_id="run-runtime-only-recovery",
    )
    run = _workflow_run(
        run_id="run-runtime-only-recovery",
        task_id="task-runtime-only-recovery",
    )
    store.tasks.insert(0, task)
    store.workflow_runs.insert(0, run)

    summary = service.bootstrap(delay=0.2, step_delay=0.6)

    assert summary == {
        "recovered": 0,
        "skipped_claimed": 0,
        "skipped_terminal": 0,
        "skipped_orphaned": 0,
    }
    assert scheduler.scheduled == []
    assert scheduler.cancelled == []
    assert dispatcher.attempts == []
    assert dispatcher.dispatched == []
    assert dispatcher.processed == []
    assert persistence.execution_persisted_run_ids == []


def test_workflow_recovery_service_uses_persisted_future_dispatch_time(monkeypatch) -> None:
    fixed_now = datetime(2026, 4, 3, 14, 0, 0, tzinfo=UTC)
    scheduler = FakeScheduler()
    persistence = FakePersistence()
    dispatcher = FakeDispatcher(claimed_run_ids={"run-future"})
    service = WorkflowRecoveryService(
        scheduler=scheduler,
        persistence=persistence,
        dispatcher=dispatcher,
    )

    monkeypatch.setattr(recovery_module, "_utc_now", lambda: fixed_now)

    task = _running_task(task_id="task-future", run_id="run-future")
    store.tasks.insert(0, task)
    store.workflow_runs.insert(
        0,
        _workflow_run(
            run_id="run-future",
            task_id="task-future",
            next_dispatch_at=(fixed_now + timedelta(seconds=1.25)).isoformat(),
        ),
    )

    summary = service.bootstrap(delay=0.2, step_delay=0.6)

    assert summary["recovered"] == 1
    assert scheduler.scheduled == [("run-future", 1.25, 0.6)]
    assert persistence.execution_persisted_run_ids == ["run-future"]
    assert persistence.persist_calls == 0


def test_workflow_recovery_service_runs_overdue_dispatches_immediately(monkeypatch) -> None:
    fixed_now = datetime(2026, 4, 3, 14, 0, 0, tzinfo=UTC)
    scheduler = FakeScheduler()
    persistence = FakePersistence()
    dispatcher = FakeDispatcher(claimed_run_ids={"run-overdue"})
    service = WorkflowRecoveryService(
        scheduler=scheduler,
        persistence=persistence,
        dispatcher=dispatcher,
    )

    monkeypatch.setattr(recovery_module, "_utc_now", lambda: fixed_now)

    task = _running_task(task_id="task-overdue", run_id="run-overdue")
    store.tasks.insert(0, task)
    store.workflow_runs.insert(
        0,
        _workflow_run(
            run_id="run-overdue",
            task_id="task-overdue",
            next_dispatch_at=(fixed_now - timedelta(seconds=5)).isoformat(),
        ),
    )

    summary = service.bootstrap(delay=0.2, step_delay=0.6)

    assert summary["recovered"] == 1
    assert scheduler.scheduled == []
    assert dispatcher.dispatched == [("run-overdue", 0.6)]
    assert dispatcher.processed == [("run-overdue", 0.6)]
    assert persistence.execution_persisted_run_ids == ["run-overdue"]
    assert persistence.persist_calls == 0


def test_workflow_recovery_service_publishes_overdue_runs_without_local_timer(monkeypatch) -> None:
    fixed_now = datetime(2026, 4, 3, 14, 0, 0, tzinfo=UTC)
    scheduler = FakeScheduler()
    persistence = FakePersistence()
    dispatcher = FakeDispatcher(claimed_run_ids={"run-publish"}, dispatch_success=True)
    service = WorkflowRecoveryService(
        scheduler=scheduler,
        persistence=persistence,
        dispatcher=dispatcher,
    )

    monkeypatch.setattr(recovery_module, "_utc_now", lambda: fixed_now)

    task = _running_task(task_id="task-publish", run_id="run-publish")
    store.tasks.insert(0, task)
    store.workflow_runs.insert(
        0,
        _workflow_run(
            run_id="run-publish",
            task_id="task-publish",
            next_dispatch_at=(fixed_now - timedelta(seconds=1)).isoformat(),
        ),
    )

    summary = service.bootstrap(delay=0.2, step_delay=0.6)

    assert summary["recovered"] == 1
    assert scheduler.scheduled == []
    assert dispatcher.dispatched == [("run-publish", 0.6)]
    assert dispatcher.processed == []
    assert persistence.execution_persisted_run_ids == ["run-publish"]
    assert persistence.persist_calls == 0


def test_workflow_recovery_service_recovers_due_runs_outside_bootstrap(monkeypatch) -> None:
    fixed_now = datetime(2026, 4, 3, 14, 0, 0, tzinfo=UTC)
    scheduler = FakeScheduler()
    persistence = FakePersistence()
    dispatcher = FakeDispatcher(claimed_run_ids={"run-due"})
    service = WorkflowRecoveryService(
        scheduler=scheduler,
        persistence=persistence,
        dispatcher=dispatcher,
    )

    monkeypatch.setattr(recovery_module, "_utc_now", lambda: fixed_now)

    task = _running_task(task_id="task-due", run_id="run-due")
    store.tasks.insert(0, task)
    store.workflow_runs.insert(
        0,
        _workflow_run(
            run_id="run-due",
            task_id="task-due",
            next_dispatch_at=(fixed_now - timedelta(seconds=3)).isoformat(),
        ),
    )

    summary = service.recover_due_runs(step_delay=0.9)

    assert summary == {
        "recovered": 1,
        "skipped_claimed": 0,
        "skipped_terminal": 0,
        "skipped_orphaned": 0,
        "skipped_scheduled": 0,
    }
    assert scheduler.scheduled == []
    assert dispatcher.dispatched == [("run-due", 0.9)]
    assert dispatcher.processed == [("run-due", 0.9)]
    assert persistence.persist_calls == 0
    assert persistence.execution_persisted_run_ids == []


def test_workflow_recovery_service_uses_database_claimed_due_runs(monkeypatch) -> None:
    fixed_now = datetime(2026, 4, 3, 14, 0, 0, tzinfo=UTC)

    class AlreadyClaimedDispatcher(FakeDispatcher):
        def try_acquire_schedule_slot(self, run_id: str) -> dict | None:
            raise AssertionError(
                f"recovery should not re-acquire atomically claimed due run {run_id}"
            )

    scheduler = FakeScheduler()
    dispatcher = AlreadyClaimedDispatcher()
    persistence = FakePersistence(
        claimed_due_runs=[
            _workflow_run(
                run_id="run-db-claimed",
                task_id="task-db-claimed",
                next_dispatch_at=(fixed_now - timedelta(seconds=2)).isoformat(),
            )
            | {
                "dispatcher_id": "dispatcher-test",
                "dispatch_claimed_at": fixed_now.isoformat(),
                "dispatch_lease_expires_at": (fixed_now + timedelta(seconds=30)).isoformat(),
            }
        ]
    )
    service = WorkflowRecoveryService(
        scheduler=scheduler,
        persistence=persistence,
        dispatcher=dispatcher,
    )

    monkeypatch.setattr(recovery_module, "_utc_now", lambda: fixed_now)

    task = _running_task(task_id="task-db-claimed", run_id="run-db-claimed")
    store.tasks.insert(0, task)

    summary = service.recover_due_runs(step_delay=0.7)

    assert summary == {
        "recovered": 1,
        "skipped_claimed": 0,
        "skipped_terminal": 0,
        "skipped_orphaned": 0,
        "skipped_scheduled": 0,
    }
    assert dispatcher.attempts == []
    assert dispatcher.dispatched == [("run-db-claimed", 0.7)]
    assert dispatcher.processed == [("run-db-claimed", 0.7)]
    assert scheduler.scheduled == []
    assert persistence.claim_calls[0]["dispatcher_id"] == "dispatcher-test"
    assert persistence.claim_calls[0]["before"] == fixed_now.isoformat()


def test_workflow_recovery_service_due_run_scan_skips_existing_local_timer(monkeypatch) -> None:
    fixed_now = datetime(2026, 4, 3, 14, 0, 0, tzinfo=UTC)
    scheduler = FakeScheduler(scheduled_run_ids={"run-timer"})
    persistence = FakePersistence()
    dispatcher = FakeDispatcher(claimed_run_ids={"run-timer"})
    service = WorkflowRecoveryService(
        scheduler=scheduler,
        persistence=persistence,
        dispatcher=dispatcher,
    )

    monkeypatch.setattr(recovery_module, "_utc_now", lambda: fixed_now)

    task = _running_task(task_id="task-timer", run_id="run-timer")
    store.tasks.insert(0, task)
    store.workflow_runs.insert(
        0,
        _workflow_run(
            run_id="run-timer",
            task_id="task-timer",
            next_dispatch_at=(fixed_now - timedelta(seconds=1)).isoformat(),
        ),
    )

    summary = service.recover_due_runs(step_delay=0.9)

    assert summary == {
        "recovered": 0,
        "skipped_claimed": 0,
        "skipped_terminal": 0,
        "skipped_orphaned": 0,
        "skipped_scheduled": 1,
    }
    assert scheduler.scheduled == []
    assert dispatcher.dispatched == []


def test_workflow_recovery_service_defers_due_run_when_dispatch_raises(monkeypatch) -> None:
    fixed_now = datetime(2026, 4, 3, 14, 0, 0, tzinfo=UTC)
    scheduler = FakeScheduler()
    persistence = FakePersistence()
    dispatcher = FakeDispatcher(
        claimed_run_ids={"run-recovery-error"},
        dispatch_success=False,
        process_error=RuntimeError("recovery dispatch failed"),
    )
    service = WorkflowRecoveryService(
        scheduler=scheduler,
        persistence=persistence,
        dispatcher=dispatcher,
    )

    monkeypatch.setattr(recovery_module, "_utc_now", lambda: fixed_now)

    task = _running_task(task_id="task-recovery-error", run_id="run-recovery-error")
    store.tasks.insert(0, task)
    store.workflow_runs.insert(
        0,
        _workflow_run(
            run_id="run-recovery-error",
            task_id="task-recovery-error",
            next_dispatch_at=(fixed_now - timedelta(seconds=1)).isoformat(),
        ),
    )

    summary = service.recover_due_runs(step_delay=0.75)

    assert summary == {
        "recovered": 1,
        "skipped_claimed": 0,
        "skipped_terminal": 0,
        "skipped_orphaned": 0,
        "skipped_scheduled": 0,
    }
    assert dispatcher.dispatched == [("run-recovery-error", 0.75)]
    assert scheduler.deferred == [
        (
            "run-recovery-error",
            DEFAULT_DISPATCH_FAILURE_RETRY_DELAY_SECONDS,
            0.75,
            "dispatcher-test",
        )
    ]
    assert dispatcher.released == ["run-recovery-error"]


def test_workflow_recovery_service_defers_when_execution_publish_fails(monkeypatch) -> None:
    if "dispatch_execution" not in WorkflowRecoveryService._dispatch_due_run.__code__.co_names:
        pytest.skip("execution publish path is not enabled in this branch")

    fixed_now = datetime(2026, 4, 3, 14, 0, 0, tzinfo=UTC)
    scheduler = FakeScheduler()
    persistence = FakePersistence()

    class ExecutionDispatcher(FakeDispatcher):
        def __init__(self) -> None:
            super().__init__(claimed_run_ids={"run-execution-recovery"})
            self.execution_published: list[tuple[str, float]] = []

        def dispatch_execution(self, run_id: str, *, step_delay: float) -> bool:
            self.execution_published.append((run_id, step_delay))
            return False

        def process_tick(self, run_id: str, *, step_delay: float) -> dict:
            raise RuntimeError("execution publish fallback failed")

    dispatcher = ExecutionDispatcher()
    service = WorkflowRecoveryService(
        scheduler=scheduler,
        persistence=persistence,
        dispatcher=dispatcher,
    )

    monkeypatch.setattr(recovery_module, "_utc_now", lambda: fixed_now)

    task = _running_task(task_id="task-execution-recovery", run_id="run-execution-recovery")
    store.tasks.insert(0, task)
    store.workflow_runs.insert(
        0,
        _workflow_run(
            run_id="run-execution-recovery",
            task_id="task-execution-recovery",
            next_dispatch_at=(fixed_now - timedelta(seconds=1)).isoformat(),
        ),
    )

    summary = service.recover_due_runs(step_delay=0.85)

    assert summary["recovered"] == 1
    assert dispatcher.execution_published == [("run-execution-recovery", 0.85)]
    assert scheduler.deferred == [
        (
            "run-execution-recovery",
            DEFAULT_DISPATCH_FAILURE_RETRY_DELAY_SECONDS,
            0.85,
            "dispatcher-test",
        )
    ]
    assert dispatcher.released == ["run-execution-recovery"]
