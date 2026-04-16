from __future__ import annotations

import asyncio
import inspect
from typing import Any

import pytest

from app.services import workflow_execution_service


worker_module = pytest.importorskip("app.services.agent_execution_worker_service")
AgentExecutionWorkerService = getattr(
    worker_module,
    "AgentExecutionWorkerService",
    None,
)
if AgentExecutionWorkerService is None:
    pytest.skip("AgentExecutionWorkerService is not available", allow_module_level=True)


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
    def __init__(
        self,
        *,
        due_jobs: list[dict] | None = None,
        tasks: list[dict] | None = None,
        runs: list[dict] | None = None,
    ) -> None:
        self.enabled = True
        self.due_jobs = due_jobs or []
        self.jobs: dict[str, dict] = {
            str(job.get("run_id") or ""): dict(job) for job in (due_jobs or [])
        }
        self.tasks: dict[str, dict] = {
            str(task.get("id") or ""): dict(task) for task in (tasks or [])
        }
        self.runs: dict[str, dict] = {
            str(run.get("id") or ""): dict(run) for run in (runs or [])
        }
        self.upserted_jobs: list[dict] = []

    def claim_due_agent_execution_jobs(self, **_kwargs) -> list[dict]:
        return [dict(job) for job in self.due_jobs]

    def claim_agent_execution_job(self, run_id: str, **kwargs) -> dict | None:
        job = self.jobs.get(run_id)
        if job is None:
            return None
        claimed = dict(job)
        claimed["worker_id"] = kwargs["worker_id"]
        claimed["claimed_at"] = kwargs["claimed_at"]
        claimed["lease_expires_at"] = kwargs["lease_expires_at"]
        self.jobs[run_id] = dict(claimed)
        return claimed

    def delete_agent_execution_job(self, run_id: str, **_kwargs) -> bool:
        self.jobs.pop(run_id, None)
        return True

    def get_agent_execution_job(self, run_id: str) -> dict | None:
        job = self.jobs.get(run_id)
        return dict(job) if job is not None else None

    def upsert_agent_execution_job(self, run_id: str, **kwargs) -> dict:
        payload = {
            "run_id": run_id,
            "task_id": kwargs["task_id"],
            "workflow_id": kwargs["workflow_id"],
            "execution_agent_id": kwargs.get("execution_agent_id"),
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
            "emitted_at",
            "available_at",
            "dead_letter",
            "dead_letter_reason",
            "last_error",
        ):
            if key in kwargs:
                payload[key] = kwargs.get(key)
        self.jobs[run_id] = dict(payload)
        self.upserted_jobs.append(dict(payload))
        return payload

    def get_task(self, task_id: str) -> dict | None:
        task = self.tasks.get(task_id)
        return dict(task) if task is not None else None

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
    signature = inspect.signature(AgentExecutionWorkerService)
    kwargs: dict[str, Any] = {}
    if "event_bus" in signature.parameters:
        kwargs["event_bus"] = event_bus
    if "persistence" in signature.parameters:
        kwargs["persistence"] = persistence
    return AgentExecutionWorkerService(**kwargs)


def _invoke_handler(handler, subject: str, payload: dict) -> None:
    result = handler(subject, payload)
    if inspect.isawaitable(result):
        asyncio.run(result)


def test_agent_execution_worker_service_subscribes_execution_queue() -> None:
    event_bus = FakeEventBus()
    service = _build_worker_service(event_bus)
    _ = service

    assert event_bus.subscriptions
    assert event_bus.subscriptions[0][0] == worker_module.AGENT_EXECUTION_SUBJECT
    assert event_bus.subscriptions[0][1] == worker_module.AGENT_EXECUTION_QUEUE


