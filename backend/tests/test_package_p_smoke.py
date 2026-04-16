from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services.external_agent_registry_service import external_agent_registry_service
from app.services.external_skill_registry_service import external_skill_registry_service
from app.services.store import store


client = TestClient(app)


def test_external_capability_governance_rollout_and_rollback_smoke(auth_headers) -> None:
    external_agent_registry_service.register_agent(
        {
            "id": "smoke-agent-v1",
            "name": "Smoke Agent",
            "agent_family": "smoke_agent",
            "type": "search",
            "version": "1.0.0",
            "release_channel": "stable",
            "default_version": True,
            "compatibility": ["brain-core-v1"],
            "capabilities": ["web_search"],
            "base_url": "https://agents.example.com",
        }
    )
    external_agent_registry_service.register_agent(
        {
            "id": "smoke-agent-v2",
            "name": "Smoke Agent",
            "agent_family": "smoke_agent",
            "type": "search",
            "version": "2.0.0",
            "release_channel": "canary",
            "compatibility": ["brain-core-v1"],
            "capabilities": ["web_search"],
            "base_url": "https://agents.example.com",
        }
    )
    external_skill_registry_service.register_skill(
        {
            "id": "smoke-skill-v1",
            "name": "Smoke Skill",
            "skill_family": "smoke_skill",
            "description": "smoke",
            "version": "1.0.0",
            "release_channel": "stable",
            "default_version": True,
            "compatibility": ["brain-core-v1"],
            "capabilities": ["web_search"],
            "base_url": "https://skills.example.com",
            "invoke_path": "/invoke",
        }
    )
    external_skill_registry_service.register_skill(
        {
            "id": "smoke-skill-v2",
            "name": "Smoke Skill",
            "skill_family": "smoke_skill",
            "description": "smoke",
            "version": "2.0.0",
            "release_channel": "canary",
            "compatibility": ["brain-core-v1"],
            "capabilities": ["web_search"],
            "base_url": "https://skills.example.com",
            "invoke_path": "/invoke",
        }
    )

    set_agent_rollout = client.post(
        "/api/external-connections/agents/smoke-agent-v2/rollout-policy",
        json={"rolloutPolicy": {"canaryPercent": 20, "routeKey": "tenant"}},
        headers=auth_headers,
    )
    set_agent_rollback = client.post(
        "/api/external-connections/agents/smoke-agent-v2/rollback",
        json={"rollbackPolicy": {"active": True, "targetVersionId": "smoke-agent-v1"}},
        headers=auth_headers,
    )
    set_skill_rollout = client.post(
        "/api/external-connections/skills/smoke-skill-v2/rollout-policy",
        json={"rolloutPolicy": {"canaryPercent": 10, "routeKey": "chat"}},
        headers=auth_headers,
    )
    set_skill_rollback = client.post(
        "/api/external-connections/skills/smoke-skill-v2/rollback",
        json={"rollbackPolicy": {"active": True, "targetVersionId": "smoke-skill-v1"}},
        headers=auth_headers,
    )
    governance = client.get("/api/external-connections/governance", headers=auth_headers)
    list_agent_versions = client.get(
        "/api/external-connections/agents/families/smoke_agent/versions",
        headers=auth_headers,
    )
    list_skill_versions = client.get(
        "/api/external-connections/skills/families/smoke_skill/versions",
        headers=auth_headers,
    )

    assert set_agent_rollout.status_code == 200
    assert set_agent_rollback.status_code == 200
    assert set_skill_rollout.status_code == 200
    assert set_skill_rollback.status_code == 200
    assert governance.status_code == 200
    assert list_agent_versions.status_code == 200
    assert list_skill_versions.status_code == 200

    payload = governance.json()
    agent_family = next(
        item
        for item in payload["items"]
        if item["capabilityType"] == "agent" and item["family"] == "smoke_agent"
    )
    skill_family = next(
        item
        for item in payload["items"]
        if item["capabilityType"] == "skill" and item["family"] == "smoke_skill"
    )
    agent_v2 = next(item for item in list_agent_versions.json()["items"] if item["id"] == "smoke-agent-v2")
    skill_v2 = next(item for item in list_skill_versions.json()["items"] if item["id"] == "smoke-skill-v2")
    assert agent_family["currentVersion"] == "1.0.0"
    assert skill_family["currentVersion"] == "1.0.0"
    assert agent_v2["rolloutPolicy"]["canaryPercent"] == 20
    assert agent_v2["rollbackPolicy"]["active"] is True
    assert skill_v2["rolloutPolicy"]["canaryPercent"] == 10
    assert skill_v2["rollbackPolicy"]["active"] is True


def test_collaboration_execution_plan_visualization_smoke(auth_headers) -> None:
    created_at = store.now_string()
    task_id = "task-package-p-smoke"
    run_id = "run-package-p-smoke"
    store.tasks.append(
        {
            "id": task_id,
            "workflow_run_id": run_id,
            "workflow_id": "workflow-1",
            "title": "执行计划可视化 smoke",
            "description": "验证协作页执行计划字段稳定输出",
            "status": "running",
            "priority": "medium",
            "created_at": created_at,
            "completed_at": None,
            "agent": "Master Bot Planner",
            "tokens": 20,
            "route_decision": {
                "intent": "help",
                "workflow_id": "workflow-1",
                "workflow_name": "客户服务工作流",
                "execution_agent": "Master Bot Planner",
                "execution_plan": {
                    "plan_type": "multi_agent",
                    "coordination_mode": "parallel",
                    "summary": "搜索 Agent + 写作 Agent",
                    "fan_out": {"mode": "parallel", "branch_count": 2},
                    "fan_in": {"strategy": "merge_summary", "aggregator": "master_bot"},
                    "steps": [
                        {
                            "id": "research",
                            "branch_id": "branch-research",
                            "intent": "search",
                            "execution_agent": "搜索 Agent",
                        },
                        {
                            "id": "synthesis",
                            "branch_id": "branch-synthesis",
                            "intent": "write",
                            "execution_agent": "写作 Agent",
                        },
                    ],
                },
                "fallback_policy": {"mode": "planner_recovery", "target": "master_bot_planner"},
                "route_rationale": {"route_reason_summary": "smoke plan"},
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
                    "cancelled_agents": 0,
                    "branch_results": [
                        {
                            "step_id": "research",
                            "branch_id": "branch-research",
                            "intent": "search",
                            "agent": "搜索 Agent",
                            "status": "completed",
                        }
                    ],
                },
                "aggregation_notes": {
                    "selected_branch_id": "branch-research",
                    "selected_agent": "搜索 Agent",
                },
            },
        },
    )

    response = client.get("/api/collaboration/overview", params={"taskId": task_id}, headers=auth_headers)

    assert response.status_code == 200
    plan = response.json()["session"]["executionPlan"]
    assert plan["version"] == "execution_plan.v1"
    assert plan["planType"] == "multi_agent"
    assert plan["coordinationMode"] == "parallel"
    assert plan["stepCount"] == 2
    assert plan["fanOut"]["branch_count"] == 2
    assert plan["steps"][0]["branchId"] == "branch-research"
    assert plan["steps"][1]["executionAgent"] == "写作 Agent"
    assert plan["fallback"]["mode"] == "planner_recovery"
    assert plan["selectedAgent"] == "搜索 Agent"
