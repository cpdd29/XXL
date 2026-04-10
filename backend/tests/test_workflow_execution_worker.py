from __future__ import annotations

import asyncio
import inspect
from typing import Any

import pytest

from app.services import workflow_execution_service
from app.services.store import store


worker_module = pytest.importorskip("app.services.workflow_execution_worker_service")
WorkflowExecutionWorkerService = getattr(
    worker_module,
    "WorkflowExecutionWorkerService",
    None,
)
if WorkflowExecutionWorkerService is None:
    pytest.skip("WorkflowExecutionWorkerService is not available", allow_module_level=True)


class FakeEventBus:
    def __init__(self) -> None:
        self.subscriptions: list[tuple[str, str, object]] = []
        self.published: list[tuple[str, dict]] = []

    def subscribe(self, subject: str, handler, *, queue_group: str = "") -> None:
        self.subscriptions.append((subject, queue_group, handler))

    def publish_json(self, subject: str, payload: dict) -> bool:
        self.published.append((subject, payload))
        return True


class FakePersistence:
    def __init__(self, *, due_jobs: list[dict] | None = None, runs: list[dict] | None = None) -> None:
        self.enabled = True
        self.due_jobs = due_jobs or []
        self.jobs: dict[str, dict] = {
            str(job.get("run_id") or ""): dict(job) for job in (due_jobs or [])
        }
        self.runs: dict[str, dict] = {
            str(run.get("id") or ""): dict(run) for run in (runs or [])
        }
        self.upserted_jobs: list[dict] = []

    def claim_due_workflow_execution_jobs(self, **_kwargs) -> list[dict]:
        return [dict(job) for job in self.due_jobs]

    def claim_workflow_execution_job(self, run_id: str, **kwargs) -> dict | None:
        job = self.jobs.get(run_id)
        if job is None:
            return None
        claimed = dict(job)
        claimed["worker_id"] = kwargs["worker_id"]
        claimed["claimed_at"] = kwargs["claimed_at"]
        claimed["lease_expires_at"] = kwargs["lease_expires_at"]
        self.jobs[run_id] = dict(claimed)
        return claimed

    def delete_workflow_execution_job(self, run_id: str, **_kwargs) -> bool:
        self.jobs.pop(run_id, None)
        return True

    def get_workflow_execution_job(self, run_id: str) -> dict | None:
        job = self.jobs.get(run_id)
        return dict(job) if job is not None else None

    def upsert_workflow_execution_job(self, run_id: str, **kwargs) -> dict:
        payload = {
            "run_id": run_id,
            "available_at": kwargs["available_at"],
            "step_delay_seconds": kwargs.get("step_delay_seconds"),
            "worker_id": None,
            "claimed_at": None,
            "lease_expires_at": None,
            "created_at": kwargs["queued_at"],
            "updated_at": kwargs["queued_at"],
        }
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
        self.jobs[run_id] = dict(payload)
        self.upserted_jobs.append(dict(payload))
        return payload

    def get_workflow_run(self, run_id: str) -> dict | None:
        run = self.runs.get(run_id)
        return dict(run) if run is not None else None

    def persist_execution_state(self, *, workflow_run: dict | None = None, **_: object) -> bool:
        if workflow_run is None:
            return False
        self.runs[str(workflow_run.get("id") or "")] = dict(workflow_run)
        return True

    def persist_runtime_state(self) -> bool:
        return True


def _build_worker_service(event_bus: FakeEventBus, persistence: FakePersistence | None = None):
    signature = inspect.signature(WorkflowExecutionWorkerService)
    kwargs: dict[str, Any] = {}
    if "event_bus" in signature.parameters:
        kwargs["event_bus"] = event_bus
    if "dispatcher" in signature.parameters:
        kwargs["dispatcher"] = None
    if "persistence" in signature.parameters:
        kwargs["persistence"] = persistence
    return WorkflowExecutionWorkerService(**kwargs)


def _invoke_handler(handler, subject: str, payload: dict) -> None:
    result = handler(subject, payload)
    if inspect.isawaitable(result):
        asyncio.run(result)


def test_workflow_execution_worker_service_subscribes_execution_queue() -> None:
    event_bus = FakeEventBus()
    service = _build_worker_service(event_bus)
    _ = service

    execution_subject = getattr(
        worker_module,
        "WORKFLOW_EXECUTION_SUBJECT",
        "workflow.dispatch.execution",
    )
    execution_queue = getattr(
        worker_module,
        "WORKFLOW_EXECUTION_QUEUE",
        "workflow_execution_workers",
    )
    assert event_bus.subscriptions
    assert event_bus.subscriptions[0][0] == execution_subject
    assert event_bus.subscriptions[0][1] == execution_queue


