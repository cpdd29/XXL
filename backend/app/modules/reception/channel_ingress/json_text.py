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


def _parse_json_object(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized.startswith("{") or not normalized.endswith("}"):
        return None
    try:
        parsed = json.loads(normalized)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _attachment_kind_label(kind: str) -> str:
    return {
        "image": "图片",
        "file": "文件",
        "audio": "音频",
        "voice": "语音",
        "video": "视频",
    }.get(str(kind or "").strip().lower(), "附件")


def _attachment_summary_text(attachments: list[dict[str, Any]], *, limit: int = 3) -> str:
    summaries: list[str] = []
    for item in attachments[:limit]:
        if not isinstance(item, dict):
            continue
        kind = _attachment_kind_label(str(item.get("kind") or ""))
        name = _normalize_text(item.get("name") or item.get("title") or item.get("file_name"))
        if name:
            summaries.append(f"{kind}“{name}”")
        else:
            summaries.append(kind)
    if not summaries:
        return ""
    suffix = " 等附件" if len(attachments) > limit else ""
    return "、".join(summaries) + suffix


def build_attachment_placeholder(attachments: list[dict[str, Any]]) -> str | None:
    summary = _attachment_summary_text(attachments)
    if not summary:
        return None
    return f"客户发送了{summary}，请结合附件类型继续接待。"


def normalize_attachment(
    raw_item: Any,
    *,
    fallback_kind: str | None = None,
    fallback_name: str | None = None,
) -> dict[str, Any] | None:
    payload = _parse_json_object(raw_item) if not isinstance(raw_item, dict) else raw_item
    if payload is None:
        return None

    kind = (
        _normalize_text(payload.get("kind"))
        or _normalize_text(payload.get("type"))
        or fallback_kind
        or "file"
    )
    name = (
        _normalize_text(payload.get("name"))
        or _normalize_text(payload.get("title"))
        or _normalize_text(payload.get("file_name"))
        or _normalize_text(payload.get("fileName"))
        or _normalize_text(payload.get("filename"))
        or fallback_name
    )
    attachment = {
        "kind": kind,
        "name": name or _attachment_kind_label(kind),
        "url": _normalize_text(
            payload.get("url")
            or payload.get("download_url")
            or payload.get("downloadUrl")
            or payload.get("pic_url")
            or payload.get("picUrl")
        ),
        "mime_type": _normalize_text(payload.get("mime_type") or payload.get("mimeType")),
        "file_key": _normalize_text(payload.get("file_key") or payload.get("fileKey")),
        "image_key": _normalize_text(payload.get("image_key") or payload.get("imageKey")),
        "audio_key": _normalize_text(payload.get("audio_key") or payload.get("audioKey")),
        "video_key": _normalize_text(payload.get("video_key") or payload.get("videoKey")),
        "media_id": _normalize_text(payload.get("media_id") or payload.get("mediaId")),
        "duration_ms": payload.get("duration")
        if isinstance(payload.get("duration"), int)
        else payload.get("duration_ms")
        if isinstance(payload.get("duration_ms"), int)
        else payload.get("durationMs"),
        "summary": _normalize_text(payload.get("summary")),
        "excerpt": _normalize_text(payload.get("excerpt")),
        "content": _normalize_text(payload.get("content") or payload.get("text_content") or payload.get("textContent")),
        "transcript": _normalize_text(payload.get("transcript")),
        "ocr_text": _normalize_text(payload.get("ocr_text") or payload.get("ocrText")),
        "description": _normalize_text(payload.get("description")),
    }
    return {key: value for key, value in attachment.items() if value not in (None, "", [])}


class JSONTextChannelAdapter(ChannelAdapter):
    channel: ChannelType
    display_name: str
    message_id_paths: tuple[str, ...] = ()
    user_id_paths: tuple[str, ...] = ()
    chat_id_paths: tuple[str, ...] = ()
    text_paths: tuple[str, ...] = ()
    metadata_fields: dict[str, tuple[str, ...]] = {}

    def extract_attachments(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        msgtype = _normalize_text(_extract_value(payload, "msgtype", "message_type", "message.message_type")) or ""
        normalized_type = msgtype.lower()
        if normalized_type not in {"image", "file", "audio", "voice", "video"}:
            return []

        raw_payload = _extract_value(
            payload,
            normalized_type,
            f"message.{normalized_type}",
            f"event.message.{normalized_type}",
            "attachment",
            "attachments",
        )
        candidates = raw_payload if isinstance(raw_payload, list) else [raw_payload]
        items = [
            normalized
            for candidate in candidates
            if (normalized := normalize_attachment(candidate, fallback_kind=normalized_type)) is not None
        ]
        if items:
            return items
        return [
            {
                "kind": normalized_type,
                "name": _attachment_kind_label(normalized_type),
            }
        ]

    def receive_message(self, payload: dict[str, Any]) -> UnifiedMessage:
        platform_user_id = _normalize_text(_extract_value(payload, *self.user_id_paths))
        if not platform_user_id:
            raise ValueError(f"{self.display_name} payload missing platform user id")

        attachments = self.extract_attachments(payload)
        text = _normalize_text(_extract_value(payload, *self.text_paths))
        if not text and attachments:
            text = build_attachment_placeholder(attachments)
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
        if attachments:
            metadata["attachments"] = attachments
            metadata["attachment_count"] = len(attachments)

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
