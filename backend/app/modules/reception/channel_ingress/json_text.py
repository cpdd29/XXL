from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.modules.reception.channel_ingress.base import ChannelAdapter
from app.modules.reception.schemas.messages import ChannelType, UnifiedMessage


def _extract_value(payload: dict[str, Any], *paths: str) -> Any:
    for path in paths:
        current: Any = payload
        matched = True
        for part in path.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                matched = False
                break
        if matched and current not in (None, ""):
            return current
    return None


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, dict):
        return _normalize_text(value.get("text") or value.get("content"))

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.startswith("{") and text.endswith("}"):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return text
            return _normalize_text(parsed)
        return text

    text = str(value).strip()
    return text or None


class JSONTextChannelAdapter(ChannelAdapter):
    channel: ChannelType
    display_name: str
    message_id_paths: tuple[str, ...] = ()
    user_id_paths: tuple[str, ...] = ()
    chat_id_paths: tuple[str, ...] = ()
    text_paths: tuple[str, ...] = ()
    metadata_fields: dict[str, tuple[str, ...]] = {}

    def receive_message(self, payload: dict[str, Any]) -> UnifiedMessage:
        platform_user_id = _normalize_text(_extract_value(payload, *self.user_id_paths))
        if not platform_user_id:
            raise ValueError(f"{self.display_name} payload missing platform user id")

        text = _normalize_text(_extract_value(payload, *self.text_paths))
        if not text:
            raise ValueError(f"{self.display_name} message text is required")

        chat_id = _normalize_text(_extract_value(payload, *self.chat_id_paths)) or platform_user_id
        message_id = (
            _normalize_text(_extract_value(payload, *self.message_id_paths))
            or f"{self.channel.value}:{uuid4().hex[:12]}"
        )

        metadata = {
            key: value
            for key, paths in self.metadata_fields.items()
            if (value := _extract_value(payload, *paths)) is not None
        }

        return UnifiedMessage(
            message_id=message_id,
            channel=self.channel,
            platform_user_id=platform_user_id,
            chat_id=chat_id,
            text=text,
            received_at=datetime.now(UTC).isoformat(),
            raw_payload=payload,
            metadata=metadata,
        )

    def send_message(self, *, chat_id: str, text: str) -> dict[str, Any]:
        raise NotImplementedError(f"{self.display_name} outbound delivery is not implemented yet")

    def get_user_info(self, platform_user_id: str) -> dict[str, Any]:
        return {"id": platform_user_id}
