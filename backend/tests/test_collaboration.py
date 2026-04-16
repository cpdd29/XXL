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


def test_collaboration_overview_exposes_manager_packet(auth_headers) -> None:
    created_at = store.now_string()
    task_id = "task-collaboration-manager-packet"
    store.tasks.append(
        {
            "id": task_id,
            "workflow_id": "workflow-1",
            "title": "协作经理分发测试",
            "description": "验证协作页会话摘要显示主脑项目经理分发信息",
            "status": "running",
            "priority": "medium",
            "created_at": created_at,
            "completed_at": None,
            "agent": "搜索 Agent",
            "tokens": 21,
            "manager_packet": {
                "manager_role": "reception_project_manager",
                "manager_action": "handoff_to_execution",
                "next_owner": "搜索 Agent",
                "delivery_mode": "structured_result",
            },
            "route_decision": {
                "intent": "search",
                "workflow_id": "workflow-1",
                "workflow_name": "客户服务工作流",
                "execution_agent": "搜索 Agent",
            },
            "result": None,
        }
    )
    store.task_steps[task_id] = []

    response = client.get("/api/collaboration/overview", params={"taskId": task_id}, headers=auth_headers)

    assert response.status_code == 200
    session = response.json()["session"]
    assert session["managerPacket"]["managerRole"] == "reception_project_manager"
    assert session["managerPacket"]["nextOwner"]


def test_collaboration_overview_exposes_memory_and_state_machine(auth_headers) -> None:
    ingest = client.post(
        "/api/messages/ingest",
        json={
            "channel": "telegram",
            "platformUserId": "collaboration-memory-user",
            "chatId": "collaboration-memory-chat",
            "text": "请帮我总结一下当前项目里的安全中心设计",
        },
    )
    assert ingest.status_code == 200

    response = client.get(
        "/api/collaboration/overview",
        params={"taskId": ingest.json()["taskId"]},
        headers=auth_headers,
    )

    assert response.status_code == 200
    session = response.json()["session"]
    assert session["memoryInjectionSummary"]["boundary"] == "long_term_read_only"
    assert session["stateMachine"]["version"] == "brain_fact_layer_v1"
    assert isinstance(session["contextPatchAudit"], list)


