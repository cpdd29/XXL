from __future__ import annotations

from pathlib import Path

from app.adapters.dingtalk import (
    DingTalkAdapter,
    decode_dingtalk_delivery_target,
    encode_dingtalk_delivery_target,
)
from app.adapters.feishu import FeishuAdapter
from app.adapters.telegram import TelegramAdapter
from app.adapters.wecom import WeComAdapter
import app.services.operational_log_service as operational_log_service_module
from app.services.channel_outbound_service import ChannelOutboundService
from app.services.persistence_service import StatePersistenceService
from app.services.store import store


class FakeTelegramAdapter:
    def __init__(self) -> None:
        self.sent_messages: list[dict[str, str]] = []

    def send_message(self, *, chat_id: str, text: str) -> dict[str, str]:
        self.sent_messages.append({"chat_id": chat_id, "text": text})
        return {"ok": True, "chat_id": chat_id, "message_id": "tg-msg-1"}

    def get_user_info(self, platform_user_id: str) -> dict[str, str]:
        return {"id": platform_user_id}


class FakeDingTalkAdapter:
    def __init__(self) -> None:
        self.sent_messages: list[dict[str, str]] = []

    def send_message(self, *, chat_id: str, text: str) -> dict[str, str]:
        self.sent_messages.append({"chat_id": chat_id, "text": text})
        return {"ok": True, "chat_id": chat_id, "message_id": "ding-msg-1"}

    def get_user_info(self, platform_user_id: str) -> dict[str, str]:
        return {"id": platform_user_id}


def _channel_runtime_settings() -> dict[str, dict[str, object]]:
    return {
        "telegram": {
            "enabled": True,
            "api_base_url": "https://api.telegram.org",
            "http_timeout_seconds": 10.0,
            "bot_token": "telegram-token-1",
            "webhook_secret": None,
        },
        "wecom": {
            "enabled": True,
            "webhook_secret": None,
            "webhook_secret_header": "X-WorkBot-Webhook-Secret",
            "webhook_secret_query_param": "token",
            "bot_webhook_base_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send",
            "bot_webhook_key": "wecom-key-default",
            "http_timeout_seconds": 10.0,
        },
        "feishu": {
            "enabled": True,
            "webhook_secret": None,
            "webhook_secret_header": "X-WorkBot-Webhook-Secret",
            "webhook_secret_query_param": "token",
            "bot_webhook_base_url": "https://open.feishu.cn/open-apis/bot/v2/hook",
            "bot_webhook_key": "feishu-key-default",
            "http_timeout_seconds": 10.0,
        },
        "dingtalk": {
            "enabled": True,
            "app_id": "",
            "agent_id": "",
            "client_id": "",
            "client_secret": None,
            "corp_id": "",
            "api_base_url": "https://oapi.dingtalk.com",
            "http_timeout_seconds": 10.0,
            "webhook_secret": None,
            "webhook_secret_header": "X-WorkBot-Webhook-Secret",
            "webhook_secret_query_param": "token",
        },
    }


def test_channel_outbound_service_sends_telegram_result_when_chat_binding_exists() -> None:
    store.audit_logs = []
    adapter = FakeTelegramAdapter()
    service = ChannelOutboundService(adapters={"telegram": adapter})

    delivery = service.deliver_task_result(
        {
            "id": "task-1",
            "channel": "telegram",
            "session_id": "telegram:80001",
            "title": "渠道消息任务 - search",
        },
        {
            "title": "检索摘要 - 部署文档",
            "summary": "已整理部署文档要点",
            "content": "这里是部署文档的详细摘要。",
            "references": [{"title": "WorkBot_开发全指南.md / Deployment"}],
        },
    )

    assert delivery["status"] == "sent"
    assert delivery["message"] == "结果已通过 Telegram 回传到 chat 80001"
    assert adapter.sent_messages[0]["chat_id"] == "80001"
    assert "检索摘要 - 部署文档" in adapter.sent_messages[0]["text"]
    assert "WorkBot_开发全指南.md / Deployment" in adapter.sent_messages[0]["text"]
    assert store.audit_logs[0]["action"] == "渠道出站成功"
    assert store.audit_logs[0]["resource"] == "channel_outbound:telegram"


