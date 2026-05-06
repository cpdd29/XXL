import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status

from app.modules.agent_config.registries.agent_config_service import agent_config_service, build_agent_config_summary
from app.modules.agent_config.registries.brain_skill_service import brain_skill_service
from app.modules.agent_config.registries.capability_scope import CAPABILITY_SCOPE_SHARED
from app.modules.agent_config.registries.external_agent_registry_service import (
    external_agent_registry_service,
    redact_external_agent_payload,
)
from app.platform.persistence.persistence_service import persistence_service
from app.platform.config.settings_service import get_agent_api_runtime_settings
from app.platform.persistence.runtime_store import LEGACY_AGENT_IDS, store
from app.modules.agent_config.registries.tool_source_service import tool_source_service

DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 15
DEFAULT_HEARTBEAT_TIMEOUT_SECONDS = 90
MIN_HEARTBEAT_INTERVAL_SECONDS = 3
MAX_HEARTBEAT_INTERVAL_SECONDS = 3600
MIN_HEARTBEAT_TIMEOUT_SECONDS = 10
MAX_HEARTBEAT_TIMEOUT_SECONDS = 24 * 3600
HEARTBEAT_DEGRADED_RATIO = 2.0
ONLINE_RUNTIME_STATUSES = {"online", "unknown"}
ALLOWED_AGENT_STATUSES = {
    "running",
    "idle",
    "waiting",
    "busy",
    "degraded",
    "offline",
    "maintenance",
    "error",
}
DEFAULT_AGENT_TYPE = "default"
MODEL_BINDING_RUNTIME_KEY = "agent_binding"
SKILL_BINDING_RUNTIME_KEY = "brain_skill_binding"
TOOL_BINDING_RUNTIME_KEY = "tool_binding"
WORKFLOW_BINDING_RUNTIME_KEY = "agent_workflow_binding"
DEFAULT_AGENT_WORKFLOW_CONTRACT_VERSION = "agent-workflow-contract-v1"
WORKFLOW_BINDING_UNSET = object()
PROVIDER_LABELS = {
    "openai": "OpenAI",
    "codex": "Codex",
    "claude": "Claude",
    "kimi": "Kimi",
    "minimax": "MiniMax",
    "gemini": "Gemini",
    "deepseek": "DeepSeek",
    "openapi": "OpenAPI Compatible",
}


def _workflow_exists(workflow_id: str | None) -> bool:
    normalized_workflow_id = _normalize_text(workflow_id)
    if not normalized_workflow_id:
        return False

    get_workflow = getattr(persistence_service, "get_workflow", None)
    if callable(get_workflow):
        persisted = get_workflow(normalized_workflow_id)
        if isinstance(persisted, dict):
            return True

    list_workflows = getattr(persistence_service, "list_workflows", None)
    if callable(list_workflows):
        persisted_items = list_workflows()
        if isinstance(persisted_items, list) and any(
            str(item.get("id") or "").strip() == normalized_workflow_id
            for item in persisted_items
            if isinstance(item, dict)
        ):
            return True

    if any(str(item.get("id") or "").strip() == normalized_workflow_id for item in store.workflows):
        return True

    return False


def _normalize_contract_payload(value: Any, *, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} 必须为对象",
        )
    return store.clone(value)


def _payload_value(payload: dict[str, Any], *keys: str) -> tuple[bool, Any]:
    for key in keys:
        if key in payload:
            return True, payload[key]
    return False, WORKFLOW_BINDING_UNSET


def _load_agents() -> list[dict]:
    database_agents = persistence_service.list_agents()
    if database_agents is not None:
        base_agents = database_agents
    elif getattr(persistence_service, "enabled", False):
        base_agents = []
    else:
        base_agents = store.clone(store.agents)

    merged: dict[str, dict] = {
        str(agent.get("id") or "").strip(): store.clone(agent)
        for agent in base_agents
        if str(agent.get("id") or "").strip()
        and str(agent.get("id") or "").strip() not in LEGACY_AGENT_IDS
    }
    for external_agent in external_agent_registry_service.list_agents(include_offline=True):
        agent_id = str(external_agent.get("id") or "").strip()
        if not agent_id or agent_id in LEGACY_AGENT_IDS:
            continue
        existing = merged.get(agent_id)
        if existing is not None and not _should_refresh_from_external_registry(existing):
            continue
        merged[agent_id] = store.clone(redact_external_agent_payload(external_agent))
    return list(merged.values())


def _find_cached_agent(agent_id: str) -> dict | None:
    for agent in store.agents:
        if agent["id"] == agent_id:
            return agent
    return None


def _should_refresh_from_external_registry(agent_payload: dict[str, Any]) -> bool:
    config_summary = agent_payload.get("config_summary") if isinstance(agent_payload.get("config_summary"), dict) else {}
    config_snapshot = agent_payload.get("config_snapshot") if isinstance(agent_payload.get("config_snapshot"), dict) else {}
    metadata = agent_payload.get("metadata") if isinstance(agent_payload.get("metadata"), dict) else {}
    runtime = config_snapshot.get("runtime") if isinstance(config_snapshot.get("runtime"), dict) else {}

    source = str(
        config_summary.get("source")
        or metadata.get("source")
        or runtime.get("source")
        or ""
    ).strip().lower()
    snapshot_status = str(config_snapshot.get("status") or "").strip().lower()

    return source in {"external_agent_registry", "control_plane"} or snapshot_status == "external_registered"


def _sync_cached_agent(agent_payload: dict) -> dict:
    agent_id = str(agent_payload.get("id") or "").strip()
    cached_agent = _find_cached_agent(agent_id)
    payload = store.clone(agent_payload)
    if cached_agent is None:
        store.agents.append(payload)
        return payload

    cached_agent.clear()
    cached_agent.update(payload)
    return cached_agent


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_datetime(value: object) -> datetime | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    candidate = normalized.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _normalize_agent_status(value: object) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in ALLOWED_AGENT_STATUSES:
        return normalized
    return None


def _normalize_seconds(value: object, *, default: int, minimum: int, maximum: int) -> int:
    if value in {"", None}:
        return default
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return default
    if normalized < minimum:
        return minimum
    if normalized > maximum:
        return maximum
    return normalized


def _normalize_text(value: object, *, lowercase: bool = False) -> str:
    normalized = str(value or "").strip()
    return normalized.lower() if lowercase else normalized