def test_collaboration_overview_exposes_execution_plan_snapshot_from_run(auth_headers) -> None:
    created_at = store.now_string()
    task_id = "task-collaboration-plan"
    run_id = "run-collaboration-plan"
    store.tasks.append(
        {
            "id": task_id,
            "workflow_run_id": run_id,
            "workflow_id": "workflow-1",
            "title": "协作执行计划测试",
            "description": "验证协作页显示执行计划快照",
            "status": "running",
            "priority": "medium",
            "created_at": created_at,
            "completed_at": None,
            "agent": "Master Bot Planner",
            "tokens": 32,
            "route_decision": {
                "intent": "help",
                "workflow_id": "workflow-1",
                "workflow_name": "客户服务工作流",
                "execution_agent": "Master Bot Planner",
                "execution_plan": {
                    "plan_type": "multi_agent",
                    "coordination_mode": "parallel",
                    "planner": "master_bot",
                    "aggregator": "master_bot",
                    "fan_out": {
                        "mode": "parallel",
                        "branch_count": 2,
                    },
                    "fan_in": {
                        "strategy": "merge_summary",
                        "aggregator": "master_bot",
                    },
                    "merge_strategy": "append_bullets_and_references",
                    "summary": "搜索 Agent + 写作 Agent",
                    "steps": [
                        {
                            "id": "research",
                            "branch_id": "branch-research",
                            "intent": "search",
                            "role": "grounding",
                            "execution_agent": "搜索 Agent",
                            "agent_type": "search",
                        },
                        {
                            "id": "synthesis",
                            "intent": "write",
                            "role": "final_response",
                            "execution_agent": "写作 Agent",
                            "agent_type": "write",
                        },
                    ],
                },
                "fallback_policy": {
                    "mode": "planner_recovery",
                    "target": "master_bot_planner",
                    "summary": "Planner can retry or degrade to single-agent execution",
                },
                "route_rationale": {
                    "routing_strategy": "dynamic_multi_agent_dispatch",
                    "route_reason_summary": "检测到复合任务，启用动态编排",
                    "candidate_count": 0,
                    "skipped_count": 0,
                },
            },
            "manager_packet": {
                "next_owner": "Master Bot Planner",
            },
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
            "intent": "help",
            "status": "running",
            "created_at": created_at,
            "updated_at": created_at,
            "started_at": created_at,
            "completed_at": None,
            "current_stage": "规划执行",
            "active_edges": [],
            "nodes": [],
            "logs": [],
            "dispatch_context": {
                "aggregation_contract": {
                    "mode": "parallel",
                    "successful_agents": 1,
                    "failed_agents": 0,
                    "cancelled_agents": 1,
                    "branch_results": [
                        {
                            "step_id": "research",
                            "branch_id": "branch-research",
                            "intent": "search",
                            "agent": "搜索 Agent",
                            "status": "completed",
                            "score": 7,
                        },
                        {
                            "step_id": "synthesis",
                            "branch_id": "branch-write",
                            "intent": "write",
                            "agent": "写作 Agent",
                            "status": "cancelled",
                            "score": 0,
                        },
                    ],
                },
                "aggregation_notes": {
                    "selected_branch_id": "branch-research",
                    "selected_agent": "搜索 Agent",
                },
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
    assert session["executionPlan"]["version"] == "execution_plan.v1"
    assert session["executionPlan"]["planType"] == "multi_agent"
    assert session["executionPlan"]["coordinationMode"] == "parallel"
    assert session["executionPlan"]["stepCount"] == 2
    assert session["executionPlan"]["fanOut"]["branch_count"] == 2
    assert session["executionPlan"]["fanIn"]["strategy"] == "merge_summary"
    assert session["executionPlan"]["mergeStrategy"] == "append_bullets_and_references"
    assert session["executionPlan"]["steps"][0]["branchId"] == "branch-research"
    assert session["executionPlan"]["steps"][0]["executionAgent"] == "搜索 Agent"
    assert session["executionPlan"]["steps"][1]["executionAgent"] == "写作 Agent"
    assert session["executionPlan"]["selectedBranchId"] == "branch-research"
    assert session["executionPlan"]["selectedAgent"] == "搜索 Agent"
    assert session["executionPlan"]["successfulAgents"] == 1
    assert session["executionPlan"]["cancelledAgents"] == 1
    assert session["executionPlan"]["branchResults"][0]["status"] == "completed"
    assert session["executionPlan"]["fallback"]["mode"] == "planner_recovery"
    assert session["executionPlan"]["routeRationale"]["routeReasonSummary"] == "检测到复合任务，启用动态编排"


def test_collaboration_overview_exposes_task_execution_plan_without_run(auth_headers) -> None:
    created_at = store.now_string()
    task_id = "task-collaboration-task-plan"
    store.tasks.append(
        {
            "id": task_id,
            "workflow_id": "workflow-1",
            "title": "协作执行计划任务快照测试",
            "description": "验证无 workflow run 时展示 task execution_plan",
            "status": "running",
            "priority": "medium",
            "created_at": created_at,
            "completed_at": None,
            "agent": "Master Bot Planner",
            "tokens": 12,
            "execution_plan": {
                "version": "execution_plan.v1",
                "plan_type": "single_agent",
                "coordination_mode": "serial",
                "step_count": 1,
                "steps": [
                    {
                        "index": 1,
                        "id": "step-write",
                        "intent": "write",
                        "execution_agent": "写作 Agent",
                    }
                ],
            },
            "result": None,
        }
    )

    response = client.get(
        "/api/collaboration/overview",
        params={"taskId": task_id},
        headers=auth_headers,
    )

    assert response.status_code == 200
    session = response.json()["session"]
    assert session["workflowRunId"] is None
    assert session["executionPlan"]["version"] == "execution_plan.v1"
    assert session["executionPlan"]["planType"] == "single_agent"
    assert session["executionPlan"]["coordinationMode"] == "serial"
    assert session["executionPlan"]["stepCount"] == 1
    assert session["executionPlan"]["steps"][0]["executionAgent"] == "写作 Agent"


def test_collaboration_overview_exposes_fallback_history(auth_headers) -> None:
    created_at = store.now_string()
    task_id = "task-collaboration-fallback-history"
    run_id = "run-collaboration-fallback-history"
    store.tasks.append(
        {
            "id": task_id,
            "workflow_run_id": run_id,
            "workflow_id": "workflow-1",
            "title": "协作回退历史测试",
            "description": "验证协作页会话显示 fallback history",
            "status": "failed",
            "priority": "high",
            "created_at": created_at,
            "completed_at": created_at,
            "agent": "搜索 Agent",
            "tokens": 12,
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
                "state": "execution_timeout",
                "fallback_history": [
                    {
                        "id": "fallback-1",
                        "timestamp": created_at,
                        "state": "execution_timeout",
                        "failure_stage": "execution",
                        "reason": "execution_timeout",
                        "message": "Agent Worker 执行超时",
                        "policy_mode": "planner_recovery",
                        "policy_target": "master_bot_planner",
                        "resolved_action": "planner_retry",
                    }
                ],
            },
        },
    )

    response = client.get(
        "/api/collaboration/overview",
        params={"taskId": task_id},
        headers=auth_headers,
    )

    assert response.status_code == 200
    history = response.json()["session"]["fallbackHistory"]
    assert history[0]["reason"] == "execution_timeout"
    assert history[0]["policyMode"] == "planner_recovery"
    assert history[0]["resolvedAction"] == "planner_retry"
