from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.internal_event_delivery_poller_service import (
    InternalEventDeliveryPollerService,
)
from app.services.store import store


class FakePersistence:
    def __init__(self, claimed_deliveries: list[dict] | None = None) -> None:
        self.claimed_deliveries = claimed_deliveries
        self.claim_calls: list[dict[str, object]] = []

    def claim_due_internal_event_deliveries(
        self,
        *,
        claimed_at: str,
        retry_before: str | None = None,
        retrying_stale_before: str | None = None,
        limit: int | None = None,
    ) -> list[dict] | None:
        self.claim_calls.append(
            {
                "claimed_at": claimed_at,
                "retry_before": retry_before,
                "retrying_stale_before": retrying_stale_before,
                "limit": limit,
            }
        )
        if self.claimed_deliveries is None:
            return None
        items = list(self.claimed_deliveries)
        if limit is not None:
            items = items[:limit]
        return [store.clone(item) for item in items]


def _delivery(
    delivery_id: str,
    *,
    status: str = "failed",
    updated_at: str,
    created_at: str | None = None,
) -> dict:
    created_timestamp = created_at or "2026-04-04T11:00:00+00:00"
    return {
        "id": delivery_id,
        "event_name": "memory.distilled",
        "source": "Memory Service",
        "payload": {"sessionId": "poller-session-1"},
        "idempotency_key": f"memory.distilled:{delivery_id}",
        "status": status,
        "attempt_count": 1,
        "last_error": "transient failure",
        "triggered_count": 1,
        "triggered_workflow_ids": ["workflow-1"],
        "triggered_run_ids": ["run-1"],
        "triggered_task_ids": ["task-1"],
        "primary_workflow": None,
        "created_at": created_timestamp,
        "updated_at": updated_at,
        "delivered_at": None,
    }


def test_internal_event_delivery_poller_retries_claimed_failed_delivery(monkeypatch) -> None:
    fixed_now = datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC)
    persistence = FakePersistence(
        [
            _delivery(
                "evt-poller-1",
                status="retrying",
                updated_at=(fixed_now - timedelta(seconds=90)).isoformat(),
            )
        ]
    )
    retried_ids: list[str] = []

    monkeypatch.setattr(
        "app.services.internal_event_delivery_poller_service._utc_now",
        lambda: fixed_now,
    )
    monkeypatch.setattr(
        "app.services.workflow_service.retry_internal_event_delivery",
        lambda delivery_id: retried_ids.append(delivery_id)
        or {"internal_event_status": "delivered"},
    )

    service = InternalEventDeliveryPollerService(
        persistence=persistence,
        poll_interval_seconds=0.1,
        retry_backoff_seconds=15,
        retry_lease_seconds=60,
        scan_limit=10,
    )

    summary = service.poll_once()

    assert summary == {
        "claimed": 1,
        "retried": 1,
        "failed": 0,
    }
    assert retried_ids == ["evt-poller-1"]
    assert persistence.claim_calls[0]["claimed_at"] == fixed_now.isoformat()
    assert persistence.claim_calls[0]["retry_before"] == (
        fixed_now - timedelta(seconds=15)
    ).isoformat()
    assert persistence.claim_calls[0]["retrying_stale_before"] == (
        fixed_now - timedelta(seconds=60)
    ).isoformat()


def test_internal_event_delivery_poller_counts_retry_failures(monkeypatch) -> None:
    fixed_now = datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC)
    persistence = FakePersistence(
        [
            _delivery(
                "evt-poller-fail",
                status="failed",
                updated_at=(fixed_now - timedelta(seconds=30)).isoformat(),
            )
        ]
    )

    monkeypatch.setattr(
        "app.services.internal_event_delivery_poller_service._utc_now",
        lambda: fixed_now,
    )

    def _raise_retry(delivery_id: str) -> dict:
        raise RuntimeError(f"retry failed for {delivery_id}")

    monkeypatch.setattr(
        "app.services.workflow_service.retry_internal_event_delivery",
        _raise_retry,
    )

    service = InternalEventDeliveryPollerService(
        persistence=persistence,
        poll_interval_seconds=0.1,
        retry_backoff_seconds=15,
        retry_lease_seconds=60,
        scan_limit=10,
    )

    summary = service.poll_once()

    assert summary == {
        "claimed": 1,
        "retried": 0,
        "failed": 1,
    }


def test_internal_event_delivery_poller_treats_ignored_delivery_as_closed(monkeypatch) -> None:
    fixed_now = datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC)
    persistence = FakePersistence(
        [
            _delivery(
                "evt-poller-ignored",
                status="failed",
                updated_at=(fixed_now - timedelta(seconds=30)).isoformat(),
            )
        ]
    )

    monkeypatch.setattr(
        "app.services.internal_event_delivery_poller_service._utc_now",
        lambda: fixed_now,
    )
    monkeypatch.setattr(
        "app.services.workflow_service.retry_internal_event_delivery",
        lambda delivery_id: {
            "internal_event_id": delivery_id,
            "internal_event_status": "ignored",
        },
    )

    service = InternalEventDeliveryPollerService(
        persistence=persistence,
        poll_interval_seconds=0.1,
        retry_backoff_seconds=15,
        retry_lease_seconds=60,
        scan_limit=10,
    )

    summary = service.poll_once()

    assert summary == {
        "claimed": 1,
        "retried": 1,
        "failed": 0,
    }


def test_internal_event_delivery_poller_falls_back_to_failed_delivery_listing(
    monkeypatch,
) -> None:
    fixed_now = datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC)
    persistence = FakePersistence(claimed_deliveries=None)
    listed_calls: list[dict[str, object]] = []
    retried_ids: list[str] = []

    monkeypatch.setattr(
        "app.services.internal_event_delivery_poller_service._utc_now",
        lambda: fixed_now,
    )
    monkeypatch.setattr(
        "app.services.workflow_service.list_internal_event_deliveries",
        lambda **kwargs: listed_calls.append(kwargs)
        or {
            "items": [
                _delivery(
                    "evt-poller-fallback",
                    status="failed",
                    updated_at=(fixed_now - timedelta(seconds=20)).isoformat(),
                )
            ],
            "total": 1,
        },
    )
    monkeypatch.setattr(
        "app.services.workflow_service.retry_internal_event_delivery",
        lambda delivery_id: retried_ids.append(delivery_id)
        or {"internal_event_status": "delivered"},
    )

    service = InternalEventDeliveryPollerService(
        persistence=persistence,
        poll_interval_seconds=0.1,
        retry_backoff_seconds=15,
        retry_lease_seconds=60,
        scan_limit=10,
    )

    summary = service.poll_once()

    assert summary == {
        "claimed": 1,
        "retried": 1,
        "failed": 0,
    }
    assert listed_calls == [{"status_filter": "failed", "limit": 10, "offset": 0}]
    assert retried_ids == ["evt-poller-fallback"]
