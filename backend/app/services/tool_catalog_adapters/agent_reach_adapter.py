from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import json
import re


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _infer_health_status(*, enabled: bool, base_url: str | None = None, command: str | None = None) -> str:
    if not enabled:
        return "disabled"
    if base_url:
        return "healthy"
    if command:
        return "degraded"
    return "unknown"


def _parse_channel_names(channels_init_path: Path) -> list[str]:
    if not channels_init_path.exists() or not channels_init_path.is_file():
        return []
    try:
        content = channels_init_path.read_text(encoding="utf-8")
    except OSError:
        return []
    candidates = re.findall(r"from\s+\.(\w+)\s+import", content)
    channel_names = sorted(
        {
            item.strip()
            for item in candidates
            if item.strip() and item.strip() not in {"base", "__init__"}
        }
    )
    return channel_names


def _tool_permissions(*, requires_permission: bool, scopes: list[str], roles: list[str]) -> dict[str, Any]:
    return {
        "requires_permission": requires_permission,
        "scopes": scopes,
        "roles": roles,
        "approval_required": requires_permission,
    }


def list_agent_reach_tools(*, source_id: str, source_name: str, path: str | Path) -> list[dict[str, Any]]:
    root = Path(path)
    if not root.exists():
        return []

    items: list[dict[str, Any]] = []
    mcporter_config = _read_json(root / "config" / "mcporter.json") or {}
    mcp_servers = mcporter_config.get("mcpServers")
    if isinstance(mcp_servers, dict):
        for server_name, server_config in sorted(mcp_servers.items()):
            base_url = ""
            if isinstance(server_config, dict):
                base_url = str(server_config.get("baseUrl") or "").strip()
            enabled = bool(base_url)
            health_status = _infer_health_status(enabled=enabled, base_url=base_url)
            items.append(
                {
                    "id": f"{source_id}:mcp:{server_name}",
                    "name": server_name,
                    "type": "mcp",
                    "source": source_id,
                    "source_id": source_id,
                    "source_kind": "external_repo",
                    "enabled": enabled,
                    "description": f"{source_name} 暴露的 MCP Server：{server_name}",
                    "tags": ["external", "mcp", server_name],
                    "provider": "mcporter",
                    "bridge_mode": "runtime_bridge",
                    "health_status": health_status,
                    "agent_ids": [],
                    "permissions": _tool_permissions(
                        requires_permission=False,
                        scopes=["agents:read"],
                        roles=["admin", "operator", "power_user", "viewer"],
                    ),
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "params": {"type": "object"},
                        },
                        "required": ["query"],
                    },
                    "output_schema": {
                        "type": "object",
                        "properties": {
                            "items": {"type": "array"},
                            "raw": {"type": "object"},
                        },
                    },
                    "recent_call_summary": {
                        "total_calls": 0,
                        "success_calls": 0,
                        "failed_calls": 0,
                        "last_called_at": None,
                        "last_status": "never_called",
                        "last_error": None,
                    },
                    "health_summary": {
                        "status": health_status,
                        "checked_at": _utc_now_iso(),
                        "reason": "mcp_base_url_configured" if base_url else "missing_base_url",
                    },
                    "config_summary": {
                        "baseUrl": base_url or None,
                        "base_url": base_url or None,
                        "importsCount": len(mcporter_config.get("imports") or []),
                        "imports_count": len(mcporter_config.get("imports") or []),
                    },
                }
            )

    cli_path = root / "agent_reach" / "cli.py"
    if cli_path.exists():
        items.extend(
            [
                {
                    "id": f"{source_id}:tool:doctor",
                    "name": "agent-reach doctor",
                    "type": "bridge",
                    "source": source_id,
                    "source_id": source_id,
                    "source_kind": "external_repo",
                    "enabled": True,
                    "description": "外部能力健康检查入口，可用于诊断平台可用性。",
                    "tags": ["external", "diagnostics", "doctor"],
                    "provider": "agent-reach-cli",
                    "bridge_mode": "doctor_bridge",
                    "health_status": _infer_health_status(enabled=True, command="agent-reach doctor"),
                    "agent_ids": [],
                    "permissions": _tool_permissions(
                        requires_permission=True,
                        scopes=["agents:reload", "agents:read"],
                        roles=["admin", "operator"],
                    ),
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "verbose": {"type": "boolean"},
                        },
                    },
                    "output_schema": {
                        "type": "object",
                        "properties": {
                            "status": {"type": "string"},
                            "report": {"type": "string"},
                        },
                    },
                    "recent_call_summary": {
                        "total_calls": 0,
                        "success_calls": 0,
                        "failed_calls": 0,
                        "last_called_at": None,
                        "last_status": "never_called",
                        "last_error": None,
                    },
                    "health_summary": {
                        "status": "degraded",
                        "checked_at": _utc_now_iso(),
                        "reason": "cli_bridge_requires_runtime_execution",
                    },
                    "config_summary": {
                        "command": "agent-reach doctor",
                    },
                },
                {
                    "id": f"{source_id}:tool:skill",
                    "name": "agent-reach skill",
                    "type": "bridge",
                    "source": source_id,
                    "source_id": source_id,
                    "source_kind": "external_repo",
                    "enabled": True,
                    "description": "外部 SKILL 安装与卸载入口，可用于桥接技能包。",
                    "tags": ["external", "skill-management"],
                    "provider": "agent-reach-cli",
                    "bridge_mode": "catalog_bridge",
                    "health_status": _infer_health_status(enabled=True, command="agent-reach skill"),
                    "agent_ids": [],
                    "permissions": _tool_permissions(
                        requires_permission=True,
                        scopes=["agents:reload"],
                        roles=["admin", "operator"],
                    ),
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ["install", "uninstall"]},
                            "target": {"type": "string"},
                        },
                        "required": ["action"],
                    },
                    "output_schema": {
                        "type": "object",
                        "properties": {
                            "ok": {"type": "boolean"},
                            "message": {"type": "string"},
                        },
                    },
                    "recent_call_summary": {
                        "total_calls": 0,
                        "success_calls": 0,
                        "failed_calls": 0,
                        "last_called_at": None,
                        "last_status": "never_called",
                        "last_error": None,
                    },
                    "health_summary": {
                        "status": "degraded",
                        "checked_at": _utc_now_iso(),
                        "reason": "cli_bridge_requires_runtime_execution",
                    },
                    "config_summary": {
                        "command": "agent-reach skill --install|--uninstall",
                    },
                },
                {
                    "id": f"{source_id}:tool:runtime",
                    "name": "agent-reach runtime bridge",
                    "type": "bridge",
                    "source": source_id,
                    "source_id": source_id,
                    "source_kind": "external_repo",
                    "enabled": True,
                    "description": "外部运行时桥接入口，用于把 MCP/CLI 能力映射到本系统工具运行层。",
                    "tags": ["external", "runtime", "bridge"],
                    "provider": "agent-reach-cli",
                    "bridge_mode": "runtime_bridge",
                    "health_status": _infer_health_status(enabled=True, command="agent-reach"),
                    "agent_ids": [],
                    "permissions": _tool_permissions(
                        requires_permission=True,
                        scopes=["agents:read", "agents:reload"],
                        roles=["admin", "operator"],
                    ),
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "toolId": {"type": "string"},
                            "payload": {"type": "object"},
                        },
                        "required": ["toolId"],
                    },
                    "output_schema": {
                        "type": "object",
                        "properties": {
                            "traceId": {"type": "string"},
                            "result": {"type": "object"},
                        },
                    },
                    "recent_call_summary": {
                        "total_calls": 0,
                        "success_calls": 0,
                        "failed_calls": 0,
                        "last_called_at": None,
                        "last_status": "never_called",
                        "last_error": None,
                    },
                    "health_summary": {
                        "status": "degraded",
                        "checked_at": _utc_now_iso(),
                        "reason": "runtime_bridge_waiting_for_executor_wiring",
                    },
                    "config_summary": {
                        "command": "agent-reach <subcommand>",
                    },
                },
            ]
        )

    return items


