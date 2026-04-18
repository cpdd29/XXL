import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status

from app.services.agent_config_service import agent_config_service, build_agent_config_summary
from app.services.brain_skill_service import brain_skill_service
from app.services.external_agent_registry_service import external_agent_registry_service
from app.services.persistence_service import persistence_service
from app.services.settings_service import get_agent_api_runtime_settings
from app.services.store import store

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
    }
    for external_agent in external_agent_registry_service.list_agents(include_offline=True):
        agent_id = str(external_agent.get("id") or "").strip()
        if not agent_id or agent_id in merged:
            continue
        merged[agent_id] = store.clone(external_agent)
    return list(merged.values())


def _find_cached_agent(agent_id: str) -> dict | None:
    for agent in store.agents:
        if agent["id"] == agent_id:
            return agent
    return None


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


def _normalize_agent_config_payload(payload: dict[str, Any], *, current_agent: dict | None = None) -> dict[str, Any]:
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
        resolved_skills = brain_skill_service.resolve_skill_summaries(skill_ids)
        resolved_skill_ids = {str(item.get("id") or "") for item in resolved_skills}
        missing_skill_ids = [skill_id for skill_id in skill_ids if skill_id not in resolved_skill_ids]
        if missing_skill_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"以下 Skill 不存在：{', '.join(missing_skill_ids)}",
            )

    return {
        "name": name,
        "description": description,
        "type": agent_type,
        "enabled": enabled,
        "provider_key": provider_key,
        "provider_label": enabled_models[provider_key]["provider_label"],
        "model": model,
        "skill_ids": skill_ids,
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
        payload["config_summary"] = build_agent_config_summary(snapshot)
        cached_agent = _find_cached_agent(str(payload.get("id") or "").strip())
        if cached_agent is not None:
            cached_agent["config_snapshot"] = store.clone(snapshot)
            cached_agent["config_summary"] = build_agent_config_summary(snapshot)
    elif not isinstance(payload.get("config_summary"), dict):
        payload["config_summary"] = build_agent_config_summary(snapshot)
    payload.update(_build_runtime_view(payload))
    payload["model_binding"] = _resolve_agent_model_binding(payload)
    payload["bound_skill_ids"] = _resolve_agent_skill_binding(payload)
    payload["bound_skills"] = brain_skill_service.resolve_skill_summaries(payload["bound_skill_ids"])
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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
        return _sync_cached_agent(database_agent)

    cached_agent = _find_cached_agent(agent_id)
    if cached_agent is not None:
        return cached_agent

    external_agent = external_agent_registry_service.get_agent(agent_id)
    if external_agent is not None:
        return _sync_cached_agent(external_agent)

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


def list_agents() -> dict:
    items = []
    for agent in _load_agents():
        items.append(_decorate_agent(agent, include_snapshot=False))
    return {"items": items, "total": len(items)}


def get_agent(agent_id: str) -> dict:
    database_agent, database_authoritative = _load_database_agent(agent_id)
    if database_authoritative:
        if database_agent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
        return _decorate_agent(database_agent)
    cached_agent = _find_cached_agent(agent_id)
    if cached_agent is not None:
        return _decorate_agent(cached_agent)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")


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
    agent["config_snapshot"] = config_snapshot
    agent["config_summary"] = build_agent_config_summary(config_snapshot)
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
    agent["config_snapshot"] = config_snapshot
    agent["config_summary"] = build_agent_config_summary(config_snapshot)
    _persist_agent(agent)
    return _decorate_agent(agent)


def create_agent(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_agent_config_payload(payload)
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
    agent["config_summary"] = build_agent_config_summary(agent["config_snapshot"])
    cached_agent = _sync_cached_agent(agent)
    _persist_agent(cached_agent)
    return {
        "ok": True,
        "message": f"Agent {normalized['name']} created",
        "agent": _decorate_agent(cached_agent),
    }


def update_agent_config(agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    agent = _find_agent_mutable(agent_id)
    normalized = _normalize_agent_config_payload(payload, current_agent=agent)
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
    agent["config_snapshot"] = updated_snapshot
    agent["config_summary"] = build_agent_config_summary(updated_snapshot)
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
