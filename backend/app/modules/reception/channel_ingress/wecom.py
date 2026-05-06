from __future__ import annotations

import base64
import json
import logging
import os
import struct
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import httpx

from app.modules.reception.channel_binding.service import (
    ILINK_APP_CLIENT_VERSION,
    ILINK_APP_ID,
    wecom_channel_binding_service,
)
from app.modules.reception.channel_ingress.json_text import JSONTextChannelAdapter, normalize_attachment
from app.modules.reception.schemas.messages import ChannelType
from app.platform.config.settings_service import get_channel_integration_runtime_settings

logger = logging.getLogger(__name__)
WECOM_ILINK_DELIVERY_PREFIX = "wecom-ilink:"
WECOM_ILINK_CHANNEL_VERSION = "0.2.1"
WECOM_ILINK_TEXT_LIMIT = 4000


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def encode_wecom_delivery_target(payload: dict[str, Any]) -> str:
    normalized = {
        key: value
        for key, value in payload.items()
        if value not in (None, "", [])
    }
    raw = json.dumps(normalized, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    token = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"{WECOM_ILINK_DELIVERY_PREFIX}{token}"


def decode_wecom_delivery_target(target: str) -> dict[str, Any] | None:
    normalized_target = _normalize_text(target)
    if not normalized_target.startswith(WECOM_ILINK_DELIVERY_PREFIX):
        return None
    encoded = normalized_target[len(WECOM_ILINK_DELIVERY_PREFIX) :]
    if not encoded:
        return None
    padding = "=" * (-len(encoded) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(encoded + padding).decode("utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _ilink_headers(token: str) -> dict[str, str]:
    random_uin = struct.unpack(">I", os.urandom(4))[0]
    return {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Authorization": f"Bearer {token}",
        "X-WECHAT-UIN": base64.b64encode(str(random_uin).encode("utf-8")).decode("ascii"),
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": str(ILINK_APP_CLIENT_VERSION),
    }


def _ilink_base_info() -> dict[str, str]:
    return {"channel_version": WECOM_ILINK_CHANNEL_VERSION}


def _chunk_text(text: str, limit: int = WECOM_ILINK_TEXT_LIMIT) -> list[str]:
    normalized = _normalize_text(text)
    if len(normalized) <= limit:
        return [normalized]
    chunks: list[str] = []
    remaining = normalized
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        window = remaining[:limit]
        cut = max(window.rfind("\n\n"), window.rfind("\n"), window.rfind(" "))
        if cut < limit // 3:
            cut = limit
        else:
            cut += 1
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    return chunks


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

    def extract_attachments(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        msgtype = str(payload.get("msgtype") or "").strip().lower()
        if msgtype not in {"image", "voice", "video", "file"}:
            return []

        raw_payload = payload.get(msgtype)
        attachment = normalize_attachment(
            raw_payload,
            fallback_kind=msgtype,
            fallback_name=f"WeCom {msgtype}",
        )
        return [attachment] if attachment is not None else [{"kind": msgtype, "name": f"WeCom {msgtype}"}]

    def send_message(self, *, chat_id: str, text: str) -> dict[str, Any]:
        ilink_target = decode_wecom_delivery_target(chat_id)
        if ilink_target is not None:
            return self._send_ilink_message(target=ilink_target, text=text)
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

    def _send_ilink_message(self, *, target: dict[str, Any], text: str) -> dict[str, Any]:
        tenant_id = _normalize_text(target.get("tenant_id") or target.get("tenantId"))
        user_id = _normalize_text(target.get("user_id") or target.get("userId"))
        context_token = _normalize_text(target.get("context_token") or target.get("contextToken"))
        if not tenant_id or not user_id or not context_token:
            raise RuntimeError("WeCom iLink outbound target is incomplete")

        credential = wecom_channel_binding_service.get_credential(tenant_id)
        if credential is None:
            raise RuntimeError(f"WeCom iLink credential not found for tenant {tenant_id}")

        base_url = _normalize_text(credential.base_url).rstrip("/")
        access_token = _normalize_text(credential.access_token)
        if not base_url or not access_token:
            raise RuntimeError(f"WeCom iLink credential is incomplete for tenant {tenant_id}")

        last_message_id = ""
        with httpx.Client(
            timeout=float(get_channel_integration_runtime_settings()["wecom"].get("http_timeout_seconds") or 10.0),
            trust_env=False,
        ) as client:
            chunks = _chunk_text(text)
            for chunk in chunks:
                message_id = uuid4().hex
                body = {
                    "msg": {
                        "from_user_id": "",
                        "to_user_id": user_id,
                        "client_id": message_id,
                        "message_type": 2,
                        "message_state": 2,
                        "context_token": context_token,
                        "item_list": [
                            {
                                "type": 1,
                                "text_item": {
                                    "text": chunk,
                                },
                            }
                        ],
                    },
                    "base_info": _ilink_base_info(),
                }
                logger.info(
                    "WeCom iLink outbound send: tenant_id=%s user_id=%s chunk_chars=%s",
                    tenant_id,
                    user_id,
                    len(chunk),
                )
                response = client.post(
                    f"{base_url}/ilink/bot/sendmessage",
                    headers=_ilink_headers(access_token),
                    json=body,
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise RuntimeError("WeCom iLink API returned an invalid response")
                ret = payload.get("ret")
                errcode = payload.get("errcode")
                if ret not in {None, 0} or errcode not in {None, 0}:
                    raise RuntimeError(
                        _normalize_text(payload.get("errmsg"))
                        or f"WeCom iLink API returned an error (ret={ret}, errcode={errcode})"
                    )
                last_message_id = message_id
            logger.info(
                "WeCom iLink outbound sent: tenant_id=%s user_id=%s chunks=%s",
                tenant_id,
                user_id,
                len(chunks),
            )

        return {
            "ok": True,
            "chat_id": user_id,
            "message_id": last_message_id,
        }

    def _resolve_outbound_url(self, target: str) -> str:
        normalized_target = str(target or "").strip()
        runtime_settings = get_channel_integration_runtime_settings()["wecom"]
        if not runtime_settings.get("enabled", False):
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