class AgentReachAdapter:
    def scan(
        self,
        *,
        source_id: str,
        source_name: str,
        source_path: str | Path,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        root = Path(source_path)
        tools = list_agent_reach_tools(source_id=source_id, source_name=source_name, path=root)
        channels = _parse_channel_names(root / "agent_reach" / "channels" / "__init__.py")
        mcporter_config = _read_json(root / "config" / "mcporter.json") or {}
        mcp_servers = mcporter_config.get("mcpServers")
        mcp_server_count = len(mcp_servers) if isinstance(mcp_servers, dict) else 0
        imports_count = len(mcporter_config.get("imports") or [])
        if not root.exists() or not root.is_dir():
            return (
                {
                    "id": source_id,
                    "name": source_name,
                    "kind": "external_repo",
                    "path": str(root),
                    "status": "unavailable",
                    "scan_status": "failed",
                    "tool_count": 0,
                    "notes": ["外部能力目录不存在或不可访问。"],
                    "registry": {
                        "source_id": source_id,
                        "origin": "external_repo",
                        "bridge_enabled": False,
                    },
                    "config_summary": {
                        "mcp_server_count": 0,
                        "imports_count": 0,
                        "channel_count": 0,
                    },
                    "health_summary": {
                        "status": "error",
                        "checked_at": _utc_now_iso(),
                        "reason": "source_unavailable",
                    },
                    "bridge_summary": {
                        "catalog_bridge": False,
                        "doctor_bridge": False,
                        "runtime_bridge": False,
                        "skill_bridge": False,
                    },
                },
                [],
            )

        health_statuses = {str(tool.get("health_status") or "unknown") for tool in tools}
        if "error" in health_statuses:
            source_health_status = "error"
        elif "degraded" in health_statuses:
            source_health_status = "degraded"
        elif "healthy" in health_statuses:
            source_health_status = "healthy"
        elif "disabled" in health_statuses and len(health_statuses) == 1:
            source_health_status = "disabled"
        else:
            source_health_status = "unknown"

        bridge_modes = {str(tool.get("bridge_mode") or "").strip() for tool in tools}
        notes = [
            "以桥接方式接入外部能力仓，不直接并入主运行时。",
            "优先暴露 MCP、doctor、skill-management 等入口。",
        ]
        if not tools:
            notes.append("已扫描到来源，但暂未提取到可展示能力。")
        if channels:
            notes.append(f"检测到 {len(channels)} 个可诊断渠道（doctor bridge）。")

        return (
            {
                "id": source_id,
                "name": source_name,
                "kind": "external_repo",
                "path": str(root),
                "status": "available",
                "scan_status": "success" if tools else "empty",
                "tool_count": len(tools),
                "notes": notes,
                "registry": {
                    "source_id": source_id,
                    "origin": "external_repo",
                    "bridge_enabled": True,
                    "project_root": str(root),
                },
                "config_summary": {
                    "mcp_server_count": mcp_server_count,
                    "imports_count": imports_count,
                    "channel_count": len(channels),
                },
                "health_summary": {
                    "status": source_health_status,
                    "checked_at": _utc_now_iso(),
                    "tool_health_distribution": {
                        status: sum(1 for tool in tools if str(tool.get("health_status") or "unknown") == status)
                        for status in sorted(health_statuses)
                    },
                },
                "bridge_summary": {
                    "catalog_bridge": "catalog_bridge" in bridge_modes or bool(tools),
                    "doctor_bridge": "doctor_bridge" in bridge_modes,
                    "runtime_bridge": "runtime_bridge" in bridge_modes,
                    "skill_bridge": any("skill" in str(tool.get("name") or "") for tool in tools),
                },
                "doctor_summary": {
                    "channels": channels,
                    "channel_count": len(channels),
                },
            },
            tools,
        )
