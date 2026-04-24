from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from app.modules.reception.channel_ingress.json_text import JSONTextChannelAdapter
from app.config import get_settings
from app.modules.reception.schemas.messages import ChannelType
from app.platform.config.settings_service import get_channel_integration_runtime_settings


class FeishuAdapter(JSONTextChannelAdapter):
    channel = ChannelType.FEISHU
    display_name = "Feishu"
    message_id_paths = (
        "event.message.message_id",
        "message.message_id",
        "message_id",
        "event_id",
    )
    user_id_paths = (
        "event.sender.sender_id.open_id",
        "event.sender.sender_id.user_id",
        "sender.sender_id.open_id",
        "sender.sender_id.user_id",
        "sender.open_id",
        "sender.user_id",
        "platform_user_id",
    )
    chat_id_paths = (
        "event.message.chat_id",
        "message.chat_id",
        "open_chat_id",
        "chat_id",
        "conversation_id",
    )
    text_paths = (
        "event.message.content",
        "message.content",
        "content",
        "text.content",
        "text",
    )
    metadata_fields = {
        "event_type": ("header.event_type",),
        "sender_type": ("event.sender.sender_type", "sender.sender_type"),
    }

    def send_message(self, *, chat_id: str, text: str) -> dict[str, Any]:
        target_url = self._resolve_outbound_url(chat_id)
        payload = self._request(
            target_url,
            {
                "msg_type": "text",
                "content": {"text": text},
            },
        )
        code = payload.get("code", payload.get("StatusCode"))
        if code not in {None, 0, "0"}:
            raise RuntimeError(
                str(
                    payload.get("msg")
                    or payload.get("message")
                    or payload.get("StatusMessage")
                    or "Feishu API returned an error"
                )
            )

        return {
            "ok": True,
            "chat_id": str(payload.get("chat_id") or chat_id),
            "message_id": str(payload.get("message_id") or payload.get("msg") or ""),
        }

    def _resolve_outbound_url(self, target: str) -> str:
        normalized_target = str(target or "").strip()
        runtime_settings = get_channel_integration_runtime_settings()["feishu"]
        if not runtime_settings.get("enabled", True):
            raise RuntimeError("Feishu channel integration is disabled")
        if normalized_target.startswith(("http://", "https://")):
            return normalized_target

        key = normalized_target or str(runtime_settings.get("bot_webhook_key") or "").strip()
        if not key:
            raise RuntimeError("Feishu outbound target is missing")

        base_url = str(runtime_settings.get("bot_webhook_base_url") or "").rstrip("/")
        if not base_url:
            raise RuntimeError("Feishu bot webhook base URL is not configured")
        return f"{base_url}/{quote(key, safe='')}"

    def _request(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        runtime_settings = get_channel_integration_runtime_settings()["feishu"]
        try:
            with httpx.Client(
                timeout=float(runtime_settings.get("http_timeout_seconds") or 10.0),
                trust_env=False,
            ) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Feishu API request failed: {exc}") from exc

        if not isinstance(data, dict):
            raise RuntimeError("Feishu API returned an invalid response")
        return data
