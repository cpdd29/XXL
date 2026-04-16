from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta


def trim_time_window(window: deque[datetime], *, now: datetime, window_seconds: int) -> deque[datetime]:
    threshold = now - timedelta(seconds=max(int(window_seconds), 1))
    while window and window[0] < threshold:
        window.popleft()
    return window


def resolve_window_count(
    *,
    persisted_count: int | None,
    database_authoritative: bool,
    runtime_count: int,
) -> int:
    if database_authoritative:
        return int(persisted_count or 0)
    if persisted_count is None:
        return runtime_count
    return max(runtime_count, persisted_count)


def is_limit_exceeded(*, current_count: int, limit: int) -> bool:
    return int(current_count) >= int(limit)


def build_penalty_payload(
    *,
    now: datetime,
    level: str,
    detail: str,
    duration_seconds: int,
    status_code: int,
) -> dict[str, object]:
    return {
        "level": level,
        "detail": detail,
        "status_code": status_code,
        "until": (now + timedelta(seconds=max(int(duration_seconds), 1))).isoformat(),
    }


def is_penalty_active(payload: dict[str, object] | None, *, now: datetime) -> bool:
    if not isinstance(payload, dict):
        return False
    until = str(payload.get("until") or "").strip()
    if not until:
        return False
    try:
        return datetime.fromisoformat(until) > now
    except ValueError:
        return False


def choose_rate_limit_penalty_level(*, incident_count: int, ban_threshold: int) -> str:
    return "ban" if int(incident_count) >= int(ban_threshold) else "cooldown"


def choose_rate_limit_penalty_detail(*, incident_count: int, ban_threshold: int) -> str:
    if int(incident_count) >= int(ban_threshold):
        return "User temporarily blocked by security policy"
    return "User is cooling down after rate limit violations"


def choose_rate_limit_penalty_duration(
    *,
    incident_count: int,
    ban_threshold: int,
    cooldown_seconds: int,
    ban_seconds: int,
) -> int:
    if int(incident_count) >= int(ban_threshold):
        return int(ban_seconds)
    return int(cooldown_seconds)