def test_channel_outbound_service_renders_chat_reply_as_plain_text() -> None:
    service = ChannelOutboundService(adapters={"telegram": FakeTelegramAdapter()})

    text = service.render_task_result_text(
        {"id": "task-chat-plain-1", "title": "渠道消息任务 - help"},
        {
            "kind": "chat_reply",
            "title": "问候回复",
            "summary": "已返回轻量问候消息",
            "text": "你好，我在。现在你想让我帮你处理什么？",
            "content": "不应使用这段内容",
        },
    )

    assert text == "你好，我在。现在你想让我帮你处理什么？"
    assert "【" not in text


def test_channel_outbound_service_sends_chat_reply_without_structured_wrapper() -> None:
    store.audit_logs = []
    adapter = FakeTelegramAdapter()
    service = ChannelOutboundService(adapters={"telegram": adapter})

    delivery = service.deliver_task_result(
        {
            "id": "task-chat-plain-2",
            "channel": "telegram",
            "session_id": "telegram:chat-reply-room-1",
            "title": "渠道消息任务 - help",
        },
        {
            "kind": "chat_reply",
            "text": "我可以继续帮你排查钉钉对话体验，你先告诉我你最想优化哪一段。",
        },
    )

    assert delivery["status"] == "sent"
    assert adapter.sent_messages[0]["chat_id"] == "chat-reply-room-1"
    assert adapter.sent_messages[0]["text"] == "我可以继续帮你排查钉钉对话体验，你先告诉我你最想优化哪一段。"
    assert "【" not in adapter.sent_messages[0]["text"]


def test_channel_outbound_service_renders_failure_in_conversational_tone() -> None:
    service = ChannelOutboundService(adapters={"telegram": FakeTelegramAdapter()})

    text = service.render_task_failure_text(
        {"id": "task-chat-failure-1", "title": "渠道消息任务 - help"},
        "工作流推进失败，请稍后重试。",
    )

    assert text.startswith("这次我没顺利处理完。")
    assert "【" not in text
    assert "本次任务未能成功完成" not in text
    assert "工作流推进失败" in text


def test_channel_outbound_service_skips_when_chat_binding_is_missing() -> None:
    store.audit_logs = []
    adapter = FakeTelegramAdapter()
    service = ChannelOutboundService(adapters={"telegram": adapter})

    delivery = service.deliver_task_result(
        {
            "id": "task-2",
            "channel": "telegram",
            "session_id": "",
        },
        {
            "title": "帮助说明",
            "summary": "已生成帮助说明",
        },
    )

    assert delivery["status"] == "skipped"
    assert delivery["message"] == "结果已生成，但缺少 Telegram chat_id，无法自动回传。"
    assert adapter.sent_messages == []
    assert store.audit_logs[0]["action"] == "渠道出站跳过"
    assert store.audit_logs[0]["status"] == "warning"


def test_channel_outbound_service_retries_after_transient_adapter_failure() -> None:
    store.audit_logs = []
    attempts: list[dict[str, str]] = []

    class FlakyAdapter:
        def send_message(self, *, chat_id: str, text: str) -> dict[str, str]:
            attempts.append({"chat_id": chat_id, "text": text})
            if len(attempts) == 1:
                raise RuntimeError("temporary unavailable")
            return {"ok": True, "chat_id": chat_id, "message_id": "retry-msg-1"}

        def get_user_info(self, platform_user_id: str) -> dict[str, str]:
            return {"id": platform_user_id}

    service = ChannelOutboundService(adapters={"telegram": FlakyAdapter()})

    delivery = service.deliver_task_result(
        {
            "id": "task-3",
            "channel": "telegram",
            "session_id": "telegram:retry-room-1",
        },
        {
            "title": "重试回传",
            "summary": "第一次失败后再次发送",
        },
    )

    assert delivery["status"] == "sent"
    assert len(attempts) == 2
    assert store.audit_logs[0]["resource"] == "channel_outbound:telegram"


