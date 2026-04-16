from fastapi.testclient import TestClient

from app.core.event_protocol import build_event_envelope
from app.core.nats_event_bus import nats_event_bus
from app.main import app
from app.services.event_journal_service import (
    EVENT_DEAD_LETTER_KEY,
    EVENT_JOURNAL_KEY,
    get_event,
    list_dead_letters,
    mark_event_published,
    record_event_publish_attempt,
)
from app.services.store import store


client = TestClient(app)


def _reset_event_store() -> None:
    store.system_settings.pop(EVENT_JOURNAL_KEY, None)
    store.system_settings.pop(EVENT_DEAD_LETTER_KEY, None)


def test_nats_publish_failure_creates_dead_letter(monkeypatch) -> None:
    _reset_event_store()
    monkeypatch.setattr(nats_event_bus, "initialize", lambda: True)
    def _raise_publish_error(coro, **kwargs):
        _ = kwargs
        coro.close()
        raise RuntimeError("boom")

    monkeypatch.setattr(nats_event_bus, "_run_coro", _raise_publish_error)

    payload = build_event_envelope(
        subject="brain.workflow.run.updated",
        event_name="brain.workflow.run.updated",
        aggregate={"type": "workflow_run", "id": "run-dead-letter-1"},
        payload={"run_id": "run-dead-letter-1"},
    )
    published = nats_event_bus.publish_json("brain.workflow.run.updated", payload)

    assert published is False
    event = get_event(payload["event_id"])
    assert event is not None
    assert event["status"] == "failed_publish"
    dead_letters = list_dead_letters()
    assert dead_letters["total"] >= 1
    assert dead_letters["items"][0]["event_id"] == payload["event_id"]


def test_events_route_lists_and_replays_events(auth_headers_factory, monkeypatch) -> None:
    _reset_event_store()
    source = build_event_envelope(
        subject="brain.internal_event.delivery.completed",
        event_name="brain.internal_event.delivery.completed",
        aggregate={"type": "internal_event_delivery", "id": "delivery-1"},
        trace={"trace_id": "trace-delivery-1"},
        routing={"idempotency_key": "delivery-1"},
        payload={"internal_event_id": "delivery-1"},
    )
    record_event_publish_attempt(source["subject"], source)
    mark_event_published(source["event_id"])
    monkeypatch.setattr(nats_event_bus, "publish_json", lambda subject, payload: True)

    headers = auth_headers_factory(role="operator", email="events.operator@example.test")
    list_response = client.get("/api/events", headers=headers)
    replay_response = client.post(
        f"/api/events/{source['event_id']}/replay",
        headers=headers,
        json={"reason": "重放验证"},
    )

    assert list_response.status_code == 200
    assert any(item["eventId"] == source["event_id"] for item in list_response.json()["items"])
    assert replay_response.status_code == 200
    payload = replay_response.json()
    assert payload["sourceEvent"]["eventId"] == source["event_id"]
    assert payload["replayEvent"]["eventId"] != source["event_id"]
    assert payload["replayEvent"]["replayedFromEventId"] == source["event_id"]
    assert payload["replayEvent"]["trace"]["parent_event_id"] == source["event_id"]
