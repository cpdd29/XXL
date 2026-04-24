from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class ExecutionRequest:
    tool_id: str
    payload: dict[str, Any]
    trace_context: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 15.0


@dataclass(slots=True)
class ExecutionAttempt:
    path: str
    ok: bool
    duration_ms: float
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    at: str = field(default_factory=_utc_now_iso)


@dataclass(slots=True)
class ExecutionResult:
    ok: bool
    path: str
    result: dict[str, Any] | None
    error: dict[str, Any] | None
    attempts: list[ExecutionAttempt]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "path": self.path,
            "result": self.result,
            "error": self.error,
            "attempts": [
                {
                    "path": item.path,
                    "ok": item.ok,
                    "duration_ms": item.duration_ms,
                    "error": item.error,
                    "metadata": dict(item.metadata),
                    "at": item.at,
                }
                for item in self.attempts
            ],
        }
