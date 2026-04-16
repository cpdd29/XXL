import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.services import agent_service, workflow_execution_service
from app.config import get_settings
from app.services.external_agent_registry_service import external_agent_registry_service
from app.services.external_skill_registry_service import external_skill_registry_service
from app.services.skill_registry_service import skill_registry_service
from app.services.store import store
from app.services.tool_source_service import ToolSourceService


client = TestClient(app)


@pytest.fixture(autouse=True)
def _force_secure_external_shared_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        get_settings(),
        "external_connection_shared_secret",
        "workbot-external-secret-test",
    )


def _external_headers() -> dict[str, str]:
    return {"X-WorkBot-External-Token": get_settings().external_connection_shared_secret}


def _external_signature_headers(
    payload: dict[str, object],
    *,
    timestamp: datetime | None = None,
    secret: str | None = None,
) -> dict[str, str]:
    effective_timestamp = (timestamp or datetime.now(UTC)).replace(microsecond=0)
    timestamp_text = effective_timestamp.isoformat()
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    signing_secret = secret or get_settings().external_connection_shared_secret
    signature = hmac.new(
        signing_secret.encode("utf-8"),
        f"{timestamp_text}.{body}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {
        "X-WorkBot-External-Timestamp": timestamp_text,
        "X-WorkBot-External-Signature": signature,
    }


def test_external_skill_registry_syncs_to_skill_registry_and_tool_sources() -> None:
    external_skill_registry_service.register_skill(
        {
            "id": "ext-skill-web-search",
            "name": "External Web Search",
            "description": "外接搜索 Skill",
            "version": "1.2.3",
            "capabilities": ["web_search", "fact_checking"],
            "tags": ["external", "search"],
            "base_url": "https://skills.example.com",
            "invoke_path": "/invoke/search",
            "health_path": "/healthz",
            "method": "POST",
        }
    )

    ability = skill_registry_service.get_ability("ext-skill-web-search")
    assert ability is not None
    assert ability["enabled"] is True
    assert ability["metadata"]["registry"]["origin"] == "external_skill_registry"
    assert ability["metadata"]["registry"]["version"] == "1.2.3"
    assert store.audit_logs[0]["action"] == "external_skill_registry.registered"

    source_service = ToolSourceService(include_internal_skills=False)
    sources = source_service.list_sources(refresh=True)
    tools = source_service.list_tools(refresh=True)

    external_source = next(item for item in sources["items"] if item["id"] == "external-skill-registry")
    external_tool = next(item for item in tools if item["source"] == "external-skill-registry")

    assert external_source["kind"] == "external_skill_registry"
    assert external_source.get("toolCount", external_source.get("tool_count")) == 1
    assert external_tool["name"] == "External Web Search"
    config_summary = external_tool.get("configSummary", external_tool.get("config_summary"))
    assert config_summary["version"] == "1.2.3"
    assert config_summary["invocation"]["invoke_path"] == "/invoke/search"


def test_external_agent_registry_participates_in_agent_listing_and_routing() -> None:
    external_agent_registry_service.register_agent(
        {
            "id": "external-search-agent",
            "name": "External Search Agent",
            "description": "外接搜索 Agent",
            "type": "search",
            "version": "2.0.0",
            "capabilities": ["web_search"],
            "base_url": "https://agents.example.com",
            "invoke_path": "/execute",
        }
    )

    payload = agent_service.list_agents()
    external_agent = next(item for item in payload["items"] if item["id"] == "external-search-agent")
    assert external_agent["config_summary"]["source"] == "external_agent_registry"
    assert external_agent["runtime_status"] == "online"
    assert external_agent["routable"] is True
    assert store.audit_logs[0]["action"] == "external_agent_registry.registered"

    selected = workflow_execution_service.resolve_direct_execution_agent("search")
    assert selected is not None
    assert selected["id"] == "external-search-agent"


def test_external_agent_registry_prunes_expired_agent_and_removes_routability() -> None:
    now = datetime.now(UTC)
    external_agent_registry_service.register_agent(
        {
            "id": "external-write-agent",
            "name": "External Write Agent",
            "type": "write",
            "heartbeat_timeout_seconds": 30,
            "last_heartbeat_at": (now - timedelta(seconds=120)).isoformat(),
            "lease_expires_at": (now - timedelta(seconds=30)).isoformat(),
        }
    )

    pruned = external_agent_registry_service.prune_expired(now=now)
    item = external_agent_registry_service.get_agent("external-write-agent")

    assert pruned == 1
    assert item is not None
    assert item["runtime_status"] == "offline"
    assert item["routable"] is False


