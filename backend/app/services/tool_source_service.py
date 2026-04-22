from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
from typing import Any
import logging
from urllib.parse import urlparse

from fastapi import HTTPException, status
import yaml

from app.services.tool_catalog_adapters.agent_reach_adapter import AgentReachAdapter
from app.services.external_skill_registry_service import external_skill_registry_service
from app.services.skill_registry_service import skill_registry_service


logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_AGENT_TOOLS_ROOT = PROJECT_ROOT / "agents"
DEFAULT_EXTERNAL_REGISTRY_FILENAME = "workbot_external_sources.local.json"
DEFAULT_EXTERNAL_REGISTRY_FALLBACK_PATHS = (
    Path("/opt/workbot/external-registry") / DEFAULT_EXTERNAL_REGISTRY_FILENAME,
)
AGENT_CONFIG_ROOT_ENV = "WORKBOT_AGENT_CONFIG_ROOT"
DEFAULT_EXTERNAL_AGENT_REACH_PATH: Path | None = None
LOCAL_SOURCE_ID = "local-agents"
EXTERNAL_SOURCE_ID = "agent-reach-external"
INTERNAL_SOURCE_ID = "internal-skills"
EXTERNAL_SKILL_SOURCE_ID = "external-skill-registry"
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
PROJECT_EXTERNAL_REGISTRY_PATH = PROJECT_ROOT / "deploy" / "external-registry" / DEFAULT_EXTERNAL_REGISTRY_FILENAME
CONTROL_PLANE_SKILL_SOURCE_ID = "control-plane-skill-registry"
CONTROL_PLANE_SKILL_SOURCE_NAME = "Control Plane Skill Registry"
CONTROL_PLANE_MCP_SOURCE_ID = "control-plane-mcp-registry"
CONTROL_PLANE_MCP_SOURCE_NAME = "Control Plane MCP Registry"


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
        {
            "id": "mcp-tool-browser-automation",
            "name": "delivery_note_browser_automation",
            "description": "Scenario-specific browser automation MCP for delivery note export and customer send",
            "base_url": os.getenv("WORKBOT_BROWSER_AUTOMATION_MCP_BASE_URL", "http://127.0.0.1:8099"),
            "invoke_path": "/execute",
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

        external_skill_source, external_skill_tools = self._scan_external_skill_registry_source()
        if external_skill_source is not None:
            sources.append(external_skill_source)
            raw_tools.extend(external_skill_tools)

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

    def register_external_skill_tool(self, payload: dict[str, Any]) -> dict[str, Any]:
        document, registry_path = self._load_external_registry_document_for_write()
        source_id = str(payload.get("source_id") or CONTROL_PLANE_SKILL_SOURCE_ID).strip() or CONTROL_PLANE_SKILL_SOURCE_ID
        source_name = (
            str(payload.get("source_name") or CONTROL_PLANE_SKILL_SOURCE_NAME).strip()
            or CONTROL_PLANE_SKILL_SOURCE_NAME
        )
        name = str(payload.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Skill name is required")

        tool_id = str(payload.get("id") or "").strip() or f"skill-tool-{_slugify(name)}"
        if self._registry_tool_exists(document, tool_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Tool '{tool_id}' already exists")

        base_url = self._normalize_registry_base_url(payload.get("base_url"))
        invoke_path = self._normalize_registry_path(payload.get("invoke_path"), default="/invoke")
        health_path = self._normalize_registry_path(payload.get("health_path"), default="/health")
        method = self._normalize_registry_method(payload.get("method"), default="POST")
        timeout_seconds = self._normalize_timeout_seconds(payload.get("timeout_seconds"), default=8.0)
        description = str(payload.get("description") or f"{name} external skill").strip() or f"{name} external skill"
        provider = str(payload.get("provider") or "external-skill-http").strip() or "external-skill-http"
        version = str(payload.get("version") or "1.0.0").strip() or "1.0.0"
        skill_family = str(payload.get("skill_family") or name).strip() or name
        capabilities = _as_tags(payload.get("capabilities"))
        tags = self._merge_registry_tags(payload.get("tags"), defaults=["skill", "externalized", "runtime"])

        self._ensure_registry_source(
            document,
            source_id=source_id,
            source_name=source_name,
            kind="external_repo",
            registry_origin="control_plane",
            default_notes=[
                "由控制台新增 Skill 入口登记，供本地环境直连外部 Skill 服务。",
            ],
            default_config_summary={
                "deployment_mode": "control_plane_registry",
                "notes": "Skills added from the control plane are stored as inline registry tools.",
            },
        )
        self._append_registry_tool(
            document,
            {
                "id": tool_id,
                "name": name,
                "type": "skill",
                "source": source_id,
                "source_kind": "external_repo",
                "enabled": _as_bool(payload.get("enabled"), default=True),
                "description": description,
                "tags": tags,
                "capabilities": capabilities,
                "provider": provider,
                "bridge_mode": "runtime_bridge",
                "permissions": _default_permissions(),
                "config_summary": {
                    "base_url": base_url,
                    "invoke_path": invoke_path,
                    "health_path": health_path,
                    "http_method": method,
                    "protocol": str(payload.get("protocol") or "http").strip() or "http",
                    "timeout_seconds": timeout_seconds,
                    "version": version,
                    "skill_family": skill_family,
                    "registration_kind": "control_plane_skill",
                },
            },
        )
        self._write_external_registry_document(registry_path, document)
        self.scan_sources()
        return self._build_registration_result(
            source_id=source_id,
            tool_id=tool_id,
            message=f"Skill '{name}' registered successfully.",
        )

    def register_external_mcp_tool(self, payload: dict[str, Any]) -> dict[str, Any]:
        document, registry_path = self._load_external_registry_document_for_write()
        default_source_id, default_source_name = self._resolve_default_mcp_source(document)
        source_id = str(payload.get("source_id") or default_source_id).strip() or default_source_id
        source_name = str(payload.get("source_name") or default_source_name).strip() or default_source_name
        name = str(payload.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MCP name is required")

        tool_id = str(payload.get("id") or "").strip() or f"mcp-tool-{_slugify(name)}"
        if self._registry_tool_exists(document, tool_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Tool '{tool_id}' already exists")

        requires_permission = _as_bool(payload.get("requires_permission"), default=False)
        approval_required = _as_bool(payload.get("approval_required"), default=requires_permission)
        base_url = self._normalize_registry_base_url(payload.get("base_url"))
        invoke_path = self._normalize_registry_path(payload.get("invoke_path"), default="/invoke")
        method = self._normalize_registry_method(payload.get("method"), default="POST")
        timeout_seconds = self._normalize_timeout_seconds(payload.get("timeout_seconds"), default=10.0)
        description = str(payload.get("description") or f"{name} MCP tool").strip() or f"{name} MCP tool"
        provider = str(payload.get("provider") or "mcp-http").strip() or "mcp-http"
        tags = self._merge_registry_tags(payload.get("tags"), defaults=["mcp", "externalized", "runtime"])
        scopes = _as_tags(payload.get("scopes")) or ["agents:read"]
        roles = _as_tags(payload.get("roles")) or ["admin", "operator", "power_user", "viewer"]

        self._ensure_registry_source(
            document,
            source_id=source_id,
            source_name=source_name,
            kind="mcp_registry",
            registry_origin="control_plane",
            default_notes=[
                "由控制台新增 MCP 入口登记，供本地环境直连外部 MCP 服务。",
            ],
            default_config_summary={
                "deployment_mode": "control_plane_registry",
                "notes": "MCP tools added from the control plane are stored as inline registry tools.",
            },
        )
        self._append_registry_tool(
            document,
            {
                "id": tool_id,
                "name": name,
                "type": "mcp",
                "source": source_id,
                "source_kind": "mcp_server",
                "enabled": _as_bool(payload.get("enabled"), default=True),
                "description": description,
                "tags": tags,
                "provider": provider,
                "bridge_mode": "runtime_bridge",
                "permissions": {
                    "requires_permission": requires_permission,
                    "scopes": scopes,
                    "roles": roles,
                    "approval_required": approval_required,
                },
                "config_summary": {
                    "base_url": base_url,
                    "invoke_path": invoke_path,
                    "http_method": method,
                    "timeout_seconds": timeout_seconds,
                    "registration_kind": "control_plane_mcp",
                },
            },
        )
        self._write_external_registry_document(registry_path, document)
        self.scan_sources()
        return self._build_registration_result(
            source_id=source_id,
            tool_id=tool_id,
            message=f"MCP '{name}' registered successfully.",
        )

    def update_external_skill_tool(self, tool_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        document, registry_path = self._load_external_registry_document_for_write()
        existing, _, _, _ = self._find_registry_tool(document, tool_id)
        if existing is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")
        self._assert_control_plane_managed_tool(existing, expected_type="skill")

        source_id = str(payload.get("source_id") or existing.get("source") or CONTROL_PLANE_SKILL_SOURCE_ID).strip()
        source_name = (
            str(payload.get("source_name") or self._find_source_name(document, source_id) or CONTROL_PLANE_SKILL_SOURCE_NAME).strip()
            or CONTROL_PLANE_SKILL_SOURCE_NAME
        )
        name = str(payload.get("name") or existing.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Skill name is required")

        base_url = self._normalize_registry_base_url(
            payload.get("base_url")
            or ((existing.get("config_summary") or {}).get("base_url"))
            or ((existing.get("config_summary") or {}).get("baseUrl"))
        )
        invoke_path = self._normalize_registry_path(
            payload.get("invoke_path") or ((existing.get("config_summary") or {}).get("invoke_path")) or ((existing.get("config_summary") or {}).get("invokePath")),
            default="/invoke",
        )
        health_path = self._normalize_registry_path(
            payload.get("health_path") or ((existing.get("config_summary") or {}).get("health_path")) or ((existing.get("config_summary") or {}).get("healthPath")),
            default="/health",
        )
        method = self._normalize_registry_method(
            payload.get("method") or ((existing.get("config_summary") or {}).get("http_method")) or ((existing.get("config_summary") or {}).get("httpMethod")),
            default="POST",
        )
        timeout_seconds = self._normalize_timeout_seconds(
            payload.get("timeout_seconds") or ((existing.get("config_summary") or {}).get("timeout_seconds")) or ((existing.get("config_summary") or {}).get("timeoutSeconds")),
            default=8.0,
        )
        description = str(payload.get("description") or existing.get("description") or f"{name} external skill").strip()
        provider = str(payload.get("provider") or existing.get("provider") or "external-skill-http").strip() or "external-skill-http"
        version = str(payload.get("version") or ((existing.get("config_summary") or {}).get("version")) or "1.0.0").strip() or "1.0.0"
        skill_family = str(payload.get("skill_family") or ((existing.get("config_summary") or {}).get("skill_family")) or name).strip() or name
        protocol = (
            str(payload.get("protocol") or ((existing.get("config_summary") or {}).get("protocol")) or "http").strip() or "http"
        )
        tags = self._merge_registry_tags(payload.get("tags") if "tags" in payload else existing.get("tags"), defaults=["skill", "externalized", "runtime"])
        capabilities = _as_tags(payload.get("capabilities") if "capabilities" in payload else existing.get("capabilities"))
        enabled = _as_bool(payload.get("enabled") if "enabled" in payload else existing.get("enabled"), default=True)

        self._ensure_registry_source(
            document,
            source_id=source_id,
            source_name=source_name,
            kind="external_repo",
            registry_origin="control_plane",
            default_notes=[
                "由控制台新增 Skill 入口登记，供本地环境直连外部 Skill 服务。",
            ],
            default_config_summary={
                "deployment_mode": "control_plane_registry",
                "notes": "Skills added from the control plane are stored as inline registry tools.",
            },
        )

        existing["name"] = name
        existing["source"] = source_id
        existing["source_kind"] = "external_repo"
        existing["enabled"] = enabled
        existing["description"] = description
        existing["tags"] = tags
        existing["capabilities"] = capabilities
        existing["provider"] = provider
        existing["bridge_mode"] = "runtime_bridge"
        existing["permissions"] = _default_permissions()
        existing["config_summary"] = {
            **deepcopy(existing.get("config_summary") or {}),
            "base_url": base_url,
            "invoke_path": invoke_path,
            "health_path": health_path,
            "http_method": method,
            "protocol": protocol,
            "timeout_seconds": timeout_seconds,
            "version": version,
            "skill_family": skill_family,
            "registration_kind": "control_plane_skill",
        }

        self._write_external_registry_document(registry_path, document)
        self.scan_sources()
        return self._build_registration_result(
            source_id=source_id,
            tool_id=tool_id,
            message=f"Skill '{name}' updated successfully.",
        )

    def update_external_mcp_tool(self, tool_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        document, registry_path = self._load_external_registry_document_for_write()
        existing, _, _, _ = self._find_registry_tool(document, tool_id)
        if existing is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")
        self._assert_control_plane_managed_tool(existing, expected_type="mcp")

        source_id = str(payload.get("source_id") or existing.get("source") or CONTROL_PLANE_MCP_SOURCE_ID).strip()
        source_name = (
            str(payload.get("source_name") or self._find_source_name(document, source_id) or CONTROL_PLANE_MCP_SOURCE_NAME).strip()
            or CONTROL_PLANE_MCP_SOURCE_NAME
        )
        name = str(payload.get("name") or existing.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MCP name is required")

        requires_permission = _as_bool(
            payload.get("requires_permission")
            if "requires_permission" in payload
            else ((existing.get("permissions") or {}).get("requires_permission")),
            default=False,
        )
        approval_required = _as_bool(
            payload.get("approval_required")
            if "approval_required" in payload
            else ((existing.get("permissions") or {}).get("approval_required")),
            default=requires_permission,
        )
        base_url = self._normalize_registry_base_url(
            payload.get("base_url")
            or ((existing.get("config_summary") or {}).get("base_url"))
            or ((existing.get("config_summary") or {}).get("baseUrl"))
        )
        invoke_path = self._normalize_registry_path(
            payload.get("invoke_path") or ((existing.get("config_summary") or {}).get("invoke_path")) or ((existing.get("config_summary") or {}).get("invokePath")),
            default="/invoke",
        )
        method = self._normalize_registry_method(
            payload.get("method") or ((existing.get("config_summary") or {}).get("http_method")) or ((existing.get("config_summary") or {}).get("httpMethod")),
            default="POST",
        )
        timeout_seconds = self._normalize_timeout_seconds(
            payload.get("timeout_seconds") or ((existing.get("config_summary") or {}).get("timeout_seconds")) or ((existing.get("config_summary") or {}).get("timeoutSeconds")),
            default=10.0,
        )
        description = str(payload.get("description") or existing.get("description") or f"{name} MCP tool").strip()
        provider = str(payload.get("provider") or existing.get("provider") or "mcp-http").strip() or "mcp-http"
        tags = self._merge_registry_tags(payload.get("tags") if "tags" in payload else existing.get("tags"), defaults=["mcp", "externalized", "runtime"])
        scopes = _as_tags(payload.get("scopes") if "scopes" in payload else ((existing.get("permissions") or {}).get("scopes"))) or ["agents:read"]
        roles = _as_tags(payload.get("roles") if "roles" in payload else ((existing.get("permissions") or {}).get("roles"))) or ["admin", "operator", "power_user", "viewer"]
        enabled = _as_bool(payload.get("enabled") if "enabled" in payload else existing.get("enabled"), default=True)

        self._ensure_registry_source(
            document,
            source_id=source_id,
            source_name=source_name,
            kind="mcp_registry",
            registry_origin="control_plane",
            default_notes=[
                "由控制台新增 MCP 入口登记，供本地环境直连外部 MCP 服务。",
            ],
            default_config_summary={
                "deployment_mode": "control_plane_registry",
                "notes": "MCP tools added from the control plane are stored as inline registry tools.",
            },
        )

        existing["name"] = name
        existing["source"] = source_id
        existing["source_kind"] = "mcp_server"
        existing["enabled"] = enabled
        existing["description"] = description
        existing["tags"] = tags
        existing["provider"] = provider
        existing["bridge_mode"] = "runtime_bridge"
        existing["permissions"] = {
            "requires_permission": requires_permission,
            "scopes": scopes,
            "roles": roles,
            "approval_required": approval_required,
        }
        existing["config_summary"] = {
            **deepcopy(existing.get("config_summary") or {}),
            "base_url": base_url,
            "invoke_path": invoke_path,
            "http_method": method,
            "timeout_seconds": timeout_seconds,
            "registration_kind": "control_plane_mcp",
        }

        self._write_external_registry_document(registry_path, document)
        self.scan_sources()
        return self._build_registration_result(
            source_id=source_id,
            tool_id=tool_id,
            message=f"MCP '{name}' updated successfully.",
        )

    def delete_external_registry_tool(self, tool_id: str) -> dict[str, Any]:
        document, registry_path = self._load_external_registry_document_for_write()
        existing, container, index, _ = self._find_registry_tool(document, tool_id)
        if existing is None or container is None or index is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")
        self._assert_control_plane_managed_tool(existing)

        source_id = str(existing.get("source") or "").strip()
        deleted_name = str(existing.get("name") or tool_id).strip() or tool_id
        container.pop(index)
        self._cleanup_managed_empty_source(document, source_id)
        self._write_external_registry_document(registry_path, document)
        self.scan_sources()
        return {
            "ok": True,
            "message": f"Tool '{deleted_name}' deleted successfully.",
            "source_id": source_id,
            "tool_id": tool_id,
        }

    def _build_registration_result(self, *, source_id: str, tool_id: str, message: str) -> dict[str, Any]:
        source = self.get_source(source_id, refresh=False)
        tool = next(
            (deepcopy(item) for item in self._tools_cache if str(item.get("id") or "").strip() == tool_id),
            None,
        )
        if tool is None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Registered tool not found")
        return {
            "ok": True,
            "message": message,
            "source_id": source_id,
            "tool_id": tool_id,
            "source": source,
            "tool": tool,
        }

    def _assert_control_plane_managed_tool(
        self,
        tool: dict[str, Any],
        *,
        expected_type: str | None = None,
    ) -> None:
        if expected_type is not None and str(tool.get("type") or "").strip() != expected_type:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tool type mismatch")
        registration_kind = str(((tool.get("config_summary") or {}).get("registration_kind")) or "").strip()
        if registration_kind not in {"control_plane_skill", "control_plane_mcp"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tool is not managed by control plane",
            )

    def _find_registry_tool(
        self,
        document: dict[str, Any],
        tool_id: str,
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]] | None, int | None, dict[str, Any] | None]:
        normalized_tool_id = str(tool_id or "").strip()
        raw_tools = document.get("tools")
        if isinstance(raw_tools, list):
            for index, item in enumerate(raw_tools):
                if not isinstance(item, dict):
                    continue
                if str(item.get("id") or "").strip() == normalized_tool_id:
                    return item, raw_tools, index, None

        raw_sources = document.get("sources")
        if isinstance(raw_sources, list):
            for source in raw_sources:
                if not isinstance(source, dict):
                    continue
                source_tools = source.get("tools")
                if not isinstance(source_tools, list):
                    continue
                for index, item in enumerate(source_tools):
                    if not isinstance(item, dict):
                        continue
                    if str(item.get("id") or "").strip() == normalized_tool_id:
                        return item, source_tools, index, source

        return None, None, None, None

    def _find_source_name(self, document: dict[str, Any], source_id: str) -> str | None:
        raw_sources = document.get("sources")
        if not isinstance(raw_sources, list):
            return None
        for source in raw_sources:
            if not isinstance(source, dict):
                continue
            if str(source.get("id") or "").strip() != source_id:
                continue
            return str(source.get("name") or "").strip() or None
        return None

    def _cleanup_managed_empty_source(self, document: dict[str, Any], source_id: str) -> None:
        if not source_id:
            return
        raw_sources = document.get("sources")
        if not isinstance(raw_sources, list):
            return

        still_referenced = False
        raw_tools = document.get("tools")
        if isinstance(raw_tools, list):
            still_referenced = any(
                isinstance(item, dict) and str(item.get("source") or "").strip() == source_id
                for item in raw_tools
            )

        if still_referenced:
            return

        for index, source in enumerate(raw_sources):
            if not isinstance(source, dict):
                continue
            if str(source.get("id") or "").strip() != source_id:
                continue
            registry = source.get("registry") if isinstance(source.get("registry"), dict) else {}
            managed_by = str(registry.get("managed_by") or "").strip()
            if source_id == CONTROL_PLANE_SKILL_SOURCE_ID or source_id == CONTROL_PLANE_MCP_SOURCE_ID or managed_by == "control_plane":
                raw_sources.pop(index)
            return

    def _resolve_default_mcp_source(self, document: dict[str, Any]) -> tuple[str, str]:
        sources = document.get("sources")
        if isinstance(sources, list):
            for item in sources:
                if not isinstance(item, dict):
                    continue
                if str(item.get("kind") or "").strip().lower() != "mcp_registry":
                    continue
                source_id = str(item.get("id") or "").strip()
                source_name = str(item.get("name") or "").strip()
                if source_id:
                    return source_id, source_name or CONTROL_PLANE_MCP_SOURCE_NAME
        return CONTROL_PLANE_MCP_SOURCE_ID, CONTROL_PLANE_MCP_SOURCE_NAME

    def _registry_tool_exists(self, document: dict[str, Any], tool_id: str) -> bool:
        raw_tools = document.get("tools")
        if isinstance(raw_tools, list) and any(
            str(item.get("id") or "").strip() == tool_id for item in raw_tools if isinstance(item, dict)
        ):
            return True

        raw_sources = document.get("sources")
        if not isinstance(raw_sources, list):
            return False
        for source in raw_sources:
            if not isinstance(source, dict):
                continue
            source_tools = source.get("tools")
            if not isinstance(source_tools, list):
                continue
            if any(str(item.get("id") or "").strip() == tool_id for item in source_tools if isinstance(item, dict)):
                return True
        return False

    def _append_registry_tool(self, document: dict[str, Any], tool: dict[str, Any]) -> None:
        raw_tools = document.get("tools")
        if not isinstance(raw_tools, list):
            raw_tools = []
            document["tools"] = raw_tools
        raw_tools.append(deepcopy(tool))
        document["version"] = _utc_now_iso().split("T", 1)[0]
        document.setdefault("mode", "external_only")

    def _ensure_registry_source(
        self,
        document: dict[str, Any],
        *,
        source_id: str,
        source_name: str,
        kind: str,
        registry_origin: str,
        default_notes: list[str],
        default_config_summary: dict[str, Any],
    ) -> None:
        raw_sources = document.get("sources")
        if not isinstance(raw_sources, list):
            raw_sources = []
            document["sources"] = raw_sources

        for item in raw_sources:
            if not isinstance(item, dict):
                continue
            if str(item.get("id") or "").strip() != source_id:
                continue
            item["name"] = source_name
            item["kind"] = kind
            item["enabled"] = True
            registry = item.get("registry")
            if not isinstance(registry, dict):
                registry = {}
                item["registry"] = registry
            registry.setdefault("origin", registry_origin)
            registry["bridge_enabled"] = True
            registry["managed_by"] = "control_plane"
            config_summary = item.get("config_summary")
            if not isinstance(config_summary, dict):
                config_summary = {}
                item["config_summary"] = config_summary
            for key, value in default_config_summary.items():
                config_summary.setdefault(key, deepcopy(value))
            notes = item.get("notes")
            if not isinstance(notes, list):
                notes = []
                item["notes"] = notes
            for note in default_notes:
                if note not in notes:
                    notes.append(note)
            return

        raw_sources.append(
            {
                "id": source_id,
                "name": source_name,
                "kind": kind,
                "enabled": True,
                "registry": {
                    "origin": registry_origin,
                    "bridge_enabled": True,
                    "managed_by": "control_plane",
                },
                "config_summary": deepcopy(default_config_summary),
                "notes": list(default_notes),
            }
        )

    def _load_external_registry_document_for_write(self) -> tuple[dict[str, Any], Path]:
        document = self._read_external_registry_document()
        registry_path = self._resolve_external_registry_write_path()
        return document, registry_path

    def _read_external_registry_document(self) -> dict[str, Any]:
        registry_file = str(os.getenv(EXTERNAL_TOOL_SOURCES_FILE_ENV, "")).strip()
        file_candidates: list[Path] = []
        if registry_file:
            registry_path = Path(registry_file)
            if not registry_path.is_absolute():
                registry_path = PROJECT_ROOT / registry_path
            file_candidates.append(registry_path)
        file_candidates.extend(DEFAULT_EXTERNAL_REGISTRY_FALLBACK_PATHS)

        checked_paths: set[Path] = set()
        for registry_path in [*file_candidates, PROJECT_EXTERNAL_REGISTRY_PATH]:
            if registry_path in checked_paths:
                continue
            checked_paths.add(registry_path)
            try:
                raw = registry_path.read_text(encoding="utf-8")
            except OSError:
                continue
            payload = _safe_parse_json(raw, env_key=f"{EXTERNAL_TOOL_SOURCES_FILE_ENV}={registry_path}")
            if payload is None:
                continue
            return self._normalize_external_registry_document(payload)

        for env_key in EXTERNAL_TOOL_SOURCES_JSON_ENV_KEYS:
            raw = str(os.getenv(env_key, "")).strip()
            if not raw:
                continue
            payload = _safe_parse_json(raw, env_key=env_key)
            if payload is None:
                continue
            return self._normalize_external_registry_document(payload)

        return self._normalize_external_registry_document({})

    def _resolve_external_registry_write_path(self) -> Path:
        registry_file = str(os.getenv(EXTERNAL_TOOL_SOURCES_FILE_ENV, "")).strip()
        candidates: list[Path] = []
        if registry_file:
            registry_path = Path(registry_file)
            if not registry_path.is_absolute():
                registry_path = PROJECT_ROOT / registry_path
            candidates.append(registry_path)
        candidates.extend(DEFAULT_EXTERNAL_REGISTRY_FALLBACK_PATHS)
        candidates.append(PROJECT_EXTERNAL_REGISTRY_PATH)

        checked_paths: set[Path] = set()
        for candidate in candidates:
            if candidate in checked_paths:
                continue
            checked_paths.add(candidate)
            try:
                candidate.parent.mkdir(parents=True, exist_ok=True)
            except OSError:
                continue
            os.environ[EXTERNAL_TOOL_SOURCES_FILE_ENV] = str(candidate)
            return candidate

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to access external registry file",
        )

    def _write_external_registry_document(self, path: Path, document: dict[str, Any]) -> None:
        document["version"] = _utc_now_iso().split("T", 1)[0]
        document.setdefault("mode", "external_only")
        try:
            path.write_text(
                json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to write external registry file: {exc}",
            ) from exc

    def _normalize_external_registry_document(self, payload: Any) -> dict[str, Any]:
        if isinstance(payload, list):
            return {
                "version": _utc_now_iso().split("T", 1)[0],
                "mode": "external_only",
                "sources": [deepcopy(item) for item in payload if isinstance(item, dict)],
                "tools": [],
            }

        if not isinstance(payload, dict):
            payload = {}

        normalized = deepcopy(payload)
        raw_sources = normalized.get("sources")
        normalized["sources"] = [deepcopy(item) for item in raw_sources if isinstance(item, dict)] if isinstance(raw_sources, list) else []
        raw_tools = normalized.get("tools")
        normalized["tools"] = [deepcopy(item) for item in raw_tools if isinstance(item, dict)] if isinstance(raw_tools, list) else []
        normalized.setdefault("version", _utc_now_iso().split("T", 1)[0])
        normalized.setdefault("mode", "external_only")
        return normalized

    def _merge_registry_tags(self, value: Any, *, defaults: list[str]) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for item in [*defaults, *_as_tags(value)]:
            normalized = str(item or "").strip()
            if not normalized:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(normalized)
        return merged

    def _normalize_registry_base_url(self, value: Any) -> str:
        base_url = str(value or "").strip()
        parsed = urlparse(base_url)
        if not base_url or parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="base_url must be a valid http(s) URL",
            )
        return base_url.rstrip("/")

    def _normalize_registry_path(self, value: Any, *, default: str) -> str:
        normalized = str(value or default).strip() or default
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"
        return normalized

    def _normalize_registry_method(self, value: Any, *, default: str) -> str:
        normalized = str(value or default).strip().upper() or default
        if normalized not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported HTTP method")
        return normalized

    def _normalize_timeout_seconds(self, value: Any, *, default: float) -> float:
        try:
            resolved = float(value if value not in {None, ""} else default)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="timeout_seconds must be numeric") from exc
        if resolved <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="timeout_seconds must be greater than 0",
            )
        return resolved

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
        file_candidates: list[Path] = []
        if registry_file:
            registry_path = Path(registry_file)
            if not registry_path.is_absolute():
                registry_path = PROJECT_ROOT / registry_path
            file_candidates.append(registry_path)
        file_candidates.extend(DEFAULT_EXTERNAL_REGISTRY_FALLBACK_PATHS)

        checked_paths: set[Path] = set()
        configured_path = file_candidates[0] if file_candidates else None
        for registry_path in file_candidates:
            if registry_path in checked_paths:
                continue
            checked_paths.add(registry_path)
            try:
                raw = registry_path.read_text(encoding="utf-8")
            except OSError as exc:
                if registry_file or registry_path in DEFAULT_EXTERNAL_REGISTRY_FALLBACK_PATHS:
                    logger.warning(
                        "Failed to read external tool sources registry file %s: %s",
                        registry_path,
                        exc,
                    )
                continue
            if configured_path is not None and registry_path != configured_path:
                logger.info(
                    "External tool sources registry fallback activated: %s -> %s",
                    configured_path,
                    registry_path,
                )
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
        effective_registration_kind = str(
            item.get("registration_kind")
            or config_summary_payload.get("registration_kind")
            or registration_kind
        ).strip() or registration_kind
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
            "registration_kind": effective_registration_kind,
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
            "capabilities": _as_tags(item.get("capabilities")),
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
            metadata = ability.get("metadata") if isinstance(ability.get("metadata"), dict) else {}
            if (
                str(ability.get("source") or "").strip().lower() == "local_brain_skill_library"
                or str(metadata.get("registration_scope") or "").strip().lower() == "brain_skill_library"
            ):
                continue
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

    def _scan_external_skill_registry_source(self) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        skill_items = external_skill_registry_service.list_skills(include_offline=True)
        if not skill_items:
            return None, []

        tools: list[dict[str, Any]] = []
        for ability in skill_items:
            invocation = deepcopy(ability.get("invocation") or {})
            health_status = (
                "healthy"
                if ability.get("routable", False)
                else str(ability.get("health_status") or "offline")
            )
            tools.append(
                {
                    "id": str(ability.get("id") or ability.get("name") or ""),
                    "name": str(ability.get("name") or ability.get("id") or ""),
                    "type": "skill",
                    "source": EXTERNAL_SKILL_SOURCE_ID,
                    "source_id": EXTERNAL_SKILL_SOURCE_ID,
                    "source_kind": "external_skill_registry",
                    "enabled": bool(ability.get("routable", False)),
                    "description": str(ability.get("description") or ""),
                    "tags": list(ability.get("tags") or []),
                    "provider": str(invocation.get("protocol") or "external-http"),
                    "bridge_mode": "external_skill_registry",
                    "health_status": health_status,
                    "agent_ids": [],
                    "permissions": {
                        "requires_permission": False,
                        "scopes": ["agents:read"],
                        "roles": ["admin", "operator", "power_user", "viewer"],
                        "approval_required": False,
                    },
                    "input_schema": deepcopy(ability.get("input_schema") or {}),
                    "output_schema": deepcopy(ability.get("output_schema") or {}),
                    "recent_call_summary": _default_recent_call_summary(),
                    "health_summary": deepcopy(ability.get("health_summary") or {}),
                    "config_summary": {
                        "version": ability.get("version"),
                        "capabilities": list(ability.get("capabilities") or []),
                        "invocation": invocation,
                    },
                }
            )

        source = {
            "id": EXTERNAL_SKILL_SOURCE_ID,
            "name": "External Skill Registry",
            "kind": "external_skill_registry",
            "path": "",
            "status": "available",
            "scan_status": "success" if tools else "empty",
            "tool_count": len(tools),
            "notes": ["外接 Skill 通过正式注册中心进入主脑，不依赖本地目录扫描。"],
            "registry": {
                "source_id": EXTERNAL_SKILL_SOURCE_ID,
                "origin": "external_skill_registry",
                "bridge_enabled": True,
            },
            "origin": "external_skill_registry",
            "config_summary": {
                "path_exists": True,
                "scanned_at": _utc_now_iso(),
                "registered_count": len(skill_items),
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