def test_workflow_execution_worker_service_consumes_payload_and_executes_locally(
    monkeypatch,
) -> None:
    event_bus = FakeEventBus()
    persistence = FakePersistence(
        runs=[
            {
                "id": "run-worker-1",
                "workflow_id": "workflow-1",
                "task_id": "task-worker-1",
                "status": "running",
                "dispatch_context": {},
            }
        ]
    )
    service = _build_worker_service(event_bus, persistence=persistence)
    _ = service

    assert event_bus.subscriptions
    _subject, _queue, handler = event_bus.subscriptions[0]
    execute_calls: list[str] = []

    monkeypatch.setattr(
        workflow_execution_service,
        "execute_workflow_run",
        lambda run_id: execute_calls.append(run_id) or {"id": run_id, "status": "running"},
    )

    _invoke_handler(
        handler,
        getattr(worker_module, "WORKFLOW_EXECUTION_SUBJECT", "workflow.dispatch.execution"),
        {
            "run_id": "run-worker-1",
            "task_id": "task-worker-1",
            "workflow_id": "workflow-1",
            "step_delay": 0.6,
            "message_type": "command",
            "message_name": "workflow.execution.request",
            "request_id": "req-worker-1",
            "correlation_id": "req-worker-1",
            "message_id": "msg-worker-command-1",
            "attempt": 1,
            "max_attempts": 4,
            "dispatch_context": {
                "state": "dispatched",
                "execution_agent_id": "search",
            },
        },
    )

    assert execute_calls == ["run-worker-1"]
    result_events = [item for item in event_bus.published if item[0] == worker_module.WORKFLOW_EXECUTION_RESULT_SUBJECT]
    assert len(result_events) == 1
    result_payload = result_events[0][1]
    assert result_payload["message_type"] == "result"
    assert result_payload["message_name"] == "workflow.execution.completed"
    assert result_payload["request_id"] == "req-worker-1"
    assert result_payload["correlation_id"] == "msg-worker-command-1"


def test_workflow_execution_worker_service_consumes_camel_case_payload_and_step_delay(
    monkeypatch,
) -> None:
    event_bus = FakeEventBus()
    persistence = FakePersistence(
        runs=[
            {
                "id": "run-worker-camel",
                "status": "running",
                "dispatcher_id": "dispatcher-camel",
            }
        ]
    )
    service = _build_worker_service(event_bus, persistence=persistence)
    _ = service

    assert event_bus.subscriptions
    _subject, _queue, handler = event_bus.subscriptions[0]
    execute_calls: list[str] = []
    released: list[str] = []

    monkeypatch.setattr(
        workflow_execution_service,
        "execute_workflow_run",
        lambda run_id: execute_calls.append(run_id)
        or {"id": run_id, "status": "completed", "dispatcher_id": "dispatcher-camel"},
    )
    monkeypatch.setattr(
        "app.services.workflow_dispatcher_service.workflow_dispatcher_service.release_run_claim",
        lambda run_id: released.append(run_id),
    )

    _invoke_handler(
        handler,
        getattr(worker_module, "WORKFLOW_EXECUTION_SUBJECT", "workflow.dispatch.execution"),
        {
            "runId": "run-worker-camel",
            "taskId": "task-worker-camel",
            "workflowId": "workflow-1",
            "stepDelay": 1.25,
            "dispatcherId": "dispatcher-camel",
            "request_id": "req-worker-camel",
            "correlation_id": "req-worker-camel",
            "message_id": "msg-worker-camel-1",
            "attempt": 1,
            "max_attempts": 3,
            "publishedAt": "2026-04-07T10:00:00+00:00",
        },
    )

    assert execute_calls == ["run-worker-camel"]
    assert released == ["run-worker-camel"]
    assert persistence.upserted_jobs[0]["run_id"] == "run-worker-camel"
    assert persistence.upserted_jobs[0]["available_at"] == "2026-04-07T10:00:00+00:00"
    assert persistence.upserted_jobs[0]["step_delay_seconds"] == 1.25
    assert persistence.upserted_jobs[0]["request_id"] == "req-worker-camel"
    assert persistence.get_workflow_execution_job("run-worker-camel") is None
    result_events = [item for item in event_bus.published if item[0] == worker_module.WORKFLOW_EXECUTION_RESULT_SUBJECT]
    assert len(result_events) == 1
    assert result_events[0][1]["request_id"] == "req-worker-camel"