def test_external_agent_registry_failure_prune_recover_heartbeat_closure() -> None:
    settings = get_settings()
    external_agent_registry_service.register_agent(
        {
            "id": "external-agent-recover-flow",
            "name": "External Recover Agent",
            "agent_family": "external_recover_agent_family",
            "type": "search",
            "version": "1.0.0",
            "release_channel": "stable",
            "default_version": True,
            "compatibility": ["brain-core-v1"],
            "capabilities": ["web_search"],
            "base_url": "https://agents.example.com",
        }
    )

    opened = None
    for _ in range(max(1, int(settings.external_connection_circuit_breaker_threshold))):
        opened = external_agent_registry_service.report_failure(
            "external-agent-recover-flow",
            error="timeout",
        )
    assert opened is not None
    assert opened["circuit_state"] == "open"
    assert opened["routable"] is False

    open_until = datetime.fromisoformat(str(opened["circuit_open_until"]))
    external_agent_registry_service.prune_expired(now=open_until + timedelta(seconds=1))
    half_open = external_agent_registry_service.get_agent("external-agent-recover-flow")
    assert half_open is not None
    assert half_open["circuit_state"] == "half_open"
    assert half_open["routable"] is True

    recovered = external_agent_registry_service.recover_agent("external-agent-recover-flow")
    assert recovered["circuit_state"] == "closed"
    assert recovered["runtime_status"] == "online"
    assert recovered["routable"] is True
    assert recovered["consecutive_failures"] == 0

    heartbeat = external_agent_registry_service.report_heartbeat(
        "external-agent-recover-flow",
        status="online",
        load=0.1,
        queue_depth=0,
        metadata={"probe": "post-recover"},
    )
    assert heartbeat["runtime_status"] == "online"
    assert heartbeat["circuit_state"] == "closed"
    assert heartbeat["routable"] is True
    assert heartbeat["lease_expires_at"] is not None


def test_external_agent_registry_prefers_default_stable_compatible_version_for_routing() -> None:
    external_agent_registry_service.register_agent(
        {
            "id": "search-agent-beta",
            "name": "External Search Agent",
            "agent_family": "external_search_agent",
            "type": "search",
            "version": "1.9.0",
            "release_channel": "beta",
            "compatibility": ["brain-core-v1"],
            "capabilities": ["web_search"],
            "base_url": "https://agents.example.com",
        }
    )
    external_agent_registry_service.register_agent(
        {
            "id": "search-agent-stable",
            "name": "External Search Agent",
            "agent_family": "external_search_agent",
            "type": "search",
            "version": "1.8.0",
            "release_channel": "stable",
            "default_version": True,
            "compatibility": ["brain-core-v1"],
            "capabilities": ["web_search"],
            "base_url": "https://agents.example.com",
        }
    )
    external_agent_registry_service.register_agent(
        {
            "id": "search-agent-v2-incompatible",
            "name": "External Search Agent",
            "agent_family": "external_search_agent",
            "type": "search",
            "version": "2.0.0",
            "release_channel": "stable",
            "compatibility": ["brain-core-v2"],
            "capabilities": ["web_search"],
            "base_url": "https://agents.example.com",
        }
    )

    selected = workflow_execution_service.resolve_direct_execution_agent("search")

    assert selected is not None
    assert selected["id"] == "search-agent-stable"