def test_agent_execution_worker_service_enqueues_and_publishes() -> None:
    event_bus = FakeEventBus()
    persistence = FakePersistence()
    service = _build_worker_service(event_bus, persistence=persistence)

    queued = service.enqueue_execution(
        run_id="run-agent-1",
        task_id="task-agent-1",
        workflow_id="workflow-1",
        execution_agent_id="agent-search",
        step_delay=0.6,
        published_at="2026-04-08T10:00:00+00:00",
    )

    assert queued is True
    assert persistence.upserted_jobs[0]["run_id"] == "run-agent-1"
    assert persistence.upserted_jobs[0]["execution_agent_id"] == "agent-search"
    subject, payload = event_bus.published[0]
    assert subject == worker_module.AGENT_EXECUTION_SUBJECT
    assert payload["message_type"] == "command"
    assert payload["message_name"] == "agent.execution.request"
    assert payload["run_id"] == "run-agent-1"
    assert payload["task_id"] == "task-agent-1"
    assert payload["workflow_id"] == "workflow-1"
    assert payload["execution_agent_id"] == "agent-search"
    assert payload["payload"]["run_id"] == "run-agent-1"
    assert payload["request_id"] is not None
    assert payload["correlation_id"] is not None
    assert payload["attempt"] == 1
    assert payload["max_attempts"] == 3
    assert persistence.upserted_jobs[0]["request_id"] == payload["request_id"]
    assert persistence.upserted_jobs[0]["message_type"] == "command"
    assert any(item[0] == "brain.agent.execution.request" for item in event_bus.published)


def test_agent_execution_worker_service_consumes_payload_and_completes_job(monkeypatch) -> None:
    event_bus = FakeEventBus()
    persistence = FakePersistence(
        tasks=[{"id": "task-agent-1", "status": "running"}],
        runs=[
            {
                "id": "run-agent-1",
                "task_id": "task-agent-1",
                "workflow_id": "workflow-1",
                "status": "running",
                "dispatch_context": {},
            }
        ],
    )
    service = _build_worker_service(event_bus, persistence=persistence)
    _ = service

    assert event_bus.subscriptions
    _subject, _queue, handler = event_bus.subscriptions[0]
    completed: list[tuple[str, str | None]] = []

    monkeypatch.setattr(
        workflow_execution_service,
        "complete_agent_execution_job",
        lambda run_id, *, execution_agent_id=None: completed.append((run_id, execution_agent_id))
        or {"id": run_id, "status": "completed"},
    )

    _invoke_handler(
        handler,
        worker_module.AGENT_EXECUTION_SUBJECT,
        {
            "run_id": "run-agent-1",
            "task_id": "task-agent-1",
            "workflow_id": "workflow-1",
            "execution_agent_id": "agent-search",
            "message_type": "command",
            "message_name": "agent.execution.request",
            "request_id": "req-agent-1",
            "correlation_id": "req-agent-1",
            "message_id": "msg-agent-command-1",
            "attempt": 1,
            "max_attempts": 3,
            "published_at": "2026-04-08T10:00:00+00:00",
            "step_delay": 0.6,
        },
    )

    assert completed == [("run-agent-1", "agent-search")]
    assert persistence.get_agent_execution_job("run-agent-1") is None
    result_events = [item for item in event_bus.published if item[0] == worker_module.AGENT_EXECUTION_RESULT_SUBJECT]
    assert len(result_events) == 1
    assert any(item[0] == "brain.agent.execution.claimed" for item in event_bus.published)
    assert any(item[0] == "brain.agent.execution.started" for item in event_bus.published)
    assert any(item[0] == "brain.agent.execution.completed" for item in event_bus.published)
    result_payload = result_events[0][1]
    assert result_payload["message_type"] == "result"
    assert result_payload["message_name"] == "agent.execution.completed"
    assert result_payload["request_id"] == "req-agent-1"
    assert result_payload["correlation_id"] == "msg-agent-command-1"
    assert result_payload["execution_agent_id"] == "agent-search"


