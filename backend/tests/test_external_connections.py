from fastapi.testclient import TestClient

from app.main import app
from app.config import get_settings
from app.services.external_agent_registry_service import external_agent_registry_service
from app.services.external_skill_registry_service import external_skill_registry_service


client = TestClient(app)


def test_external_governance_overview_returns_family_summaries_and_recent_audits(
    auth_headers: dict[str, str],
) -> None:
    external_agent_registry_service.register_agent(
        {
            "id": "search-agent-stable-v1",
            "name": "External Search Agent",
            "agent_family": "external_search_agent",
            "type": "search",
            "version": "1.0.0",
            "release_channel": "stable",
            "default_version": True,
            "compatibility": ["brain-core-v1"],
            "capabilities": ["web_search"],
            "base_url": "https://agents.example.com",
        }
    )
    external_skill_registry_service.register_skill(
        {
            "id": "search-skill-stable-v1",
            "name": "External Search Skill",
            "skill_family": "external_search_skill",
            "version": "1.0.0",
            "release_channel": "stable",
            "default_version": True,
            "compatibility": ["brain-core-v1"],
            "capabilities": ["web_search"],
            "base_url": "https://skills.example.com",
        }
    )

    response = client.get("/api/external-connections/governance", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["agentFamilies"] == 1
    assert payload["summary"]["skillFamilies"] == 1
    assert payload["summary"]["totalFamilies"] == 2
    assert payload["summary"]["totalVersions"] == 2
    assert len(payload["items"]) == 2
    agent_item = next(item for item in payload["items"] if item["capabilityType"] == "agent")
    skill_item = next(item for item in payload["items"] if item["capabilityType"] == "skill")
    assert agent_item["family"] == "external_search_agent"
    assert agent_item["currentVersion"] == "1.0.0"
    assert agent_item["defaultVersionId"] == "search-agent-stable-v1"
    assert skill_item["family"] == "external_search_skill"
    assert skill_item["currentVersion"] == "1.0.0"
    assert skill_item["defaultVersionId"] == "search-skill-stable-v1"
    assert any(audit["resource"] == "external_agent_registry" for audit in payload["recentAudits"])
    assert any(audit["resource"] == "external_skill_registry" for audit in payload["recentAudits"])


def test_external_governance_overview_requires_external_read_permission(
    auth_headers_factory,
) -> None:
    response = client.get(
        "/api/external-connections/governance",
        headers=auth_headers_factory(role="power_user"),
    )

    assert response.status_code == 403


def test_external_recover_routes_close_open_circuits(
    auth_headers_factory,
) -> None:
    settings = get_settings()
    operator_headers = auth_headers_factory(role="operator")
    external_agent_registry_service.register_agent(
        {
            "id": "recover-route-agent",
            "name": "Recover Route Agent",
            "agent_family": "recover_route_agent_family",
            "type": "search",
            "version": "1.0.0",
            "compatibility": ["brain-core-v1"],
            "base_url": "https://agents.example.com",
        }
    )
    external_skill_registry_service.register_skill(
        {
            "id": "recover-route-skill",
            "name": "Recover Route Skill",
            "skill_family": "recover_route_skill_family",
            "version": "1.0.0",
            "compatibility": ["brain-core-v1"],
            "capabilities": ["web_search"],
            "base_url": "https://skills.example.com",
        }
    )

    for _ in range(max(1, int(settings.external_connection_circuit_breaker_threshold))):
        agent_failure = client.post(
            "/api/external-connections/agents/recover-route-agent/failures",
            headers=operator_headers,
            json={"error": "timeout"},
        )
        skill_failure = client.post(
            "/api/external-connections/skills/recover-route-skill/failures",
            headers=operator_headers,
            json={"error": "timeout"},
        )
        assert agent_failure.status_code == 200
        assert skill_failure.status_code == 200

    recover_agent = client.post(
        "/api/external-connections/agents/recover-route-agent/recover",
        headers=operator_headers,
    )
    recover_skill = client.post(
        "/api/external-connections/skills/recover-route-skill/recover",
        headers=operator_headers,
    )

    assert recover_agent.status_code == 200
    assert recover_agent.json()["item"]["circuit_state"] == "closed"
    assert recover_agent.json()["item"]["runtime_status"] == "online"
    assert recover_agent.json()["item"]["routable"] is True
    assert recover_skill.status_code == 200
    assert recover_skill.json()["item"]["circuit_state"] == "closed"
    assert recover_skill.json()["item"]["health_status"] == "healthy"
    assert recover_skill.json()["item"]["routable"] is True