def test_external_agent_registry_supports_canary_rollout_and_rollback() -> None:
    external_agent_registry_service.register_agent(
        {
            "id": "search-agent-stable-v1",
            "name": "External Search Agent",
            "agent_family": "external_search_agent_gray",
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
            "id": "search-agent-canary-v2",
            "name": "External Search Agent",
            "agent_family": "external_search_agent_gray",
            "type": "search",
            "version": "2.0.0",
            "release_channel": "canary",
            "compatibility": ["brain-core-v1"],
            "capabilities": ["web_search"],
            "base_url": "https://agents.example.com",
            "rollout_policy": {
                "canary_percent": 100,
                "route_key": "task",
            },
        }
    )

    canary = workflow_execution_service.resolve_direct_execution_agent(
        "search",
        route_seed="task-100",
    )
    assert canary is not None
    assert canary["id"] == "search-agent-canary-v2"

    external_agent_registry_service.set_rollout_policy(
        "search-agent-canary-v2",
        {"canary_percent": 0, "route_key": "task"},
    )
    stable = workflow_execution_service.resolve_direct_execution_agent(
        "search",
        route_seed="task-100",
    )
    assert stable is not None
    assert stable["id"] == "search-agent-stable-v1"

    external_agent_registry_service.set_rollback_policy(
        "search-agent-canary-v2",
        {
            "active": True,
            "target_version_id": "search-agent-stable-v1",
        },
    )
    rollback_selected = workflow_execution_service.resolve_direct_execution_agent(
        "search",
        route_seed="task-200",
    )
    assert rollback_selected is not None
    assert rollback_selected["id"] == "search-agent-stable-v1"


def test_external_skill_registry_selects_latest_compatible_non_deprecated_skill() -> None:
    external_skill_registry_service.register_skill(
        {
            "id": "ext-skill-search-old",
            "name": "External Search Skill",
            "skill_family": "external_search_skill",
            "version": "1.0.0",
            "release_channel": "stable",
            "compatibility": ["brain-core-v1"],
            "capabilities": ["web_search"],
            "base_url": "https://skills.example.com",
        }
    )
    external_skill_registry_service.register_skill(
        {
            "id": "ext-skill-search-deprecated",
            "name": "External Search Skill",
            "skill_family": "external_search_skill",
            "version": "1.1.0",
            "release_channel": "deprecated",
            "deprecated": True,
            "compatibility": ["brain-core-v1"],
            "capabilities": ["web_search"],
            "base_url": "https://skills.example.com",
        }
    )
    external_skill_registry_service.register_skill(
        {
            "id": "ext-skill-search-default",
            "name": "External Search Skill",
            "skill_family": "external_search_skill",
            "version": "1.2.0",
            "release_channel": "stable",
            "default_version": True,
            "compatibility": ["brain-core-v1"],
            "capabilities": ["web_search", "fact_checking"],
            "base_url": "https://skills.example.com",
        }
    )

    selected = external_skill_registry_service.select_skill(required_capabilities=["web_search"])
    ranked = skill_registry_service.query_by_capabilities(["web_search"], ability_type="skill", enabled=True)

    assert selected is not None
    assert selected["id"] == "ext-skill-search-default"
    synced = next(item for item in ranked if item["id"] == "ext-skill-search-default")
    assert synced["metadata"]["registry"]["version"] == "1.2.0"
    assert synced["metadata"]["registry"]["deprecated"] is False


def test_external_skill_registry_failure_prune_recover_heartbeat_closure() -> None:
    settings = get_settings()
    external_skill_registry_service.register_skill(
        {
            "id": "external-skill-recover-flow",
            "name": "External Recover Skill",
            "skill_family": "external_recover_skill_family",
            "version": "1.0.0",
            "release_channel": "stable",
            "default_version": True,
            "compatibility": ["brain-core-v1"],
            "capabilities": ["web_search"],
            "base_url": "https://skills.example.com",
        }
    )

    opened = None
    for _ in range(max(1, int(settings.external_connection_circuit_breaker_threshold))):
        opened = external_skill_registry_service.report_failure(
            "external-skill-recover-flow",
            error="gateway timeout",
        )
    assert opened is not None
    assert opened["circuit_state"] == "open"
    assert opened["routable"] is False

    open_until = datetime.fromisoformat(str(opened["circuit_open_until"]))
    lease_expires_at = datetime.fromisoformat(str(opened["lease_expires_at"]))
    probe_time = max(open_until, lease_expires_at) + timedelta(seconds=1)
    external_skill_registry_service.prune_expired(now=probe_time)
    half_open = external_skill_registry_service.get_skill("external-skill-recover-flow")
    assert half_open is not None
    assert half_open["circuit_state"] == "half_open"

    recovered = external_skill_registry_service.recover_skill("external-skill-recover-flow")
    assert recovered["circuit_state"] == "closed"
    assert recovered["health_status"] == "healthy"
    assert recovered["routable"] is True
    assert recovered["consecutive_failures"] == 0

    heartbeat = external_skill_registry_service.report_heartbeat(
        "external-skill-recover-flow",
        status="healthy",
        metadata={"probe": "post-recover"},
    )
    assert heartbeat["health_status"] == "healthy"
    assert heartbeat["circuit_state"] == "closed"
    assert heartbeat["routable"] is True
    assert heartbeat["lease_expires_at"] is not None