def _normalize_identifier_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    seen: set[str] = set()
    for raw_item in value:
        normalized = _normalize_text(raw_item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        items.append(normalized)
    return items


def _enabled_provider_models() -> dict[str, dict[str, str]]:
    runtime_settings = get_agent_api_runtime_settings()
    providers = runtime_settings.get("providers")
    if not isinstance(providers, dict):
        return {}

    result: dict[str, dict[str, str]] = {}
    for provider_key, provider in providers.items():
        if not isinstance(provider, dict):
            continue
        normalized_key = _normalize_text(provider_key, lowercase=True)
        if not normalized_key or not bool(provider.get("enabled")):
            continue
        model = _normalize_text(provider.get("model"))
        if not model:
            continue
        result[normalized_key] = {
            "provider_key": normalized_key,
            "provider_label": PROVIDER_LABELS.get(normalized_key, normalized_key.title()),
            "model": model,
        }
    return result


def _guess_provider_key_from_model(model: object) -> str | None:
    normalized = _normalize_text(model, lowercase=True)
    if not normalized:
        return None
    if "claude" in normalized:
        return "claude"
    if "kimi" in normalized or "moonshot" in normalized:
        return "kimi"
    if "deepseek" in normalized:
        return "deepseek"
    if "gemini" in normalized:
        return "gemini"
    if "codex" in normalized:
        return "codex"
    if normalized.startswith("gpt"):
        return "openai"
    return None


def _runtime_snapshot(agent: dict) -> dict:
    snapshot = agent.get("config_snapshot")
    if not isinstance(snapshot, dict):
        return {}
    runtime = snapshot.get("runtime")
    if not isinstance(runtime, dict):
        return {}
    return store.clone(runtime)


def _runtime_model_binding(snapshot: dict | None) -> dict[str, str | None] | None:
    if not isinstance(snapshot, dict):
        return None
    runtime = snapshot.get("runtime")
    if not isinstance(runtime, dict):
        return None
    binding = runtime.get(MODEL_BINDING_RUNTIME_KEY)
    if not isinstance(binding, dict):
        return None

    provider_key = _normalize_text(
        binding.get("provider_key", binding.get("providerKey")),
        lowercase=True,
    ) or None
    model = _normalize_text(binding.get("model")) or None
    source = _normalize_text(binding.get("source")) or "manual"
    if not provider_key and model:
        provider_key = _guess_provider_key_from_model(model)
    if not provider_key and not model:
        return None
    return {
        "provider_key": provider_key,
        "provider_label": PROVIDER_LABELS.get(provider_key, provider_key.title()) if provider_key else None,
        "model": model,
        "source": source,
    }


def _runtime_skill_binding(snapshot: dict | None) -> dict[str, Any] | None:
    if not isinstance(snapshot, dict):
        return None
    runtime = snapshot.get("runtime")
    if isinstance(runtime, dict):
        binding = runtime.get(SKILL_BINDING_RUNTIME_KEY)
        if isinstance(binding, dict):
            return {
                "skill_ids": _normalize_identifier_list(binding.get("skill_ids") or binding.get("skillIds")),
                "source": _normalize_text(binding.get("source")) or "manual",
            }
        if isinstance(binding, list):
            return {
                "skill_ids": _normalize_identifier_list(binding),
                "source": "manual",
            }

    agent_doc = snapshot.get("agent")
    if not isinstance(agent_doc, dict):
        return None
    skill_ids = _normalize_identifier_list(agent_doc.get("skill_ids") or agent_doc.get("skillIds"))
    if not skill_ids and "skill_ids" not in agent_doc and "skillIds" not in agent_doc:
        return None
    return {"skill_ids": skill_ids, "source": "config"}


def _resolve_agent_model_binding(agent_payload: dict) -> dict[str, str | None] | None:
    snapshot = agent_payload.get("config_snapshot")
    runtime_binding = _runtime_model_binding(snapshot)
    if runtime_binding is not None:
        return runtime_binding

    if not isinstance(snapshot, dict):
        return None

    agent_doc = snapshot.get("agent")
    if not isinstance(agent_doc, dict):
        return None

    provider_key = _normalize_text(agent_doc.get("provider"), lowercase=True) or None
    model = _normalize_text(agent_doc.get("model")) or None
    if not provider_key and model:
        provider_key = _guess_provider_key_from_model(model)
    if not provider_key and not model:
        return None
    return {
        "provider_key": provider_key,
        "provider_label": PROVIDER_LABELS.get(provider_key, provider_key.title()) if provider_key else None,
        "model": model,
        "source": "config",
    }


def _resolve_agent_skill_binding(agent_payload: dict) -> list[str]:
    snapshot = agent_payload.get("config_snapshot")
    binding = _runtime_skill_binding(snapshot)
    if binding is None:
        return []
    return _normalize_identifier_list(binding.get("skill_ids"))


def _resolve_agent_soul(agent_payload: dict | None) -> str | None:
    if not isinstance(agent_payload, dict):
        return None
    snapshot = agent_payload.get("config_snapshot")
    if not isinstance(snapshot, dict):
        return None
    soul = _normalize_text(snapshot.get("soul"))
    return soul or None


def _runtime_tool_binding(snapshot: dict | None) -> dict[str, Any] | None:
    if not isinstance(snapshot, dict):
        return None
    runtime = snapshot.get("runtime")
    if isinstance(runtime, dict):
        binding = runtime.get(TOOL_BINDING_RUNTIME_KEY)
        if isinstance(binding, dict):
            return {
                "tool_ids": _normalize_identifier_list(
                    binding.get("tool_ids")
                    or binding.get("toolIds")
                    or binding.get("bound_tool_ids")
                    or binding.get("boundToolIds")
                ),
                "source": _normalize_text(binding.get("source")) or "manual",
            }
        if isinstance(binding, list):
            return {
                "tool_ids": _normalize_identifier_list(binding),
                "source": "manual",
            }

    agent_doc = snapshot.get("agent")
    if not isinstance(agent_doc, dict):
        return None
    tool_ids = _normalize_identifier_list(
        agent_doc.get("tool_ids")
        or agent_doc.get("toolIds")
        or agent_doc.get("bound_tool_ids")
        or agent_doc.get("boundToolIds")
    )
    if not tool_ids and all(
        key not in agent_doc for key in ("tool_ids", "toolIds", "bound_tool_ids", "boundToolIds")
    ):
        return None
    return {"tool_ids": tool_ids, "source": "config"}


def _runtime_workflow_binding(snapshot: dict | None) -> dict[str, Any] | None:
    if not isinstance(snapshot, dict):
        return None
    runtime = snapshot.get("runtime")
    if isinstance(runtime, dict):
        binding = runtime.get(WORKFLOW_BINDING_RUNTIME_KEY)
        if isinstance(binding, dict):
            workflow_id = _normalize_text(
                binding.get("agent_workflow_id") or binding.get("agentWorkflowId")
            ) or None
            input_contract = store.clone(
                binding.get("input_contract") or binding.get("inputContract")
            ) if isinstance(binding.get("input_contract") or binding.get("inputContract"), dict) else {}
            output_contract = store.clone(
                binding.get("output_contract") or binding.get("outputContract")
            ) if isinstance(binding.get("output_contract") or binding.get("outputContract"), dict) else {}
            contract_version = _normalize_text(
                binding.get("contract_version") or binding.get("contractVersion")
            ) or None
            if not workflow_id and not input_contract and not output_contract and not contract_version:
                return None
            return {
                "agent_workflow_id": workflow_id,
                "input_contract": input_contract,
                "output_contract": output_contract,
                "contract_version": contract_version,
                "source": _normalize_text(binding.get("source")) or "manual",
            }

    agent_doc = snapshot.get("agent")
    if not isinstance(agent_doc, dict):
        return None
    workflow_id = _normalize_text(agent_doc.get("agent_workflow_id") or agent_doc.get("agentWorkflowId")) or None
    input_contract = store.clone(agent_doc.get("input_contract") or agent_doc.get("inputContract")) if isinstance(
        agent_doc.get("input_contract") or agent_doc.get("inputContract"),
        dict,
    ) else {}
    output_contract = store.clone(agent_doc.get("output_contract") or agent_doc.get("outputContract")) if isinstance(
        agent_doc.get("output_contract") or agent_doc.get("outputContract"),
        dict,
    ) else {}
    contract_version = _normalize_text(
        agent_doc.get("contract_version") or agent_doc.get("contractVersion")
    ) or None
    if not workflow_id and not input_contract and not output_contract and not contract_version:
        return None
    return {
        "agent_workflow_id": workflow_id,
        "input_contract": input_contract,
        "output_contract": output_contract,
        "contract_version": contract_version,
        "source": "config",
    }


def _runtime_agent_metadata(snapshot: dict | None) -> dict[str, Any] | None:
    if not isinstance(snapshot, dict):
        return None
    runtime = snapshot.get("runtime")
    if isinstance(runtime, dict):
        metadata_binding = runtime.get("agent_metadata")
        if isinstance(metadata_binding, dict):
            metadata = metadata_binding.get("metadata")
            if isinstance(metadata, dict) and metadata:
                return store.clone(metadata)

    agent_doc = snapshot.get("agent")
    if not isinstance(agent_doc, dict):
        return None
    metadata = agent_doc.get("metadata")
    if isinstance(metadata, dict) and metadata:
        return store.clone(metadata)
    return None


def _available_tool_map(
    *,
    refresh: bool = False,
    tenant_id: str | None = None,
    include_all_tenants: bool = True,
) -> dict[str, dict[str, Any]]:
    available_tools: dict[str, dict[str, Any]] = {}
    for tool in tool_source_service.list_tools(
        refresh=refresh,
        tenant_id=tenant_id,
        include_all_tenants=include_all_tenants,
    ):
        tool_id = _normalize_text(tool.get("id"))
        if not tool_id:
            continue
        available_tools[tool_id] = tool
    return available_tools


def _validate_tool_ids(
    tool_ids: list[str],
    *,
    refresh: bool = False,
    tenant_id: str | None = None,
    include_all_tenants: bool = True,
) -> list[str]:
    normalized_tool_ids = _normalize_identifier_list(tool_ids)
    if not normalized_tool_ids:
        return []

    available_tools = _available_tool_map(
        refresh=refresh,
        tenant_id=tenant_id,
        include_all_tenants=include_all_tenants,
    )
    missing_tool_ids = [tool_id for tool_id in normalized_tool_ids if tool_id not in available_tools]
    if missing_tool_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"以下 Tool 不存在或当前租户不可绑定：{', '.join(missing_tool_ids)}",
        )
    return normalized_tool_ids


