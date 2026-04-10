from fastapi.testclient import TestClient

from app.main import app
from app.services.store import store


client = TestClient(app)


def test_collaboration_overview_defaults_to_running_task(auth_headers) -> None:
    response = client.get("/api/collaboration/overview", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["session"]["taskId"] == "2"
    assert payload["session"]["workflowId"] == "workflow-1"
    assert "e4-5" in payload["activeEdges"]
    search_node = next(node for node in payload["nodes"] if node["label"] == "搜索 Agent")
    assert search_node["status"] == "running"


def test_collaboration_overview_supports_task_switching(auth_headers) -> None:
    response = client.get(
        "/api/collaboration/overview",
        params={"taskId": "1"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session"]["taskId"] == "1"
    assert payload["session"]["taskStatus"] == "completed"
    assert "e4-6" in payload["activeEdges"]
    write_node = next(node for node in payload["nodes"] if node["label"] == "写作 Agent")
    assert write_node["status"] == "completed"


def test_collaboration_overview_exposes_node_error_history(auth_headers) -> None:
    created_at = store.now_string()
    task_id = "task-collaboration-node-error"
    run_id = "run-task-collaboration-node-error"
    store.tasks.append(
        {
            "id": task_id,
            "workflow_run_id": run_id,
            "workflow_id": "workflow-1",
            "title": "协作节点错误历史测试",
            "description": "验证协作页能看到节点异常归档",
            "status": "failed",
            "priority": "high",
            "created_at": created_at,
            "completed_at": created_at,
            "agent": "搜索Agent",
            "tokens": 64,
            "duration": "失败收敛",
            "result": None,
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
            "memory_hits": 0,
            "warnings": [],
            "dispatch_failure_count": 0,
            "last_dispatch_error": None,
        },
    )
    store.task_steps[task_id] = [
        {
            "id": f"{task_id}-1",
            "title": "执行节点",
            "status": "failed",
            "agent": "搜索Agent",
            "started_at": created_at,
            "finished_at": created_at,
            "message": "协作页需要展示的节点失败",
            "tokens": 64,
        }
    ]

    response = client.get(
        "/api/collaboration/overview",
        params={"taskId": task_id},
        headers=auth_headers,
    )

    assert response.status_code == 200
    search_node = next(node for node in response.json()["nodes"] if node["label"] == "搜索 Agent")
    assert search_node["errorCount"] == 1
    assert search_node["latestError"] == "协作页需要展示的节点失败"
    assert search_node["errorHistory"][0]["stepTitle"] == "执行节点"


def test_collaboration_overview_returns_404_for_unknown_task(auth_headers) -> None:
    response = client.get(
        "/api/collaboration/overview",
        params={"taskId": "missing"},
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"


def test_collaboration_overview_exposes_session_failure_and_delivery_status(auth_headers) -> None:
    created_at = store.now_string()
    task_id = "task-collaboration-attribution"
    run_id = "run-collaboration-attribution"
    store.tasks.append(
        {
            "id": task_id,
            "workflow_run_id": run_id,
            "workflow_id": "workflow-1",
            "title": "协作归因测试",
            "description": "验证协作页会话摘要显示失败归因和回传状态",
            "status": "failed",
            "priority": "high",
            "created_at": created_at,
            "completed_at": created_at,
            "agent": "搜索Agent",
            "tokens": 18,
            "duration": "失败收敛",
            "result": None,
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
                "state": "agent_execution_failed",
                "failure_stage": "execution",
                "failure_message": "Agent Worker 执行超时",
                "delivery_status": "skipped",
                "delivery_message": "任务失败信息已记录，但当前任务未绑定可用出站渠道。",
            },
        },
    )

    response = client.get(
        "/api/collaboration/overview",
        params={"taskId": task_id},
        headers=auth_headers,
    )

    assert response.status_code == 200
    session = response.json()["session"]
    assert session["failureStage"] == "execution"
    assert session["failureMessage"] == "Agent Worker 执行超时"
    assert session["deliveryStatus"] == "skipped"
    assert "失败于执行阶段" in session["statusReason"]
