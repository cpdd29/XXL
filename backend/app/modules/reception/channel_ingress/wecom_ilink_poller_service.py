from __future__ import annotations

import base64
from datetime import UTC, datetime
import hashlib
import logging
import os
import struct
from threading import Event, Lock, Thread
from typing import Any

import httpx

import app.modules.reception.application.message_ingestion_service as message_ingestion_service
from app.modules.reception.channel_binding.schemas import WecomChannelCredential
from app.modules.reception.channel_binding.service import (
    ILINK_APP_CLIENT_VERSION,
    ILINK_APP_ID,
    wecom_channel_binding_service,
)
from app.modules.reception.channel_ingress.json_text import build_attachment_placeholder
from app.modules.reception.schemas.messages import ChannelType, UnifiedMessage
from app.platform.config.settings_service import get_channel_integration_runtime_settings
from app.platform.observability.operational_log_service import append_realtime_event


logger = logging.getLogger(__name__)
ILINK_BASE_INFO = {"channel_version": "0.2.1"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _parse_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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


def _received_at(raw_payload: dict[str, Any]) -> str:
    timestamp_ms = _parse_int(raw_payload.get("create_time_ms"))
    if timestamp_ms is None or timestamp_ms <= 0:
        return datetime.now(UTC).isoformat()
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).isoformat()


def _fallback_message_id(raw_payload: dict[str, Any], *, platform_user_id: str, text: str) -> str:
    signature = "|".join(
        [
            platform_user_id,
            _text(raw_payload.get("context_token")),
            _text(raw_payload.get("create_time_ms")),
            text,
        ]
    )
    return f"wecom-ilink:{hashlib.sha1(signature.encode('utf-8')).hexdigest()[:20]}"


def _text_from_item(item: dict[str, Any]) -> str | None:
    item_type = _parse_int(item.get("type"))
    if item_type == 1:
        return _text((item.get("text_item") or {}).get("text")) or None
    if item_type == 3:
        return _text((item.get("voice_item") or {}).get("text")) or None
    return None


def _attachments_from_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    attachments: list[dict[str, Any]] = []
    for item in items:
        item_type = _parse_int(item.get("type"))
        if item_type == 2:
            image_item = item.get("image_item") if isinstance(item.get("image_item"), dict) else {}
            attachment = {
                "kind": "image",
                "name": _text(image_item.get("file_name")) or "微信图片",
                "url": _text(image_item.get("url")) or None,
                "description": _text(image_item.get("url")) or None,
            }
            attachments.append({key: value for key, value in attachment.items() if value not in (None, "", [])})
        elif item_type == 3:
            voice_item = item.get("voice_item") if isinstance(item.get("voice_item"), dict) else {}
            attachment = {
                "kind": "voice",
                "name": "微信语音",
                "transcript": _text(voice_item.get("text")) or None,
                "duration_ms": _parse_int(voice_item.get("playtime")),
            }
            attachments.append({key: value for key, value in attachment.items() if value not in (None, "", [])})
        elif item_type == 4:
            file_item = item.get("file_item") if isinstance(item.get("file_item"), dict) else {}
            attachment = {
                "kind": "file",
                "name": _text(file_item.get("file_name")) or "微信文件",
            }
            attachments.append({key: value for key, value in attachment.items() if value not in (None, "", [])})
        elif item_type == 5:
            attachments.append({"kind": "video", "name": "微信视频"})
    return attachments


def _message_text(items: list[dict[str, Any]], attachments: list[dict[str, Any]]) -> str:
    parts = [part for item in items if isinstance(item, dict) if (part := _text_from_item(item))]
    normalized = "\n".join(parts).strip()
    if normalized:
        return normalized
    return build_attachment_placeholder(attachments) or "客户发送了一条微信消息，请继续接待。"


