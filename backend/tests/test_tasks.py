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


def test_get_task_exposes_governance_fields_from_route_decision(auth_headers) -> None:
    created_at = store.now_string()
    task_id = "task-governance-from-route-decision"
    route_decision = {
        "confirmation_status": "pending",
        "approval_status": "not_required",
        "approval_required": False,
        "audit_id": "audit-task-governance-1",
        "idempotency_key": "route:task-governance-1",
        "execution_scope": "read_only",
        "schedule_plan": {"kind": "weekly_report", "cron": "0 15 * * 5", "timezone": "Asia/Shanghai"},
    }
    store.tasks.append(
        {
            "id": task_id,
            "title": "治理字段回传任务",
            "description": "验证任务详情从 route_decision 回填治理字段",
            "status": "pending",
            "priority": "medium",
            "created_at": created_at,
            "completed_at": None,
            "agent": "Dispatcher Agent",
            "tokens": 0,
            "duration": None,
            "route_decision": route_decision,
        }
    )

    response = client.get(f"/api/tasks/{task_id}", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["confirmationStatus"] == "pending"
    assert payload["approvalStatus"] == "not_required"
    assert payload["approvalRequired"] is False
    assert payload["auditId"] == "audit-task-governance-1"
    assert payload["idempotencyKey"] == "route:task-governance-1"
    assert payload["executionScope"] == "read_only"
    assert payload["schedulePlan"]["cron"] == "0 15 * * 5"


def test_get_task_exposes_brain_dispatch_summary_from_dispatch_context(auth_headers) -> None:
    created_at = store.now_string()
    task_id = "task-brain-dispatch-summary"
    store.tasks.append(
        {
            "id": task_id,
            "title": "主脑分发摘要任务",
            "description": "验证任务详情从 dispatch_context 回填主脑分发摘要",
            "status": "running",
            "priority": "medium",
            "created_at": created_at,
            "completed_at": None,
            "agent": "Dispatcher Agent",
            "tokens": 0,
            "duration": None,
            "workflow_run_id": "run-brain-dispatch-summary",
            "route_decision": {"workflow_mode": "free_workflow"},
        }
    )
    store.workflow_runs.append(
        {
            "id": "run-brain-dispatch-summary",
            "workflow_id": "workflow-brain-dispatch",
            "workflow_name": "自由工作流",
            "task_id": task_id,
            "trigger": "message",
            "status": "running",
            "created_at": created_at,
            "updated_at": created_at,
            "started_at": created_at,
            "current_stage": "等待调度",
            "nodes": [],
            "logs": [],
            "dispatch_context": {
                "state": "queued",
                "brain_dispatch_summary": {
                    "dispatch_type": "agent_dispatch",
                    "workflow_mode": "free_workflow",
                    "execution_agent": "Writer Agent",
                    "summary_line": "项目经理 handoff_to_execution -> 路由 free_workflow -> 直达 Writer Agent",
                },
            },
        }
    )

    response = client.get(f"/api/tasks/{task_id}", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["brainDispatchSummary"]["dispatchType"] == "agent_dispatch"
    assert payload["brainDispatchSummary"]["workflowMode"] == "free_workflow"
    assert payload["brainDispatchSummary"]["executionAgent"] == "Writer Agent"
    assert payload["brainDispatchSummary"]["summaryLine"]


def test_get_task_exposes_memory_injection_summary_and_state_machine(auth_headers) -> None:
    ingest = client.post(
        "/api/messages/ingest",
        json={
            "channel": "telegram",
            "platformUserId": "task-memory-user",
            "chatId": "task-memory-chat",
            "text": "请帮我整理一下之前关于安全网关的结论",
        },
    )
    assert ingest.status_code == 200

    response = client.get(f"/api/tasks/{ingest.json()['taskId']}", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["memoryInjectionSummary"]["boundary"] == "long_term_read_only"
    assert {"total_hits", "injected_hits", "blocked_hits", "source_counts"}.issubset(
        set(payload["memoryInjectionSummary"].keys())
    )
    assert payload["stateMachine"]["version"] == "brain_fact_layer_v1"
    assert payload["stateMachine"]["dispatch_state"] in {"queued", "agent_queued", "dispatched", "completed"}
