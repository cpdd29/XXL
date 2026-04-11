from __future__ import annotations

from pathlib import Path
from urllib.parse import quote
import json

from fastapi.testclient import TestClient

from app.main import app
from app.services import tool_catalog_service as tool_catalog_module
from app.services import tool_source_service as tool_source_module


client = TestClient(app)


def _seed_agent_reach_project(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "agent_reach").mkdir(parents=True, exist_ok=True)
    (root / "config" / "mcporter.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "exa": {"baseUrl": "https://mcp.exa.ai/mcp"},
                    "xiaohongshu": {"baseUrl": "http://localhost:18060/mcp"},
                },
                "imports": [],
            }
        ),
        encoding="utf-8",
    )
    (root / "agent_reach" / "cli.py").write_text(
        "def main():\n    return 0\n",
        encoding="utf-8",
    )


def _external_registry_payload(external_root: Path) -> str:
    return json.dumps(
        {
            "sources": [
                {
                    "id": "registered-agent-reach",
                    "name": "Registered Agent Reach",
                    "kind": "external_repo",
                    "path": str(external_root),
                },
                {
                    "id": "registered-mcp",
                    "name": "Registered MCP",
                    "kind": "mcp_registry",
                    "tools": [
                        {
                            "id": "mcp-tool-registry-search",
                            "name": "registry_search",
                            "base_url": "https://mcp.registry.local",
                            "invoke_path": "/search",
                            "method": "POST",
                            "permissions": {
                                "requires_permission": False,
                                "scopes": ["agents:read"],
                                "roles": ["admin", "operator", "power_user", "viewer"],
                            },
                        }
                    ],
                },
            ]
        }
    )


def _external_registry_payload_with_skill(external_root: Path) -> str:
    return json.dumps(
        {
            "sources": [
                {
                    "id": "registered-agent-reach",
                    "name": "Registered Agent Reach",
                    "kind": "external_repo",
                    "path": str(external_root),
                },
                {
                    "id": "registered-mcp",
                    "name": "Registered MCP",
                    "kind": "mcp_registry",
                    "tools": [
                        {
                            "id": "mcp-tool-registry-search",
                            "name": "registry_search",
                            "base_url": "https://mcp.registry.local",
                            "invoke_path": "/search",
                            "method": "POST",
                        }
                    ],
                },
            ],
            "tools": [
                {
                    "id": "skill-tool-external-skill-router",
                    "name": "external_skill_router",
                    "type": "skill",
                    "source": "registered-agent-reach",
                    "source_kind": "external_repo",
                    "provider": "external-registry",
                    "bridge_mode": "runtime_bridge",
                    "config_summary": {
                        "endpoint": "https://skills.example.com/router/invoke",
                        "timeout_seconds": 20,
                    },
                }
            ],
        }
    )


