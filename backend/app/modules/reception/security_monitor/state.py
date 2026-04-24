from __future__ import annotations

import json
from datetime import UTC, datetime


def default_subject_state(user_key: str, *, now: datetime | None = None) -> dict[str, object]:
    timestamp = now or datetime.now(UTC)
    return {
        "user_key": user_key,
        "rate_request_timestamps": [],
        "incident_timestamps": [],
        "active_penalty": None,
        "updated_at": timestamp.isoformat(),
    }


def parse_timestamp(value: object) -> datetime | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def normalized_persisted_timestamps(
    values: object,
    *,
    threshold: datetime | None = None,
) -> list[datetime]:
    if not isinstance(values, list):
        return []
    timestamps: list[datetime] = []
    for item in values:
        parsed = parse_timestamp(item)
        if parsed is None:
            continue
        if threshold is not None and parsed < threshold:
            continue
        timestamps.append(parsed)
    timestamps.sort()
    return timestamps


def serialize_penalty(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def deserialize_penalty(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        payload = dict(value)
    else:
        try:
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            payload = json.loads(str(value))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
    try:
        until = str(payload.get("until") or "").strip()
        if not until:
            return None
        datetime.fromisoformat(until)
    except (AttributeError, TypeError, ValueError):
        return None
    return payload
