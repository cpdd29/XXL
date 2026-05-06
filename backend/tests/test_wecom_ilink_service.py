from __future__ import annotations

import httpx

import app.modules.reception.application.message_ingestion_service as message_ingestion_service_module
import app.modules.reception.channel_ingress.wecom_ilink_poller_service as wecom_ilink_poller_service_module
import app.modules.reception.customer_access.service as customer_access_service_module
from app.modules.reception.channel_binding.schemas import WecomChannelCredential
from app.modules.reception.channel_ingress.wecom import (
    WeComAdapter,
    decode_wecom_delivery_target,
    encode_wecom_delivery_target,
)
from app.modules.reception.channel_ingress.wecom_ilink_poller_service import WecomIlinkPollerService
from app.modules.reception.schemas.messages import ChannelType, UnifiedMessage


def test_message_tenant_binding_prefers_message_metadata() -> None:
    message = UnifiedMessage(
        message_id="msg-wecom-tenant-001",
        channel=ChannelType.WECOM,
        platform_user_id="wx-user-tenant-001",
        chat_id="wx-user-tenant-001",
        text="你好",
        received_at="2026-05-05T12:00:00+08:00",
        raw_payload={},
        metadata={
            "tenant_id": "tenant-from-message",
            "tenant_name": "消息租户",
        },
    )

    tenant_id, tenant_name = customer_access_service_module._resolve_message_tenant_binding(message)

    assert tenant_id == "tenant-from-message"
    assert tenant_name == "消息租户"


def test_build_channel_delivery_binding_uses_ilink_context_for_wecom() -> None:
    message = UnifiedMessage(
        message_id="msg-wecom-ctx-001",
        channel=ChannelType.WECOM,
        platform_user_id="wx-user-001",
        chat_id="wx-user-001",
        text="你好",
        received_at="2026-05-05T12:00:00+08:00",
        raw_payload={},
        metadata={
            "tenant_id": "tenant-wechat-a",
            "context_token": "ctx-wechat-001",
        },
        session_id="wecom:tenant-wechat-a:wx-user-001",
    )

    binding = message_ingestion_service_module._build_channel_delivery_binding(message)

    assert binding is not None
    assert binding["target_type"] == "ilink_context"
    assert decode_wecom_delivery_target(binding["target_id"]) == {
        "tenant_id": "tenant-wechat-a",
        "user_id": "wx-user-001",
        "context_token": "ctx-wechat-001",
    }


def test_wecom_adapter_sends_reply_via_ilink_context(monkeypatch) -> None:
    credential = WecomChannelCredential(
        tenant_id="tenant-wechat-a",
        tenant_name="微信租户A",
        account_id="wx-bot-001",
        access_token="wx-token-001",
        base_url="https://ilinkai.weixin.qq.com",
        user_id="wx-login-001",
        updated_at="2026-05-05T12:00:00+08:00",
    )
    target = encode_wecom_delivery_target(
        {
            "tenant_id": "tenant-wechat-a",
            "user_id": "wx-user-001",
            "context_token": "ctx-wechat-001",
        }
    )
    captured: dict[str, object] = {}

    def _mock_get_credential(tenant_id: str):
        assert tenant_id == "tenant-wechat-a"
        return credential

    def _mock_post(self, url: str, headers: dict[str, str] | None = None, json: dict | None = None, **_: object) -> httpx.Response:
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"ret": 0},
        )

    monkeypatch.setattr(
        wecom_ilink_poller_service_module.wecom_channel_binding_service,
        "get_credential",
        _mock_get_credential,
    )
    monkeypatch.setattr(httpx.Client, "post", _mock_post)

    result = WeComAdapter().send_message(chat_id=target, text="你好，已经收到您的消息。")

    assert result["ok"] is True
    assert result["chat_id"] == "wx-user-001"
    assert captured["url"] == "https://ilinkai.weixin.qq.com/ilink/bot/sendmessage"
    request_headers = captured["headers"]
    assert isinstance(request_headers, dict)
    assert request_headers["Authorization"] == "Bearer wx-token-001"
    request_json = captured["json"]
    assert isinstance(request_json, dict)
    assert request_json["base_info"]["channel_version"] == "0.2.1"
    assert request_json["msg"]["to_user_id"] == "wx-user-001"
    assert request_json["msg"]["context_token"] == "ctx-wechat-001"
    assert request_json["msg"]["item_list"][0]["text_item"]["text"] == "你好，已经收到您的消息。"


def test_wecom_ilink_poller_ingests_text_message(monkeypatch) -> None:
    credential = WecomChannelCredential(
        tenant_id="tenant-wechat-a",
        tenant_name="微信租户A",
        account_id="wx-bot-001",
        access_token="wx-token-001",
        base_url="https://ilinkai.weixin.qq.com",
        user_id="wx-login-001",
        updated_at="2026-05-05T12:00:00+08:00",
    )
    captured: list[UnifiedMessage] = []

    def _mock_settings() -> dict[str, object]:
        return {
            "wecom": {
                "enabled": True,
            }
        }

    def _mock_list_credentials():
        return [credential]

    def _mock_post(self, url: str, headers: dict[str, str] | None = None, json: dict | None = None, **_: object) -> httpx.Response:
        assert url == "https://ilinkai.weixin.qq.com/ilink/bot/getupdates"
        assert headers is not None
        assert headers["Authorization"] == "Bearer wx-token-001"
        assert json is not None
        assert json["base_info"]["channel_version"] == "0.2.1"
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "ret": 0,
                "get_updates_buf": "buf-002",
                "msgs": [
                    {
                        "client_id": "wx-msg-001",
                        "message_type": 1,
                        "from_user_id": "wx-user-001",
                        "context_token": "ctx-wechat-001",
                        "create_time_ms": 1777953600000,
                        "item_list": [
                            {
                                "type": 1,
                                "text_item": {
                                    "text": "你好，我想咨询报价",
                                },
                            }
                        ],
                    }
                ],
            },
        )

    def _mock_ingest_unified_message(message: UnifiedMessage, **_: object) -> dict[str, object]:
        captured.append(message)
        return {"message": "accepted"}

    monkeypatch.setattr(wecom_ilink_poller_service_module, "get_channel_integration_runtime_settings", _mock_settings)
    monkeypatch.setattr(
        wecom_ilink_poller_service_module.wecom_channel_binding_service,
        "list_credentials",
        _mock_list_credentials,
    )
    monkeypatch.setattr(httpx.Client, "post", _mock_post)
    monkeypatch.setattr(
        wecom_ilink_poller_service_module.message_ingestion_service,
        "ingest_unified_message",
        _mock_ingest_unified_message,
    )

    service = WecomIlinkPollerService()
    summary = service.poll_once()

    assert summary == {"credentials": 1, "polled": 1, "ingested": 1, "errors": 0}
    assert service._cursor_by_tenant["tenant-wechat-a"] == "buf-002"
    assert len(captured) == 1
    message = captured[0]
    assert message.channel == ChannelType.WECOM
    assert message.platform_user_id == "wx-user-001"
    assert message.text == "你好，我想咨询报价"
    assert message.metadata["tenant_id"] == "tenant-wechat-a"
    assert message.metadata["context_token"] == "ctx-wechat-001"
    assert message.session_id == "wecom:tenant-wechat-a:wx-user-001"
