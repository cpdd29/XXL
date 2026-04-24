from __future__ import annotations

import json
from time import time
from typing import Any
from urllib.parse import quote

import httpx

from app.modules.reception.channel_ingress.json_text import JSONTextChannelAdapter
from app.modules.reception.schemas.messages import ChannelType
from app.platform.config.settings_service import get_channel_integration_runtime_settings


DINGTALK_TARGET_SPEC_PREFIX = "__workbot_dingtalk_target__:"


def encode_dingtalk_delivery_target(spec: dict[str, Any]) -> str:
    return f"{DINGTALK_TARGET_SPEC_PREFIX}{json.dumps(spec, ensure_ascii=True, separators=(',', ':'))}"


def decode_dingtalk_delivery_target(target: str) -> dict[str, Any] | None:
    normalized = str(target or "").strip()
    if not normalized.startswith(DINGTALK_TARGET_SPEC_PREFIX):
        return None
    payload = normalized[len(DINGTALK_TARGET_SPEC_PREFIX) :]
    if not payload:
        return None
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


class DingTalkAdapter(JSONTextChannelAdapter):
    channel = ChannelType.DINGTALK
    display_name = "DingTalk"
    message_id_paths = ("msgId", "message_id", "msg_id", "event_id")
    user_id_paths = (
        "senderStaffId",
        "sender.staff_id",
        "sender.sender_id",
        "staff_id",
        "from_user_id",
        "platform_user_id",
    )
    chat_id_paths = (
        "conversationId",
        "conversation.id",
        "chatbotConversationId",
        "chat_id",
        "sessionWebhook",
    )
    text_paths = (
        "text.content",
        "message.text",
        "message.content",
        "content",
        "text",
    )
    metadata_fields = {
        "conversation_type": ("conversationType", "conversation.type"),
        "msgtype": ("msgtype",),
        "robot_code": ("robotCode", "robot_code"),
        "session_webhook": ("sessionWebhook", "session_webhook"),
        "corp_id": (
            "corpId",
            "corp_id",
            "chatbotCorpId",
            "senderCorpId",
            "conversation.corp_id",
        ),
    }

    def __init__(self) -> None:
        self._cached_access_token: str | None = None
        self._cached_access_token_expires_at: float = 0.0

    def send_message(self, *, chat_id: str, text: str) -> dict[str, Any]:
        target_spec = decode_dingtalk_delivery_target(chat_id)
        if target_spec is not None:
            return self._send_via_delivery_target(target_spec, text=text)

        return self._send_via_webhook_target(chat_id, text=text)

    def _send_via_delivery_target(self, target_spec: dict[str, Any], *, text: str) -> dict[str, Any]:
        runtime_settings = get_channel_integration_runtime_settings()["dingtalk"]
        if not runtime_settings.get("enabled", True):
            raise RuntimeError("DingTalk channel integration is disabled")

        session_webhook = str(target_spec.get("session_webhook") or "").strip() or None
        if self._can_use_openapi(runtime_settings, target_spec):
            try:
                return self._send_via_openapi(runtime_settings, target_spec, text=text)
            except RuntimeError:
                if session_webhook:
                    return self._send_via_webhook_target(session_webhook, text=text)
                raise

        if session_webhook:
            return self._send_via_webhook_target(session_webhook, text=text)

        raise RuntimeError("DingTalk outbound target is missing a usable OpenAPI identity or sessionWebhook")

    def _send_via_webhook_target(self, target: str, *, text: str) -> dict[str, Any]:
        target_url = self._resolve_outbound_url(target)
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
                str(payload.get("errmsg") or payload.get("message") or "DingTalk API returned an error")
            )

        return {
            "ok": True,
            "chat_id": str(payload.get("sessionWebhook") or target),
            "message_id": str(payload.get("messageId") or payload.get("msgId") or ""),
        }

    def _can_use_openapi(self, runtime_settings: dict[str, Any], target_spec: dict[str, Any]) -> bool:
        agent_id = str(runtime_settings.get("agent_id") or "").strip()
        client_id = str(runtime_settings.get("client_id") or "").strip()
        client_secret = str(runtime_settings.get("client_secret") or "").strip()
        platform_user_id = str(target_spec.get("platform_user_id") or "").strip()
        if not all((agent_id, client_id, client_secret, platform_user_id)):
            return False

        configured_corp_id = str(runtime_settings.get("corp_id") or "").strip()
        target_corp_id = str(target_spec.get("corp_id") or "").strip()
        if configured_corp_id and target_corp_id and configured_corp_id != target_corp_id:
            return False
        return True

    def _send_via_openapi(
        self,
        runtime_settings: dict[str, Any],
        target_spec: dict[str, Any],
        *,
        text: str,
    ) -> dict[str, Any]:
        access_token = self._get_access_token(runtime_settings)
        base_url = str(runtime_settings.get("api_base_url") or "").rstrip("/")
        if not base_url:
            raise RuntimeError("DingTalk API base URL is not configured")

        agent_id = str(runtime_settings.get("agent_id") or "").strip()
        platform_user_id = str(target_spec.get("platform_user_id") or "").strip()
        if not agent_id or not platform_user_id:
            raise RuntimeError("DingTalk OpenAPI outbound target is missing agent_id or platform_user_id")

        response = self._request_json(
            "POST",
            f"{base_url}/topapi/message/corpconversation/asyncsend_v2",
            payload={
                "agent_id": int(agent_id) if agent_id.isdigit() else agent_id,
                "userid_list": platform_user_id,
                "msg": {
                    "msgtype": "text",
                    "text": {"content": text},
                },
                "to_all_user": False,
            },
            params={"access_token": access_token},
        )

        errcode = response.get("errcode")
        if errcode not in {None, 0, "0"}:
            raise RuntimeError(
                str(response.get("errmsg") or response.get("message") or "DingTalk OpenAPI returned an error")
            )

        return {
            "ok": True,
            "chat_id": platform_user_id,
            "message_id": str(response.get("task_id") or response.get("taskId") or ""),
        }

    def _get_access_token(self, runtime_settings: dict[str, Any]) -> str:
        if self._cached_access_token and self._cached_access_token_expires_at > time() + 30:
            return self._cached_access_token

        base_url = str(runtime_settings.get("api_base_url") or "").rstrip("/")
        client_id = str(runtime_settings.get("client_id") or "").strip()
        client_secret = str(runtime_settings.get("client_secret") or "").strip()
        if not base_url or not client_id or not client_secret:
            raise RuntimeError("DingTalk application credentials are not fully configured")

        payload = self._request_json(
            "GET",
            f"{base_url}/gettoken",
            params={"appkey": client_id, "appsecret": client_secret},
        )

        access_token = str(payload.get("access_token") or payload.get("accessToken") or "").strip()
        if not access_token:
            raise RuntimeError("DingTalk access token response did not include access_token")

        expires_in_raw = payload.get("expires_in", payload.get("expireIn"))
        try:
            expires_in = int(expires_in_raw or 7200)
        except (TypeError, ValueError):
            expires_in = 7200
        self._cached_access_token = access_token
        self._cached_access_token_expires_at = time() + max(expires_in - 60, 60)
        return access_token

    def _resolve_outbound_url(self, target: str) -> str:
        normalized_target = str(target or "").strip()
        runtime_settings = get_channel_integration_runtime_settings()["dingtalk"]
        if not runtime_settings.get("enabled", True):
            raise RuntimeError("DingTalk channel integration is disabled")
        if not normalized_target:
            raise RuntimeError("DingTalk outbound target is missing")
        if normalized_target.startswith(("http://", "https://")):
            return normalized_target

        session = normalized_target
        if "session=" in session:
            session = session.split("session=", maxsplit=1)[1].strip()
        if not session:
            raise RuntimeError("DingTalk session token is missing")

        base_url = str(runtime_settings.get("api_base_url") or "").rstrip("/")
        if not base_url:
            raise RuntimeError("DingTalk API base URL is not configured")
        return f"{base_url}/robot/sendBySession?session={quote(session, safe='')}"

    def _request(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        runtime_settings = get_channel_integration_runtime_settings()["dingtalk"]
        return self._request_json(
            "POST",
            url,
            payload=payload,
            timeout=float(runtime_settings.get("http_timeout_seconds") or 10.0),
        )

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        runtime_settings = get_channel_integration_runtime_settings()["dingtalk"]
        request_timeout = float(timeout or runtime_settings.get("http_timeout_seconds") or 10.0)
        try:
            with httpx.Client(timeout=request_timeout, trust_env=False) as client:
                response = client.request(method.upper(), url, json=payload, params=params)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"DingTalk API request failed: {exc}") from exc

        if not isinstance(data, dict):
            raise RuntimeError("DingTalk API returned an invalid response")
        return data
