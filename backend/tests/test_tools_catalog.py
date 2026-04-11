from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.routes import tool_sources as tool_sources_route
from app.api.routes import tools as tools_route
from app.main import app
from app.services.tool_catalog_service import ToolCatalogService
from app.services.tool_source_service import ToolSourceService


client = TestClient(app)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _mount_test_tool_services(tmp_path: Path, monkeypatch) -> None:
    agents_root = tmp_path / "agents"
    external_root = tmp_path / "agent-reach"

    _write_text(
        agents_root / "1" / "tools.yaml",
        """
tools:
  - name: web_search
    provider: tavily
    timeout: 10
""".strip(),
    )
    _write_text(
        agents_root / "3" / "tools.yaml",
        """
tools:
  - name: web_search
    provider: tavily
    timeout: 8
  - name: pdf_reader
    provider: local_pdf
    enabled: false
""".strip(),
    )
    _write_text(
        external_root / "config" / "mcporter.json",
        json.dumps(
            {
                "mcpServers": {
                    "exa": {"baseUrl": "https://mcp.exa.ai/mcp"},
                    "xiaohongshu": {"baseUrl": "http://localhost:18060/mcp"},
                },
                "imports": [],
            }
        ),
    )

    source_service = ToolSourceService(
        agent_tools_root=agents_root,
        external_source_path=external_root,
    )
    catalog_service = ToolCatalogService(source_service=source_service)

    monkeypatch.setattr(tools_route, "tool_catalog_service", catalog_service)
    monkeypatch.setattr(tool_sources_route, "tool_source_service", source_service)


def test_list_tools_returns_unified_catalog(auth_headers, monkeypatch, tmp_path: Path) -> None:
    _mount_test_tool_services(tmp_path, monkeypatch)

    response = client.get("/api/tools", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 8

    required_keys = {
        "id",
        "name",
        "type",
        "source",
        "enabled",
        "description",
        "tags",
        "provider",
        "healthStatus",
        "agentIds",
        "configSummary",
        "healthSummary",
        "recentCallSummary",
    }
    assert required_keys.issubset(set(payload["items"][0].keys()))

    local_web_search = next(
        item
        for item in payload["items"]
        if item["source"] == "local-agents" and item["name"] == "web_search"
    )
    assert local_web_search["provider"] == "tavily"
    assert local_web_search["agentIds"] == ["1", "3"]
    assert local_web_search["configSummary"]["instances"] == 2

    external_exa = next(
        item
        for item in payload["items"]
        if item["source"] == "agent-reach-external" and item["name"] == "exa"
    )
    assert external_exa["type"] == "mcp"
    assert external_exa["configSummary"]["baseUrl"] == "https://mcp.exa.ai/mcp"


def test_get_tool_by_id_and_missing_tool(auth_headers, monkeypatch, tmp_path: Path) -> None:
    _mount_test_tool_services(tmp_path, monkeypatch)

    list_response = client.get("/api/tools", headers=auth_headers)
    tool_id = list_response.json()["items"][0]["id"]

    response = client.get(f"/api/tools/{tool_id}", headers=auth_headers)
    missing_response = client.get("/api/tools/not-exist-tool", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["id"] == tool_id
    assert missing_response.status_code == 404
    assert missing_response.json()["detail"] == "Tool not found"


def test_tool_sources_list_and_scan(auth_headers, monkeypatch, tmp_path: Path) -> None:
    _mount_test_tool_services(tmp_path, monkeypatch)

    response = client.get("/api/tool-sources", headers=auth_headers)
    scan_response = client.post("/api/tool-sources/scan", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert {"mode", "local_agent_enabled", "local_mcp_enabled", "external_enabled", "has_legacy_fallback"}.issubset(
        set(payload["governanceSummary"].keys())
    )

    mcp_source = next(item for item in payload["items"] if item["id"] == "local-mcp-services")
    local_source = next(item for item in payload["items"] if item["id"] == "local-agents")
    external_source = next(item for item in payload["items"] if item["id"] == "agent-reach-external")

    assert mcp_source["kind"] == "mcp_server"
    assert mcp_source["scanStatus"] == "success"
    assert mcp_source["toolCount"] >= 6
    assert mcp_source["configSummary"]["source_mode"] == "local_only_or_manual_fallback"
    assert local_source["kind"] == "local_agents"
    assert local_source["scanStatus"] == "success"
    assert local_source["toolCount"] == 3
    assert local_source["name"] == "Legacy Local Agents Fallback"
    assert local_source["configSummary"]["source_mode"] == "local_only_or_manual_fallback"
    assert external_source["kind"] == "external_repo"
    assert external_source["scanStatus"] == "success"
    assert external_source["toolCount"] == 2

    assert scan_response.status_code == 200
    scan_payload = scan_response.json()
    assert scan_payload["total"] == 3
    assert {"mode", "local_agent_enabled", "local_mcp_enabled", "external_enabled", "has_legacy_fallback"}.issubset(
        set(scan_payload["governanceSummary"].keys())
    )


def test_tool_sources_scan_requires_agents_reload_permission(
    viewer_auth_headers: dict[str, str],
    monkeypatch,
    tmp_path: Path,
) -> None:
    _mount_test_tool_services(tmp_path, monkeypatch)

    response = client.post("/api/tool-sources/scan", headers=viewer_auth_headers)

    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied"
