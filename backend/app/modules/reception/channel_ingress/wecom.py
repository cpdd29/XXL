from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from app.modules.reception.channel_ingress.json_text import JSONTextChannelAdapter
from app.modules.reception.schemas.messages import ChannelType
from app.platform.config.settings_service import get_channel_integration_runtime_settings


class WeComAdapter(JSONTextChannelAdapter):
    channel = ChannelType.WECOM
    display_name = "WeCom"
    message_id_paths = ("msgid", "message_id", "msg_id", "event_id")
    user_id_paths = (
        "from.userid",
        "from.user_id",
        "sender.userid",
        "sender.user_id",
        "sender.id",
        "fromUserId",
        "platform_user_id",
    )
    chat_id_paths = (
        "chatid",
        "chat_id",
        "conversation.id",
        "conversation_id",
        "external_userid",
    )
    text_paths = (
        "text.content",
        "message.text",
        "message.content",
        "content",
        "text",
    )
    metadata_fields = {
        "msgtype": ("msgtype",),
        "conversation_type": ("conversation.type",),
    }

    def send_message(self, *, chat_id: str, text: str) -> dict[str, Any]:
        target_url = self._resolve_outbound_url(chat_id)
        payload = self._request(
            target_url,
            {
                "msgtype": "text",
                "text": {"content": text},
            },
        )
        errcode = payload.get("errcode")
        if errcode not in {None, 0, "0"}:
            raise RuntimeError(
                str(payload.get("errmsg") or payload.get("message") or "WeCom API returned an error")
            )

        return {
            "ok": True,
            "chat_id": str(payload.get("chat_id") or chat_id),
            "message_id": str(payload.get("msgid") or payload.get("message_id") or ""),
        }

    def _resolve_outbound_url(self, target: str) -> str:
        normalized_target = str(target or "").strip()
        runtime_settings = get_channel_integration_runtime_settings()["wecom"]
        if not runtime_settings.get("enabled", True):
            raise RuntimeError("WeCom channel integration is disabled")
        if normalized_target.startswith(("http://", "https://")):
            return normalized_target

        key = normalized_target or str(runtime_settings.get("bot_webhook_key") or "").strip()
        if not key:
            raise RuntimeError("WeCom outbound target is missing")

        base_url = str(runtime_settings.get("bot_webhook_base_url") or "").rstrip("/")
        if not base_url:
            raise RuntimeError("WeCom bot webhook base URL is not configured")
        return f"{base_url}?key={quote(key, safe='')}"

    def _request(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        runtime_settings = get_channel_integration_runtime_settings()["wecom"]
        try:
            with httpx.Client(
                timeout=float(runtime_settings.get("http_timeout_seconds") or 10.0),
                trust_env=False,
            ) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"WeCom API request failed: {exc}") from exc

        if not isinstance(data, dict):
            raise RuntimeError("WeCom API returned an invalid response")
        return data
