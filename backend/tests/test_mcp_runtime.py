from __future__ import annotations

from pathlib import Path
import json
from typing import Any

from app.services.mcp_runtime_service import MCPRuntimeService
from app.services import mcp_runtime_service as mcp_runtime_module
from app.services.tool_source_service import ToolSourceService


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_source_service(tmp_path: Path) -> tuple[ToolSourceService, Path, Path]:
    agents_root = tmp_path / "agents"
    external_root = tmp_path / "external"

    _write_text(
        agents_root / "1" / "tools.yaml",
        """
tools:
  - name: crm_reader
    provider: custom
    command: custom-crm
    timeout: 9
""".strip(),
    )
    _write_text(
        external_root / "config" / "mcporter.json",
        json.dumps(
            {
                "mcpServers": {
                    "exa": {"baseUrl": "https://mcp.exa.ai/mcp"},
                },
                "imports": [],
            }
        ),
    )
    source_service = ToolSourceService(agent_tools_root=agents_root, external_source_path=external_root)
    return source_service, agents_root, external_root


def _build_source_service_without_external(tmp_path: Path) -> tuple[ToolSourceService, Path]:
    agents_root = tmp_path / "agents"
    _write_text(
        agents_root / "1" / "tools.yaml",
        """
tools:
  - name: crm_reader
    provider: custom
    command: custom-crm
""".strip(),
    )
    source_service = ToolSourceService(agent_tools_root=agents_root, external_source_path=None)
    return source_service, agents_root


def _external_mcp_registry_payload_with_search_tool(base_url: str) -> str:
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


def _external_mcp_registry_payload_with_execute_tool(base_url: str, *, tool_id: str, tool_name: str) -> str:
    return json.dumps(
        {
            "sources": [
                {
                    "id": "registered-mcp",
                    "name": "Registered MCP",
                    "kind": "mcp_registry",
                    "tools": [
                        {
                            "id": tool_id,
                            "name": tool_name,
                            "base_url": base_url,
                            "invoke_path": "/execute",
                            "method": "POST",
                            "config_summary": {
                                "request_mode": "execute_tool_payload",
                                "tool_alias": tool_name,
                            },
                        }
                    ],
                }
            ]
        }
    )


class _CustomClient:
    def health(self, *, tool, runtime_config):  # noqa: ANN001
        return {
            "status": "healthy",
            "reason": "custom_client_ready",
            "checked_at": "2026-04-10T00:00:00+00:00",
            "runtime": {"provider": runtime_config["provider"]},
        }

    def invoke(self, *, tool, payload, runtime_config, trace_context=None):  # noqa: ANN001
        return {
            "ok": True,
            "bridge_mode": "custom",
            "output": {
                "tool_id": tool["id"],
                "payload": payload,
                "runtime_provider": runtime_config["provider"],
            },
            "meta": {"trace_context": trace_context or {}},
        }


