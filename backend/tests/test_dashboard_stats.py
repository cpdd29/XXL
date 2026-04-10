from fastapi.testclient import TestClient

from app.main import app
from app.services.store import store


client = TestClient(app)


def test_dashboard_stats_are_built_from_runtime_entities_instead_of_static_samples(
    auth_headers,
) -> None:
    store.dashboard_stats = [
        {
            "key": "active_agents",
            "title": "不应再使用",
            "value": 999,
            "description": "静态样例",
            "trend_value": 999,
            "trend_positive": False,
        }
    ]
    store.chart_data = [{"time": "00:00", "requests": 999, "tokens": 999}]
    store.agents = [
        {
            "id": "agent-1",
            "name": "意图识别 Agent",
            "type": "intent",
            "status": "running",
            "enabled": True,
            "tasks_completed": 10,
            "avg_response_time": "45ms",
        },
        {
            "id": "agent-2",
            "name": "搜索 Agent",
            "type": "search",
            "status": "waiting",
            "enabled": True,
            "tasks_completed": 8,
            "avg_response_time": "320ms",
        },
        {
            "id": "agent-3",
            "name": "写作 Agent",
            "type": "write",
            "status": "idle",
            "enabled": True,
            "tasks_completed": 5,
            "avg_response_time": "1.2s",
        },
    ]
    store.workflows = [
        {"id": "workflow-1", "status": "active"},
        {"id": "workflow-2", "status": "draft"},
    ]
    store.tasks = [
        {
            "id": "task-1",
            "status": "completed",
            "tokens": 120,
            "created_at": "2026-04-03T08:10:00+00:00",
        },
        {
            "id": "task-2",
            "status": "running",
            "tokens": 80,
            "created_at": "2026-04-03T10:15:00+00:00",
        },
        {
            "id": "task-3",
            "status": "pending",
            "tokens": 40,
            "created_at": "2026-04-03T11:40:00+00:00",
        },
    ]
    store.workflow_runs = [
        {
            "id": "run-1",
            "task_id": "task-1",
            "status": "completed",
            "created_at": "2026-04-03T08:10:00+00:00",
        },
        {
            "id": "run-2",
            "task_id": "task-2",
            "status": "running",
            "created_at": "2026-04-03T10:15:00+00:00",
        },
        {
            "id": "run-3",
            "task_id": "task-3",
            "status": "pending",
            "created_at": "2026-04-03T11:40:00+00:00",
        },
    ]
    store.realtime_logs = [
        {
            "id": "log-1",
            "timestamp": "11:40:00",
            "type": "info",
            "agent": "Dispatcher Agent",
            "message": "工作流已排队等待执行",
        }
    ]

    response = client.get("/api/dashboard/stats", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    stats_by_key = {item["key"]: item for item in body["stats"]}

    assert stats_by_key["active_agents"]["value"] == 2
    assert stats_by_key["workflows"]["value"] == 2
    assert stats_by_key["pending_tasks"]["value"] == 2
    assert stats_by_key["today_runs"]["value"] == 3
    assert stats_by_key["active_agents"]["title"] != "不应再使用"
    assert len(body["chartData"]) == 7
    assert sum(point["requests"] for point in body["chartData"]) == 3
    assert sum(point["tokens"] for point in body["chartData"]) == 240
    assert body["agentStatuses"][0]["id"] == "agent-1"
    assert body["realtimeLogs"][0]["id"] == "log-1"


def test_dashboard_stats_fall_back_to_tasks_when_workflow_runs_are_missing(
    auth_headers,
) -> None:
    store.agents = []
    store.workflows = []
    store.workflow_runs = []
    store.tasks = [
        {
            "id": "task-a",
            "status": "completed",
            "tokens": 30,
            "created_at": "2026-04-03T09:00:00+00:00",
        },
        {
            "id": "task-b",
            "status": "failed",
            "tokens": 15,
            "created_at": "2026-04-03T13:00:00+00:00",
        },
    ]
    store.realtime_logs = []

    response = client.get("/api/dashboard/stats", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    stats_by_key = {item["key"]: item for item in body["stats"]}

    assert stats_by_key["today_runs"]["value"] == 2
    assert sum(point["requests"] for point in body["chartData"]) == 2
    assert sum(point["tokens"] for point in body["chartData"]) == 45


def test_dashboard_stats_expose_failure_breakdown(auth_headers) -> None:
    store.agents = []
    store.workflows = [{"id": "workflow-1", "status": "active"}]
    store.tasks = [
        {
            "id": "task-dashboard-dispatch",
            "status": "failed",
            "tokens": 12,
            "created_at": "2026-04-03T09:00:00+00:00",
            "workflow_run_id": "run-dashboard-dispatch",
        },
        {
            "id": "task-dashboard-outbound",
            "status": "completed",
            "tokens": 16,
            "created_at": "2026-04-03T10:00:00+00:00",
            "workflow_run_id": "run-dashboard-outbound",
        },
    ]
    store.workflow_runs = [
        {
            "id": "run-dashboard-dispatch",
            "workflow_id": "workflow-1",
            "workflow_name": "客户服务工作流",
            "task_id": "task-dashboard-dispatch",
            "trigger": "message",
            "status": "failed",
            "created_at": "2026-04-03T09:00:00+00:00",
            "updated_at": "2026-04-03T09:05:00+00:00",
            "started_at": "2026-04-03T09:00:00+00:00",
            "completed_at": "2026-04-03T09:05:00+00:00",
            "current_stage": "执行失败",
            "dispatch_context": {
                "state": "failed",
                "failure_stage": "dispatch",
                "failure_message": "dispatcher unavailable",
            },
        },
        {
            "id": "run-dashboard-outbound",
            "workflow_id": "workflow-1",
            "workflow_name": "客户服务工作流",
            "task_id": "task-dashboard-outbound",
            "trigger": "message",
            "status": "completed",
            "created_at": "2026-04-03T10:00:00+00:00",
            "updated_at": "2026-04-03T10:03:00+00:00",
            "started_at": "2026-04-03T10:00:00+00:00",
            "completed_at": "2026-04-03T10:03:00+00:00",
            "current_stage": "执行完成",
            "dispatch_context": {
                "state": "completed",
                "failure_stage": "outbound",
                "failure_message": "channel outbound failed",
                "delivery_status": "failed",
                "delivery_message": "channel outbound failed",
            },
        },
    ]
    store.realtime_logs = []

    response = client.get("/api/dashboard/stats", headers=auth_headers)

    assert response.status_code == 200
    failure_breakdown = {item["stage"]: item["count"] for item in response.json()["failureBreakdown"]}
    assert failure_breakdown["dispatch"] == 1
    assert failure_breakdown["outbound"] == 1
