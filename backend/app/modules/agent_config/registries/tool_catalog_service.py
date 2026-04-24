from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status

from app.modules.agent_config.registries.mcp_runtime_service import MCPRuntimeService, mcp_runtime_service
from app.modules.agent_config.registries.tool_source_service import tool_source_service, ToolSourceService


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _slugify(value: str) -> str:
    normalized = "".join(character.lower() if character.isalnum() else "-" for character in value)
    normalized = "-".join(segment for segment in normalized.split("-") if segment)
    return normalized or "item"


def _merge_health_status(current: str, incoming: str) -> str:
    ranking = {
        "healthy": 5,
        "unknown": 4,
        "degraded": 3,
        "disabled": 2,
        "error": 1,
    }
    current_rank = ranking.get(str(current).strip().lower(), 0)
    incoming_rank = ranking.get(str(incoming).strip().lower(), 0)
    return current if current_rank >= incoming_rank else incoming


class ToolCatalogService:
    def __init__(
        self,
        *,
        source_service: ToolSourceService | None = None,
        runtime_service: MCPRuntimeService | None = None,
    ) -> None:
        self._source_service = source_service or tool_source_service
        self._runtime_service = runtime_service or mcp_runtime_service

    def list_tools(self, *, refresh: bool = False) -> dict[str, Any]:
        raw_tools = self._source_service.list_tools(refresh=refresh)
        aggregated = self._aggregate_tools(raw_tools)
        self._enrich_with_runtime_state(aggregated)
        return {
            "items": aggregated,
            "total": len(aggregated),
        }

    def get_catalog(self, *, refresh: bool = False) -> dict[str, Any]:
        tools_payload = self.list_tools(refresh=refresh)
        source_items = self._source_service.list_sources(refresh=refresh)["items"]
        source_summary: dict[str, int] = {}
        type_summary: dict[str, int] = {}
        for item in tools_payload["items"]:
            source = str(item.get("source") or "")
            tool_type = str(item.get("type") or "")
            source_summary[source] = source_summary.get(source, 0) + 1
            type_summary[tool_type] = type_summary.get(tool_type, 0) + 1
        return {
            "items": tools_payload["items"],
            "total": tools_payload["total"],
            "source_summary": source_summary,
            "type_summary": type_summary,
            "sources": source_items,
            "scanned_at": _utc_now_iso(),
        }

    def get_health(self, *, refresh: bool = False) -> dict[str, Any]:
        return self._runtime_service.list_health(refresh=refresh)

    def get_tool(self, tool_id: str, *, refresh: bool = False) -> dict[str, Any]:
        normalized_tool_id = str(tool_id or "").strip()
        for item in self.list_tools(refresh=refresh)["items"]:
            if item["id"] == normalized_tool_id:
                return item
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")

    def _aggregate_tools(self, raw_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str, str, str], dict[str, Any]] = {}

        for entry in raw_tools:
            source = str(entry.get("source") or "").strip()
            tool_type = str(entry.get("type") or "tool").strip() or "tool"
            name = str(entry.get("name") or "").strip()
            provider = str(entry.get("provider") or "unknown").strip() or "unknown"
            if not source or not name:
                continue
            group_key = (source, tool_type, name, provider)
            if group_key not in grouped:
                grouped[group_key] = {
                    "id": f"tool-{_slugify(':'.join(group_key))}",
                    "name": name,
                    "type": tool_type,
                    "source": source,
                    "source_kind": str(entry.get("source_kind") or "unknown"),
                    "bridge_mode": str(entry.get("bridge_mode") or "catalog"),
                    "enabled": bool(entry.get("enabled", True)),
                    "description": str(entry.get("description") or "").strip(),
                    "tags": list(entry.get("tags") or []),
                    "provider": provider,
                    "health_status": str(entry.get("health_status") or "unknown"),
                    "agent_ids": list(entry.get("agent_ids") or []),
                    "permissions": deepcopy(entry.get("permissions") or {}),
                    "input_schema": deepcopy(entry.get("input_schema") or {}),
                    "output_schema": deepcopy(entry.get("output_schema") or {}),
                    "recent_call_summary": deepcopy(entry.get("recent_call_summary") or {}),
                    "health_summary": deepcopy(entry.get("health_summary") or {}),
                    "migration_stage": deepcopy(entry.get("migration_stage") or {}),
                    "rollback": deepcopy(entry.get("rollback") or {}),
                    "traffic_policy": deepcopy(entry.get("traffic_policy") or {}),
                    "_config_entries": [deepcopy(entry.get("config_summary") or {})],
                    "_health_entries": [deepcopy(entry.get("health_summary") or {})],
                }
                continue

            current = grouped[group_key]
            current["enabled"] = bool(current["enabled"]) or bool(entry.get("enabled", True))
            if not current["description"] and entry.get("description"):
                current["description"] = str(entry["description"]).strip()
            current["health_status"] = _merge_health_status(
                str(current.get("health_status") or "unknown"),
                str(entry.get("health_status") or "unknown"),
            )
            current["tags"] = sorted(
                {
                    str(tag).strip()
                    for tag in [*current.get("tags", []), *(entry.get("tags") or [])]
                    if str(tag).strip()
                }
            )
            current["agent_ids"] = sorted(
                {
                    str(agent_id).strip()
                    for agent_id in [*current.get("agent_ids", []), *(entry.get("agent_ids") or [])]
                    if str(agent_id).strip()
                }
            )
            current["_config_entries"].append(deepcopy(entry.get("config_summary") or {}))
            current["_health_entries"].append(deepcopy(entry.get("health_summary") or {}))

            if not current.get("permissions") and entry.get("permissions"):
                current["permissions"] = deepcopy(entry.get("permissions") or {})
            if not current.get("input_schema") and entry.get("input_schema"):
                current["input_schema"] = deepcopy(entry.get("input_schema") or {})
            if not current.get("output_schema") and entry.get("output_schema"):
                current["output_schema"] = deepcopy(entry.get("output_schema") or {})
            if not current.get("recent_call_summary") and entry.get("recent_call_summary"):
                current["recent_call_summary"] = deepcopy(entry.get("recent_call_summary") or {})
            if not current.get("source_kind") and entry.get("source_kind"):
                current["source_kind"] = str(entry.get("source_kind") or "unknown")
            if not current.get("bridge_mode") and entry.get("bridge_mode"):
                current["bridge_mode"] = str(entry.get("bridge_mode") or "catalog")
            if not current.get("migration_stage") and entry.get("migration_stage"):
                current["migration_stage"] = deepcopy(entry.get("migration_stage") or {})
            if not current.get("rollback") and entry.get("rollback"):
                current["rollback"] = deepcopy(entry.get("rollback") or {})
            if not current.get("traffic_policy") and entry.get("traffic_policy"):
                current["traffic_policy"] = deepcopy(entry.get("traffic_policy") or {})

        items: list[dict[str, Any]] = []
        for item in grouped.values():
            config_entries = item.pop("_config_entries", [])
            health_entries = item.pop("_health_entries", [])
            if len(config_entries) == 1:
                config_summary = config_entries[0]
            else:
                config_summary = {
                    "instances": len(config_entries),
                    "entries": config_entries,
                }
            item["config_summary"] = config_summary
            item["health_summary"] = self._coalesce_health_entries(
                health_entries=health_entries,
                fallback_status=str(item.get("health_status") or "unknown"),
            )
            if not item.get("description"):
                item["description"] = f"Tool '{item['name']}' from source '{item['source']}'."
            item["tags"] = sorted({str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()})
            item["agent_ids"] = sorted(
                {str(agent_id).strip() for agent_id in item.get("agent_ids", []) if str(agent_id).strip()}
            )
            item.setdefault(
                "permissions",
                {
                    "requires_permission": False,
                    "scopes": ["agents:read"],
                    "roles": ["admin", "operator", "power_user", "viewer"],
                    "approval_required": False,
                },
            )
            item.setdefault("input_schema", {"type": "object", "properties": {}})
            item.setdefault("output_schema", {"type": "object", "properties": {}})
            item.setdefault("source_kind", "unknown")
            item.setdefault("bridge_mode", "catalog")
            item.setdefault(
                "recent_call_summary",
                {
                    "total_calls": 0,
                    "success_calls": 0,
                    "failed_calls": 0,
                    "last_called_at": None,
                    "last_status": "never_called",
                    "last_error": None,
                },
            )
            item.setdefault(
                "migration_stage",
                {
                    "stage": "retained_in_core",
                    "status": "stable",
                    "target": "internal_runtime",
                },
            )
            item.setdefault(
                "rollback",
                {
                    "enabled": True,
                    "switch_key": "traffic_policy.mode",
                    "target_mode": "builtin_primary",
                    "last_rollback_at": None,
                    "reason": "catalog_default_guardrail",
                },
            )
            item.setdefault(
                "traffic_policy",
                {
                    "mode": "builtin_primary",
                    "shadow_mode": False,
                    "canary_percent": 0,
                    "route_key": "global",
                },
            )
            items.append(item)

        items.sort(key=lambda entry: (entry["source"], entry["type"], entry["name"], entry["id"]))
        return items

    def _coalesce_health_entries(self, *, health_entries: list[dict[str, Any]], fallback_status: str) -> dict[str, Any]:
        valid_entries = [entry for entry in health_entries if isinstance(entry, dict) and entry]
        if not valid_entries:
            return {
                "status": fallback_status,
                "checked_at": _utc_now_iso(),
                "reason": "no_health_entry",
            }
        latest = deepcopy(valid_entries[-1])
        latest.setdefault("status", fallback_status)
        latest.setdefault("checked_at", _utc_now_iso())
        return latest

    def _enrich_with_runtime_state(self, items: list[dict[str, Any]]) -> None:
        for item in items:
            runtime_health = self._runtime_service.health_for_tool(item)
            runtime_recent_call = self._runtime_service.recent_call_summary(str(item.get("id") or ""))
            runtime_shadow_call = self._runtime_service.recent_shadow_summary(str(item.get("id") or ""))
            if runtime_recent_call.get("total_calls", 0) == 0:
                alias = f"{str(item.get('source') or '').strip()}:{str(item.get('name') or '').strip()}".strip(":")
                if alias:
                    runtime_recent_call = self._runtime_service.recent_call_summary(alias)
                    runtime_shadow_call = self._runtime_service.recent_shadow_summary(alias)
            item["health_status"] = str(runtime_health.get("status") or item.get("health_status") or "unknown")
            item["health_summary"] = {
                **deepcopy(item.get("health_summary") or {}),
                "status": str(runtime_health.get("status") or item.get("health_status") or "unknown"),
                "checked_at": str(runtime_health.get("checked_at") or _utc_now_iso()),
                "runtime": deepcopy(runtime_health.get("runtime") or {}),
                "reason": str(runtime_health.get("reason") or item.get("health_summary", {}).get("reason") or ""),
            }
            item["recent_call_summary"] = {
                **deepcopy(item.get("recent_call_summary") or {}),
                **runtime_recent_call,
                **runtime_shadow_call,
            }
            item["traffic_policy"] = {
                **deepcopy(item.get("traffic_policy") or {}),
                "runtime": deepcopy(runtime_health.get("runtime") or {}),
            }
            runtime_meta = runtime_health.get("runtime") if isinstance(runtime_health.get("runtime"), dict) else {}
            item["runtime_summary"] = {
                "status": item["health_status"],
                "provider": str(runtime_meta.get("provider") or item.get("provider") or "unknown"),
                "base_url": runtime_meta.get("base_url"),
                "command": runtime_meta.get("command"),
                "last_called_at": item["recent_call_summary"].get("last_called_at"),
                "last_status": item["recent_call_summary"].get("last_status"),
                "success_calls": item["recent_call_summary"].get("success_calls", 0),
                "failed_calls": item["recent_call_summary"].get("failed_calls", 0),
            }


tool_catalog_service = ToolCatalogService()
