from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
import app.modules.agent_config.registries.agent_service as agent_service_module
from app.platform.persistence.persistence_service import persistence_service
from app.platform.persistence.runtime_store import store


client = TestClient(app)


def _set_user_scope(user_id: str, tenant_id: str) -> None:
    store.user_profiles[user_id] = {
        "id": user_id,
        "tenant_id": tenant_id,
        "project_id": "default",
        "environment": "development",
    }


def _enable_agent_provider(monkeypatch) -> None:
    enabled_models = {
        "openai": {
            "provider_key": "openai",
            "provider_label": "OpenAI",
            "model": "gpt-5.4",
        }
    }
    monkeypatch.setattr(agent_service_module, "_enabled_provider_models", lambda: deepcopy(enabled_models))


def test_brain_skill_scope_is_persisted_and_filtered_by_tenant(auth_headers_factory, monkeypatch) -> None:
    alpha_headers = auth_headers_factory(role="admin", user_id="tenant-admin-alpha")
    beta_headers = auth_headers_factory(role="admin", user_id="tenant-admin-beta")
    _set_user_scope("tenant-admin-alpha", "tenant-alpha")
    _set_user_scope("tenant-admin-beta", "tenant-beta")

    tenant_response = client.post(
        "/api/agents/brain-skills",
        headers=alpha_headers,
        json={
            "file_name": "tenant-alpha-skill.md",
            "content": "---\nname: Tenant Alpha Skill\n---\nTenant-only skill body.",
            "scope": "tenant",
        },
    )
    assert tenant_response.status_code == 200
    tenant_payload = tenant_response.json()
    assert tenant_payload["skill"]["scope"] == "tenant"
    assert tenant_payload["skill"]["ownerTenantId"] == "tenant-alpha"

    shared_response = client.post(
        "/api/agents/brain-skills",
        headers=alpha_headers,
        json={
            "file_name": "shared-skill.md",
            "content": "---\nname: Shared Skill\n---\nShared skill body.",
            "scope": "shared",
        },
    )
    assert shared_response.status_code == 200
    assert shared_response.json()["skill"]["ownerTenantId"] is None

    persisted_items = store.system_settings["brain_skill_library"]["items"]
    tenant_item = next(item for item in persisted_items if item["name"] == "Tenant Alpha Skill")
    assert tenant_item["scope"] == "tenant"
    assert tenant_item["owner_tenant_id"] == "tenant-alpha"

    alpha_list = client.get("/api/agents/brain-skills?tenant_id=tenant-alpha", headers=alpha_headers)
    assert alpha_list.status_code == 200
    alpha_items = alpha_list.json()["items"]
    assert [item["name"] for item in alpha_items] == ["Tenant Alpha Skill", "Shared Skill"]

    beta_list = client.get("/api/agents/brain-skills?tenant_id=tenant-beta", headers=beta_headers)
    assert beta_list.status_code == 200
    beta_items = beta_list.json()["items"]
    assert [item["name"] for item in beta_items] == ["Shared Skill"]