def _format_missing_tool_binding_warning(tool_ids: list[str]) -> str:
    normalized_tool_ids = _normalize_identifier_list(tool_ids)
    if not normalized_tool_ids:
        return ""
    return f"以下 Tool 已失效或当前租户不可见：{', '.join(normalized_tool_ids)}"


def _bound_tool_payload(
    tool_id: str,
    tool_doc: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(tool_doc, dict):
        return {
            "id": tool_id,
            "name": tool_id,
            "type": "unavailable",
            "description": None,
            "source": None,
            "scope": CAPABILITY_SCOPE_SHARED,
            "owner_tenant_id": None,
        }
    return {
        "id": tool_id,
        "name": _normalize_text(tool_doc.get("name")) or tool_id,
        "type": _normalize_text(tool_doc.get("type")) or "unknown",
        "description": _normalize_text(tool_doc.get("description")) or None,
        "source": _normalize_text(tool_doc.get("source") or tool_doc.get("source_id")) or None,
        "scope": _normalize_text(tool_doc.get("scope")) or CAPABILITY_SCOPE_SHARED,
        "owner_tenant_id": _normalize_text(tool_doc.get("owner_tenant_id")) or None,
    }


def _resolve_bound_tools_result(
    tool_ids: list[str],
    *,
    refresh: bool = False,
    tenant_id: str | None = None,
    include_all_tenants: bool = True,
    strict: bool = True,
) -> tuple[list[dict[str, Any]], list[str]]:
    normalized_tool_ids = _normalize_identifier_list(tool_ids)
    if not normalized_tool_ids:
        return [], []

    available_tools = _available_tool_map(
        refresh=refresh,
        tenant_id=tenant_id,
        include_all_tenants=include_all_tenants,
    )
    missing_tool_ids = [tool_id for tool_id in normalized_tool_ids if tool_id not in available_tools]
    if strict and missing_tool_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"以下 Tool 不存在或当前租户不可绑定：{', '.join(missing_tool_ids)}",
        )

    resolved_tools = [
        _bound_tool_payload(tool_id, available_tools.get(tool_id))
        for tool_id in normalized_tool_ids
    ]
    return resolved_tools, missing_tool_ids


def _resolve_bound_tools(
    tool_ids: list[str],
    *,
    refresh: bool = False,
    tenant_id: str | None = None,
    include_all_tenants: bool = True,
) -> list[dict[str, Any]]:
    resolved_tools, _ = _resolve_bound_tools_result(
        tool_ids,
        refresh=refresh,
        tenant_id=tenant_id,
        include_all_tenants=include_all_tenants,
        strict=True,
    )
    return resolved_tools


def _resolve_bound_tools_safe(
    tool_ids: list[str],
    *,
    refresh: bool = False,
    tenant_id: str | None = None,
    include_all_tenants: bool = True,
) -> tuple[list[dict[str, Any]], list[str]]:
    return _resolve_bound_tools_result(
        tool_ids,
        refresh=refresh,
        tenant_id=tenant_id,
        include_all_tenants=include_all_tenants,
        strict=False,
    )


def _resolve_agent_tool_binding(agent_payload: dict) -> list[str]:
    snapshot = agent_payload.get("config_snapshot")
    binding = _runtime_tool_binding(snapshot)
    if binding is None:
        return []
    return _normalize_identifier_list(binding.get("tool_ids"))


def _resolve_agent_workflow_binding(agent_payload: dict) -> dict[str, Any] | None:
    snapshot = agent_payload.get("config_snapshot")
    binding = _runtime_workflow_binding(snapshot)
    if binding is None:
        return None
    return {
        "agent_workflow_id": _normalize_text(binding.get("agent_workflow_id")) or None,
        "input_contract": store.clone(binding.get("input_contract"))
        if isinstance(binding.get("input_contract"), dict)
        else {},
        "output_contract": store.clone(binding.get("output_contract"))
        if isinstance(binding.get("output_contract"), dict)
        else {},
        "contract_version": _normalize_text(binding.get("contract_version")) or None,
    }


def _build_manual_config_snapshot(agent: dict) -> dict[str, Any]:
    return {
        "agent_id": str(agent.get("id") or "").strip(),
        "status": "manual",
        "directory": None,
        "version": None,
        "loaded_at": _now().isoformat(),
        "files_loaded": [],
        "warnings": [],
        "agent": {
            "agent_id": str(agent.get("id") or "").strip(),
            "name": str(agent.get("name") or "").strip(),
            "type": str(agent.get("type") or DEFAULT_AGENT_TYPE).strip().lower() or DEFAULT_AGENT_TYPE,
        },
        "soul": None,
        "tools": None,
        "memory_rules": None,
        "examples": [],
        "runtime": {},
    }


def _apply_model_binding_to_snapshot(
    snapshot: dict | None,
    *,
    agent: dict,
    provider_key: str | None,
    model: str | None,
    source: str = "manual",
) -> dict[str, Any]:
    next_snapshot = store.clone(snapshot) if isinstance(snapshot, dict) else _build_manual_config_snapshot(agent)
    agent_doc = next_snapshot.get("agent")
    if not isinstance(agent_doc, dict):
        agent_doc = {}
    agent_doc["agent_id"] = str(agent.get("id") or "").strip()
    agent_doc["name"] = str(agent.get("name") or "").strip()
    agent_doc["type"] = str(agent.get("type") or DEFAULT_AGENT_TYPE).strip().lower() or DEFAULT_AGENT_TYPE
    if provider_key:
        agent_doc["provider"] = provider_key
    if model:
        agent_doc["model"] = model
    next_snapshot["agent"] = agent_doc

    runtime = next_snapshot.get("runtime")
    if not isinstance(runtime, dict):
        runtime = {}
    runtime[MODEL_BINDING_RUNTIME_KEY] = {
        "provider_key": provider_key,
        "model": model,
        "source": source,
    }
    next_snapshot["runtime"] = runtime
    next_snapshot["loaded_at"] = _now().isoformat()
    return next_snapshot


def _apply_skill_binding_to_snapshot(
    snapshot: dict | None,
    *,
    agent: dict,
    skill_ids: list[str],
    source: str = "manual",
) -> dict[str, Any]:
    next_snapshot = store.clone(snapshot) if isinstance(snapshot, dict) else _build_manual_config_snapshot(agent)
    normalized_skill_ids = _normalize_identifier_list(skill_ids)
    agent_doc = next_snapshot.get("agent")
    if not isinstance(agent_doc, dict):
        agent_doc = {}
    agent_doc["agent_id"] = str(agent.get("id") or "").strip()
    agent_doc["name"] = str(agent.get("name") or "").strip()
    agent_doc["type"] = str(agent.get("type") or DEFAULT_AGENT_TYPE).strip().lower() or DEFAULT_AGENT_TYPE
    agent_doc["skill_ids"] = normalized_skill_ids
    next_snapshot["agent"] = agent_doc

    runtime = next_snapshot.get("runtime")
    if not isinstance(runtime, dict):
        runtime = {}
    runtime[SKILL_BINDING_RUNTIME_KEY] = {
        "skill_ids": normalized_skill_ids,
        "source": source,
    }
    next_snapshot["runtime"] = runtime
    next_snapshot["loaded_at"] = _now().isoformat()
    return next_snapshot


def _apply_tool_binding_to_snapshot(
    snapshot: dict | None,
    *,
    agent: dict,
    tool_ids: list[str],
    source: str = "manual",
) -> dict[str, Any]:
    next_snapshot = store.clone(snapshot) if isinstance(snapshot, dict) else _build_manual_config_snapshot(agent)
    normalized_tool_ids = _normalize_identifier_list(tool_ids)
    agent_doc = next_snapshot.get("agent")
    if not isinstance(agent_doc, dict):
        agent_doc = {}
    agent_doc["agent_id"] = str(agent.get("id") or "").strip()
    agent_doc["name"] = str(agent.get("name") or "").strip()
    agent_doc["type"] = str(agent.get("type") or DEFAULT_AGENT_TYPE).strip().lower() or DEFAULT_AGENT_TYPE
    agent_doc["tool_ids"] = normalized_tool_ids
    next_snapshot["agent"] = agent_doc

    runtime = next_snapshot.get("runtime")
    if not isinstance(runtime, dict):
        runtime = {}
    runtime[TOOL_BINDING_RUNTIME_KEY] = {
        "tool_ids": normalized_tool_ids,
        "source": source,
    }
    next_snapshot["runtime"] = runtime
    next_snapshot["loaded_at"] = _now().isoformat()
    return next_snapshot


