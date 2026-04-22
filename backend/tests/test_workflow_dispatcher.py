from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

import app.services.workflow_dispatcher_service as dispatcher_module
from app.services import workflow_execution_service
from app.services.workflow_dispatcher_service import (
    DEFAULT_DISPATCH_FAILURE_RETRY_DELAY_SECONDS,
    DISPATCH_FAILURE_TERMINAL_WARNING_TEMPLATE,
    DISPATCH_FAILURE_WARNING_TEMPLATE,
    MAX_DISPATCH_FAILURE_COUNT,
    MAX_DISPATCH_FAILURE_RETRY_DELAY_SECONDS,
    WORKFLOW_DISPATCH_QUEUE,
    WORKFLOW_DISPATCH_SUBJECT,
    WorkflowDispatcherService,
)
from app.services.workflow_scheduler_service import workflow_scheduler_service
from app.services.store import store


class FakeEventBus:
    def __init__(self, publish_result: bool = True) -> None:
        self.publish_result = publish_result
        self.subscriptions: list[tuple[str, str, object]] = []
        self.published: list[tuple[str, dict]] = []

    def subscribe(self, subject: str, handler, *, queue_group: str = "") -> None:
        self.subscriptions.append((subject, queue_group, handler))

    def publish_json(self, subject: str, payload: dict) -> bool:
        self.published.append((subject, payload))
        return self.publish_result


class FakePersistence:
    def __init__(self) -> None:
        self.enabled = False
        self.persist_calls = 0
        self.execution_persisted_run_ids: list[str] = []
        self.claim_calls: list[dict[str, str | None]] = []
        self.release_calls: list[dict[str, str | None]] = []
        self.claim_response: dict | None = None
        self.release_response: dict | None = None
        self.database_runs: dict[str, dict] = {}
        self.execution_jobs: dict[str, dict] = {}
        self.execution_job_upserts: list[dict[str, object]] = []

    def get_workflow_run(self, run_id: str) -> dict | None:
        persisted = self.database_runs.get(run_id)
        if persisted is not None:
            return deepcopy(persisted)
        for run in store.workflow_runs:
            if run["id"] == run_id:
                return deepcopy(run)
        return None

    def persist_runtime_state(self) -> bool:
        self.persist_calls += 1
        return True

    def persist_execution_state(self, *, workflow_run: dict | None = None, **_: object) -> bool:
        if workflow_run is not None:
            self.execution_persisted_run_ids.append(str(workflow_run["id"]))
            return True
        return False

    @staticmethod
    def _build_call_payload(names: list[str], args: tuple, kwargs: dict) -> dict[str, str | None]:
        payload = {name: None for name in names}
        for name, value in zip(names, args):
            payload[name] = value
        payload.update(kwargs)
        return payload

    def claim_workflow_run(self, *args, **kwargs) -> dict | None:
        call_payload = self._build_call_payload(
            ["run_id", "dispatcher_id", "claimed_at", "lease_expires_at"],
            args,
            kwargs,
        )
        self.claim_calls.append(call_payload)
        if self.claim_response is None:
            return None
        return deepcopy(self.claim_response)

    def release_workflow_run_claim(self, *args, **kwargs) -> dict | None:
        call_payload = self._build_call_payload(
            ["run_id", "dispatcher_id"],
            args,
            kwargs,
        )
        self.release_calls.append(call_payload)
        if self.release_response is None:
            return None
        return deepcopy(self.release_response)

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
            "step_delay_seconds": step_delay_seconds,
            "worker_id": None,
            "claimed_at": None,
            "lease_expires_at": None,
            "created_at": queued_at,
            "updated_at": queued_at,
        }
        protocol: dict[str, object] = {}
        for key in (
            "spec_version",
            "message_id",
            "message_type",
            "message_name",
            "request_id",
            "correlation_id",
            "causation_id",
            "idempotency_key",
            "attempt",
            "max_attempts",
            "dead_letter",
            "dead_letter_reason",
            "last_error",
        ):
            if key in kwargs:
                payload[key] = kwargs.get(key)
                protocol[key] = kwargs.get(key)
        if protocol:
            payload["protocol"] = dict(protocol)
        self.execution_job_upserts.append(payload)
        self.execution_jobs[run_id] = deepcopy(payload)
        return deepcopy(payload)

    def get_workflow_execution_job(self, run_id: str) -> dict | None:
        payload = self.execution_jobs.get(run_id)
        return deepcopy(payload) if payload is not None else None


