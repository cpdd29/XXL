from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import uuid4

from app.config import get_settings
from app.services.persistence_service import persistence_service
from app.services.skill_registry_service import skill_registry_service
from app.services.store import store
from app.services.trace_exporter_service import trace_exporter_service


DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 15
DEFAULT_HEARTBEAT_TIMEOUT_SECONDS = 90
DEFAULT_METHOD = "POST"
ALLOWED_PROTOCOLS = {"http", "https", "mcp", "grpc"}
ALLOWED_MEMORY_SAFE_TYPES = {"session_summary", "preferences", "decisions", "task_result", "event"}
DEFAULT_RELEASE_CHANNEL = "stable"
DEFAULT_COMPATIBILITY = "brain-core-v1"
ALLOWED_RELEASE_CHANNELS = {"stable", "canary", "beta", "alpha", "deprecated"}


def _now() -> datetime:
    return datetime.now(UTC)


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_list(value: Any) -> list[str]:
    if isinstance(value, str):
        values = value.split(",")
    elif isinstance(value, list):
        values = value
    else:
        values = []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        candidate = _normalize_text(item).lower()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)
    return normalized


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


def _normalize_percent(value: Any, *, default: int = 0) -> int:
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        resolved = default
    return max(0, min(100, resolved))


def _stable_bucket(route_key: str, route_seed: str) -> int:
    digest = sha256(f"{route_key}:{route_seed}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


class ExternalSkillRegistryService:
    def __init__(self) -> None:
        self._skills: dict[str, dict[str, Any]] = {}

    def clear(self) -> None:
        self._skills.clear()

    def register_skill(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_skill(payload)
        self._skills[normalized["id"]] = normalized
        self._apply_version_governance(normalized["id"])
        normalized = self._skills[normalized["id"]]
        self._sync_to_skill_registry(normalized)
        self._append_registry_audit(
            action="external_skill_registry.registered",
            details=(
                f"id={normalized['id']}; version={normalized['version']}; "
                f"release_channel={normalized['release_channel']}; deprecated={normalized['deprecated']}"
            ),
            metadata={
                "registry": "external_skill_registry",
                "skill_id": normalized["id"],
                "skill_family": normalized["skill_family"],
                "version": normalized["version"],
                "release_channel": normalized["release_channel"],
                "compatibility": list(normalized.get("compatibility") or []),
                "deprecated": bool(normalized.get("deprecated")),
                "default_version": bool(normalized.get("default_version")),
                "fallback_version_id": normalized.get("fallback_version_id"),
            },
        )
        return deepcopy(normalized)

    def list_skills(self, *, include_offline: bool = True) -> list[dict[str, Any]]:
        self.prune_expired()
        items = []
        for item in self._skills.values():
            if not include_offline and not bool(item.get("routable", False)):
                continue
            items.append(deepcopy(item))
        items.sort(key=lambda item: (not bool(item.get("routable", False)), item["name"].lower()))
        return items

    def get_skill(self, skill_id: str) -> dict[str, Any] | None:
        self.prune_expired()
        item = self._skills.get(_normalize_text(skill_id))
        return deepcopy(item) if item is not None else None

    def select_skill(
        self,
        *,
        required_capabilities: list[str] | None = None,
        compatibility: str | None = None,
        release_channel: str | None = None,
        include_deprecated: bool = False,
        route_seed: str | None = None,
    ) -> dict[str, Any] | None:
        self.prune_expired()
        normalized_capabilities = set(_normalize_list(required_capabilities))
        normalized_compatibility = _normalize_text(compatibility or DEFAULT_COMPATIBILITY)
        normalized_channel = _normalize_text(release_channel or "").lower()
        candidates: list[dict[str, Any]] = []
        for item in self._skills.values():
            if not bool(item.get("routable", False)):
                continue
            if normalized_capabilities and not (set(item.get("capabilities") or []) & normalized_capabilities):
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
        candidates.sort(key=self._selection_sort_key, reverse=True)
        selected_family = _normalize_text(candidates[0].get("skill_family")).lower()
        family_candidates = [
            item
            for item in candidates
            if _normalize_text(item.get("skill_family")).lower() == selected_family
        ]
        rollback_candidate = self._select_rollback_target(family_candidates)
        if rollback_candidate is not None:
            return deepcopy(rollback_candidate)
        canary_candidate = self._select_canary_candidate(family_candidates)
        if canary_candidate is not None:
            stable_candidate = self._select_stable_candidate(family_candidates)
            if stable_candidate is None:
                return deepcopy(canary_candidate)
            effective_seed = _normalize_text(route_seed)
            if not effective_seed:
                effective_seed = _normalize_text(stable_candidate.get("id")) or "default"
            canary_percent = _normalize_percent(canary_candidate.get("canary_percent"), default=0)
            route_key = _normalize_text(canary_candidate.get("route_key")).lower() or selected_family or "default"
            if _stable_bucket(route_key, effective_seed) < canary_percent:
                return deepcopy(canary_candidate)
            return deepcopy(stable_candidate)
        return deepcopy(candidates[0])

    def resolve_fallback_version(self, skill_id_or_family: str) -> dict[str, Any] | None:
        normalized = _normalize_text(skill_id_or_family).lower()
        if not normalized:
            return None
        direct = self._skills.get(_normalize_text(skill_id_or_family))
        family = (
            _normalize_text((direct or {}).get("skill_family")).lower()
            if isinstance(direct, dict)
            else normalized
        )
        family_versions = [item for item in self._skills.values() if _normalize_text(item.get("skill_family")).lower() == family]
        if isinstance(direct, dict):
            fallback_id = _normalize_text(direct.get("fallback_version_id"))
            if fallback_id:
                fallback = self._skills.get(fallback_id)
                if isinstance(fallback, dict):
                    return deepcopy(fallback)
        eligible = [item for item in family_versions if bool(item.get("routable", False)) and not bool(item.get("deprecated", False))]
        if not eligible:
            return None
        eligible.sort(key=self._selection_sort_key, reverse=True)
        return deepcopy(eligible[0])

    def list_versions(self, family: str) -> list[dict[str, Any]]:
        normalized_family = _normalize_text(family).lower()
        items = [
            deepcopy(item)
            for item in self._skills.values()
            if _normalize_text(item.get("skill_family")).lower() == normalized_family
        ]
        items.sort(key=self._selection_sort_key, reverse=True)
        return items

    def promote_version(self, skill_id: str) -> dict[str, Any]:
        item = self._skills.get(_normalize_text(skill_id))
        if item is None:
            raise KeyError(f"External skill '{skill_id}' not found")
        family = _normalize_text(item.get("skill_family")).lower()
        for candidate in self._skills.values():
            if _normalize_text(candidate.get("skill_family")).lower() != family:
                continue
            candidate["default_version"] = str(candidate.get("id") or "") == item["id"]
        self._apply_version_governance(item["id"])
        self._sync_to_skill_registry(self._skills[item["id"]])
        return deepcopy(self._skills[item["id"]])

    def set_fallback_version(self, skill_id: str, fallback_version_id: str | None) -> dict[str, Any]:
        item = self._skills.get(_normalize_text(skill_id))
        if item is None:
            raise KeyError(f"External skill '{skill_id}' not found")
        item["fallback_version_id"] = _normalize_text(fallback_version_id) or None
        self._apply_version_governance(item["id"])
        self._sync_to_skill_registry(self._skills[item["id"]])
        return deepcopy(self._skills[item["id"]])

    def set_deprecated(self, skill_id: str, *, deprecated: bool) -> dict[str, Any]:
        item = self._skills.get(_normalize_text(skill_id))
        if item is None:
            raise KeyError(f"External skill '{skill_id}' not found")
        item["deprecated"] = bool(deprecated)
        item["release_channel"] = "deprecated" if deprecated else (
            _normalize_text(item.get("release_channel")).lower() or DEFAULT_RELEASE_CHANNEL
        )
        if deprecated:
            item["default_version"] = False
        self._apply_version_governance(item["id"])
        self._sync_to_skill_registry(self._skills[item["id"]])
        return deepcopy(self._skills[item["id"]])

    def set_rollout_policy(self, skill_id: str, rollout_policy: dict[str, Any] | None) -> dict[str, Any]:
        item = self._skills.get(_normalize_text(skill_id))
        if item is None:
            raise KeyError(f"External skill '{skill_id}' not found")
        policy = dict(rollout_policy) if isinstance(rollout_policy, dict) else {}
        raw_percent = (
            policy.get("canary_percent")
            if "canary_percent" in policy
            else policy.get("canaryPercent")
        )
        item["canary_percent"] = _normalize_percent(
            raw_percent,
            default=int(item.get("canary_percent") or 0),
        )
        item["route_key"] = _normalize_text(
            policy.get("route_key") or policy.get("routeKey") or item.get("route_key") or "global"
        ).lower() or "global"
        item["rollout_policy"] = {
            "canary_percent": int(item.get("canary_percent") or 0),
            "route_key": item["route_key"],
        }
        self._apply_version_governance(item["id"])
        self._sync_to_skill_registry(self._skills[item["id"]])
        return deepcopy(self._skills[item["id"]])

    def set_rollback_policy(self, skill_id: str, rollback_policy: dict[str, Any] | None) -> dict[str, Any]:
        item = self._skills.get(_normalize_text(skill_id))
        if item is None:
            raise KeyError(f"External skill '{skill_id}' not found")
        policy = dict(rollback_policy) if isinstance(rollback_policy, dict) else {}
        item["rollback_active"] = _normalize_bool(
            policy.get("rollback_active")
            if policy.get("rollback_active") is not None
            else policy.get("active"),
            default=bool(item.get("rollback_active", False)),
        )
        item["rollback_target_version_id"] = _normalize_text(
            policy.get("rollback_target_version_id")
            or policy.get("rollbackTargetVersionId")
            or policy.get("target_version_id")
            or policy.get("targetVersionId")
            or item.get("rollback_target_version_id")
            or item.get("fallback_version_id")
        ) or None
        item["rollback_policy"] = {
            "active": bool(item.get("rollback_active", False)),
            "rollback_active": bool(item.get("rollback_active", False)),
            "target_version_id": item.get("rollback_target_version_id"),
            "rollback_target_version_id": item.get("rollback_target_version_id"),
        }
        self._apply_version_governance(item["id"])
        self._sync_to_skill_registry(self._skills[item["id"]])
        return deepcopy(self._skills[item["id"]])

    def report_heartbeat(
        self,
        skill_id: str,
        *,
        status: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        item = self._skills.get(_normalize_text(skill_id))
        if item is None:
            raise KeyError(f"External skill '{skill_id}' not found")
        now = _now()
        item["last_heartbeat_at"] = now.isoformat()
        item["lease_expires_at"] = (
            now + timedelta(seconds=int(item["heartbeat_timeout_seconds"]))
        ).isoformat()
        health_status = _normalize_text(status).lower() or "healthy"
        if health_status not in {"healthy", "degraded", "offline", "error"}:
            health_status = "healthy"
        item["health_status"] = health_status
        item["consecutive_failures"] = 0
        item["circuit_state"] = "closed"
        item["circuit_open_until"] = None
        item["next_retry_at"] = None
        item["routable"] = bool(item.get("enabled", True)) and health_status in {"healthy", "degraded"}
        item["health_summary"] = {
            "status": health_status,
            "checked_at": now.isoformat(),
            "reason": "heartbeat_accepted",
        }
        if metadata:
            item["metadata"] = {
                **deepcopy(item.get("metadata") or {}),
                **{str(key).strip(): value for key, value in metadata.items() if str(key).strip()},
            }
        self._sync_to_skill_registry(item)
        return deepcopy(item)

    def report_failure(self, skill_id: str, *, error: str | None = None) -> dict[str, Any]:
        item = self._skills.get(_normalize_text(skill_id))
        if item is None:
            raise KeyError(f"External skill '{skill_id}' not found")
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
        item["health_status"] = "degraded"
        item["health_summary"] = {
            "status": "degraded",
            "checked_at": now.isoformat(),
            "reason": "network_failure_backoff",
        }
        item["circuit_state"] = "open" if consecutive_failures >= threshold else "closed"
        item["circuit_open_until"] = (
            (now + timedelta(seconds=backoff_seconds)).isoformat()
            if item["circuit_state"] == "open"
            else None
        )
        item["routable"] = bool(item.get("enabled", True)) and item["circuit_state"] != "open"
        self._sync_to_skill_registry(item)
        return deepcopy(item)

    def recover_skill(self, skill_id: str) -> dict[str, Any]:
        item = self._skills.get(_normalize_text(skill_id))
        if item is None:
            raise KeyError(f"External skill '{skill_id}' not found")
        now = _now()
        item["consecutive_failures"] = 0
        item["last_failure_at"] = None
        item["last_error"] = None
        item["next_retry_at"] = None
        item["circuit_state"] = "closed"
        item["circuit_open_until"] = None
        item["health_status"] = "healthy"
        item["health_summary"] = {
            "status": "healthy",
            "checked_at": now.isoformat(),
            "reason": "recovered",
        }
        item["routable"] = bool(item.get("enabled", True))
        self._sync_to_skill_registry(item)
        return deepcopy(item)

    def prune_expired(self, *, now: datetime | None = None) -> int:
        current = now or _now()
        changed = 0
        for item in self._skills.values():
            circuit_open_until = _parse_datetime(item.get("circuit_open_until"))
            if (
                str(item.get("circuit_state") or "").strip().lower() == "open"
                and circuit_open_until is not None
                and circuit_open_until <= current
            ):
                item["circuit_state"] = "half_open"
                item["health_status"] = "degraded"
                item["routable"] = bool(item.get("enabled", True))
                item["health_summary"] = {
                    "status": "degraded",
                    "checked_at": current.isoformat(),
                    "reason": "circuit_half_open",
                }
                self._sync_to_skill_registry(item)
                changed += 1
            lease_expires_at = _parse_datetime(item.get("lease_expires_at"))
            if lease_expires_at is None or lease_expires_at > current:
                continue
            if item.get("health_status") == "offline" and item.get("routable") is False:
                continue
            item["health_status"] = "offline"
            item["routable"] = False
            item["health_summary"] = {
                "status": "offline",
                "checked_at": current.isoformat(),
                "reason": "lease_expired",
            }
            changed += 1
            self._sync_to_skill_registry(item)
        return changed

    def _family_versions(self, family: str) -> list[dict[str, Any]]:
        normalized_family = _normalize_text(family).lower()
        return [
            item
            for item in self._skills.values()
            if _normalize_text(item.get("skill_family")).lower() == normalized_family
        ]

    def _validate_fallback_reference(self, item: dict[str, Any]) -> None:
        fallback_version_id = _normalize_text(item.get("fallback_version_id"))
        if not fallback_version_id:
            return
        fallback = self._skills.get(fallback_version_id)
        if fallback is None:
            raise ValueError(f"Fallback skill version '{fallback_version_id}' not found")
        if _normalize_text(fallback.get("skill_family")).lower() != _normalize_text(item.get("skill_family")).lower():
            raise ValueError("Fallback skill version must belong to the same family")
        item_compatibility = set(item.get("compatibility") or [])
        fallback_compatibility = set(fallback.get("compatibility") or [])
        if item_compatibility and fallback_compatibility and not (item_compatibility & fallback_compatibility):
            raise ValueError("Fallback skill version compatibility does not overlap")

    def _validate_rollback_reference(self, item: dict[str, Any]) -> None:
        rollback_target_version_id = _normalize_text(item.get("rollback_target_version_id"))
        if not rollback_target_version_id:
            return
        rollback_target = self._skills.get(rollback_target_version_id)
        if rollback_target is None:
            raise ValueError(f"Rollback target skill version '{rollback_target_version_id}' not found")
        if _normalize_text(rollback_target.get("skill_family")).lower() != _normalize_text(item.get("skill_family")).lower():
            raise ValueError("Rollback target skill version must belong to the same family")

    def _select_rollback_target(self, family_candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not family_candidates:
            return None
        by_id = {str(item.get("id") or ""): item for item in family_candidates}
        ordered = sorted(family_candidates, key=self._selection_sort_key, reverse=True)
        for item in ordered:
            if not bool(item.get("rollback_active", False)):
                continue
            target_id = _normalize_text(item.get("rollback_target_version_id"))
            if not target_id:
                continue
            target = by_id.get(target_id)
            if target is None:
                continue
            if bool(target.get("deprecated", False)) or not bool(target.get("routable", False)):
                continue
            return target
        return None

    def _select_canary_candidate(self, family_candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
        canaries = []
        for item in family_candidates:
            if _normalize_text(item.get("release_channel")).lower() != "canary":
                continue
            if bool(item.get("deprecated", False)) or not bool(item.get("routable", False)):
                continue
            if _normalize_percent(item.get("canary_percent"), default=0) <= 0:
                continue
            canaries.append(item)
        if not canaries:
            return None
        canaries.sort(
            key=lambda item: (
                _normalize_percent(item.get("canary_percent"), default=0),
                self._selection_sort_key(item),
            ),
            reverse=True,
        )
        return canaries[0]

    def _select_stable_candidate(self, family_candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
        stables = [
            item
            for item in family_candidates
            if _normalize_text(item.get("release_channel")).lower() == "stable"
            and not bool(item.get("deprecated", False))
            and bool(item.get("routable", False))
        ]
        if stables:
            preferred_default = [item for item in stables if bool(item.get("default_version"))]
            if preferred_default:
                preferred_default.sort(key=self._selection_sort_key, reverse=True)
                return preferred_default[0]
            stables.sort(key=self._selection_sort_key, reverse=True)
            return stables[0]
        routable = [
            item
            for item in family_candidates
            if not bool(item.get("deprecated", False)) and bool(item.get("routable", False))
        ]
        if not routable:
            return None
        preferred_default = [item for item in routable if bool(item.get("default_version"))]
        if preferred_default:
            preferred_default.sort(key=self._selection_sort_key, reverse=True)
            return preferred_default[0]
        routable.sort(key=self._selection_sort_key, reverse=True)
        return routable[0]

    def _apply_version_governance(self, skill_id: str) -> None:
        item = self._skills.get(_normalize_text(skill_id))
        if item is None:
            return
        self._validate_fallback_reference(item)
        self._validate_rollback_reference(item)
        family = _normalize_text(item.get("skill_family")).lower()
        family_versions = self._family_versions(family)
        if bool(item.get("default_version")):
            for candidate in family_versions:
                if candidate is item:
                    continue
                candidate["default_version"] = False
        if bool(item.get("deprecated")):
            item["release_channel"] = "deprecated"
            item["routable"] = False
            item["health_status"] = "offline"
            item["health_summary"] = {
                "status": "offline",
                "checked_at": _now().isoformat(),
                "reason": "deprecated_version",
            }
        else:
            item["routable"] = bool(item.get("enabled", True)) and str(item.get("health_status") or "").strip().lower() in {"healthy", "degraded"}
        if not any(bool(candidate.get("default_version")) for candidate in family_versions if not bool(candidate.get("deprecated"))):
            eligible = [candidate for candidate in family_versions if not bool(candidate.get("deprecated"))]
            if eligible:
                eligible.sort(key=self._selection_sort_key, reverse=True)
                eligible[0]["default_version"] = True

    def _normalize_skill(self, payload: dict[str, Any]) -> dict[str, Any]:
        skill_id = _normalize_text(payload.get("id") or payload.get("skill_id") or payload.get("name"))
        if not skill_id:
            raise ValueError("External skill id is required")
        name = _normalize_text(payload.get("name") or skill_id)
        version = _normalize_text(payload.get("version") or "0.0.0")
        skill_family = (
            _normalize_text(payload.get("skill_family") or payload.get("skillFamily") or name).lower()
            or skill_id.lower()
        )
        protocol = _normalize_text(payload.get("protocol") or payload.get("transport") or "http").lower()
        if protocol not in ALLOWED_PROTOCOLS:
            protocol = "http"
        base_url = _normalize_text(payload.get("base_url") or payload.get("baseUrl"))
        invoke_path = _normalize_text(payload.get("invoke_path") or payload.get("invokePath") or "/invoke")
        health_path = _normalize_text(payload.get("health_path") or payload.get("healthPath") or "/health")
        method = _normalize_text(payload.get("method") or payload.get("http_method") or DEFAULT_METHOD).upper()
        interval = _normalize_seconds(
            payload.get("heartbeat_interval_seconds") or payload.get("heartbeatIntervalSeconds"),
            default=DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
        )
        timeout = _normalize_seconds(
            payload.get("heartbeat_timeout_seconds") or payload.get("heartbeatTimeoutSeconds"),
            default=max(DEFAULT_HEARTBEAT_TIMEOUT_SECONDS, interval * 3),
            minimum=max(10, interval * 2),
        )
        enabled = bool(payload.get("enabled", True))
        now = _now()
        last_heartbeat_at = _parse_datetime(payload.get("last_heartbeat_at")) or now
        health_status = _normalize_text(payload.get("health_status") or "healthy").lower() or "healthy"
        routable = enabled and health_status in {"healthy", "degraded"}
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
        raw_canary_percent = (
            payload.get("canary_percent")
            if payload.get("canary_percent") is not None
            else payload.get("canaryPercent")
            if payload.get("canaryPercent") is not None
            else (payload.get("rollout_policy") or {}).get("canary_percent")
            if (payload.get("rollout_policy") or {}).get("canary_percent") is not None
            else (payload.get("traffic_policy") or {}).get("canary_percent")
        )
        canary_percent = _normalize_percent(
            raw_canary_percent,
            default=0,
        )
        route_key = _normalize_text(
            payload.get("route_key")
            or payload.get("routeKey")
            or (payload.get("rollout_policy") or {}).get("route_key")
            or (payload.get("traffic_policy") or {}).get("route_key")
        ).lower() or skill_family
        rollback_active = _normalize_bool(
            payload.get("rollback_active")
            if payload.get("rollback_active") is not None
            else payload.get("rollbackActive")
            if payload.get("rollbackActive") is not None
            else (payload.get("rollback_policy") or {}).get("rollback_active"),
            default=False,
        )
        rollback_target_version_id = _normalize_text(
            payload.get("rollback_target_version_id")
            or payload.get("rollbackTargetVersionId")
            or (payload.get("rollback_policy") or {}).get("rollback_target_version_id")
        ) or None
        input_schema = deepcopy(payload.get("input_schema") or payload.get("inputSchema") or {})
        output_schema = deepcopy(payload.get("output_schema") or payload.get("outputSchema") or {})
        capabilities = _normalize_list(payload.get("capabilities") or payload.get("capability_tags"))
        tags = _normalize_list(payload.get("tags"))
        metadata = deepcopy(payload.get("metadata") or {})
        metadata.setdefault("registration_scope", "external_skill_registry")
        metadata.setdefault("version", version)
        metadata.setdefault("compatibility", compatibility)
        metadata.setdefault("release_channel", release_channel)
        metadata.setdefault("deprecated", deprecated)
        metadata.setdefault("canary_percent", canary_percent)
        metadata.setdefault("route_key", route_key)
        metadata.setdefault("rollback_active", rollback_active)
        metadata.setdefault("rollback_target_version_id", rollback_target_version_id)
        metadata.setdefault(
            "rollout_policy",
            {
                "canary_percent": canary_percent,
                "route_key": route_key,
            },
        )
        metadata.setdefault(
            "rollback_policy",
            {
                "active": rollback_active,
                "rollback_active": rollback_active,
                "target_version_id": rollback_target_version_id,
                "rollback_target_version_id": rollback_target_version_id,
            },
        )
        metadata.setdefault("memory_safe_types", sorted(ALLOWED_MEMORY_SAFE_TYPES))
        return {
            "id": skill_id,
            "skill_family": skill_family,
            "name": name,
            "type": "skill",
            "source": "external_registry",
            "description": _normalize_text(payload.get("description") or f"{name} external skill"),
            "version": version,
            "compatibility": compatibility,
            "deprecated": deprecated,
            "release_channel": release_channel,
            "default_version": default_version,
            "fallback_version_id": fallback_version_id,
            "canary_percent": canary_percent,
            "route_key": route_key,
            "rollout_policy": {
                "canary_percent": canary_percent,
                "route_key": route_key,
            },
            "rollback_active": rollback_active,
            "rollback_target_version_id": rollback_target_version_id,
            "rollback_policy": {
                "active": rollback_active,
                "rollback_active": rollback_active,
                "target_version_id": rollback_target_version_id,
                "rollback_target_version_id": rollback_target_version_id,
            },
            "enabled": enabled,
            "routable": routable,
            "capabilities": capabilities,
            "tags": tags,
            "timeout_seconds": float(payload.get("timeout_seconds") or payload.get("timeout") or 8.0),
            "input_schema": input_schema,
            "output_schema": output_schema,
            "metadata": metadata,
            "protocol": protocol,
            "base_url": base_url,
            "invoke_path": invoke_path,
            "health_path": health_path,
            "method": method,
            "heartbeat_interval_seconds": interval,
            "heartbeat_timeout_seconds": timeout,
            "last_heartbeat_at": last_heartbeat_at.isoformat(),
            "lease_expires_at": (
                _parse_datetime(payload.get("lease_expires_at"))
                or (last_heartbeat_at + timedelta(seconds=timeout))
            ).isoformat(),
            "health_status": health_status if enabled else "disabled",
            "health_summary": {
                "status": health_status if enabled else "disabled",
                "checked_at": now.isoformat(),
                "reason": "registered",
            },
            "consecutive_failures": int(payload.get("consecutive_failures") or 0),
            "last_failure_at": _normalize_text(payload.get("last_failure_at")) or None,
            "last_error": _normalize_text(payload.get("last_error")) or None,
            "next_retry_at": _normalize_text(payload.get("next_retry_at")) or None,
            "circuit_state": _normalize_text(payload.get("circuit_state") or "closed").lower() or "closed",
            "circuit_open_until": _normalize_text(payload.get("circuit_open_until")) or None,
            "invocation": {
                "protocol": protocol,
                "base_url": base_url,
                "invoke_path": invoke_path,
                "health_path": health_path,
                "method": method,
            },
        }

    def _sync_to_skill_registry(self, item: dict[str, Any]) -> None:
        skill_registry_service.register_ability(
            {
                "id": item["id"],
                "name": item["name"],
                "type": "skill",
                "source": item["source"],
                "description": item["description"],
                "tags": item["tags"],
                "capabilities": item["capabilities"],
                "enabled": bool(item.get("routable", False)),
                "timeout_seconds": item["timeout_seconds"],
                "input_schema": deepcopy(item.get("input_schema") or {}),
                "output_schema": deepcopy(item.get("output_schema") or {}),
                "metadata": {
                    **deepcopy(item.get("metadata") or {}),
                    "registry": {
                        "origin": "external_skill_registry",
                        "family": item.get("skill_family"),
                        "version": item.get("version"),
                        "compatibility": deepcopy(item.get("compatibility") or []),
                        "deprecated": bool(item.get("deprecated")),
                        "release_channel": item.get("release_channel"),
                        "default_version": bool(item.get("default_version")),
                        "fallback_version_id": item.get("fallback_version_id"),
                        "canary_percent": _normalize_percent(item.get("canary_percent"), default=0),
                        "route_key": _normalize_text(item.get("route_key")).lower() or _normalize_text(item.get("skill_family")).lower(),
                        "rollout_policy": deepcopy(item.get("rollout_policy") or {}),
                        "rollback_active": bool(item.get("rollback_active", False)),
                        "rollback_target_version_id": item.get("rollback_target_version_id"),
                        "rollback_policy": deepcopy(item.get("rollback_policy") or {}),
                        "invocation": deepcopy(item.get("invocation") or {}),
                        "health_status": item.get("health_status"),
                        "lease_expires_at": item.get("lease_expires_at"),
                    },
                },
            },
            overwrite=True,
        )

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
            "id": f"audit-skill-registry-{uuid4().hex[:10]}",
            "timestamp": store.now_string(),
            "action": action,
            "user": "system",
            "resource": "external_skill_registry",
            "status": "success",
            "ip": "-",
            "details": details,
            "metadata": deepcopy(metadata),
        }
        store.audit_logs.insert(0, deepcopy(payload))
        del store.audit_logs[200:]
        persistence_service.append_audit_log(log=payload)
        trace_exporter_service.export_audit_event(payload)


external_skill_registry_service = ExternalSkillRegistryService()


def reset_external_skill_registry_state() -> None:
    external_skill_registry_service.clear()
