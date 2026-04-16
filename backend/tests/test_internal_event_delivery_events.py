from __future__ import annotations

from pathlib import Path

import pytest

from app.services import workflow_service
from app.services.store import InMemoryStore
from tests.test_database_priority_reads import _sqlite_service


def test_trigger_workflow_internal_publishes_requested_and_completed_events(
    tmp_path: Path,
    monkeypatch,
) -> None:
    seeded_store = InMemoryStore()
    seeded_store.workflows = [
        {
            "id": "workflow-db-internal-event-publish",
            "name": "数据库内部事件发布工作流",
            "description": "验证 requested/completed 事件发布",
            "version": "v1",
            "status": "active",
            "updated_at": "2026-04-04T11:30:00+00:00",
            "node_count": 2,
            "edge_count": 1,
            "trigger": {
                "type": "internal",
                "internal_event": "memory.distilled",
                "priority": 260,
                "description": "数据库内部事件入口",
            },
            "agent_bindings": ["3"],
            "nodes": [
                {"id": "1", "type": "trigger", "label": "内部触发", "x": 0, "y": 0},
                {"id": "2", "type": "agent", "label": "搜索 Agent", "agent_id": "3", "x": 120, "y": 0},
            ],
            "edges": [{"id": "e1-2", "source": "1", "target": "2"}],
        }
    ]
    service = _sqlite_service(tmp_path, seeded_store)
    published: list[tuple[str, dict]] = []
    monkeypatch.setattr(workflow_service, "persistence_service", service)
    monkeypatch.setattr(workflow_service.nats_event_bus, "publish_json", lambda subject, payload: published.append((subject, payload)) or True)

    try:
        result = workflow_service.trigger_workflow_internal(
            "memory.distilled",
            {"sessionId": "event-publish-session"},
            source="Memory Service",
            idempotency_key="event-publish-1",
        )
    finally:
        service.close()

    assert result["ok"] is True
    subjects = [item[0] for item in published]
    assert "brain.internal_event.delivery.requested" in subjects
    assert "brain.internal_event.delivery.completed" in subjects


def test_trigger_workflow_internal_publishes_failed_event_on_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    seeded_store = InMemoryStore()
    seeded_store.workflows = [
        {
            "id": "workflow-db-internal-event-fail",
            "name": "数据库内部事件失败发布工作流",
            "description": "验证 failed 事件发布",
            "version": "v1",
            "status": "active",
            "updated_at": "2026-04-04T11:30:00+00:00",
            "node_count": 2,
            "edge_count": 1,
            "trigger": {
                "type": "internal",
                "internal_event": "memory.failed",
                "priority": 260,
                "description": "数据库内部事件入口",
            },
            "agent_bindings": ["3"],
            "nodes": [
                {"id": "1", "type": "trigger", "label": "内部触发", "x": 0, "y": 0},
                {"id": "2", "type": "agent", "label": "搜索 Agent", "agent_id": "3", "x": 120, "y": 0},
            ],
            "edges": [{"id": "e1-2", "source": "1", "target": "2"}],
        }
    ]
    service = _sqlite_service(tmp_path, seeded_store)
    published: list[tuple[str, dict]] = []
    monkeypatch.setattr(workflow_service, "persistence_service", service)
    monkeypatch.setattr(workflow_service.nats_event_bus, "publish_json", lambda subject, payload: published.append((subject, payload)) or True)
    monkeypatch.setattr(
        workflow_service,
        "create_manual_workflow_run",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("forced internal event failure")),
    )

    try:
        with pytest.raises(RuntimeError):
            workflow_service.trigger_workflow_internal(
                "memory.failed",
                {"sessionId": "event-fail-session"},
                source="Memory Service",
                idempotency_key="event-fail-1",
            )
    finally:
        service.close()

    subjects = [item[0] for item in published]
    assert "brain.internal_event.delivery.requested" in subjects
    assert "brain.internal_event.delivery.failed" in subjects


def test_retry_internal_event_delivery_publishes_retried_event(
    tmp_path: Path,
    monkeypatch,
) -> None:
    seeded_store = InMemoryStore()
    seeded_store.workflows = [
        {
            "id": "workflow-db-internal-event-retry",
            "name": "数据库内部事件重试发布工作流",
            "description": "验证 retried 事件发布",
            "version": "v1",
            "status": "active",
            "updated_at": "2026-04-04T11:30:00+00:00",
            "node_count": 2,
            "edge_count": 1,
            "trigger": {
                "type": "internal",
                "internal_event": "memory.retry",
                "priority": 260,
                "description": "数据库内部事件入口",
            },
            "agent_bindings": ["3"],
            "nodes": [
                {"id": "1", "type": "trigger", "label": "内部触发", "x": 0, "y": 0},
                {"id": "2", "type": "agent", "label": "搜索 Agent", "agent_id": "3", "x": 120, "y": 0},
            ],
            "edges": [{"id": "e1-2", "source": "1", "target": "2"}],
        }
    ]
    service = _sqlite_service(tmp_path, seeded_store)
    published: list[tuple[str, dict]] = []
    monkeypatch.setattr(workflow_service, "persistence_service", service)
    monkeypatch.setattr(workflow_service.nats_event_bus, "publish_json", lambda subject, payload: published.append((subject, payload)) or True)

    try:
        first = workflow_service.trigger_workflow_internal(
            "memory.retry",
            {"sessionId": "event-retry-session"},
            source="Memory Service",
            idempotency_key="event-retry-1",
        )
        retried = workflow_service.retry_internal_event_delivery(first["internal_event_id"])
    finally:
        service.close()

    assert retried["ok"] is True
    assert any(item[0] == "brain.internal_event.delivery.retried" for item in published)
