from __future__ import annotations

import asyncio
import json

from app.core.nats_event_bus import NatsEventBus
from app.services.store import store
from app.services.workflow_realtime_service import WorkflowRealtimeService


class FakeNatsMessage:
    def __init__(self, subject: str, data: bytes) -> None:
        self.subject = subject
        self.data = data


class FakeNatsSubscription:
    def __init__(self, subject: str, queue: str) -> None:
        self.subject = subject
        self.queue = queue
        self.unsubscribed = False

    async def unsubscribe(self) -> None:
        self.unsubscribed = True


class FakeNatsClient:
    def __init__(self) -> None:
        self.is_connected = True
        self.is_closed = False
        self.drained = False
        self.published: list[tuple[str, dict]] = []
        self._subscriptions: dict[str, tuple[FakeNatsSubscription, object]] = {}

    async def subscribe(self, subject: str, queue: str = "", cb=None):
        subscription = FakeNatsSubscription(subject, queue)
        self._subscriptions[f"{subject}::{queue}"] = (subscription, cb)
        return subscription

    async def publish(self, subject: str, data: bytes) -> None:
        payload = json.loads(data.decode("utf-8"))
        self.published.append((subject, payload))
        await self.emit(subject, payload)

    async def flush(self, timeout=None) -> None:
        _ = timeout
        return None

    async def drain(self) -> None:
        self.drained = True
        self.is_closed = True
        self.is_connected = False

    async def emit(self, subject: str, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        for key, (_, callback) in list(self._subscriptions.items()):
            pattern, _, _queue = key.partition("::")
            if self._matches(pattern, subject):
                await callback(FakeNatsMessage(subject, data))

    @staticmethod
    def _matches(pattern: str, subject: str) -> bool:
        if pattern.endswith(".*"):
            prefix = pattern[:-1]
            return subject.startswith(prefix)
        return pattern == subject


def test_nats_event_bus_publish_round_trips_to_wildcard_subscribers() -> None:
    fake_client = FakeNatsClient()
    event_bus = NatsEventBus(
        retry_interval_seconds=0,
        client_factory_override=lambda: fake_client,
    )
    received: list[tuple[str, dict]] = []
    event_bus.subscribe("workflow.runs.*", lambda subject, payload: received.append((subject, payload)))

    try:
        published = event_bus.publish_json(
            "workflow.runs.workflow-1",
            {
                "type": "workflow_run.updated",
                "workflowId": "workflow-1",
                "run": {"id": "run-1"},
            },
        )

        assert published is True
        assert received == [
            (
                "workflow.runs.workflow-1",
                {
                    "type": "workflow_run.updated",
                    "workflowId": "workflow-1",
                    "run": {"id": "run-1"},
                },
            )
        ]
        assert fake_client.published[0][0] == "workflow.runs.workflow-1"
    finally:
        event_bus.close()

    assert fake_client.drained is True


def test_workflow_realtime_service_uses_nats_bus_when_available() -> None:
    fake_client = FakeNatsClient()
    event_bus = NatsEventBus(
        retry_interval_seconds=0,
        client_factory_override=lambda: fake_client,
    )
    realtime_service = WorkflowRealtimeService(event_bus=event_bus)
    created_at = store.now_string()
    run = {
        "id": "run-nats-1",
        "workflow_id": "workflow-1",
        "workflow_name": "工作流一",
        "task_id": "task-1",
        "trigger": "manual",
        "intent": "search",
        "status": "running",
        "created_at": created_at,
        "updated_at": created_at,
        "started_at": created_at,
        "completed_at": None,
        "current_stage": "执行中",
        "active_edges": [],
        "nodes": [],
        "logs": [],
    }
    store.workflow_runs.insert(0, run)
    subscriber = realtime_service._subscribe("workflow-1")

    try:
        realtime_service.publish_run_event(run, "workflow_run.created")
        payload = subscriber.get(timeout=1.0)

        assert payload["type"] == "workflow_run.created"
        assert payload["workflowId"] == "workflow-1"
        assert payload["run"]["id"] == "run-nats-1"
        assert fake_client.published[0][0] == "workflow.runs.workflow-1"
    finally:
        realtime_service._unsubscribe("workflow-1", subscriber)
        event_bus.close()


def test_workflow_realtime_service_falls_back_to_local_broadcast_when_nats_unavailable() -> None:
    def failing_client_factory():
        raise RuntimeError("nats unavailable")

    event_bus = NatsEventBus(
        retry_interval_seconds=0,
        client_factory_override=failing_client_factory,
    )
    realtime_service = WorkflowRealtimeService(event_bus=event_bus)
    created_at = store.now_string()
    run = {
        "id": "run-local-1",
        "workflow_id": "workflow-local",
        "workflow_name": "本地回退工作流",
        "task_id": "task-local",
        "trigger": "manual",
        "intent": "help",
        "status": "running",
        "created_at": created_at,
        "updated_at": created_at,
        "started_at": created_at,
        "completed_at": None,
        "current_stage": "执行中",
        "active_edges": [],
        "nodes": [],
        "logs": [],
    }
    store.workflow_runs.insert(0, run)
    subscriber = realtime_service._subscribe("workflow-local")

    try:
        realtime_service.publish_run_event(run, "workflow_run.updated")
        payload = subscriber.get(timeout=1.0)

        assert payload["type"] == "workflow_run.updated"
        assert payload["workflowId"] == "workflow-local"
        assert payload["run"]["id"] == "run-local-1"
    finally:
        realtime_service._unsubscribe("workflow-local", subscriber)
        event_bus.close()


def test_nats_event_bus_can_consume_remote_workflow_events() -> None:
    fake_client = FakeNatsClient()
    event_bus = NatsEventBus(
        retry_interval_seconds=0,
        client_factory_override=lambda: fake_client,
    )
    received: list[tuple[str, dict]] = []
    event_bus.subscribe("workflow.runs.*", lambda subject, payload: received.append((subject, payload)))

    try:
        assert event_bus.initialize() is True
        asyncio.run(
            fake_client.emit(
                "workflow.runs.workflow-remote",
                {
                    "type": "workflow_run.updated",
                    "workflowId": "workflow-remote",
                    "run": {"id": "run-remote"},
                },
            )
        )

        assert received == [
            (
                "workflow.runs.workflow-remote",
                {
                    "type": "workflow_run.updated",
                    "workflowId": "workflow-remote",
                    "run": {"id": "run-remote"},
                },
            )
        ]
    finally:
        event_bus.close()


def test_nats_event_bus_round_trips_protocol_envelopes_without_mutation() -> None:
    fake_client = FakeNatsClient()
    event_bus = NatsEventBus(
        retry_interval_seconds=0,
        client_factory_override=lambda: fake_client,
    )
    received: list[tuple[str, dict]] = []
    event_bus.subscribe("agent.execution.*", lambda subject, payload: received.append((subject, payload)))

    command_payload = {
        "spec_version": "agentbus.v1",
        "message_id": "msg-command-1",
        "message_type": "command",
        "message_name": "agent.execution.request",
        "request_id": "req-1",
        "correlation_id": "req-1",
        "idempotency_key": "agent.execution.request:run-1",
        "attempt": 1,
        "max_attempts": 3,
        "dead_letter": False,
        "payload": {"run_id": "run-1"},
    }
    result_payload = {
        "spec_version": "agentbus.v1",
        "message_id": "msg-result-1",
        "message_type": "result",
        "message_name": "agent.execution.completed",
        "request_id": "req-1",
        "correlation_id": "msg-command-1",
        "idempotency_key": "agent.execution.request:run-1",
        "attempt": 1,
        "max_attempts": 3,
        "dead_letter": False,
        "payload": {"run_id": "run-1", "status": "completed"},
    }
    event_payload = {
        "spec_version": "agentbus.v1",
        "message_id": "msg-event-1",
        "message_type": "event",
        "message_name": "agent.execution.dead_lettered",
        "request_id": "req-1",
        "correlation_id": "msg-result-1",
        "idempotency_key": "agent.execution.request:run-1",
        "attempt": 3,
        "max_attempts": 3,
        "dead_letter": True,
        "dead_letter_reason": "boom",
        "payload": {"run_id": "run-1", "status": "failed"},
    }

    try:
        assert event_bus.publish_json("agent.execution.command", command_payload) is True
        assert event_bus.publish_json("agent.execution.result", result_payload) is True
        assert event_bus.publish_json("agent.execution.event", event_payload) is True
    finally:
        event_bus.close()

    assert received == [
        ("agent.execution.command", command_payload),
        ("agent.execution.result", result_payload),
        ("agent.execution.event", event_payload),
    ]