def test_tool_catalog_service_lists_local_and_external_tools(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed_agent_reach_project(tmp_path)
    monkeypatch.setenv("WORKBOT_TOOL_SOURCES_MODE", "hybrid")
    monkeypatch.delenv("WORKBOT_EXTERNAL_TOOL_SOURCES_JSON", raising=False)
    monkeypatch.setattr(tool_source_module, "DEFAULT_EXTERNAL_AGENT_REACH_PATH", tmp_path)
    tool_source_module.tool_source_service._external_source_path = tmp_path

    payload = tool_catalog_module.tool_catalog_service.list_tools(refresh=True)

    assert payload["total"] >= 6
    names = {item["name"] for item in payload["items"]}
    assert "web_search" in names
    assert "exa" in names
    assert "agent-reach doctor" in names
    exa = next(item for item in payload["items"] if item["name"] == "exa")
    assert "source_kind" in exa
    assert "bridge_mode" in exa
    assert "migration_stage" in exa
    assert "rollback" in exa
    assert "traffic_policy" in exa
    assert "runtime_summary" in exa
    assert exa["runtime_summary"]["provider"] in {"mcporter", "unknown"}


def test_tools_route_returns_catalog_and_tool_detail(
    tmp_path: Path,
    monkeypatch,
    auth_headers,
) -> None:
    _seed_agent_reach_project(tmp_path)
    monkeypatch.setenv("WORKBOT_TOOL_SOURCES_MODE", "hybrid")
    monkeypatch.delenv("WORKBOT_EXTERNAL_TOOL_SOURCES_JSON", raising=False)
    monkeypatch.setattr(tool_source_module, "DEFAULT_EXTERNAL_AGENT_REACH_PATH", tmp_path)
    tool_source_module.tool_source_service._external_source_path = tmp_path

    list_response = client.get("/api/tools?refresh=true", headers=auth_headers)
    assert list_response.status_code == 200
    body = list_response.json()
    assert body["total"] >= 1
    assert isinstance(body["items"], list)

    tool_id = next(item["id"] for item in body["items"] if item["name"] == "exa")
    detail_response = client.get(f"/api/tools/{quote(tool_id, safe='')}", headers=auth_headers)
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["id"] == tool_id
    assert detail["type"] == "mcp"


def test_tool_sources_scan_route_reports_local_and_external_sources(
    tmp_path: Path,
    monkeypatch,
    auth_headers,
) -> None:
    _seed_agent_reach_project(tmp_path)
    monkeypatch.setenv("WORKBOT_TOOL_SOURCES_MODE", "hybrid")
    monkeypatch.delenv("WORKBOT_EXTERNAL_TOOL_SOURCES_JSON", raising=False)
    monkeypatch.setattr(tool_source_module, "DEFAULT_EXTERNAL_AGENT_REACH_PATH", tmp_path)
    tool_source_module.tool_source_service._external_source_path = tmp_path

    response = client.post("/api/tool-sources/scan", headers=auth_headers)
    assert response.status_code == 200

    body = response.json()
    assert body["ok"] is True
    assert body["total"] == 3
    assert {"mode", "local_agent_enabled", "local_mcp_enabled", "external_enabled", "has_legacy_fallback"}.issubset(
        set(body["governanceSummary"].keys())
    )
    sources = {item["id"]: item for item in body["items"]}
    assert "local-mcp-services" in sources
    assert "local-agents" in sources
    assert "agent-reach-external" in sources
    assert sources["local-mcp-services"]["toolCount"] >= 6
    assert sources["local-agents"]["name"] == "Legacy Local Agents Fallback"
    assert sources["local-agents"]["registry"]["legacy_fallback"] is True
    assert sources["local-agents"]["configSummary"]["deprecated"] is True
    assert sources["agent-reach-external"]["toolCount"] >= 4


def test_tool_sources_scan_route_external_only_uses_external_registry(
    tmp_path: Path,
    monkeypatch,
    auth_headers,
) -> None:
    _seed_agent_reach_project(tmp_path)
    monkeypatch.setenv("WORKBOT_TOOL_SOURCES_MODE", "external_only")
    monkeypatch.setenv("WORKBOT_ENABLE_LOCAL_MCP_SOURCE", "true")
    monkeypatch.setenv("WORKBOT_ENABLE_LOCAL_AGENT_SOURCE", "true")
    monkeypatch.setenv("WORKBOT_EXTERNAL_TOOL_SOURCES_JSON", _external_registry_payload(tmp_path))
    tool_source_module.tool_source_service._external_source_path = tmp_path

    response = client.post("/api/tool-sources/scan", headers=auth_headers)
    assert response.status_code == 200

    body = response.json()
    source_ids = {item["id"] for item in body["items"]}
    assert source_ids == {"registered-agent-reach", "registered-mcp"}
    assert body["governanceSummary"]["mode"] == "external_only"
    assert body["governanceSummary"]["local_agent_enabled"] is False
    assert body["governanceSummary"]["local_mcp_enabled"] is False
    assert body["governanceSummary"]["external_enabled"] is True


def test_tool_catalog_service_external_registry_file_includes_skill_and_agent_reach_tools(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed_agent_reach_project(tmp_path)
    registry_file = tmp_path / "external-tool-sources.json"
    registry_file.write_text(
        _external_registry_payload_with_skill(tmp_path),
        encoding="utf-8",
    )
    monkeypatch.setenv("WORKBOT_TOOL_SOURCES_MODE", "external_only")
    monkeypatch.setenv("WORKBOT_EXTERNAL_TOOL_SOURCES_FILE", str(registry_file))
    monkeypatch.delenv("WORKBOT_EXTERNAL_TOOL_SOURCES_JSON", raising=False)
    monkeypatch.delenv("WORKBOT_TOOL_SOURCES_REGISTRY_JSON", raising=False)
    tool_source_module.tool_source_service._external_source_path = tmp_path

    payload = tool_catalog_module.tool_catalog_service.get_catalog(refresh=True)

    assert payload["total"] >= 7
    names = {item["name"] for item in payload["items"]}
    assert "exa" in names
    assert "agent-reach doctor" in names
    assert "registry_search" in names
    assert "external_skill_router" in names

    skill_tool = next(
        item
        for item in payload["items"]
        if item["name"] == "external_skill_router" and item["source"] == "registered-agent-reach"
    )
    assert skill_tool["type"] == "skill"
    assert skill_tool["source"] == "registered-agent-reach"
    assert skill_tool["source_kind"] == "external_repo"
    assert skill_tool["bridge_mode"] == "runtime_bridge"

    assert payload["source_summary"]["registered-agent-reach"] >= 6
    assert payload["source_summary"]["registered-mcp"] == 1
