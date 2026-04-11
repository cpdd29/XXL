from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
from typing import Any
import logging

from fastapi import HTTPException, status
import yaml

from app.services.tool_catalog_adapters.agent_reach_adapter import AgentReachAdapter
from app.services.skill_registry_service import skill_registry_service


logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_AGENT_TOOLS_ROOT = PROJECT_ROOT / "agents"
AGENT_CONFIG_ROOT_ENV = "WORKBOT_AGENT_CONFIG_ROOT"
DEFAULT_EXTERNAL_AGENT_REACH_PATH: Path | None = None
LOCAL_SOURCE_ID = "local-agents"
EXTERNAL_SOURCE_ID = "agent-reach-external"
INTERNAL_SOURCE_ID = "internal-skills"
LOCAL_MCP_SOURCE_ID = "local-mcp-services"
TOOL_SOURCES_MODE_ENV = "WORKBOT_TOOL_SOURCES_MODE"
ENABLE_LOCAL_MCP_SOURCE_ENV = "WORKBOT_ENABLE_LOCAL_MCP_SOURCE"
ENABLE_LOCAL_AGENT_SOURCE_ENV = "WORKBOT_ENABLE_LOCAL_AGENT_SOURCE"
EXTERNAL_TOOL_SOURCES_JSON_ENV_KEYS = (
    "WORKBOT_EXTERNAL_TOOL_SOURCES_JSON",
    "WORKBOT_TOOL_SOURCES_REGISTRY_JSON",
)
EXTERNAL_TOOL_SOURCES_FILE_ENV = "WORKBOT_EXTERNAL_TOOL_SOURCES_FILE"
EXTERNAL_AGENT_REACH_PATH_ENV = "WORKBOT_EXTERNAL_AGENT_REACH_PATH"
ENV_PLACEHOLDER_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def _local_mcp_specs() -> list[dict[str, Any]]:
    return [
        {
            "id": "mcp-tool-web-search",
            "name": "web_search",
            "description": "Search MCP tool",
            "base_url": os.getenv("WORKBOT_SEARCH_MCP_BASE_URL", "http://127.0.0.1:8093"),
            "invoke_path": "/search",
            "method": "POST",
            "requires_permission": False,
            "scopes": ["agents:read"],
            "roles": ["admin", "operator", "power_user", "viewer"],
        },
        {
            "id": "mcp-tool-pdf-read",
            "name": "pdf_read",
            "description": "PDF read MCP tool",
            "base_url": os.getenv("WORKBOT_PDF_MCP_BASE_URL", "http://127.0.0.1:8092"),
            "invoke_path": "/tools/read",
            "method": "POST",
            "requires_permission": False,
            "scopes": ["agents:read"],
            "roles": ["admin", "operator", "power_user", "viewer"],
        },
        {
            "id": "mcp-tool-pdf-summary",
            "name": "pdf_summary",
            "description": "PDF summary MCP tool",
            "base_url": os.getenv("WORKBOT_PDF_MCP_BASE_URL", "http://127.0.0.1:8092"),
            "invoke_path": "/tools/summary",
            "method": "POST",
            "requires_permission": False,
            "scopes": ["agents:read"],
            "roles": ["admin", "operator", "power_user", "viewer"],
        },
        {
            "id": "mcp-tool-pdf-to-docx",
            "name": "pdf_to_docx",
            "description": "PDF to DOCX MCP tool",
            "base_url": os.getenv("WORKBOT_PDF_MCP_BASE_URL", "http://127.0.0.1:8092"),
            "invoke_path": "/tools/to_docx",
            "method": "POST",
            "requires_permission": False,
            "scopes": ["agents:read"],
            "roles": ["admin", "operator", "power_user", "viewer"],
        },
        {
            "id": "mcp-tool-writer-generate",
            "name": "writer_generate",
            "description": "Writer MCP tool",
            "base_url": os.getenv("WORKBOT_WRITER_MCP_BASE_URL", "http://127.0.0.1:8094"),
            "invoke_path": "/generate",
            "method": "POST",
            "requires_permission": False,
            "scopes": ["agents:read"],
            "roles": ["admin", "operator", "power_user", "viewer"],
        },
        {
            "id": "mcp-tool-weather-lookup",
            "name": "weather_lookup",
            "description": "Weather MCP tool",
            "base_url": os.getenv("WORKBOT_WEATHER_MCP_BASE_URL", "http://127.0.0.1:8095"),
            "invoke_path": "/weather",
            "method": "POST",
            "requires_permission": False,
            "scopes": ["agents:read"],
            "roles": ["admin", "operator", "power_user", "viewer"],
        },
        {
            "id": "mcp-tool-order-query",
            "name": "order_query",
            "description": "Order read-only MCP tool",
            "base_url": os.getenv("WORKBOT_ORDER_MCP_BASE_URL", "http://127.0.0.1:8096"),
            "invoke_path": "/query",
            "method": "POST",
            "requires_permission": True,
            "scopes": ["agents:read", "tasks:write"],
            "roles": ["admin", "operator"],
        },
        {
            "id": "mcp-tool-crm-query",
            "name": "crm_query",
            "description": "CRM read-only MCP tool",
            "base_url": os.getenv("WORKBOT_CRM_MCP_BASE_URL", "http://127.0.0.1:8097"),
            "invoke_path": "/query",
            "method": "POST",
            "requires_permission": True,
            "scopes": ["agents:read", "tasks:write"],
            "roles": ["admin", "operator"],
        },
    ]


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _slugify(value: str) -> str:
    normalized = "".join(character.lower() if character.isalnum() else "-" for character in value)
    normalized = "-".join(segment for segment in normalized.split("-") if segment)
    return normalized or "item"