def test_mcp_scope_persists_and_agent_binding_rejects_cross_tenant_private_tool(
    auth_headers_factory,
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("WORKBOT_EXTERNAL_TOOL_SOURCES_FILE", str(tmp_path / "external-tools.json"))
    alpha_headers = auth_headers_factory(role="admin", user_id="tenant-admin-alpha")
    beta_headers = auth_headers_factory(role="admin", user_id="tenant-admin-beta")
    _set_user_scope("tenant-admin-alpha", "tenant-alpha")
    _set_user_scope("tenant-admin-beta", "tenant-beta")
    _enable_agent_provider(monkeypatch)

    response = client.post(
        "/api/tool-sources/register-mcp",
        headers=alpha_headers,
        json={
            "name": "tenant_alpha_query",
            "description": "Tenant Alpha only MCP",
            "base_url": "https://mcp.example.test",
            "invoke_path": "/invoke",
            "scope": "tenant",
        },
    )
    assert response.status_code == 200
    response_payload = response.json()
    tool_id = response_payload["toolId"]
    assert response_payload["tool"]["scope"] == "tenant"
    assert (
        response_payload["tool"].get("ownerTenantId")
        or response_payload["tool"].get("owner_tenant_id")
    ) == "tenant-alpha"

    registry_payload = json.loads((tmp_path / "external-tools.json").read_text(encoding="utf-8"))
    persisted_tool = next(item for item in registry_payload["tools"] if item["id"] == tool_id)
    assert persisted_tool["scope"] == "tenant"
    assert persisted_tool["owner_tenant_id"] == "tenant-alpha"

    alpha_tenant_tools = client.get("/api/tools?scope=tenant&tenant_id=tenant-alpha", headers=alpha_headers)
    assert alpha_tenant_tools.status_code == 200
    assert [item["id"] for item in alpha_tenant_tools.json()["items"]] == [tool_id]

    beta_tenant_tools = client.get("/api/tools?scope=tenant&tenant_id=tenant-beta", headers=beta_headers)
    assert beta_tenant_tools.status_code == 200
    assert beta_tenant_tools.json()["items"] == []

    create_agent_response = client.post(
        "/api/agents",
        params={"tenant_id": "tenant-beta"},
        headers=beta_headers,
        json={
            "name": "Tenant Beta Agent",
            "description": "should fail on cross-tenant tool",
            "type": "default",
            "enabled": True,
            "provider_key": "openai",
            "model": "gpt-5.4",
            "skill_ids": [],
            "tool_ids": [tool_id],
        },
    )
    assert create_agent_response.status_code == 400
    assert "当前租户不可绑定" in create_agent_response.json()["detail"]


def test_agent_config_supports_soul_roundtrip(auth_headers_factory, monkeypatch) -> None:
    headers = auth_headers_factory(role="admin", user_id="tenant-admin-soul")
    _set_user_scope("tenant-admin-soul", "tenant-alpha")
    _enable_agent_provider(monkeypatch)

    create_response = client.post(
        "/api/agents",
        params={"tenant_id": "tenant-alpha"},
        headers=headers,
        json={
            "name": "Soul Enabled Agent",
            "description": "local agent with editable soul",
            "type": "default",
            "enabled": True,
                "soul": "# Soul\n\n你负责高质量答复。",
            "provider_key": "openai",
            "model": "gpt-5.4",
            "skill_ids": [],
            "tool_ids": [],
        },
    )
    assert create_response.status_code == 200
    created_agent = create_response.json()["agent"]
    agent_id = created_agent["id"]
    assert created_agent["soul"] == "# Soul\n\n你负责高质量答复。"
    created_summary = created_agent["configSummary"]
    assert (created_summary.get("soulPresent") or created_summary.get("soul_present")) is True
    assert "soul.md" in (created_summary.get("filesLoaded") or created_summary.get("files_loaded") or [])

    update_result = agent_service_module.update_agent_config(
        agent_id,
        {
            "name": "Soul Enabled Agent",
            "description": "updated local agent soul",
            "type": "default",
            "enabled": True,
            "soul": "# Updated Soul\n\n保持结构化输出。",
            "provider_key": "openai",
            "model": "gpt-5.4",
            "skill_ids": [],
            "tool_ids": [],
        },
        tenant_id="tenant-alpha",
    )
    updated_agent = update_result["agent"]
    assert updated_agent["soul"] == "# Updated Soul\n\n保持结构化输出。"
    assert updated_agent["config_snapshot"]["soul"] == "# Updated Soul\n\n保持结构化输出。"

    listed_agent = next(item for item in agent_service_module.list_agents()["items"] if item["id"] == agent_id)
    assert listed_agent["soul"] == "# Updated Soul\n\n保持结构化输出。"
    listed_summary = listed_agent["config_summary"]
    assert (listed_summary.get("soulPresent") or listed_summary.get("soul_present")) is True


def test_list_agents_tolerates_stale_bound_tool_ids(auth_headers_factory) -> None:
    headers = auth_headers_factory(role="admin", user_id="tenant-admin-stale-tool")
    _set_user_scope("tenant-admin-stale-tool", "tenant-alpha")

    stale_agent = {
        "id": "stale-bound-tool-agent",
        "name": "Stale Bound Tool Agent",
        "description": "contains historical tool binding",
        "type": "default",
        "status": "idle",
        "enabled": True,
        "tasks_completed": 0,
        "tasks_total": 0,
        "avg_response_time": "--",
        "tokens_used": 0,
        "tokens_limit": 0,
        "success_rate": 100.0,
        "last_active": "未运行",
        "config_snapshot": {
            "status": "generated",
            "warnings": [],
            "agent": {
                "agent_id": "stale-bound-tool-agent",
                "name": "Stale Bound Tool Agent",
                "type": "default",
            },
            "runtime": {
                "tool_binding": {
                    "tool_ids": ["tool-a"],
                    "source": "manual",
                }
            },
        },
    }
    store.agents[:] = [deepcopy(stale_agent)]
    persistence_service.persist_agent_state(agent=stale_agent)

    response = client.get("/api/agents", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    listed_agent = next(item for item in payload["items"] if item["id"] == "stale-bound-tool-agent")
    assert listed_agent["boundToolIds"] == ["tool-a"]
    assert listed_agent["boundTools"][0]["id"] == "tool-a"
    assert listed_agent["boundTools"][0]["type"] == "unavailable"
    assert any(
        "以下 Tool 已失效或当前租户不可见：tool-a" == warning
        for warning in listed_agent["configSummary"]["warnings"]
    )


def test_agent_management_list_excludes_task_child_agents_by_default(auth_headers_factory) -> None:
    headers = auth_headers_factory(role="admin", user_id="tenant-admin-agent-list")
    _set_user_scope("tenant-admin-agent-list", "tenant-alpha")

    base_agent = {
        "id": "general-agent",
        "name": "General Agent",
        "description": "control plane agent",
        "type": "default",
        "status": "idle",
        "enabled": True,
        "tasks_completed": 0,
        "tasks_total": 0,
        "avg_response_time": "--",
        "tokens_used": 0,
        "tokens_limit": 0,
        "success_rate": 100.0,
        "last_active": "未运行",
    }
    task_child_agent = {
        "id": "task-child-agent",
        "name": "Task Child Agent",
        "description": "generated by requirement dispatch",
        "type": "default",
        "status": "idle",
        "enabled": True,
        "tasks_completed": 0,
        "tasks_total": 0,
        "avg_response_time": "--",
        "tokens_used": 0,
        "tokens_limit": 0,
        "success_rate": 100.0,
        "last_active": "未运行",
        "config_snapshot": {
            "status": "generated",
            "agent": {
                "agent_id": "task-child-agent",
                "name": "Task Child Agent",
                "type": "default",
                "metadata": {
                    "source": "requirement_dispatch_agent",
                    "task_id": "task-001",
                    "group_id": "reqgrp-task-001",
                    "group_role": "frontend",
                },
            },
        },
    }
    store.agents[:] = [deepcopy(base_agent), deepcopy(task_child_agent)]
    persistence_service.persist_agent_state(agent=base_agent)
    persistence_service.persist_agent_state(agent=task_child_agent)

    response = client.get("/api/agents", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["items"]] == ["general-agent"]

    debug_response = client.get("/api/agents?include_task_child_agents=true", headers=headers)

    assert debug_response.status_code == 200
    debug_payload = debug_response.json()
    assert {item["id"] for item in debug_payload["items"]} == {"general-agent", "task-child-agent"}
