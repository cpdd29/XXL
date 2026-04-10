from __future__ import annotations

import ssl

import certifi

from app.services.dingtalk_stream_service import DingTalkStreamService, WorkBotDingTalkStreamHandler


def test_dingtalk_stream_handler_accepts_incoming_text_message(monkeypatch) -> None:
    ingested_payloads: list[dict] = []

    def fake_ingest(channel: str, payload: dict) -> dict:
        ingested_payloads.append({"channel": channel, "payload": payload})
        return {"ok": True}

    monkeypatch.setattr(
        "app.services.dingtalk_stream_service.ingest_channel_webhook",
        fake_ingest,
    )

    handler = WorkBotDingTalkStreamHandler()
    code, message = handler.process_payload(
        {
            "msgId": "ding-stream-1",
            "senderId": "$:LWCP_v1:$sender-1",
            "senderStaffId": "ding-user-1",
            "chatbotUserId": "$:LWCP_v1:$bot-1",
            "conversationId": "cid-test-1",
            "conversationType": "2",
            "sessionWebhook": "https://oapi.dingtalk.com/robot/sendBySession?session=abc123",
            "msgtype": "text",
            "text": {"content": "你好，帮我总结一下今天的进度"},
        }
    )

    assert code == 200
    assert message == "accepted"
    assert ingested_payloads[0]["channel"] == "dingtalk"
    assert ingested_payloads[0]["payload"]["platform_user_id"] == "ding-user-1"


def test_dingtalk_stream_handler_ignores_self_message(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.dingtalk_stream_service.ingest_channel_webhook",
        lambda channel, payload: (_ for _ in ()).throw(AssertionError("should not ingest")),
    )

    handler = WorkBotDingTalkStreamHandler()
    code, message = handler.process_payload(
        {
            "msgId": "ding-stream-self-1",
            "senderId": "$:LWCP_v1:$bot-1",
            "chatbotUserId": "$:LWCP_v1:$bot-1",
            "conversationId": "cid-self-1",
            "msgtype": "text",
            "text": {"content": "机器人自己发出的消息"},
        }
    )

    assert code == 200
    assert message == "ignored self message"


def test_dingtalk_stream_handler_skips_non_text_message_without_warning_noise(monkeypatch) -> None:
    realtime_events: list[dict] = []
    monkeypatch.setattr(
        "app.services.dingtalk_stream_service.ingest_channel_webhook",
        lambda channel, payload: (_ for _ in ()).throw(AssertionError("should not ingest")),
    )
    monkeypatch.setattr(
        "app.services.dingtalk_stream_service.append_realtime_event",
        lambda **kwargs: realtime_events.append(kwargs),
    )

    handler = WorkBotDingTalkStreamHandler()
    code, message = handler.process_payload(
        {
            "msgId": "ding-stream-image-1",
            "senderId": "$:LWCP_v1:$sender-2",
            "senderStaffId": "ding-user-2",
            "chatbotUserId": "$:LWCP_v1:$bot-1",
            "conversationId": "cid-non-text-1",
            "msgtype": "image",
            "content": {"downloadCode": "abc"},
        }
    )

    assert code == 200
    assert message == "ignored non-text message (image)"
    assert realtime_events == []


def test_dingtalk_stream_handler_skips_message_without_text_content_without_warning_noise(monkeypatch) -> None:
    realtime_events: list[dict] = []
    monkeypatch.setattr(
        "app.services.dingtalk_stream_service.ingest_channel_webhook",
        lambda channel, payload: (_ for _ in ()).throw(AssertionError("should not ingest")),
    )
    monkeypatch.setattr(
        "app.services.dingtalk_stream_service.append_realtime_event",
        lambda **kwargs: realtime_events.append(kwargs),
    )

    handler = WorkBotDingTalkStreamHandler()
    code, message = handler.process_payload(
        {
            "msgId": "ding-stream-empty-text-1",
            "senderId": "$:LWCP_v1:$sender-3",
            "senderStaffId": "ding-user-3",
            "chatbotUserId": "$:LWCP_v1:$bot-1",
            "conversationId": "cid-empty-text-1",
            "msgtype": "text",
            "text": {"content": "   "},
        }
    )

    assert code == 200
    assert message == "ignored message without text content"
    assert realtime_events == []


def test_dingtalk_stream_service_reconcile_runtime_uses_client_credentials(monkeypatch) -> None:
    started: list[tuple[str, str]] = []
    stopped: list[bool] = []

    monkeypatch.setattr(
        "app.services.dingtalk_stream_service.get_channel_integration_runtime_settings",
        lambda: {
            "dingtalk": {
                "enabled": True,
                "client_id": "ding-client-id",
                "client_secret": "ding-client-secret",
            }
        },
    )

    service = DingTalkStreamService()
    monkeypatch.setattr(service, "stop", lambda: stopped.append(True))
    monkeypatch.setattr(
        service,
        "_start_with_credentials",
        lambda *, client_id, client_secret: started.append((client_id, client_secret)),
    )

    assert service.reconcile_runtime() is True
    assert stopped == [True]
    assert started == [("ding-client-id", "ding-client-secret")]


def test_dingtalk_stream_service_uses_certifi_ssl_context() -> None:
    service = DingTalkStreamService()

    assert isinstance(service._ssl_context, ssl.SSLContext)
    assert service._ssl_context.get_ca_certs()
    assert certifi.where().endswith("cacert.pem")
