from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.services.agent_execution_service import AgentExecutionService
from app.services import agent_service
from app.services import execution_directory_service
from app.services import mandatory_agent_registry_service
from app.services import workflow_execution_service
from app.services.agent_config_service import AgentConfigService
from app.services.brain_skill_service import BrainSkillService
from app.services.mandatory_agent_registry_service import ensure_mandatory_agents_registered
from app.services.mandatory_workflow_registry_service import ensure_mandatory_workflows_registered
from app.services.persistence_service import StatePersistenceService
from app.services.skill_registry_service import skill_registry_service
from app.services.store import InMemoryStore, store


client = TestClient(app)


def _sqlite_service(tmp_path: Path, seeded_store: InMemoryStore) -> StatePersistenceService:
    database_path = tmp_path / "agents-runtime.db"
    service = StatePersistenceService(
        runtime_store=seeded_store,
        database_url=f"sqlite:///{database_path}",
    )
    assert service.initialize() is True
    return service


def _build_agent(
    *,
    agent_id: str,
    agent_type: str,
    status_text: str = "running",
    enabled: bool = True,
    config_snapshot: dict | None = None,
) -> dict:
    return {
        "id": agent_id,
        "name": f"{agent_id}-name",
        "description": f"{agent_id}-description",
        "type": agent_type,
        "status": status_text,
        "enabled": enabled,
        "tasks_completed": 10,
        "tasks_total": 10,
        "avg_response_time": "10ms",
        "tokens_used": 100,
        "tokens_limit": 1000,
        "success_rate": 99.0,
        "last_active": "刚刚",
        "config_snapshot": config_snapshot,
    }


