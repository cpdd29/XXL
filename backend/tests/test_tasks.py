from fastapi.testclient import TestClient

from app.main import app
from app.services.store import store


client = TestClient(app)


def test_list_tasks_returns_items(auth_headers) -> None:
    response = client.get("/api/tasks", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 1
    assert payload["items"][0]["id"]


def test_list_tasks_supports_priority_agent_and_channel_filters(auth_headers) -> None:
    store.tasks = [
        {
            "id": "task-filter-1",
            "title": "筛选命中任务",
            "description": "用于验证更细粒度筛选",
            "status": "running",
            "priority": "high",
            "created_at": "2026-04-06 10:00:00",
            "completed_at": None,
            "agent": "搜索Agent",
            "tokens": 12,
            "duration": None,
            "channel": "telegram",
        },
        {
            "id": "task-filter-2",
            "title": "筛选未命中任务",
            "description": "不应出现在筛选结果中",
            "status": "running",
            "priority": "low",
            "created_at": "2026-04-06 10:01:00",
            "completed_at": None,
            "agent": "写作Agent",
            "tokens": 8,
            "duration": None,
            "channel": "wecom",
        },
    ]

    response = client.get(
        "/api/tasks",
        params={
            "priority": "high",
            "agent": "搜索Agent",
            "channel": "telegram",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == "task-filter-1"
    assert payload["items"][0]["priority"] == "high"
    assert payload["items"][0]["agent"] == "搜索Agent"
    assert payload["items"][0]["channel"] == "telegram"


def test_retry_task_sets_task_to_running(auth_headers) -> None:
    response = client.post("/api/tasks/1/retry", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["task"]["status"] == "running"
    assert payload["task"]["completedAt"] is None
    assert payload["task"]["workflowId"]
    assert payload["task"]["workflowRunId"]

    steps_response = client.get("/api/tasks/1/steps", headers=auth_headers)
    steps_payload = steps_response.json()
    assert steps_response.status_code == 200
    assert steps_payload["items"][-1]["status"] == "running"
    assert steps_payload["items"][0]["title"] == "任务重试"


def test_get_task_enriches_failure_and_delivery_fields(auth_headers) -> None:
    created_at = store.now_string()
    task_id = "task-enriched-detail"
    run_id = "run-enriched-detail"
    store.tasks.append(
        {
            "id": task_id,
            "title": "状态归因详情",
            "description": "验证任务详情会补齐失败归因与回传状态",
            "status": "completed",
            "priority": "medium",
            "created_at": created_at,
            "completed_at": created_at,
            "agent": "写作Agent",
            "tokens": 28,
            "duration": "自动完成",
            "workflow_id": "workflow-1",
            "workflow_run_id": run_id,
        }
    )
    store.workflow_runs.insert(
        0,
        {
            "id": run_id,
            "workflow_id": "workflow-1",
            "workflow_name": "客户服务工作流",
            "task_id": task_id,
            "trigger": "message",
            "intent": "write",
            "status": "completed",
            "created_at": created_at,
            "updated_at": created_at,
            "started_at": created_at,
            "completed_at": created_at,
            "current_stage": "执行完成",
            "active_edges": [],
            "nodes": [],
            "logs": [],
            "dispatch_context": {
                "state": "completed",
                "failure_stage": "outbound",
                "failure_message": "结果已生成，但 Telegram 回传失败：network timeout",
                "delivery_status": "failed",
                "delivery_message": "结果已生成，但 Telegram 回传失败：network timeout",
            },
        },
    )

    response = client.get(f"/api/tasks/{task_id}", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["currentStage"] == "执行完成"
    assert payload["failureStage"] == "outbound"
    assert payload["deliveryStatus"] == "failed"
    assert "回传失败" in payload["statusReason"]


def test_list_tasks_enriches_dispatch_failure_reason(auth_headers) -> None:
    created_at = store.now_string()
    task_id = "task-enriched-list"
    run_id = "run-enriched-list"
    store.tasks.append(
        {
            "id": task_id,
            "title": "调度失败任务",
            "description": "验证列表返回统一失败归因",
            "status": "failed",
            "priority": "high",
            "created_at": created_at,
            "completed_at": created_at,
            "agent": "搜索Agent",
            "tokens": 0,
            "duration": "调度失败",
            "workflow_id": "workflow-1",
            "workflow_run_id": run_id,
        }
    )
    store.workflow_runs.insert(
        0,
        {
            "id": run_id,
            "workflow_id": "workflow-1",
            "workflow_name": "客户服务工作流",
            "task_id": task_id,
            "trigger": "message",
            "intent": "search",
            "status": "failed",
            "created_at": created_at,
            "updated_at": created_at,
            "started_at": created_at,
            "completed_at": created_at,
            "current_stage": "执行失败",
            "active_edges": [],
            "nodes": [],
            "logs": [],
            "dispatch_context": {
                "state": "failed",
                "failure_stage": "dispatch",
                "failure_message": "Dispatcher 发布执行任务失败",
            },
            "last_dispatch_error": "Dispatcher 发布执行任务失败",
        },
    )

    response = client.get("/api/tasks", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    item = next(entry for entry in payload["items"] if entry["id"] == task_id)
    assert item["failureStage"] == "dispatch"
    assert item["failureMessage"] == "Dispatcher 发布执行任务失败"
    assert "调度" in item["statusReason"]