def test_agent_execution_worker_service_marks_failure_when_completion_raises(monkeypatch) -> None:
    event_bus = FakeEventBus()
    persistence = FakePersistence(
        tasks=[{"id": "task-agent-failure", "status": "running"}],
        due_jobs=[
            {
                "run_id": "run-agent-failure",
                "task_id": "task-agent-failure",
                "workflow_id": "workflow-1",
                "execution_agent_id": "agent-write",
                "available_at": "2026-04-08T10:00:00+00:00",
                "claimed_at": "2026-04-08T10:00:00+00:00",
                "request_id": "req-agent-failure",
                "correlation_id": "msg-agent-failure-1",
                "message_id": "msg-agent-failure-1",
                "attempt": 1,
                "max_attempts": 3,
            }
        ],
    )
    service = _build_worker_service(event_bus, persistence=persistence)
    failures: list[tuple[str, str]] = []

    monkeypatch.setattr(
        workflow_execution_service,
        "complete_agent_execution_job",
        lambda run_id, *, execution_agent_id=None: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(
        workflow_execution_service,
        "fail_workflow_run_due_agent_execution_error",
        lambda run_id, *, failure_message: failures.append((run_id, failure_message))
        or {"id": run_id, "status": "failed"},
    )

    summary = service.poll_once()

    assert summary["skipped_claimed"] == 1
    assert failures == []
    requeued_job = persistence.get_agent_execution_job("run-agent-failure")
    assert requeued_job is not None
    assert requeued_job["attempt"] == 2
    assert requeued_job["request_id"] == "req-agent-failure"
    command_events = [item for item in event_bus.published if item[0] == worker_module.AGENT_EXECUTION_SUBJECT]
    assert len(command_events) == 1
    assert command_events[0][1]["attempt"] == 2
    retry_events = [
        item
        for item in event_bus.published
        if item[0] == worker_module.AGENT_EXECUTION_EVENT_SUBJECT
        and item[1]["message_name"] == "agent.execution.retry_scheduled"
    ]
    assert len(retry_events) == 1
    assert retry_events[0][1]["request_id"] == "req-agent-failure"
    assert any(item[0] == "brain.agent.execution.claimed" for item in event_bus.published)
    assert any(item[0] == "brain.agent.execution.started" for item in event_bus.published)


def test_agent_execution_worker_service_marks_dead_letter_after_max_attempts(monkeypatch) -> None:
    event_bus = FakeEventBus()
    persistence = FakePersistence(
        tasks=[{"id": "task-agent-dead-letter", "status": "running"}],
        due_jobs=[
            {
                "run_id": "run-agent-dead-letter",
                "task_id": "task-agent-dead-letter",
                "workflow_id": "workflow-1",
                "execution_agent_id": "agent-write",
                "available_at": "2026-04-08T10:00:00+00:00",
                "claimed_at": "2026-04-08T10:00:00+00:00",
                "request_id": "req-agent-dead-letter",
                "correlation_id": "msg-agent-dead-letter-3",
                "message_id": "msg-agent-dead-letter-3",
                "attempt": 3,
                "max_attempts": 3,
            }
        ],
    )
    service = _build_worker_service(event_bus, persistence=persistence)
    failures: list[tuple[str, str]] = []

    monkeypatch.setattr(
        workflow_execution_service,
        "complete_agent_execution_job",
        lambda run_id, *, execution_agent_id=None: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(
        workflow_execution_service,
        "fail_workflow_run_due_agent_execution_error",
        lambda run_id, *, failure_message: failures.append((run_id, failure_message))
        or {"id": run_id, "status": "failed"},
    )

    summary = service.poll_once()

    assert summary["skipped_claimed"] == 1
    assert failures == [("run-agent-dead-letter", "Agent 执行失败并进入死信：boom")]
    assert persistence.get_agent_execution_job("run-agent-dead-letter") is None
    dead_letter_events = [
        item
        for item in event_bus.published
        if item[0] == worker_module.AGENT_EXECUTION_EVENT_SUBJECT
        and item[1]["message_name"] == "agent.execution.dead_lettered"
    ]
    assert len(dead_letter_events) == 1
    dead_letter_payload = dead_letter_events[0][1]
    assert dead_letter_payload["message_name"] == "agent.execution.dead_lettered"
    assert dead_letter_payload["dead_letter"] is True
    assert dead_letter_payload["dead_letter_reason"] == "boom"
    assert dead_letter_payload["request_id"] == "req-agent-dead-letter"
    assert any(item[0] == "brain.agent.execution.failed" for item in event_bus.published)