def test_agent_heartbeat_route_updates_runtime_status_and_metrics(auth_headers) -> None:
    response = client.post(
        "/api/agents/3/heartbeat",
        headers=auth_headers,
        json={
            "status": "running",
            "intervalSeconds": 6,
            "timeoutSeconds": 30,
            "source": "agent-worker-3",
            "load": 0.42,
            "queueDepth": 3,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["agent"]["runtimeStatus"] == "online"
    assert payload["agent"]["routable"] is True
    assert payload["agent"]["runtimeMetrics"]["source"] == "agent-worker-3"
    assert payload["agent"]["runtimeMetrics"]["load"] == 0.42
    assert payload["agent"]["runtimeMetrics"]["queue_depth"] == 3

    status_response = client.get("/api/agents/3/status", headers=auth_headers)
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["runtimeStatus"] == "online"
    assert status_payload["lastHeartbeatAt"]


def test_agent_list_marks_stale_heartbeat_agent_offline(auth_headers) -> None:
    stale_at = (datetime.now(UTC) - timedelta(seconds=120)).isoformat()
    store.agents.append(
        _build_agent(
            agent_id="agent-stale-heartbeat",
            agent_type="search",
            config_snapshot={
                "runtime": {
                    "last_heartbeat_at": stale_at,
                    "heartbeat_interval_seconds": 5,
                    "heartbeat_timeout_seconds": 30,
                }
            },
        )
    )

    response = client.get("/api/agents", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    stale_agent = next(item for item in payload["items"] if item["id"] == "agent-stale-heartbeat")
    assert stale_agent["runtimeStatus"] == "offline"
    assert stale_agent["routable"] is False
    assert stale_agent["deletable"] is True
    assert stale_agent["deleteBlockedReason"] is None


def test_delete_agent_route_removes_custom_agent(auth_headers) -> None:
    store.agents = [
        _build_agent(
            agent_id="removable-agent",
            agent_type="default",
            enabled=False,
            config_snapshot={"status": "loaded", "runtime": {}},
        )
    ]

    response = client.delete("/api/agents/removable-agent", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["agentId"] == "removable-agent"
    assert not any(agent["id"] == "removable-agent" for agent in store.agents)

    listed = client.get("/api/agents", headers=auth_headers)
    assert listed.status_code == 200
    assert not any(item["id"] == "removable-agent" for item in listed.json()["items"])


def test_delete_agent_route_allows_deleting_mandatory_agent(auth_headers) -> None:
    ensure_mandatory_agents_registered()

    response = client.delete("/api/agents/security", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["agentId"] == "security"
    assert not any(agent["id"] == "security" for agent in store.agents)

    listed = client.get("/api/agents", headers=auth_headers)
    assert listed.status_code == 200
    assert not any(item["id"] == "security" for item in listed.json()["items"])


def test_delete_mandatory_agent_route_hides_projection_when_database_is_enabled(
    tmp_path: Path,
    monkeypatch,
    auth_headers,
) -> None:
    runtime_store = InMemoryStore()
    runtime_store.agents = []
    service = _sqlite_service(tmp_path, runtime_store)
    config_root = Path(__file__).resolve().parents[2] / "agents"

    original_agent_persistence = agent_service.persistence_service
    original_agent_store = agent_service.store
    original_registry_persistence = mandatory_agent_registry_service.persistence_service
    original_registry_store = mandatory_agent_registry_service.store
    original_registry_agent_config_service = mandatory_agent_registry_service.agent_config_service

    monkeypatch.setattr(agent_service, "persistence_service", service)
    monkeypatch.setattr(agent_service, "store", runtime_store)
    monkeypatch.setattr(mandatory_agent_registry_service, "persistence_service", service)
    monkeypatch.setattr(mandatory_agent_registry_service, "store", runtime_store)
    monkeypatch.setattr(
        mandatory_agent_registry_service,
        "agent_config_service",
        AgentConfigService(config_root=config_root),
    )

    try:
        mandatory_agent_registry_service.ensure_mandatory_agents_registered()

        response = client.delete("/api/agents/security", headers=auth_headers)
        listed = client.get("/api/agents", headers=auth_headers)
        with pytest.raises(HTTPException) as exc_info:
            agent_service.get_agent("security")
        persisted_agent = service.get_agent("security")
        suppressed_agent_ids = runtime_store.system_settings.get(
            mandatory_agent_registry_service.MANDATORY_AGENT_SUPPRESSION_SETTING_KEY
        )
    finally:
        monkeypatch.setattr(agent_service, "persistence_service", original_agent_persistence)
        monkeypatch.setattr(agent_service, "store", original_agent_store)
        monkeypatch.setattr(mandatory_agent_registry_service, "persistence_service", original_registry_persistence)
        monkeypatch.setattr(mandatory_agent_registry_service, "store", original_registry_store)
        monkeypatch.setattr(
            mandatory_agent_registry_service,
            "agent_config_service",
            original_registry_agent_config_service,
        )
        service.close()

    assert response.status_code == 200
    assert listed.status_code == 200
    assert not any(item["id"] == "security" for item in listed.json()["items"])
    assert exc_info.value.status_code == 404
    assert persisted_agent is None
    assert suppressed_agent_ids == ["security"]


def test_set_agent_enabled_route_updates_enabled_state(auth_headers) -> None:
    store.agents = [
        _build_agent(
            agent_id="toggle-agent",
            agent_type="default",
            enabled=True,
            config_snapshot={"status": "loaded", "runtime": {}},
        )
    ]

    disable_response = client.put(
        "/api/agents/toggle-agent/enabled",
        headers=auth_headers,
        json={"enabled": False},
    )
    assert disable_response.status_code == 200
    disable_payload = disable_response.json()
    assert disable_payload["ok"] is True
    assert disable_payload["agent"]["enabled"] is False

    status_response = client.get("/api/agents/toggle-agent/status", headers=auth_headers)
    assert status_response.status_code == 200
    assert status_response.json()["enabled"] is False

    enable_response = client.put(
        "/api/agents/toggle-agent/enabled",
        headers=auth_headers,
        json={"enabled": True},
    )
    assert enable_response.status_code == 200
    assert enable_response.json()["agent"]["enabled"] is True


def test_create_agent_route_sets_enabled_project_model_binding(auth_headers, monkeypatch) -> None:
    ensure_mandatory_workflows_registered()
    monkeypatch.setattr(
        agent_service,
        "get_agent_api_runtime_settings",
        lambda: {
            "providers": {
                "openai": {
                    "enabled": True,
                    "model": "gpt-5.4",
                },
                "claude": {
                    "enabled": False,
                    "model": "claude-sonnet-4-0",
                },
            }
        },
    )

    response = client.post(
        "/api/agents",
        headers=auth_headers,
        json={
            "name": "客服写作 Agent",
            "description": "负责客户回复草拟",
            "type": "write",
            "enabled": True,
            "providerKey": "openai",
            "agentWorkflowId": "mandatory-workflow-brain-foundation",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["agent"]["modelBinding"]["providerKey"] == "openai"
    assert payload["agent"]["modelBinding"]["model"] == "gpt-5.4"
    assert payload["agent"]["name"] == "客服写作 Agent"


def test_create_agent_route_requires_agent_workflow_binding_when_enabled(auth_headers, monkeypatch) -> None:
    ensure_mandatory_workflows_registered()
    monkeypatch.setattr(
        agent_service,
        "get_agent_api_runtime_settings",
        lambda: {
            "providers": {
                "openai": {
                    "enabled": True,
                    "model": "gpt-5.4",
                },
            }
        },
    )

    response = client.post(
        "/api/agents",
        headers=auth_headers,
        json={
            "name": "无绑定 Agent",
            "description": "测试启用前绑定限制",
            "type": "write",
            "enabled": True,
            "providerKey": "openai",
            "model": "gpt-5.4",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "启用 Agent 前必须绑定 agent_workflow_id"


def test_update_agent_config_route_updates_selected_model_binding(auth_headers, monkeypatch) -> None:
    ensure_mandatory_workflows_registered()
    monkeypatch.setattr(
        agent_service,
        "get_agent_api_runtime_settings",
        lambda: {
            "providers": {
                "openai": {
                    "enabled": True,
                    "model": "gpt-5.4",
                },
                "deepseek": {
                    "enabled": True,
                    "model": "deepseek-chat",
                },
            }
        },
    )
    store.agents = [
        _build_agent(
            agent_id="search-agent",
            agent_type="search",
            config_snapshot={
                "status": "loaded",
                "agent": {
                    "model": "gpt-4.1-mini",
                    "provider": "openai",
                },
                "runtime": {},
            },
        )
    ]

    response = client.put(
        "/api/agents/search-agent/config",
        headers=auth_headers,
        json={
            "name": "搜索 Agent",
            "description": "更新后的搜索配置",
            "type": "search",
            "enabled": True,
            "providerKey": "deepseek",
            "model": "deepseek-chat",
            "agentWorkflowId": "mandatory-workflow-brain-foundation",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["agent"]["modelBinding"]["providerKey"] == "deepseek"
    assert payload["agent"]["modelBinding"]["model"] == "deepseek-chat"

    status_response = client.get("/api/agents/search-agent/status", headers=auth_headers)
    assert status_response.status_code == 200
    assert status_response.json()["modelBinding"]["providerKey"] == "deepseek"


def test_update_agent_config_route_allows_saving_existing_enabled_agent_without_workflow_binding(
    auth_headers,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        agent_service,
        "get_agent_api_runtime_settings",
        lambda: {
            "providers": {
                "openai": {
                    "enabled": True,
                    "model": "gpt-5.4",
                },
            }
        },
    )
    store.agents = [
        _build_agent(
            agent_id="legacy-enabled-agent",
            agent_type="default",
            enabled=True,
            config_snapshot={
                "status": "loaded",
                "agent": {
                    "model": "gpt-5.4",
                    "provider": "openai",
                },
                "runtime": {},
            },
        )
    ]

    response = client.put(
        "/api/agents/legacy-enabled-agent/config",
        headers=auth_headers,
        json={
            "name": "legacy-enabled-agent-name",
            "description": "更新现有无绑定 Agent",
            "type": "default",
            "enabled": True,
            "providerKey": "openai",
            "model": "gpt-5.4",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["agent"]["enabled"] is True
    assert payload["agent"]["agentWorkflowId"] is None


def test_update_agent_config_route_persists_agent_workflow_contract_binding(
    auth_headers,
    monkeypatch,
) -> None:
    ensure_mandatory_workflows_registered()
    monkeypatch.setattr(
        agent_service,
        "get_agent_api_runtime_settings",
        lambda: {
            "providers": {
                "openai": {
                    "enabled": True,
                    "model": "gpt-5.4",
                },
            }
        },
    )
    store.agents = [
        _build_agent(
            agent_id="contract-agent",
            agent_type="search",
            config_snapshot={
                "status": "loaded",
                "agent": {
                    "model": "gpt-5.4",
                    "provider": "openai",
                },
                "runtime": {},
            },
        )
    ]

    response = client.put(
        "/api/agents/contract-agent/config",
        headers=auth_headers,
        json={
            "name": "Contract Agent",
            "description": "绑定执行契约",
            "type": "search",
            "enabled": True,
            "providerKey": "openai",
            "model": "gpt-5.4",
            "agentWorkflowId": "mandatory-workflow-brain-foundation",
            "inputContract": {"required": ["query"]},
            "outputContract": {"required": ["summary"]},
            "contractVersion": "agent-workflow-contract-v2",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["agent"]["agentWorkflowId"] == "mandatory-workflow-brain-foundation"
    assert payload["agent"]["inputContract"] == {"required": ["query"]}
    assert payload["agent"]["outputContract"] == {"required": ["summary"]}
    assert payload["agent"]["contractVersion"] == "agent-workflow-contract-v2"

    status_response = client.get("/api/agents/contract-agent/status", headers=auth_headers)
    assert status_response.status_code == 200
    assert status_response.json()["agentWorkflowId"] == "mandatory-workflow-brain-foundation"
    assert status_response.json()["contractVersion"] == "agent-workflow-contract-v2"


def test_update_agent_config_route_preserves_existing_workflow_binding_when_request_omits_it(
    auth_headers,
    monkeypatch,
) -> None:
    ensure_mandatory_workflows_registered()
    monkeypatch.setattr(
        agent_service,
        "get_agent_api_runtime_settings",
        lambda: {
            "providers": {
                "openai": {
                    "enabled": True,
                    "model": "gpt-5.4",
                },
            }
        },
    )
    store.agents = [
        _build_agent(
            agent_id="preserve-binding-agent",
            agent_type="search",
            config_snapshot={
                "status": "loaded",
                "agent": {
                    "model": "gpt-5.4",
                    "provider": "openai",
                    "agent_workflow_id": "mandatory-workflow-brain-foundation",
                    "input_contract": {"required": ["query"]},
                    "output_contract": {"required": ["summary"]},
                    "contract_version": "agent-workflow-contract-v2",
                },
                "runtime": {},
            },
        )
    ]

    response = client.put(
        "/api/agents/preserve-binding-agent/config",
        headers=auth_headers,
        json={
            "name": "Preserve Binding Agent",
            "description": "省略绑定字段时仍应保留",
            "type": "search",
            "enabled": True,
            "providerKey": "openai",
            "model": "gpt-5.4",
            "skillIds": [],
            "toolIds": [],
        },
    )

    assert response.status_code == 200
    payload = response.json()["agent"]
    assert payload["agentWorkflowId"] == "mandatory-workflow-brain-foundation"
    assert payload["inputContract"] == {"required": ["query"]}
    assert payload["outputContract"] == {"required": ["summary"]}
    assert payload["contractVersion"] == "agent-workflow-contract-v2"


def test_create_agent_route_exposes_workflow_binding_in_list_and_status(auth_headers, monkeypatch) -> None:
    ensure_mandatory_workflows_registered()
    monkeypatch.setattr(
        agent_service,
        "get_agent_api_runtime_settings",
        lambda: {
            "providers": {
                "openai": {
                    "enabled": True,
                    "model": "gpt-5.4",
                },
            }
        },
    )

    response = client.post(
        "/api/agents",
        headers=auth_headers,
        json={
            "name": "Binding Visible Agent",
            "description": "验证绑定字段序列化",
            "type": "search",
            "enabled": True,
            "providerKey": "openai",
            "model": "gpt-5.4",
            "agentWorkflowId": "mandatory-workflow-brain-foundation",
            "inputContract": {"required": ["query"]},
            "outputContract": {"required": ["summary"]},
            "contractVersion": "agent-workflow-contract-v3",
        },
    )

    assert response.status_code == 200
    created = response.json()["agent"]
    assert created["agentWorkflowId"] == "mandatory-workflow-brain-foundation"
    assert created["inputContract"] == {"required": ["query"]}
    assert created["outputContract"] == {"required": ["summary"]}
    assert created["contractVersion"] == "agent-workflow-contract-v3"

    list_response = client.get("/api/agents", headers=auth_headers)
    assert list_response.status_code == 200
    listed = next(item for item in list_response.json()["items"] if item["id"] == created["id"])
    assert listed["agentWorkflowId"] == "mandatory-workflow-brain-foundation"
    assert listed["inputContract"] == {"required": ["query"]}
    assert listed["outputContract"] == {"required": ["summary"]}
    assert listed["contractVersion"] == "agent-workflow-contract-v3"

    status_response = client.get(f"/api/agents/{created['id']}/status", headers=auth_headers)
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["agentWorkflowId"] == "mandatory-workflow-brain-foundation"
    assert status_payload["inputContract"] == {"required": ["query"]}
    assert status_payload["outputContract"] == {"required": ["summary"]}
    assert status_payload["contractVersion"] == "agent-workflow-contract-v3"


def test_create_agent_route_serializes_unbound_workflow_fields(auth_headers, monkeypatch) -> None:
    monkeypatch.setattr(
        agent_service,
        "get_agent_api_runtime_settings",
        lambda: {
            "providers": {
                "openai": {
                    "enabled": True,
                    "model": "gpt-5.4",
                },
            }
        },
    )

    response = client.post(
        "/api/agents",
        headers=auth_headers,
        json={
            "name": "Unbound Agent",
            "description": "验证未绑定序列化",
            "type": "search",
            "enabled": False,
            "providerKey": "openai",
            "model": "gpt-5.4",
        },
    )

    assert response.status_code == 200
    created = response.json()["agent"]
    assert created["agentWorkflowId"] is None
    assert created["inputContract"] == {}
    assert created["outputContract"] == {}
    assert created["contractVersion"] is None

    list_response = client.get("/api/agents", headers=auth_headers)
    assert list_response.status_code == 200
    listed = next(item for item in list_response.json()["items"] if item["id"] == created["id"])
    assert listed["agentWorkflowId"] is None
    assert listed["inputContract"] == {}
    assert listed["outputContract"] == {}
    assert listed["contractVersion"] is None

    status_response = client.get(f"/api/agents/{created['id']}/status", headers=auth_headers)
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["agentWorkflowId"] is None
    assert status_payload["inputContract"] == {}
    assert status_payload["outputContract"] == {}
    assert status_payload["contractVersion"] is None


def test_update_agent_config_route_supports_unbind_and_rebind_workflow_contract(
    auth_headers,
    monkeypatch,
) -> None:
    ensure_mandatory_workflows_registered()
    monkeypatch.setattr(
        agent_service,
        "get_agent_api_runtime_settings",
        lambda: {
            "providers": {
                "openai": {
                    "enabled": True,
                    "model": "gpt-5.4",
                },
            }
        },
    )
    store.agents = [
        _build_agent(
            agent_id="rebind-agent",
            agent_type="search",
            config_snapshot={
                "status": "loaded",
                "agent": {
                    "model": "gpt-5.4",
                    "provider": "openai",
                    "agent_workflow_id": "mandatory-workflow-brain-foundation",
                    "input_contract": {"required": ["query"]},
                    "output_contract": {"required": ["summary"]},
                    "contract_version": "agent-workflow-contract-v2",
                },
                "runtime": {},
            },
        )
    ]

    unbind_response = client.put(
        "/api/agents/rebind-agent/config",
        headers=auth_headers,
        json={
            "name": "Rebind Agent",
            "description": "先解绑再重绑",
            "type": "search",
            "enabled": False,
            "providerKey": "openai",
            "model": "gpt-5.4",
            "agentWorkflowId": "",
            "inputContract": {},
            "outputContract": None,
            "contractVersion": "",
        },
    )

    assert unbind_response.status_code == 200
    unbound = unbind_response.json()["agent"]
    assert unbound["agentWorkflowId"] is None
    assert unbound["inputContract"] == {}
    assert unbound["outputContract"] == {}
    assert unbound["contractVersion"] is None

    list_response = client.get("/api/agents", headers=auth_headers)
    assert list_response.status_code == 200
    listed_unbound = next(item for item in list_response.json()["items"] if item["id"] == "rebind-agent")
    assert listed_unbound["agentWorkflowId"] is None
    assert listed_unbound["inputContract"] == {}
    assert listed_unbound["outputContract"] == {}
    assert listed_unbound["contractVersion"] is None

    status_response = client.get("/api/agents/rebind-agent/status", headers=auth_headers)
    assert status_response.status_code == 200
    unbound_status = status_response.json()
    assert unbound_status["agentWorkflowId"] is None
    assert unbound_status["inputContract"] == {}
    assert unbound_status["outputContract"] == {}
    assert unbound_status["contractVersion"] is None

    rebind_response = client.put(
        "/api/agents/rebind-agent/config",
        headers=auth_headers,
        json={
            "name": "Rebind Agent",
            "description": "重新绑定契约",
            "type": "search",
            "enabled": True,
            "providerKey": "openai",
            "model": "gpt-5.4",
            "agentWorkflowId": "mandatory-workflow-brain-foundation",
            "inputContract": {"required": ["keywords"]},
            "outputContract": {"required": ["answer"]},
            "contractVersion": "agent-workflow-contract-v4",
        },
    )

    assert rebind_response.status_code == 200
    rebound = rebind_response.json()["agent"]
    assert rebound["agentWorkflowId"] == "mandatory-workflow-brain-foundation"
    assert rebound["inputContract"] == {"required": ["keywords"]}
    assert rebound["outputContract"] == {"required": ["answer"]}
    assert rebound["contractVersion"] == "agent-workflow-contract-v4"

    list_response = client.get("/api/agents", headers=auth_headers)
    assert list_response.status_code == 200
    listed_rebound = next(item for item in list_response.json()["items"] if item["id"] == "rebind-agent")
    assert listed_rebound["agentWorkflowId"] == "mandatory-workflow-brain-foundation"
    assert listed_rebound["inputContract"] == {"required": ["keywords"]}
    assert listed_rebound["outputContract"] == {"required": ["answer"]}
    assert listed_rebound["contractVersion"] == "agent-workflow-contract-v4"

    status_response = client.get("/api/agents/rebind-agent/status", headers=auth_headers)
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["agentWorkflowId"] == "mandatory-workflow-brain-foundation"
    assert status_payload["inputContract"] == {"required": ["keywords"]}
    assert status_payload["outputContract"] == {"required": ["answer"]}
    assert status_payload["contractVersion"] == "agent-workflow-contract-v4"


def test_agent_execution_contracts_preserve_agent_specific_snapshots() -> None:
    service = AgentExecutionService()
    task = {
        "id": "task-agent-contract",
        "title": "Agent Contract",
        "description": "请整理客户交付说明",
        "manager_packet": {"delivery_mode": "structured_result"},
    }
    run = {
        "id": "run-agent-contract",
        "workflow_id": "mandatory-workflow-brain-foundation",
        "intent": "write",
        "dispatch_context": {
            "route_decision": {
                "routing_strategy": "workflow_trigger+execution_agent_support",
            }
        },
    }
    execution_agent = {"id": "agent-contract", "name": "Contract Agent", "type": "write"}
    result = {
        "kind": "draft_message",
        "title": "Agent Specific Result",
        "summary": "保留专属契约快照",
        "content": "这是 Agent 工作流生成的结果。",
        "bullets": ["契约保真"],
        "references": [],
        "contract_version": "agent-workflow-contract-v9",
        "input_snapshot": {
            "schema": "agent-specific-input",
            "task_id": "agent-specific-task",
        },
        "output_snapshot": {
            "schema": "agent-specific-output",
            "result_kind": "draft_message",
        },
    }

    attached = service._attach_execution_contracts(
        task=task,
        run=run,
        execution_agent=execution_agent,
        result=result,
    )

    assert attached["dispatch_contract"]["contract_version"] == "brain-core-v1"
    assert attached["contract_version"] == "agent-workflow-contract-v9"
    assert attached["input_snapshot"]["schema"] == "agent-specific-input"
    assert attached["input_snapshot"]["task_id"] == "agent-specific-task"
    assert attached["input_snapshot"]["workflow_run_id"] == "run-agent-contract"
    assert attached["output_snapshot"]["schema"] == "agent-specific-output"
    assert attached["output_snapshot"]["result_kind"] == "draft_message"
    assert attached["output_snapshot"]["summary"] == "保留专属契约快照"


def test_update_agent_config_route_persists_bound_skill_ids(auth_headers, monkeypatch) -> None:
    ensure_mandatory_workflows_registered()

    class _MemoryPersistence:
        def __init__(self) -> None:
            self._settings: dict[str, dict] = {}

        def read_system_setting(self, key: str) -> tuple[dict | None, bool]:
            payload = self._settings.get(key)
            if payload is None:
                return None, False
            return {"key": key, "payload": payload, "updated_at": ""}, True

        def persist_system_setting(self, *, key: str, payload: dict, updated_at: str | None = None) -> bool:
            self._settings[key] = payload
            return True

    original_brain_skill_service = agent_service.brain_skill_service
    original_registry = skill_registry_service.list_abilities(enabled=None)
    skill_registry_service.clear()
    brain_skill_service = BrainSkillService(
        runtime_store=store,
        persistence=_MemoryPersistence(),
        registry=skill_registry_service,
    )
    brain_skill_service.upload_skill(
        {
            "file_name": "customer_support.yaml",
            "content": """
id: customer-support
name: Customer Support
description: 客服答复知识库。
tags:
  - support
capabilities:
  - answer
""".strip(),
        }
    )

    monkeypatch.setattr(agent_service, "brain_skill_service", brain_skill_service)
    monkeypatch.setattr(
        agent_service,
        "get_agent_api_runtime_settings",
        lambda: {
            "providers": {
                "openai": {
                    "enabled": True,
                    "model": "gpt-5.4",
                },
            }
        },
    )
    store.agents = [
        _build_agent(
            agent_id="support-agent",
            agent_type="write",
            config_snapshot={
                "status": "loaded",
                "agent": {
                    "model": "gpt-5.4",
                    "provider": "openai",
                },
                "runtime": {},
            },
        )
    ]

    response = client.put(
        "/api/agents/support-agent/config",
        headers=auth_headers,
        json={
            "name": "Support Agent",
            "description": "带本地 Skill 的客服 Agent",
            "type": "write",
            "enabled": True,
            "providerKey": "openai",
            "model": "gpt-5.4",
            "agentWorkflowId": "mandatory-workflow-brain-foundation",
            "skillIds": ["customer-support"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["agent"]["boundSkillIds"] == ["customer-support"]
    assert payload["agent"]["boundSkills"][0]["id"] == "customer-support"
    assert payload["agent"]["boundSkills"][0]["name"] == "Customer Support"
    skill_registry_service.clear()
    for ability in original_registry:
        skill_registry_service.register_ability(ability, overwrite=True)
    monkeypatch.setattr(agent_service, "brain_skill_service", original_brain_skill_service)


def test_update_agent_config_route_persists_bound_tool_ids(auth_headers, monkeypatch) -> None:
    ensure_mandatory_workflows_registered()
    class _ToolSourceServiceStub:
        @staticmethod
        def list_tools(*, refresh: bool = False) -> list[dict]:
            return [
                {
                    "id": "mcp-tool-web-search",
                    "name": "web_search",
                    "type": "mcp",
                    "description": "Search MCP tool",
                    "source": "local-mcp-services",
                },
                {
                    "id": "mcp-tool-weather-lookup",
                    "name": "weather_lookup",
                    "type": "mcp",
                    "description": "Weather MCP tool",
                    "source": "local-mcp-services",
                },
            ]

    monkeypatch.setattr(agent_service, "tool_source_service", _ToolSourceServiceStub())
    monkeypatch.setattr(
        agent_service,
        "get_agent_api_runtime_settings",
        lambda: {
            "providers": {
                "openai": {
                    "enabled": True,
                    "model": "gpt-5.4",
                },
            }
        },
    )
    store.agents = [
        _build_agent(
            agent_id="tool-bound-agent",
            agent_type="search",
            config_snapshot={
                "status": "loaded",
                "agent": {
                    "model": "gpt-5.4",
                    "provider": "openai",
                },
                "runtime": {},
            },
        )
    ]

    response = client.put(
        "/api/agents/tool-bound-agent/config",
        headers=auth_headers,
        json={
            "name": "Tool Bound Agent",
            "description": "绑定 MCP 工具的 Agent",
            "type": "search",
            "enabled": True,
            "providerKey": "openai",
            "model": "gpt-5.4",
            "agentWorkflowId": "mandatory-workflow-brain-foundation",
            "toolIds": ["mcp-tool-web-search", "mcp-tool-weather-lookup"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["agent"]["boundToolIds"] == [
        "mcp-tool-web-search",
        "mcp-tool-weather-lookup",
    ]
    assert payload["agent"]["boundTools"] == [
        {
            "id": "mcp-tool-web-search",
            "name": "web_search",
            "type": "mcp",
            "description": "Search MCP tool",
            "source": "local-mcp-services",
        },
        {
            "id": "mcp-tool-weather-lookup",
            "name": "weather_lookup",
            "type": "mcp",
            "description": "Weather MCP tool",
            "source": "local-mcp-services",
        },
    ]
    assert payload["agent"]["configSnapshot"]["agent"]["tool_ids"] == [
        "mcp-tool-web-search",
        "mcp-tool-weather-lookup",
    ]
    assert payload["agent"]["configSnapshot"]["runtime"]["tool_binding"]["tool_ids"] == [
        "mcp-tool-web-search",
        "mcp-tool-weather-lookup",
    ]
    assert payload["agent"]["configSummary"]["tools_count"] == 2

    status_response = client.get("/api/agents/tool-bound-agent/status", headers=auth_headers)
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["boundToolIds"] == [
        "mcp-tool-web-search",
        "mcp-tool-weather-lookup",
    ]
    assert status_payload["boundTools"][0]["id"] == "mcp-tool-web-search"


def test_resolve_direct_execution_agent_prefers_healthy_status() -> None:
    now = datetime.now(UTC)
    store.agents = [
        _build_agent(
            agent_id="search-degraded",
            agent_type="search",
            config_snapshot={
                "runtime": {
                    "last_heartbeat_at": (now - timedelta(seconds=40)).isoformat(),
                    "heartbeat_interval_seconds": 10,
                    "heartbeat_timeout_seconds": 60,
                }
            },
        ),
        _build_agent(
            agent_id="search-online",
            agent_type="search",
            config_snapshot={
                "runtime": {
                    "last_heartbeat_at": now.isoformat(),
                    "heartbeat_interval_seconds": 10,
                    "heartbeat_timeout_seconds": 60,
                }
            },
        ),
    ]

    selected = workflow_execution_service.resolve_direct_execution_agent("search")
    assert selected is not None
    assert selected["id"] == "search-online"


def test_resolve_direct_execution_agent_falls_back_to_degraded() -> None:
    now = datetime.now(UTC)
    store.agents = [
        _build_agent(
            agent_id="search-degraded-only",
            agent_type="search",
            config_snapshot={
                "runtime": {
                    "last_heartbeat_at": (now - timedelta(seconds=40)).isoformat(),
                    "heartbeat_interval_seconds": 10,
                    "heartbeat_timeout_seconds": 60,
                }
            },
        )
    ]

    selected = workflow_execution_service.resolve_direct_execution_agent("search")
    assert selected is not None
    assert selected["id"] == "search-degraded-only"


def test_resolve_agent_dispatch_execution_agent_keeps_direct_wrapper_compatible() -> None:
    now = datetime.now(UTC)
    store.agents = [
        _build_agent(
            agent_id="search-online",
            agent_type="search",
            config_snapshot={
                "runtime": {
                    "last_heartbeat_at": now.isoformat(),
                    "heartbeat_interval_seconds": 10,
                    "heartbeat_timeout_seconds": 60,
                }
            },
        )
    ]

    selected = workflow_execution_service.resolve_agent_dispatch_execution_agent("search")
    wrapped = workflow_execution_service.resolve_direct_execution_agent("search")

    assert selected is not None
    assert wrapped is not None
    assert selected["id"] == "search-online"
    assert wrapped["id"] == selected["id"]


def test_resolve_named_execution_agent_does_not_auto_register_missing_agent(monkeypatch) -> None:
    original_agents = store.clone(store.agents)
    original_persistence = workflow_execution_service.persistence_service
    original_registry_persistence = mandatory_agent_registry_service.persistence_service
    remaining_agents: list[dict] | None = None

    class _NoPersistence:
        enabled = False

        @staticmethod
        def get_agent(_agent_id: str):
            return None

        @staticmethod
        def list_agents():
            return []

    try:
        store.agents = []
        monkeypatch.setattr(workflow_execution_service, "persistence_service", _NoPersistence())
        monkeypatch.setattr(mandatory_agent_registry_service, "persistence_service", _NoPersistence())
        monkeypatch.setattr(
            mandatory_agent_registry_service,
            "ensure_mandatory_agents_registered",
            lambda: (_ for _ in ()).throw(AssertionError("unexpected auto registration")),
        )

        selected = workflow_execution_service.resolve_named_execution_agent("security")
        wrapped = execution_directory_service.resolve_named_execution_agent("security")
        remaining_agents = store.clone(store.agents)
    finally:
        store.agents = original_agents
        monkeypatch.setattr(workflow_execution_service, "persistence_service", original_persistence)
        monkeypatch.setattr(mandatory_agent_registry_service, "persistence_service", original_registry_persistence)

    assert selected is None
    assert wrapped is None
    assert remaining_agents == []


def test_resolve_named_execution_agent_uses_mandatory_projection_when_database_is_empty(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime_store = InMemoryStore()
    runtime_store.agents = []
    service = _sqlite_service(tmp_path, runtime_store)
    config_root = Path(__file__).resolve().parents[2] / "agents"

    original_execution_persistence = workflow_execution_service.persistence_service
    original_execution_store = workflow_execution_service.store
    original_registry_agent_config_service = mandatory_agent_registry_service.agent_config_service
    original_registry_store = mandatory_agent_registry_service.store

    monkeypatch.setattr(workflow_execution_service, "persistence_service", service)
    monkeypatch.setattr(workflow_execution_service, "store", runtime_store)
    monkeypatch.setattr(
        mandatory_agent_registry_service,
        "agent_config_service",
        AgentConfigService(config_root=config_root),
    )
    monkeypatch.setattr(mandatory_agent_registry_service, "store", runtime_store)

    try:
        selected = workflow_execution_service.resolve_named_execution_agent("security")
        wrapped = execution_directory_service.resolve_named_execution_agent("conversation")
        persisted_agents = service.list_agents() or []
    finally:
        monkeypatch.setattr(workflow_execution_service, "persistence_service", original_execution_persistence)
        monkeypatch.setattr(workflow_execution_service, "store", original_execution_store)
        monkeypatch.setattr(
            mandatory_agent_registry_service,
            "agent_config_service",
            original_registry_agent_config_service,
        )
        monkeypatch.setattr(mandatory_agent_registry_service, "store", original_registry_store)
        service.close()

    assert selected is not None
    assert selected["id"] == "security"
    assert wrapped is not None
    assert wrapped["id"] == "conversation"
    assert persisted_agents == []


def test_agent_dispatch_run_detection_accepts_canonical_type() -> None:
    assert workflow_execution_service._is_agent_dispatch_run(
        {
            "workflow_id": "workflow-1",
            "dispatch_context": {"type": "agent_dispatch"},
        }
    )


def test_agent_dispatch_run_detection_accepts_legacy_type_alias() -> None:
    assert workflow_execution_service._is_agent_dispatch_run(
        {
            "workflow_id": "workflow-1",
            "dispatch_context": {"type": "direct_agent_dispatch"},
        }
    )
    assert workflow_execution_service._is_agent_dispatch_run(
        {
            "workflow_id": workflow_execution_service.AGENT_DISPATCH_WORKFLOW_ID,
            "dispatch_context": {"type": "workflow_dispatch"},
        }
    )
    assert workflow_execution_service._is_agent_dispatch_run(
        {
            "workflow_id": workflow_execution_service.LEGACY_AGENT_DISPATCH_WORKFLOW_ID,
            "dispatch_context": {"type": "workflow_dispatch"},
        }
    )


def test_dispatch_type_alias_normalization_maps_legacy_direct_name() -> None:
    assert workflow_execution_service._normalize_dispatch_context_type("agent_dispatch") == "agent_dispatch"
    assert (
        workflow_execution_service._normalize_dispatch_context_type("direct_agent_dispatch")
        == "agent_dispatch"
    )


def test_fallback_policy_canonical_mode_resolves_agent_execution_recovery_action() -> None:
    assert workflow_execution_service._resolved_fallback_action(
        fallback_policy={"mode": "agent_dispatch_fallback"},
        reason="executor_unavailable",
    ) == "reroute_agent_execution"


def test_fallback_policy_legacy_mode_alias_resolves_agent_execution_recovery_action() -> None:
    assert workflow_execution_service._resolved_fallback_action(
        fallback_policy={"mode": "direct_agent_fallback"},
        reason="executor_unavailable",
    ) == "reroute_agent_execution"


def test_fallback_policy_canonical_mode_allows_auto_recovery_gate() -> None:
    dispatch_context = {"state_machine": {"fallback_attempt_count": 0}}
    assert workflow_execution_service._should_auto_recover_fallback(
        fallback_policy={"mode": "agent_dispatch_fallback"},
        reason="dispatch_failure",
        dispatch_context=dispatch_context,
    )


def test_fallback_policy_legacy_mode_alias_allows_auto_recovery_gate() -> None:
    dispatch_context = {"state_machine": {"fallback_attempt_count": 0}}
    assert workflow_execution_service._should_auto_recover_fallback(
        fallback_policy={"mode": "direct_agent_fallback"},
        reason="dispatch_failure",
        dispatch_context=dispatch_context,
    )


def test_fallback_mode_alias_normalization_maps_legacy_direct_name() -> None:
    assert workflow_execution_service._normalize_fallback_policy_mode("direct_agent_fallback") == (
        "agent_dispatch_fallback"
    )
    assert workflow_execution_service._normalize_fallback_policy_mode("agent_dispatch_fallback") == (
        "agent_dispatch_fallback"
    )
