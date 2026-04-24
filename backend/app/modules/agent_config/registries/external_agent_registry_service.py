from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import hashlib
from typing import Any
from uuid import uuid4

from app.config import get_settings
from app.platform.persistence.persistence_service import persistence_service
from app.platform.persistence.runtime_store import store
from app.platform.observability.trace_exporter_service import trace_exporter_service


DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 15
DEFAULT_HEARTBEAT_TIMEOUT_SECONDS = 90
DEFAULT_METHOD = "POST"
DEFAULT_RELEASE_CHANNEL = "stable"
DEFAULT_COMPATIBILITY = "brain-core-v1"
ALLOWED_RELEASE_CHANNELS = {"stable", "canary", "beta", "alpha", "deprecated"}


def _now() -> datetime:
    return datetime.now(UTC)


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _parse_datetime(value: Any) -> datetime | None:
    normalized = _normalize_text(value)
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _normalize_list(value: Any) -> list[str]:
    if isinstance(value, str):
        values = value.split(",")
    elif isinstance(value, list):
        values = value
    else:
        values = []
    items: list[str] = []
    seen: set[str] = set()
    for item in values:
        candidate = _normalize_text(item).lower()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        items.append(candidate)
    return items


def _normalize_seconds(value: Any, *, default: int, minimum: int = 3, maximum: int = 24 * 3600) -> int:
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        resolved = default
    return max(minimum, min(maximum, resolved))


def _normalize_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    normalized = _normalize_text(value).lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _parse_version_parts(value: str) -> tuple[int, ...]:
    normalized = _normalize_text(value).lower().lstrip("v")
    if not normalized:
        return (0,)
    parts: list[int] = []
    for piece in normalized.replace("-", ".").split("."):
        digits = "".join(char for char in piece if char.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts or [0])


def _release_channel_rank(value: str) -> int:
    return {
        "stable": 4,
        "canary": 3,
        "beta": 2,
        "alpha": 1,
        "deprecated": 0,
    }.get(value, 0)


def _stable_bucket(value: str) -> int:
    digest = hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()
    return int(digest[:8], 16) % 100


def _coerce_percent(value: Any, *, default: int = 0) -> int:
    try:
        percent = int(value)
    except (TypeError, ValueError):
        percent = default
    if percent < 0:
        return 0
    if percent > 100:
        return 100
    return percent