def _apply_workflow_binding_to_snapshot(
    snapshot: dict | None,
    *,
    agent: dict,
    agent_workflow_id: str | None,
    input_contract: dict[str, Any] | None,
    output_contract: dict[str, Any] | None,
    contract_version: str | None,
    source: str = "manual",
) -> dict[str, Any]:
    next_snapshot = store.clone(snapshot) if isinstance(snapshot, dict) else _build_manual_config_snapshot(agent)
    normalized_workflow_id = _normalize_text(agent_workflow_id) or None
    normalized_contract_version = _normalize_text(contract_version) or None
    normalized_input_contract = _normalize_contract_payload(input_contract, field_name="input_contract")
    normalized_output_contract = _normalize_contract_payload(output_contract, field_name="output_contract")
    has_contract_payload = bool(
        normalized_input_contract or normalized_output_contract or normalized_contract_version
    )

    agent_doc = next_snapshot.get("agent")
    if not isinstance(agent_doc, dict):
        agent_doc = {}
    agent_doc["agent_id"] = str(agent.get("id") or "").strip()
    agent_doc["name"] = str(agent.get("name") or "").strip()
    agent_doc["type"] = str(agent.get("type") or DEFAULT_AGENT_TYPE).strip().lower() or DEFAULT_AGENT_TYPE
    if normalized_workflow_id is None and not has_contract_payload:
        agent_doc.pop("agent_workflow_id", None)
        agent_doc.pop("input_contract", None)
        agent_doc.pop("output_contract", None)
        agent_doc.pop("contract_version", None)
    else:
        if normalized_workflow_id is None:
            agent_doc.pop("agent_workflow_id", None)
        else:
            agent_doc["agent_workflow_id"] = normalized_workflow_id
        agent_doc["input_contract"] = store.clone(normalized_input_contract)
        agent_doc["output_contract"] = store.clone(normalized_output_contract)
        agent_doc["contract_version"] = normalized_contract_version
    next_snapshot["agent"] = agent_doc

    runtime = next_snapshot.get("runtime")
    if not isinstance(runtime, dict):
        runtime = {}
    if normalized_workflow_id is None and not has_contract_payload:
        runtime.pop(WORKFLOW_BINDING_RUNTIME_KEY, None)
    else:
        runtime[WORKFLOW_BINDING_RUNTIME_KEY] = {
            "agent_workflow_id": normalized_workflow_id,
            "input_contract": store.clone(normalized_input_contract),
            "output_contract": store.clone(normalized_output_contract),
            "contract_version": normalized_contract_version,
            "source": source,
        }
    next_snapshot["runtime"] = runtime
    next_snapshot["loaded_at"] = _now().isoformat()
    return next_snapshot


def _apply_soul_to_snapshot(
    snapshot: dict | None,
    *,
    agent: dict,
    soul: str | None,
    source: str = "manual",
) -> dict[str, Any]:
    next_snapshot = store.clone(snapshot) if isinstance(snapshot, dict) else _build_manual_config_snapshot(agent)
    normalized_soul = _normalize_text(soul) or None

    agent_doc = next_snapshot.get("agent")
    if not isinstance(agent_doc, dict):
        agent_doc = {}
    agent_doc["agent_id"] = str(agent.get("id") or "").strip()
    agent_doc["name"] = str(agent.get("name") or "").strip()
    agent_doc["type"] = str(agent.get("type") or DEFAULT_AGENT_TYPE).strip().lower() or DEFAULT_AGENT_TYPE
    if normalized_soul is None:
        agent_doc.pop("soul", None)
    else:
        agent_doc["soul"] = normalized_soul
    next_snapshot["agent"] = agent_doc

    if normalized_soul is None:
        next_snapshot["soul"] = None
    else:
        next_snapshot["soul"] = normalized_soul

    files_loaded = next_snapshot.get("files_loaded")
    normalized_files_loaded = [
        str(item or "").strip()
        for item in files_loaded
        if str(item or "").strip()
    ] if isinstance(files_loaded, list) else []
    has_soul_file = "soul.md" in normalized_files_loaded
    if normalized_soul is not None and not has_soul_file:
        normalized_files_loaded.append("soul.md")
    if normalized_soul is None and has_soul_file:
        normalized_files_loaded = [item for item in normalized_files_loaded if item != "soul.md"]
    next_snapshot["files_loaded"] = normalized_files_loaded

    runtime = next_snapshot.get("runtime")
    if not isinstance(runtime, dict):
        runtime = {}
    if normalized_soul is None:
        runtime.pop("soul_binding", None)
    else:
        runtime["soul_binding"] = {
            "source": source,
        }
    next_snapshot["runtime"] = runtime
    next_snapshot["loaded_at"] = _now().isoformat()
    return next_snapshot


def _apply_agent_metadata_to_snapshot(
    snapshot: dict | None,
    *,
    agent: dict,
    metadata: dict[str, Any] | None,
    source: str = "manual",
) -> dict[str, Any]:
    next_snapshot = store.clone(snapshot) if isinstance(snapshot, dict) else _build_manual_config_snapshot(agent)
    normalized_metadata = store.clone(metadata) if isinstance(metadata, dict) else {}

    agent_doc = next_snapshot.get("agent")
    if not isinstance(agent_doc, dict):
        agent_doc = {}
    agent_doc["agent_id"] = str(agent.get("id") or "").strip()
    agent_doc["name"] = str(agent.get("name") or "").strip()
    agent_doc["type"] = str(agent.get("type") or DEFAULT_AGENT_TYPE).strip().lower() or DEFAULT_AGENT_TYPE
    if normalized_metadata:
        agent_doc["metadata"] = normalized_metadata
    else:
        agent_doc.pop("metadata", None)
    next_snapshot["agent"] = agent_doc

    runtime = next_snapshot.get("runtime")
    if not isinstance(runtime, dict):
        runtime = {}
    if normalized_metadata:
        runtime["agent_metadata"] = {
            "metadata": normalized_metadata,
            "source": source,
        }
    else:
        runtime.pop("agent_metadata", None)
    next_snapshot["runtime"] = runtime
    next_snapshot["loaded_at"] = _now().isoformat()
    return next_snapshot


