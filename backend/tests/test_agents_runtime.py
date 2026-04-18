from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.services import agent_service
from app.services import workflow_execution_service
from app.services.brain_skill_service import BrainSkillService
from app.services.skill_registry_service import skill_registry_service
from app.services.store import store


client = TestClient(app)


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


def test_create_agent_route_sets_enabled_project_model_binding(auth_headers, monkeypatch) -> None:
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
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["agent"]["modelBinding"]["providerKey"] == "openai"
    assert payload["agent"]["modelBinding"]["model"] == "gpt-5.4"
    assert payload["agent"]["name"] == "客服写作 Agent"


def test_update_agent_config_route_updates_selected_model_binding(auth_headers, monkeypatch) -> None:
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


def test_update_agent_config_route_persists_bound_skill_ids(auth_headers, monkeypatch) -> None:
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
