from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from threading import Event, Lock, Thread

from app.config import get_settings
from app.platform.contracts.event_protocol import build_event_envelope
from app.platform.contracts.event_subjects import INTERNAL_EVENT_DELIVERY_CLAIMED_SUBJECT
from app.platform.messaging.nats_event_bus import nats_event_bus
from app.platform.persistence.persistence_service import persistence_service
from app.platform.persistence.runtime_store import store


logger = logging.getLogger(__name__)
DEFAULT_INTERNAL_EVENT_RETRY_POLL_INTERVAL_SECONDS = 5.0
DEFAULT_INTERNAL_EVENT_RETRY_BACKOFF_SECONDS = 15.0
DEFAULT_INTERNAL_EVENT_RETRY_LEASE_SECONDS = 60.0
DEFAULT_INTERNAL_EVENT_RETRY_SCAN_LIMIT = 20
TERMINAL_CLOSED_INTERNAL_EVENT_STATUSES = {"delivered", "ignored"}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


class InternalEventDeliveryPollerService:
    def __init__(
        self,
        *,
        persistence=None,
        event_bus=None,
        poll_interval_seconds: float | None = None,
        retry_backoff_seconds: float | None = None,
        retry_lease_seconds: float | None = None,
        scan_limit: int | None = None,
    ) -> None:
        settings = get_settings()
        self._persistence = persistence or persistence_service
        self._event_bus = event_bus or nats_event_bus
        self._poll_interval_seconds = max(
            float(
                poll_interval_seconds
                if poll_interval_seconds is not None
                else settings.internal_event_retry_poll_interval_seconds
            ),
            0.1,
        )
        self._retry_backoff_seconds = max(
            float(
                retry_backoff_seconds
                if retry_backoff_seconds is not None
                else settings.internal_event_retry_backoff_seconds
            ),
            0.0,
        )
        self._retry_lease_seconds = max(
            float(
                retry_lease_seconds
                if retry_lease_seconds is not None
                else settings.internal_event_retry_lease_seconds
            ),
            0.0,
        )
        self._scan_limit = max(
            int(
                scan_limit
                if scan_limit is not None
                else settings.internal_event_retry_scan_limit
            ),
            1,
        )
        self._stop_event = Event()
        self._lock = Lock()
        self._thread: Thread | None = None

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = Thread(
                target=self._run_loop,
                daemon=True,
                name="workbot-internal-event-delivery-poller",
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            self._thread = None

        self._stop_event.set()
        if thread is not None:
            thread.join(timeout=self._poll_interval_seconds + 0.5)
        self._stop_event.clear()

    def poll_once(self) -> dict[str, int]:
        from app.modules.dispatch.workflow_runtime.workflow_service import retry_internal_event_delivery

        summary = {
            "claimed": 0,
            "retried": 0,
            "failed": 0,
        }
        for delivery in self._load_due_deliveries():
            delivery_id = str(delivery.get("id") or "").strip()
            if not delivery_id:
                continue

            summary["claimed"] += 1
            self._publish_claimed_event(delivery)
            try:
                result = retry_internal_event_delivery(delivery_id)
                if (
                    str(result.get("internal_event_status") or "").strip().lower()
                    in TERMINAL_CLOSED_INTERNAL_EVENT_STATUSES
                ):
                    summary["retried"] += 1
                else:
                    summary["failed"] += 1
            except Exception as exc:
                logger.warning(
                    "Internal event delivery poller failed for delivery %s: %s",
                    delivery_id,
                    exc,
                )
                summary["failed"] += 1

        return summary

    def _publish_claimed_event(self, delivery: dict) -> None:
        delivery_id = str(delivery.get("id") or "").strip()
        if not delivery_id:
            return
        emitted_at = str(delivery.get("updated_at") or "").strip() or _utc_now().isoformat()
        envelope = build_event_envelope(
            subject=INTERNAL_EVENT_DELIVERY_CLAIMED_SUBJECT,
            event_name="brain.internal_event.delivery.claimed",
            aggregate={"type": "internal_event_delivery", "id": delivery_id},
            trace={"request_id": delivery_id},
            routing={
                "partition_key": delivery_id,
                "idempotency_key": str(delivery.get("idempotency_key") or "").strip()
                or f"brain.internal_event.delivery.claimed:{delivery_id}",
            },
            timing={"emitted_at": emitted_at, "available_at": emitted_at},
            source={"kind": "internal_event_delivery_poller_service", "id": "poller"},
            target={"kind": "workflow_service", "id": "retry_internal_event_delivery"},
            payload={
                "internal_event_id": delivery_id,
                "internal_event_name": str(delivery.get("event_name") or "").strip() or None,
                "status": str(delivery.get("status") or "").strip() or None,
                "attempt_count": int(delivery.get("attempt_count") or 0),
                "idempotency_key": str(delivery.get("idempotency_key") or "").strip() or None,
            },
        )
        self._event_bus.publish_json(INTERNAL_EVENT_DELIVERY_CLAIMED_SUBJECT, envelope)

    def _run_loop(self) -> None:
        while not self._stop_event.wait(timeout=self._poll_interval_seconds):
            try:
                self.poll_once()
            except Exception as exc:  # pragma: no cover - defensive runtime guard
                logger.warning("Internal event delivery poller iteration failed: %s", exc)

    def _load_due_deliveries(self) -> list[dict]:
        deadline = _utc_now()
        retry_before = (deadline - timedelta(seconds=self._retry_backoff_seconds)).isoformat()
        retrying_stale_before = (
            deadline - timedelta(seconds=self._retry_lease_seconds)
        ).isoformat()

        claim_due_deliveries = getattr(
            self._persistence,
            "claim_due_internal_event_deliveries",
            None,
        )
        if callable(claim_due_deliveries):
            claimed = claim_due_deliveries(
                claimed_at=deadline.isoformat(),
                retry_before=retry_before,
                retrying_stale_before=retrying_stale_before,
                limit=self._scan_limit,
            )
            if claimed is not None:
                return [
                    store.clone(delivery)
                    for delivery in sorted(
                        claimed,
                        key=lambda item: (
                            _parse_datetime(item.get("updated_at"))
                            or _parse_datetime(item.get("created_at"))
                            or deadline,
                            str(item.get("id") or ""),
                        ),
                    )[: self._scan_limit]
                ]

        from app.modules.dispatch.workflow_runtime.workflow_service import list_internal_event_deliveries

        listed = list_internal_event_deliveries(
            status_filter="failed",
            limit=self._scan_limit,
            offset=0,
        )
        items = listed.get("items") or []
        due_items = [
            store.clone(item)
            for item in items
            if (_parse_datetime(item.get("updated_at")) or _parse_datetime(item.get("created_at")) or deadline)
            <= _parse_datetime(retry_before)
        ]
        return due_items[: self._scan_limit]


internal_event_delivery_poller_service = InternalEventDeliveryPollerService()


def reset_internal_event_delivery_poller_state() -> None:
    internal_event_delivery_poller_service.stop()