def test_external_skill_registry_supports_canary_rollout_and_rollback_selection() -> None:
    external_skill_registry_service.register_skill(
        {
            "id": "skill-stable-v1",
            "name": "External Search Skill",
            "skill_family": "external_search_skill_gray",
            "version": "1.0.0",
            "release_channel": "stable",
            "default_version": True,
            "compatibility": ["brain-core-v1"],
            "capabilities": ["web_search"],
            "base_url": "https://skills.example.com",
        }
    )
    external_skill_registry_service.register_skill(
        {
            "id": "skill-canary-v2",
            "name": "External Search Skill",
            "skill_family": "external_search_skill_gray",
            "version": "2.0.0",
            "release_channel": "canary",
            "compatibility": ["brain-core-v1"],
            "capabilities": ["web_search"],
            "base_url": "https://skills.example.com",
            "rollout_policy": {
                "canary_percent": 100,
                "route_key": "task",
            },
        }
    )

    canary = external_skill_registry_service.select_skill(
        required_capabilities=["web_search"],
        route_seed="task-100",
    )
    assert canary is not None
    assert canary["id"] == "skill-canary-v2"

    external_skill_registry_service.set_rollout_policy(
        "skill-canary-v2",
        {"canary_percent": 0, "route_key": "task"},
    )
    stable = external_skill_registry_service.select_skill(
        required_capabilities=["web_search"],
        route_seed="task-100",
    )
    assert stable is not None
    assert stable["id"] == "skill-stable-v1"

    external_skill_registry_service.set_rollout_policy(
        "skill-canary-v2",
        {"canary_percent": 100, "route_key": "task"},
    )
    external_skill_registry_service.set_rollback_policy(
        "skill-canary-v2",
        {
            "active": True,
            "target_version_id": "skill-stable-v1",
        },
    )
    rollback_selected = external_skill_registry_service.select_skill(
        required_capabilities=["web_search"],
        route_seed="task-200",
    )
    assert rollback_selected is not None
    assert rollback_selected["id"] == "skill-stable-v1"


def test_external_registries_expose_explicit_fallback_versions() -> None:
    external_agent_registry_service.register_agent(
        {
            "id": "writer-agent-fallback",
            "name": "External Write Agent",
            "agent_family": "external_write_agent",
            "type": "write",
            "version": "1.0.0",
            "release_channel": "stable",
            "compatibility": ["brain-core-v1"],
            "capabilities": ["drafting"],
            "base_url": "https://agents.example.com",
        }
    )
    external_agent_registry_service.register_agent(
        {
            "id": "writer-agent-primary",
            "name": "External Write Agent",
            "agent_family": "external_write_agent",
            "type": "write",
            "version": "1.1.0",
            "release_channel": "stable",
            "fallback_version_id": "writer-agent-fallback",
            "compatibility": ["brain-core-v1"],
            "capabilities": ["drafting"],
            "base_url": "https://agents.example.com",
        }
    )
    external_skill_registry_service.register_skill(
        {
            "id": "writer-skill-fallback",
            "name": "External Writer Skill",
            "skill_family": "external_writer_skill",
            "version": "1.0.0",
            "release_channel": "stable",
            "compatibility": ["brain-core-v1"],
            "capabilities": ["drafting"],
            "base_url": "https://skills.example.com",
        }
    )
    external_skill_registry_service.register_skill(
        {
            "id": "writer-skill-primary",
            "name": "External Writer Skill",
            "skill_family": "external_writer_skill",
            "version": "1.1.0",
            "release_channel": "stable",
            "fallback_version_id": "writer-skill-fallback",
            "compatibility": ["brain-core-v1"],
            "capabilities": ["drafting"],
            "base_url": "https://skills.example.com",
        }
    )

    fallback_agent = external_agent_registry_service.resolve_fallback_version("writer-agent-primary")
    fallback_skill = external_skill_registry_service.resolve_fallback_version("writer-skill-primary")

    assert fallback_agent is not None
    assert fallback_agent["id"] == "writer-agent-fallback"
    assert fallback_skill is not None
    assert fallback_skill["id"] == "writer-skill-fallback"


