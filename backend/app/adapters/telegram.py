from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import ValidationError

from app.adapters.base import ChannelAdapter
from app.schemas.messages import ChannelType, TelegramWebhookUpdate, UnifiedMessage
from app.services.settings_service import get_channel_integration_runtime_settings


class TelegramAdapter(ChannelAdapter):
    def receive_message(self, payload: dict[str, Any]) -> UnifiedMessage:
        try:
            update = TelegramWebhookUpdate.model_validate(payload)
        except ValidationError as exc:
            raise ValueError("Invalid Telegram payload structure") from exc

        if update.message is None:
            raise ValueError("Telegram payload does not contain message")
        if not update.message.text or not update.message.text.strip():
            raise ValueError("Telegram message text is required")

        received_at = datetime.now(UTC).isoformat()
        user = update.message.from_
        chat = update.message.chat

        return UnifiedMessage(
            message_id=f"telegram:{update.update_id}:{update.message.message_id}",
            channel=ChannelType.TELEGRAM,
            platform_user_id=str(user.id),
            chat_id=str(chat.id),
            text=update.message.text.strip(),
            received_at=received_at,
            raw_payload=payload,
            metadata={
                "update_id": update.update_id,
                "chat_type": chat.type,
                "username": user.username,
                "language_code": user.language_code,
                "is_bot": user.is_bot,
            },
        )

    def send_message(self, *, chat_id: str, text: str) -> dict[str, Any]:
        payload = self._request("sendMessage", {"chat_id": chat_id, "text": text})
        result = payload.get("result") or {}
        return {
            "ok": True,
            "chat_id": str(result.get("chat", {}).get("id") or chat_id),
            "message_id": str(result.get("message_id") or ""),
        }

    def get_user_info(self, platform_user_id: str) -> dict[str, Any]:
        payload = self._request("getChat", {"chat_id": platform_user_id})
        result = payload.get("result") or {}
        return {
            "id": str(result.get("id") or platform_user_id),
            "type": str(result.get("type") or ""),
            "title": result.get("title"),
            "username": result.get("username"),
            "first_name": result.get("first_name"),
            "last_name": result.get("last_name"),
        }

    def _request(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        runtime_settings = get_channel_integration_runtime_settings()["telegram"]
        if not runtime_settings.get("enabled", True):
            raise RuntimeError("Telegram channel integration is disabled")
        bot_token = str(runtime_settings.get("bot_token") or "").strip()
        if not bot_token:
            raise RuntimeError("Telegram bot token is not configured")

        base_url = str(runtime_settings.get("api_base_url") or "").rstrip("/")
        if not base_url:
            raise RuntimeError("Telegram API base URL is not configured")
        url = f"{base_url}/bot{bot_token}/{method}"

        try:
            with httpx.Client(
                timeout=float(runtime_settings.get("http_timeout_seconds") or 10.0),
                trust_env=False,
            ) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Telegram API request failed: {exc}") from exc

        if not isinstance(data, dict) or not data.get("ok"):
            description = data.get("description") if isinstance(data, dict) else None
            raise RuntimeError(description or f"Telegram API returned an invalid response for {method}")

        return data