def _build_agent_config_summary_with_bindings(
    snapshot: dict[str, Any] | None,
    *,
    bound_tool_ids: list[str],
    existing_summary: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    summary = build_agent_config_summary(snapshot)
    if not isinstance(summary, dict):
        if isinstance(existing_summary, dict):
            return store.clone(existing_summary)
        return summary

    merged_summary = store.clone(existing_summary) if isinstance(existing_summary, dict) else {}
    if not isinstance(merged_summary, dict):
        merged_summary = {}
    merged_summary.update(summary)

    normalized_tool_ids = _normalize_identifier_list(bound_tool_ids)
    existing_tools_count = merged_summary.get("tools_count")
    try:
        resolved_tools_count = int(existing_tools_count)
    except (TypeError, ValueError):
        resolved_tools_count = 0

    merged_summary["bound_tool_count"] = len(normalized_tool_ids)
    merged_summary["bound_tool_ids"] = normalized_tool_ids
    merged_summary["tools_count"] = max(resolved_tools_count, len(normalized_tool_ids))
    return merged_summary


def _normalize_agent_config_payload(
    payload: dict[str, Any],
    *,
    current_agent: dict | None = None,
    tenant_id: str | None = None,
    include_all_tenants: bool = True,
) -> dict[str, Any]:
    current = current_agent or {}
    name = _normalize_text(payload.get("name", current.get("name")))
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Agent 名称不能为空")

    description = _normalize_text(payload.get("description", current.get("description")))
    agent_type = _normalize_text(payload.get("type", current.get("type") or DEFAULT_AGENT_TYPE), lowercase=True)
    if not agent_type:
        agent_type = DEFAULT_AGENT_TYPE

    enabled_value = payload.get("enabled", current.get("enabled", True))
    enabled = bool(enabled_value)

    soul_requested, requested_soul = _payload_value(payload, "soul")
    if soul_requested:
        soul = _normalize_text(requested_soul) or None
    else:
        soul = _resolve_agent_soul(current)

    provider_key = _normalize_text(
        payload.get("provider_key", payload.get("providerKey")),
        lowercase=True,
    )
    if not provider_key:
        provider_key = (
            _normalize_text(current.get("provider"), lowercase=True)
            or (_resolve_agent_model_binding(current) or {}).get("provider_key")
            or ""
        )
    enabled_models = _enabled_provider_models()
    if provider_key not in enabled_models:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请选择项目内已启用的模型")

    requested_model = _normalize_text(payload.get("model"))
    model = requested_model or enabled_models[provider_key]["model"]
    if not model:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="所选模型不可用")

    requested_skill_ids = payload.get("skill_ids", payload.get("skillIds"))
    if requested_skill_ids is None:
        skill_ids = _resolve_agent_skill_binding(current)
    else:
        skill_ids = _normalize_identifier_list(requested_skill_ids)

    if skill_ids:
        resolved_skills = brain_skill_service.resolve_skill_summaries(
            skill_ids,
            tenant_id=tenant_id,
            include_all_tenants=include_all_tenants,
        )
        resolved_skill_ids = {str(item.get("id") or "") for item in resolved_skills}
        missing_skill_ids = [skill_id for skill_id in skill_ids if skill_id not in resolved_skill_ids]
        if missing_skill_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"以下 Skill 不存在或当前租户不可绑定：{', '.join(missing_skill_ids)}",
            )

    requested_tool_ids = payload.get("tool_ids", payload.get("toolIds"))
    if requested_tool_ids is None:
        tool_ids = _resolve_agent_tool_binding(current)
    else:
        tool_ids = _normalize_identifier_list(requested_tool_ids)
    tool_ids = _validate_tool_ids(
        tool_ids,
        tenant_id=tenant_id,
        include_all_tenants=include_all_tenants,
    )

    current_workflow_binding = _resolve_agent_workflow_binding(current) or {}
    current_agent_workflow_id = _normalize_text(current_workflow_binding.get("agent_workflow_id")) or None

    workflow_binding_requested, requested_agent_workflow_id = _payload_value(
        payload,
        "agent_workflow_id",
        "agentWorkflowId",
    )
    if workflow_binding_requested:
        agent_workflow_id = _normalize_text(requested_agent_workflow_id) or None
    else:
        agent_workflow_id = current_agent_workflow_id
    workflow_binding_cleared = workflow_binding_requested and agent_workflow_id is None

    input_contract_requested, requested_input_contract = _payload_value(
        payload,
        "input_contract",
        "inputContract",
    )
    if input_contract_requested:
        input_contract = _normalize_contract_payload(
            requested_input_contract,
            field_name="input_contract",
        )
    elif workflow_binding_cleared:
        input_contract = {}
    else:
        input_contract = _normalize_contract_payload(
            current_workflow_binding.get("input_contract"),
            field_name="input_contract",
        )

    output_contract_requested, requested_output_contract = _payload_value(
        payload,
        "output_contract",
        "outputContract",
    )
    if output_contract_requested:
        output_contract = _normalize_contract_payload(
            requested_output_contract,
            field_name="output_contract",
        )
    elif workflow_binding_cleared:
        output_contract = {}
    else:
        output_contract = _normalize_contract_payload(
            current_workflow_binding.get("output_contract"),
            field_name="output_contract",
        )

    contract_version_requested, requested_contract_version = _payload_value(
        payload,
        "contract_version",
        "contractVersion",
    )
    if contract_version_requested:
        contract_version = _normalize_text(requested_contract_version) or None
    elif workflow_binding_cleared:
        contract_version = None
    else:
        contract_version = _normalize_text(current_workflow_binding.get("contract_version")) or None
        if contract_version is None and agent_workflow_id and current_agent_workflow_id is None:
            contract_version = DEFAULT_AGENT_WORKFLOW_CONTRACT_VERSION

    if agent_workflow_id and not _workflow_exists(agent_workflow_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"agent_workflow_id 不存在：{agent_workflow_id}",
        )

    metadata_value = payload.get("metadata")
    if isinstance(metadata_value, dict):
        metadata = store.clone(metadata_value)
    elif current:
        metadata = _runtime_agent_metadata(current.get("config_snapshot")) or {}
    else:
        metadata = {}

    return {
        "name": name,
        "description": description,
        "type": agent_type,
        "enabled": enabled,
        "soul": soul,
        "provider_key": provider_key,
        "provider_label": enabled_models[provider_key]["provider_label"],
        "model": model,
        "skill_ids": skill_ids,
        "tool_ids": tool_ids,
        "agent_workflow_id": agent_workflow_id,
        "input_contract": input_contract,
        "output_contract": output_contract,
        "contract_version": contract_version,
        "metadata": metadata,
    }


