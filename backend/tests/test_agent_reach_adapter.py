from __future__ import annotations

from pathlib import Path
import json

from app.services.tool_catalog_adapters.agent_reach_adapter import AgentReachAdapter


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _seed_external_project(root: Path) -> None:
    _write_text(
        root / "config" / "mcporter.json",
        json.dumps(
            {
                "mcpServers": {
                    "exa": {"baseUrl": "https://mcp.exa.ai/mcp"},
                    "crm": {"baseUrl": "http://localhost:18060/mcp"},
                },
                "imports": [],
            }
        ),
    )
    _write_text(
        root / "agent_reach" / "cli.py",
        "def main():\n    return 0\n",
    )
    _write_text(
        root / "agent_reach" / "channels" / "__init__.py",
        "from .github import GitHubChannel\nfrom .twitter import TwitterChannel\n",
    )


def test_agent_reach_adapter_scan_exposes_bridge_and_tool_details(tmp_path: Path) -> None:
    _seed_external_project(tmp_path)
    adapter = AgentReachAdapter()

    source, tools = adapter.scan(
        source_id="agent-reach-external",
        source_name="Agent Reach External",
        source_path=tmp_path,
    )

    assert source["status"] == "available"
    assert source["bridge_summary"]["catalog_bridge"] is True
    assert source["bridge_summary"]["doctor_bridge"] is True
    assert source["bridge_summary"]["runtime_bridge"] is True
    assert source["doctor_summary"]["channel_count"] == 2
    names = {item["name"] for item in tools}
    assert "exa" in names
    assert "agent-reach doctor" in names
    assert "agent-reach skill" in names
    assert "agent-reach runtime bridge" in names

    exa = next(item for item in tools if item["name"] == "exa")
    assert exa["permissions"]["requires_permission"] is False
    assert "query" in exa["input_schema"]["properties"]
    assert "items" in exa["output_schema"]["properties"]
    assert exa["health_summary"]["status"] in {"healthy", "degraded", "unknown"}


def test_agent_reach_adapter_scan_handles_missing_source() -> None:
    adapter = AgentReachAdapter()
    missing_path = Path("/tmp/not-exists-agent-reach-source")

    source, tools = adapter.scan(
        source_id="missing-source",
        source_name="Missing",
        source_path=missing_path,
    )

    assert source["status"] == "unavailable"
    assert source["scan_status"] == "failed"
    assert source["bridge_summary"]["runtime_bridge"] is False
    assert tools == []
