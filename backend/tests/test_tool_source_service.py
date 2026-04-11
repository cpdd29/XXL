from __future__ import annotations

from pathlib import Path
import json

from fastapi.testclient import TestClient

from app.api.routes import tool_sources as tool_sources_route
from app.api.routes import tools as tools_route
from app.main import app
from app.services.mcp_runtime_service import MCPRuntimeService
from app.services.tool_catalog_service import ToolCatalogService
from app.services.tool_source_service import ToolSourceService


client = TestClient(app)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_source_service(tmp_path: Path) -> ToolSourceService:
    agents_root = tmp_path / "agents"
    external_root = tmp_path / "external"

    _write_text(
        agents_root / "7" / "tools.yaml",
        """
tools:
  - name: order_exporter
    provider: internal
    timeout: 5
""".strip(),
    )
    _write_text(
        external_root / "config" / "mcporter.json",
        json.dumps(
            {
                "mcpServers": {
                    "crm": {"baseUrl": "https://mcp.crm.local/mcp"},
                },
                "imports": [],
            }
        ),
    )
    _write_text(
        external_root / "agent_reach" / "cli.py",
        "def main():\n    return 0\n",
    )
    _write_text(
        external_root / "agent_reach" / "channels" / "__init__.py",
        "from .github import GitHubChannel\nfrom .twitter import TwitterChannel\n",
    )

    return ToolSourceService(agent_tools_root=agents_root, external_source_path=external_root)


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
                            "id": "mcp-tool-external-order-query",
                            "name": "external_order_query",
                            "base_url": "https://mcp.external.local",
                            "invoke_path": "/query",
                            "method": "POST",
                            "permissions": {
                                "requires_permission": True,
                                "scopes": ["agents:read", "tasks:write"],
                                "roles": ["admin", "operator"],
                            },
                        }
                    ],
                },
            ]
        }
    )


def _external_mcp_registry_payload_with_local_tool_id(base_url: str) -> str:
    return json.dumps(
        {
            "sources": [
                {
                    "id": "registered-mcp",
                    "name": "Registered MCP",
                    "kind": "mcp_registry",
                    "tools": [
                        {
                            "id": "mcp-tool-web-search",
                            "name": "web_search",
                            "base_url": base_url,
                            "invoke_path": "/search",
                            "method": "POST",
                        }
                    ],
                }
            ]
        }
    )


def _top_level_tools_registry_payload() -> str:
    return json.dumps(
        {
            "sources": [
                {
                    "id": "external-agent-repo",
                    "name": "External Agent Repo",
                    "kind": "external_repo",
                }
            ],
            "tools": [
                {
                    "id": "skill-tool-rewrite-style",
                    "name": "rewrite_style_skill",
                    "type": "skill",
                    "source": "external-agent-repo",
                    "source_kind": "external_repo",
                    "provider": "agent-reach-cli",
                    "bridge_mode": "runtime_bridge",
                    "config_summary": {
                        "endpoint": "https://skill-gateway.example.com/skills/rewrite_style/invoke",
                        "timeout_seconds": 12,
                    },
                }
            ],
        }
    )


def _external_registry_file_payload_with_skill(external_root: Path) -> str:
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


def test_tool_source_service_scan_and_detail_include_bridge_fields(tmp_path: Path) -> None:
    service = _build_source_service(tmp_path)

    scan = service.scan_sources()
    listed = service.list_sources(refresh=False)
    detail = service.get_source("agent-reach-external")
    local_detail = service.get_source("local-agents")
    mcp_detail = service.get_source("local-mcp-services")

    assert scan["ok"] is True
    assert scan["total"] >= 3
    assert {"mode", "local_agent_enabled", "local_mcp_enabled", "external_enabled", "has_legacy_fallback"}.issubset(
        set(scan["governance_summary"].keys())
    )
    assert {"mode", "local_agent_enabled", "local_mcp_enabled", "external_enabled", "has_legacy_fallback"}.issubset(
        set(listed["governance_summary"].keys())
    )
    assert detail["bridge_summary"]["runtime_bridge"] is True
    assert detail["tool_total"] >= 2
    assert detail["health_summary"]["status"] in {"healthy", "degraded", "unknown"}
    assert {"mode", "local_agent_enabled", "local_mcp_enabled", "external_enabled", "has_legacy_fallback"}.issubset(
        set(detail["governance_summary"].keys())
    )
    assert local_detail["registry"]["legacy_fallback"] is True
    assert local_detail["registry"]["activation_mode"] == "local_only_or_manual_fallback"
    assert local_detail["config_summary"]["deprecated"] is True
    assert mcp_detail["kind"] == "mcp_server"
    assert mcp_detail["tool_total"] >= 6


