from __future__ import annotations

import asyncio
from concurrent.futures import TimeoutError as FutureTimeoutError

import pytest

from app.platform.messaging.nats_event_bus import NatsEventBus


async def _sample_publish() -> bool:
    return True


def test_run_coro_closes_coroutine_when_event_loop_is_missing() -> None:
    bus = NatsEventBus()
    coro = _sample_publish()

    with pytest.raises(RuntimeError, match="event loop is not ready"):
        bus._run_coro(coro, timeout=0.1)

    assert coro.cr_frame is None


def test_run_coro_closes_coroutine_when_event_loop_is_closed() -> None:
    bus = NatsEventBus()
    loop = asyncio.new_event_loop()
    loop.close()
    bus._loop = loop
    coro = _sample_publish()

    with pytest.raises(RuntimeError):
        bus._run_coro(coro, timeout=0.1)

    assert coro.cr_frame is None


def test_run_coro_closes_coroutine_when_waiting_for_result_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    class _TimedOutFuture:
        def __init__(self) -> None:
            self.cancelled = False

        def result(self, timeout: float) -> bool:
            raise FutureTimeoutError()

        def cancel(self) -> None:
            self.cancelled = True

    bus = NatsEventBus()
    bus._loop = object()
    coro = _sample_publish()
    future = _TimedOutFuture()

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", lambda awaitable, loop: future)

    with pytest.raises(TimeoutError, match="Timed out while waiting for NATS event bus operation"):
        bus._run_coro(coro, timeout=0.1)

    assert future.cancelled is True
    assert coro.cr_frame is None