def test_channel_outbound_service_persists_trace_metadata_for_audit() -> None:
    store.audit_logs = []
    adapter = FakeTelegramAdapter()
    service = ChannelOutboundService(adapters={"telegram": adapter})

    delivery = service.deliver_task_result(
        {
            "id": "task-trace-1",
            "channel": "telegram",
            "session_id": "telegram:90001",
            "trace_id": "trace-channel-outbound-1",
            "workflow_run_id": "run-channel-outbound-1",
        },
        {"title": "结果摘要", "summary": "已完成回传"},
    )

    assert delivery["status"] == "sent"
    assert store.audit_logs[0]["metadata"]["trace"]["trace_id"] == "trace-channel-outbound-1"
    assert store.audit_logs[0]["metadata"]["trace"]["layer"] == "channel_outbound"


def test_channel_outbound_service_appends_durable_operational_log(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store.audit_logs = []
    store.realtime_logs = []
    adapter = FakeTelegramAdapter()
    service = ChannelOutboundService(adapters={"telegram": adapter})
    persistence = StatePersistenceService(
        runtime_store=store,
        database_url=f"sqlite:///{tmp_path / 'channel-outbound-operational.db'}",
    )
    assert persistence.initialize() is True
    monkeypatch.setattr(operational_log_service_module, "persistence_service", persistence)

    try:
        delivery = service.deliver_task_result(
            {
                "id": "task-operational-1",
                "channel": "telegram",
                "session_id": "telegram:90002",
                "trace_id": "trace-channel-operational-1",
                "workflow_run_id": "run-channel-operational-1",
            },
            {"title": "结果摘要", "summary": "已完成 durable realtime 落库"},
        )
        logs = persistence.list_operational_logs(limit=10)
    finally:
        persistence.close()

    assert delivery["status"] == "sent"
    assert logs is not None
    assert logs[0]["source"] == "channel_outbound"
    assert logs[0]["trace_id"] == "trace-channel-operational-1"
    assert logs[0]["task_id"] == "task-operational-1"
    assert logs[0]["workflow_run_id"] == "run-channel-operational-1"
    assert logs[0]["metadata"]["event"] == "delivery_succeeded"


def test_channel_outbound_service_prefers_dingtalk_session_webhook_from_run_dispatch_context() -> None:
    store.audit_logs = []
    adapter = FakeDingTalkAdapter()
    service = ChannelOutboundService(adapters={"dingtalk": adapter})

    delivery = service.deliver_task_result(
        {
            "id": "task-ding-1",
            "channel": "dingtalk",
            "session_id": "dingtalk:ding-conv-1",
            "title": "钉钉渠道任务",
        },
        {
            "title": "会议纪要",
            "summary": "已生成钉钉会议纪要",
        },
        run={
            "dispatch_context": {
                "channel_delivery": {
                    "channel": "dingtalk",
                    "target_id": "https://oapi.dingtalk.com/robot/sendBySession?session=abc123",
                    "target_type": "session_webhook_url",
                    "session_webhook": "https://oapi.dingtalk.com/robot/sendBySession?session=abc123",
                    "conversation_id": "ding-conv-1",
                }
            }
        },
    )

    assert delivery["status"] == "sent"
    assert adapter.sent_messages[0]["chat_id"] == "https://oapi.dingtalk.com/robot/sendBySession?session=abc123"
    assert store.audit_logs[0]["resource"] == "channel_outbound:dingtalk"
    assert store.audit_logs[0]["status"] == "success"


def test_channel_outbound_service_builds_dingtalk_openapi_target_when_app_credentials_are_configured(
    monkeypatch,
) -> None:
    store.audit_logs = []
    adapter = FakeDingTalkAdapter()
    service = ChannelOutboundService(adapters={"dingtalk": adapter})
    monkeypatch.setattr(
        "app.services.channel_outbound_service.get_channel_integration_runtime_settings",
        lambda: {
            **_channel_runtime_settings(),
            "dingtalk": {
                **_channel_runtime_settings()["dingtalk"],
                "agent_id": "100001",
                "client_id": "ding-client-id",
                "client_secret": "ding-client-secret",
            },
        },
    )

    delivery = service.deliver_task_result(
        {
            "id": "task-ding-openapi-1",
            "channel": "dingtalk",
            "session_id": "dingtalk:ding-conv-openapi-1",
            "title": "钉钉应用凭证回发",
        },
        {
            "title": "会议纪要",
            "summary": "已生成钉钉会议纪要",
        },
        run={
            "dispatch_context": {
                "channel_delivery": {
                    "channel": "dingtalk",
                    "target_id": "https://oapi.dingtalk.com/robot/sendBySession?session=fallback-openapi-1",
                    "target_type": "session_webhook_url",
                    "session_webhook": "https://oapi.dingtalk.com/robot/sendBySession?session=fallback-openapi-1",
                    "conversation_id": "ding-conv-openapi-1",
                    "platform_user_id": "ding-user-openapi-1",
                    "corp_id": "ding-corp-001",
                }
            }
        },
    )

    assert delivery["status"] == "sent"
    encoded_target = adapter.sent_messages[0]["chat_id"]
    decoded_target = decode_dingtalk_delivery_target(encoded_target)
    assert decoded_target == {
        "target_type": "openapi_user",
        "platform_user_id": "ding-user-openapi-1",
        "corp_id": "ding-corp-001",
        "conversation_id": "ding-conv-openapi-1",
        "session_webhook": "https://oapi.dingtalk.com/robot/sendBySession?session=fallback-openapi-1",
    }


def test_channel_outbound_service_reports_missing_dingtalk_session_webhook() -> None:
    store.audit_logs = []
    adapter = FakeDingTalkAdapter()
    service = ChannelOutboundService(adapters={"dingtalk": adapter})

    delivery = service.deliver_task_result(
        {
            "id": "task-ding-2",
            "channel": "dingtalk",
            "session_id": "dingtalk:ding-conv-2",
            "title": "钉钉渠道任务",
        },
        {
            "title": "帮助说明",
            "summary": "已生成帮助说明",
        },
        run={
            "dispatch_context": {
                "channel_delivery": {
                    "channel": "dingtalk",
                    "target_id": "ding-conv-2",
                    "target_type": "conversation_id",
                    "conversation_id": "ding-conv-2",
                }
            }
        },
    )

    assert delivery["status"] == "skipped"
    assert "sessionWebhook" in delivery["message"]
    assert adapter.sent_messages == []


def test_dingtalk_adapter_send_message_normalizes_session_token(monkeypatch) -> None:
    adapter = DingTalkAdapter()
    monkeypatch.setattr(
        "app.adapters.dingtalk.get_channel_integration_runtime_settings",
        _channel_runtime_settings,
    )

    def fake_request(url: str, payload: dict[str, str]) -> dict[str, str]:
        assert url == "https://oapi.dingtalk.com/robot/sendBySession?session=abc123"
        assert payload["msgtype"] == "text"
        assert payload["text"]["content"] == "hello dingtalk"
        return {"errcode": 0, "errmsg": "ok", "messageId": "ding-msg-2"}

    monkeypatch.setattr(adapter, "_request", fake_request)

    response = adapter.send_message(chat_id="abc123", text="hello dingtalk")

    assert response["ok"] is True
    assert response["chat_id"] == "abc123"
    assert response["message_id"] == "ding-msg-2"


def test_dingtalk_adapter_prefers_openapi_delivery_when_app_credentials_configured(monkeypatch) -> None:
    adapter = DingTalkAdapter()
    monkeypatch.setattr(
        "app.adapters.dingtalk.get_channel_integration_runtime_settings",
        lambda: {
            **_channel_runtime_settings(),
            "dingtalk": {
                **_channel_runtime_settings()["dingtalk"],
                "agent_id": "100001",
                "client_id": "ding-client-id",
                "client_secret": "ding-client-secret",
                "corp_id": "ding-corp-001",
            },
        },
    )

    calls: list[dict[str, object]] = []

    def fake_request_json(
        method: str,
        url: str,
        *,
        payload: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        timeout: float | None = None,
    ) -> dict[str, object]:
        calls.append(
            {
                "method": method,
                "url": url,
                "payload": payload,
                "params": params,
                "timeout": timeout,
            }
        )
        if url.endswith("/gettoken"):
            return {"access_token": "token-123", "expires_in": 7200}
        return {"errcode": 0, "task_id": "task-openapi-1"}

    monkeypatch.setattr(adapter, "_request_json", fake_request_json)

    response = adapter.send_message(
        chat_id=encode_dingtalk_delivery_target(
            {
                "target_type": "openapi_user",
                "platform_user_id": "ding-user-123",
                "corp_id": "ding-corp-001",
                "session_webhook": "https://oapi.dingtalk.com/robot/sendBySession?session=fallback-1",
            }
        ),
        text="hello openapi dingtalk",
    )

    assert [call["url"] for call in calls] == [
        "https://oapi.dingtalk.com/gettoken",
        "https://oapi.dingtalk.com/topapi/message/corpconversation/asyncsend_v2",
    ]
    assert calls[0]["method"] == "GET"
    assert calls[0]["params"] == {"appkey": "ding-client-id", "appsecret": "ding-client-secret"}
    assert calls[1]["method"] == "POST"
    assert calls[1]["params"] == {"access_token": "token-123"}
    assert calls[1]["payload"] == {
        "agent_id": 100001,
        "userid_list": "ding-user-123",
        "msg": {"msgtype": "text", "text": {"content": "hello openapi dingtalk"}},
        "to_all_user": False,
    }
    assert response["ok"] is True
    assert response["chat_id"] == "ding-user-123"
    assert response["message_id"] == "task-openapi-1"


def test_dingtalk_adapter_falls_back_to_session_webhook_when_openapi_send_fails(monkeypatch) -> None:
    adapter = DingTalkAdapter()
    monkeypatch.setattr(
        "app.adapters.dingtalk.get_channel_integration_runtime_settings",
        lambda: {
            **_channel_runtime_settings(),
            "dingtalk": {
                **_channel_runtime_settings()["dingtalk"],
                "agent_id": "100001",
                "client_id": "ding-client-id",
                "client_secret": "ding-client-secret",
            },
        },
    )

    monkeypatch.setattr(
        adapter,
        "_send_via_openapi",
        lambda runtime_settings, target_spec, *, text: (_ for _ in ()).throw(
            RuntimeError("openapi unavailable")
        ),
    )

    def fake_request(url: str, payload: dict[str, object]) -> dict[str, object]:
        assert url == "https://oapi.dingtalk.com/robot/sendBySession?session=fallback-2"
        assert payload == {
            "msgtype": "text",
            "text": {"content": "hello fallback dingtalk"},
        }
        return {"errcode": 0, "messageId": "ding-fallback-1"}

    monkeypatch.setattr(adapter, "_request", fake_request)

    response = adapter.send_message(
        chat_id=encode_dingtalk_delivery_target(
            {
                "target_type": "openapi_user",
                "platform_user_id": "ding-user-456",
                "session_webhook": "https://oapi.dingtalk.com/robot/sendBySession?session=fallback-2",
            }
        ),
        text="hello fallback dingtalk",
    )

    assert response["ok"] is True
    assert response["chat_id"] == "https://oapi.dingtalk.com/robot/sendBySession?session=fallback-2"
    assert response["message_id"] == "ding-fallback-1"


def test_wecom_adapter_send_message_supports_direct_webhook_url(monkeypatch) -> None:
    adapter = WeComAdapter()
    monkeypatch.setattr(
        "app.adapters.wecom.get_channel_integration_runtime_settings",
        _channel_runtime_settings,
    )

    def fake_request(url: str, payload: dict[str, object]) -> dict[str, object]:
        assert url == "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=wecom-key-1"
        assert payload == {
            "msgtype": "text",
            "text": {"content": "hello wecom"},
        }
        return {"errcode": 0, "errmsg": "ok", "msgid": "wecom-msg-1"}

    monkeypatch.setattr(adapter, "_request", fake_request)

    response = adapter.send_message(
        chat_id="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=wecom-key-1",
        text="hello wecom",
    )

    assert response["ok"] is True
    assert response["chat_id"] == "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=wecom-key-1"
    assert response["message_id"] == "wecom-msg-1"


def test_feishu_adapter_send_message_normalizes_bot_key(monkeypatch) -> None:
    adapter = FeishuAdapter()
    monkeypatch.setattr(
        "app.adapters.feishu.get_channel_integration_runtime_settings",
        _channel_runtime_settings,
    )

    def fake_request(url: str, payload: dict[str, object]) -> dict[str, object]:
        assert url == "https://open.feishu.cn/open-apis/bot/v2/hook/feishu-key-2"
        assert payload == {
            "msg_type": "text",
            "content": {"text": "hello feishu"},
        }
        return {"code": 0, "msg": "success", "message_id": "feishu-msg-1"}

    monkeypatch.setattr(adapter, "_request", fake_request)

    response = adapter.send_message(chat_id="feishu-key-2", text="hello feishu")

    assert response["ok"] is True
    assert response["chat_id"] == "feishu-key-2"
    assert response["message_id"] == "feishu-msg-1"


def test_telegram_adapter_send_message_uses_runtime_channel_settings(monkeypatch) -> None:
    adapter = TelegramAdapter()
    monkeypatch.setattr(
        "app.adapters.telegram.get_channel_integration_runtime_settings",
        lambda: {
            **_channel_runtime_settings(),
            "telegram": {
                **_channel_runtime_settings()["telegram"],
                "api_base_url": "https://telegram.internal",
                "http_timeout_seconds": 12.5,
                "bot_token": "telegram-runtime-token",
            },
        },
    )

    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "ok": True,
                "result": {"chat": {"id": "chat-telegram-1"}, "message_id": 99},
            }

    class FakeClient:
        def __init__(self, *, timeout: float, trust_env: bool) -> None:
            captured["timeout"] = timeout
            captured["trust_env"] = trust_env

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, url: str, json: dict[str, object]) -> FakeResponse:
            captured["url"] = url
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr("app.adapters.telegram.httpx.Client", FakeClient)

    response = adapter.send_message(chat_id="chat-telegram-1", text="hello telegram")

    assert captured["timeout"] == 12.5
    assert captured["trust_env"] is False
    assert captured["url"] == "https://telegram.internal/bottelegram-runtime-token/sendMessage"
    assert captured["json"] == {"chat_id": "chat-telegram-1", "text": "hello telegram"}
    assert response["ok"] is True
    assert response["chat_id"] == "chat-telegram-1"
    assert response["message_id"] == "99"


def test_wecom_adapter_send_message_uses_runtime_default_bot_key(monkeypatch) -> None:
    adapter = WeComAdapter()
    monkeypatch.setattr(
        "app.adapters.wecom.get_channel_integration_runtime_settings",
        lambda: {
            **_channel_runtime_settings(),
            "wecom": {
                **_channel_runtime_settings()["wecom"],
                "bot_webhook_base_url": "https://qyapi.internal/webhook/send",
                "bot_webhook_key": "runtime-wecom-key",
            },
        },
    )

    def fake_request(url: str, payload: dict[str, object]) -> dict[str, object]:
        assert url == "https://qyapi.internal/webhook/send?key=runtime-wecom-key"
        assert payload == {
            "msgtype": "text",
            "text": {"content": "hello runtime wecom"},
        }
        return {"errcode": 0, "errmsg": "ok", "msgid": "wecom-msg-runtime-1"}

    monkeypatch.setattr(adapter, "_request", fake_request)

    response = adapter.send_message(chat_id="", text="hello runtime wecom")

    assert response["ok"] is True
    assert response["chat_id"] == ""
    assert response["message_id"] == "wecom-msg-runtime-1"
