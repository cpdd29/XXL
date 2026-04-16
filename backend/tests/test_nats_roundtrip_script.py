from __future__ import annotations

from collections.abc import Awaitable, Callable
from collections import defaultdict

from app.core.event_subjects import AGENT_EXECUTION_CLAIMED_SUBJECT
from app.services.workflow_dispatcher_service import (
    WORKFLOW_DISPATCH_QUEUE,
    WORKFLOW_DISPATCH_SUBJECT,
)
from app.core.nats_event_bus import NatsEventBus
from scripts.check_nats_roundtrip import run_check


class _FakeMessage:
    def __init__(self, subject: str, data: bytes) -> None:
        self.subject = subject
        self.data = data


class _FakeSubscription:
    def __init__(self, subject: str, queue: str, callback: Callable[[_FakeMessage], Awaitable[None]]) -> None:
        self.subject = subject
        self.queue = queue
        self.callback = callback
        self.unsubscribed = False

    async def unsubscribe(self) -> None:
        self.unsubscribed = True


class _QueueAwareBroker:
    def __init__(self) -> None:
        self.subscriptions: list[_FakeSubscription] = []
        self.queue_offsets: dict[tuple[str, str], int] = defaultdict(int)

    def add_subscription(self, subscription: _FakeSubscription) -> None:
        self.subscriptions.append(subscription)

    async def publish(self, subject: str, data: bytes) -> None:
        matching = [
            item
            for item in self.subscriptions
            if not item.unsubscribed and item.subject == subject
        ]
        grouped: dict[str, list[_FakeSubscription]] = defaultdict(list)
        for subscription in matching:
            grouped[subscription.queue].append(subscription)

        message = _FakeMessage(subject, data)
        if "" in grouped:
            for subscription in grouped[""]:
                await subscription.callback(message)

        for queue, subscriptions in grouped.items():
            if not queue:
                continue
            offset = self.queue_offsets[(subject, queue)] % len(subscriptions)
            self.queue_offsets[(subject, queue)] += 1
            await subscriptions[offset].callback(message)


class _QueueAwareFakeClient:
    def __init__(self, broker: _QueueAwareBroker) -> None:
        self._broker = broker
        self.is_connected = True
        self.is_closed = False

    async def subscribe(self, subject: str, queue: str = "", cb=None):
        subscription = _FakeSubscription(subject, queue, cb)
        self._broker.add_subscription(subscription)
        return subscription

    async def publish(self, subject: str, data: bytes) -> None:
        await self._broker.publish(subject, data)

    async def flush(self, timeout=None) -> None:
        _ = timeout
        return None

    async def drain(self) -> None:
        self.is_connected = False
        self.is_closed = True


def test_check_nats_roundtrip_passes_with_queue_aware_fake_broker() -> None:
    broker = _QueueAwareBroker()

    def _factory() -> NatsEventBus:
        return NatsEventBus(
            nats_url="nats://fake:4222",
            retry_interval_seconds=0.0,
            operation_timeout_seconds=0.1,
            client_factory_override=lambda: _QueueAwareFakeClient(broker),
        )

    payload = run_check(
        nats_url="nats://fake:4222",
        message_count=4,
        bus_factory=_factory,
    )

    assert payload["ok"] is True
    assert payload["phases"]["connect"]["ok"] is True
    assert payload["phases"]["roundtrip"]["summary"]["received"] == 1
    assert payload["phases"]["dispatch_queue"]["summary"]["hits"]["a"] + payload["phases"]["dispatch_queue"]["summary"]["hits"]["b"] == 4
    assert payload["phases"]["workflow_queue_and_filter"]["summary"]["hits"]["command"] == 1
    assert payload["phases"]["workflow_queue_and_filter"]["summary"]["hits"]["ignored"] == 1
    assert payload["phases"]["agent_queue_and_filter"]["summary"]["hits"]["command"] == 1
    assert payload["phases"]["agent_queue_and_filter"]["summary"]["hits"]["ignored"] == 1
    assert (
        payload["phases"]["agent_queue_and_filter"]["summary"]["event_subject"]
        == AGENT_EXECUTION_CLAIMED_SUBJECT
    )


def test_check_nats_roundtrip_isolated_from_live_dispatch_consumers() -> None:
    broker = _QueueAwareBroker()

    async def _live_dispatch_consumer(_message: _FakeMessage) -> None:
        return None

    broker.add_subscription(
        _FakeSubscription(
            WORKFLOW_DISPATCH_SUBJECT,
            WORKFLOW_DISPATCH_QUEUE,
            _live_dispatch_consumer,
        )
    )

    def _factory() -> NatsEventBus:
        return NatsEventBus(
            nats_url="nats://fake:4222",
            retry_interval_seconds=0.0,
            operation_timeout_seconds=0.1,
            client_factory_override=lambda: _QueueAwareFakeClient(broker),
        )

    payload = run_check(
        nats_url="nats://fake:4222",
        message_count=4,
        bus_factory=_factory,
    )

    assert payload["ok"] is True
    assert payload["phases"]["dispatch_queue"]["summary"]["base_subject"] == WORKFLOW_DISPATCH_SUBJECT
    assert payload["phases"]["dispatch_queue"]["summary"]["queue_group"] == WORKFLOW_DISPATCH_QUEUE
    assert payload["phases"]["dispatch_queue"]["summary"]["hits"]["a"] + payload["phases"]["dispatch_queue"]["summary"]["hits"]["b"] == 4
