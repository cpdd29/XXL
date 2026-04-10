from __future__ import annotations

import asyncio
import json
import logging
import ssl
from threading import Event, Lock, Thread
from typing import Any
from urllib.parse import quote_plus

import certifi
import websockets

try:
    from dingtalk_stream import Credential, DingTalkStreamClient
    from dingtalk_stream.chatbot import ChatbotHandler, ChatbotMessage
    from dingtalk_stream.frames import AckMessage, CallbackMessage

    DINGTALK_STREAM_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency fallback
    DINGTALK_STREAM_AVAILABLE = False

    class Credential:  # type: ignore[no-redef]
        def __init__(self, client_id: str, client_secret: str) -> None:
            self.client_id = client_id
            self.client_secret = client_secret

    class ChatbotHandler:  # type: ignore[no-redef]
        pass

    class _FallbackChatbotMessage:
        def __init__(self, payload: dict[str, Any]) -> None:
            self._payload = payload
            self.sender_staff_id = payload.get("senderStaffId")
            self.sender_id = payload.get("senderId")

        def to_dict(self) -> dict[str, Any]:
            return dict(self._payload)

    class ChatbotMessage:  # type: ignore[no-redef]
        TOPIC = "chatbot"
        DELEGATE_TOPIC = "chatbot_delegate"

        @staticmethod
        def from_dict(payload: dict[str, Any]) -> _FallbackChatbotMessage:
            return _FallbackChatbotMessage(payload or {})

    class AckMessage:  # type: ignore[no-redef]
        STATUS_OK = 200
        STATUS_SYSTEM_EXCEPTION = 500

    class CallbackMessage:  # type: ignore[no-redef]
        def __init__(self, data: dict[str, Any] | None = None) -> None:
            self.data = data or {}

    class DingTalkStreamClient:  # type: ignore[no-redef]
        def __init__(self, credential: Credential, logger=None) -> None:
            self.credential = credential
            self.logger = logger
            self.websocket = None

        def register_callback_handler(self, topic: str, handler: object) -> None:
            return None

        def pre_start(self) -> None:
            return None

        def open_connection(self) -> dict[str, Any] | None:
            return None

        async def keepalive(self, websocket) -> None:
            return None

        async def background_task(self, json_message: dict[str, Any]) -> None:
            return None

from app.services.message_ingestion_service import ingest_channel_webhook
from app.services.operational_log_service import append_realtime_event
from app.services.settings_service import get_channel_integration_runtime_settings


logger = logging.getLogger(__name__)


class WorkBotDingTalkStreamHandler(ChatbotHandler):
    def __init__(self) -> None:
        super().__init__()

    @staticmethod
    def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
        incoming_message = ChatbotMessage.from_dict(payload or {})
        normalized_payload = incoming_message.to_dict()
        platform_user_id = str(
            incoming_message.sender_staff_id
            or incoming_message.sender_id
            or normalized_payload.get("senderStaffId")
            or normalized_payload.get("senderId")
            or ""
        ).strip()
        if platform_user_id:
            normalized_payload["platform_user_id"] = platform_user_id
        return normalized_payload

    @staticmethod
    def _is_self_message(payload: dict[str, Any]) -> bool:
        sender_id = str(payload.get("senderId") or "").strip()
        chatbot_user_id = str(payload.get("chatbotUserId") or "").strip()
        return bool(sender_id and chatbot_user_id and sender_id == chatbot_user_id)

    @staticmethod
    def _message_text_content(payload: dict[str, Any]) -> str:
        text_payload = payload.get("text")
        if isinstance(text_payload, dict):
            return str(text_payload.get("content") or text_payload.get("text") or "").strip()
        if isinstance(text_payload, str):
            return text_payload.strip()
        return ""

    @classmethod
    def _expected_skip_reason(cls, payload: dict[str, Any]) -> str | None:
        msgtype = str(payload.get("msgtype") or "").strip().lower()
        if msgtype and msgtype != "text":
            return f"ignored non-text message ({msgtype})"
        if not cls._message_text_content(payload):
            return "ignored message without text content"
        return None

    def process_payload(self, payload: dict[str, Any]) -> tuple[int, str]:
        normalized_payload = self._normalize_payload(payload)
        if self._is_self_message(normalized_payload):
            return AckMessage.STATUS_OK, "ignored self message"
        skip_reason = self._expected_skip_reason(normalized_payload)
        if skip_reason is not None:
            return AckMessage.STATUS_OK, skip_reason

        try:
            ingest_channel_webhook("dingtalk", normalized_payload)
        except ValueError as exc:
            logger.warning("Ignoring unsupported DingTalk stream payload: %s", exc)
            append_realtime_event(
                agent="DingTalk Stream",
                message=f"已忽略不支持的钉钉消息：{exc}",
                type_="warning",
                source="dingtalk_stream",
                metadata={"event": "message_ignored", "reason": str(exc)},
            )
            return AckMessage.STATUS_OK, f"ignored: {exc}"
        except Exception as exc:  # pragma: no cover - defensive retry path
            logger.exception("Failed to ingest DingTalk stream payload")
            append_realtime_event(
                agent="DingTalk Stream",
                message=f"钉钉消息入站失败：{exc}",
                type_="warning",
                source="dingtalk_stream",
                metadata={"event": "message_ingest_failed", "error": str(exc)},
            )
            return AckMessage.STATUS_SYSTEM_EXCEPTION, str(exc)

        return AckMessage.STATUS_OK, "accepted"

    async def process(self, message: CallbackMessage) -> tuple[int, str]:
        payload = message.data if isinstance(message.data, dict) else {}
        return self.process_payload(payload)