def test_tool_source_service_tool_entries_include_io_permission_and_health(tmp_path: Path) -> None:
    service = _build_source_service(tmp_path)

    tools = service.list_tools(refresh=True)
    sample = next(item for item in tools if item["source"] == "agent-reach-external")

    assert "permissions" in sample
    assert "input_schema" in sample
    assert "output_schema" in sample
    assert "recent_call_summary" in sample
    assert "health_summary" in sample
    assert "migration_stage" in sample
    assert "rollback" in sample
    assert "traffic_policy" in sample
    assert sample["migration_stage"]["stage"] in {"externalized", "bridge_in_progress", "retained_in_core"}


def test_tool_source_detail_route_returns_source_payload(auth_headers, monkeypatch, tmp_path: Path) -> None:
    service = _build_source_service(tmp_path)
    monkeypatch.setattr(tool_sources_route, "tool_source_service", service)

    response = client.get("/api/tool-sources/agent-reach-external?refresh=true", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "agent-reach-external"
    assert payload["toolTotal"] >= 2
    assert isinstance(payload["tools"], list)


def test_tool_source_detail_route_returns_404_for_missing_source(
    auth_headers,
    monkeypatch,
    tmp_path: Path,
) -> None:
    service = _build_source_service(tmp_path)
    monkeypatch.setattr(tool_sources_route, "tool_source_service", service)

    response = client.get("/api/tool-sources/not-exist", headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Tool source not found"


def test_tools_catalog_and_health_routes(auth_headers, monkeypatch, tmp_path: Path) -> None:
    service = _build_source_service(tmp_path)
    runtime = MCPRuntimeService(source_service=service, config_root=tmp_path / "external")
    catalog_service = ToolCatalogService(source_service=service, runtime_service=runtime)
    monkeypatch.setattr(tool_sources_route, "tool_source_service", service)
    monkeypatch.setattr(tools_route, "tool_catalog_service", catalog_service)

    catalog_response = client.get("/api/tools/catalog?refresh=true", headers=auth_headers)
    health_response = client.get("/api/tools/health?refresh=true", headers=auth_headers)

    assert catalog_response.status_code == 200
    catalog_payload = catalog_response.json()
    assert catalog_payload["total"] >= 6
    assert "sourceSummary" in catalog_payload
    assert "typeSummary" in catalog_payload
    assert "sources" in catalog_payload

    assert health_response.status_code == 200
    health_payload = health_response.json()
    assert "items" in health_payload
    assert "summary" in health_payload


def test_tool_source_scan_returns_source_migration_and_traffic_summaries(tmp_path: Path) -> None:
    service = _build_source_service(tmp_path)
    payload = service.scan_sources()
    source = next(item for item in payload["items"] if item["id"] == "agent-reach-external")
    mcp_source = next(item for item in payload["items"] if item["id"] == "local-mcp-services")

    assert "migration_summary" in source
    assert "traffic_policy" in source
    assert "rollback" in source
    assert source["migration_summary"]["total"] >= 1
    assert mcp_source["migration_summary"]["total"] >= 6


def test_tool_source_service_external_only_prefers_external_registry(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = _build_source_service(tmp_path)
    monkeypatch.setenv("WORKBOT_TOOL_SOURCES_MODE", "external_only")
    monkeypatch.setenv("WORKBOT_ENABLE_LOCAL_MCP_SOURCE", "true")
    monkeypatch.setenv("WORKBOT_ENABLE_LOCAL_AGENT_SOURCE", "true")
    monkeypatch.setenv(
        "WORKBOT_EXTERNAL_TOOL_SOURCES_JSON",
        _external_registry_payload(tmp_path / "external"),
    )

    payload = service.scan_sources()
    source_ids = {item["id"] for item in payload["items"]}

    assert source_ids == {"registered-agent-reach", "registered-mcp"}
    assert "local-mcp-services" not in source_ids
    assert "local-agents" not in source_ids
    registered_agent_reach = next(item for item in payload["items"] if item["id"] == "registered-agent-reach")
    registered_mcp = next(item for item in payload["items"] if item["id"] == "registered-mcp")
    assert registered_agent_reach["origin"] == "external_registry"
    assert registered_mcp["config_summary"]["registration_kind"] == "mcp_registry"


def test_tool_source_service_local_only_keeps_local_sources(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = _build_source_service(tmp_path)
    monkeypatch.setenv("WORKBOT_TOOL_SOURCES_MODE", "local_only")
    monkeypatch.setenv(
        "WORKBOT_EXTERNAL_TOOL_SOURCES_JSON",
        _external_registry_payload(tmp_path / "external"),
    )

    payload = service.scan_sources()
    source_ids = {item["id"] for item in payload["items"]}

    assert "local-mcp-services" in source_ids
    assert "local-agents" in source_ids
    assert "agent-reach-external" not in source_ids
    assert "registered-agent-reach" not in source_ids


def test_tool_source_service_supports_top_level_registry_tools(monkeypatch, tmp_path: Path) -> None:
    service = _build_source_service(tmp_path)
    monkeypatch.setenv("WORKBOT_TOOL_SOURCES_MODE", "external_only")
    monkeypatch.setenv(
        "WORKBOT_EXTERNAL_TOOL_SOURCES_JSON",
        _top_level_tools_registry_payload(),
    )

    payload = service.scan_sources()
    source_ids = {item["id"] for item in payload["items"]}
    assert source_ids == {"external-agent-repo"}
    tools = service.list_tools(refresh=False)
    rewrite_tool = next(item for item in tools if item["id"] == "skill-tool-rewrite-style")
    assert rewrite_tool["type"] == "skill"
    assert rewrite_tool["source"] == "external-agent-repo"
    assert rewrite_tool["source_kind"] == "external_repo"
    assert rewrite_tool["config_summary"]["registration_kind"] == "external_repo"


def test_tool_source_service_external_registry_file_includes_skill_and_agent_reach_tools(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = _build_source_service(tmp_path)
    registry_file = tmp_path / "external-tool-sources.json"
    _write_text(
        registry_file,
        _external_registry_file_payload_with_skill(tmp_path / "external"),
    )
    monkeypatch.setenv("WORKBOT_TOOL_SOURCES_MODE", "external_only")
    monkeypatch.setenv("WORKBOT_EXTERNAL_TOOL_SOURCES_FILE", str(registry_file))
    monkeypatch.delenv("WORKBOT_EXTERNAL_TOOL_SOURCES_JSON", raising=False)
    monkeypatch.delenv("WORKBOT_TOOL_SOURCES_REGISTRY_JSON", raising=False)

    payload = service.scan_sources()
    source_ids = {item["id"] for item in payload["items"]}
    assert source_ids == {"registered-agent-reach", "registered-mcp"}

    tools = service.list_tools(refresh=False)
    tool_names = {item["name"] for item in tools}
    assert "crm" in tool_names
    assert "agent-reach doctor" in tool_names
    assert "external_skill_router" in tool_names
    skill_tool = next(item for item in tools if item["id"] == "skill-tool-external-skill-router")
    assert skill_tool["type"] == "skill"
    assert skill_tool["source"] == "registered-agent-reach"
    assert skill_tool["source_kind"] == "external_repo"
    assert skill_tool["config_summary"]["registration_kind"] == "external_repo"

    source_detail = service.get_source("registered-agent-reach")
    assert source_detail["origin"] == "external_registry"
    assert source_detail["tool_total"] >= 5
    assert any(item["type"] == "skill" for item in source_detail["tools"])


def test_tool_source_service_external_registry_mcp_tools_replace_local_mcp_services(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = _build_source_service(tmp_path)
    monkeypatch.setenv("WORKBOT_TOOL_SOURCES_MODE", "external_only")
    monkeypatch.setenv("WORKBOT_ENABLE_LOCAL_MCP_SOURCE", "true")
    monkeypatch.setenv(
        "WORKBOT_EXTERNAL_TOOL_SOURCES_JSON",
        _external_mcp_registry_payload_with_local_tool_id("https://mcp.registry.replace.local"),
    )

    payload = service.scan_sources()
    source_ids = {item["id"] for item in payload["items"]}
    assert source_ids == {"registered-mcp"}
    assert "local-mcp-services" not in source_ids

    tools = service.list_tools(refresh=False)
    assert len(tools) == 1
    registry_web_search = tools[0]
    assert registry_web_search["id"] == "mcp-tool-web-search"
    assert registry_web_search["source"] == "registered-mcp"
    assert registry_web_search["source_kind"] == "mcp_server"
    assert registry_web_search["config_summary"]["base_url"] == "https://mcp.registry.replace.local"


def test_tool_source_service_resolves_base_url_env_placeholder_for_external_registry(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = _build_source_service(tmp_path)
    monkeypatch.setenv("WORKBOT_TOOL_SOURCES_MODE", "external_only")
    monkeypatch.setenv("WORKBOT_PLACEHOLDER_SEARCH_MCP_BASE_URL", "https://mcp.env-resolved.local")
    monkeypatch.setenv(
        "WORKBOT_EXTERNAL_TOOL_SOURCES_JSON",
        _external_mcp_registry_payload_with_local_tool_id(
            "${WORKBOT_PLACEHOLDER_SEARCH_MCP_BASE_URL:-https://mcp.default.local}"
        ),
    )

    service.scan_sources()
    registry_web_search = next(item for item in service.list_tools(refresh=False) if item["id"] == "mcp-tool-web-search")
    assert registry_web_search["config_summary"]["base_url"] == "https://mcp.env-resolved.local"
    assert registry_web_search["config_summary"]["baseUrl"] == "https://mcp.env-resolved.local"