def test_workflow_execution_worker_service_defers_and_releases_claim_when_execution_fails(
    monkeypatch,
) -> None:
    event_bus = FakeEventBus()
    service = _build_worker_service(event_bus)
    _ = service

    assert event_bus.subscriptions
    _subject, _queue, handler = event_bus.subscriptions[0]
    deferred: list[tuple[str, float, float, str | None]] = []
    released: list[str] = []

    monkeypatch.setattr(
        workflow_execution_service,
        "execute_workflow_run",
        lambda _run_id: (_ for _ in ()).throw(RuntimeError("worker boom")),
    )
    monkeypatch.setattr(
        "app.services.workflow_scheduler_service.workflow_scheduler_service.defer",
        lambda run_id, *, delay, step_delay=None, dispatcher_id=None: deferred.append(
            (run_id, delay, step_delay, dispatcher_id)
        ),
    )
    monkeypatch.setattr(
        "app.services.workflow_dispatcher_service.workflow_dispatcher_service.release_run_claim",
        lambda run_id: released.append(run_id),
    )

    _invoke_handler(
        handler,
        getattr(worker_module, "WORKFLOW_EXECUTION_SUBJECT", "workflow.dispatch.execution"),
        {
            "run_id": "run-worker-failure",
            "task_id": "task-worker-failure",
            "workflow_id": "workflow-1",
            "step_delay": 0.2,
            "dispatcher_id": "dispatcher-a",
            "request_id": "req-worker-failure",
            "correlation_id": "req-worker-failure",
            "message_id": "msg-worker-failure-1",
            "attempt": 1,
            "max_attempts": 3,
        },
    )

    assert deferred == [("run-worker-failure", 0.5, 0.2, "dispatcher-a")]
    assert released == ["run-worker-failure"]
    deferred_events = [item for item in event_bus.published if item[0] == worker_module.WORKFLOW_EXECUTION_EVENT_SUBJECT]
    assert len(deferred_events) == 1
    assert deferred_events[0][1]["message_name"] == "workflow.execution.deferred"
    assert deferred_events[0][1]["request_id"] == "req-worker-failure"


def test_workflow_execution_worker_service_polls_due_execution_jobs(monkeypatch) -> None:
    event_bus = FakeEventBus()
    persistence = FakePersistence(
        due_jobs=[
            {
                "run_id": "run-polled-1",
                "available_at": "2026-04-07T10:00:00+00:00",
                "step_delay_seconds": 0.4,
                "claimed_at": "2026-04-07T10:00:00+00:00",
            }
        ],
        runs=[
            {
                "id": "run-polled-1",
                "status": "running",
                "dispatcher_id": "dispatcher-polled",
            }
        ],
    )
    service = _build_worker_service(event_bus, persistence=persistence)
    executed: list[str] = []

    monkeypatch.setattr(
        workflow_execution_service,
        "execute_workflow_run",
        lambda run_id: executed.append(run_id) or {"id": run_id, "status": "completed"},
    )

    summary = service.poll_once()

    assert summary["executed"] == 1
    assert executed == ["run-polled-1"]
    assert persistence.get_workflow_execution_job("run-polled-1") is None


def test_workflow_execution_worker_service_ignores_stale_runtime_run_when_database_run_is_missing(
    monkeypatch,
) -> None:
    event_bus = FakeEventBus()
    persistence = FakePersistence()
    service = _build_worker_service(event_bus, persistence=persistence)
    _ = service

    assert event_bus.subscriptions
    _subject, _queue, handler = event_bus.subscriptions[0]
    execute_calls: list[str] = []
    released: list[str] = []

    monkeypatch.setattr(
        workflow_execution_service,
        "execute_workflow_run",
        lambda run_id: execute_calls.append(run_id) or {"id": run_id, "status": "running"},
    )
    monkeypatch.setattr(
        "app.services.workflow_dispatcher_service.workflow_dispatcher_service.release_run_claim",
        lambda run_id: released.append(run_id),
    )
    monkeypatch.setattr(
        store,
        "workflow_runs",
        [
            {
                "id": "run-worker-stale",
                "status": "running",
                "dispatcher_id": "dispatcher-stale",
            }
        ],
        raising=False,
    )

    _invoke_handler(
        handler,
        getattr(worker_module, "WORKFLOW_EXECUTION_SUBJECT", "workflow.dispatch.execution"),
        {
            "run_id": "run-worker-stale",
            "task_id": "task-worker-stale",
            "workflow_id": "workflow-stale",
            "step_delay": 0.2,
            "dispatcher_id": "dispatcher-stale",
        },
    )

    assert execute_calls == []
    assert released == ["run-worker-stale"]
    assert persistence.get_workflow_execution_job("run-worker-stale") is None