def _as_bool(value: Any, *, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value in {None, ""}:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _as_tags(value: Any) -> list[str]:
    if isinstance(value, str):
        candidates = [segment.strip() for segment in value.split(",")]
        return [tag for tag in candidates if tag]
    if isinstance(value, list):
        tags: list[str] = []
        for item in value:
            normalized = str(item or "").strip()
            if normalized:
                tags.append(normalized)
        return tags
    return []


def _default_permissions() -> dict[str, Any]:
    return {
        "requires_permission": False,
        "scopes": ["agents:read"],
        "roles": ["admin", "operator", "power_user", "viewer"],
        "approval_required": False,
    }


def _default_recent_call_summary() -> dict[str, Any]:
    return {
        "total_calls": 0,
        "success_calls": 0,
        "failed_calls": 0,
        "last_called_at": None,
        "last_status": "never_called",
        "last_error": None,
    }


def _default_health_summary(*, status: str, reason: str) -> dict[str, Any]:
    return {
        "status": status,
        "checked_at": _utc_now_iso(),
        "reason": reason,
    }


def _safe_parse_json(value: str, *, env_key: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse external tool source registry from %s: %s", env_key, exc)
        return None


def _resolve_env_placeholder_string(value: str) -> str:
    if "${" not in value:
        return value

    def replace(match: re.Match[str]) -> str:
        env_key = str(match.group(1) or "").strip()
        default_value = match.group(2) if match.group(2) is not None else ""
        env_value = os.getenv(env_key)
        if env_value not in {None, ""}:
            return str(env_value)
        return default_value

    return ENV_PLACEHOLDER_PATTERN.sub(replace, value)


def _resolve_env_placeholders(value: Any) -> Any:
    if isinstance(value, str):
        return _resolve_env_placeholder_string(value)
    if isinstance(value, list):
        return [_resolve_env_placeholders(item) for item in value]
    if isinstance(value, dict):
        return {key: _resolve_env_placeholders(item) for key, item in value.items()}
    return value


class ToolSourceService:
    def __init__(
        self,
        *,
        agent_tools_root: str | Path | None = None,
        external_source_path: str | Path | None = DEFAULT_EXTERNAL_AGENT_REACH_PATH,
        include_internal_skills: bool = False,
    ) -> None:
        resolved_agent_root = agent_tools_root
        if resolved_agent_root is None:
            configured_agent_root = str(os.getenv(AGENT_CONFIG_ROOT_ENV, "")).strip()
            if configured_agent_root:
                resolved_agent_root = configured_agent_root
        agent_root_path = Path(resolved_agent_root) if resolved_agent_root is not None else DEFAULT_AGENT_TOOLS_ROOT
        if not agent_root_path.is_absolute():
            agent_root_path = PROJECT_ROOT / agent_root_path
        self._agent_tools_root = agent_root_path
        resolved_external_path = external_source_path
        if resolved_external_path is None:
            external_source_from_env = str(os.getenv(EXTERNAL_AGENT_REACH_PATH_ENV, "")).strip()
            if external_source_from_env:
                resolved_external_path = external_source_from_env
        self._external_source_path = Path(resolved_external_path) if resolved_external_path is not None else None
        self._include_internal_skills = bool(include_internal_skills)
        self._agent_reach_adapter = AgentReachAdapter()
        self._sources_cache: list[dict[str, Any]] = []
        self._tools_cache: list[dict[str, Any]] = []
        self._source_detail_cache: dict[str, dict[str, Any]] = {}

    def list_sources(self, *, refresh: bool = False) -> dict[str, Any]:
        if refresh or not self._sources_cache:
            self.scan_sources()
        return {
            "items": deepcopy(self._sources_cache),
            "total": len(self._sources_cache),
            "governance_summary": self._build_governance_summary(self._sources_cache),
        }

    def get_source(self, source_id: str, *, refresh: bool = False) -> dict[str, Any]:
        normalized_source_id = str(source_id or "").strip()
        if refresh or not self._sources_cache:
            self.scan_sources()
        detail = self._source_detail_cache.get(normalized_source_id)
        if detail is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool source not found")
        payload = deepcopy(detail)
        payload["governance_summary"] = self._build_governance_summary(self._sources_cache)
        return payload

    def list_tools(self, *, refresh: bool = False) -> list[dict[str, Any]]:
        if refresh or not self._sources_cache:
            self.scan_sources()
        return deepcopy(self._tools_cache)

    def scan_sources(self) -> dict[str, Any]:
        sources: list[dict[str, Any]] = []
        raw_tools: list[dict[str, Any]] = []
        mode, enable_local_agent_source, enable_local_mcp_source, enable_external_sources = (
            self._resolve_source_scan_mode()
        )
        registered_external_sources = self._load_external_sources_registry()

        if self._include_internal_skills:
            internal_source, internal_tools = self._scan_internal_skills_source()
            sources.append(internal_source)
            raw_tools.extend(internal_tools)

        if enable_local_mcp_source:
            mcp_source, mcp_tools = self._scan_local_mcp_services_source()
            sources.append(mcp_source)
            raw_tools.extend(mcp_tools)

        if enable_local_agent_source:
            local_source, local_tools = self._scan_local_agents_source()
            sources.append(local_source)
            raw_tools.extend(local_tools)

        if enable_external_sources:
            if registered_external_sources:
                for index, definition in enumerate(registered_external_sources, start=1):
                    source, tools = self._scan_registered_external_source(definition, index=index)
                    if source is None:
                        continue
                    sources.append(source)
                    raw_tools.extend(tools)
            else:
                external_source_path = self._external_source_path
                if external_source_path is not None:
                    external_source, external_tools = self._agent_reach_adapter.scan(
                        source_id=EXTERNAL_SOURCE_ID,
                        source_name="Agent Reach External",
                        source_path=external_source_path,
                    )
                    external_source["origin"] = "local_external_path"
                    external_source["registry"] = {
                        **deepcopy(external_source.get("registry") or {}),
                        "origin": "local_external_path",
                    }
                    external_source["config_summary"] = {
                        **deepcopy(external_source.get("config_summary") or {}),
                        "source_mode": mode,
                        "registration": "legacy_external_path",
                    }
                    sources.append(external_source)
                    raw_tools.extend(external_tools)

        tools = [self._normalize_tool_entry(item) for item in raw_tools if isinstance(item, dict)]

        self._sources_cache = [self._normalize_source_item(source=source, all_tools=tools) for source in sources]
        self._tools_cache = tools
        self._source_detail_cache = {
            str(item["id"]): self._build_source_detail(item, tools=tools) for item in self._sources_cache
        }
        return {
            "ok": True,
            "message": f"Scanned {len(sources)} tool sources and {len(tools)} tool entries.",
            "items": deepcopy(self._sources_cache),
            "total": len(self._sources_cache),
            "governance_summary": self._build_governance_summary(self._sources_cache),
        }

    def _resolve_source_scan_mode(self) -> tuple[str, bool, bool, bool]:
        mode = str(os.getenv(TOOL_SOURCES_MODE_ENV, "hybrid") or "hybrid").strip().lower()
        if mode not in {"external_only", "hybrid", "local_only"}:
            mode = "hybrid"

        enable_local_agent_source = _as_bool(os.getenv(ENABLE_LOCAL_AGENT_SOURCE_ENV), default=True)
        enable_local_mcp_source = _as_bool(os.getenv(ENABLE_LOCAL_MCP_SOURCE_ENV), default=True)

        if mode == "external_only":
            enable_local_agent_source = False
            enable_local_mcp_source = False
            enable_external_sources = True
        elif mode == "local_only":
            enable_external_sources = False
        else:
            enable_external_sources = True

        return mode, enable_local_agent_source, enable_local_mcp_source, enable_external_sources

    def _load_external_sources_registry(self) -> list[dict[str, Any]]:
        registry_file = str(os.getenv(EXTERNAL_TOOL_SOURCES_FILE_ENV, "")).strip()
        if registry_file:
            registry_path = Path(registry_file)
            if not registry_path.is_absolute():
                registry_path = PROJECT_ROOT / registry_path
            try:
                raw = registry_path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning(
                    "Failed to read external tool sources registry file %s: %s",
                    registry_path,
                    exc,
                )
                return []
            payload = _safe_parse_json(raw, env_key=f"{EXTERNAL_TOOL_SOURCES_FILE_ENV}={registry_path}")
            normalized = self._normalize_external_sources_payload(
                payload,
                source_label=f"{EXTERNAL_TOOL_SOURCES_FILE_ENV}={registry_path}",
            )
            if normalized is not None:
                return normalized

        for env_key in EXTERNAL_TOOL_SOURCES_JSON_ENV_KEYS:
            raw = str(os.getenv(env_key, "")).strip()
            if not raw:
                continue
            payload = _safe_parse_json(raw, env_key=env_key)
            normalized = self._normalize_external_sources_payload(payload, source_label=env_key)
            if normalized is not None:
                return normalized
        return []

    def _normalize_external_sources_payload(
        self,
        payload: Any,
        *,
        source_label: str,
    ) -> list[dict[str, Any]] | None:
        payload = _resolve_env_placeholders(payload)
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            source_items = payload.get("sources")
            if isinstance(source_items, list):
                normalized_sources = [deepcopy(item) for item in source_items if isinstance(item, dict)]
                top_level_tools = payload.get("tools")
                if isinstance(top_level_tools, list):
                    normalized_sources = self._merge_top_level_registry_tools(
                        normalized_sources,
                        top_level_tools,
                    )
                return normalized_sources
            logger.warning("External registry %s is missing 'sources' list", source_label)
            return []
        if payload is None:
            return []
        logger.warning("External registry %s must be JSON object or array", source_label)
        return []

    def _merge_top_level_registry_tools(
        self,
        source_items: list[dict[str, Any]],
        top_level_tools: list[Any],
    ) -> list[dict[str, Any]]:
        merged_sources = [deepcopy(item) for item in source_items]
        source_index: dict[str, dict[str, Any]] = {}
        for item in merged_sources:
            source_id = str(item.get("id") or "").strip()
            if source_id:
                source_index[source_id] = item

        for item in top_level_tools:
            if not isinstance(item, dict):
                continue
            source_id = str(item.get("source") or "").strip()
            if not source_id:
                continue
            source = source_index.get(source_id)
            if source is None:
                source = {
                    "id": source_id,
                    "name": source_id,
                    "kind": "mcp_registry",
                    "tools": [],
                }
                merged_sources.append(source)
                source_index[source_id] = source
            raw_tools = source.get("tools")
            if not isinstance(raw_tools, list):
                raw_tools = []
                source["tools"] = raw_tools
            raw_tools.append(deepcopy(item))
        return merged_sources

    def _scan_registered_external_source(
        self,
        definition: dict[str, Any],
        *,
        index: int,
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        kind = str(definition.get("kind") or "").strip().lower()
        source_id = str(definition.get("id") or "").strip()
        source_name = str(definition.get("name") or "").strip()

        if kind == "external_repo":
            source_path = str(definition.get("path") or "").strip()
            resolved_source_id = source_id or (EXTERNAL_SOURCE_ID if index == 1 else f"{EXTERNAL_SOURCE_ID}-{index}")
            resolved_source_name = source_name or f"External Repo Source {index}"
            inline_tools = definition.get("tools")
            notes: list[str] = []
            tools: list[dict[str, Any]] = []
            if source_path:
                source, tools = self._agent_reach_adapter.scan(
                    source_id=resolved_source_id,
                    source_name=resolved_source_name,
                    source_path=source_path,
                )
            else:
                source = {
                    "id": resolved_source_id,
                    "name": resolved_source_name,
                    "kind": "external_repo",
                    "path": "",
                    "status": "available",
                    "scan_status": "empty",
                    "tool_count": 0,
                    "notes": ["未提供本地源码路径，使用 registry 内联工具定义。"],
                    "registry": {
                        "source_id": resolved_source_id,
                        "origin": "external_repo",
                        "bridge_enabled": True,
                    },
                    "config_summary": {
                        "mcp_server_count": 0,
                        "imports_count": 0,
                        "channel_count": 0,
                    },
                    "health_summary": {
                        "status": "unknown",
                        "checked_at": _utc_now_iso(),
                        "reason": "inline_registry_tools_only",
                    },
                    "bridge_summary": {
                        "catalog_bridge": True,
                        "doctor_bridge": False,
                        "runtime_bridge": True,
                        "skill_bridge": False,
                    },
                }
            extra_tools: list[dict[str, Any]] = []
            if isinstance(inline_tools, list):
                for item in inline_tools:
                    if not isinstance(item, dict):
                        notes.append("external_repo 内联 tools 含非对象项，已跳过。")
                        continue
                    normalized = self._normalize_registry_tool(
                        item=item,
                        source_id=resolved_source_id,
                        default_source_kind="external_repo",
                        default_provider="external-registry",
                        default_type=str(item.get("type") or "skill"),
                        registration_kind="external_repo",
                    )
                    if normalized is None:
                        notes.append("external_repo 内联工具缺少 id/name，已跳过。")
                        continue
                    extra_tools.append(normalized)
            deduplicated: dict[str, dict[str, Any]] = {}
            for item in [*tools, *extra_tools]:
                item_id = str(item.get("id") or "").strip()
                if not item_id:
                    continue
                deduplicated[item_id] = item
            tools = list(deduplicated.values())
            source["origin"] = "external_registry"
            source_notes = list(source.get("notes") or [])
            source_notes.extend(notes)
            source["notes"] = source_notes
            source["tool_count"] = len(tools)
            source["scan_status"] = "success" if tools else source.get("scan_status", "empty")
            if tools:
                source["status"] = "available"
            source["registry"] = {
                **deepcopy(source.get("registry") or {}),
                "origin": "external_registry",
                "registration_kind": "external_repo",
                "registration_index": index,
            }
            source["config_summary"] = {
                **deepcopy(source.get("config_summary") or {}),
                "registration_kind": "external_repo",
                "registered_path": source_path or None,
                "path_exists": Path(source_path).exists() if source_path else False,
                "registered_tool_count": len(extra_tools),
            }
            return source, tools

        if kind == "mcp_registry":
            return self._scan_external_mcp_registry_source(definition, index=index)

        logger.warning("Skip unsupported external source kind=%s for id=%s", kind or "<empty>", source_id or f"source-{index}")
        return None, []

    def _scan_external_mcp_registry_source(
        self,
        definition: dict[str, Any],
        *,
        index: int,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        source_id = str(definition.get("id") or "").strip() or f"external-mcp-registry-{index}"
        source_name = str(definition.get("name") or "").strip() or f"External MCP Registry {index}"
        raw_tools = definition.get("tools")
        notes: list[str] = []
        tools: list[dict[str, Any]] = []

        if not isinstance(raw_tools, list):
            notes.append("外部 mcp_registry 未提供 tools 数组。")
            raw_tools = []

        for item in raw_tools:
            if not isinstance(item, dict):
                notes.append("外部 mcp_registry 含非对象 tools 项，已跳过。")
                continue
            normalized = self._normalize_registry_tool(
                item=item,
                source_id=source_id,
                default_source_kind="mcp_server",
                default_provider="external-mcp-registry",
                default_type="mcp",
                registration_kind="mcp_registry",
            )
            if normalized is None:
                notes.append("外部 mcp_registry 工具缺少 id/name，已跳过。")
                continue
            tools.append(normalized)

        scan_status = "success" if tools else ("failed" if notes else "empty")
        source = {
            "id": source_id,
            "name": source_name,
            "kind": "mcp_server",
            "path": "",
            "status": "available",
            "scan_status": scan_status,
            "tool_count": len(tools),
            "notes": notes or ["由外部 mcp_registry 注入工具定义。"],
            "origin": "external_registry",
            "registry": {
                "source_id": source_id,
                "origin": "external_registry",
                "registration_kind": "mcp_registry",
                "bridge_enabled": True,
            },
            "config_summary": {
                "registration_kind": "mcp_registry",
                "registered_tool_count": len(raw_tools),
                "loaded_tool_count": len(tools),
                "path_exists": True,
                "scanned_at": _utc_now_iso(),
            },
            "bridge_summary": {
                "catalog_bridge": True,
                "doctor_bridge": False,
                "runtime_bridge": True,
                "skill_bridge": False,
            },
        }
        return source, tools

    def _normalize_registry_tool(
        self,
        *,
        item: dict[str, Any],
        source_id: str,
        default_source_kind: str,
        default_provider: str,
        default_type: str,
        registration_kind: str,
    ) -> dict[str, Any] | None:
        tool_id = str(item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()
        if not tool_id and not name:
            return None
        resolved_tool_id = tool_id or f"{source_id}:mcp:{_slugify(name)}"
        resolved_name = name or resolved_tool_id
        config_summary_payload = item.get("config_summary") if isinstance(item.get("config_summary"), dict) else {}
        base_url = str(
            config_summary_payload.get("baseUrl")
            or config_summary_payload.get("base_url")
            or item.get("base_url")
            or ""
        ).strip()
        invoke_path = str(
            config_summary_payload.get("invokePath")
            or config_summary_payload.get("invoke_path")
            or item.get("invoke_path")
            or "/invoke"
        ).strip() or "/invoke"
        method = str(
            config_summary_payload.get("httpMethod")
            or config_summary_payload.get("http_method")
            or item.get("method")
            or "POST"
        ).strip().upper() or "POST"
        provider = str(item.get("provider") or default_provider).strip() or default_provider
        source_kind = str(item.get("source_kind") or default_source_kind).strip() or default_source_kind
        bridge_mode = str(item.get("bridge_mode") or "runtime_bridge").strip() or "runtime_bridge"
        tool_type = str(item.get("type") or default_type).strip() or default_type
        enabled = _as_bool(item.get("enabled"), default=True)
        permissions_payload = item.get("permissions")
        if isinstance(permissions_payload, dict):
            requires_permission = _as_bool(permissions_payload.get("requires_permission"), default=False)
            scopes = list(permissions_payload.get("scopes") or ["agents:read"])
            roles = list(permissions_payload.get("roles") or ["admin", "operator", "power_user", "viewer"])
            approval_required = _as_bool(
                permissions_payload.get("approval_required"),
                default=requires_permission,
            )
        else:
            requires_permission = False
            scopes = ["agents:read"]
            roles = ["admin", "operator", "power_user", "viewer"]
            approval_required = False

        health_status = str(item.get("health_status") or ("healthy" if base_url else ("disabled" if not enabled else "unknown")))
        input_schema = item.get("input_schema") if isinstance(item.get("input_schema"), dict) else None
        output_schema = item.get("output_schema") if isinstance(item.get("output_schema"), dict) else None
        merged_config_summary = {
            **deepcopy(config_summary_payload),
            "baseUrl": base_url or None,
            "base_url": base_url or None,
            "invokePath": invoke_path,
            "invoke_path": invoke_path,
            "httpMethod": method,
            "http_method": method,
            "registration_kind": registration_kind,
        }
        return {
            "id": resolved_tool_id,
            "name": resolved_name,
            "type": tool_type,
            "source": source_id,
            "source_id": source_id,
            "source_kind": source_kind,
            "enabled": enabled,
            "description": str(item.get("description") or f"External MCP tool: {resolved_name}"),
            "tags": _as_tags(item.get("tags")) or ["mcp", "external", "runtime"],
            "provider": provider,
            "bridge_mode": bridge_mode,
            "health_status": health_status,
            "agent_ids": [],
            "permissions": {
                "requires_permission": requires_permission,
                "scopes": scopes,
                "roles": roles,
                "approval_required": approval_required,
            },
            "input_schema": input_schema or {"type": "object", "properties": {"payload": {"type": "object"}}},
            "output_schema": output_schema or {"type": "object", "properties": {"result": {"type": "object"}}},
            "recent_call_summary": _default_recent_call_summary(),
            "health_summary": _default_health_summary(
                status=health_status,
                reason="external_mcp_registry_registered",
            ),
            "config_summary": merged_config_summary,
        }

    def _scan_internal_skills_source(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        from app.services.free_workflow_service import free_workflow_service  # noqa: F401

        skill_items = skill_registry_service.list_abilities(ability_type="skill", enabled=True)
        tools: list[dict[str, Any]] = []
        for ability in skill_items:
            tools.append(
                {
                    "id": str(ability.get("id") or ability.get("name") or ""),
                    "name": str(ability.get("name") or ability.get("id") or ""),
                    "type": "skill",
                    "source": INTERNAL_SOURCE_ID,
                    "source_id": INTERNAL_SOURCE_ID,
                    "source_kind": "internal",
                    "enabled": bool(ability.get("enabled", True)),
                    "description": str(ability.get("description") or ""),
                    "tags": list(ability.get("tags") or []),
                    "provider": "internal-runtime",
                    "bridge_mode": "skill_runtime",
                    "health_status": "healthy" if ability.get("enabled", True) else "disabled",
                    "agent_ids": [],
                    "permissions": {
                        "requires_permission": False,
                        "scopes": ["agents:read"],
                        "roles": ["admin", "operator", "power_user", "viewer"],
                        "approval_required": False,
                    },
                    "input_schema": deepcopy(ability.get("input_schema") or {}),
                    "output_schema": deepcopy(ability.get("output_schema") or {}),
                    "recent_call_summary": {
                        "total_calls": 0,
                        "success_calls": 0,
                        "failed_calls": 0,
                        "last_called_at": None,
                        "last_status": "never_called",
                        "last_error": None,
                    },
                    "health_summary": {
                        "status": "healthy" if ability.get("enabled", True) else "disabled",
                        "checked_at": _utc_now_iso(),
                        "reason": "internal_skill_registered",
                    },
                    "config_summary": {
                        "capabilities": list(ability.get("capabilities") or []),
                        "timeout_seconds": ability.get("timeout_seconds"),
                    },
                }
            )
        source = {
            "id": INTERNAL_SOURCE_ID,
            "name": "Internal Skills",
            "kind": "internal",
            "path": "",
            "status": "available",
            "scan_status": "success" if tools else "empty",
            "tool_count": len(tools),
            "notes": ["内置技能直接由 Skill Runtime 调用。"],
            "registry": {
                "source_id": INTERNAL_SOURCE_ID,
                "origin": "skill_registry",
                "bridge_enabled": True,
            },
            "origin": "skill_registry",
            "config_summary": {
                "path_exists": True,
                "scanned_at": _utc_now_iso(),
            },
            "bridge_summary": {
                "catalog_bridge": True,
                "doctor_bridge": False,
                "runtime_bridge": True,
                "skill_bridge": True,
            },
        }
        return source, tools

    def _normalize_source_item(self, *, source: dict[str, Any], all_tools: list[dict[str, Any]]) -> dict[str, Any]:
        source_id = str(source.get("id") or "").strip()
        source_tools = [tool for tool in all_tools if str(tool.get("source") or "").strip() == source_id]
        config_summary = deepcopy(source.get("config_summary") or {})
        if "path_exists" not in config_summary:
            path = Path(str(source.get("path") or ""))
            config_summary["path_exists"] = path.exists()
        config_summary.setdefault("scanned_at", _utc_now_iso())
        registry = deepcopy(source.get("registry") or {})
        origin = str(source.get("origin") or registry.get("origin") or "unknown")
        config_summary.setdefault("origin", origin)
        metadata = deepcopy(source.get("metadata") or {})
        metadata.setdefault("deprecated", bool(registry.get("deprecated")))
        metadata.setdefault("legacy_fallback", bool(registry.get("legacy_fallback")))
        metadata.setdefault(
            "activation_mode",
            str(
                metadata.get("activation_mode")
                or registry.get("activation_mode")
                or config_summary.get("activation_mode")
                or ("local_only_or_manual_fallback" if metadata.get("legacy_fallback") else "catalog_driven")
            ),
        )
        config_summary.setdefault("deprecated", metadata.get("deprecated"))
        config_summary.setdefault("legacy_fallback", metadata.get("legacy_fallback"))
        config_summary.setdefault("activation_mode", metadata.get("activation_mode"))

        normalized = {
            **deepcopy(source),
            "origin": origin,
            "registry": registry,
            "metadata": metadata,
            "config_summary": config_summary,
            "health_summary": self._build_source_health_summary(source=source, tools=source_tools),
            "bridge_summary": deepcopy(source.get("bridge_summary") or {}),
            "migration_summary": self._build_source_migration_summary(source_tools),
            "traffic_policy": deepcopy(source.get("traffic_policy") or self._default_source_traffic_policy()),
            "rollback": deepcopy(source.get("rollback") or self._default_source_rollback()),
        }
        return normalized

    def _normalize_tool_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        normalized = deepcopy(entry)
        enabled = bool(normalized.get("enabled", True))
        source_kind = str(normalized.get("source_kind") or "").strip() or self._infer_source_kind(normalized)
        bridge_mode = str(normalized.get("bridge_mode") or "").strip() or self._infer_bridge_mode(normalized)
        health_status = str(normalized.get("health_status") or ("healthy" if enabled else "disabled"))

        normalized["source_kind"] = source_kind
        normalized["bridge_mode"] = bridge_mode
        normalized["permissions"] = deepcopy(normalized.get("permissions") or _default_permissions())
        normalized["input_schema"] = deepcopy(
            normalized.get("input_schema") or {"type": "object", "properties": {}}
        )
        normalized["output_schema"] = deepcopy(
            normalized.get("output_schema") or {"type": "object", "properties": {}}
        )
        normalized["recent_call_summary"] = deepcopy(
            normalized.get("recent_call_summary") or _default_recent_call_summary()
        )
        normalized["health_summary"] = deepcopy(
            normalized.get("health_summary")
            or _default_health_summary(status=health_status, reason="tool_registered")
        )
        normalized["migration_stage"] = deepcopy(
            normalized.get("migration_stage") or self._infer_migration_stage(normalized)
        )
        normalized["rollback"] = deepcopy(normalized.get("rollback") or self._default_tool_rollback(normalized))
        normalized["traffic_policy"] = deepcopy(
            normalized.get("traffic_policy") or self._default_tool_traffic_policy(normalized)
        )
        normalized.setdefault("agent_ids", [])
        normalized.setdefault("tags", [])
        return normalized

    def _infer_source_kind(self, entry: dict[str, Any]) -> str:
        source = str(entry.get("source") or "").strip()
        if source == INTERNAL_SOURCE_ID:
            return "internal"
        if source == LOCAL_SOURCE_ID:
            return "local_agents"
        if source == EXTERNAL_SOURCE_ID:
            return "external_repo"
        return "unknown"

    def _infer_bridge_mode(self, entry: dict[str, Any]) -> str:
        source_kind = str(entry.get("source_kind") or "").strip().lower()
        if source_kind in {"external_repo", "mcp_server"}:
            return "runtime_bridge"
        if source_kind == "internal":
            return "skill_runtime"
        return "local_registry"

    def _infer_migration_stage(self, entry: dict[str, Any]) -> dict[str, Any]:
        name = str(entry.get("name") or "").strip().lower()
        source_kind = str(entry.get("source_kind") or "").strip().lower()
        if source_kind in {"external_repo", "mcp_server"}:
            return {
                "stage": "externalized",
                "status": "active",
                "target": "mcp_runtime",
            }
        if name in {"web_search_skill", "pdf_read_skill", "pdf_summary_skill"}:
            return {
                "stage": "bridge_in_progress",
                "status": "dual_run",
                "target": "mcp_runtime",
            }
        return {
            "stage": "retained_in_core",
            "status": "stable",
            "target": "internal_runtime",
        }

    def _default_tool_traffic_policy(self, entry: dict[str, Any]) -> dict[str, Any]:
        migration = entry.get("migration_stage") or {}
        stage = str(migration.get("stage") or "").strip().lower()
        if stage == "externalized":
            mode = "runtime_primary"
            shadow = False
            canary = 100
        elif stage == "bridge_in_progress":
            mode = "builtin_primary"
            shadow = True
            canary = 20
        else:
            mode = "builtin_primary"
            shadow = False
            canary = 0
        return {
            "mode": mode,
            "shadow_mode": shadow,
            "canary_percent": canary,
            "route_key": "global",
        }

    def _default_tool_rollback(self, entry: dict[str, Any]) -> dict[str, Any]:
        return {
            "enabled": True,
            "switch_key": "traffic_policy.mode",
            "target_mode": "builtin_primary",
            "last_rollback_at": None,
            "reason": "default_guardrail",
            "source_kind": str(entry.get("source_kind") or "unknown"),
        }

    def _build_source_migration_summary(self, tools: list[dict[str, Any]]) -> dict[str, Any]:
        stages: dict[str, int] = {}
        for tool in tools:
            stage = str((tool.get("migration_stage") or {}).get("stage") or "unknown")
            stages[stage] = stages.get(stage, 0) + 1
        return {
            "total": len(tools),
            "stages": stages,
            "updated_at": _utc_now_iso(),
        }

    @staticmethod
    def _default_source_traffic_policy() -> dict[str, Any]:
        return {
            "mode": "catalog_driven",
            "shadow_mode": False,
            "canary_percent": 0,
            "route_key": "source_default",
        }

    @staticmethod
    def _default_source_rollback() -> dict[str, Any]:
        return {
            "enabled": True,
            "switch_key": "traffic_policy.mode",
            "target_mode": "catalog_driven",
            "last_rollback_at": None,
            "reason": "source_default_guardrail",
        }

    def _build_source_detail(self, source: dict[str, Any], *, tools: list[dict[str, Any]]) -> dict[str, Any]:
        source_id = str(source.get("id") or "").strip()
        source_tools = [deepcopy(tool) for tool in tools if str(tool.get("source") or "").strip() == source_id]
        return {
            **deepcopy(source),
            "tools": source_tools,
            "tool_total": len(source_tools),
            "scanned_at": str(source.get("config_summary", {}).get("scanned_at") or _utc_now_iso()),
        }

    def _build_governance_summary(self, sources: list[dict[str, Any]]) -> dict[str, Any]:
        mode, enable_local_agent_source, enable_local_mcp_source, enable_external_sources = (
            self._resolve_source_scan_mode()
        )
        has_legacy_fallback = any(
            bool((source.get("metadata") or {}).get("legacy_fallback"))
            or bool((source.get("registry") or {}).get("legacy_fallback"))
            or bool((source.get("config_summary") or {}).get("legacy_fallback"))
            for source in sources
        )
        return {
            "mode": mode,
            "local_agent_enabled": enable_local_agent_source,
            "local_mcp_enabled": enable_local_mcp_source,
            "external_enabled": enable_external_sources,
            "has_legacy_fallback": has_legacy_fallback,
            "source_count": len(sources),
            "updated_at": _utc_now_iso(),
        }

    def _build_source_health_summary(self, *, source: dict[str, Any], tools: list[dict[str, Any]]) -> dict[str, Any]:
        statuses = [str(tool.get("health_status") or "unknown") for tool in tools]
        distribution = {status: statuses.count(status) for status in sorted(set(statuses))}
        source_status = str(source.get("status") or "").strip().lower()
        scan_status = str(source.get("scan_status") or "").strip().lower()
        if source_status != "available":
            status_value = "error"
        elif "error" in distribution:
            status_value = "error"
        elif "degraded" in distribution:
            status_value = "degraded"
        elif "healthy" in distribution:
            status_value = "healthy"
        elif scan_status in {"empty", "failed"}:
            status_value = "unknown"
        else:
            status_value = "unknown"

        return {
            "status": status_value,
            "checked_at": _utc_now_iso(),
            "tool_health_distribution": distribution,
        }

    def _scan_local_agents_source(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        root = self._agent_tools_root
        notes: list[str] = []
        tools: list[dict[str, Any]] = []
        activation_mode = "local_only_or_manual_fallback"
        fallback_notes = [
            "本地 Agent 仅作为 legacy/manual fallback，不作为主运行时来源。",
            "建议使用外部注册表中的 agent/skill/mcp 作为默认入口。",
        ]

        if not root.exists() or not root.is_dir():
            return (
                {
                    "id": LOCAL_SOURCE_ID,
                    "name": "Legacy Local Agents Fallback",
                    "kind": "local_agents",
                    "path": str(root),
                    "status": "unavailable",
                    "scan_status": "failed",
                    "tool_count": 0,
                    "notes": ["本地 agents 目录不存在或不可访问。", *fallback_notes],
                    "registry": {
                        "source_id": LOCAL_SOURCE_ID,
                        "origin": "local_agents",
                        "bridge_enabled": False,
                        "deprecated": True,
                        "legacy_fallback": True,
                        "activation_mode": activation_mode,
                        "source_mode": activation_mode,
                    },
                    "origin": "local_agents",
                    "metadata": {
                        "deprecated": True,
                        "legacy_fallback": True,
                        "activation_mode": activation_mode,
                        "source_mode": activation_mode,
                    },
                    "config_summary": {
                        "path_exists": False,
                        "scanned_at": _utc_now_iso(),
                        "deprecated": True,
                        "legacy_fallback": True,
                        "activation_mode": activation_mode,
                        "source_mode": activation_mode,
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

        for directory in sorted(root.iterdir(), key=lambda item: item.name):
            if not directory.is_dir():
                continue
            agent_id = str(directory.name).strip()
            if not agent_id:
                continue

            tools_path = directory / "tools.yaml"
            if not tools_path.exists() or not tools_path.is_file():
                continue

            parsed = self._load_tools_yaml(tools_path, notes=notes)
            for entry in self._extract_tools(parsed):
                normalized = self._normalize_agent_tool(entry, agent_id=agent_id, tools_path=tools_path)
                if normalized is None:
                    notes.append(f"已跳过非法工具配置: {tools_path}")
                    continue
                tools.append(normalized)

        scan_status = "success"
        if notes and tools:
            scan_status = "partial"
        elif notes:
            scan_status = "failed"
        elif not tools:
            scan_status = "empty"

        source = {
            "id": LOCAL_SOURCE_ID,
            "name": "Legacy Local Agents Fallback",
            "kind": "local_agents",
            "path": str(root),
            "status": "available",
            "scan_status": scan_status,
            "tool_count": len(tools),
            "notes": list(dict.fromkeys([*notes, *fallback_notes])),
            "registry": {
                "source_id": LOCAL_SOURCE_ID,
                "origin": "local_agents",
                "bridge_enabled": False,
                "deprecated": True,
                "legacy_fallback": True,
                "activation_mode": activation_mode,
                "source_mode": activation_mode,
            },
            "origin": "local_agents",
            "metadata": {
                "deprecated": True,
                "legacy_fallback": True,
                "activation_mode": activation_mode,
                "source_mode": activation_mode,
            },
            "config_summary": {
                "path_exists": True,
                "agent_count": len(
                    [directory for directory in root.iterdir() if directory.is_dir() and str(directory.name).strip()]
                ),
                "scanned_at": _utc_now_iso(),
                "deprecated": True,
                "legacy_fallback": True,
                "activation_mode": activation_mode,
                "source_mode": activation_mode,
            },
            "bridge_summary": {
                "catalog_bridge": False,
                "doctor_bridge": False,
                "runtime_bridge": False,
                "skill_bridge": False,
            },
        }
        return source, tools

    def _scan_local_mcp_services_source(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        tools: list[dict[str, Any]] = []
        notes: list[str] = []
        for spec in _local_mcp_specs():
            base_url = str(spec.get("base_url") or "").strip()
            if not base_url:
                notes.append(f"{spec['name']} 未配置 base_url")
            health_status = "degraded" if base_url.startswith("http://127.0.0.1") else ("healthy" if base_url else "unknown")
            requires_permission = bool(spec.get("requires_permission", False))
            tools.append(
                {
                    "id": str(spec["id"]),
                    "name": str(spec["name"]),
                    "type": "mcp",
                    "source": LOCAL_MCP_SOURCE_ID,
                    "source_id": LOCAL_MCP_SOURCE_ID,
                    "source_kind": "mcp_server",
                    "enabled": True,
                    "description": str(spec["description"]),
                    "tags": ["mcp", "externalized", "runtime"],
                    "provider": "mcp-http",
                    "bridge_mode": "runtime_bridge",
                    "health_status": health_status,
                    "agent_ids": [],
                    "permissions": {
                        "requires_permission": requires_permission,
                        "scopes": list(spec.get("scopes") or ["agents:read"]),
                        "roles": list(spec.get("roles") or ["admin", "operator", "power_user", "viewer"]),
                        "approval_required": requires_permission,
                    },
                    "input_schema": {"type": "object", "properties": {"payload": {"type": "object"}}},
                    "output_schema": {"type": "object", "properties": {"result": {"type": "object"}}},
                    "recent_call_summary": _default_recent_call_summary(),
                    "health_summary": _default_health_summary(status=health_status, reason="local_mcp_registered"),
                    "config_summary": {
                        "baseUrl": base_url,
                        "base_url": base_url,
                        "invokePath": str(spec.get("invoke_path") or "/invoke"),
                        "invoke_path": str(spec.get("invoke_path") or "/invoke"),
                        "httpMethod": str(spec.get("method") or "POST").upper(),
                        "http_method": str(spec.get("method") or "POST").upper(),
                        "timeoutSeconds": 10,
                        "retryAttempts": 2,
                        "probeHealth": False,
                        "circuitBreakerThreshold": 3,
                        "circuitBreakerTtlSeconds": 30,
                    },
                }
            )
        source = {
            "id": LOCAL_MCP_SOURCE_ID,
            "name": "Legacy Local MCP Fallback",
            "kind": "mcp_server",
            "path": str(PROJECT_ROOT),
            "status": "available",
            "scan_status": "success" if tools else "empty",
            "tool_count": len(tools),
            "notes": notes
            or [
                "本地 MCP 仅作为 legacy/manual fallback，不作为主运行时来源。",
                "建议使用外部注册表 sources[].kind=mcp_registry 作为默认入口。",
            ],
            "registry": {
                "source_id": LOCAL_MCP_SOURCE_ID,
                "origin": "local_mcp_registry",
                "bridge_enabled": True,
                "deprecated": True,
                "legacy_fallback": True,
                "activation_mode": "local_only_or_manual_fallback",
                "source_mode": "local_only_or_manual_fallback",
            },
            "origin": "local_mcp_registry",
            "metadata": {
                "deprecated": True,
                "legacy_fallback": True,
                "activation_mode": "local_only_or_manual_fallback",
                "source_mode": "local_only_or_manual_fallback",
            },
            "config_summary": {
                "path_exists": True,
                "scanned_at": _utc_now_iso(),
                "deprecated": True,
                "legacy_fallback": True,
                "activation_mode": "local_only_or_manual_fallback",
                "source_mode": "local_only_or_manual_fallback",
            },
            "bridge_summary": {
                "catalog_bridge": True,
                "doctor_bridge": False,
                "runtime_bridge": True,
                "skill_bridge": False,
            },
        }
        return source, tools

    def _load_tools_yaml(self, path: Path, *, notes: list[str]) -> dict[str, Any] | list[Any] | None:
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Failed to read tools config %s: %s", path, exc)
            notes.append(f"读取失败 {path}: {exc}")
            return None

        try:
            return yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            logger.warning("Failed to parse tools config %s: %s", path, exc)
            notes.append(f"解析失败 {path}: {exc}")
            return None

    def _extract_tools(self, payload: dict[str, Any] | list[Any] | None) -> list[dict[str, Any]]:
        if payload is None:
            return []
        if isinstance(payload, dict):
            raw_tools = payload.get("tools")
            if isinstance(raw_tools, list):
                return [tool for tool in raw_tools if isinstance(tool, dict)]
            return []
        if isinstance(payload, list):
            return [tool for tool in payload if isinstance(tool, dict)]
        return []

    def _normalize_agent_tool(
        self,
        tool: dict[str, Any],
        *,
        agent_id: str,
        tools_path: Path,
    ) -> dict[str, Any] | None:
        name = str(tool.get("name") or "").strip()
        if not name:
            return None

        provider = str(tool.get("provider") or "unknown").strip() or "unknown"
        tool_type = str(tool.get("type") or "tool").strip() or "tool"
        enabled = _as_bool(tool.get("enabled"), default=True)
        description = str(tool.get("description") or "").strip()
        if not description:
            description = f"Tool '{name}' configured for agent {agent_id}."
        tags = _as_tags(tool.get("tags"))
        if "agent" not in tags:
            tags.append("agent")

        reserved_keys = {"name", "provider", "type", "enabled", "description", "tags"}
        extra_config = {key: value for key, value in tool.items() if key not in reserved_keys}
        health_status = "unknown" if enabled else "disabled"

        return {
            "id": f"local-agent-{agent_id}-{_slugify(name)}-{_slugify(provider)}",
            "name": name,
            "type": tool_type,
            "source": LOCAL_SOURCE_ID,
            "source_id": LOCAL_SOURCE_ID,
            "source_kind": "local_agents",
            "enabled": enabled,
            "description": description,
            "tags": tags,
            "provider": provider,
            "bridge_mode": "local_registry",
            "health_status": health_status,
            "agent_ids": [agent_id],
            "permissions": {
                "requires_permission": False,
                "scopes": ["agents:read"],
                "roles": ["admin", "operator", "power_user", "viewer"],
                "approval_required": False,
            },
            "input_schema": {
                "type": "object",
                "properties": {
                    "input": {"type": "string"},
                    "options": {"type": "object"},
                },
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "result": {"type": "string"},
                    "meta": {"type": "object"},
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
                "reason": "local_tool_registered",
            },
            "config_summary": {
                "agentId": agent_id,
                "path": str(tools_path),
                **extra_config,
            },
        }


tool_source_service = ToolSourceService()