def _generate_agent_id(name: str, agent_type: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    type_prefix = re.sub(r"[^a-z0-9]+", "-", agent_type.strip().lower()).strip("-") or "agent"
    if not slug:
        slug = f"{type_prefix}-agent"

    existing_ids = {str(item.get("id") or "").strip() for item in _load_agents()}
    if slug not in existing_ids:
        return slug
    return f"{slug}-{uuid4().hex[:6]}"


def _set_runtime_snapshot(agent: dict, runtime: dict) -> None:
    snapshot = agent.get("config_snapshot")
    if not isinstance(snapshot, dict):
        snapshot = {}
    snapshot["runtime"] = store.clone(runtime)
    agent["config_snapshot"] = snapshot


def _runtime_priority(status_text: str) -> int:
    return {
        "online": 3,
        "unknown": 2,
        "degraded": 1,
        "offline": 0,
    }.get(status_text, 0)


def _is_task_child_agent(agent_payload: dict[str, Any] | None) -> bool:
    if not isinstance(agent_payload, dict):
        return False
    snapshot = agent_payload.get("config_snapshot")
    metadata = _runtime_agent_metadata(snapshot if isinstance(snapshot, dict) else None) or {}
    if not metadata and isinstance(agent_payload.get("metadata"), dict):
        metadata = store.clone(agent_payload.get("metadata"))
    source = _normalize_text(metadata.get("source"), lowercase=True)
    if source == "requirement_dispatch_agent":
        return True
    task_id = _normalize_text(metadata.get("task_id") or metadata.get("taskId"))
    group_id = _normalize_text(metadata.get("group_id") or metadata.get("groupId"))
    return bool(task_id and group_id)


def _build_runtime_view(agent: dict, *, now: datetime | None = None) -> dict:
    runtime = _runtime_snapshot(agent)
    current = now or _now()
    enabled = bool(agent.get("enabled", False))
    status_text = _normalize_agent_status(agent.get("status")) or ""
    interval_seconds = _normalize_seconds(
        runtime.get("heartbeat_interval_seconds"),
        default=DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
        minimum=MIN_HEARTBEAT_INTERVAL_SECONDS,
        maximum=MAX_HEARTBEAT_INTERVAL_SECONDS,
    )
    timeout_seconds = _normalize_seconds(
        runtime.get("heartbeat_timeout_seconds"),
        default=max(DEFAULT_HEARTBEAT_TIMEOUT_SECONDS, interval_seconds * 3),
        minimum=max(MIN_HEARTBEAT_TIMEOUT_SECONDS, interval_seconds * 2),
        maximum=MAX_HEARTBEAT_TIMEOUT_SECONDS,
    )
    heartbeat_at = _parse_datetime(runtime.get("last_heartbeat_at"))
    age_seconds: int | None = None
    runtime_status = "unknown"
    reason = "heartbeat_not_reported"

    if not enabled:
        runtime_status = "offline"
        reason = "agent_disabled"
    elif status_text in {"offline", "maintenance"}:
        runtime_status = "offline"
        reason = f"status_{status_text}"
    elif heartbeat_at is None:
        if status_text == "degraded":
            runtime_status = "degraded"
            reason = "agent_self_reported_degraded"
        elif status_text in {"running", "busy", "idle", "waiting", "error"}:
            runtime_status = "unknown"
            reason = "heartbeat_not_reported"
    else:
        age_seconds = max(int((current - heartbeat_at).total_seconds()), 0)
        degraded_after = min(
            timeout_seconds,
            max(int(interval_seconds * HEARTBEAT_DEGRADED_RATIO), interval_seconds + 5),
        )
        if age_seconds <= degraded_after:
            runtime_status = "online"
            reason = "heartbeat_fresh"
        elif age_seconds <= timeout_seconds:
            runtime_status = "degraded"
            reason = "heartbeat_stale"
        else:
            runtime_status = "offline"
            reason = "heartbeat_timeout"

        if status_text == "degraded" and runtime_status == "online":
            runtime_status = "degraded"
            reason = "agent_self_reported_degraded"

    priority = _runtime_priority(runtime_status)
    routable = enabled and priority > 0
    return {
        "runtime_status": runtime_status,
        "runtime_status_reason": reason,
        "runtime_priority": priority,
        "routable": routable,
        "last_heartbeat_at": heartbeat_at.isoformat() if heartbeat_at is not None else None,
        "heartbeat_interval_seconds": interval_seconds,
        "heartbeat_timeout_seconds": timeout_seconds,
        "runtime_metrics": {
            "heartbeat_age_seconds": age_seconds,
            "last_reported_status": str(runtime.get("last_reported_status") or "").strip() or None,
            "source": str(runtime.get("source") or "").strip() or None,
            "load": runtime.get("load"),
            "queue_depth": runtime.get("queue_depth"),
        },
    }


def _decorate_agent(agent_payload: dict, *, include_snapshot: bool = True) -> dict:
    payload = store.clone(agent_payload)
    snapshot = payload.get("config_snapshot")
    if not isinstance(snapshot, dict):
        snapshot = agent_config_service.load_agent_config(payload)
        payload["config_snapshot"] = snapshot
        payload["config_summary"] = _build_agent_config_summary_with_bindings(
            snapshot,
            bound_tool_ids=_resolve_agent_tool_binding(payload),
            existing_summary=payload.get("config_summary"),
        )
        cached_agent = _find_cached_agent(str(payload.get("id") or "").strip())
        if cached_agent is not None:
            cached_agent["config_snapshot"] = store.clone(snapshot)
            cached_agent["config_summary"] = _build_agent_config_summary_with_bindings(
                snapshot,
                bound_tool_ids=_resolve_agent_tool_binding(payload),
                existing_summary=cached_agent.get("config_summary"),
            )
    payload["bound_tool_ids"] = _resolve_agent_tool_binding(payload)
    payload["bound_tools"], missing_bound_tool_ids = _resolve_bound_tools_safe(payload["bound_tool_ids"])
    payload["soul"] = _resolve_agent_soul(payload)
    payload["config_summary"] = _build_agent_config_summary_with_bindings(
        snapshot,
        bound_tool_ids=payload["bound_tool_ids"],
        existing_summary=payload.get("config_summary"),
    )
    if missing_bound_tool_ids:
        config_summary = payload["config_summary"] if isinstance(payload.get("config_summary"), dict) else {}
        existing_warnings = config_summary.get("warnings")
        warnings = [
            str(item or "").strip()
            for item in existing_warnings
            if str(item or "").strip()
        ] if isinstance(existing_warnings, list) else []
        missing_tools_warning = _format_missing_tool_binding_warning(missing_bound_tool_ids)
        if missing_tools_warning and missing_tools_warning not in warnings:
            warnings.append(missing_tools_warning)
        config_summary["warnings"] = warnings
        payload["config_summary"] = config_summary
    payload.update(_build_runtime_view(payload))
    payload["model_binding"] = _resolve_agent_model_binding(payload)
    payload["bound_skill_ids"] = _resolve_agent_skill_binding(payload)
    payload["bound_skills"] = brain_skill_service.resolve_skill_summaries(payload["bound_skill_ids"])
    workflow_binding = _resolve_agent_workflow_binding(payload) or {}
    payload["agent_workflow_id"] = _normalize_text(workflow_binding.get("agent_workflow_id")) or None
    payload["input_contract"] = (
        store.clone(workflow_binding.get("input_contract"))
        if isinstance(workflow_binding.get("input_contract"), dict)
        else {}
    )
    payload["output_contract"] = (
        store.clone(workflow_binding.get("output_contract"))
        if isinstance(workflow_binding.get("output_contract"), dict)
        else {}
    )
    payload["contract_version"] = _normalize_text(workflow_binding.get("contract_version")) or None
    payload["metadata"] = _runtime_agent_metadata(snapshot) or {}
    payload["delete_blocked_reason"] = _delete_blocked_reason(str(payload.get("id") or "").strip())
    payload["deletable"] = payload["delete_blocked_reason"] is None
    if not include_snapshot:
        payload.pop("config_snapshot", None)
    return payload


def is_agent_routable(agent_payload: dict, *, include_degraded: bool = True) -> bool:
    view = _build_runtime_view(agent_payload)
    if not view["routable"]:
        return False
    if not include_degraded and view["runtime_status"] == "degraded":
        return False
    return True


def routing_priority(agent_payload: dict) -> tuple[int, int, int]:
    view = _build_runtime_view(agent_payload)
    return (
        int(view["runtime_priority"]),
        int(agent_payload.get("tasks_completed") or 0),
        int(agent_payload.get("success_rate") or 0),
    )


def _find_agent_mutable(agent_id: str) -> dict:
    database_agent, database_authoritative = _load_database_agent(agent_id)
    if database_authoritative:
        if database_agent is None:
            external_agent = external_agent_registry_service.get_agent(agent_id)
            if external_agent is not None:
                return _sync_cached_agent(redact_external_agent_payload(external_agent))
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
        return _sync_cached_agent(database_agent)

    cached_agent = _find_cached_agent(agent_id)
    if cached_agent is not None:
        return cached_agent

    external_agent = external_agent_registry_service.get_agent(agent_id)
    if external_agent is not None:
        return _sync_cached_agent(redact_external_agent_payload(external_agent))

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")


def _load_database_agent(agent_id: str) -> tuple[dict | None, bool]:
    if not getattr(persistence_service, "enabled", False):
        return None, False

    database_agent = persistence_service.get_agent(agent_id)
    if database_agent is not None:
        return database_agent, True

    database_agents = persistence_service.list_agents()
    if database_agents is None:
        return None, True

    for candidate in database_agents:
        if str(candidate.get("id") or "").strip() == agent_id:
            return candidate, True
    return None, True


def _delete_blocked_reason(agent_id: str) -> str | None:
    return None


def list_agents(*, include_task_child_agents: bool = False) -> dict:
    items = []
    for agent in _load_agents():
        if not include_task_child_agents and _is_task_child_agent(agent):
            continue
        items.append(_decorate_agent(agent, include_snapshot=False))
    return {"items": items, "total": len(items)}


def get_agent(agent_id: str) -> dict:
    if _normalize_text(agent_id) in LEGACY_AGENT_IDS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    database_agent, database_authoritative = _load_database_agent(agent_id)
    if database_authoritative:
        if database_agent is None:
            external_agent = external_agent_registry_service.get_agent(agent_id)
            if external_agent is not None:
                return _decorate_agent(_sync_cached_agent(redact_external_agent_payload(external_agent)))
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
        if _should_refresh_from_external_registry(database_agent):
            external_agent = external_agent_registry_service.get_agent(agent_id)
            if external_agent is not None:
                return _decorate_agent(_sync_cached_agent(redact_external_agent_payload(external_agent)))
        return _decorate_agent(database_agent)
    cached_agent = _find_cached_agent(agent_id)
    if cached_agent is not None:
        if _should_refresh_from_external_registry(cached_agent):
            external_agent = external_agent_registry_service.get_agent(agent_id)
            if external_agent is not None:
                return _decorate_agent(_sync_cached_agent(redact_external_agent_payload(external_agent)))
        return _decorate_agent(cached_agent)
    external_agent = external_agent_registry_service.get_agent(agent_id)
    if external_agent is not None:
        return _decorate_agent(_sync_cached_agent(redact_external_agent_payload(external_agent)))
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")


def delete_agent(agent_id: str) -> dict[str, Any]:
    normalized_agent_id = _normalize_text(agent_id)
    if not normalized_agent_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    external_agent = external_agent_registry_service.get_agent(normalized_agent_id)
    if external_agent is not None:
        deleted_external = external_agent_registry_service.delete_agent(normalized_agent_id)
        store.agents = [
            item for item in store.agents if str(item.get("id") or "").strip() != normalized_agent_id
        ]
        persistence_service.delete_agent_state(agent_id=normalized_agent_id)
        persisted = persistence_service.persist_runtime_state()
        if getattr(persistence_service, "enabled", False) and not persisted:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Agent 删除后持久化失败")
        return {
            "ok": True,
            "message": f"Agent {deleted_external['name']} deleted",
            "agent_id": normalized_agent_id,
        }

    agent = _find_agent_mutable(normalized_agent_id)
    store.agents = [
        item for item in store.agents if str(item.get("id") or "").strip() != normalized_agent_id
    ]
    persistence_service.delete_agent_state(agent_id=normalized_agent_id)
    persisted = persistence_service.persist_runtime_state()
    if getattr(persistence_service, "enabled", False) and not persisted:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Agent 删除后持久化失败")

    return {
        "ok": True,
        "message": f"Agent {agent['name']} deleted",
        "agent_id": normalized_agent_id,
    }


def set_agent_enabled(agent_id: str, *, enabled: bool) -> dict[str, Any]:
    normalized_agent_id = _normalize_text(agent_id)
    if not normalized_agent_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    external_agent = external_agent_registry_service.get_agent(normalized_agent_id)
    if external_agent is not None:
        updated_external = external_agent_registry_service.set_enabled(
            normalized_agent_id,
            enabled=bool(enabled),
        )
        _sync_cached_agent(updated_external)
        return {
            "ok": True,
            "message": f"Agent {updated_external['name']} enabled set to {bool(enabled)}",
            "agent": _decorate_agent(updated_external),
        }

    agent = _find_agent_mutable(normalized_agent_id)
    agent["enabled"] = bool(enabled)
    _persist_agent(agent)
    return {
        "ok": True,
        "message": f"Agent {agent['name']} enabled set to {bool(enabled)}",
        "agent": _decorate_agent(agent),
    }


def _persist_agent(agent: dict | None) -> None:
    if agent is None:
        return

    persist_agent_state = getattr(persistence_service, "persist_agent_state", None)
    if callable(persist_agent_state):
        if persist_agent_state(agent=agent):
            return
        if getattr(persistence_service, "enabled", False):
            return

    persistence_service.persist_runtime_state()


def reload_agent(agent_id: str) -> dict:
    agent = _find_agent_mutable(agent_id)
    existing_snapshot = agent.get("config_snapshot")
    existing_binding = _runtime_model_binding(existing_snapshot if isinstance(existing_snapshot, dict) else None)
    existing_skill_binding = _runtime_skill_binding(existing_snapshot if isinstance(existing_snapshot, dict) else None)
    existing_tool_binding = _runtime_tool_binding(existing_snapshot if isinstance(existing_snapshot, dict) else None)
    existing_workflow_binding = _runtime_workflow_binding(existing_snapshot if isinstance(existing_snapshot, dict) else None)
    existing_metadata = _runtime_agent_metadata(existing_snapshot if isinstance(existing_snapshot, dict) else None)
    runtime_snapshot = _runtime_snapshot(agent)
    config_snapshot = agent_config_service.load_agent_config(agent)
    if runtime_snapshot:
        config_snapshot["runtime"] = runtime_snapshot
    if existing_binding is not None:
        config_snapshot = _apply_model_binding_to_snapshot(
            config_snapshot,
            agent=agent,
            provider_key=existing_binding.get("provider_key"),
            model=existing_binding.get("model"),
            source=str(existing_binding.get("source") or "manual"),
        )
    if existing_skill_binding is not None:
        config_snapshot = _apply_skill_binding_to_snapshot(
            config_snapshot,
            agent=agent,
            skill_ids=_normalize_identifier_list(existing_skill_binding.get("skill_ids")),
            source=str(existing_skill_binding.get("source") or "manual"),
        )
    if existing_tool_binding is not None:
        config_snapshot = _apply_tool_binding_to_snapshot(
            config_snapshot,
            agent=agent,
            tool_ids=_validate_tool_ids(_normalize_identifier_list(existing_tool_binding.get("tool_ids"))),
            source=str(existing_tool_binding.get("source") or "manual"),
        )
    if existing_workflow_binding is not None:
        config_snapshot = _apply_workflow_binding_to_snapshot(
            config_snapshot,
            agent=agent,
            agent_workflow_id=_normalize_text(existing_workflow_binding.get("agent_workflow_id")) or None,
            input_contract=store.clone(existing_workflow_binding.get("input_contract") or {}),
            output_contract=store.clone(existing_workflow_binding.get("output_contract") or {}),
            contract_version=_normalize_text(existing_workflow_binding.get("contract_version")) or None,
            source=str(existing_workflow_binding.get("source") or "manual"),
        )
    if existing_metadata is not None:
        config_snapshot = _apply_agent_metadata_to_snapshot(
            config_snapshot,
            agent=agent,
            metadata=existing_metadata,
        )
    agent["config_snapshot"] = config_snapshot
    agent["config_summary"] = _build_agent_config_summary_with_bindings(
        config_snapshot,
        bound_tool_ids=_resolve_agent_tool_binding({"config_snapshot": config_snapshot}),
    )
    agent["status"] = "idle"
    agent["last_active"] = "刚刚"
    _persist_agent(agent)
    return {
        "ok": True,
        "message": f"Agent {agent['name']} reloaded",
        "agent": _decorate_agent(agent),
    }


def refresh_agent_config_snapshot(agent_id: str) -> dict:
    agent = _find_agent_mutable(agent_id)
    existing_snapshot = agent.get("config_snapshot")
    existing_binding = _runtime_model_binding(existing_snapshot if isinstance(existing_snapshot, dict) else None)
    existing_skill_binding = _runtime_skill_binding(existing_snapshot if isinstance(existing_snapshot, dict) else None)
    existing_tool_binding = _runtime_tool_binding(existing_snapshot if isinstance(existing_snapshot, dict) else None)
    existing_workflow_binding = _runtime_workflow_binding(existing_snapshot if isinstance(existing_snapshot, dict) else None)
    existing_metadata = _runtime_agent_metadata(existing_snapshot if isinstance(existing_snapshot, dict) else None)
    runtime_snapshot = _runtime_snapshot(agent)
    config_snapshot = agent_config_service.load_agent_config(agent)
    if runtime_snapshot:
        config_snapshot["runtime"] = runtime_snapshot
    if existing_binding is not None:
        config_snapshot = _apply_model_binding_to_snapshot(
            config_snapshot,
            agent=agent,
            provider_key=existing_binding.get("provider_key"),
            model=existing_binding.get("model"),
            source=str(existing_binding.get("source") or "manual"),
        )
    if existing_skill_binding is not None:
        config_snapshot = _apply_skill_binding_to_snapshot(
            config_snapshot,
            agent=agent,
            skill_ids=_normalize_identifier_list(existing_skill_binding.get("skill_ids")),
            source=str(existing_skill_binding.get("source") or "manual"),
        )
    if existing_tool_binding is not None:
        config_snapshot = _apply_tool_binding_to_snapshot(
            config_snapshot,
            agent=agent,
            tool_ids=_validate_tool_ids(_normalize_identifier_list(existing_tool_binding.get("tool_ids"))),
            source=str(existing_tool_binding.get("source") or "manual"),
        )
    if existing_workflow_binding is not None:
        config_snapshot = _apply_workflow_binding_to_snapshot(
            config_snapshot,
            agent=agent,
            agent_workflow_id=_normalize_text(existing_workflow_binding.get("agent_workflow_id")) or None,
            input_contract=store.clone(existing_workflow_binding.get("input_contract") or {}),
            output_contract=store.clone(existing_workflow_binding.get("output_contract") or {}),
            contract_version=_normalize_text(existing_workflow_binding.get("contract_version")) or None,
            source=str(existing_workflow_binding.get("source") or "manual"),
        )
    if existing_metadata is not None:
        config_snapshot = _apply_agent_metadata_to_snapshot(
            config_snapshot,
            agent=agent,
            metadata=existing_metadata,
        )
    agent["config_snapshot"] = config_snapshot
    agent["config_summary"] = _build_agent_config_summary_with_bindings(
        config_snapshot,
        bound_tool_ids=_resolve_agent_tool_binding({"config_snapshot": config_snapshot}),
    )
    _persist_agent(agent)
    return _decorate_agent(agent)


def create_agent(
    payload: dict[str, Any],
    *,
    tenant_id: str | None = None,
    include_all_tenants: bool = True,
) -> dict[str, Any]:
    normalized = _normalize_agent_config_payload(
        payload,
        tenant_id=tenant_id,
        include_all_tenants=include_all_tenants,
    )
    agent_id = _generate_agent_id(normalized["name"], normalized["type"])
    agent = {
        "id": agent_id,
        "name": normalized["name"],
        "description": normalized["description"],
        "type": normalized["type"],
        "status": "idle",
        "enabled": normalized["enabled"],
        "tasks_completed": 0,
        "tasks_total": 0,
        "avg_response_time": "--",
        "tokens_used": 0,
        "tokens_limit": 0,
        "success_rate": 0.0,
        "last_active": "未运行",
    }
    agent["config_snapshot"] = _apply_model_binding_to_snapshot(
        None,
        agent=agent,
        provider_key=normalized["provider_key"],
        model=normalized["model"],
    )
    agent["config_snapshot"] = _apply_skill_binding_to_snapshot(
        agent["config_snapshot"],
        agent=agent,
        skill_ids=normalized["skill_ids"],
    )
    agent["config_snapshot"] = _apply_tool_binding_to_snapshot(
        agent["config_snapshot"],
        agent=agent,
        tool_ids=normalized["tool_ids"],
    )
    agent["config_snapshot"] = _apply_soul_to_snapshot(
        agent["config_snapshot"],
        agent=agent,
        soul=normalized["soul"],
    )
    agent["config_snapshot"] = _apply_workflow_binding_to_snapshot(
        agent["config_snapshot"],
        agent=agent,
        agent_workflow_id=normalized["agent_workflow_id"],
        input_contract=normalized["input_contract"],
        output_contract=normalized["output_contract"],
        contract_version=normalized["contract_version"],
    )
    agent["config_snapshot"] = _apply_agent_metadata_to_snapshot(
        agent["config_snapshot"],
        agent=agent,
        metadata=normalized["metadata"],
    )
    agent["config_summary"] = _build_agent_config_summary_with_bindings(
        agent["config_snapshot"],
        bound_tool_ids=normalized["tool_ids"],
    )
    cached_agent = _sync_cached_agent(agent)
    _persist_agent(cached_agent)
    return {
        "ok": True,
        "message": f"Agent {normalized['name']} created",
        "agent": _decorate_agent(cached_agent),
    }


def update_agent_config(
    agent_id: str,
    payload: dict[str, Any],
    *,
    tenant_id: str | None = None,
    include_all_tenants: bool = True,
) -> dict[str, Any]:
    agent = _find_agent_mutable(agent_id)
    normalized = _normalize_agent_config_payload(
        payload,
        current_agent=agent,
        tenant_id=tenant_id,
        include_all_tenants=include_all_tenants,
    )
    agent["name"] = normalized["name"]
    agent["description"] = normalized["description"]
    agent["type"] = normalized["type"]
    agent["enabled"] = normalized["enabled"]

    current_snapshot = agent.get("config_snapshot")
    if not isinstance(current_snapshot, dict):
        current_snapshot = agent_config_service.load_agent_config(agent)

    updated_snapshot = _apply_model_binding_to_snapshot(
        current_snapshot,
        agent=agent,
        provider_key=normalized["provider_key"],
        model=normalized["model"],
    )
    updated_snapshot = _apply_skill_binding_to_snapshot(
        updated_snapshot,
        agent=agent,
        skill_ids=normalized["skill_ids"],
    )
    updated_snapshot = _apply_tool_binding_to_snapshot(
        updated_snapshot,
        agent=agent,
        tool_ids=normalized["tool_ids"],
    )
    updated_snapshot = _apply_soul_to_snapshot(
        updated_snapshot,
        agent=agent,
        soul=normalized["soul"],
    )
    updated_snapshot = _apply_workflow_binding_to_snapshot(
        updated_snapshot,
        agent=agent,
        agent_workflow_id=normalized["agent_workflow_id"],
        input_contract=normalized["input_contract"],
        output_contract=normalized["output_contract"],
        contract_version=normalized["contract_version"],
    )
    updated_snapshot = _apply_agent_metadata_to_snapshot(
        updated_snapshot,
        agent=agent,
        metadata=normalized["metadata"],
    )
    agent["config_snapshot"] = updated_snapshot
    agent["config_summary"] = _build_agent_config_summary_with_bindings(
        updated_snapshot,
        bound_tool_ids=normalized["tool_ids"],
    )
    _persist_agent(agent)
    return {
        "ok": True,
        "message": f"Agent {agent['name']} config updated",
        "agent": _decorate_agent(agent),
    }


def report_agent_heartbeat(
    agent_id: str,
    *,
    status_text: str | None = None,
    interval_seconds: int | None = None,
    timeout_seconds: int | None = None,
    source: str | None = None,
    load: float | None = None,
    queue_depth: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict:
    external_agent = external_agent_registry_service.get_agent(agent_id)
    if external_agent is not None:
        updated_external = external_agent_registry_service.report_heartbeat(
            agent_id,
            status=status_text,
            load=load,
            queue_depth=queue_depth,
            metadata=metadata,
        )
        _sync_cached_agent(updated_external)
        return {
            "ok": True,
            "message": (
                f"External agent {updated_external['name']} heartbeat accepted; "
                f"runtime={updated_external['runtime_status']}, routable={updated_external['routable']}"
            ),
            "agent": _decorate_agent(updated_external),
        }

    agent = _find_agent_mutable(agent_id)
    runtime = _runtime_snapshot(agent)
    normalized_status = _normalize_agent_status(status_text)
    if normalized_status:
        agent["status"] = normalized_status
    runtime["last_reported_status"] = normalized_status or str(agent.get("status") or "").strip().lower() or "running"
    runtime["last_heartbeat_at"] = _now().isoformat()
    runtime["heartbeat_interval_seconds"] = _normalize_seconds(
        interval_seconds,
        default=_normalize_seconds(
            runtime.get("heartbeat_interval_seconds"),
            default=DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
            minimum=MIN_HEARTBEAT_INTERVAL_SECONDS,
            maximum=MAX_HEARTBEAT_INTERVAL_SECONDS,
        ),
        minimum=MIN_HEARTBEAT_INTERVAL_SECONDS,
        maximum=MAX_HEARTBEAT_INTERVAL_SECONDS,
    )
    runtime["heartbeat_timeout_seconds"] = _normalize_seconds(
        timeout_seconds,
        default=_normalize_seconds(
            runtime.get("heartbeat_timeout_seconds"),
            default=max(
                DEFAULT_HEARTBEAT_TIMEOUT_SECONDS,
                int(runtime["heartbeat_interval_seconds"]) * 3,
            ),
            minimum=max(MIN_HEARTBEAT_TIMEOUT_SECONDS, int(runtime["heartbeat_interval_seconds"]) * 2),
            maximum=MAX_HEARTBEAT_TIMEOUT_SECONDS,
        ),
        minimum=max(MIN_HEARTBEAT_TIMEOUT_SECONDS, int(runtime["heartbeat_interval_seconds"]) * 2),
        maximum=MAX_HEARTBEAT_TIMEOUT_SECONDS,
    )
    if source is not None:
        runtime["source"] = str(source).strip() or None
    if load is not None:
        try:
            runtime["load"] = float(load)
        except (TypeError, ValueError):
            runtime["load"] = None
    if queue_depth is not None:
        try:
            runtime["queue_depth"] = max(int(queue_depth), 0)
        except (TypeError, ValueError):
            runtime["queue_depth"] = None
    if metadata:
        runtime["metadata"] = {
            str(key).strip(): value
            for key, value in metadata.items()
            if str(key).strip()
        }

    _set_runtime_snapshot(agent, runtime)
    agent["last_active"] = "刚刚"
    _persist_agent(agent)
    runtime_view = _build_runtime_view(agent)
    return {
        "ok": True,
        "message": (
            f"Agent {agent['name']} heartbeat accepted; "
            f"runtime={runtime_view['runtime_status']}, routable={runtime_view['routable']}"
        ),
        "agent": _decorate_agent(agent),
    }
