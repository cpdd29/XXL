from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def now_isoformat() -> str:
    return datetime.now(UTC).isoformat()


def mapping_get(payload: Mapping[str, Any] | None, *path: str) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def first_string(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                return normalized
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            normalized = str(value).strip()
            if normalized:
                return normalized
    return None


def parse_text_content(value: Any) -> str | None:
    if isinstance(value, Mapping):
        return first_string(
            value.get("content"),
            value.get("text"),
            mapping_get(value, "text", "content"),
            mapping_get(value, "content", "text"),
        )

    if not isinstance(value, str):
        return first_string(value)

    normalized = value.strip()
    if not normalized:
        return None

    if normalized[:1] not in {"{", "["}:
        return normalized

    try:
        parsed = json.loads(normalized)
    except json.JSONDecodeError:
        return normalized

    if isinstance(parsed, Mapping):
        return first_string(
            parsed.get("text"),
            mapping_get(parsed, "text", "content"),
            mapping_get(parsed, "content", "text"),
            parsed.get("content"),
        ) or normalized
    return normalized


def require_string(*, value: Any, field_name: str, channel_name: str) -> str:
    normalized = first_string(value)
    if normalized:
        return normalized
    raise ValueError(f"{channel_name} payload missing {field_name}")


def fallback_message_id(channel: str, external_id: str | None = None) -> str:
    normalized_external_id = first_string(external_id)
    if normalized_external_id:
        return f"{channel}:{normalized_external_id}"
    return f"{channel}:{uuid4().hex[:16]}"