def test_external_registry_version_governance_enforces_single_default_and_same_family_fallback() -> None:
    external_agent_registry_service.register_agent(
        {
            "id": "agent-family-a-v1",
            "name": "Agent Family A",
            "agent_family": "family_a",
            "type": "search",
            "version": "1.0.0",
            "default_version": True,
            "compatibility": ["brain-core-v1"],
        }
    )
    external_agent_registry_service.register_agent(
        {
            "id": "agent-family-a-v2",
            "name": "Agent Family A",
            "agent_family": "family_a",
            "type": "search",
            "version": "2.0.0",
            "default_version": True,
            "compatibility": ["brain-core-v1"],
        }
    )

    versions = external_agent_registry_service.list_versions("family_a")
    assert [item["id"] for item in versions[:2]] == ["agent-family-a-v2", "agent-family-a-v1"]
    assert versions[0]["default_version"] is True
    assert versions[1]["default_version"] is False

    external_skill_registry_service.register_skill(
        {
            "id": "skill-family-a-v1",
            "name": "Skill Family A",
            "skill_family": "skill_family_a",
            "version": "1.0.0",
            "compatibility": ["brain-core-v1"],
        }
    )
    external_skill_registry_service.register_skill(
        {
            "id": "skill-family-b-v1",
            "name": "Skill Family B",
            "skill_family": "skill_family_b",
            "version": "1.0.0",
            "compatibility": ["brain-core-v1"],
        }
    )

    try:
        external_skill_registry_service.set_fallback_version("skill-family-a-v1", "skill-family-b-v1")
    except ValueError as exc:
        assert "same family" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("cross-family fallback should be rejected")


def test_external_connection_routes_register_and_heartbeat(auth_headers_factory) -> None:
    register_agent = client.post(
        "/api/external-connections/agents/register",
        headers=_external_headers(),
        json={
            "id": "route-agent-1",
            "name": "Route Agent",
            "type": "search",
            "version": "1.0.0",
            "baseUrl": "https://agent.example.test",
            "invokePath": "/execute",
        },
    )
    register_skill = client.post(
        "/api/external-connections/skills/register",
        headers=_external_headers(),
        json={
            "id": "route-skill-1",
            "name": "Route Skill",
            "version": "1.0.0",
            "capabilities": ["web_search"],
            "baseUrl": "https://skill.example.test",
            "invokePath": "/invoke",
        },
    )
    heartbeat = client.post(
        "/api/external-connections/agents/route-agent-1/heartbeat",
        headers=_external_headers(),
        json={"status": "online", "load": 0.2, "queueDepth": 1},
    )
    health = client.get(
        "/api/external-connections/health",
        headers=auth_headers_factory(role="operator"),
    )

    assert register_agent.status_code == 200
    assert register_skill.status_code == 200
    assert heartbeat.status_code == 200
    assert heartbeat.json()["item"]["runtime_status"] == "online"
    assert health.status_code == 200
    assert health.json()["summary"]["routable"] >= 2
    assert any(item["id"] == "route-agent-1" for item in health.json()["items"])
    assert any(item["id"] == "route-skill-1" for item in health.json()["items"])


