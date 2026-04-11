from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable


Subscriber = Callable[[dict[str, Any]], None]


class InMemoryEventBus:
    """Simple in-memory event bus for local/tests compatibility."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Subscriber]] = defaultdict(list)

    def subscribe(self, topic: str, callback: Subscriber) -> None:
        self._subscribers[str(topic)].append(callback)

    def publish(self, topic: str, payload: dict[str, Any]) -> int:
        count = 0
        for callback in self._subscribers.get(str(topic), []):
            callback(dict(payload))
            count += 1
        return count