@pytest.fixture(autouse=True)
def _bind_scheduler_service(monkeypatch) -> None:
    # The dispatcher keeps a module-level scheduler reference.
    monkeypatch.setattr(
        dispatcher_module,
        "workflow_scheduler_service",
        workflow_scheduler_service,
        raising=False,
    )


def _workflow_run(
    run_id: str,
    *,
    status: str = "running",
    dispatch_failure_count: int = 0,
    last_dispatch_error: str | None = None,
    dispatcher_id: str | None = None,
    dispatch_lease_expires_at: str | None = None,
) -> dict:
    created_at = store.now_string()
    return {
        "id": run_id,
        "workflow_id": "workflow-1",
        "workflow_name": "客户服务工作流",
        "task_id": f"task-{run_id}",
        "trigger": "message",
        "intent": "search",
        "status": status,
        "created_at": created_at,
        "updated_at": created_at,
        "started_at": created_at,
        "completed_at": None,
        "dispatch_failure_count": dispatch_failure_count,
        "last_dispatch_error": last_dispatch_error,
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


def test_workflow_dispatcher_service_registers_queue_subscription_and_publishes_tick() -> None:
    event_bus = FakeEventBus()
    service = WorkflowDispatcherService(event_bus=event_bus, persistence=FakePersistence())

    assert event_bus.subscriptions == [
        (WORKFLOW_DISPATCH_SUBJECT, WORKFLOW_DISPATCH_QUEUE, service._handle_dispatch_message)
    ]

    assert service.dispatch_tick("run-1", step_delay=0.6) is True
    assert event_bus.published == [
        (
            WORKFLOW_DISPATCH_SUBJECT,
            {
                "run_id": "run-1",
                "step_delay": 0.6,
            },
        )
    ]


def test_workflow_dispatcher_service_process_tick_reschedules_non_terminal_run(monkeypatch) -> None:
    event_bus = FakeEventBus()
    persistence = FakePersistence()
    service = WorkflowDispatcherService(
        event_bus=event_bus,
        persistence=persistence,
        dispatcher_id="dispatcher-a",
    )
    scheduled: list[tuple[str, float, float]] = []
    cancelled: list[str] = []
    store.workflow_runs.insert(
        0,
        _workflow_run(
            "run-2",
            dispatch_failure_count=2,
            last_dispatch_error="previous failure",
        ),
    )

    monkeypatch.setattr(
        workflow_execution_service,
        "dispatch_workflow_run",
        lambda run_id: {"id": run_id, "status": "running"},
    )
    monkeypatch.setattr(
        workflow_scheduler_service,
        "schedule",
        lambda run_id, *, delay, step_delay: scheduled.append((run_id, delay, step_delay)),
    )
    monkeypatch.setattr(
        workflow_scheduler_service,
        "cancel",
        lambda run_id: cancelled.append(run_id),
    )

    run = service.process_tick("run-2", step_delay=0.75)

    assert run["id"] == "run-2"
    assert run["status"] == "running"
    assert run["dispatch_failure_count"] == 0
    assert run["last_dispatch_error"] is None
    assert scheduled == [("run-2", 0.75, 0.75)]
    assert cancelled == []
    assert store.workflow_runs[0]["dispatcher_id"] == "dispatcher-a"
    assert store.workflow_runs[0]["dispatch_failure_count"] == 0
    assert store.workflow_runs[0]["last_dispatch_error"] is None
    assert persistence.execution_persisted_run_ids.count("run-2") >= 2
    assert persistence.persist_calls == 0


def test_workflow_dispatcher_service_process_tick_cancels_terminal_run(monkeypatch) -> None:
    event_bus = FakeEventBus()
    persistence = FakePersistence()
    service = WorkflowDispatcherService(
        event_bus=event_bus,
        persistence=persistence,
        dispatcher_id="dispatcher-a",
    )
    scheduled: list[tuple[str, float, float]] = []
    cancelled: list[str] = []
    store.workflow_runs.insert(0, _workflow_run("run-3"))

    monkeypatch.setattr(
        workflow_execution_service,
        "dispatch_workflow_run",
        lambda run_id: {"id": run_id, "status": "completed"},
    )
    monkeypatch.setattr(
        workflow_scheduler_service,
        "schedule",
        lambda run_id, *, delay, step_delay: scheduled.append((run_id, delay, step_delay)),
    )
    monkeypatch.setattr(
        workflow_scheduler_service,
        "cancel",
        lambda run_id: cancelled.append(run_id),
    )

    run = service.process_tick("run-3", step_delay=0.25)

    assert run["id"] == "run-3"
    assert run["status"] == "completed"
    assert run["dispatch_failure_count"] == 0
    assert run["last_dispatch_error"] is None
    assert scheduled == []
    assert cancelled == ["run-3"]
    assert store.workflow_runs[0]["dispatcher_id"] is None
    assert persistence.execution_persisted_run_ids.count("run-3") >= 2
    assert persistence.persist_calls == 0


def test_workflow_dispatcher_service_process_tick_stops_redispatch_when_agent_queue_is_active(
    monkeypatch,
) -> None:
    event_bus = FakeEventBus()
    persistence = FakePersistence()
    service = WorkflowDispatcherService(
        event_bus=event_bus,
        persistence=persistence,
        dispatcher_id="dispatcher-a",
    )
    released: list[str] = []
    store.workflow_runs.insert(0, _workflow_run("run-agent-queued"))

    monkeypatch.setattr(
        workflow_execution_service,
        "dispatch_workflow_run",
        lambda run_id: {
            "id": run_id,
            "status": "running",
            "dispatch_context": {"state": "agent_queued"},
        },
    )
    monkeypatch.setattr(service, "release_run_claim", lambda run_id: released.append(run_id) or {})

    run = service.process_tick("run-agent-queued", step_delay=0.25)

    assert run["id"] == "run-agent-queued"
    assert event_bus.published == []
    assert released == ["run-agent-queued"]


def test_workflow_dispatcher_service_process_tick_keeps_graph_execution_progressing(
    monkeypatch,
) -> None:
    event_bus = FakeEventBus()
    persistence = FakePersistence()
    service = WorkflowDispatcherService(
        event_bus=event_bus,
        persistence=persistence,
        dispatcher_id="dispatcher-a",
    )
    scheduled: list[tuple[str, float, float]] = []
    released: list[str] = []
    dispatch_calls: list[tuple[str, float]] = []
    store.workflow_runs.insert(0, _workflow_run("run-graph-executing"))

    monkeypatch.setattr(
        workflow_execution_service,
        "dispatch_workflow_run",
        lambda run_id: {
            "id": run_id,
            "status": "running",
            "dispatch_context": {"state": "executing", "execution_engine": "graph_v2"},
        },
    )
    monkeypatch.setattr(
        service,
        "dispatch_execution",
        lambda run_id, *, step_delay, published_at: (
            dispatch_calls.append((run_id, step_delay)) or True
        ),
    )
    monkeypatch.setattr(
        workflow_scheduler_service,
        "schedule",
        lambda run_id, *, delay, step_delay: scheduled.append((run_id, delay, step_delay)),
    )
    monkeypatch.setattr(service, "release_run_claim", lambda run_id: released.append(run_id) or {})

    run = service.process_tick("run-graph-executing", step_delay=0.4)

    assert run["id"] == "run-graph-executing"
    assert dispatch_calls == [("run-graph-executing", 0.4)]
    assert scheduled == [("run-graph-executing", 0.4, 0.4)]
    assert released == []


def test_workflow_dispatcher_service_schedule_slot_respects_active_foreign_claim() -> None:
    event_bus = FakeEventBus()
    persistence = FakePersistence()
    service = WorkflowDispatcherService(
        event_bus=event_bus,
        persistence=persistence,
        dispatcher_id="dispatcher-a",
    )
    store.workflow_runs.insert(
        0,
        _workflow_run(
            "run-locked",
            dispatcher_id="dispatcher-b",
            dispatch_lease_expires_at=(
                datetime.now(UTC) + timedelta(seconds=30)
            ).isoformat(),
        ),
    )

    claimed = service.try_acquire_schedule_slot("run-locked")

    assert claimed is None
    assert store.workflow_runs[0]["dispatcher_id"] == "dispatcher-b"
    assert persistence.persist_calls == 0
    assert persistence.execution_persisted_run_ids == []


def test_workflow_dispatcher_service_releases_claim_when_tick_fails(monkeypatch) -> None:
    fixed_now = datetime(2026, 4, 3, 15, 30, 0, tzinfo=UTC)
    event_bus = FakeEventBus()
    persistence = FakePersistence()
    service = WorkflowDispatcherService(
        event_bus=event_bus,
        persistence=persistence,
        dispatcher_id="dispatcher-a",
    )
    store.workflow_runs.insert(0, _workflow_run("run-error"))

    def _raise(_: str) -> dict:
        raise RuntimeError("tick failed")

    deferred: list[tuple[str, float, float | None, str | None]] = []
    monkeypatch.setattr(workflow_execution_service, "dispatch_workflow_run", _raise)
    monkeypatch.setattr(dispatcher_module, "_utc_now", lambda: fixed_now)
    monkeypatch.setattr(
        workflow_scheduler_service,
        "defer",
        lambda run_id, *, delay, step_delay=None, dispatcher_id=None: deferred.append(
            (run_id, delay, step_delay, dispatcher_id)
        )
        or None,
    )

    run = service.process_tick("run-error", step_delay=0.5)

    assert run is not None
    assert deferred == [
        (
            "run-error",
            DEFAULT_DISPATCH_FAILURE_RETRY_DELAY_SECONDS,
            0.5,
            "dispatcher-a",
        )
    ]
    assert run["dispatch_failure_count"] == 1
    assert run["last_dispatch_error"] == "tick failed"
    assert run["dispatcher_id"] is None
    assert run["dispatch_claimed_at"] is None
    assert run["dispatch_lease_expires_at"] is None
    assert run["updated_at"] == fixed_now.isoformat()
    assert run["warnings"] == [
        DISPATCH_FAILURE_WARNING_TEMPLATE.format(
            delay=DEFAULT_DISPATCH_FAILURE_RETRY_DELAY_SECONDS,
            error="tick failed",
        )
    ]
    assert run["logs"][-1]["type"] == "warning"
    assert run["logs"][-1]["agent"] == "Workflow Dispatcher"
    assert "tick failed" in run["logs"][-1]["message"]
    assert persistence.execution_persisted_run_ids.count("run-error") >= 2
    assert persistence.persist_calls == 0


def test_workflow_dispatcher_service_grows_failure_backoff_and_caps_it(monkeypatch) -> None:
    event_bus = FakeEventBus()
    persistence = FakePersistence()
    service = WorkflowDispatcherService(
        event_bus=event_bus,
        persistence=persistence,
        dispatcher_id="dispatcher-a",
    )
    store.workflow_runs.insert(
        0,
        _workflow_run(
                "run-backoff",
                dispatch_failure_count=4,
                last_dispatch_error="older failure",
            ),
        )

    def _raise(_: str) -> dict:
        raise RuntimeError("tick failed again")

    deferred: list[tuple[str, float, float | None, str | None]] = []
    monkeypatch.setattr(workflow_execution_service, "dispatch_workflow_run", _raise)
    monkeypatch.setattr(
        workflow_scheduler_service,
        "defer",
        lambda run_id, *, delay, step_delay=None, dispatcher_id=None: deferred.append(
            (run_id, delay, step_delay, dispatcher_id)
        )
        or None,
    )

    run = service.process_tick("run-backoff", step_delay=1.0)

    assert run is not None
    assert run["dispatch_failure_count"] == 5
    assert run["last_dispatch_error"] == "tick failed again"
    assert deferred == [
        (
            "run-backoff",
            MAX_DISPATCH_FAILURE_RETRY_DELAY_SECONDS,
            1.0,
            "dispatcher-a",
        )
    ]


def test_workflow_dispatcher_service_fails_run_after_reaching_failure_threshold(
    monkeypatch,
) -> None:
    fixed_now = datetime(2026, 4, 3, 16, 0, 0, tzinfo=UTC)
    event_bus = FakeEventBus()
    persistence = FakePersistence()
    service = WorkflowDispatcherService(
        event_bus=event_bus,
        persistence=persistence,
        dispatcher_id="dispatcher-a",
    )
    store.workflow_runs.insert(
        0,
        _workflow_run(
            "run-terminal-dispatch-error",
            dispatch_failure_count=MAX_DISPATCH_FAILURE_COUNT - 1,
            last_dispatch_error="older failure",
        ),
    )

    def _raise(_: str) -> dict:
        raise RuntimeError("tick failed terminally")

    deferred: list[tuple[str, float, str | None]] = []
    failed_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(workflow_execution_service, "dispatch_workflow_run", _raise)
    monkeypatch.setattr(dispatcher_module, "_utc_now", lambda: fixed_now)
    monkeypatch.setattr(
        workflow_execution_service,
        "fail_workflow_run_due_dispatch_failure",
        lambda run_id, *, failure_message: failed_calls.append((run_id, failure_message))
        or {
            "id": run_id,
            "status": "failed",
            "message": failure_message,
        },
    )
    monkeypatch.setattr(
        workflow_scheduler_service,
        "defer",
        lambda run_id, *, delay, dispatcher_id=None: deferred.append((run_id, delay, dispatcher_id)) or None,
    )

    run = service.process_tick("run-terminal-dispatch-error", step_delay=1.0)

    assert run == {
        "id": "run-terminal-dispatch-error",
        "status": "failed",
        "message": DISPATCH_FAILURE_TERMINAL_WARNING_TEMPLATE.format(
            error="tick failed terminally",
        ),
    }
    assert deferred == []
    assert failed_calls == [
        (
            "run-terminal-dispatch-error",
            DISPATCH_FAILURE_TERMINAL_WARNING_TEMPLATE.format(
                error="tick failed terminally",
            ),
        )
    ]
    assert store.workflow_runs[0]["dispatch_failure_count"] == MAX_DISPATCH_FAILURE_COUNT
    assert store.workflow_runs[0]["last_dispatch_error"] == "tick failed terminally"
    assert store.workflow_runs[0]["warnings"] == [
        DISPATCH_FAILURE_TERMINAL_WARNING_TEMPLATE.format(
            error="tick failed terminally",
        )
    ]
    assert store.workflow_runs[0]["logs"][-1]["type"] == "warning"
    assert "最大重试次数" in store.workflow_runs[0]["logs"][-1]["message"]


def test_workflow_dispatcher_service_schedule_slot_prefers_persistence(monkeypatch) -> None:
    fixed_now = datetime(2026, 4, 3, 16, 30, 0, tzinfo=UTC)
    event_bus = FakeEventBus()
    persistence = FakePersistence()
    service = WorkflowDispatcherService(
        event_bus=event_bus,
        persistence=persistence,
        dispatcher_id="dispatcher-a",
    )
    persistence.enabled = True

    store.workflow_runs.insert(0, _workflow_run("run-persistence"))

    claim_response = _workflow_run(
        "run-persistence",
        dispatcher_id="dispatcher-a",
    )
    lease_expiration = fixed_now + timedelta(seconds=service._lease_seconds)
    claim_response["updated_at"] = fixed_now.isoformat()
    claim_response["dispatch_claimed_at"] = fixed_now.isoformat()
    claim_response["dispatch_lease_expires_at"] = lease_expiration.isoformat()

    persistence.claim_response = claim_response
    monkeypatch.setattr(dispatcher_module, "_utc_now", lambda: fixed_now)

    result = service.try_acquire_schedule_slot("run-persistence")

    assert result == claim_response
    assert store.workflow_runs[0] == result
    assert persistence.claim_calls == [
        {
            "run_id": "run-persistence",
            "dispatcher_id": "dispatcher-a",
            "claimed_at": fixed_now.isoformat(),
            "lease_expires_at": lease_expiration.isoformat(),
            "respect_existing_owner": True,
        }
    ]


def test_workflow_dispatcher_service_prefers_database_run_over_stale_runtime_cache() -> None:
    event_bus = FakeEventBus()
    persistence = FakePersistence()
    service = WorkflowDispatcherService(
        event_bus=event_bus,
        persistence=persistence,
        dispatcher_id="dispatcher-a",
    )

    stale_runtime_run = _workflow_run(
        "run-stale-dispatcher",
        dispatcher_id="dispatcher-other",
        dispatch_lease_expires_at=(datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
    )
    store.workflow_runs.insert(0, stale_runtime_run)
    persistence.database_runs["run-stale-dispatcher"] = _workflow_run(
        "run-stale-dispatcher",
        status="completed",
    )

    claimed = service.try_acquire_schedule_slot("run-stale-dispatcher")

    assert claimed is not None
    assert claimed["status"] == "completed"
    assert store.workflow_runs[0]["status"] == "completed"
    assert store.workflow_runs[0]["dispatcher_id"] is None
    assert persistence.claim_calls == []


def test_workflow_dispatcher_service_release_run_claim_prefers_persistence() -> None:
    event_bus = FakeEventBus()
    persistence = FakePersistence()
    service = WorkflowDispatcherService(
        event_bus=event_bus,
        persistence=persistence,
        dispatcher_id="dispatcher-a",
    )
    persistence.enabled = True

    store.workflow_runs.insert(
        0,
        _workflow_run(
            "run-release",
            dispatcher_id="dispatcher-a",
            dispatch_lease_expires_at=(datetime.now(UTC) + timedelta(seconds=15)).isoformat(),
        ),
    )

    release_response = _workflow_run("run-release")
    release_response["dispatcher_id"] = None
    release_response["dispatch_claimed_at"] = None
    release_response["dispatch_lease_expires_at"] = None
    persistence.release_response = release_response

    result = service.release_run_claim("run-release")

    assert result == release_response
    assert store.workflow_runs[0] == result
    assert persistence.release_calls == [
        {
            "run_id": "run-release",
            "dispatcher_id": "dispatcher-a",
        }
    ]


def test_workflow_dispatcher_service_dispatch_ready_run_publishes_execution_payload(monkeypatch) -> None:
    execution_subject = getattr(dispatcher_module, "WORKFLOW_EXECUTION_SUBJECT", None)
    if not execution_subject:
        pytest.skip("execution worker subject is not available in this branch")

    event_bus = FakeEventBus()
    persistence = FakePersistence()
    service = WorkflowDispatcherService(
        event_bus=event_bus,
        persistence=persistence,
        dispatcher_id="dispatcher-a",
    )

    run = _workflow_run("run-execution-ready")
    run["task_id"] = "task-run-execution-ready"
    run["workflow_id"] = "workflow-1"
    run["dispatch_context"] = {
        "state": "queued",
        "route_decision": {"execution_agent_id": "search"},
        "execution_agent_id": "search",
    }
    store.workflow_runs.insert(0, run)

    monkeypatch.setattr(
        workflow_execution_service,
        "dispatch_workflow_run",
        lambda run_id: {"id": run_id, "status": "running"},
    )
    monkeypatch.setattr(
        workflow_execution_service,
        "execute_workflow_run",
        lambda _run_id: (_ for _ in ()).throw(
            AssertionError("dispatch-ready run should not execute locally")
        ),
    )

    result = service.process_tick("run-execution-ready", step_delay=0.65)

    assert result is not None
    execution_events = [item for item in event_bus.published if item[0] == execution_subject]
    assert len(execution_events) == 1
    payload = execution_events[0][1]
    assert payload["run_id"] == "run-execution-ready"
    assert payload["task_id"] == "task-run-execution-ready"
    assert payload["workflow_id"] == "workflow-1"
    assert payload.get("step_delay") == 0.65
    assert payload["message_type"] == "command"
    assert payload["message_name"] == "workflow.execution.request"
    assert payload["request_id"] is not None
    assert payload["correlation_id"] is not None
    assert payload["attempt"] == 1
    assert payload["max_attempts"] == dispatcher_module.MAX_DISPATCH_FAILURE_COUNT
    persisted_run = next(item for item in store.workflow_runs if item["id"] == "run-execution-ready")
    assert persisted_run["dispatch_context"]["protocol"]["request_id"] == payload["request_id"]


def test_workflow_dispatcher_service_preserves_retry_attempt_from_run_protocol(monkeypatch) -> None:
    execution_subject = getattr(dispatcher_module, "WORKFLOW_EXECUTION_SUBJECT", None)
    if not execution_subject:
        pytest.skip("execution worker subject is not available in this branch")

    event_bus = FakeEventBus()
    persistence = FakePersistence()
    service = WorkflowDispatcherService(
        event_bus=event_bus,
        persistence=persistence,
        dispatcher_id="dispatcher-a",
    )

    run = _workflow_run("run-execution-retry", dispatch_failure_count=0)
    run["task_id"] = "task-run-execution-retry"
    run["workflow_id"] = "workflow-1"
    run["dispatch_context"] = {
        "state": "queued",
        "execution_agent_id": "search",
        "protocol": {
            "request_id": "req-execution-retry",
            "correlation_id": "msg-execution-retry-1",
            "message_id": "msg-execution-retry-1",
            "attempt": 2,
            "max_attempts": 4,
            "last_error": "retry boom",
        },
    }
    store.workflow_runs.insert(0, run)

    monkeypatch.setattr(
        workflow_execution_service,
        "dispatch_workflow_run",
        lambda run_id: {"id": run_id, "status": "running"},
    )
    monkeypatch.setattr(
        workflow_execution_service,
        "execute_workflow_run",
        lambda _run_id: (_ for _ in ()).throw(
            AssertionError("retry-ready run should stay on execution worker path")
        ),
    )

    result = service.process_tick("run-execution-retry", step_delay=0.65)

    assert result is not None
    execution_events = [item for item in event_bus.published if item[0] == execution_subject]
    assert len(execution_events) == 1
    payload = execution_events[0][1]
    assert payload["attempt"] == 2
    assert payload["max_attempts"] == 4
    assert payload["request_id"] == "req-execution-retry"


def test_workflow_dispatcher_service_dispatch_ready_run_normalizes_camel_case_handoff_fields(
    monkeypatch,
) -> None:
    execution_subject = getattr(dispatcher_module, "WORKFLOW_EXECUTION_SUBJECT", None)
    if not execution_subject:
        pytest.skip("execution worker subject is not available in this branch")

    event_bus = FakeEventBus()
    persistence = FakePersistence()
    service = WorkflowDispatcherService(
        event_bus=event_bus,
        persistence=persistence,
        dispatcher_id="dispatcher-a",
    )

    run = _workflow_run("run-execution-camel")
    run["task_id"] = "task-run-execution-camel"
    run["workflow_id"] = "workflow-1"
    run["dispatch_context"] = {
        "dispatchState": "executing",
        "routeDecision": {"executionAgentId": "agent-camel"},
    }
    store.workflow_runs.insert(0, run)

    monkeypatch.setattr(
        workflow_execution_service,
        "dispatch_workflow_run",
        lambda run_id: {"id": run_id, "status": "running"},
    )
    monkeypatch.setattr(
        workflow_execution_service,
        "execute_workflow_run",
        lambda _run_id: (_ for _ in ()).throw(
            AssertionError("camelCase handoff should stay on execution worker path")
        ),
    )

    result = service.process_tick("run-execution-camel", step_delay=1.1)

    assert result is not None
    execution_events = [item for item in event_bus.published if item[0] == execution_subject]
    assert len(execution_events) == 1
    payload = execution_events[0][1]
    assert payload["run_id"] == "run-execution-camel"
    assert payload["dispatcher_id"] == "dispatcher-a"
    assert payload["step_delay"] == 1.1
    assert payload["dispatch_context"] == {
        "state": "executing",
        "execution_agent_id": "agent-camel",
    }
    assert payload["message_type"] == "command"
    assert payload["message_name"] == "workflow.execution.request"
    assert payload["request_id"] is not None
    assert payload["correlation_id"] is not None


def test_workflow_dispatcher_service_keeps_worker_path_when_execution_publish_fails_but_job_is_durable(
    monkeypatch,
) -> None:
    event_bus = FakeEventBus(publish_result=False)
    persistence = FakePersistence()
    persistence.enabled = True
    service = WorkflowDispatcherService(
        event_bus=event_bus,
        persistence=persistence,
        dispatcher_id="dispatcher-a",
    )
    scheduled: list[tuple[str, float, float]] = []
    store.workflow_runs.insert(0, _workflow_run("run-durable-execution"))
    persistence.claim_response = _workflow_run(
        "run-durable-execution",
        dispatcher_id="dispatcher-a",
    )

    monkeypatch.setattr(
        workflow_execution_service,
        "dispatch_workflow_run",
        lambda run_id: {"id": run_id, "status": "running"},
    )
    monkeypatch.setattr(
        workflow_execution_service,
        "execute_workflow_run",
        lambda _run_id: (_ for _ in ()).throw(
            AssertionError("durable execution job should keep dispatcher off the local execute path")
        ),
    )
    monkeypatch.setattr(
        workflow_scheduler_service,
        "schedule",
        lambda run_id, *, delay, step_delay: scheduled.append((run_id, delay, step_delay)),
    )

    result = service.process_tick("run-durable-execution", step_delay=0.7)

    assert result is not None
    assert scheduled == [("run-durable-execution", 0.7, 0.7)]
    assert persistence.execution_job_upserts
    assert persistence.execution_job_upserts[0]["run_id"] == "run-durable-execution"