def test_external_connection_version_management_routes(auth_headers_factory) -> None:
    operator_headers = auth_headers_factory(role="operator")
    external_agent_registry_service.register_agent(
        {
            "id": "route-agent-v1",
            "name": "Route Agent",
            "agent_family": "route_agent_family",
            "type": "search",
            "version": "1.0.0",
            "compatibility": ["brain-core-v1"],
            "default_version": True,
        }
    )
    external_agent_registry_service.register_agent(
        {
            "id": "route-agent-v2",
            "name": "Route Agent",
            "agent_family": "route_agent_family",
            "type": "search",
            "version": "2.0.0",
            "compatibility": ["brain-core-v1"],
        }
    )
    external_skill_registry_service.register_skill(
        {
            "id": "route-skill-v1",
            "name": "Route Skill",
            "skill_family": "route_skill_family",
            "version": "1.0.0",
            "compatibility": ["brain-core-v1"],
            "default_version": True,
            "capabilities": ["web_search"],
        }
    )
    external_skill_registry_service.register_skill(
        {
            "id": "route-skill-v2",
            "name": "Route Skill",
            "skill_family": "route_skill_family",
            "version": "2.0.0",
            "compatibility": ["brain-core-v1"],
            "capabilities": ["web_search"],
        }
    )

    list_agents = client.get(
        "/api/external-connections/agents/families/route_agent_family/versions",
        headers=operator_headers,
    )
    promote_agent = client.post(
        "/api/external-connections/agents/route-agent-v2/promote",
        headers=operator_headers,
    )
    set_agent_fallback = client.post(
        "/api/external-connections/agents/route-agent-v2/set-fallback",
        headers=operator_headers,
        json={"fallbackVersionId": "route-agent-v1"},
    )
    set_agent_rollout = client.post(
        "/api/external-connections/agents/route-agent-v2/rollout-policy",
        headers=operator_headers,
        json={"rolloutPolicy": {"canaryPercent": 25, "routeKey": "tenant"}},
    )
    set_agent_rollback = client.post(
        "/api/external-connections/agents/route-agent-v2/rollback",
        headers=operator_headers,
        json={"rollbackPolicy": {"active": True, "targetVersionId": "route-agent-v1"}},
    )
    deprecate_skill = client.post(
        "/api/external-connections/skills/route-skill-v1/deprecate",
        headers=operator_headers,
        json={"deprecated": True},
    )
    promote_skill = client.post(
        "/api/external-connections/skills/route-skill-v2/promote",
        headers=operator_headers,
    )
    set_skill_rollout = client.post(
        "/api/external-connections/skills/route-skill-v2/rollout-policy",
        headers=operator_headers,
        json={"rolloutPolicy": {"canaryPercent": 10, "routeKey": "chat"}},
    )
    set_skill_rollback = client.post(
        "/api/external-connections/skills/route-skill-v2/rollback",
        headers=operator_headers,
        json={"rollbackPolicy": {"active": True, "targetVersionId": "route-skill-v1"}},
    )
    updated_list_agents = client.get(
        "/api/external-connections/agents/families/route_agent_family/versions",
        headers=operator_headers,
    )
    list_skills = client.get(
        "/api/external-connections/skills/families/route_skill_family/versions",
        headers=operator_headers,
    )

    assert list_agents.status_code == 200
    assert list_agents.json()["total"] == 2
    assert list_agents.json()["items"][0]["capabilityType"] == "agent"
    assert promote_agent.status_code == 200
    assert promote_agent.json()["item"]["default_version"] is True
    assert set_agent_fallback.status_code == 200
    assert set_agent_fallback.json()["item"]["fallback_version_id"] == "route-agent-v1"
    assert set_agent_rollout.status_code == 200
    assert set_agent_rollout.json()["item"]["rollout_policy"]["canary_percent"] == 25
    assert set_agent_rollback.status_code == 200
    assert set_agent_rollback.json()["item"]["rollback_policy"]["active"] is True
    assert deprecate_skill.status_code == 200
    assert deprecate_skill.json()["item"]["deprecated"] is True
    assert deprecate_skill.json()["item"]["routable"] is False
    assert promote_skill.status_code == 200
    assert set_skill_rollout.status_code == 200
    assert set_skill_rollout.json()["item"]["rollout_policy"]["canary_percent"] == 10
    assert set_skill_rollback.status_code == 200
    assert set_skill_rollback.json()["item"]["rollback_policy"]["active"] is True
    assert updated_list_agents.status_code == 200
    assert list_skills.status_code == 200
    assert list_skills.json()["items"][0]["id"] == "route-skill-v2"
    assert updated_list_agents.json()["items"][0]["rolloutPolicy"]["canaryPercent"] == 25
    assert updated_list_agents.json()["items"][0]["rollbackPolicy"]["active"] is True
    assert list_skills.json()["items"][0]["rolloutPolicy"]["canaryPercent"] == 10
    assert list_skills.json()["items"][0]["rollbackPolicy"]["active"] is True


def test_external_connection_routes_require_auth_for_registration() -> None:
    response = client.post(
        "/api/external-connections/agents/register",
        json={
            "id": "unauthorized-agent",
            "name": "Unauthorized Agent",
            "type": "search",
        },
    )

    assert response.status_code == 401


