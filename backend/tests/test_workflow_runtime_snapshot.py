from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services import dashboard_service, workflow_execution_service, workflow_service
from app.services.persistence_service import StatePersistenceService
from app.services.store import InMemoryStore
from app.services.workflow_runtime_snapshot_service import workflow_runtime_snapshot_service


client = TestClient(app)


def _sqlite_service(tmp_path: Path, seeded_store: InMemoryStore) -> StatePersistenceService:
    database_path = tmp_path / "workflow-runtime-snapshot.db"
    service = StatePersistenceService(
        runtime_store=seeded_store,
        database_url=f"sqlite:///{database_path}",
    )
    assert service.initialize() is True
    return service


def test_workflow_runtime_snapshot_service_aggregates_queue_state(tmp_path: Path) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    seeded_store = InMemoryStore()
    seeded_store.workflows = [
        {
            "id": "workflow-runtime",
            "name": "运行时控制面工作流",
            "description": "聚合 queue/lease/dead-letter",
            "version": "v1",
            "status": "active",
            "updated_at": now.isoformat(),
            "node_count": 1,
            "edge_count": 0,
            "trigger": {"type": "manual"},
            "agent_bindings": ["agent-runtime"],
            "nodes": [{"id": "node-1", "type": "trigger", "label": "手动触发", "x": 0, "y": 0}],
            "edges": [],
        }
    ]
    seeded_store.workflow_runs = [
        {
            "id": "run-runtime-retry",
            "workflow_id": "workflow-runtime",
            "workflow_name": "运行时控制面工作流",
            "task_id": "task-runtime-retry",
            "trigger": "manual",
            "intent": "retry",
            "status": "pending",
            "created_at": (now - timedelta(minutes=5)).isoformat(),
            "updated_at": now.isoformat(),
            "started_at": (now - timedelta(minutes=5)).isoformat(),
            "completed_at": None,
            "current_stage": "等待重试",
            "active_edges": [],
            "nodes": [],
            "logs": [],
            "next_dispatch_at": (now + timedelta(minutes=2)).isoformat(),
            "dispatch_failure_count": 2,
            "last_dispatch_error": "dispatch boom",
            "warnings": [],
        },
        {
            "id": "run-runtime-active",
            "workflow_id": "workflow-runtime",
            "workflow_name": "运行时控制面工作流",
            "task_id": "task-runtime-active",
            "trigger": "manual",
            "intent": "execute",
            "status": "running",
            "created_at": (now - timedelta(minutes=3)).isoformat(),
            "updated_at": now.isoformat(),
            "started_at": (now - timedelta(minutes=3)).isoformat(),
            "completed_at": None,
            "current_stage": "执行中",
            "active_edges": [],
            "nodes": [],
            "logs": [],
            "warnings": [],
        },
        {
            "id": "run-runtime-agent-retry",
            "workflow_id": "workflow-runtime",
            "workflow_name": "运行时控制面工作流",
            "task_id": "task-runtime-agent-retry",
            "trigger": "manual",
            "intent": "agent",
            "status": "pending",
            "created_at": (now - timedelta(minutes=1)).isoformat(),
            "updated_at": now.isoformat(),
            "started_at": (now - timedelta(minutes=1)).isoformat(),
            "completed_at": None,
            "current_stage": "等待 Agent 重试",
            "active_edges": [],
            "nodes": [],
            "logs": [],
            "warnings": [],
        },
        {
            "id": "run-runtime-deadletter",
            "workflow_id": "workflow-runtime",
            "workflow_name": "运行时控制面工作流",
            "task_id": "task-runtime-deadletter",
            "trigger": "manual",
            "intent": "dead_letter",
            "status": "failed",
            "created_at": (now - timedelta(minutes=10)).isoformat(),
            "updated_at": (now - timedelta(minutes=1)).isoformat(),
            "started_at": (now - timedelta(minutes=10)).isoformat(),
            "completed_at": (now - timedelta(minutes=1)).isoformat(),
            "current_stage": "失败",
            "active_edges": [],
            "nodes": [],
            "logs": [],
            "dispatch_context": {
                "protocol": {
                    "attempt": 3,
                    "dead_letter": True,
                    "dead_letter_reason": "agent boom",
                    "last_error": "agent boom",
                }
            },
            "failure_message": "agent boom",
            "warnings": [],
        },
    ]

    service = _sqlite_service(tmp_path, seeded_store)
    try:
        service.upsert_workflow_dispatch_job(
            "run-runtime-retry",
            available_at=(now + timedelta(minutes=2)).isoformat(),
            queued_at=(now - timedelta(minutes=1)).isoformat(),
            dispatcher_id="dispatcher-stale",
            claimed_at=(now - timedelta(minutes=2)).isoformat(),
            lease_expires_at=(now - timedelta(minutes=1)).isoformat(),
            protocol={"attempt": 2, "last_error": "dispatch boom"},
        )
        service.upsert_workflow_execution_job(
            "run-runtime-active",
            available_at=now.isoformat(),
            queued_at=(now - timedelta(seconds=30)).isoformat(),
            worker_id="worker-active",
            claimed_at=(now - timedelta(seconds=10)).isoformat(),
            lease_expires_at=(now + timedelta(minutes=1)).isoformat(),
            protocol={"attempt": 1},
        )
        service.upsert_agent_execution_job(
            "run-runtime-agent-retry",
            task_id="task-runtime-agent-retry",
            workflow_id="workflow-runtime",
            execution_agent_id="agent-runtime",
            available_at=(now + timedelta(seconds=45)).isoformat(),
            queued_at=(now - timedelta(seconds=15)).isoformat(),
            protocol={"attempt": 3, "last_error": "agent retry"},
        )

        snapshot = workflow_runtime_snapshot_service.build_snapshot(
            workflow_id="workflow-runtime",
            now=now,
            persistence=service,
        )
    finally:
        service.close()

    assert snapshot["dispatch_queue_depth"] == 1
    assert snapshot["workflow_execution_queue_depth"] == 1
    assert snapshot["agent_execution_queue_depth"] == 1
    assert snapshot["active_workflow_execution_leases"] == 1
    assert snapshot["stale_claims"] == 1
    assert snapshot["retry_scheduled"] == 2
    assert snapshot["dead_letters"] == 1
    assert any(alert["key"] == "retry:run-runtime-retry" for alert in snapshot["recent_alerts"])
    assert any(alert["key"] == "dead_letter:run-runtime-deadletter" for alert in snapshot["recent_alerts"])
    assert any(alert["key"].startswith("stale:dispatch:run-runtime-retry") for alert in snapshot["recent_alerts"])


