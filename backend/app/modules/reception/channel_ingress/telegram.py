from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import ValidationError

from app.modules.reception.channel_ingress.base import ChannelAdapter
from app.modules.reception.channel_ingress.json_text import build_attachment_placeholder
from app.modules.reception.schemas.messages import ChannelType, TelegramWebhookUpdate, UnifiedMessage
from app.platform.config.settings_service import get_channel_integration_runtime_settings


class TelegramAdapter(ChannelAdapter):
    @staticmethod
    def _extract_attachments(message_payload: dict[str, Any]) -> list[dict[str, Any]]:
        attachments: list[dict[str, Any]] = []
        photos = message_payload.get("photo")
        if isinstance(photos, list) and photos:
            attachments.append({"kind": "image", "name": "Telegram 图片"})
        document = message_payload.get("document")
        if isinstance(document, dict):
            attachments.append(
                {
                    "kind": "file",
                    "name": str(document.get("file_name") or "Telegram 文件"),
                    "mime_type": str(document.get("mime_type") or "").strip() or None,
                }
            )
        voice = message_payload.get("voice")
        if isinstance(voice, dict):
            attachments.append({"kind": "voice", "name": "Telegram 语音"})
        audio = message_payload.get("audio")
        if isinstance(audio, dict):
            attachments.append(
                {
                    "kind": "audio",
                    "name": str(audio.get("file_name") or "Telegram 音频"),
                    "mime_type": str(audio.get("mime_type") or "").strip() or None,
                }
            )
        video = message_payload.get("video")
        if isinstance(video, dict):
            attachments.append(
                {
                    "kind": "video",
                    "name": str(video.get("file_name") or "Telegram 视频"),
                    "mime_type": str(video.get("mime_type") or "").strip() or None,
                }
            )
        return [
            {key: value for key, value in item.items() if value not in (None, "")}
            for item in attachments
        ]

    def receive_message(self, payload: dict[str, Any]) -> UnifiedMessage:
        try:
            update = TelegramWebhookUpdate.model_validate(payload)
        except ValidationError as exc:
            raise ValueError("Invalid Telegram payload structure") from exc

        if update.message is None:
            raise ValueError("Telegram payload does not contain message")
        raw_message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
        attachments = self._extract_attachments(raw_message)
        text = (update.message.text or update.message.caption or "").strip()
        if not text and attachments:
            text = str(build_attachment_placeholder(attachments) or "").strip()
        if not text:
            raise ValueError("Telegram message text is required")

        received_at = datetime.now(UTC).isoformat()
        user = update.message.from_
        chat = update.message.chat

        metadata = {
            "update_id": update.update_id,
            "chat_type": chat.type,
            "username": user.username,
            "language_code": user.language_code,
            "is_bot": user.is_bot,
        }
        if attachments:
            metadata["attachments"] = attachments
            metadata["attachment_count"] = len(attachments)

        return UnifiedMessage(
            message_id=f"telegram:{update.update_id}:{update.message.message_id}",
            channel=ChannelType.TELEGRAM,
            platform_user_id=str(user.id),
            chat_id=str(chat.id),
            text=text,
            received_at=received_at,
            raw_payload=payload,
            metadata=metadata,
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
        if not runtime_settings.get("enabled", False):
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
