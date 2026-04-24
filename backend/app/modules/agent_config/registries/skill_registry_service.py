from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable


ALLOWED_ABILITY_TYPES = {"skill", "tool", "mcp"}


def _normalize_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_list(values: Iterable[object] | None, *, lowercase: bool = True) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_item in values or ():
        item = _normalize_text(raw_item)
        if not item:
            continue
        candidate = item.lower() if lowercase else item
        if candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)
    return normalized


def _parse_version_parts(value: object) -> tuple[int, ...]:
    normalized = _normalize_text(value).lower().lstrip("v")
    if not normalized:
        return (0,)
    parts: list[int] = []
    for piece in normalized.replace("-", ".").split("."):
        digits = "".join(char for char in piece if char.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts or [0])


def _release_channel_rank(value: object) -> int:
    normalized = _normalize_text(value).lower()
    return {
        "stable": 4,
        "canary": 3,
        "beta": 2,
        "alpha": 1,
        "deprecated": 0,
    }.get(normalized, 0)


class SkillRegistryService:
    def __init__(self) -> None:
        self._abilities_by_name: dict[str, dict[str, Any]] = {}
        self._abilities_by_id: dict[str, str] = {}

    def clear(self) -> None:
        self._abilities_by_name.clear()
        self._abilities_by_id.clear()

    def register_ability(self, ability: dict[str, Any], *, overwrite: bool = False) -> dict[str, Any]:
        normalized = self._normalize_ability(ability)
        name_key = normalized["name"].lower()
        if not overwrite and name_key in self._abilities_by_name:
            raise ValueError(f"Ability '{normalized['name']}' already registered")
        self._abilities_by_name[name_key] = normalized
        self._abilities_by_id[normalized["id"]] = name_key
        return self._clone_ability(normalized)

    def register_many(self, abilities: Iterable[dict[str, Any]], *, overwrite: bool = False) -> list[dict[str, Any]]:
        registered: list[dict[str, Any]] = []
        for ability in abilities:
            registered.append(self.register_ability(ability, overwrite=overwrite))
        return registered

    def get_ability(self, name_or_id: str) -> dict[str, Any] | None:
        key = _normalize_text(name_or_id)
        if not key:
            return None
        name_key = self._abilities_by_id.get(key) or key.lower()
        ability = self._abilities_by_name.get(name_key)
        return self._clone_ability(ability) if ability is not None else None

    def remove_ability(self, name_or_id: str) -> bool:
        key = _normalize_text(name_or_id)
        if not key:
            return False
        name_key = self._abilities_by_id.get(key) or key.lower()
        ability = self._abilities_by_name.pop(name_key, None)
        if ability is None:
            return False
        self._abilities_by_id.pop(str(ability.get("id") or "").strip(), None)
        return True

    def list_abilities(
        self,
        *,
        name: str | None = None,
        ability_type: str | None = None,
        tag: str | None = None,
        source: str | None = None,
        capability: str | None = None,
        enabled: bool | None = None,
    ) -> list[dict[str, Any]]:
        normalized_name = _normalize_text(name).lower() if name else None
        normalized_type = _normalize_text(ability_type).lower() if ability_type else None
        normalized_tag = _normalize_text(tag).lower() if tag else None
        normalized_source = _normalize_text(source).lower() if source else None
        normalized_capability = _normalize_text(capability).lower() if capability else None

        items: list[dict[str, Any]] = []
        for ability in self._abilities_by_name.values():
            if normalized_name and normalized_name not in ability["name"].lower():
                continue
            if normalized_type and ability["type"] != normalized_type:
                continue
            if normalized_tag and normalized_tag not in ability["tags"]:
                continue
            if normalized_source and ability["source"] != normalized_source:
                continue
            if normalized_capability and normalized_capability not in ability["capabilities"]:
                continue
            if enabled is not None and bool(ability["enabled"]) is not enabled:
                continue
            items.append(self._clone_ability(ability))

        items.sort(key=lambda item: (item["type"], item["source"], item["name"].lower()))
        return items

    def query_by_capabilities(
        self,
        required_capabilities: Iterable[object],
        *,
        ability_type: str | None = None,
        enabled: bool = True,
    ) -> list[dict[str, Any]]:
        normalized_required = _normalize_list(required_capabilities)
        if not normalized_required:
            return []

        required_set = set(normalized_required)
        candidates = self.list_abilities(
            ability_type=ability_type,
            enabled=enabled,
        )
        scored: list[tuple[int, int, dict[str, Any]]] = []
        for ability in candidates:
            matched = set(ability["capabilities"]) & required_set
            if not matched:
                continue
            metadata = ability.get("metadata") or {}
            registry = metadata.get("registry") if isinstance(metadata, dict) else {}
            if not isinstance(registry, dict):
                registry = {}
            deprecated_penalty = 0 if bool(registry.get("deprecated")) else 1
            default_bonus = 1 if bool(registry.get("default_version")) else 0
            channel_rank = _release_channel_rank(registry.get("release_channel"))
            version_rank = _parse_version_parts(registry.get("version"))
            scored.append(
                (
                    len(matched),
                    deprecated_penalty,
                    default_bonus,
                    channel_rank,
                    version_rank,
                    -len(ability["capabilities"]),
                    ability,
                )
            )
        scored.sort(
            key=lambda item: (
                -item[0],
                -item[1],
                -item[2],
                -item[3],
                tuple(-part for part in item[4]),
                item[5],
                item[6]["name"].lower(),
            )
        )
        return [self._clone_ability(item[6]) for item in scored]

    # Compatibility API used by existing execution chain.
    def list_skills(
        self,
        *,
        source: str | None = None,
        skill_type: str | None = None,
        tags: list[str] | None = None,
        capabilities: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        items = self.list_abilities(
            ability_type=skill_type,
            source=source,
            enabled=None,
        )
        requested_tags = {item.lower() for item in _normalize_list(tags)}
        requested_capabilities = {item.lower() for item in _normalize_list(capabilities)}
        filtered: list[dict[str, Any]] = []
        for ability in items:
            ability_tags = set(ability.get("tags") or [])
            ability_capabilities = set(ability.get("capabilities") or [])
            if requested_tags and not requested_tags.issubset(ability_tags):
                continue
            if requested_capabilities and not (requested_capabilities & ability_capabilities):
                continue
            filtered.append(ability)
        return filtered

    def get_skill(self, skill_id: str) -> dict[str, Any] | None:
        return self.get_ability(skill_id)

    def resolve_skill_for_capabilities(self, capabilities: list[str]) -> dict[str, Any] | None:
        matches = self.query_by_capabilities(capabilities, ability_type="skill", enabled=True)
        return matches[0] if matches else None

    def _normalize_ability(self, ability: dict[str, Any]) -> dict[str, Any]:
        name = _normalize_text(ability.get("name") or ability.get("id"))
        if not name:
            raise ValueError("Ability name is required")

        ability_type = _normalize_text(ability.get("type") or "skill").lower()
        if ability_type not in ALLOWED_ABILITY_TYPES:
            raise ValueError(f"Unsupported ability type '{ability_type}'")

        source = _normalize_text(ability.get("source") or "internal").lower()
        if not source:
            raise ValueError("Ability source is required")

        timeout_raw = ability.get("timeout_seconds", ability.get("timeout", 8.0))
        timeout_seconds = float(timeout_raw)
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        ability_id = _normalize_text(ability.get("id") or name.lower().replace(" ", "_"))
        if not ability_id:
            raise ValueError("Ability id is required")

        capabilities = _normalize_list(
            ability.get("capabilities") or ability.get("capability_tags"),
            lowercase=True,
        )
        normalized: dict[str, Any] = {
            "id": ability_id,
            "name": name,
            "type": ability_type,
            "source": source,
            "description": _normalize_text(ability.get("description")),
            "tags": _normalize_list(ability.get("tags"), lowercase=True),
            "capabilities": capabilities,
            "capability_tags": list(capabilities),
            "enabled": bool(ability.get("enabled", True)),
            "timeout_seconds": timeout_seconds,
            "timeout": timeout_seconds,
            "permissions": _normalize_list(ability.get("permissions"), lowercase=False),
            "input_schema": deepcopy(ability.get("input_schema") or ability.get("inputSchema") or {}),
            "output_schema": deepcopy(ability.get("output_schema") or ability.get("outputSchema") or {}),
            "metadata": deepcopy(ability.get("metadata") or {}),
            "handler": ability.get("handler"),
        }
        if not normalized["description"]:
            normalized["description"] = f"{name} ({ability_type})"
        return normalized

    def _clone_ability(self, ability: dict[str, Any]) -> dict[str, Any]:
        cloned = dict(ability)
        cloned["tags"] = list(ability.get("tags") or [])
        cloned["capabilities"] = list(ability.get("capabilities") or [])
        cloned["capability_tags"] = list(ability.get("capability_tags") or [])
        cloned["permissions"] = list(ability.get("permissions") or [])
        cloned["input_schema"] = deepcopy(ability.get("input_schema") or {})
        cloned["output_schema"] = deepcopy(ability.get("output_schema") or {})
        cloned["metadata"] = deepcopy(ability.get("metadata") or {})
        cloned["handler"] = ability.get("handler")
        return cloned


skill_registry_service = SkillRegistryService()
