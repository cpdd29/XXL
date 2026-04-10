from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status

from app.services.agent_config_service import agent_config_service, build_agent_config_summary
from app.services.persistence_service import persistence_service
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


def _load_agents() -> list[dict]:
    database_agents = persistence_service.list_agents()
    if database_agents is not None:
        return database_agents

    if getattr(persistence_service, "enabled", False):
        return []

    return store.clone(store.agents)


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


def _runtime_snapshot(agent: dict) -> dict:
    snapshot = agent.get("config_snapshot")
    if not isinstance(snapshot, dict):
        return {}
    runtime = snapshot.get("runtime")
    if not isinstance(runtime, dict):
        return {}
    return store.clone(runtime)


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
    payload.update(_build_runtime_view(payload))
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
    runtime_snapshot = _runtime_snapshot(agent)
    config_snapshot = agent_config_service.load_agent_config(agent)
    if runtime_snapshot:
        config_snapshot["runtime"] = runtime_snapshot
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