class _FakeResponse:
    def __init__(self, *, status_code: int, payload: dict[str, Any] | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeHTTPClient:
    def __init__(self, *, timeout: float) -> None:
        self.timeout = timeout

    def __enter__(self):  # noqa: ANN204
        return self

    def __exit__(self, exc_type, exc, tb):  # noqa: ANN001, ANN204
        return False

    def request(self, method: str, url: str, json: dict[str, Any] | None = None):  # noqa: A002
        return _FakeResponse(
            status_code=200,
            payload={
                "method": method,
                "url": url,
                "echo": json or {},
            },
        )

    def get(self, url: str, params: dict[str, Any] | None = None):
        return _FakeResponse(status_code=200, payload={"url": url, "params": params or {}})


def test_mcp_runtime_builds_tool_mapping_with_alias(tmp_path: Path) -> None:
    source_service, _, external_root = _build_source_service(tmp_path)
    runtime = MCPRuntimeService(source_service=source_service, config_root=external_root)

    mapping = runtime.build_tool_mapping(refresh=True)
    assert any(key.startswith("local-agent-1-crm-reader-custom") for key in mapping.keys())
    assert "local-agents:crm_reader" in mapping
    assert "agent-reach-external:exa" in mapping


def test_mcp_runtime_uses_registered_client_for_health_and_invoke(tmp_path: Path) -> None:
    source_service, _, external_root = _build_source_service(tmp_path)
    runtime = MCPRuntimeService(source_service=source_service, config_root=external_root)
    runtime.register_client("custom", _CustomClient())

    local_tool = next(item for item in source_service.list_tools(refresh=True) if item["name"] == "crm_reader")
    health = runtime.health_for_tool(local_tool)
    call = runtime.invoke_tool(tool_id=local_tool["id"], payload={"order": "A100"})

    assert health["status"] == "healthy"
    assert call["ok"] is True
    assert call["result"]["bridge_mode"] == "custom"
    assert call["result"]["output"]["payload"]["order"] == "A100"


def test_mcp_runtime_invocation_records_trace_and_recent_summary(tmp_path: Path) -> None:
    source_service, _, external_root = _build_source_service(tmp_path)
    runtime = MCPRuntimeService(source_service=source_service, config_root=external_root)
    runtime.register_client("custom", _CustomClient())

    local_tool = next(item for item in source_service.list_tools(refresh=True) if item["name"] == "crm_reader")
    runtime.invoke_tool(tool_id=local_tool["id"], payload={"month": "10"})
    runtime.invoke_tool(tool_id=local_tool["id"], payload={"month": "11"})

    traces = runtime.list_traces()
    summary = runtime.recent_call_summary(local_tool["id"])

    assert len(traces) == 2
    assert summary["total_calls"] == 2
    assert summary["success_calls"] == 2
    assert summary["last_status"] == "success"


def test_mcp_runtime_shadow_invocation_records_shadow_summary(tmp_path: Path) -> None:
    source_service, _, external_root = _build_source_service(tmp_path)
    runtime = MCPRuntimeService(source_service=source_service, config_root=external_root)
    runtime.register_client("custom", _CustomClient())

    local_tool = next(item for item in source_service.list_tools(refresh=True) if item["name"] == "crm_reader")
    runtime.invoke_shadow_tool(tool_id=local_tool["id"], payload={"month": "10"})
    shadow = runtime.recent_shadow_summary(local_tool["id"])

    assert shadow["shadow_total_calls"] == 1
    assert shadow["shadow_success_calls"] == 1
    assert shadow["shadow_last_status"] == "success"


def test_mcp_runtime_returns_error_payload_for_unknown_tool(tmp_path: Path) -> None:
    source_service, _, external_root = _build_source_service(tmp_path)
    runtime = MCPRuntimeService(source_service=source_service, config_root=external_root)

    result = runtime.invoke_tool(tool_id="missing-tool", payload={"x": 1})

    assert result["ok"] is False
    assert result["error"]["type"] == "LookupError"
    traces = runtime.list_traces()
    assert traces[0]["status"] == "failed"


def test_mcp_runtime_http_client_invocation_for_local_mcp_tool(monkeypatch, tmp_path: Path) -> None:
    source_service, _, external_root = _build_source_service(tmp_path)
    runtime = MCPRuntimeService(source_service=source_service, config_root=external_root)
    monkeypatch.setattr(mcp_runtime_module.httpx, "Client", _FakeHTTPClient)

    result = runtime.invoke_tool(tool_id="mcp-tool-web-search", payload={"query": "workflow"})

    assert result["ok"] is True
    assert result["result"]["bridge_mode"] == "http"
    assert result["result"]["output"]["method"] == "POST"
    assert result["result"]["output"]["echo"]["payload"]["query"] == "workflow"
    assert "http://127.0.0.1:8093/search" in result["result"]["output"]["url"]


def test_mcp_runtime_http_retry_and_circuit_breaker(monkeypatch, tmp_path: Path) -> None:
    source_service, _, external_root = _build_source_service(tmp_path)
    runtime = MCPRuntimeService(source_service=source_service, config_root=external_root)

    class _FailingHTTPClient(_FakeHTTPClient):
        def request(self, method: str, url: str, json: dict[str, Any] | None = None):  # noqa: A002, ARG002
            raise RuntimeError("network_down")

    monkeypatch.setattr(mcp_runtime_module.httpx, "Client", _FailingHTTPClient)

    first = runtime.invoke_tool(tool_id="mcp-tool-web-search", payload={"query": "a"})
    second = runtime.invoke_tool(tool_id="mcp-tool-web-search", payload={"query": "b"})
    third = runtime.invoke_tool(tool_id="mcp-tool-web-search", payload={"query": "c"})
    fourth = runtime.invoke_tool(tool_id="mcp-tool-web-search", payload={"query": "d"})

    assert first["ok"] is False
    assert second["ok"] is False
    assert third["ok"] is False
    assert fourth["ok"] is False
    assert "circuit_open" in str((fourth.get("error") or {}).get("message") or "")


def test_mcp_runtime_list_servers_and_health_work_without_local_config(tmp_path: Path) -> None:
    source_service, _ = _build_source_service_without_external(tmp_path)
    runtime = MCPRuntimeService(source_service=source_service, config_root=None)

    loaded = runtime.load_config()
    servers = runtime.list_servers()
    summary = runtime.health_summary()

    assert loaded == {}
    assert any(item["id"] == "mcp-tool-web-search" for item in servers)
    assert summary["total"] >= 1
    assert summary["counts"]["healthy"] + summary["counts"]["degraded"] + summary["counts"]["unknown"] == summary["total"]


def test_mcp_runtime_invoke_works_without_local_config(monkeypatch, tmp_path: Path) -> None:
    source_service, _ = _build_source_service_without_external(tmp_path)
    runtime = MCPRuntimeService(source_service=source_service, config_root=None)
    monkeypatch.setattr(mcp_runtime_module.httpx, "Client", _FakeHTTPClient)

    health = runtime.list_health(refresh=True)
    result = runtime.invoke_tool(tool_id="mcp-tool-web-search", payload={"query": "workflow"})

    assert any(item["tool_id"] == "mcp-tool-web-search" for item in health["items"])
    assert result["ok"] is True
    assert result["result"]["bridge_mode"] == "http"
    assert result["result"]["output"]["echo"]["payload"]["query"] == "workflow"


def test_mcp_runtime_invokes_external_registry_mcp_tool_and_keeps_tool_id(
    monkeypatch,
    tmp_path: Path,
) -> None:
    source_service, _ = _build_source_service_without_external(tmp_path)
    monkeypatch.setenv("WORKBOT_TOOL_SOURCES_MODE", "external_only")
    monkeypatch.setenv(
        "WORKBOT_EXTERNAL_TOOL_SOURCES_JSON",
        _external_mcp_registry_payload_with_search_tool("https://mcp.runtime.external.local"),
    )
    runtime = MCPRuntimeService(source_service=source_service, config_root=None)
    monkeypatch.setattr(mcp_runtime_module.httpx, "Client", _FakeHTTPClient)

    mapping = runtime.build_tool_mapping(refresh=True)
    assert "mcp-tool-web-search" in mapping
    assert "registered-mcp:web_search" in mapping

    result = runtime.invoke_tool(tool_id="mcp-tool-web-search", payload={"query": "workflow"})
    assert result["ok"] is True
    assert result["tool"]["id"] == "mcp-tool-web-search"
    assert result["result"]["bridge_mode"] == "http"
    assert result["result"]["output"]["echo"]["tool_id"] == "mcp-tool-web-search"
    assert result["result"]["output"]["url"] == "https://mcp.runtime.external.local/search"

    traces = runtime.list_traces()
    assert traces
    assert traces[0]["tool_id"] == "mcp-tool-web-search"


def test_mcp_runtime_execute_tool_payload_mode_for_external_registry_tool(
    monkeypatch,
    tmp_path: Path,
) -> None:
    source_service, _ = _build_source_service_without_external(tmp_path)
    monkeypatch.setenv("WORKBOT_TOOL_SOURCES_MODE", "external_only")
    monkeypatch.setenv(
        "WORKBOT_EXTERNAL_TOOL_SOURCES_JSON",
        _external_mcp_registry_payload_with_execute_tool(
            "https://mcp.runtime.external.local",
            tool_id="mcp-tool-weather-lookup",
            tool_name="weather_lookup",
        ),
    )
    runtime = MCPRuntimeService(source_service=source_service, config_root=None)
    monkeypatch.setattr(mcp_runtime_module.httpx, "Client", _FakeHTTPClient)

    result = runtime.invoke_tool(tool_id="mcp-tool-weather-lookup", payload={"location": "Guangzhou"})
    assert result["ok"] is True
    assert result["result"]["output"]["url"] == "https://mcp.runtime.external.local/execute"
    assert result["result"]["output"]["echo"]["tool"] == "weather_lookup"
    assert result["result"]["output"]["echo"]["payload"]["location"] == "Guangzhou"
