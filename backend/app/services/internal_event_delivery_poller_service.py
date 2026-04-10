from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from threading import Event, Lock, Thread

from app.config import get_settings
from app.services.persistence_service import persistence_service
from app.services.store import store


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
        poll_interval_seconds: float | None = None,
        retry_backoff_seconds: float | None = None,
        retry_lease_seconds: float | None = None,
        scan_limit: int | None = None,
    ) -> None:
        settings = get_settings()
        self._persistence = persistence or persistence_service
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
        from app.services.workflow_service import retry_internal_event_delivery

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

        from app.services.workflow_service import list_internal_event_deliveries

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