class DingTalkStreamService:
    reconnect_interval_seconds = 5.0
    receive_timeout_seconds = 1.0

    def __init__(self) -> None:
        self._lock = Lock()
        self._thread: Thread | None = None
        self._stop_event: Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client: DingTalkStreamClient | None = None
        self._config_signature: tuple[str, str] | None = None
        self._handler = WorkBotDingTalkStreamHandler()
        self._ssl_context = ssl.create_default_context(cafile=certifi.where())

    def reconcile_runtime(self) -> bool:
        if not DINGTALK_STREAM_AVAILABLE:
            self.stop()
            return False
        runtime_settings = get_channel_integration_runtime_settings()["dingtalk"]
        if not bool(runtime_settings.get("enabled", True)):
            self.stop()
            return False

        client_id = str(runtime_settings.get("client_id") or "").strip()
        client_secret = str(runtime_settings.get("client_secret") or "").strip()
        if not client_id or not client_secret:
            self.stop()
            return False

        signature = (client_id, client_secret)
        with self._lock:
            thread_alive = self._thread is not None and self._thread.is_alive()
            if thread_alive and self._config_signature == signature:
                return True

        self.stop()
        self._start_with_credentials(client_id=client_id, client_secret=client_secret)
        return True

    def start(self) -> bool:
        return self.reconcile_runtime()

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            loop = self._loop
            client = self._client
            stop_event = self._stop_event
            self._thread = None
            self._loop = None
            self._client = None
            self._stop_event = None
            self._config_signature = None

        if stop_event is not None:
            stop_event.set()
        if loop is not None and client is not None and client.websocket is not None:
            try:
                asyncio.run_coroutine_threadsafe(client.websocket.close(), loop)
            except RuntimeError:
                pass
        if thread is not None and thread.is_alive():
            thread.join(timeout=5)

    def _start_with_credentials(self, *, client_id: str, client_secret: str) -> None:
        stop_event = Event()
        thread = Thread(
            target=self._run_thread,
            kwargs={
                "client_id": client_id,
                "client_secret": client_secret,
                "stop_event": stop_event,
            },
            daemon=True,
            name="workbot-dingtalk-stream",
        )
        with self._lock:
            self._stop_event = stop_event
            self._thread = thread
            self._config_signature = (client_id, client_secret)
        thread.start()

    def _run_thread(self, *, client_id: str, client_secret: str, stop_event: Event) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        with self._lock:
            self._loop = loop
        try:
            loop.run_until_complete(
                self._run_forever(
                    client_id=client_id,
                    client_secret=client_secret,
                    stop_event=stop_event,
                )
            )
        finally:
            pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()

    async def _run_forever(self, *, client_id: str, client_secret: str, stop_event: Event) -> None:
        client = DingTalkStreamClient(Credential(client_id, client_secret), logger=logger)
        client.register_callback_handler(ChatbotMessage.TOPIC, self._handler)
        client.register_callback_handler(ChatbotMessage.DELEGATE_TOPIC, self._handler)
        client.pre_start()
        with self._lock:
            self._client = client

        while not stop_event.is_set():
            connection = client.open_connection()
            if not connection:
                await asyncio.sleep(self.reconnect_interval_seconds)
                continue

            endpoint = str(connection.get("endpoint") or "").strip()
            ticket = str(connection.get("ticket") or "").strip()
            if not endpoint or not ticket:
                logger.warning("DingTalk stream open_connection returned invalid payload: %s", connection)
                await asyncio.sleep(self.reconnect_interval_seconds)
                continue

            uri = f"{endpoint}?ticket={quote_plus(ticket)}"
            try:
                async with websockets.connect(uri, ssl=self._ssl_context) as websocket:
                    client.websocket = websocket
                    keepalive_task = asyncio.create_task(client.keepalive(websocket))
                    try:
                        while not stop_event.is_set():
                            try:
                                raw_message = await asyncio.wait_for(
                                    websocket.recv(),
                                    timeout=self.receive_timeout_seconds,
                                )
                            except TimeoutError:
                                continue
                            try:
                                json_message = json.loads(raw_message)
                            except json.JSONDecodeError:
                                logger.warning("Ignoring non-JSON DingTalk stream payload")
                                continue
                            await client.background_task(json_message)
                    finally:
                        keepalive_task.cancel()
                        await asyncio.gather(keepalive_task, return_exceptions=True)
            except Exception as exc:  # pragma: no cover - network reconnect path
                if stop_event.is_set():
                    break
                logger.warning("DingTalk stream connection interrupted: %s", exc)
                await asyncio.sleep(self.reconnect_interval_seconds)


dingtalk_stream_service = DingTalkStreamService()