def test_external_connection_registration_accepts_valid_signature_headers() -> None:
    payload = {
        "id": "sig-agent-valid",
        "name": "Signature Valid Agent",
        "type": "search",
        "version": "1.0.0",
        "base_url": "https://agent.example.test",
        "invoke_path": "/execute",
        "metadata": {"nonce": "nonce-sig-valid"},
    }
    response = client.post(
        "/api/external-connections/agents/register",
        headers=_external_signature_headers(payload),
        json=payload,
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["item"]["id"] == "sig-agent-valid"


def test_external_connection_registration_accepts_valid_external_token_only() -> None:
    payload = {
        "id": "token-agent-valid",
        "name": "Token Valid Agent",
        "type": "search",
        "version": "1.0.0",
        "baseUrl": "https://agent.example.test",
        "invokePath": "/execute",
    }
    response = client.post(
        "/api/external-connections/agents/register",
        headers=_external_headers(),
        json=payload,
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["item"]["id"] == "token-agent-valid"


def test_external_connection_registration_rejects_expired_signature() -> None:
    payload = {
        "id": "sig-agent-expired",
        "name": "Signature Expired Agent",
        "type": "search",
        "version": "1.0.0",
        "base_url": "https://agent.example.test",
        "invoke_path": "/execute",
        "metadata": {"nonce": "nonce-sig-expired"},
    }
    ttl = max(10, int(get_settings().external_connection_signature_ttl_seconds))
    expired_at = datetime.now(UTC) - timedelta(seconds=ttl + 30)
    response = client.post(
        "/api/external-connections/agents/register",
        headers=_external_signature_headers(payload, timestamp=expired_at),
        json=payload,
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "External connection signature expired"


def test_external_connection_registration_rejects_invalid_signature() -> None:
    payload = {
        "id": "sig-agent-invalid",
        "name": "Signature Invalid Agent",
        "type": "search",
        "version": "1.0.0",
        "base_url": "https://agent.example.test",
        "invoke_path": "/execute",
        "metadata": {"nonce": "nonce-sig-invalid"},
    }
    headers = _external_signature_headers(payload)
    headers["X-WorkBot-External-Signature"] = "deadbeef" * 8
    response = client.post(
        "/api/external-connections/agents/register",
        headers=headers,
        json=payload,
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "External connection signature invalid"


def test_external_connection_registration_rejects_invalid_timestamp_format() -> None:
    payload = {
        "id": "sig-agent-bad-ts",
        "name": "Signature Bad Timestamp Agent",
        "type": "search",
        "version": "1.0.0",
        "base_url": "https://agent.example.test",
        "invoke_path": "/execute",
        "metadata": {"nonce": "nonce-sig-bad-ts"},
    }
    response = client.post(
        "/api/external-connections/agents/register",
        headers={
            "X-WorkBot-External-Timestamp": "not-an-iso-timestamp",
            "X-WorkBot-External-Signature": "deadbeef" * 8,
        },
        json=payload,
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "External connection auth required"


def test_external_connection_registration_rejects_same_nonce_replay() -> None:
    payload = {
        "id": "sig-agent-replay",
        "name": "Signature Replay Agent",
        "type": "search",
        "version": "1.0.0",
        "base_url": "https://agent.example.test",
        "invoke_path": "/execute",
        "metadata": {"nonce": "nonce-replay-fixed"},
    }
    headers = _external_signature_headers(payload)

    first = client.post(
        "/api/external-connections/agents/register",
        headers=headers,
        json=payload,
    )
    replay = client.post(
        "/api/external-connections/agents/register",
        headers=headers,
        json=payload,
    )

    assert first.status_code == 200
    assert replay.status_code == 401
    assert replay.json()["detail"] == "External connection nonce replayed"


def test_external_connection_failure_reporting_opens_circuit(auth_headers_factory) -> None:
    external_agent_registry_service.register_agent(
        {
            "id": "failing-agent-1",
            "name": "Failing Agent",
            "type": "write",
            "base_url": "https://agent.example.test",
        }
    )
    headers = auth_headers_factory(role="operator", email="external.ops@example.test")
    for _ in range(get_settings().external_connection_circuit_breaker_threshold):
        failure_response = client.post(
            "/api/external-connections/agents/failing-agent-1/failures",
            headers=headers,
            json={"error": "connection refused"},
        )
        assert failure_response.status_code == 200

    health = client.get("/api/external-connections/health", headers=headers)
    item = next(entry for entry in health.json()["items"] if entry["id"] == "failing-agent-1")

    assert item["circuitState"] == "open"
    assert item["routable"] is False
    assert item["consecutiveFailures"] >= get_settings().external_connection_circuit_breaker_threshold
