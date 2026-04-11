from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _normalize_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


@dataclass(slots=True)
class ReceptionPayload:
    text: str
    language: str
    channel: str
    user_id: str | None
    session_id: str | None
    metadata: dict[str, Any]


class ReceptionService:
    """Normalize inbound message payloads for routing/orchestration."""

    def normalize(self, payload: dict[str, Any] | None) -> ReceptionPayload:
        raw = payload or {}
        text = _normalize_text(raw.get("text") or raw.get("content") or raw.get("message"))
        language = _normalize_text(raw.get("language") or "zh").lower() or "zh"
        channel = _normalize_text(raw.get("channel") or raw.get("source") or "unknown") or "unknown"
        user_id = _normalize_text(raw.get("user_id") or raw.get("userId")) or None
        session_id = _normalize_text(raw.get("session_id") or raw.get("sessionId")) or None
        metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
        return ReceptionPayload(
            text=text,
            language=language,
            channel=channel,
            user_id=user_id,
            session_id=session_id,
            metadata=dict(metadata),
        )

