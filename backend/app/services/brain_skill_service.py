from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Any

from fastapi import HTTPException, status
import yaml

from app.services.persistence_service import persistence_service
from app.services.skill_registry_service import skill_registry_service
from app.services.store import store


BRAIN_SKILL_LIBRARY_SETTING_KEY = "brain_skill_library"
BRAIN_SKILL_LIBRARY_SOURCE = "local_brain_skill_library"
DEFAULT_TIMEOUT_SECONDS = 8.0
SUPPORTED_FILE_SUFFIXES = {
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
}
FRONT_MATTER_PATTERN = re.compile(r"\A---\s*\n(?P<front>.*?)\n---\s*(?:\n(?P<body>.*))?\Z", re.DOTALL)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _normalize_string_list(value: object) -> list[str]:
    if isinstance(value, str):
        candidates = [segment.strip() for segment in value.split(",")]
    elif isinstance(value, list):
        candidates = [str(item or "").strip() for item in value]
    else:
        candidates = []

    items: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate:
            continue
        lowered = candidate.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        items.append(candidate)
    return items


def _normalize_bool(value: object, *, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value in {None, ""}:
        return default
    normalized = _normalize_text(value).lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _normalize_timeout(value: object) -> float:
    if value in {None, ""}:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_SECONDS
    return timeout if timeout > 0 else DEFAULT_TIMEOUT_SECONDS


def _slugify(value: str) -> str:
    normalized = "".join(character.lower() if character.isalnum() else "-" for character in value)
    normalized = "-".join(segment for segment in normalized.split("-") if segment)
    return normalized or "skill"


def _display_name_from_file(file_name: str) -> str:
    stem = Path(file_name).stem.replace("-", " ").replace("_", " ").strip()
    return stem or "Untitled Skill"


def _detect_format(file_name: str) -> str:
    suffix = Path(file_name).suffix.lower()
    format_name = SUPPORTED_FILE_SUFFIXES.get(suffix)
    if not format_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅支持上传 .json、.yaml、.yml、.md 格式的 skill 文件",
        )
    return format_name


def _first_body_paragraph(body: str) -> str:
    paragraphs = [segment.strip() for segment in re.split(r"\n\s*\n", body) if segment.strip()]
    if not paragraphs:
        return ""
    first = paragraphs[0]
    cleaned_lines = [line.lstrip("#*- ").strip() for line in first.splitlines()]
    return " ".join(line for line in cleaned_lines if line).strip()


def _normalize_schema(value: object) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _normalize_metadata(value: object) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


