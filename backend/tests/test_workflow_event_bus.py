from __future__ import annotations

from queue import Empty

from app.core.nats_event_bus import NatsEventBus
from app.services.store import store
from app.services.workflow_realtime_service import WorkflowRealtimeService


class FakeSubscription:
    def __init__(self, subject: str, queue: str, callback) -> None:
        self.subject = subject
        self.queue = queue
        self.callback = callback
        self.unsubscribed = False

    async def unsubscribe(self) -> None:
        self.unsubscribed = True


class FakeMessage:
    def __init__(self, subject: str, data: bytes) -> None:
        self.subject = subject
        self.data = data


class FakeNatsClient:
    def __init__(self) -> None:
        self.is_connected = True
        self.is_closed = False
        self.subscriptions: list[FakeSubscription] = []
        self.published_subjects: list[str] = []

    async def subscribe(self, subject: str, queue: str = "", cb=None):
        subscription = FakeSubscription(subject, queue, cb)
        self.subscriptions.append(subscription)
        return subscription

    async def publish(self, subject: str, data: bytes) -> None:
        self.published_subjects.append(subject)
        message = FakeMessage(subject, data)
        for subscription in list(self.subscriptions):
            if subscription.unsubscribed:
                continue
            if _matches_subject(subscription.subject, subject):
                await subscription.callback(message)

    async def flush(self, timeout=None) -> None:
        _ = timeout
        return None

    async def drain(self) -> None:
        self.is_connected = False
        self.is_closed = True


def _matches_subject(pattern: str, subject: str) -> bool:
    pattern_parts = pattern.split(".")
    subject_parts = subject.split(".")
    if len(pattern_parts) != len(subject_parts):
        return False
    return all(left == "*" or left == right for left, right in zip(pattern_parts, subject_parts))


def _build_run(run_id: str = "run-1", workflow_id: str = "workflow-1") -> dict:
    return {
        "id": run_id,
        "workflow_id": workflow_id,
        "status": "running",
        "created_at": "2026-04-03T10:00:00+00:00",
        "updated_at": "2026-04-03T10:00:00+00:00",
    }


def test_workflow_realtime_service_uses_nats_event_bus_when_available() -> None:
    fake_client = FakeNatsClient()
    event_bus = NatsEventBus(
        nats_url="nats://fake:4222",
        retry_interval_seconds=0.0,
        client_factory_override=lambda: fake_client,
    )
    service = WorkflowRealtimeService(event_bus=event_bus)
    run = _build_run()
    store.workflow_runs = [run]
    queue = service._subscribe("workflow-1")

    try:
        service.publish_run_event(run, "workflow_run.updated")
        payload = queue.get(timeout=1.0)

        assert fake_client.published_subjects == ["workflow.runs.workflow-1"]
        assert payload["type"] == "workflow_run.updated"
        assert payload["workflowId"] == "workflow-1"
        assert payload["run"]["id"] == "run-1"
        assert payload["items"][0]["id"] == "run-1"
    finally:
        service._unsubscribe("workflow-1", queue)
        event_bus.close()


def test_workflow_realtime_service_falls_back_to_local_broadcast_when_nats_unavailable() -> None:
    event_bus = NatsEventBus(
        nats_url="nats://fake:4222",
        retry_interval_seconds=0.0,
        client_factory_override=lambda: (_ for _ in ()).throw(RuntimeError("nats unavailable")),
    )
    service = WorkflowRealtimeService(event_bus=event_bus)
    run = _build_run(run_id="run-fallback")
    store.workflow_runs = [run]
    queue = service._subscribe("workflow-1")

    try:
        service.publish_run_event(run, "workflow_run.created")
        payload = queue.get(timeout=1.0)

        assert payload["type"] == "workflow_run.created"
        assert payload["workflowId"] == "workflow-1"
        assert payload["run"]["id"] == "run-fallback"
    finally:
        service._unsubscribe("workflow-1", queue)
        event_bus.close()

    try:
        queue.get_nowait()
    except Empty:
        pass
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Expected exactly one local fallback event")