class ExternalAgentRegistryService:
    def __init__(self) -> None:
        self._agents: dict[str, dict[str, Any]] = {}

    def clear(self) -> None:
        self._agents.clear()

    def register_agent(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_agent(payload)
        self._agents[normalized["id"]] = normalized
        self._apply_version_governance(normalized["id"])
        self._append_registry_audit(
            action="external_agent_registry.registered",
            details=(
                f"id={normalized['id']}; version={normalized['version']}; "
                f"release_channel={normalized['release_channel']}; deprecated={normalized['deprecated']}"
            ),
            metadata={
                "registry": "external_agent_registry",
                "agent_id": normalized["id"],
                "agent_family": normalized["agent_family"],
                "version": normalized["version"],
                "release_channel": normalized["release_channel"],
                "compatibility": list(normalized.get("compatibility") or []),
                "deprecated": bool(normalized.get("deprecated")),
                "default_version": bool(normalized.get("default_version")),
                "fallback_version_id": normalized.get("fallback_version_id"),
            },
        )
        return deepcopy(self._agents[normalized["id"]])

    def delete_agent(self, agent_id: str) -> dict[str, Any]:
        normalized_agent_id = _normalize_text(agent_id)
        item = self._agents.pop(normalized_agent_id, None)
        if item is None:
            raise KeyError(f"External agent '{agent_id}' not found")
        self._append_registry_audit(
            action="external_agent_registry.deleted",
            details=f"id={item['id']}; version={item['version']}; family={item['agent_family']}",
            metadata={
                "registry": "external_agent_registry",
                "agent_id": item["id"],
                "agent_family": item["agent_family"],
                "version": item["version"],
            },
        )
        return deepcopy(item)

    def list_agents(self, *, include_offline: bool = True) -> list[dict[str, Any]]:
        self.prune_expired()
        items: list[dict[str, Any]] = []
        for item in self._agents.values():
            if not include_offline and not bool(item.get("routable", False)):
                continue
            items.append(deepcopy(item))
        items.sort(key=lambda item: (not bool(item.get("routable", False)), item["name"].lower()))
        return items

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        self.prune_expired()
        item = self._agents.get(_normalize_text(agent_id))
        return deepcopy(item) if item is not None else None

    def select_agent(
        self,
        *,
        agent_type: str | None = None,
        compatibility: str | None = None,
        release_channel: str | None = None,
        include_deprecated: bool = False,
        route_seed: str | None = None,
    ) -> dict[str, Any] | None:
        self.prune_expired()
        normalized_type = _normalize_text(agent_type).lower()
        normalized_compatibility = _normalize_text(compatibility or DEFAULT_COMPATIBILITY)
        normalized_channel = _normalize_text(release_channel or "").lower()
        candidates: list[dict[str, Any]] = []
        for item in self._agents.values():
            if normalized_type and _normalize_text(item.get("type")).lower() != normalized_type:
                continue
            if not bool(item.get("routable", False)):
                continue
            if not include_deprecated and bool(item.get("deprecated", False)):
                continue
            if normalized_channel and _normalize_text(item.get("release_channel")).lower() != normalized_channel:
                continue
            compatibility_items = {
                _normalize_text(value).lower() for value in item.get("compatibility") or []
            }
            if normalized_compatibility and compatibility_items and normalized_compatibility.lower() not in compatibility_items:
                continue
            candidates.append(item)
        if not candidates:
            return None
        if not normalized_channel:
            family_winners: list[dict[str, Any]] = []
            family_groups: dict[str, list[dict[str, Any]]] = {}
            for item in candidates:
                family = _normalize_text(item.get("agent_family") or item.get("id")).lower()
                family_groups.setdefault(family, []).append(item)
            for family, versions in family_groups.items():
                selected = self._select_family_version(versions, route_seed=route_seed, family=family)
                if selected is not None:
                    family_winners.append(selected)
            if family_winners:
                family_winners.sort(key=self._selection_sort_key, reverse=True)
                return deepcopy(family_winners[0])
        candidates.sort(key=self._selection_sort_key, reverse=True)
        return deepcopy(candidates[0])

    def list_versions(self, family: str) -> list[dict[str, Any]]:
        normalized_family = _normalize_text(family).lower()
        items = [
            deepcopy(item)
            for item in self._agents.values()
            if _normalize_text(item.get("agent_family")).lower() == normalized_family
        ]
        items.sort(key=self._selection_sort_key, reverse=True)
        return items

    def promote_version(self, agent_id: str) -> dict[str, Any]:
        item = self._agents.get(_normalize_text(agent_id))
        if item is None:
            raise KeyError(f"External agent '{agent_id}' not found")
        family = _normalize_text(item.get("agent_family")).lower()
        for candidate in self._agents.values():
            if _normalize_text(candidate.get("agent_family")).lower() != family:
                continue
            candidate["default_version"] = str(candidate.get("id") or "") == item["id"]
        self._apply_version_governance(item["id"])
        return deepcopy(self._agents[item["id"]])

    def set_fallback_version(self, agent_id: str, fallback_version_id: str | None) -> dict[str, Any]:
        item = self._agents.get(_normalize_text(agent_id))
        if item is None:
            raise KeyError(f"External agent '{agent_id}' not found")
        item["fallback_version_id"] = _normalize_text(fallback_version_id) or None
        self._apply_version_governance(item["id"])
        return deepcopy(self._agents[item["id"]])

    def set_deprecated(self, agent_id: str, *, deprecated: bool) -> dict[str, Any]:
        item = self._agents.get(_normalize_text(agent_id))
        if item is None:
            raise KeyError(f"External agent '{agent_id}' not found")
        item["deprecated"] = bool(deprecated)
        item["release_channel"] = "deprecated" if deprecated else (
            _normalize_text(item.get("release_channel")).lower() or DEFAULT_RELEASE_CHANNEL
        )
        if deprecated:
            item["default_version"] = False
        self._apply_version_governance(item["id"])
        return deepcopy(self._agents[item["id"]])

    def set_rollout_policy(self, agent_id: str, rollout_policy: dict[str, Any] | None) -> dict[str, Any]:
        item = self._agents.get(_normalize_text(agent_id))
        if item is None:
            raise KeyError(f"External agent '{agent_id}' not found")
        item["rollout_policy"] = self._normalize_rollout_policy(
            rollout_policy,
            release_channel=str(item.get("release_channel") or ""),
        )
        item["canary_percent"] = int((item.get("rollout_policy") or {}).get("canary_percent") or 0)
        item["route_key"] = str((item.get("rollout_policy") or {}).get("route_key") or "global")
        config_summary = item.get("config_summary") if isinstance(item.get("config_summary"), dict) else {}
        config_summary["rollout_policy"] = deepcopy(item.get("rollout_policy") or {})
        item["config_summary"] = config_summary
        self._apply_version_governance(item["id"])
        return deepcopy(self._agents[item["id"]])

    def set_rollback_policy(self, agent_id: str, rollback_policy: dict[str, Any] | None) -> dict[str, Any]:
        item = self._agents.get(_normalize_text(agent_id))
        if item is None:
            raise KeyError(f"External agent '{agent_id}' not found")
        item["rollback_policy"] = self._normalize_rollback_policy(
            rollback_policy,
            fallback_version_id=str(item.get("fallback_version_id") or ""),
        )
        item["rollback_active"] = bool((item.get("rollback_policy") or {}).get("active"))
        item["rollback_target_version_id"] = (item.get("rollback_policy") or {}).get("target_version_id")
        config_summary = item.get("config_summary") if isinstance(item.get("config_summary"), dict) else {}
        config_summary["rollback_policy"] = deepcopy(item.get("rollback_policy") or {})
        item["config_summary"] = config_summary
        self._apply_version_governance(item["id"])
        return deepcopy(self._agents[item["id"]])

    def resolve_fallback_version(self, agent_id_or_family: str) -> dict[str, Any] | None:
        normalized = _normalize_text(agent_id_or_family).lower()
        if not normalized:
            return None
        direct = self._agents.get(_normalize_text(agent_id_or_family))
        family = (
            _normalize_text((direct or {}).get("agent_family")).lower()
            if isinstance(direct, dict)
            else normalized
        )
        family_versions = [item for item in self._agents.values() if _normalize_text(item.get("agent_family")).lower() == family]
        if isinstance(direct, dict):
            fallback_id = _normalize_text(direct.get("fallback_version_id"))
            if fallback_id:
                fallback = self._agents.get(fallback_id)
                if isinstance(fallback, dict):
                    return deepcopy(fallback)
        eligible = [item for item in family_versions if bool(item.get("routable", False)) and not bool(item.get("deprecated", False))]
        if not eligible:
            return None
        eligible.sort(key=self._selection_sort_key, reverse=True)
        return deepcopy(eligible[0])

    def _family_versions(self, family: str) -> list[dict[str, Any]]:
        normalized_family = _normalize_text(family).lower()
        return [
            item
            for item in self._agents.values()
            if _normalize_text(item.get("agent_family")).lower() == normalized_family
        ]

    def _validate_fallback_reference(self, item: dict[str, Any]) -> None:
        fallback_version_id = _normalize_text(item.get("fallback_version_id"))
        if not fallback_version_id:
            return
        fallback = self._agents.get(fallback_version_id)
        if fallback is None:
            raise ValueError(f"Fallback agent version '{fallback_version_id}' not found")
        if _normalize_text(fallback.get("agent_family")).lower() != _normalize_text(item.get("agent_family")).lower():
            raise ValueError("Fallback agent version must belong to the same family")
        item_compatibility = set(item.get("compatibility") or [])
        fallback_compatibility = set(fallback.get("compatibility") or [])
        if item_compatibility and fallback_compatibility and not (item_compatibility & fallback_compatibility):
            raise ValueError("Fallback agent version compatibility does not overlap")

    def _validate_rollback_reference(self, item: dict[str, Any]) -> None:
        rollback_policy = item.get("rollback_policy") if isinstance(item.get("rollback_policy"), dict) else {}
        target_version_id = _normalize_text(rollback_policy.get("target_version_id"))
        if not target_version_id:
            return
        target = self._agents.get(target_version_id)
        if target is None:
            raise ValueError(f"Rollback agent version '{target_version_id}' not found")
        if _normalize_text(target.get("agent_family")).lower() != _normalize_text(item.get("agent_family")).lower():
            raise ValueError("Rollback agent version must belong to the same family")
        item_compatibility = set(item.get("compatibility") or [])
        target_compatibility = set(target.get("compatibility") or [])
        if item_compatibility and target_compatibility and not (item_compatibility & target_compatibility):
            raise ValueError("Rollback agent version compatibility does not overlap")

    def _select_family_version(
        self,
        family_versions: list[dict[str, Any]],
        *,
        route_seed: str | None,
        family: str,
    ) -> dict[str, Any] | None:
        eligible = [
            item
            for item in family_versions
            if bool(item.get("routable", False)) and not bool(item.get("deprecated", False))
        ]
        if not eligible:
            return None

        rollback_selected = self._resolve_active_rollback_target(eligible)
        if rollback_selected is not None:
            return rollback_selected

        baseline_candidates = [
            item
            for item in eligible
            if _normalize_text(item.get("release_channel")).lower() != "canary"
            and int(((item.get("rollout_policy") or {}).get("canary_percent") or 0)) <= 0
        ]
        baseline = None
        if baseline_candidates:
            baseline_candidates.sort(key=self._selection_sort_key, reverse=True)
            baseline = baseline_candidates[0]

        canary_candidates = [
            item
            for item in eligible
            if (
                _normalize_text(item.get("release_channel")).lower() == "canary"
                or bool(((item.get("rollout_policy") or {}).get("enabled")))
            )
            and int(((item.get("rollout_policy") or {}).get("canary_percent") or 0)) > 0
        ]
        if canary_candidates:
            canary_candidates.sort(key=self._selection_sort_key, reverse=True)
            canary = canary_candidates[0]
            canary_percent = int(((canary.get("rollout_policy") or {}).get("canary_percent") or 0))
            if canary_percent > 0:
                if canary_percent >= 100:
                    return canary
                seed = _normalize_text(route_seed or family)
                if seed and _stable_bucket(f"{seed}:{family}") < canary_percent:
                    return canary

        if baseline is not None:
            return baseline
        eligible.sort(key=self._selection_sort_key, reverse=True)
        return eligible[0]

    def _resolve_active_rollback_target(self, eligible: list[dict[str, Any]]) -> dict[str, Any] | None:
        for item in sorted(eligible, key=self._selection_sort_key, reverse=True):
            rollback_policy = item.get("rollback_policy") if isinstance(item.get("rollback_policy"), dict) else {}
            if not bool(rollback_policy.get("active")):
                continue
            target_version_id = _normalize_text(rollback_policy.get("target_version_id"))
            if target_version_id:
                for candidate in eligible:
                    if _normalize_text(candidate.get("id")) == target_version_id:
                        return candidate
            fallback_version_id = _normalize_text(item.get("fallback_version_id"))
            if fallback_version_id:
                for candidate in eligible:
                    if _normalize_text(candidate.get("id")) == fallback_version_id:
                        return candidate
        return None

    def _apply_version_governance(self, agent_id: str) -> None:
        item = self._agents.get(_normalize_text(agent_id))
        if item is None:
            return
        self._validate_fallback_reference(item)
        self._validate_rollback_reference(item)
        family = _normalize_text(item.get("agent_family")).lower()
        family_versions = self._family_versions(family)
        if bool(item.get("default_version")):
            for candidate in family_versions:
                if candidate is item:
                    continue
                candidate["default_version"] = False
        if bool(item.get("deprecated")):
            item["release_channel"] = "deprecated"
            item["routable"] = False
            item["runtime_status_reason"] = "deprecated_version"
        else:
            item["routable"] = bool(item.get("enabled", True)) and str(item.get("runtime_status") or "").strip().lower() in {"online", "degraded"}
        if not any(bool(candidate.get("default_version")) for candidate in family_versions if not bool(candidate.get("deprecated"))):
            eligible = [candidate for candidate in family_versions if not bool(candidate.get("deprecated"))]
            if eligible:
                eligible.sort(key=self._selection_sort_key, reverse=True)
                eligible[0]["default_version"] = True

    def report_heartbeat(
        self,
        agent_id: str,
        *,
        status: str | None = None,
        load: float | None = None,
        queue_depth: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        item = self._agents.get(_normalize_text(agent_id))
        if item is None:
            raise KeyError(f"External agent '{agent_id}' not found")
        now = _now()
        runtime_status = _normalize_text(status).lower() or "online"
        if runtime_status not in {"online", "degraded", "offline", "error", "maintenance"}:
            runtime_status = "online"
        item["status"] = "idle" if runtime_status == "online" else runtime_status
        item["last_active"] = "刚刚"
        item["runtime_status"] = runtime_status
        item["runtime_status_reason"] = "heartbeat_accepted"
        item["consecutive_failures"] = 0
        item["circuit_state"] = "closed"
        item["circuit_open_until"] = None
        item["next_retry_at"] = None
        item["routable"] = bool(item.get("enabled", True)) and runtime_status in {"online", "degraded"}
        item["last_heartbeat_at"] = now.isoformat()
        item["heartbeat_interval_seconds"] = int(item["heartbeat_interval_seconds"])
        item["heartbeat_timeout_seconds"] = int(item["heartbeat_timeout_seconds"])
        item["runtime_metrics"] = {
            **deepcopy(item.get("runtime_metrics") or {}),
            "source": "external_agent_registry",
            "load": load,
            "queue_depth": queue_depth,
        }
        if metadata:
            item["runtime_metrics"]["metadata"] = {
                str(key).strip(): value for key, value in metadata.items() if str(key).strip()
            }
        item["lease_expires_at"] = (
            now + timedelta(seconds=int(item["heartbeat_timeout_seconds"]))
        ).isoformat()
        return deepcopy(item)

    def report_failure(self, agent_id: str, *, error: str | None = None) -> dict[str, Any]:
        item = self._agents.get(_normalize_text(agent_id))
        if item is None:
            raise KeyError(f"External agent '{agent_id}' not found")
        settings = get_settings()
        now = _now()
        consecutive_failures = int(item.get("consecutive_failures") or 0) + 1
        threshold = max(1, int(settings.external_connection_circuit_breaker_threshold))
        base_seconds = max(1, int(settings.external_connection_backoff_base_seconds))
        max_seconds = max(base_seconds, int(settings.external_connection_backoff_max_seconds))
        backoff_seconds = min(max_seconds, base_seconds * (2 ** max(0, consecutive_failures - 1)))
        item["consecutive_failures"] = consecutive_failures
        item["last_failure_at"] = now.isoformat()
        item["last_error"] = _normalize_text(error) or None
        item["next_retry_at"] = (now + timedelta(seconds=backoff_seconds)).isoformat()
        item["runtime_status"] = "degraded"
        item["runtime_status_reason"] = "network_failure_backoff"
        item["status"] = "degraded"
        item["circuit_state"] = "open" if consecutive_failures >= threshold else "closed"
        item["circuit_open_until"] = (
            (now + timedelta(seconds=backoff_seconds)).isoformat()
            if item["circuit_state"] == "open"
            else None
        )
        item["routable"] = bool(item.get("enabled", True)) and item["circuit_state"] != "open"
        return deepcopy(item)

    def set_enabled(self, agent_id: str, *, enabled: bool) -> dict[str, Any]:
        item = self._agents.get(_normalize_text(agent_id))
        if item is None:
            raise KeyError(f"External agent '{agent_id}' not found")
        item["enabled"] = bool(enabled)
        if not enabled:
            item["runtime_status"] = "offline"
            item["runtime_status_reason"] = "agent_disabled"
            item["status"] = "offline"
            item["routable"] = False
            return deepcopy(item)

        runtime_status = _normalize_text(item.get("runtime_status")).lower() or "online"
        if runtime_status == "offline" and _normalize_text(item.get("runtime_status_reason")) == "agent_disabled":
            runtime_status = "online"
        item["runtime_status"] = runtime_status
        item["runtime_status_reason"] = "agent_enabled"
        item["status"] = "idle" if runtime_status == "online" else runtime_status
        item["routable"] = runtime_status in {"online", "degraded"}
        return deepcopy(item)

    def recover_agent(self, agent_id: str) -> dict[str, Any]:
        item = self._agents.get(_normalize_text(agent_id))
        if item is None:
            raise KeyError(f"External agent '{agent_id}' not found")
        item["consecutive_failures"] = 0
        item["last_error"] = None
        item["next_retry_at"] = None
        item["circuit_state"] = "closed"
        item["circuit_open_until"] = None
        item["runtime_status"] = "online"
        item["runtime_status_reason"] = "recovered"
        item["status"] = "idle"
        item["routable"] = bool(item.get("enabled", True))
        return deepcopy(item)

    def prune_expired(self, *, now: datetime | None = None) -> int:
        current = now or _now()
        changed = 0
        for item in self._agents.values():
            circuit_open_until = _parse_datetime(item.get("circuit_open_until"))
            if (
                str(item.get("circuit_state") or "").strip().lower() == "open"
                and circuit_open_until is not None
                and circuit_open_until <= current
            ):
                item["circuit_state"] = "half_open"
                item["runtime_status"] = "degraded"
                item["runtime_status_reason"] = "circuit_half_open"
                item["routable"] = bool(item.get("enabled", True))
                changed += 1
            lease_expires_at = _parse_datetime(item.get("lease_expires_at"))
            if lease_expires_at is None or lease_expires_at > current:
                continue
            if item.get("runtime_status") == "offline" and item.get("routable") is False:
                continue
            item["runtime_status"] = "offline"
            item["runtime_status_reason"] = "lease_expired"
            item["routable"] = False
            item["status"] = "offline"
            changed += 1
        return changed

    def _normalize_agent(self, payload: dict[str, Any]) -> dict[str, Any]:
        agent_id = _normalize_text(payload.get("id") or payload.get("agent_id") or payload.get("name"))
        if not agent_id:
            raise ValueError("External agent id is required")
        name = _normalize_text(payload.get("name") or agent_id)
        agent_type = _normalize_text(payload.get("type") or "default").lower() or "default"
        interval = _normalize_seconds(
            payload.get("heartbeat_interval_seconds") or payload.get("heartbeatIntervalSeconds"),
            default=DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
        )
        timeout = _normalize_seconds(
            payload.get("heartbeat_timeout_seconds") or payload.get("heartbeatTimeoutSeconds"),
            default=max(DEFAULT_HEARTBEAT_TIMEOUT_SECONDS, interval * 3),
            minimum=max(10, interval * 2),
        )
        now = _now()
        last_heartbeat_at = _parse_datetime(payload.get("last_heartbeat_at")) or now
        runtime_status = _normalize_text(payload.get("runtime_status") or "online").lower() or "online"
        enabled = bool(payload.get("enabled", True))
        routable = enabled and runtime_status in {"online", "degraded"}
        version = _normalize_text(payload.get("version") or "0.0.0")
        agent_family = (
            _normalize_text(payload.get("agent_family") or payload.get("agentFamily") or name).lower()
            or agent_id.lower()
        )
        compatibility = _normalize_list(payload.get("compatibility") or DEFAULT_COMPATIBILITY)
        if not compatibility:
            compatibility = [DEFAULT_COMPATIBILITY]
        release_channel = _normalize_text(
            payload.get("release_channel") or payload.get("releaseChannel") or DEFAULT_RELEASE_CHANNEL
        ).lower() or DEFAULT_RELEASE_CHANNEL
        if release_channel not in ALLOWED_RELEASE_CHANNELS:
            release_channel = DEFAULT_RELEASE_CHANNEL
        deprecated = _normalize_bool(payload.get("deprecated"), default=release_channel == "deprecated")
        default_version = _normalize_bool(payload.get("default_version") or payload.get("defaultVersion"))
        fallback_version_id = _normalize_text(
            payload.get("fallback_version_id") or payload.get("fallbackVersionId")
        ) or None
        rollout_policy = self._normalize_rollout_policy(
            payload.get("rollout_policy") or payload.get("rolloutPolicy"),
            release_channel=release_channel,
        )
        rollback_policy = self._normalize_rollback_policy(
            payload.get("rollback_policy") or payload.get("rollbackPolicy"),
            fallback_version_id=fallback_version_id or "",
        )
        base_url = _normalize_text(payload.get("base_url") or payload.get("baseUrl"))
        invoke_path = _normalize_text(payload.get("invoke_path") or payload.get("invokePath") or "/execute")
        health_path = _normalize_text(payload.get("health_path") or payload.get("healthPath") or "/health")
        method = _normalize_text(payload.get("method") or DEFAULT_METHOD).upper()
        capabilities = _normalize_list(payload.get("capabilities"))
        metadata = deepcopy(payload.get("metadata") or {})
        metadata.setdefault("registration_scope", "external_agent_registry")
        metadata.setdefault("version", version)
        metadata.setdefault("compatibility", compatibility)
        metadata.setdefault("release_channel", release_channel)
        metadata.setdefault("deprecated", deprecated)
        metadata.setdefault("rollout_policy", deepcopy(rollout_policy))
        metadata.setdefault("rollback_policy", deepcopy(rollback_policy))
        return {
            "id": agent_id,
            "agent_family": agent_family,
            "name": name,
            "description": _normalize_text(payload.get("description") or f"{name} external agent"),
            "type": agent_type,
            "status": "idle" if runtime_status == "online" else runtime_status,
            "enabled": enabled,
            "tasks_completed": int(payload.get("tasks_completed") or payload.get("tasksCompleted") or 0),
            "tasks_total": int(payload.get("tasks_total") or payload.get("tasksTotal") or 0),
            "avg_response_time": _normalize_text(payload.get("avg_response_time") or payload.get("avgResponseTime") or "0ms"),
            "tokens_used": int(payload.get("tokens_used") or payload.get("tokensUsed") or 0),
            "tokens_limit": int(payload.get("tokens_limit") or payload.get("tokensLimit") or 0),
            "success_rate": float(payload.get("success_rate") or payload.get("successRate") or 100.0),
            "last_active": _normalize_text(payload.get("last_active") or "刚刚"),
            "version": version,
            "compatibility": compatibility,
            "deprecated": deprecated,
            "release_channel": release_channel,
            "default_version": default_version,
            "fallback_version_id": fallback_version_id,
            "canary_percent": int(rollout_policy.get("canary_percent") or 0),
            "route_key": str(rollout_policy.get("route_key") or "global"),
            "rollout_policy": rollout_policy,
            "rollback_active": bool(rollback_policy.get("active")),
            "rollback_target_version_id": rollback_policy.get("target_version_id"),
            "rollback_policy": rollback_policy,
            "runtime_status": runtime_status,
            "runtime_status_reason": "registered",
            "routable": routable,
            "runtime_priority": 3 if runtime_status == "online" else 1 if runtime_status == "degraded" else 0,
            "last_heartbeat_at": last_heartbeat_at.isoformat(),
            "heartbeat_interval_seconds": interval,
            "heartbeat_timeout_seconds": timeout,
            "runtime_metrics": {
                "source": "external_agent_registry",
                "load": payload.get("load"),
                "queue_depth": payload.get("queue_depth") or payload.get("queueDepth"),
                "capabilities": capabilities,
                "version": version,
                "compatibility": compatibility,
                "release_channel": release_channel,
                "deprecated": deprecated,
                "rollout_policy": deepcopy(rollout_policy),
                "rollback_policy": deepcopy(rollback_policy),
            },
            "consecutive_failures": int(payload.get("consecutive_failures") or 0),
            "last_failure_at": _normalize_text(payload.get("last_failure_at")) or None,
            "last_error": _normalize_text(payload.get("last_error")) or None,
            "next_retry_at": _normalize_text(payload.get("next_retry_at")) or None,
            "circuit_state": _normalize_text(payload.get("circuit_state") or "closed").lower() or "closed",
            "circuit_open_until": _normalize_text(payload.get("circuit_open_until")) or None,
            "config_summary": {
                "source": "external_agent_registry",
                "version": version,
                "compatibility": compatibility,
                "deprecated": deprecated,
                "release_channel": release_channel,
                "default_version": default_version,
                "fallback_version_id": fallback_version_id,
                "rollout_policy": deepcopy(rollout_policy),
                "rollback_policy": deepcopy(rollback_policy),
                "capabilities": capabilities,
                "invocation": {
                    "protocol": _normalize_text(payload.get("protocol") or "http").lower() or "http",
                    "base_url": base_url,
                    "invoke_path": invoke_path,
                    "health_path": health_path,
                    "method": method,
                },
                "circuit_breaker": {
                    "state": _normalize_text(payload.get("circuit_state") or "closed").lower() or "closed",
                    "consecutive_failures": int(payload.get("consecutive_failures") or 0),
                },
            },
            "config_snapshot": {
                "status": "external_registered",
                "agent": {
                    "id": agent_id,
                    "name": name,
                    "family": agent_family,
                    "version": version,
                    "compatibility": compatibility,
                    "deprecated": deprecated,
                    "release_channel": release_channel,
                    "default_version": default_version,
                    "fallback_version_id": fallback_version_id,
                    "rollout_policy": deepcopy(rollout_policy),
                    "rollback_policy": deepcopy(rollback_policy),
                    "capabilities": capabilities,
                },
                "runtime": {
                    "source": "external_agent_registry",
                    "last_heartbeat_at": last_heartbeat_at.isoformat(),
                    "heartbeat_interval_seconds": interval,
                    "heartbeat_timeout_seconds": timeout,
                },
                "metadata": metadata,
            },
            "lease_expires_at": (
                _parse_datetime(payload.get("lease_expires_at"))
                or (last_heartbeat_at + timedelta(seconds=timeout))
            ).isoformat(),
        }

    def _normalize_rollout_policy(self, value: Any, *, release_channel: str) -> dict[str, Any]:
        policy = dict(value) if isinstance(value, dict) else {}
        mode = _normalize_text(policy.get("mode")).lower()
        if mode not in {"stable_only", "canary"}:
            mode = "canary" if _normalize_text(release_channel).lower() == "canary" else "stable_only"
        default_percent = 100 if mode == "canary" and _normalize_text(release_channel).lower() == "canary" else 0
        raw_percent = (
            policy.get("canary_percent")
            if "canary_percent" in policy
            else policy.get("canaryPercent")
        )
        canary_percent = _coerce_percent(
            raw_percent,
            default=default_percent,
        )
        route_key = _normalize_text(policy.get("route_key") or policy.get("routeKey") or "global") or "global"
        return {
            "mode": mode,
            "canary_percent": canary_percent,
            "route_key": route_key,
            "enabled": mode == "canary" and canary_percent > 0,
        }

    def _normalize_rollback_policy(self, value: Any, *, fallback_version_id: str) -> dict[str, Any]:
        policy = dict(value) if isinstance(value, dict) else {}
        target_version_id = _normalize_text(
            policy.get("target_version_id") or policy.get("targetVersionId") or fallback_version_id
        ) or None
        active = _normalize_bool(policy.get("active"))
        return {
            "active": active,
            "rollback_active": active,
            "target_version_id": target_version_id,
            "rollback_target_version_id": target_version_id,
        }

    def _selection_sort_key(self, item: dict[str, Any]) -> tuple[int, int, int, tuple[int, ...], str]:
        return (
            1 if bool(item.get("default_version")) else 0,
            _release_channel_rank(_normalize_text(item.get("release_channel")).lower()),
            0 if bool(item.get("deprecated")) else 1,
            _parse_version_parts(_normalize_text(item.get("version"))),
            _normalize_text(item.get("id")),
        )

    def _append_registry_audit(
        self,
        *,
        action: str,
        details: str,
        metadata: dict[str, Any],
    ) -> None:
        payload = {
            "id": f"audit-agent-registry-{uuid4().hex[:10]}",
            "timestamp": store.now_string(),
            "action": action,
            "user": "system",
            "resource": "external_agent_registry",
            "status": "success",
            "ip": "-",
            "details": details,
            "metadata": deepcopy(metadata),
        }
        store.audit_logs.insert(0, deepcopy(payload))
        del store.audit_logs[200:]
        persistence_service.append_audit_log(log=payload)
        trace_exporter_service.export_audit_event(payload)


external_agent_registry_service = ExternalAgentRegistryService()


def reset_external_agent_registry_state() -> None:
    external_agent_registry_service.clear()
