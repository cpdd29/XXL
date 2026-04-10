import time
from datetime import UTC, datetime

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.services.agent_execution_service import agent_execution_service
from app.services.channel_outbound_service import channel_outbound_service
from app.services.store import store
from app.services import workflow_execution_service, workflow_service


client = TestClient(app)


def wait_for_run_status(
    run_id: str,
    auth_headers: dict[str, str],
    expected_status: str,
    timeout: float = 6.0,
) -> dict:
    deadline = time.time() + timeout
    last_body: dict | None = None

    while time.time() < deadline:
        response = client.get(
            f"/api/workflows/runs/{run_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        last_body = response.json()
        if last_body["status"] == expected_status:
            return last_body
        time.sleep(0.1)

    raise AssertionError(
        f"Run {run_id} did not reach {expected_status} within {timeout}s; last={last_body}"
    )


def test_manual_workflow_run_creates_task_and_run(auth_headers) -> None:
    response = client.post("/api/workflows/workflow-1/run", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["runId"]
    assert body["taskId"]

    runs_response = client.get("/api/workflows/workflow-1/runs", headers=auth_headers)
    assert runs_response.status_code == 200
    runs_body = runs_response.json()
    assert runs_body["total"] >= 1
    assert runs_body["items"][0]["workflowId"] == "workflow-1"


def test_workflow_run_detail_exposes_node_error_history(auth_headers) -> None:
    created_at = store.now_string()
    task_id = "task-node-error-history"
    run_id = "run-task-node-error-history"
    store.tasks.append(
        {
            "id": task_id,
            "workflow_run_id": run_id,
            "title": "节点错误历史测试",
            "description": "验证 workflow run 详情会返回节点级错误归档",
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
            "message": "搜索执行失败：下游知识库不可用",
            "tokens": 64,
        }
    ]

    response = client.get(f"/api/workflows/runs/{run_id}", headers=auth_headers)

    assert response.status_code == 200
    search_node = next(node for node in response.json()["nodes"] if node["label"] == "搜索 Agent")
    assert search_node["errorCount"] == 1
    assert search_node["latestError"] == "搜索执行失败：下游知识库不可用"
    assert search_node["errorHistory"][0]["source"] == "task_step"
    assert search_node["errorHistory"][0]["stepTitle"] == "执行节点"


def test_message_ingest_creates_workflow_run_visible_to_collaboration(auth_headers) -> None:
    ingest = client.post(
        "/api/messages/ingest",
        json={
            "channel": "telegram",
            "platformUserId": "wf-user",
            "chatId": "wf-chat",
            "text": "请帮我搜索最新的部署文档",
        },
    )
    assert ingest.status_code == 200
    task_id = ingest.json()["taskId"]

    collaboration = client.get(
        "/api/collaboration/overview",
        params={"taskId": task_id},
        headers=auth_headers,
    )
    assert collaboration.status_code == 200
    body = collaboration.json()
    assert body["session"]["workflowRunId"]
    assert body["session"]["workflowId"] == "workflow-1"
    assert body["session"]["taskStatus"] in {"running", "completed"}
    assert any(node["status"] in {"running", "completed"} for node in body["nodes"])


def test_workflow_run_detail_exposes_dispatch_context(auth_headers) -> None:
    ingest = client.post(
        "/api/messages/ingest",
        json={
            "channel": "telegram",
            "platformUserId": "dispatch-context-user",
            "chatId": "dispatch-context-chat",
            "text": "请帮我搜索调度器设计文档",
        },
    )
    assert ingest.status_code == 200

    run_response = client.get(
        f"/api/workflows/runs/{ingest.json()['runId']}",
        headers=auth_headers,
    )

    assert run_response.status_code == 200
    dispatch_context = run_response.json()["dispatchContext"]
    assert dispatch_context["type"] == "message_dispatch"
    assert dispatch_context["routeDecision"]["workflowId"] == "workflow-1"
    assert dispatch_context["routeDecision"]["executionAgent"] == "搜索 Agent"
    assert dispatch_context["messagePreview"] == "请帮我搜索调度器设计文档"
    assert dispatch_context["state"] in {"queued", "dispatched", "completed"}
    monitor = run_response.json()["monitor"]
    assert monitor["triggerType"] == "message"
    assert monitor["dispatchState"] in {"queued", "dispatched", "completed"}
    assert monitor["executionAgentId"] == dispatch_context["routeDecision"]["executionAgentId"]
    assert monitor["monitorState"] in {"queued", "scheduled", "claimed", "running", "completed"}


def test_workflow_run_detail_exposes_failure_and_delivery_attribution(auth_headers) -> None:
    created_at = store.now_string()
    task_id = "task-run-attribution"
    run_id = "run-attribution"
    store.tasks.append(
        {
            "id": task_id,
            "workflow_run_id": run_id,
            "workflow_id": "workflow-1",
            "title": "Workflow Run 归因",
            "description": "验证 workflow run 详情会暴露统一失败归因字段",
            "status": "completed",
            "priority": "medium",
            "created_at": created_at,
            "completed_at": created_at,
            "agent": "写作Agent",
            "tokens": 32,
            "duration": "自动完成",
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

    response = client.get(f"/api/workflows/runs/{run_id}", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["failureStage"] == "outbound"
    assert payload["deliveryStatus"] == "failed"
    assert "channel outbound failed" not in payload["statusReason"]
    assert "network timeout" in payload["statusReason"]


def test_message_ingest_workflow_run_auto_completes_without_manual_tick(auth_headers) -> None:
    ingest = client.post(
        "/api/messages/ingest",
        json={
            "channel": "telegram",
            "platformUserId": "auto-user",
            "chatId": "auto-chat",
            "text": "请帮我写一段发布说明",
        },
    )
    assert ingest.status_code == 200

    run_id = ingest.json()["runId"]
    task_id = ingest.json()["taskId"]
    run_body = wait_for_run_status(run_id, auth_headers, "completed")
    assert any(
        node["type"] == "output" and node["status"] == "completed"
        for node in run_body["nodes"]
    )

    task_response = client.get(f"/api/tasks/{task_id}", headers=auth_headers)
    assert task_response.status_code == 200
    task_body = task_response.json()
    assert task_body["result"]["kind"] == "draft_message"
    assert "发布说明" in task_body["result"]["title"]
    assert "您好" in task_body["result"]["content"]
    assert "本次写作主要参考" in task_body["result"]["content"]
    assert any(
        any(name in reference["title"] for name in ("WorkBot_开发全指南.md", "开发指南补充.md"))
        for reference in task_body["result"]["references"]
    )


def test_english_message_produces_english_result_content(auth_headers) -> None:
    ingest = client.post(
        "/api/messages/ingest",
        json={
            "channel": "telegram",
            "platformUserId": "english-write-user",
            "chatId": "english-write-chat",
            "text": "please write a release note for the workflow dispatcher",
            "metadata": {"preferredLanguage": "en"},
        },
    )
    assert ingest.status_code == 200

    run_id = ingest.json()["runId"]
    task_id = ingest.json()["taskId"]
    wait_for_run_status(run_id, auth_headers, "completed")

    task_response = client.get(f"/api/tasks/{task_id}", headers=auth_headers)
    assert task_response.status_code == 200
    task_body = task_response.json()
    assert task_body["result"]["title"].startswith("Draft Message")
    assert "Hello," in task_body["result"]["content"]
    assert "Primary references used in this draft" in task_body["result"]["content"]
    assert "The draft is grounded in" in " ".join(task_body["result"]["bullets"])


def test_user_profile_preferred_language_drives_english_output_for_chinese_request(
    auth_headers,
) -> None:
    store.user_profiles["crm-profile-en-1"] = {
        "id": "crm-profile-en-1",
        "preferred_language": "en",
        "platform_accounts": [{"platform": "telegram", "account_id": "profile-lang-user"}],
    }

    ingest = client.post(
        "/api/messages/ingest",
        json={
            "channel": "telegram",
            "platformUserId": "profile-lang-user",
            "chatId": "profile-lang-chat",
            "text": "请帮我写一段工作流调度器发布说明",
        },
    )
    assert ingest.status_code == 200
    assert ingest.json()["detectedLang"] == "en"

    run_id = ingest.json()["runId"]
    task_id = ingest.json()["taskId"]
    wait_for_run_status(run_id, auth_headers, "completed")

    task_response = client.get(f"/api/tasks/{task_id}", headers=auth_headers)
    assert task_response.status_code == 200
    task_body = task_response.json()
    assert task_body["result"]["title"].startswith("Draft Message")
    assert "Hello," in task_body["result"]["content"]
    assert "Primary references used in this draft" in task_body["result"]["content"]
    assert "您好" not in task_body["result"]["content"]


def test_tick_workflow_run_advances_to_completion(auth_headers) -> None:
    ingest = client.post(
        "/api/messages/ingest",
        json={
            "channel": "telegram",
            "platformUserId": "tick-user",
            "chatId": "tick-chat",
            "text": "请帮我搜索最新的部署文档",
        },
    )
    assert ingest.status_code == 200
    run_id = ingest.json()["runId"]
    task_id = ingest.json()["taskId"]

    for _ in range(4):
        tick = client.post(
            f"/api/workflows/runs/{run_id}/tick",
            headers=auth_headers,
        )
        assert tick.status_code == 200

    run = client.get(f"/api/workflows/runs/{run_id}", headers=auth_headers)
    assert run.status_code == 200
    run_body = run.json()
    assert run_body["status"] == "completed"
    assert any(node["type"] == "output" and node["status"] == "completed" for node in run_body["nodes"])

    task = client.get(f"/api/tasks/{task_id}", headers=auth_headers)
    assert task.status_code == 200
    task_body = task.json()
    assert task_body["status"] == "completed"
    assert task_body["result"]["kind"] == "search_report"
    assert len(task_body["result"]["references"]) >= 1
    assert "命中的本地项目资料" in task_body["result"]["content"]
    assert any(
        any(
            name in reference["title"]
            for name in (
                "WorkBot_开发全指南.md",
                "开发指南补充.md",
                "security_gateway_pipeline.svg",
                "memory_distillation_lifecycle.svg",
            )
        )
        for reference in task_body["result"]["references"]
    )


def test_failed_workflow_run_exposes_node_error_history_for_missing_execution_agent(
    auth_headers,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        workflow_execution_service,
        "_schedule_manual_auto_progress",
        lambda run_id: None,
    )
    monkeypatch.setattr(
        workflow_execution_service,
        "_cancel_scheduled_run",
        lambda run_id: None,
    )
    monkeypatch.setattr(
        workflow_execution_service,
        "resolve_workflow_execution_agent",
        lambda workflow, intent: None,
    )

    response = client.post("/api/workflows/workflow-1/run", headers=auth_headers)
    assert response.status_code == 200
    run_id = response.json()["runId"]

    tick = client.post(f"/api/workflows/runs/{run_id}/tick", headers=auth_headers)
    assert tick.status_code == 200
    run_body = tick.json()

    assert run_body["status"] == "failed"
    failing_node = next(node for node in run_body["nodes"] if node["label"] == "搜索 Agent")
    assert failing_node["status"] == "error"
    assert failing_node["latestError"] == "选定工作流缺少可用的执行 Agent，任务已终止"
    assert failing_node["errorCount"] >= 1
    assert any(
        item["message"] == "选定工作流缺少可用的执行 Agent，任务已终止"
        for item in failing_node["errorHistory"]
    )


def test_search_result_can_reference_local_architecture_svgs(auth_headers) -> None:
    ingest = client.post(
        "/api/messages/ingest",
        json={
            "channel": "telegram",
            "platformUserId": "svg-user",
            "chatId": "svg-chat",
            "text": "请帮我搜索安全网关和记忆蒸馏方案",
        },
    )
    assert ingest.status_code == 200

    task_id = ingest.json()["taskId"]
    wait_for_run_status(ingest.json()["runId"], auth_headers, "completed")

    task_response = client.get(f"/api/tasks/{task_id}", headers=auth_headers)
    assert task_response.status_code == 200
    task_body = task_response.json()
    assert any(
        any(name in reference["title"] for name in ("security_gateway_pipeline.svg", "memory_distillation_lifecycle.svg"))
        for reference in task_body["result"]["references"]
    )
    assert any(
        keyword in task_body["result"]["content"]
        for keyword in ("安全网关", "记忆蒸馏", "Security gateway", "Memory distillation")
    )


def test_message_ingest_auto_complete_triggers_channel_outbound(
    monkeypatch,
    auth_headers,
) -> None:
    deliveries: list[tuple[str, str]] = []

    monkeypatch.setattr(
        channel_outbound_service,
        "deliver_task_result",
        lambda task, result, *, run=None: deliveries.append((task["id"], result["kind"]))
        or {"status": "sent", "message": "结果已通过 Telegram 回传到 chat auto-outbound"},
    )

    ingest = client.post(
        "/api/messages/ingest",
        json={
            "channel": "telegram",
            "platformUserId": "outbound-user",
            "chatId": "outbound-chat",
            "text": "请帮我搜索消息回传链路",
        },
    )
    assert ingest.status_code == 200

    run_id = ingest.json()["runId"]
    task_id = ingest.json()["taskId"]

    wait_for_run_status(run_id, auth_headers, "completed")

    assert deliveries == [(task_id, "search_report")]


def test_create_workflow_persists_trigger_and_agent_binding(auth_headers) -> None:
    response = client.post(
        "/api/workflows",
        json={
            "name": "定时汇总工作流",
            "description": "每小时执行一次的汇总任务",
            "version": "v1.2",
            "status": "draft",
            "trigger": {
                "type": "schedule",
                "cron": "0 * * * *",
                "description": "每小时执行一次",
                "priority": 180,
                "channels": ["telegram"],
                "preferredLanguage": "en",
            },
            "nodes": [
                {
                    "id": "1",
                    "type": "trigger",
                    "label": "定时触发",
                    "x": 60,
                    "y": 120,
                },
                {
                    "id": "2",
                    "type": "agent",
                    "label": "搜索 Agent",
                    "x": 280,
                    "y": 120,
                    "agentId": "3",
                },
            ],
            "edges": [
                {
                    "id": "e1-2",
                    "source": "1",
                    "target": "2",
                }
            ],
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["workflow"]["trigger"]["type"] == "schedule"
    assert body["workflow"]["trigger"]["cron"] == "0 * * * *"
    assert body["workflow"]["trigger"]["priority"] == 180
    assert body["workflow"]["trigger"]["channels"] == ["telegram"]
    assert body["workflow"]["trigger"]["preferredLanguage"] == "en"
    assert body["workflow"]["nodes"][1]["agentId"] == "3"
    assert body["workflow"]["agentBindings"] == ["3"]


def test_workflow_upsert_preserves_extended_node_types_and_policy_fields(auth_headers) -> None:
    create = client.post(
        "/api/workflows",
        json={
            "name": "扩展节点类型工作流",
            "description": "覆盖 parallel / merge / tool / transform 等扩展节点",
            "version": "v2.0",
            "status": "draft",
            "trigger": {
                "type": "webhook",
                "webhookPath": "/workflows/extended-node-types",
                "description": "扩展节点类型入口",
                "priority": 220,
                "channels": ["telegram", "dingtalk"],
                "preferredLanguage": "en",
                "stepDelaySeconds": 1.25,
                "maxDispatchRetry": 5,
                "dispatchRetryBackoffSeconds": 3.5,
                "executionTimeoutSeconds": 90,
            },
            "nodes": [
                {"id": "1", "type": "trigger", "label": "Webhook 触发", "x": 40, "y": 80},
                {"id": "2", "type": "agent", "label": "搜索 Agent", "x": 220, "y": 80, "agentId": "3"},
                {"id": "3", "type": "condition", "label": "条件判断", "x": 420, "y": 80},
                {"id": "4", "type": "parallel", "label": "并行分发", "x": 620, "y": 80},
                {"id": "5", "type": "tool", "label": "工具调用", "x": 820, "y": 40},
                {"id": "6", "type": "transform", "label": "结果转换", "x": 820, "y": 140},
                {"id": "7", "type": "merge", "label": "结果归并", "x": 1040, "y": 80},
                {"id": "8", "type": "output", "label": "输出结果", "x": 1240, "y": 80},
            ],
            "edges": [
                {"id": "e1-2", "source": "1", "target": "2"},
                {"id": "e2-3", "source": "2", "target": "3"},
                {"id": "e3-4", "source": "3", "target": "4"},
                {"id": "e4-5", "source": "4", "target": "5"},
                {"id": "e5-6", "source": "5", "target": "6"},
                {"id": "e6-7", "source": "6", "target": "7"},
                {"id": "e7-8", "source": "7", "target": "8"},
            ],
        },
        headers=auth_headers,
    )

    assert create.status_code == 200
    created_workflow = create.json()["workflow"]
    workflow_id = created_workflow["id"]
    assert [node["type"] for node in created_workflow["nodes"]] == [
        "trigger",
        "agent",
        "condition",
        "parallel",
        "tool",
        "transform",
        "merge",
        "output",
    ]
    assert created_workflow["trigger"]["stepDelaySeconds"] == 1.25
    assert created_workflow["trigger"]["maxDispatchRetry"] == 5
    assert created_workflow["trigger"]["dispatchRetryBackoffSeconds"] == 3.5
    assert created_workflow["trigger"]["executionTimeoutSeconds"] == 90
    assert created_workflow["agentBindings"] == ["3"]

    update = client.put(
        f"/api/workflows/{workflow_id}",
        json={
            "name": "扩展节点类型工作流 v2",
            "description": "更新后的扩展节点定义与策略",
            "version": "v2.1",
            "status": "active",
            "trigger": {
                "type": "internal",
                "internalEvent": "workflow.extended.updated",
                "description": "扩展节点更新事件",
                "priority": 260,
                "channels": ["telegram"],
                "preferredLanguage": "zh",
                "stepDelaySeconds": 0.9,
                "maxDispatchRetry": 4,
                "dispatchRetryBackoffSeconds": 4.5,
                "executionTimeoutSeconds": 120,
            },
            "nodes": [
                {"id": "1", "type": "trigger", "label": "内部触发", "x": 40, "y": 80},
                {"id": "2", "type": "parallel", "label": "并行分发", "x": 240, "y": 80},
                {"id": "3", "type": "tool", "label": "工具节点", "x": 440, "y": 40},
                {"id": "4", "type": "transform", "label": "转换节点", "x": 440, "y": 140},
                {"id": "5", "type": "merge", "label": "汇总节点", "x": 660, "y": 80},
                {"id": "6", "type": "output", "label": "发送结果", "x": 860, "y": 80},
            ],
            "edges": [
                {"id": "e1-2", "source": "1", "target": "2"},
                {"id": "e2-3", "source": "2", "target": "3"},
                {"id": "e3-4", "source": "3", "target": "4"},
                {"id": "e4-5", "source": "4", "target": "5"},
                {"id": "e5-6", "source": "5", "target": "6"},
            ],
        },
        headers=auth_headers,
    )

    assert update.status_code == 200
    updated_workflow = update.json()["workflow"]
    assert updated_workflow["name"] == "扩展节点类型工作流 v2"
    assert [node["type"] for node in updated_workflow["nodes"]] == [
        "trigger",
        "parallel",
        "tool",
        "transform",
        "merge",
        "output",
    ]
    assert updated_workflow["trigger"]["type"] == "internal"
    assert updated_workflow["trigger"]["internalEvent"] == "workflow.extended.updated"
    assert updated_workflow["trigger"]["stepDelaySeconds"] == 0.9
    assert updated_workflow["trigger"]["maxDispatchRetry"] == 4
    assert updated_workflow["trigger"]["dispatchRetryBackoffSeconds"] == 4.5
    assert updated_workflow["trigger"]["executionTimeoutSeconds"] == 120
    assert updated_workflow["agentBindings"] == []


def test_internal_trigger_route_starts_matching_workflow_and_injects_event_context(
    auth_headers,
) -> None:
    create = client.post(
        "/api/workflows",
        json={
            "name": "内部事件巡检工作流",
            "description": "处理系统内部事件",
            "version": "v1.0",
            "status": "active",
            "trigger": {
                "type": "internal",
                "internalEvent": "memory.distilled",
                "description": "处理记忆蒸馏完成事件",
                "priority": 180,
            },
            "nodes": [
                {
                    "id": "1",
                    "type": "trigger",
                    "label": "内部触发",
                    "x": 60,
                    "y": 120,
                },
                {
                    "id": "2",
                    "type": "agent",
                    "label": "搜索 Agent",
                    "x": 280,
                    "y": 120,
                    "agentId": "3",
                },
            ],
            "edges": [{"id": "e1-2", "source": "1", "target": "2"}],
        },
        headers=auth_headers,
    )
    assert create.status_code == 200
    workflow_id = create.json()["workflow"]["id"]

    response = client.post(
        "/api/workflows/internal/memory.distilled",
        json={
            "source": "Memory Service",
            "payload": {
                "sessionId": "session-memory-1",
                "trigger": "daily",
                "userId": "crm-001",
            },
        },
        headers=auth_headers,
    )
    assert response.status_code == 200

    body = response.json()
    assert body["ok"] is True
    assert body["workflow"]["id"] == workflow_id
    assert body["triggeredCount"] == 1
    assert body["triggeredWorkflowIds"] == [workflow_id]
    assert body["triggeredRunIds"] == [body["runId"]]
    assert body["triggeredTaskIds"] == [body["taskId"]]

    run_body = wait_for_run_status(body["runId"], auth_headers, "completed")
    assert run_body["workflowId"] == workflow_id
    assert run_body["trigger"] == "internal:memory.distilled"
    assert run_body["monitor"]["triggerType"] == "internal"
    assert run_body["monitor"]["monitorState"] == "completed"
    assert run_body["monitor"]["nextAction"] == "none"

    task = client.get(f"/api/tasks/{body['taskId']}", headers=auth_headers)
    assert task.status_code == 200
    task_body = task.json()
    assert task_body["title"] == "内部触发 - 内部事件巡检工作流 - Memory Service"
    assert "内部事件: memory.distilled" in task_body["description"]
    assert "事件来源: Memory Service" in task_body["description"]
    assert "Payload 字段: sessionId, trigger, userId" in task_body["description"]

    steps = client.get(f"/api/tasks/{body['taskId']}/steps", headers=auth_headers)
    assert steps.status_code == 200
    assert "已接收内部事件 memory.distilled" in steps.json()["items"][0]["message"]


def test_internal_trigger_route_fans_out_to_all_matching_workflows_in_priority_order(
    auth_headers,
) -> None:
    primary_create = client.post(
        "/api/workflows",
        json={
            "name": "内部事件主工作流",
            "description": "优先级更高的内部事件处理链",
            "version": "v1.0",
            "status": "active",
            "trigger": {
                "type": "internal",
                "internalEvent": "fanout.event",
                "description": "主内部事件入口",
                "priority": 240,
            },
            "nodes": [
                {"id": "1", "type": "trigger", "label": "内部触发", "x": 60, "y": 120},
                {"id": "2", "type": "agent", "label": "搜索 Agent", "x": 280, "y": 120, "agentId": "3"},
            ],
            "edges": [{"id": "e1-2", "source": "1", "target": "2"}],
        },
        headers=auth_headers,
    )
    assert primary_create.status_code == 200
    primary_workflow_id = primary_create.json()["workflow"]["id"]

    secondary_create = client.post(
        "/api/workflows",
        json={
            "name": "内部事件副工作流",
            "description": "优先级稍低的内部事件处理链",
            "version": "v1.0",
            "status": "active",
            "trigger": {
                "type": "internal",
                "internalEvent": "fanout.event",
                "description": "副内部事件入口",
                "priority": 180,
            },
            "nodes": [
                {"id": "1", "type": "trigger", "label": "内部触发", "x": 60, "y": 120},
                {"id": "2", "type": "agent", "label": "写作 Agent", "x": 280, "y": 120, "agentId": "4"},
            ],
            "edges": [{"id": "e1-2", "source": "1", "target": "2"}],
        },
        headers=auth_headers,
    )
    assert secondary_create.status_code == 200
    secondary_workflow_id = secondary_create.json()["workflow"]["id"]

    response = client.post(
        "/api/workflows/internal/fanout.event",
        json={
            "source": "Internal Bus",
            "payload": {
                "sessionId": "fanout-session-1",
                "topic": "fanout-test",
            },
        },
        headers=auth_headers,
    )
    assert response.status_code == 200

    body = response.json()
    assert body["ok"] is True
    assert body["message"] == "Workflow internal fan-out accepted"
    assert body["workflow"]["id"] == primary_workflow_id
    assert body["runId"] == body["triggeredRunIds"][0]
    assert body["taskId"] == body["triggeredTaskIds"][0]
    assert body["triggeredCount"] == 2
    assert body["triggeredWorkflowIds"] == [primary_workflow_id, secondary_workflow_id]
    assert len(body["triggeredRunIds"]) == 2
    assert len(body["triggeredTaskIds"]) == 2

    primary_run = wait_for_run_status(body["triggeredRunIds"][0], auth_headers, "completed")
    secondary_run = wait_for_run_status(body["triggeredRunIds"][1], auth_headers, "completed")
    assert primary_run["workflowId"] == primary_workflow_id
    assert secondary_run["workflowId"] == secondary_workflow_id
    assert primary_run["trigger"] == "internal:fanout.event"
    assert secondary_run["trigger"] == "internal:fanout.event"

    primary_task = client.get(f"/api/tasks/{body['triggeredTaskIds'][0]}", headers=auth_headers)
    secondary_task = client.get(f"/api/tasks/{body['triggeredTaskIds'][1]}", headers=auth_headers)
    assert primary_task.status_code == 200
    assert secondary_task.status_code == 200
    assert "内部事件: fanout.event" in primary_task.json()["description"]
    assert "内部事件: fanout.event" in secondary_task.json()["description"]


def test_internal_trigger_route_returns_404_for_unknown_event(auth_headers) -> None:
    response = client.post(
        "/api/workflows/internal/missing.event",
        json={"source": "System", "payload": {"taskId": "missing"}},
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Workflow internal trigger not found"

    ignored = client.get(
        "/api/workflows/internal-deliveries",
        params={"status": "ignored", "eventName": "missing.event"},
        headers=auth_headers,
    )
    assert ignored.status_code == 200
    ignored_body = ignored.json()
    assert ignored_body["total"] == 1
    assert ignored_body["items"][0]["status"] == "ignored"
    assert ignored_body["items"][0]["lastError"] == "Workflow internal trigger not found"
    assert ignored_body["items"][0]["attemptCount"] == 1

    failed = client.get(
        "/api/workflows/internal-deliveries",
        params={"status": "failed", "eventName": "missing.event"},
        headers=auth_headers,
    )
    assert failed.status_code == 200
    assert failed.json() == {"items": [], "total": 0}

    retry = client.post(
        f"/api/workflows/internal-deliveries/{ignored_body['items'][0]['id']}/retry",
        headers=auth_headers,
    )
    assert retry.status_code == 200
    retry_body = retry.json()
    assert retry_body["internalEventStatus"] == "ignored"
    assert retry_body["message"] == "Workflow internal delivery closed without matching trigger"
    assert retry_body["delivery"]["status"] == "ignored"
    assert retry_body["delivery"]["attemptCount"] == 2


def test_internal_trigger_route_deduplicates_successful_delivery(auth_headers) -> None:
    create = client.post(
        "/api/workflows",
        json={
            "name": "内部事件幂等工作流",
            "description": "验证 internal event 成功后会按幂等 key 去重",
            "version": "v1.0",
            "status": "active",
            "trigger": {
                "type": "internal",
                "internalEvent": "dedupe.event",
                "description": "内部事件幂等入口",
                "priority": 190,
            },
            "nodes": [
                {"id": "1", "type": "trigger", "label": "内部触发", "x": 60, "y": 120},
                {"id": "2", "type": "agent", "label": "搜索 Agent", "x": 280, "y": 120, "agentId": "3"},
            ],
            "edges": [{"id": "e1-2", "source": "1", "target": "2"}],
        },
        headers=auth_headers,
    )
    assert create.status_code == 200
    workflow_id = create.json()["workflow"]["id"]

    request_payload = {
        "source": "Memory Service",
        "idempotencyKey": "dedupe-route-1",
        "payload": {
            "sessionId": "dedupe-session-1",
            "trigger": "session_end",
            "userId": "crm-dedupe-1",
        },
    }

    first = client.post(
        "/api/workflows/internal/dedupe.event",
        json=request_payload,
        headers=auth_headers,
    )
    second = client.post(
        "/api/workflows/internal/dedupe.event",
        json=request_payload,
        headers=auth_headers,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    first_body = first.json()
    second_body = second.json()
    assert first_body["deduplicated"] is False
    assert second_body["deduplicated"] is True
    assert second_body["internalEventStatus"] == "delivered"
    assert second_body["internalEventAttemptCount"] == 1
    assert second_body["internalEventId"] == first_body["internalEventId"]
    assert second_body["runId"] == first_body["runId"]
    assert second_body["taskId"] == first_body["taskId"]
    assert second_body["triggeredRunIds"] == first_body["triggeredRunIds"]
    assert second_body["triggeredTaskIds"] == first_body["triggeredTaskIds"]

    runs_response = client.get(
        f"/api/workflows/{workflow_id}/runs",
        headers=auth_headers,
    )
    assert runs_response.status_code == 200
    assert runs_response.json()["total"] == 1


def test_internal_event_delivery_routes_list_and_get_delivery_detail(auth_headers) -> None:
    create = client.post(
        "/api/workflows",
        json={
            "name": "内部事件台账工作流",
            "description": "验证 internal event delivery 控制面查询",
            "version": "v1.0",
            "status": "active",
            "trigger": {
                "type": "internal",
                "internalEvent": "delivery.visible.event",
                "description": "内部事件台账入口",
                "priority": 220,
            },
            "nodes": [
                {"id": "1", "type": "trigger", "label": "内部触发", "x": 60, "y": 120},
                {"id": "2", "type": "agent", "label": "搜索 Agent", "x": 280, "y": 120, "agentId": "3"},
            ],
            "edges": [{"id": "e1-2", "source": "1", "target": "2"}],
        },
        headers=auth_headers,
    )
    assert create.status_code == 200
    workflow_id = create.json()["workflow"]["id"]

    trigger = client.post(
        "/api/workflows/internal/delivery.visible.event",
        json={
            "source": "Memory Service",
            "idempotencyKey": "delivery-visible-1",
            "payload": {
                "sessionId": "delivery-visible-session-1",
                "userId": "crm-visible-1",
            },
        },
        headers=auth_headers,
    )
    assert trigger.status_code == 200
    trigger_body = trigger.json()

    listed = client.get(
        "/api/workflows/internal-deliveries",
        params={"eventName": "delivery.visible.event"},
        headers=auth_headers,
    )
    assert listed.status_code == 200
    listed_body = listed.json()
    assert listed_body["total"] == 1
    assert listed_body["items"][0]["id"] == trigger_body["internalEventId"]
    assert listed_body["items"][0]["status"] == "delivered"
    assert listed_body["items"][0]["attemptCount"] == 1
    assert listed_body["items"][0]["triggeredWorkflowIds"] == [workflow_id]
    assert listed_body["items"][0]["primaryWorkflow"]["id"] == workflow_id

    detail = client.get(
        f"/api/workflows/internal-deliveries/{trigger_body['internalEventId']}",
        headers=auth_headers,
    )
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["id"] == trigger_body["internalEventId"]
    assert detail_body["eventName"] == "delivery.visible.event"
    assert detail_body["source"] == "Memory Service"
    assert detail_body["payload"]["userId"] == "crm-visible-1"
    assert detail_body["triggeredRunIds"] == trigger_body["triggeredRunIds"]
    assert detail_body["primaryWorkflow"]["id"] == workflow_id


def test_internal_trigger_retries_failed_delivery_without_duplicating_completed_runs(
    auth_headers,
    monkeypatch,
) -> None:
    primary_create = client.post(
        "/api/workflows",
        json={
            "name": "内部事件重试主工作流",
            "description": "验证 internal event 失败后可续跑",
            "version": "v1.0",
            "status": "active",
            "trigger": {
                "type": "internal",
                "internalEvent": "retry.partial.event",
                "description": "内部事件重试主入口",
                "priority": 240,
            },
            "nodes": [
                {"id": "1", "type": "trigger", "label": "内部触发", "x": 60, "y": 120},
                {"id": "2", "type": "agent", "label": "搜索 Agent", "x": 280, "y": 120, "agentId": "3"},
            ],
            "edges": [{"id": "e1-2", "source": "1", "target": "2"}],
        },
        headers=auth_headers,
    )
    secondary_create = client.post(
        "/api/workflows",
        json={
            "name": "内部事件重试副工作流",
            "description": "验证 partial failure 后只补剩余 fan-out",
            "version": "v1.0",
            "status": "active",
            "trigger": {
                "type": "internal",
                "internalEvent": "retry.partial.event",
                "description": "内部事件重试副入口",
                "priority": 180,
            },
            "nodes": [
                {"id": "1", "type": "trigger", "label": "内部触发", "x": 60, "y": 120},
                {"id": "2", "type": "agent", "label": "写作 Agent", "x": 280, "y": 120, "agentId": "4"},
            ],
            "edges": [{"id": "e1-2", "source": "1", "target": "2"}],
        },
        headers=auth_headers,
    )

    assert primary_create.status_code == 200
    assert secondary_create.status_code == 200
    primary_workflow_id = primary_create.json()["workflow"]["id"]
    secondary_workflow_id = secondary_create.json()["workflow"]["id"]

    original_create_manual_workflow_run = workflow_service.create_manual_workflow_run
    call_count = {"count": 0}

    def flaky_create_manual_workflow_run(*args, **kwargs):
        call_count["count"] += 1
        if call_count["count"] == 2:
            raise RuntimeError("transient internal trigger failure")
        return original_create_manual_workflow_run(*args, **kwargs)

    monkeypatch.setattr(
        workflow_service,
        "create_manual_workflow_run",
        flaky_create_manual_workflow_run,
    )

    with pytest.raises(RuntimeError):
        workflow_service.trigger_workflow_internal(
            "retry.partial.event",
            {"sessionId": "retry-session-1", "topic": "retry-test"},
            source="Internal Bus",
            idempotency_key="retry-partial-1",
        )

    monkeypatch.setattr(
        workflow_service,
        "create_manual_workflow_run",
        original_create_manual_workflow_run,
    )

    retry_payload = workflow_service.trigger_workflow_internal(
        "retry.partial.event",
        {"sessionId": "retry-session-1", "topic": "retry-test"},
        source="Internal Bus",
        idempotency_key="retry-partial-1",
    )

    assert retry_payload["deduplicated"] is False
    assert retry_payload["internal_event_status"] == "delivered"
    assert retry_payload["internal_event_attempt_count"] == 2
    assert retry_payload["triggered_count"] == 2
    assert retry_payload["triggered_workflow_ids"] == [primary_workflow_id, secondary_workflow_id]
    assert len(set(retry_payload["triggered_run_ids"])) == 2
    assert len(set(retry_payload["triggered_task_ids"])) == 2

    matching_runs = [
        run
        for run in store.workflow_runs
        if run["trigger"] == "internal:retry.partial.event"
        and run["workflow_id"] in {primary_workflow_id, secondary_workflow_id}
    ]
    assert len(matching_runs) == 2


def test_internal_event_delivery_retry_route_resumes_failed_delivery(
    auth_headers,
    monkeypatch,
) -> None:
    primary_create = client.post(
        "/api/workflows",
        json={
            "name": "内部事件重试控制面主工作流",
            "description": "验证 internal event delivery retry route",
            "version": "v1.0",
            "status": "active",
            "trigger": {
                "type": "internal",
                "internalEvent": "retry.delivery.route.event",
                "description": "内部事件重试控制面主入口",
                "priority": 240,
            },
            "nodes": [
                {"id": "1", "type": "trigger", "label": "内部触发", "x": 60, "y": 120},
                {"id": "2", "type": "agent", "label": "搜索 Agent", "x": 280, "y": 120, "agentId": "3"},
            ],
            "edges": [{"id": "e1-2", "source": "1", "target": "2"}],
        },
        headers=auth_headers,
    )
    secondary_create = client.post(
        "/api/workflows",
        json={
            "name": "内部事件重试控制面副工作流",
            "description": "验证 internal event delivery retry route partial failure resume",
            "version": "v1.0",
            "status": "active",
            "trigger": {
                "type": "internal",
                "internalEvent": "retry.delivery.route.event",
                "description": "内部事件重试控制面副入口",
                "priority": 180,
            },
            "nodes": [
                {"id": "1", "type": "trigger", "label": "内部触发", "x": 60, "y": 120},
                {"id": "2", "type": "agent", "label": "写作 Agent", "x": 280, "y": 120, "agentId": "4"},
            ],
            "edges": [{"id": "e1-2", "source": "1", "target": "2"}],
        },
        headers=auth_headers,
    )

    assert primary_create.status_code == 200
    assert secondary_create.status_code == 200
    primary_workflow_id = primary_create.json()["workflow"]["id"]
    secondary_workflow_id = secondary_create.json()["workflow"]["id"]

    original_create_manual_workflow_run = workflow_service.create_manual_workflow_run
    call_count = {"count": 0}

    def flaky_create_manual_workflow_run(*args, **kwargs):
        call_count["count"] += 1
        if call_count["count"] == 2:
            raise RuntimeError("transient internal delivery retry route failure")
        return original_create_manual_workflow_run(*args, **kwargs)

    monkeypatch.setattr(
        workflow_service,
        "create_manual_workflow_run",
        flaky_create_manual_workflow_run,
    )

    with pytest.raises(RuntimeError):
        workflow_service.trigger_workflow_internal(
            "retry.delivery.route.event",
            {"sessionId": "retry-delivery-route-session-1", "topic": "retry-route"},
            source="Internal Bus",
            idempotency_key="retry-delivery-route-1",
        )

    monkeypatch.setattr(
        workflow_service,
        "create_manual_workflow_run",
        original_create_manual_workflow_run,
    )

    failed_list = client.get(
        "/api/workflows/internal-deliveries",
        params={"status": "failed", "eventName": "retry.delivery.route.event"},
        headers=auth_headers,
    )
    assert failed_list.status_code == 200
    failed_body = failed_list.json()
    assert failed_body["total"] == 1
    assert failed_body["items"][0]["attemptCount"] == 1
    delivery_id = failed_body["items"][0]["id"]

    retry = client.post(
        f"/api/workflows/internal-deliveries/{delivery_id}/retry",
        headers=auth_headers,
    )
    assert retry.status_code == 200
    retry_body = retry.json()
    assert retry_body["deduplicated"] is False
    assert retry_body["internalEventId"] == delivery_id
    assert retry_body["internalEventStatus"] == "delivered"
    assert retry_body["internalEventAttemptCount"] == 2
    assert retry_body["triggeredCount"] == 2
    assert retry_body["triggeredWorkflowIds"] == [primary_workflow_id, secondary_workflow_id]
    assert len(set(retry_body["triggeredRunIds"])) == 2
    assert retry_body["delivery"]["id"] == delivery_id
    assert retry_body["delivery"]["status"] == "delivered"
    assert retry_body["delivery"]["attemptCount"] == 2
    assert retry_body["delivery"]["triggeredWorkflowIds"] == [
        primary_workflow_id,
        secondary_workflow_id,
    ]

    detail = client.get(
        f"/api/workflows/internal-deliveries/{delivery_id}",
        headers=auth_headers,
    )
    assert detail.status_code == 200
    assert detail.json()["status"] == "delivered"
    assert detail.json()["attemptCount"] == 2


def test_internal_event_delivery_replay_route_creates_new_delivery_and_run(
    auth_headers,
) -> None:
    create = client.post(
        "/api/workflows",
        json={
            "name": "内部事件重放工作流",
            "description": "验证 internal event delivery replay route",
            "version": "v1.0",
            "status": "active",
            "trigger": {
                "type": "internal",
                "internalEvent": "replay.visible.event",
                "description": "内部事件重放入口",
                "priority": 210,
            },
            "nodes": [
                {"id": "1", "type": "trigger", "label": "内部触发", "x": 60, "y": 120},
                {"id": "2", "type": "agent", "label": "搜索 Agent", "x": 280, "y": 120, "agentId": "3"},
            ],
            "edges": [{"id": "e1-2", "source": "1", "target": "2"}],
        },
        headers=auth_headers,
    )
    assert create.status_code == 200
    workflow_id = create.json()["workflow"]["id"]

    first = client.post(
        "/api/workflows/internal/replay.visible.event",
        json={
            "source": "Memory Service",
            "idempotencyKey": "replay-visible-1",
            "payload": {
                "sessionId": "replay-visible-session-1",
                "trigger": "weekly",
            },
        },
        headers=auth_headers,
    )
    assert first.status_code == 200
    first_body = first.json()

    replay = client.post(
        f"/api/workflows/internal-deliveries/{first_body['internalEventId']}/replay",
        headers=auth_headers,
    )
    assert replay.status_code == 200
    replay_body = replay.json()

    assert replay_body["message"] == "Internal event delivery replay accepted"
    assert replay_body["replayedFromDeliveryId"] == first_body["internalEventId"]
    assert replay_body["internalEventId"] != first_body["internalEventId"]
    assert replay_body["runId"] != first_body["runId"]
    assert replay_body["taskId"] != first_body["taskId"]
    assert replay_body["delivery"]["id"] == replay_body["internalEventId"]
    assert replay_body["delivery"]["status"] == "delivered"
    assert replay_body["delivery"]["idempotencyKey"] is not None
    assert f":replay:{first_body['internalEventId']}:" in replay_body["delivery"]["idempotencyKey"]

    runs_response = client.get(
        f"/api/workflows/{workflow_id}/runs",
        headers=auth_headers,
    )
    assert runs_response.status_code == 200
    assert runs_response.json()["total"] == 2

    replay_detail = client.get(
        f"/api/workflows/internal-deliveries/{replay_body['internalEventId']}",
        headers=auth_headers,
    )
    assert replay_detail.status_code == 200
    assert replay_detail.json()["id"] == replay_body["internalEventId"]
    assert replay_detail.json()["triggeredRunIds"] == [replay_body["runId"]]


def test_retry_internal_event_delivery_closes_ignored_delivery_without_requeue() -> None:
    created_at = store.now_string()
    workflow_service._cache_internal_event_delivery(
        {
            "id": "evt-ignored-no-trigger",
            "event_name": "missing.event",
            "source": "Memory Service",
            "payload": {"sessionId": "missing-session-1"},
            "idempotency_key": "missing-trigger-idempotency",
            "status": "ignored",
            "attempt_count": 1,
            "last_error": "Workflow internal trigger not found",
            "created_at": created_at,
            "updated_at": created_at,
            "delivered_at": None,
            "triggered_count": 0,
            "triggered_workflow_ids": [],
            "triggered_run_ids": [],
            "triggered_task_ids": [],
            "primary_workflow": None,
        }
    )

    payload = workflow_service.retry_internal_event_delivery("evt-ignored-no-trigger")
    delivery = workflow_service.get_internal_event_delivery("evt-ignored-no-trigger")

    assert payload["ok"] is True
    assert payload["message"] == "Workflow internal delivery closed without matching trigger"
    assert payload["internal_event_status"] == "ignored"
    assert payload["triggered_count"] == 0
    assert delivery["status"] == "ignored"


def test_poll_scheduled_workflows_creates_due_run_for_current_slot(auth_headers, monkeypatch) -> None:
    fixed_now = datetime(2026, 4, 4, 12, 0, 30, tzinfo=UTC)
    scheduled_run_ids: list[str] = []
    monkeypatch.setattr(
        workflow_execution_service,
        "_schedule_manual_auto_progress",
        lambda run_id: scheduled_run_ids.append(run_id),
    )

    store.workflows.insert(
        0,
        {
            "id": "workflow-schedule-due",
            "name": "定时知识库巡检",
            "description": "每小时执行一次巡检摘要",
            "version": "v1",
            "status": "active",
            "updated_at": "2026-04-04T11:30:00+00:00",
            "node_count": 2,
            "edge_count": 1,
            "trigger": {"type": "schedule", "cron": "0 * * * *", "description": "整点执行"},
            "agent_bindings": ["3"],
            "nodes": [
                {"id": "1", "type": "trigger", "label": "定时触发", "x": 0, "y": 0},
                {"id": "2", "type": "agent", "label": "搜索 Agent", "agent_id": "3", "x": 120, "y": 0},
            ],
            "edges": [{"id": "e1-2", "source": "1", "target": "2"}],
        },
    )

    summary = workflow_service.poll_scheduled_workflows(now=fixed_now)

    assert summary["triggered"] == 1
    run = next(run for run in store.workflow_runs if run["workflow_id"] == "workflow-schedule-due")
    task = next(task for task in store.tasks if task["id"] == run["task_id"])
    assert run["trigger"] == "schedule:2026-04-04T12:00:00+00:00"
    assert task["title"] == "定时触发 - 定时知识库巡检 - 2026-04-04 12:00 UTC"
    assert "Cron 表达式: 0 * * * *" in task["description"]
    assert scheduled_run_ids == [run["id"]]
    run_detail = client.get(f"/api/workflows/runs/{run['id']}", headers=auth_headers)
    assert run_detail.status_code == 200
    assert run_detail.json()["monitor"]["triggerType"] == "schedule"
    assert run_detail.json()["monitor"]["monitorState"] == "queued"
    assert run_detail.json()["monitor"]["nextAction"] == "dispatch"


def test_workflow_monitor_route_aggregates_run_states(auth_headers) -> None:
    store.workflow_runs[0:0] = [
        {
            "id": "run-monitor-completed",
            "workflow_id": "workflow-1",
            "workflow_name": "客户服务工作流",
            "task_id": "task-monitor-completed",
            "trigger": "manual",
            "intent": "search",
            "status": "completed",
            "created_at": "2026-04-04T11:20:00+00:00",
            "updated_at": "2026-04-04T11:22:00+00:00",
            "started_at": "2026-04-04T11:20:05+00:00",
            "completed_at": "2026-04-04T11:22:00+00:00",
            "current_stage": "已完成",
            "active_edges": [],
            "nodes": [],
            "logs": [],
            "dispatch_context": {"state": "completed", "executionAgentId": "3"},
            "warnings": [],
        },
        {
            "id": "run-monitor-claimed",
            "workflow_id": "workflow-1",
            "workflow_name": "客户服务工作流",
            "task_id": "task-monitor-claimed",
            "trigger": "message",
            "intent": "search",
            "status": "running",
            "created_at": "2026-04-04T11:40:00+00:00",
            "updated_at": "2026-04-04T11:40:10+00:00",
            "started_at": "2026-04-04T11:40:00+00:00",
            "completed_at": None,
            "current_stage": "调度中",
            "active_edges": [],
            "nodes": [],
            "logs": [],
            "dispatch_context": {"state": "dispatched", "executionAgentId": "3"},
            "dispatcher_id": "dispatcher-monitor",
            "dispatch_claimed_at": "2026-04-04T11:40:10+00:00",
            "dispatch_lease_expires_at": "2099-04-04T11:40:40+00:00",
            "warnings": [],
        },
        {
            "id": "run-monitor-scheduled",
            "workflow_id": "workflow-1",
            "workflow_name": "客户服务工作流",
            "task_id": "task-monitor-scheduled",
            "trigger": "schedule:2099-04-04T12:05:00+00:00",
            "intent": "manual",
            "status": "pending",
            "created_at": "2026-04-04T11:50:00+00:00",
            "updated_at": "2026-04-04T11:50:00+00:00",
            "started_at": "2026-04-04T11:50:00+00:00",
            "completed_at": None,
            "current_stage": "等待调度",
            "active_edges": [],
            "nodes": [],
            "logs": [],
            "next_dispatch_at": "2099-04-04T12:05:00+00:00",
            "dispatch_context": {"state": "queued"},
            "warnings": [],
        },
        {
            "id": "run-monitor-failed",
            "workflow_id": "workflow-1",
            "workflow_name": "客户服务工作流",
            "task_id": "task-monitor-failed",
            "trigger": "internal:monitor.failed",
            "intent": "search",
            "status": "failed",
            "created_at": "2026-04-04T10:10:00+00:00",
            "updated_at": "2026-04-04T10:12:00+00:00",
            "started_at": "2026-04-04T10:10:00+00:00",
            "completed_at": "2026-04-04T10:12:00+00:00",
            "current_stage": "失败",
            "active_edges": [],
            "nodes": [],
            "logs": [],
            "dispatch_context": {"state": "dispatched", "executionAgentId": "3"},
            "warnings": ["执行链路失败"],
        },
    ]

    response = client.get("/api/workflows/workflow-1/monitor", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["workflowId"] == "workflow-1"
    assert body["workflow"]["id"] == "workflow-1"
    assert body["stats"]["total"] >= 4
    assert body["stats"]["completed"] >= 1
    assert body["stats"]["claimed"] + body["stats"]["running"] >= 1
    assert body["stats"]["scheduled"] >= 1
    assert body["stats"]["failed"] >= 1
    assert any(item["id"] == "run-monitor-claimed" for item in body["items"])
    scheduled_item = next(item for item in body["items"] if item["id"] == "run-monitor-scheduled")
    assert scheduled_item["monitor"]["triggerType"] == "schedule"
    assert scheduled_item["monitor"]["monitorState"] == "scheduled"
    assert scheduled_item["monitor"]["nextAction"] == "wait_for_schedule"
    assert any("运行已经失败" in alert for alert in body["alerts"])


def test_workflow_monitor_route_marks_retry_waiting_and_overdue_runs(auth_headers) -> None:
    store.workflow_runs[0:0] = [
        {
            "id": "run-monitor-overdue",
            "workflow_id": "workflow-1",
            "workflow_name": "客户服务工作流",
            "task_id": "task-monitor-overdue",
            "trigger": "message",
            "intent": "search",
            "status": "pending",
            "created_at": "2026-04-04T11:00:00+00:00",
            "updated_at": "2026-04-04T11:00:00+00:00",
            "started_at": "2026-04-04T11:00:00+00:00",
            "completed_at": None,
            "current_stage": "等待拉起",
            "active_edges": [],
            "nodes": [],
            "logs": [],
            "next_dispatch_at": "2026-04-04T11:00:30+00:00",
            "dispatch_context": {"state": "queued"},
            "warnings": [],
        },
        {
            "id": "run-monitor-retry",
            "workflow_id": "workflow-1",
            "workflow_name": "客户服务工作流",
            "task_id": "task-monitor-retry",
            "trigger": "webhook:/monitor/retry",
            "intent": "search",
            "status": "pending",
            "created_at": "2026-04-04T11:10:00+00:00",
            "updated_at": "2026-04-04T11:10:00+00:00",
            "started_at": "2026-04-04T11:10:00+00:00",
            "completed_at": None,
            "current_stage": "等待重试",
            "active_edges": [],
            "nodes": [],
            "logs": [],
            "next_dispatch_at": "2099-04-04T11:10:30+00:00",
            "dispatch_failure_count": 2,
            "last_dispatch_error": "transient dispatcher failure",
            "dispatch_context": {"state": "queued"},
            "warnings": ["调度推进失败，已延后 2.0s 重试"],
        },
    ]

    response = client.get(
        "/api/workflows/workflow-1/monitor",
        params={"unhealthyOnly": "true"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["stats"]["overdue"] >= 1
    assert body["stats"]["retryWaiting"] >= 1
    assert body["stats"]["unhealthy"] >= 2
    assert {item["id"] for item in body["items"]} >= {"run-monitor-overdue", "run-monitor-retry"}
    overdue_item = next(item for item in body["items"] if item["id"] == "run-monitor-overdue")
    retry_item = next(item for item in body["items"] if item["id"] == "run-monitor-retry")
    assert overdue_item["monitor"]["monitorState"] == "overdue"
    assert overdue_item["monitor"]["nextAction"] == "dispatch"
    assert retry_item["monitor"]["monitorState"] == "retry_waiting"
    assert retry_item["monitor"]["nextAction"] == "retry_dispatch"
    assert retry_item["monitor"]["lastDispatchError"] == "transient dispatcher failure"


def test_workflow_run_detail_exposes_claimed_and_running_monitor_governance_states(
    auth_headers,
) -> None:
    store.workflow_runs[0:0] = [
        {
            "id": "run-monitor-claimed-detail",
            "workflow_id": "workflow-1",
            "workflow_name": "客户服务工作流",
            "task_id": "task-monitor-claimed-detail",
            "trigger": "message",
            "intent": "search",
            "status": "pending",
            "created_at": "2026-04-04T11:40:00+00:00",
            "updated_at": "2026-04-04T11:40:10+00:00",
            "started_at": "2026-04-04T11:40:00+00:00",
            "completed_at": None,
            "current_stage": "等待 dispatcher 推进",
            "active_edges": [],
            "nodes": [],
            "logs": [],
            "dispatch_context": {
                "dispatchState": "queued",
                "routeDecision": {
                    "intent": "search",
                    "workflowId": "workflow-1",
                    "workflowName": "客户服务工作流",
                    "executionAgentId": "agent-claimed",
                    "executionAgent": "搜索 Agent",
                    "routeMessage": "已进入 dispatcher claim 阶段",
                },
            },
            "dispatcher_id": "dispatcher-claimed",
            "dispatch_claimed_at": "2026-04-04T11:40:10+00:00",
            "dispatch_lease_expires_at": "2099-04-04T11:41:10+00:00",
            "warnings": ["dispatcher 已持有 lease"],
        },
        {
            "id": "run-monitor-running-detail",
            "workflow_id": "workflow-1",
            "workflow_name": "客户服务工作流",
            "task_id": "task-monitor-running-detail",
            "trigger": "message",
            "intent": "search",
            "status": "running",
            "created_at": "2026-04-04T11:50:00+00:00",
            "updated_at": "2026-04-04T11:50:15+00:00",
            "started_at": "2026-04-04T11:50:00+00:00",
            "completed_at": None,
            "current_stage": "等待 worker 执行",
            "active_edges": [],
            "nodes": [],
            "logs": [],
            "dispatch_context": {
                "dispatchState": "executing",
                "routeDecision": {
                    "intent": "search",
                    "workflowId": "workflow-1",
                    "workflowName": "客户服务工作流",
                    "executionAgentId": "agent-running",
                    "executionAgent": "搜索 Agent",
                    "routeMessage": "worker 已准备执行",
                },
            },
            "warnings": ["worker 已入队"],
        },
    ]

    claimed_detail = client.get(
        "/api/workflows/runs/run-monitor-claimed-detail",
        headers=auth_headers,
    )
    assert claimed_detail.status_code == 200
    claimed_monitor = claimed_detail.json()["monitor"]
    assert claimed_monitor["dispatchState"] == "queued"
    assert claimed_monitor["monitorState"] == "claimed"
    assert claimed_monitor["nextAction"] == "await_dispatch"
    assert claimed_monitor["executionAgentId"] == "agent-claimed"
    assert claimed_monitor["warningCount"] == 1
    assert claimed_monitor["latestWarning"] == "dispatcher 已持有 lease"

    running_detail = client.get(
        "/api/workflows/runs/run-monitor-running-detail",
        headers=auth_headers,
    )
    assert running_detail.status_code == 200
    running_monitor = running_detail.json()["monitor"]
    assert running_monitor["dispatchState"] == "executing"
    assert running_monitor["monitorState"] == "running"
    assert running_monitor["nextAction"] == "await_worker"
    assert running_monitor["executionAgentId"] == "agent-running"
    assert running_monitor["warningCount"] == 1
    assert running_monitor["latestWarning"] == "worker 已入队"


def test_poll_scheduled_workflows_deduplicates_same_slot(monkeypatch) -> None:
    fixed_now = datetime(2026, 4, 4, 12, 0, 45, tzinfo=UTC)
    monkeypatch.setattr(
        workflow_execution_service,
        "_schedule_manual_auto_progress",
        lambda run_id: None,
    )

    store.workflows.insert(
        0,
        {
            "id": "workflow-schedule-dedupe",
            "name": "定时同步工作流",
            "description": "同一时间窗内不应重复创建 run",
            "version": "v1",
            "status": "active",
            "updated_at": "2026-04-04T11:30:00+00:00",
            "node_count": 2,
            "edge_count": 1,
            "trigger": {"type": "schedule", "cron": "0 * * * *"},
            "agent_bindings": ["3"],
            "nodes": [
                {"id": "1", "type": "trigger", "label": "定时触发", "x": 0, "y": 0},
                {"id": "2", "type": "agent", "label": "搜索 Agent", "agent_id": "3", "x": 120, "y": 0},
            ],
            "edges": [{"id": "e1-2", "source": "1", "target": "2"}],
        },
    )
    store.workflow_runs.insert(
        0,
        {
            "id": "run-schedule-existing",
            "workflow_id": "workflow-schedule-dedupe",
            "workflow_name": "定时同步工作流",
            "task_id": "task-schedule-existing",
            "trigger": "schedule:2026-04-04T12:00:00+00:00",
            "intent": "manual",
            "status": "pending",
            "created_at": "2026-04-04T12:00:05+00:00",
            "updated_at": "2026-04-04T12:00:05+00:00",
            "started_at": "2026-04-04T12:00:05+00:00",
            "completed_at": None,
            "next_dispatch_at": None,
            "dispatch_failure_count": 0,
            "last_dispatch_error": None,
            "current_stage": "等待执行策略",
            "active_edges": [],
            "nodes": [],
            "logs": [],
        },
    )

    summary = workflow_service.poll_scheduled_workflows(now=fixed_now)

    assert summary["triggered"] == 0
    assert summary["skipped_existing"] == 1
    assert len(
        [
            run
            for run in store.workflow_runs
            if run["workflow_id"] == "workflow-schedule-dedupe"
        ]
    ) == 1


def test_message_ingest_routes_by_trigger_channel_language_and_priority(auth_headers) -> None:
    create = client.post(
        "/api/workflows",
        json={
            "name": "Telegram 英文安全检索工作流",
            "description": "优先处理 Telegram 英文安全资料检索",
            "version": "v2.0",
            "status": "active",
            "trigger": {
                "type": "message",
                "keyword": "security, gateway, docs",
                "channels": ["telegram"],
                "preferredLanguage": "en",
                "priority": 240,
                "description": "面向 Telegram 英文安全查询",
            },
            "nodes": [
                {
                    "id": "1",
                    "type": "trigger",
                    "label": "消息触发",
                    "x": 60,
                    "y": 120,
                },
                {
                    "id": "2",
                    "type": "agent",
                    "label": "搜索 Agent",
                    "x": 280,
                    "y": 120,
                    "agentId": "3",
                },
            ],
            "edges": [
                {
                    "id": "e1-2",
                    "source": "1",
                    "target": "2",
                }
            ],
        },
        headers=auth_headers,
    )
    assert create.status_code == 200
    workflow_id = create.json()["workflow"]["id"]

    ingest = client.post(
        "/api/messages/ingest",
        json={
            "channel": "telegram",
            "platformUserId": "route-user-en",
            "chatId": "route-chat-en",
            "text": "please search the security gateway docs",
            "metadata": {"preferredLanguage": "en"},
        },
    )
    assert ingest.status_code == 200
    body = ingest.json()

    run_response = client.get(
        f"/api/workflows/runs/{body['runId']}",
        headers=auth_headers,
    )
    assert run_response.status_code == 200
    run_body = run_response.json()
    assert run_body["workflowId"] == workflow_id
    assert body["routeDecision"]["workflowId"] == workflow_id
    assert body["routeDecision"]["executionAgent"] == "搜索 Agent"
    assert body["routeDecision"]["selectedByMessageTrigger"] is True

    task_response = client.get(
        f"/api/tasks/{body['taskId']}/steps",
        headers=auth_headers,
    )
    assert task_response.status_code == 200
    route_step = task_response.json()["items"][3]
    assert route_step["title"] == "Master Bot 路由"
    assert "命中工作流: Telegram 英文安全检索工作流" in route_step["message"]
    assert "渠道=telegram" in route_step["message"]
    assert "语言=en" in route_step["message"]
    assert "执行代理: 搜索 Agent" in route_step["message"]


def test_message_ingest_skips_higher_priority_workflow_without_executable_agent(
    auth_headers,
    monkeypatch,
) -> None:
    blocked = client.post(
        "/api/workflows",
        json={
            "name": "高优先级不可执行检索工作流",
            "description": "关键词命中但没有 search 执行 Agent",
            "version": "v1.0",
            "status": "active",
            "trigger": {
                "type": "message",
                "keyword": "security, gateway, docs",
                "channels": ["telegram"],
                "preferredLanguage": "en",
                "priority": 300,
            },
            "nodes": [
                {
                    "id": "1",
                    "type": "trigger",
                    "label": "消息触发",
                    "x": 60,
                    "y": 120,
                },
                {
                    "id": "2",
                    "type": "agent",
                    "label": "写作 Agent",
                    "x": 280,
                    "y": 120,
                    "agentId": "4",
                },
            ],
            "edges": [
                {
                    "id": "e1-2",
                    "source": "1",
                    "target": "2",
                }
            ],
        },
        headers=auth_headers,
    )
    assert blocked.status_code == 200
    blocked_workflow_id = blocked.json()["workflow"]["id"]

    fallback = client.post(
        "/api/workflows",
        json={
            "name": "次优可执行检索工作流",
            "description": "当高优先级工作流不可执行时回退到这里",
            "version": "v1.0",
            "status": "active",
            "trigger": {
                "type": "message",
                "keyword": "security, gateway, docs",
                "channels": ["telegram"],
                "preferredLanguage": "en",
                "priority": 220,
            },
            "nodes": [
                {
                    "id": "1",
                    "type": "trigger",
                    "label": "消息触发",
                    "x": 60,
                    "y": 120,
                },
                {
                    "id": "2",
                    "type": "agent",
                    "label": "搜索 Agent",
                    "x": 280,
                    "y": 120,
                    "agentId": "3",
                },
            ],
            "edges": [
                {
                    "id": "e1-2",
                    "source": "1",
                    "target": "2",
                }
            ],
        },
        headers=auth_headers,
    )
    assert fallback.status_code == 200
    fallback_workflow_id = fallback.json()["workflow"]["id"]

    original_resolver = workflow_execution_service.resolve_workflow_execution_agent

    def fake_resolve_workflow_execution_agent(workflow: dict, intent: str | None) -> dict | None:
        if str(workflow.get("id") or "").strip() == blocked_workflow_id:
            return None
        return original_resolver(workflow, intent)

    monkeypatch.setattr(
        workflow_execution_service,
        "resolve_workflow_execution_agent",
        fake_resolve_workflow_execution_agent,
    )

    ingest = client.post(
        "/api/messages/ingest",
        json={
            "channel": "telegram",
            "platformUserId": "route-fallback-user",
            "chatId": "route-fallback-chat",
            "text": "please search the security gateway docs",
            "metadata": {"preferredLanguage": "en"},
        },
    )
    assert ingest.status_code == 200
    body = ingest.json()

    assert body["routeDecision"]["workflowId"] == fallback_workflow_id
    assert body["routeDecision"]["workflowId"] != blocked_workflow_id
    assert body["routeDecision"]["executionAgent"] == "搜索 Agent"
    assert "已跳过不可执行工作流: 高优先级不可执行检索工作流" in body["routeDecision"]["routeMessage"]

    task_response = client.get(
        f"/api/tasks/{body['taskId']}/steps",
        headers=auth_headers,
    )
    assert task_response.status_code == 200
    route_step = task_response.json()["items"][3]
    assert "命中工作流: 次优可执行检索工作流" in route_step["message"]
    assert "已跳过不可执行工作流: 高优先级不可执行检索工作流" in route_step["message"]


def test_message_ingest_execution_agent_id_is_used_by_agent_execution_service(
    auth_headers,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        workflow_execution_service,
        "_schedule_message_auto_progress",
        lambda run_id: None,
    )
    monkeypatch.setattr(
        workflow_execution_service,
        "_schedule_follow_up",
        lambda run_id: None,
    )
    monkeypatch.setattr(
        workflow_execution_service,
        "_schedule_retry_follow_up",
        lambda run_id: None,
    )
    monkeypatch.setattr(
        workflow_execution_service,
        "_cancel_scheduled_run",
        lambda run_id: None,
    )

    captured: dict[str, str] = {}

    def fake_execute_task(*, task: dict, run: dict, execution_agent: dict | None) -> dict:
        captured["task_id"] = str(task.get("id") or "")
        captured["run_id"] = str(run.get("id") or "")
        captured["agent_id"] = str((execution_agent or {}).get("id") or "")
        return {
            "kind": "search_report",
            "title": "Executor Search Result",
            "summary": "通过 AgentExecutionService 完成搜索执行",
            "content": "已命中正式搜索执行器边界。",
            "bullets": ["dispatch context 中的 executionAgentId 已参与真实执行。"],
            "references": [],
        }

    monkeypatch.setattr(agent_execution_service, "execute_task", fake_execute_task)

    ingest = client.post(
        "/api/messages/ingest",
        json={
            "channel": "telegram",
            "platformUserId": "executor-route-user",
            "chatId": "executor-route-chat",
            "text": "请帮我搜索执行器边界设计",
        },
    )
    assert ingest.status_code == 200
    ingest_body = ingest.json()
    run_id = ingest_body["runId"]
    task_id = ingest_body["taskId"]

    first_tick = client.post(f"/api/workflows/runs/{run_id}/tick", headers=auth_headers)
    assert first_tick.status_code == 200
    assert first_tick.json()["status"] == "running"

    second_tick = client.post(f"/api/workflows/runs/{run_id}/tick", headers=auth_headers)
    assert second_tick.status_code == 200
    assert second_tick.json()["status"] == "completed"

    assert captured == {
        "task_id": task_id,
        "run_id": run_id,
        "agent_id": ingest_body["routeDecision"]["executionAgentId"],
    }

    task_response = client.get(f"/api/tasks/{task_id}", headers=auth_headers)
    assert task_response.status_code == 200
    assert task_response.json()["result"]["title"] == "Executor Search Result"


def test_message_ingest_write_execution_agent_id_routes_to_write_executor(
    auth_headers,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        workflow_execution_service,
        "_schedule_message_auto_progress",
        lambda run_id: None,
    )
    monkeypatch.setattr(
        workflow_execution_service,
        "_schedule_follow_up",
        lambda run_id: None,
    )
    monkeypatch.setattr(
        workflow_execution_service,
        "_schedule_retry_follow_up",
        lambda run_id: None,
    )
    monkeypatch.setattr(
        workflow_execution_service,
        "_cancel_scheduled_run",
        lambda run_id: None,
    )

    captured: dict[str, str] = {}

    def fake_execute_write(*, task: dict, run: dict, execution_agent: dict | None) -> dict:
        captured["task_id"] = str(task.get("id") or "")
        captured["run_id"] = str(run.get("id") or "")
        captured["agent_id"] = str((execution_agent or {}).get("id") or "")
        return {
            "kind": "draft_message",
            "title": "Executor Write Result",
            "summary": "通过 write executor 完成写作执行",
            "content": "已命中正式写作执行器边界。",
            "bullets": ["dispatch context 中的 executionAgentId 已参与写作执行。"],
            "references": [],
        }

    monkeypatch.setattr(agent_execution_service, "_execute_write", fake_execute_write)
    monkeypatch.setattr(
        agent_execution_service,
        "_execute_search",
        lambda **kwargs: pytest.fail("write intent should not hit search executor"),
    )
    monkeypatch.setattr(
        agent_execution_service,
        "_execute_help",
        lambda **kwargs: pytest.fail("write intent should not hit help executor"),
    )
    monkeypatch.setattr(
        agent_execution_service,
        "_execute_default",
        lambda **kwargs: pytest.fail("write intent should not hit default executor"),
    )

    ingest = client.post(
        "/api/messages/ingest",
        json={
            "channel": "telegram",
            "platformUserId": "executor-write-user",
            "chatId": "executor-write-chat",
            "text": "请帮我写一段执行器边界发布说明",
        },
    )
    assert ingest.status_code == 200
    ingest_body = ingest.json()
    run_id = ingest_body["runId"]
    task_id = ingest_body["taskId"]

    first_tick = client.post(f"/api/workflows/runs/{run_id}/tick", headers=auth_headers)
    assert first_tick.status_code == 200
    assert first_tick.json()["status"] == "running"

    second_tick = client.post(f"/api/workflows/runs/{run_id}/tick", headers=auth_headers)
    assert second_tick.status_code == 200
    assert second_tick.json()["status"] == "completed"

    assert captured == {
        "task_id": task_id,
        "run_id": run_id,
        "agent_id": ingest_body["routeDecision"]["executionAgentId"],
    }

    task_response = client.get(f"/api/tasks/{task_id}", headers=auth_headers)
    assert task_response.status_code == 200
    assert task_response.json()["result"]["title"] == "Executor Write Result"


def test_message_ingest_help_execution_agent_id_routes_to_help_executor(
    auth_headers,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        workflow_execution_service,
        "_schedule_message_auto_progress",
        lambda run_id: None,
    )
    monkeypatch.setattr(
        workflow_execution_service,
        "_schedule_follow_up",
        lambda run_id: None,
    )
    monkeypatch.setattr(
        workflow_execution_service,
        "_schedule_retry_follow_up",
        lambda run_id: None,
    )
    monkeypatch.setattr(
        workflow_execution_service,
        "_cancel_scheduled_run",
        lambda run_id: None,
    )

    captured: dict[str, str] = {}

    def fake_execute_help(*, task: dict, run: dict, execution_agent: dict | None) -> dict:
        captured["task_id"] = str(task.get("id") or "")
        captured["run_id"] = str(run.get("id") or "")
        captured["agent_id"] = str((execution_agent or {}).get("id") or "")
        return {
            "kind": "help_note",
            "title": "Executor Help Result",
            "summary": "通过 help executor 完成帮助执行",
            "content": "已命中正式帮助执行器边界。",
            "bullets": ["即使 execution agent 为写作 Agent，help intent 仍走帮助执行分支。"],
            "references": [],
        }

    monkeypatch.setattr(agent_execution_service, "_execute_help", fake_execute_help)
    monkeypatch.setattr(
        agent_execution_service,
        "_execute_search",
        lambda **kwargs: pytest.fail("help intent should not hit search executor"),
    )
    monkeypatch.setattr(
        agent_execution_service,
        "_execute_write",
        lambda **kwargs: pytest.fail("help intent should not hit write executor"),
    )
    monkeypatch.setattr(
        agent_execution_service,
        "_execute_default",
        lambda **kwargs: pytest.fail("help intent should not hit default executor"),
    )

    ingest = client.post(
        "/api/messages/ingest",
        json={
            "channel": "telegram",
            "platformUserId": "executor-help-user",
            "chatId": "executor-help-chat",
            "text": "这个执行器边界要怎么接入？",
        },
    )
    assert ingest.status_code == 200
    ingest_body = ingest.json()
    run_id = ingest_body["runId"]
    task_id = ingest_body["taskId"]

    first_tick = client.post(f"/api/workflows/runs/{run_id}/tick", headers=auth_headers)
    assert first_tick.status_code == 200
    assert first_tick.json()["status"] == "running"

    second_tick = client.post(f"/api/workflows/runs/{run_id}/tick", headers=auth_headers)
    assert second_tick.status_code == 200
    assert second_tick.json()["status"] == "completed"

    assert captured == {
        "task_id": task_id,
        "run_id": run_id,
        "agent_id": ingest_body["routeDecision"]["executionAgentId"],
    }

    task_response = client.get(f"/api/tasks/{task_id}", headers=auth_headers)
    assert task_response.status_code == 200
    assert task_response.json()["result"]["title"] == "Executor Help Result"


def test_workflow_realtime_websocket_pushes_run_updates(
    auth_headers,
    auth_token,
) -> None:
    with client.websocket_connect(
        f"/api/workflows/workflow-1/realtime?access_token={auth_token}"
    ) as websocket:
        snapshot = websocket.receive_json()
        assert snapshot["type"] == "workflow.runs.snapshot"
        assert snapshot["workflowId"] == "workflow-1"

        run_response = client.post(
            "/api/workflows/workflow-1/run",
            headers=auth_headers,
        )
        assert run_response.status_code == 200
        run_id = run_response.json()["runId"]

        created_event = websocket.receive_json()
        assert created_event["type"] == "workflow_run.created"
        assert created_event["workflowId"] == "workflow-1"
        assert created_event["run"]["id"] == run_id

        updated_event = None
        for _ in range(4):
            event = websocket.receive_json()
            if event["type"] == "workflow_run.updated" and event["run"]["id"] == run_id:
                updated_event = event
                break

        assert updated_event is not None
        assert updated_event["run"]["status"] in {"running", "completed"}
