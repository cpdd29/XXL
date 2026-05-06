from __future__ import annotations

from pathlib import Path

import app.platform.approval.approval_service as approval_service
from app.platform.persistence.persistence_service import StatePersistenceService
from app.platform.persistence.runtime_store import InMemoryStore


def test_approval_service_lists_and_processes_persisted_items(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime_store = InMemoryStore()
    service = StatePersistenceService(
        runtime_store=runtime_store,
        database_url=f"sqlite:///{tmp_path / 'approvals.db'}",
    )
    assert service.initialize() is True

    monkeypatch.setattr(approval_service, "persistence_service", service)
    monkeypatch.setattr(approval_service, "store", runtime_store)

    try:
        created = approval_service.create_bound_approval(
            request_type="settings_change",
            title="更新安全策略",
            resource="settings.security_policy",
            requested_by="admin@example.test",
            request_payload={"keyword_blocklist_enabled": True},
            target_action="settings.security_policy.update",
        )
        listed = approval_service.list_approvals(
            status_filter="pending",
            request_type="settings_change",
        )
        approved = approval_service.process_approval(
            created["id"],
            next_status="approved",
            reviewer="reviewer@example.test",
        )
    finally:
        service.close()

    assert listed["total"] == 1
    assert listed["items"][0]["id"] == created["id"]
    assert listed["items"][0]["status"] == "pending"
    assert approved["id"] == created["id"]
    assert approved["status"] == "approved"