def _build_unified_message(raw_payload: dict[str, Any], credential: WecomChannelCredential) -> UnifiedMessage | None:
    platform_user_id = _text(raw_payload.get("from_user_id"))
    context_token = _text(raw_payload.get("context_token"))
    if not platform_user_id or not context_token:
        return None

    items = raw_payload.get("item_list")
    normalized_items = [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
    attachments = _attachments_from_items(normalized_items)
    text = _message_text(normalized_items, attachments)
    message_id = (
        _text(raw_payload.get("client_id"))
        or _text(raw_payload.get("msgid"))
        or _fallback_message_id(raw_payload, platform_user_id=platform_user_id, text=text)
    )

    metadata: dict[str, Any] = {
        "tenant_id": credential.tenant_id,
        "tenant_name": credential.tenant_name,
        "context_token": context_token,
        "channel_binding_account_id": credential.account_id,
        "channel_binding_user_id": credential.user_id,
        "conversation_type": "direct",
    }
    if attachments:
        metadata["attachments"] = attachments
        metadata["attachment_count"] = len(attachments)

    return UnifiedMessage(
        message_id=message_id,
        channel=ChannelType.WECOM,
        platform_user_id=platform_user_id,
        chat_id=platform_user_id,
        text=text,
        received_at=_received_at(raw_payload),
        raw_payload=raw_payload,
        metadata=metadata,
        session_id=f"wecom:{credential.tenant_id}:{platform_user_id}",
    )


class WecomIlinkPollerService:
    poll_interval_seconds = 2.0
    request_timeout_seconds = 50.0

    def __init__(self) -> None:
        self._lock = Lock()
        self._thread: Thread | None = None
        self._stop_event: Event | None = None
        self._cursor_by_tenant: dict[str, str] = {}
        self._last_error_by_tenant: dict[str, str] = {}

    def start(self) -> bool:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return True
            stop_event = Event()
            thread = Thread(
                target=self._run,
                args=(stop_event,),
                name="workbot-wecom-ilink-poller",
                daemon=True,
            )
            self._stop_event = stop_event
            self._thread = thread
            thread.start()
            return True

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            stop_event = self._stop_event
            self._thread = None
            self._stop_event = None
        if stop_event is not None:
            stop_event.set()
        if thread is not None:
            thread.join(timeout=self.request_timeout_seconds + 1.0)

    def poll_once(self) -> dict[str, int]:
        runtime_settings = get_channel_integration_runtime_settings()["wecom"]
        if not bool(runtime_settings.get("enabled", False)):
            return {"credentials": 0, "polled": 0, "ingested": 0, "errors": 0}

        credentials = wecom_channel_binding_service.list_credentials()
        if not credentials:
            return {"credentials": 0, "polled": 0, "ingested": 0, "errors": 0}

        summary = {"credentials": len(credentials), "polled": 0, "ingested": 0, "errors": 0}
        for credential in credentials:
            try:
                ingested = self._poll_credential(credential)
                summary["polled"] += 1
                summary["ingested"] += ingested
                self._last_error_by_tenant.pop(_text(credential.tenant_id), None)
            except Exception as exc:  # pragma: no cover - defensive runtime path
                tenant_id = _text(credential.tenant_id)
                summary["errors"] += 1
                self._record_error_once(tenant_id, str(exc))
        return summary

    def _run(self, stop_event: Event) -> None:
        logger.info("WeCom iLink poller started")
        append_realtime_event(
            agent="WeCom iLink Poller",
            message="微信个人号轮询服务已启动",
            type_="info",
            source="wecom_ilink",
            metadata={"event": "poller_started"},
        )
        while not stop_event.wait(timeout=self.poll_interval_seconds):
            try:
                self.poll_once()
            except Exception as exc:  # pragma: no cover - defensive runtime path
                logger.exception("WeCom iLink poller cycle failed")
                append_realtime_event(
                    agent="WeCom iLink Poller",
                    message=f"微信轮询周期执行失败：{exc}",
                    type_="warning",
                    source="wecom_ilink",
                    metadata={"event": "poller_cycle_failed", "error": str(exc)},
                )
        logger.info("WeCom iLink poller stopped")
        append_realtime_event(
            agent="WeCom iLink Poller",
            message="微信个人号轮询服务已停止",
            type_="info",
            source="wecom_ilink",
            metadata={"event": "poller_stopped"},
        )

    def _poll_credential(self, credential: WecomChannelCredential) -> int:
        tenant_id = _text(credential.tenant_id)
        base_url = _text(credential.base_url).rstrip("/")
        access_token = _text(credential.access_token)
        if not tenant_id or not base_url or not access_token:
            raise RuntimeError("WeCom iLink credential is incomplete")

        cursor = self._cursor_by_tenant.get(tenant_id, "")
        body = {
            "get_updates_buf": cursor,
            "base_info": ILINK_BASE_INFO,
        }
        with httpx.Client(timeout=self.request_timeout_seconds, trust_env=False) as client:
            response = client.post(
                f"{base_url}/ilink/bot/getupdates",
                headers=_ilink_headers(access_token),
                json=body,
            )
            response.raise_for_status()
            payload = response.json()

        if not isinstance(payload, dict):
            raise RuntimeError("WeCom iLink getupdates returned an invalid response")
        ret = payload.get("ret")
        errcode = payload.get("errcode")
        if ret not in {None, 0} or errcode not in {None, 0}:
            raise RuntimeError(
                _text(payload.get("errmsg")) or f"WeCom iLink getupdates failed (ret={ret}, errcode={errcode})"
            )

        next_cursor = _text(payload.get("get_updates_buf"))
        if next_cursor:
            self._cursor_by_tenant[tenant_id] = next_cursor

        raw_messages = [item for item in payload.get("msgs") or [] if isinstance(item, dict)]
        if raw_messages:
            message_types = sorted(
                {
                    str(message_type)
                    for raw_message in raw_messages
                    if (message_type := _parse_int(raw_message.get("message_type"))) is not None
                }
            )
            logger.info(
                "WeCom iLink poll received updates: tenant_id=%s raw_messages=%s message_types=%s",
                tenant_id,
                len(raw_messages),
                ",".join(message_types) or "unknown",
            )

        ingested = 0
        skipped_non_user = 0
        skipped_invalid = 0
        for raw_message in raw_messages:
            if _parse_int(raw_message.get("message_type")) != 1:
                skipped_non_user += 1
                continue
            message = _build_unified_message(raw_message, credential)
            if message is None:
                skipped_invalid += 1
                continue
            attachment_count = len(message.metadata.get("attachments") or []) if isinstance(message.metadata, dict) else 0
            logger.info(
                "WeCom iLink inbound ingested: tenant_id=%s platform_user_id=%s message_id=%s text_chars=%s attachments=%s",
                tenant_id,
                message.platform_user_id,
                message.message_id,
                len(message.text or ""),
                attachment_count,
            )
            message_ingestion_service.ingest_unified_message(
                message,
                auth_scope="webhook:wecom",
                entrypoint="master_bot.dispatch",
                entrypoint_agent="WeCom iLink Poller",
            )
            ingested += 1
        if raw_messages:
            logger.info(
                "WeCom iLink poll processed updates: tenant_id=%s raw_messages=%s ingested=%s skipped_non_user=%s skipped_invalid=%s",
                tenant_id,
                len(raw_messages),
                ingested,
                skipped_non_user,
                skipped_invalid,
            )
        return ingested

    def _record_error_once(self, tenant_id: str, error: str) -> None:
        if self._last_error_by_tenant.get(tenant_id) == error:
            return
        self._last_error_by_tenant[tenant_id] = error
        logger.warning("WeCom iLink poll failed: tenant_id=%s error=%s", tenant_id, error)
        append_realtime_event(
            agent="WeCom iLink Poller",
            message=f"微信轮询失败：{error}",
            type_="warning",
            source="wecom_ilink",
            metadata={"event": "poll_failed", "tenant_id": tenant_id, "error": error},
        )


wecom_ilink_poller_service = WecomIlinkPollerService()
