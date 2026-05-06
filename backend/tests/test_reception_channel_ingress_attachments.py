from __future__ import annotations

from app.modules.reception.channel_ingress.dingtalk import DingTalkAdapter
from app.modules.reception.channel_ingress.feishu import FeishuAdapter
from app.modules.reception.channel_ingress.telegram import TelegramAdapter


def test_dingtalk_adapter_keeps_file_only_message_as_attachment_context() -> None:
    adapter = DingTalkAdapter()

    message = adapter.receive_message(
        {
            "msgId": "ding-file-001",
            "senderStaffId": "ding-user-001",
            "conversationId": "conv-001",
            "msgtype": "file",
            "file": {
                "fileName": "报价单.pdf",
                "downloadUrl": "https://example.test/files/offer.pdf",
            },
        }
    )

    assert "客户发送了" in message.text
    assert "报价单.pdf" in message.text
    assert message.metadata["attachment_count"] == 1
    assert message.metadata["attachments"][0]["kind"] == "file"


def test_dingtalk_adapter_preserves_attachment_excerpt_fields() -> None:
    adapter = DingTalkAdapter()

    message = adapter.receive_message(
        {
            "msgId": "ding-file-002",
            "senderStaffId": "ding-user-002",
            "conversationId": "conv-002",
            "msgtype": "file",
            "file": {
                "fileName": "需求说明.md",
                "downloadUrl": "https://example.test/files/requirements.md",
                "excerpt": "本次需要先整理官网改版需求，再给出排期建议。",
                "summary": "官网改版需求说明",
            },
        }
    )

    assert message.metadata["attachments"][0]["name"] == "需求说明.md"
    assert message.metadata["attachments"][0]["url"] == "https://example.test/files/requirements.md"
    assert message.metadata["attachments"][0]["excerpt"] == "本次需要先整理官网改版需求，再给出排期建议。"
    assert message.metadata["attachments"][0]["summary"] == "官网改版需求说明"


def test_feishu_adapter_keeps_image_only_message_as_attachment_context() -> None:
    adapter = FeishuAdapter()

    message = adapter.receive_message(
        {
            "header": {"event_type": "im.message.receive_v1"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_123"}, "sender_type": "user"},
                "message": {
                    "message_id": "om_123",
                    "chat_id": "oc_123",
                    "message_type": "image",
                    "content": '{"image_key":"img_123"}',
                },
            },
        }
    )

    assert "客户发送了" in message.text
    assert message.metadata["attachments"][0]["kind"] == "image"
    assert message.metadata["attachment_count"] == 1


def test_telegram_adapter_keeps_photo_only_message_as_attachment_context() -> None:
    adapter = TelegramAdapter()

    message = adapter.receive_message(
        {
            "update_id": 9001,
            "message": {
                "message_id": 101,
                "date": 1714212000,
                "photo": [{"file_id": "photo-file-id"}],
                "from": {"id": 42, "is_bot": False, "first_name": "Alice"},
                "chat": {"id": 99, "type": "private"},
            },
        }
    )

    assert "客户发送了" in message.text
    assert message.metadata["attachments"][0]["kind"] == "image"
    assert message.metadata["attachment_count"] == 1
