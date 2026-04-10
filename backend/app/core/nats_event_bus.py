from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
from collections import defaultdict
from concurrent.futures import TimeoutError as FutureTimeoutError
from threading import Event, Lock, Thread
from typing import Callable

from app.config import get_settings


logger = logging.getLogger(__name__)
DEFAULT_RETRY_INTERVAL_SECONDS = 30.0
DEFAULT_OPERATION_TIMEOUT_SECONDS = 1.5

try:  # pragma: no cover - exercised via runtime dependency availability
    import nats
except Exception:  # pragma: no cover - defensive import guard
    nats = None


EventHandler = Callable[[str, dict], None]
SubscriptionKey = tuple[str, str]


class NatsEventBus:
    def __init__(
        self,
        *,
        nats_url: str | None = None,
        retry_interval_seconds: float = DEFAULT_RETRY_INTERVAL_SECONDS,
        operation_timeout_seconds: float = DEFAULT_OPERATION_TIMEOUT_SECONDS,
        client_factory_override=None,
    ) -> None:
        self.nats_url = nats_url or get_settings().nats_url
        self.retry_interval_seconds = retry_interval_seconds
        self.operation_timeout_seconds = operation_timeout_seconds
        self._client_factory_override = client_factory_override

        self._client = None
        self._handlers: dict[SubscriptionKey, list[EventHandler]] = defaultdict(list)
        self._subscriptions: dict[SubscriptionKey, object] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: Thread | None = None
        self._lock = Lock()
        self._loop_ready = Event()
        self._last_connect_attempt_at = 0.0
        self._warned_unavailable = False

    def subscribe(self, subject: str, handler: EventHandler, *, queue_group: str = "") -> None:
        key = (subject, queue_group)
        should_sync = False
        with self._lock:
            handlers = self._handlers[key]
            if handler not in handlers:
                handlers.append(handler)
                should_sync = self.is_connected()

        if should_sync:
            self._sync_subscriptions()

    def initialize(self) -> bool:
        if self._client_factory_override is None and nats is None:
            self._warn_missing_dependency()
            return False

        if not self._ensure_loop():
            return False
        return self._connect()

    def is_connected(self) -> bool:
        client = self._client
        return self._client_is_connected(client)

    def publish_json(self, subject: str, payload: dict) -> bool:
        if not self.initialize():
            return False

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            return bool(
                self._run_coro(
                    self._publish_async(subject, data),
                    timeout=self.operation_timeout_seconds + 0.5,
                )
            )
        except Exception as exc:  # pragma: no cover - depends on runtime environment
            self._mark_client_unavailable()
            if not self._warned_unavailable:
                logger.warning("NATS publish failed, using in-process fallback: %s", exc)
                self._warned_unavailable = True
            return False

    def close(self) -> None:
        loop = self._loop
        thread = self._thread

        if loop is not None and thread is not None:
            try:
                self._run_coro(
                    self._close_async(),
                    timeout=self.operation_timeout_seconds + 0.5,
                )
            except Exception:  # pragma: no cover - defensive shutdown path
                pass
            try:
                loop.call_soon_threadsafe(loop.stop)
            except RuntimeError:  # pragma: no cover - loop already closed
                pass
            thread.join(timeout=1.0)

        with self._lock:
            self._client = None
            self._subscriptions.clear()
            self._loop = None
            self._thread = None
            self._last_connect_attempt_at = 0.0

        self._loop_ready.clear()

    def _ensure_loop(self) -> bool:
        with self._lock:
            thread = self._thread
            if thread is not None and thread.is_alive():
                return True

            self._loop_ready.clear()
            self._thread = Thread(target=self._run_loop, daemon=True, name="workbot-nats-event-bus")
            self._thread.start()

        return self._loop_ready.wait(timeout=1.0)

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        with self._lock:
            self._loop = loop
        self._loop_ready.set()

        try:
            loop.run_forever()
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()
            with self._lock:
                if self._loop is loop:
                    self._loop = None

    def _connect(self) -> bool:
        if self.is_connected():
            return True

        now = time.monotonic()
        with self._lock:
            if now - self._last_connect_attempt_at < self.retry_interval_seconds:
                return False
            self._last_connect_attempt_at = now

        try:
            connected = bool(
                self._run_coro(
                    self._connect_async(),
                    timeout=self.operation_timeout_seconds + 0.5,
                )
            )
            if connected:
                self._warned_unavailable = False
            return connected
        except Exception as exc:  # pragma: no cover - depends on runtime environment
            self._mark_client_unavailable()
            if not self._warned_unavailable:
                logger.warning("NATS integration disabled, using in-process fallback: %s", exc)
                self._warned_unavailable = True
            return False

    async def _connect_async(self) -> bool:
        if self._client_is_connected(self._client):
            return True

        client = await self._build_client_async()
        with self._lock:
            self._client = client
            self._subscriptions.clear()

        await self._sync_subscriptions_async()
        return True

    async def _build_client_async(self):
        if self._client_factory_override is not None:
            client = self._client_factory_override()
            if inspect.isawaitable(client):
                client = await client
            return client

        if nats is None:
            raise RuntimeError("nats-py package is not installed")

        return await nats.connect(
            servers=[self.nats_url],
            connect_timeout=self.operation_timeout_seconds,
            max_reconnect_attempts=0,
            error_cb=self._on_async_error,
            disconnected_cb=self._on_async_disconnected,
            closed_cb=self._on_async_closed,
        )

    async def _on_async_error(self, exc: Exception) -> None:
        logger.debug("NATS client error: %s", exc)

    async def _on_async_disconnected(self) -> None:
        logger.debug("NATS client disconnected")

    async def _on_async_closed(self) -> None:
        logger.debug("NATS client closed")

    async def _sync_subscriptions_async(self) -> None:
        client = self._client
        if not self._client_is_connected(client):
            return

        with self._lock:
            registrations = list(self._handlers.keys())
            subscribed_registrations = set(self._subscriptions.keys())

        for registration in registrations:
            if registration in subscribed_registrations:
                continue
            subject, queue_group = registration
            subscription = await client.subscribe(
                subject,
                queue=queue_group,
                cb=self._build_callback(registration),
            )
            with self._lock:
                self._subscriptions[registration] = subscription

    def _sync_subscriptions(self) -> None:
        if not self.is_connected():
            return
        try:
            self._run_coro(
                self._sync_subscriptions_async(),
                timeout=self.operation_timeout_seconds + 0.5,
            )
        except Exception as exc:  # pragma: no cover - depends on runtime environment
            self._mark_client_unavailable()
            logger.warning("NATS subscription sync failed, keeping local realtime fallback: %s", exc)

    def _build_callback(self, registration: SubscriptionKey):
        subject, _ = registration

        async def _callback(message) -> None:
            payload = self._decode_payload(getattr(message, "data", b""))
            if payload is None:
                return

            with self._lock:
                handlers = list(self._handlers.get(registration, []))

            message_subject = str(getattr(message, "subject", subject))
            for handler in handlers:
                try:
                    handler(message_subject, payload)
                except Exception:  # pragma: no cover - defensive callback isolation
                    logger.exception("Workflow realtime event handler raised unexpectedly")

        return _callback

    async def _publish_async(self, subject: str, data: bytes) -> bool:
        client = self._client
        if not self._client_is_connected(client):
            return False

        await client.publish(subject, data)
        flush = getattr(client, "flush", None)
        if flush is not None:
            result = flush(timeout=self.operation_timeout_seconds)
            if inspect.isawaitable(result):
                await result
        return True

    async def _close_async(self) -> None:
        with self._lock:
            client = self._client
            subscriptions = list(self._subscriptions.values())
            self._subscriptions.clear()
            self._client = None

        for subscription in subscriptions:
            unsubscribe = getattr(subscription, "unsubscribe", None)
            if unsubscribe is None:
                continue
            result = unsubscribe()
            if inspect.isawaitable(result):
                await result

        if client is None:
            return

        drain = getattr(client, "drain", None)
        close = getattr(client, "close", None)
        if drain is not None:
            result = drain()
            if inspect.isawaitable(result):
                await result
        elif close is not None:
            result = close()
            if inspect.isawaitable(result):
                await result

    @staticmethod
    def _decode_payload(data: bytes | str) -> dict | None:
        try:
            text = data.decode("utf-8") if isinstance(data, bytes) else str(data)
            return json.loads(text)
        except Exception:
            logger.warning("Received invalid JSON payload from NATS event bus")
            return None

    @staticmethod
    def _client_is_connected(client) -> bool:
        if client is None:
            return False
        if getattr(client, "is_closed", False):
            return False
        if hasattr(client, "is_connected"):
            return bool(client.is_connected)
        return True

    def _warn_missing_dependency(self) -> None:
        if self._warned_unavailable:
            return
        logger.warning("NATS integration disabled, using in-process fallback: nats-py package is not installed")
        self._warned_unavailable = True

    def _mark_client_unavailable(self) -> None:
        with self._lock:
            self._client = None
            self._subscriptions.clear()

    def _run_coro(self, coro, *, timeout: float):
        loop = self._loop
        if loop is None:
            raise RuntimeError("NATS event loop is not ready")

        future = asyncio.run_coroutine_threadsafe(coro, loop)
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError as exc:
            future.cancel()
            raise TimeoutError("Timed out while waiting for NATS event bus operation") from exc


nats_event_bus = NatsEventBus()


def reset_nats_event_bus_state() -> None:
    nats_event_bus.close()