def test_workflow_monitor_route_exposes_runtime_snapshot(
    tmp_path: Path,
    monkeypatch,
    auth_headers,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    seeded_store = InMemoryStore()
    seeded_store.workflows = [
        {
            "id": "workflow-runtime-monitor",
            "name": "数据库运行监控工作流",
            "description": "monitor 需要带 runtime snapshot",
            "version": "v1",
            "status": "active",
            "updated_at": now.isoformat(),
            "node_count": 1,
            "edge_count": 0,
            "trigger": {"type": "manual"},
            "agent_bindings": ["agent-monitor"],
            "nodes": [{"id": "node-1", "type": "trigger", "label": "手动触发", "x": 0, "y": 0}],
            "edges": [],
        }
    ]
    seeded_store.workflow_runs = [
        {
            "id": "run-monitor-runtime",
            "workflow_id": "workflow-runtime-monitor",
            "workflow_name": "数据库运行监控工作流",
            "task_id": "task-monitor-runtime",
            "trigger": "manual",
            "intent": "retry",
            "status": "pending",
            "created_at": (now - timedelta(minutes=3)).isoformat(),
            "updated_at": now.isoformat(),
            "started_at": (now - timedelta(minutes=3)).isoformat(),
            "completed_at": None,
            "current_stage": "等待重试",
            "active_edges": [],
            "nodes": [],
            "logs": [],
            "next_dispatch_at": (now + timedelta(minutes=2)).isoformat(),
            "dispatch_failure_count": 2,
            "last_dispatch_error": "dispatch retry",
            "warnings": [],
        }
    ]

    service = _sqlite_service(tmp_path, seeded_store)
    monkeypatch.setattr(workflow_service, "persistence_service", service)
    monkeypatch.setattr(workflow_execution_service, "persistence_service", service)

    try:
        service.upsert_workflow_dispatch_job(
            "run-monitor-runtime",
            available_at=(now + timedelta(minutes=2)).isoformat(),
            queued_at=(now - timedelta(minutes=1)).isoformat(),
            dispatcher_id="dispatcher-monitor",
            claimed_at=(now - timedelta(minutes=2)).isoformat(),
            lease_expires_at=(now - timedelta(minutes=1)).isoformat(),
            protocol={"attempt": 2, "last_error": "dispatch retry"},
        )

        response = client.get(
            "/api/workflows/workflow-runtime-monitor/monitor",
            headers=auth_headers,
        )
    finally:
        service.close()

    assert response.status_code == 200
    body = response.json()
    assert body["runtime"]["dispatchQueueDepth"] == 1
    assert body["runtime"]["staleClaims"] == 1
    assert any(alert["key"] == "retry:run-monitor-runtime" for alert in body["runtime"]["recentAlerts"])


def test_dashboard_stats_route_exposes_runtime_snapshot(
    tmp_path: Path,
    monkeypatch,
    auth_headers,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    seeded_store = InMemoryStore()
    seeded_store.agents = []
    seeded_store.workflows = [
        {
            "id": "workflow-runtime-dashboard",
            "name": "数据库仪表盘工作流",
            "description": "dashboard 需要展示 runtime snapshot",
            "version": "v1",
            "status": "active",
            "updated_at": now.isoformat(),
            "node_count": 1,
            "edge_count": 0,
            "trigger": {"type": "manual"},
            "agent_bindings": ["agent-dashboard"],
            "nodes": [{"id": "node-1", "type": "trigger", "label": "手动触发", "x": 0, "y": 0}],
            "edges": [],
        }
    ]
    seeded_store.tasks = [
        {
            "id": "task-dashboard-runtime",
            "title": "数据库 runtime task",
            "description": "dashboard runtime snapshot task",
            "status": "running",
            "priority": "high",
            "created_at": (now - timedelta(minutes=5)).isoformat(),
            "completed_at": None,
            "agent": "Agent Dashboard",
            "tokens": 12,
        }
    ]
    seeded_store.workflow_runs = [
        {
            "id": "run-dashboard-runtime",
            "workflow_id": "workflow-runtime-dashboard",
            "workflow_name": "数据库仪表盘工作流",
            "task_id": "task-dashboard-runtime",
            "trigger": "manual",
            "intent": "retry",
            "status": "pending",
            "created_at": (now - timedelta(minutes=5)).isoformat(),
            "updated_at": now.isoformat(),
            "started_at": (now - timedelta(minutes=5)).isoformat(),
            "completed_at": None,
            "current_stage": "等待重试",
            "active_edges": [],
            "nodes": [],
            "logs": [],
            "next_dispatch_at": (now + timedelta(minutes=1)).isoformat(),
            "dispatch_failure_count": 1,
            "last_dispatch_error": "dashboard dispatch retry",
            "warnings": [],
        }
    ]

    service = _sqlite_service(tmp_path, seeded_store)
    monkeypatch.setattr(dashboard_service, "persistence_service", service)

    try:
        service.upsert_workflow_dispatch_job(
            "run-dashboard-runtime",
            available_at=(now + timedelta(minutes=1)).isoformat(),
            queued_at=(now - timedelta(minutes=1)).isoformat(),
            dispatcher_id="dispatcher-dashboard",
            claimed_at=(now - timedelta(minutes=2)).isoformat(),
            lease_expires_at=(now - timedelta(minutes=1)).isoformat(),
            protocol={"attempt": 2, "last_error": "dashboard dispatch retry"},
        )

        response = client.get("/api/dashboard/stats", headers=auth_headers)
    finally:
        service.close()

    assert response.status_code == 200
    body = response.json()
    assert body["runtime"]["dispatchQueueDepth"] == 1
    assert body["runtime"]["staleClaims"] == 1
    assert any(
        item["key"] == "retry:run-dashboard-runtime"
        for item in body["runtime"]["recentAlerts"]
    )
    assert any(
        item["key"] == "retry:run-dashboard-runtime"
        for item in body["preparedAlerts"]
    )