class BrainSkillService:
    def __init__(
        self,
        *,
        runtime_store: Any = None,
        persistence: Any = None,
        registry: Any = None,
    ) -> None:
        self._runtime_store = runtime_store or store
        self._persistence = persistence or persistence_service
        self._registry = registry or skill_registry_service

    def bootstrap(self) -> None:
        self._sync_registry(self._library_items())

    def list_skills(self) -> dict[str, Any]:
        items = sorted(
            (self._public_item(item) for item in self._library_items()),
            key=lambda item: (
                str(item.get("uploaded_at") or ""),
                str(item.get("name") or "").lower(),
            ),
            reverse=True,
        )
        return {
            "items": items,
            "total": len(items),
        }

    def upload_skill(self, payload: dict[str, Any]) -> dict[str, Any]:
        file_name = _normalize_text(payload.get("file_name") or payload.get("fileName"))
        content = str(payload.get("content") or "")
        if not file_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Skill 文件名不能为空")
        if not content.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Skill 文件内容不能为空")

        parsed = self._parse_uploaded_file(file_name=file_name, content=content)
        items = self._library_items()
        existing_ids = {str(item.get("id") or "").strip() for item in items}
        existing_files = {str(item.get("file_name") or "").strip().lower() for item in items}
        if parsed["id"] in existing_ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="本地 skill 库中已存在相同 Skill ID")
        if file_name.strip().lower() in existing_files:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="本地 skill 库中已存在同名文件，请先删除后再上传")

        now = _now_iso()
        item = {
            "id": parsed["id"],
            "name": parsed["name"],
            "file_name": file_name.strip(),
            "format": parsed["format"],
            "description": parsed["description"],
            "enabled": parsed["enabled"],
            "tags": parsed["tags"],
            "capabilities": parsed["capabilities"],
            "uploaded_at": now,
            "updated_at": now,
            "content": content,
            "manifest": parsed["manifest"],
            "ability": self._build_runtime_ability(
                skill_id=parsed["id"],
                display_name=parsed["name"],
                description=parsed["description"],
                enabled=parsed["enabled"],
                tags=parsed["tags"],
                capabilities=parsed["capabilities"],
                file_name=file_name.strip(),
                format_name=parsed["format"],
                uploaded_at=now,
                manifest=parsed["manifest"],
            ),
        }
        items.append(item)
        self._persist_library(items)
        self._sync_registry(items)
        return {
            "ok": True,
            "message": f"已上传 Skill {item['name']} 到本地 skill 库",
            "skill": self._public_item(item),
        }

    def delete_skill(self, skill_id: str) -> dict[str, Any]:
        normalized_id = _normalize_text(skill_id)
        items = self._library_items()
        for index, item in enumerate(items):
            if str(item.get("id") or "").strip() != normalized_id:
                continue
            removed = items.pop(index)
            self._persist_library(items)
            self._sync_registry(items)
            return {
                "ok": True,
                "message": f"已从本地 skill 库删除 {removed['name']}",
                "skill_id": normalized_id,
            }
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到对应的本地 skill")

    def resolve_skill_summaries(self, skill_ids: list[str] | None) -> list[dict[str, Any]]:
        requested_ids = [_normalize_text(item) for item in (skill_ids or []) if _normalize_text(item)]
        if not requested_ids:
            return []
        items_by_id = {
            str(item.get("id") or "").strip(): item
            for item in self._library_items()
        }
        resolved: list[dict[str, Any]] = []
        for skill_id in requested_ids:
            item = items_by_id.get(skill_id)
            if item is None:
                continue
            resolved.append(
                {
                    "id": str(item.get("id") or "").strip(),
                    "name": str(item.get("name") or "").strip(),
                    "file_name": str(item.get("file_name") or "").strip(),
                    "format": str(item.get("format") or "").strip(),
                    "description": str(item.get("description") or "").strip() or None,
                    "tags": list(item.get("tags") or []),
                    "capabilities": list(item.get("capabilities") or []),
                }
            )
        return resolved

    def validate_skill_ids(self, skill_ids: list[str] | None) -> list[str]:
        normalized_ids = [_normalize_text(item) for item in (skill_ids or []) if _normalize_text(item)]
        if not normalized_ids:
            return []
        available_ids = {
            str(item.get("id") or "").strip()
            for item in self._library_items()
        }
        invalid_ids = [item for item in normalized_ids if item not in available_ids]
        if invalid_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"未找到以下 Skill: {', '.join(invalid_ids)}",
            )
        deduplicated: list[str] = []
        seen: set[str] = set()
        for item in normalized_ids:
            if item in seen:
                continue
            seen.add(item)
            deduplicated.append(item)
        return deduplicated

    def _parse_uploaded_file(self, *, file_name: str, content: str) -> dict[str, Any]:
        format_name = _detect_format(file_name)
        normalized_content = content.replace("\r\n", "\n").strip()
        if format_name == "json":
            try:
                manifest = json.loads(normalized_content or "{}")
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"JSON 解析失败: {exc.msg}") from exc
            body = ""
        elif format_name == "yaml":
            try:
                manifest = yaml.safe_load(normalized_content or "{}")
            except yaml.YAMLError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="YAML 解析失败，请检查语法") from exc
            body = ""
        else:
            manifest, body = self._parse_markdown_skill(normalized_content)

        if manifest is None:
            manifest = {}
        if not isinstance(manifest, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Skill 文件顶层内容必须是对象结构")

        display_name = (
            _normalize_text(manifest.get("name"))
            or _normalize_text(manifest.get("title"))
            or _display_name_from_file(file_name)
        )
        skill_id = _normalize_text(manifest.get("id")) or f"brain-skill-{_slugify(Path(file_name).stem)}"
        description = (
            _normalize_text(manifest.get("description"))
            or _normalize_text(manifest.get("summary"))
            or _normalize_text(manifest.get("purpose"))
            or _first_body_paragraph(body)
        )
        return {
            "id": skill_id,
            "name": display_name,
            "format": format_name,
            "description": description,
            "enabled": _normalize_bool(manifest.get("enabled"), default=True),
            "tags": _normalize_string_list(manifest.get("tags")),
            "capabilities": _normalize_string_list(
                manifest.get("capabilities")
                or manifest.get("capability_tags")
                or manifest.get("capabilityTags")
            ),
            "manifest": {
                **deepcopy(manifest),
                **({"body": body} if body else {}),
            },
        }

    def _parse_markdown_skill(self, content: str) -> tuple[dict[str, Any], str]:
        matched = FRONT_MATTER_PATTERN.match(content)
        if not matched:
            return {}, content
        front_matter = matched.group("front") or ""
        body = (matched.group("body") or "").strip()
        try:
            parsed = yaml.safe_load(front_matter or "{}")
        except yaml.YAMLError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Markdown Front Matter 解析失败") from exc
        if parsed is None:
            parsed = {}
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Markdown Front Matter 必须是对象结构")
        return parsed, body

    def _build_runtime_ability(
        self,
        *,
        skill_id: str,
        display_name: str,
        description: str,
        enabled: bool,
        tags: list[str],
        capabilities: list[str],
        file_name: str,
        format_name: str,
        uploaded_at: str,
        manifest: dict[str, Any],
    ) -> dict[str, Any]:
        metadata = _normalize_metadata(manifest.get("metadata"))
        metadata.update(
            {
                "display_name": display_name,
                "registration_scope": "brain_skill_library",
                "file_name": file_name,
                "format": format_name,
                "uploaded_at": uploaded_at,
            }
        )
        return {
            "id": skill_id,
            "name": f"brain_skill::{skill_id}",
            "type": "skill",
            "source": BRAIN_SKILL_LIBRARY_SOURCE,
            "description": description,
            "tags": tags,
            "capabilities": capabilities,
            "enabled": enabled,
            "timeout_seconds": _normalize_timeout(
                manifest.get("timeout_seconds")
                or manifest.get("timeoutSeconds")
                or manifest.get("timeout")
            ),
            "permissions": _normalize_string_list(manifest.get("permissions")),
            "input_schema": _normalize_schema(manifest.get("input_schema") or manifest.get("inputSchema")),
            "output_schema": _normalize_schema(manifest.get("output_schema") or manifest.get("outputSchema")),
            "metadata": metadata,
        }

    def _public_item(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(item.get("id") or "").strip(),
            "name": str(item.get("name") or "").strip(),
            "file_name": str(item.get("file_name") or "").strip(),
            "format": str(item.get("format") or "").strip(),
            "description": str(item.get("description") or "").strip() or None,
            "enabled": bool(item.get("enabled", True)),
            "tags": list(item.get("tags") or []),
            "capabilities": list(item.get("capabilities") or []),
            "uploaded_at": str(item.get("uploaded_at") or "").strip() or None,
        }

    def _sync_runtime_library(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = {
            "items": [deepcopy(item) for item in payload.get("items") or [] if isinstance(item, dict)]
        }
        self._runtime_store.system_settings[BRAIN_SKILL_LIBRARY_SETTING_KEY] = deepcopy(normalized)
        return normalized

    def _persist_library(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        payload = self._sync_runtime_library({"items": items})
        updated_at = _now_iso()
        persist = getattr(self._persistence, "persist_system_setting", None)
        if callable(persist):
            persist(
                key=BRAIN_SKILL_LIBRARY_SETTING_KEY,
                payload=payload,
                updated_at=updated_at,
            )
        return payload

    def _read_library_setting(self) -> tuple[dict[str, Any] | None, bool]:
        read_setting = getattr(self._persistence, "read_system_setting", None)
        if callable(read_setting):
            persisted, database_authoritative = read_setting(BRAIN_SKILL_LIBRARY_SETTING_KEY)
            if persisted is not None:
                return persisted.get("payload") if isinstance(persisted, dict) else None, True
            if database_authoritative:
                return None, True
        cached = self._runtime_store.system_settings.get(BRAIN_SKILL_LIBRARY_SETTING_KEY)
        return cached if isinstance(cached, dict) else None, False

    def _library_items(self) -> list[dict[str, Any]]:
        payload, _ = self._read_library_setting()
        raw_items = payload.get("items") if isinstance(payload, dict) else []
        items: list[dict[str, Any]] = []
        for raw_item in raw_items or []:
            normalized = self._normalize_library_item(raw_item)
            if normalized is not None:
                items.append(normalized)
        self._sync_runtime_library({"items": items})
        return items

    def _normalize_library_item(self, raw_item: object) -> dict[str, Any] | None:
        if not isinstance(raw_item, dict):
            return None
        skill_id = _normalize_text(raw_item.get("id"))
        file_name = _normalize_text(raw_item.get("file_name") or raw_item.get("fileName"))
        name = _normalize_text(raw_item.get("name"))
        if not skill_id or not file_name or not name:
            return None
        format_name = _normalize_text(raw_item.get("format")) or _detect_format(file_name)
        description = _normalize_text(raw_item.get("description"))
        enabled = _normalize_bool(raw_item.get("enabled"), default=True)
        tags = _normalize_string_list(raw_item.get("tags"))
        capabilities = _normalize_string_list(raw_item.get("capabilities"))
        uploaded_at = _normalize_text(raw_item.get("uploaded_at") or raw_item.get("uploadedAt")) or _now_iso()
        updated_at = _normalize_text(raw_item.get("updated_at") or raw_item.get("updatedAt")) or uploaded_at
        manifest = deepcopy(raw_item.get("manifest") or {})
        ability = raw_item.get("ability")
        if isinstance(ability, dict):
            normalized_ability = deepcopy(ability)
        else:
            normalized_ability = self._build_runtime_ability(
                skill_id=skill_id,
                display_name=name,
                description=description,
                enabled=enabled,
                tags=tags,
                capabilities=capabilities,
                file_name=file_name,
                format_name=format_name,
                uploaded_at=uploaded_at,
                manifest=manifest,
            )
        return {
            "id": skill_id,
            "name": name,
            "file_name": file_name,
            "format": format_name,
            "description": description,
            "enabled": enabled,
            "tags": tags,
            "capabilities": capabilities,
            "uploaded_at": uploaded_at,
            "updated_at": updated_at,
            "content": str(raw_item.get("content") or ""),
            "manifest": manifest,
            "ability": normalized_ability,
        }

    def _sync_registry(self, items: list[dict[str, Any]]) -> None:
        registered = self._registry.list_abilities(source=BRAIN_SKILL_LIBRARY_SOURCE, enabled=None)
        for ability in registered:
            self._registry.remove_ability(str(ability.get("id") or ability.get("name") or ""))
        for item in items:
            ability = item.get("ability")
            if not isinstance(ability, dict):
                continue
            self._registry.register_ability(deepcopy(ability), overwrite=True)


brain_skill_service = BrainSkillService()
