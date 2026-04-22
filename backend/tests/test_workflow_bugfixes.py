from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.main import app
from app.services.agent_execution_service import agent_execution_service
from app.services.mandatory_agent_registry_service import ensure_mandatory_agents_registered
from app.services.mandatory_workflow_registry_service import (
    CONVERSATION_AGENT_PIPELINE_WORKFLOW_ID,
    ensure_mandatory_workflows_registered,
)
from app.services.store import store
from app.services import workflow_execution_service


client = TestClient(app)


def wait_for_run_status(
    run_id: str,
    auth_headers: dict[str, str],
    expected_status: str,
    timeout: float = 8.0,
) -> dict:
    deadline = time.time() + timeout
    last_body: dict | None = None

    while time.time() < deadline:
        response = client.get(f"/api/workflows/runs/{run_id}", headers=auth_headers)
        assert response.status_code == 200
        last_body = response.json()
        if last_body["status"] == expected_status:
            return last_body
        time.sleep(0.1)

    raise AssertionError(f"Run {run_id} did not reach {expected_status}: {last_body}")


def test_run_detail_prefers_terminal_stage_and_selected_edges_over_stale_running_state(
    auth_headers,
) -> None:
    workflow_id = "workflow-bugfix-stage"
    run_id = "run-bugfix-stage"
    task_id = "task-bugfix-stage"
    now = "2026-04-22T10:00:00+00:00"

    store.workflows.insert(
        0,
        {
            "id": workflow_id,
            "name": "状态收口工作流",
            "description": "验证终态优先级和真实选边",
            "version": "v1.0",
            "status": "active",
            "updated_at": now,
            "node_count": 3,
            "edge_count": 2,
            "trigger": {"type": "manual"},
            "agent_bindings": ["3"],
            "nodes": [
                {"id": "1", "type": "trigger", "label": "开始", "x": 0, "y": 0},
                {"id": "2", "type": "agent", "label": "处理中", "x": 160, "y": 0, "agent_id": "3"},
                {"id": "3", "type": "output", "label": "输出", "x": 320, "y": 0},
            ],
            "edges": [
                {"id": "e1-2", "source": "1", "target": "2"},
                {"id": "e2-3", "source": "2", "target": "3"},
            ],
        },
    )
    store.tasks.append(
        {
            "id": task_id,
            "title": "状态收口任务",
            "description": "验证完成态不被 running 节点覆盖",
            "status": "completed",
            "priority": "medium",
            "created_at": now,
            "completed_at": now,
            "agent": "输出",
            "tokens": 12,
            "duration": "自动完成",
            "result": {
                "kind": "chat_reply",
                "title": "已完成",
                "summary": "任务已完成",
                "content": "任务已完成",
                "text": "任务已完成",
                "bullets": [],
                "references": [],
            },
            "workflow_id": workflow_id,
            "workflow_run_id": run_id,
        }
    )
    store.task_steps[task_id] = [
        {
            "id": f"{task_id}-1",
            "title": "开始",
            "status": "completed",
            "agent": "Workflow Engine",
            "started_at": now,
            "finished_at": now,
            "message": "已进入图执行",
            "tokens": 0,
            "metadata": {"node_id": "1"},
        },
        {
            "id": f"{task_id}-2",
            "title": "处理中",
            "status": "running",
            "agent": "搜索 Agent",
            "started_at": now,
            "finished_at": None,
            "message": "旧的运行标记仍残留",
            "tokens": 8,
            "metadata": {"node_id": "2"},
        },
        {
            "id": f"{task_id}-3",
            "title": "输出",
            "status": "completed",
            "agent": "输出Agent",
            "started_at": now,
            "finished_at": now,
            "message": "结果已统一输出",
            "tokens": 4,
            "metadata": {"node_id": "3"},
        },
    ]
    store.workflow_runs.insert(
        0,
        {
            "id": run_id,
            "workflow_id": workflow_id,
            "workflow_name": "状态收口工作流",
            "task_id": task_id,
            "trigger": "manual",
            "intent": "manual",
            "status": "completed",
            "created_at": now,
            "updated_at": now,
            "started_at": now,
            "completed_at": now,
            "current_stage": "处理中",
            "active_edges": [],
            "nodes": [],
            "logs": [],
            "dispatch_context": {
                "type": "manual_dispatch",
                "state": "completed",
                "queued_at": now,
                "updated_at": now,
                "execution_engine": "graph_v2",
                "graph_state": {
                    "version": "workflow_graph.v2",
                    "run_id": run_id,
                    "workflow_id": workflow_id,
                    "started_at": now,
                    "current_node_id": "2",
                    "completed_node_ids": ["1", "2", "3"],
                    "selected_edge_ids": ["e1-2", "e2-3"],
                    "execution_order": ["1", "2", "3"],
                    "node_states": {
                        "2": {
                            "id": "2",
                            "type": "agent",
                            "label": "处理中",
                            "status": "running",
                            "message": "旧的运行标记仍残留",
                            "tokens": 8,
                            "started_at": now,
                            "finished_at": None,
                            "result": None,
                            "attempt": 1,
                            "execution_instance_key": f"{run_id}:2:1",
                        },
                        "3": {
                            "id": "3",
                            "type": "output",
                            "label": "输出",
                            "status": "completed",
                            "message": "结果已统一输出",
                            "tokens": 4,
                            "started_at": now,
                            "finished_at": now,
                            "result": {"summary": "任务已完成"},
                            "attempt": 1,
                            "execution_instance_key": f"{run_id}:3:1",
                        },
                    },
                    "node_results": {},
                },
            },
            "warnings": [],
        },
    )

    response = client.get(f"/api/workflows/runs/{run_id}", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["currentStage"] == "执行完成"
    assert body["runtimeStage"] is None
    assert body["finalStage"] == "执行完成"
    assert body["lastCompletedNode"] == "输出"
    assert body["lastCompletedNodeId"] == "3"
    assert body["activeEdges"] == ["e1-2", "e2-3"]
    assert all(node["status"] != "running" for node in body["nodes"])


def test_sub_workflow_child_run_is_not_auto_scheduled_by_parent_workflow_node(
    auth_headers,
    monkeypatch,
) -> None:
    scheduled_run_ids: list[str] = []
    original_schedule_manual_auto_progress = workflow_execution_service._schedule_manual_auto_progress

    def record_schedule(run_id: str) -> None:
        scheduled_run_ids.append(run_id)
        original_schedule_manual_auto_progress(run_id)

    monkeypatch.setattr(workflow_execution_service, "_schedule_manual_auto_progress", record_schedule)
    monkeypatch.setattr(
        agent_execution_service,
        "execute_task",
        lambda *, task, run, execution_agent=None: {
            "kind": "chat_reply",
            "title": "子流程结果",
            "summary": f"已完成 {task['title']}",
            "content": "子流程已经完成。",
            "text": "子流程已经完成。",
            "bullets": [],
            "references": [],
        },
    )

    child_create = client.post(
        "/api/workflows",
        json={
            "name": "Bugfix 子工作流",
            "description": "用于验证 parent node 不会重复调度 child run",
            "version": "v1.0",
            "status": "active",
            "trigger": {"type": "manual", "description": "父流程触发"},
            "nodes": [
                {"id": "1", "type": "trigger", "label": "开始", "x": 40, "y": 60},
                {"id": "2", "type": "agent", "label": "搜索 Agent", "x": 260, "y": 60, "agentId": "3"},
            ],
            "edges": [{"id": "e1-2", "source": "1", "target": "2"}],
        },
        headers=auth_headers,
    )
    assert child_create.status_code == 200
    child_workflow_id = child_create.json()["workflow"]["id"]

    parent_create = client.post(
        "/api/workflows",
        json={
            "name": "Bugfix 父工作流",
            "description": "验证子工作流不自动调度",
            "version": "v1.0",
            "status": "active",
            "trigger": {"type": "manual", "description": "手动触发"},
            "nodes": [
                {"id": "1", "type": "trigger", "label": "开始", "x": 40, "y": 60},
                {"id": "2", "type": "workflow", "label": "子工作流节点", "x": 260, "y": 60, "workflowId": child_workflow_id},
            ],
            "edges": [{"id": "e1-2", "source": "1", "target": "2"}],
        },
        headers=auth_headers,
    )
    assert parent_create.status_code == 200
    parent_workflow_id = parent_create.json()["workflow"]["id"]

    run_response = client.post(f"/api/workflows/{parent_workflow_id}/run", headers=auth_headers)
    assert run_response.status_code == 200
    parent_run = wait_for_run_status(run_response.json()["runId"], auth_headers, "completed")

    child_runs = [
        run
        for run in store.workflow_runs
        if run["workflow_id"] == child_workflow_id and run["id"] != parent_run["id"]
    ]
    assert len(child_runs) == 1
    assert child_runs[0]["id"] not in scheduled_run_ids


def test_sub_workflow_return_payload_drives_visible_parent_condition_branch(
    auth_headers,
    monkeypatch,
) -> None:
    ensure_mandatory_agents_registered()
    ensure_mandatory_workflows_registered()

    parent_workflow_id = "workflow-bugfix-return-branch"
    store.workflows.insert(
        0,
        {
            "id": parent_workflow_id,
            "name": "回传分支验证工作流",
            "description": "验证子工作流输出事实会驱动父流程可视化条件分支",
            "version": "v1.0",
            "status": "active",
            "updated_at": "2026-04-22T11:00:00+00:00",
            "node_count": 5,
            "edge_count": 5,
            "trigger": {"type": "manual"},
            "agent_bindings": ["3"],
            "nodes": [
                {"id": "1", "type": "trigger", "label": "开始", "x": 0, "y": 0},
                {
                    "id": "2",
                    "type": "workflow",
                    "label": "对话子流程",
                    "x": 220,
                    "y": 0,
                    "workflow_id": CONVERSATION_AGENT_PIPELINE_WORKFLOW_ID,
                },
                    {
                        "id": "3",
                        "type": "condition",
                        "label": "判断回传分支",
                        "x": 480,
                        "y": 0,
                        "config": {"expression": "handoff_target_general_assistant"},
                    },
                {"id": "4", "type": "agent", "label": "命中需求分发", "x": 760, "y": -80, "agent_id": "3"},
                {"id": "5", "type": "agent", "label": "默认分支", "x": 760, "y": 80, "agent_id": "3"},
            ],
            "edges": [
                {"id": "e1-2", "source": "1", "target": "2"},
                {"id": "e2-3", "source": "2", "target": "3"},
                {"id": "e3-4", "source": "3", "source_handle": "true", "target": "4"},
                {"id": "e3-5", "source": "3", "source_handle": "false", "target": "5"},
            ],
        },
    )

    def fake_execute_task(*, task, run, execution_agent=None):
        del task, execution_agent
        current_node_label = str(
            (run.get("dispatch_context") or {}).get("current_node_label")
            or (run.get("dispatch_context") or {}).get("currentNodeLabel")
            or ""
        )
        if current_node_label in {"下发任务类", "确认客户需求"}:
            return {
                "kind": "chat_reply",
                "title": current_node_label,
                "summary": current_node_label,
                "content": current_node_label,
                "text": current_node_label,
                "bullets": [],
                "references": [],
            }
        if current_node_label == "命中需求分发":
            return {
                "kind": "chat_reply",
                "title": "需求分发分支",
                "summary": "命中需求分发分支",
                "content": "父流程按可视化条件进入需求分发分支。",
                "text": "父流程按可视化条件进入需求分发分支。",
                "bullets": [],
                "references": [],
            }
        if current_node_label == "默认分支":
            return {
                "kind": "chat_reply",
                "title": "默认分支",
                "summary": "命中默认分支",
                "content": "这里不应该被命中。",
                "text": "这里不应该被命中。",
                "bullets": [],
                "references": [],
            }
        return {
            "kind": "chat_reply",
            "title": "默认回复",
            "summary": "默认回复",
            "content": "默认回复",
            "text": "默认回复",
            "bullets": [],
            "references": [],
        }

    monkeypatch.setattr(agent_execution_service, "execute_task", fake_execute_task)

    bundle = workflow_execution_service.create_manual_workflow_run(
        parent_workflow_id,
        task_title="回传分支验证任务",
        dispatch_context={
            "execution_engine": "graph_v2",
            "request_context": {
                "channel": "telegram",
                "platform_user_id": "workflow-bugfix-branch-user",
                "chat_id": "workflow-bugfix-branch-chat",
            },
            "route_decision": {},
        },
        eager_start=False,
        auto_schedule=False,
    )
    parent_run_id = bundle["run"]["id"]

    latest_run = bundle["run"]
    for _ in range(12):
        if latest_run["status"] == "completed":
            break
        latest_run = workflow_execution_service.tick_workflow_run(parent_run_id, auto_schedule=False)

    body = wait_for_run_status(parent_run_id, auth_headers, "completed")
    assert body["dispatchContext"]["internalEventPayload"]["inputSource"] == "final_result"
    assert body["dispatchContext"]["internalEventPayload"]["handoffTarget"] == "general_assistant"
    assert body["dispatchContext"]["workflowReturn"]["handoffTarget"] == "general_assistant"
    assert body["dispatchContext"]["workflowReturn"]["conversationStage"] == "query_confirmed"
    graph_state = body["dispatchContext"].get("graphState") or body["dispatchContext"].get("graph_state") or {}
    execution_order = graph_state.get("executionOrder") or graph_state.get("execution_order")
    assert execution_order == ["1", "2", "3", "4"]
    assert [node["status"] for node in body["nodes"]] == ["completed", "completed", "completed", "completed", "idle"]

    task_response = client.get(f"/api/tasks/{body['taskId']}", headers=auth_headers)
    assert task_response.status_code == 200
    task_result = task_response.json()["result"]
    assert task_result["summary"] == "命中需求分发分支"


def test_visual_workflow_with_custom_id_defaults_to_graph_v2_execution() -> None:
    workflow_id = "workflow-bugfix-custom-graph-v2"
    now = "2026-04-22T12:00:00+00:00"

    store.workflows.insert(
        0,
        {
            "id": workflow_id,
            "name": "自定义画布工作流",
            "description": "验证非内置 ID 的画布工作流也会按图执行",
            "version": "v1.0",
            "status": "active",
            "updated_at": now,
            "node_count": 3,
            "edge_count": 2,
            "trigger": {"type": "manual"},
            "agent_bindings": [],
            "nodes": [
                {"id": "1", "type": "trigger", "label": "开始", "x": 0, "y": 0},
                {"id": "2", "type": "transform", "label": "处理中", "x": 220, "y": 0},
                {"id": "3", "type": "output", "label": "输出", "x": 440, "y": 0},
            ],
            "edges": [
                {"id": "e1-2", "source": "1", "target": "2"},
                {"id": "e2-3", "source": "2", "target": "3"},
            ],
        },
    )

    bundle = workflow_execution_service.create_manual_workflow_run(
        workflow_id,
        task_title="自定义画布执行任务",
        eager_start=False,
        auto_schedule=False,
    )
    run_id = bundle["run"]["id"]

    latest_run = bundle["run"]
    for _ in range(8):
        if latest_run["status"] == "completed":
            break
        latest_run = workflow_execution_service.tick_workflow_run(run_id, auto_schedule=False)

    assert latest_run["status"] == "completed"
    dispatch_context = latest_run.get("dispatch_context") or {}
    assert dispatch_context.get("execution_engine") == "graph_v2"

    graph_state = dispatch_context.get("graph_state") or dispatch_context.get("graphState") or {}
    execution_order = graph_state.get("execution_order") or graph_state.get("executionOrder")
    assert execution_order == ["1", "2", "3"]

    task = next(item for item in store.tasks if item["id"] == latest_run["task_id"])
    assert task["status"] == "completed"
    assert task["result"]["kind"] == "help_note"
