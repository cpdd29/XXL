import app.modules.reception.security_monitor.webhook_guard_service as webhook_guard_service
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import delete

from app.db.models import SecuritySubjectStateRecord
from app.main import app
import app.modules.reception.api.webhooks as webhooks
from app.modules.agent_config.registries.mandatory_agent_registry_service import ensure_mandatory_agents_registered
from app.platform.persistence.persistence_service import persistence_service
from app.modules.dispatch.workflow_runtime.mandatory_workflow_registry_service import ensure_mandatory_workflows_registered
from app.platform.persistence.runtime_store import store


def _camel_to_snake(key: str) -> str:
    characters: list[str] = []
    for character in key:
        if character.isupper():
            if characters:
                characters.append("_")
            characters.append(character.lower())
        else:
            characters.append(character)
    return "".join(characters)


def _payload_value(payload: dict, key: str):
    if key in payload:
        return payload[key]
    return payload.get(_camel_to_snake(key))


def _channel_payload(channel: str) -> dict:
    if channel == "wecom":
        return {
            "msgid": "wecom-secret-msg-1",
            "from": {"userid": "wecom-secret-user-1", "name": "张三"},
            "chatid": "wecom-secret-room-1",
            "msgtype": "text",
            "text": {"content": "请帮我搜索企业微信适配方案"},
        }
    if channel == "feishu":
        return {
            "header": {"event_type": "im.message.receive_v1"},
            "event": {
                "sender": {
                    "sender_id": {"open_id": "ou_feishu_secret_user_1"},
                    "sender_type": "user",
                },
                "message": {
                    "message_id": "om_feishu_secret_1",
                    "chat_id": "oc_feishu_secret_chat_1",
                    "message_type": "text",
                    "content": "{\"text\":\"请帮我写一段飞书通知\"}",
                },
            },
        }
    return {
        "msgId": "ding-secret-msg-1",
        "senderStaffId": "ding-secret-user-1",
        "conversationId": "ding-secret-conv-1",
        "conversationType": "2",
        "msgtype": "text",
        "text": {"content": "请生成会议纪要"},
    }


def _settings_with_channel_secret(channel: str, secret: str):
    config = _runtime_channel_settings()
    config[channel]["webhook_secret"] = secret
    return config


def _runtime_channel_settings() -> dict[str, dict[str, object]]:
    return {
        "telegram": {
            "enabled": True,
            "api_base_url": "https://api.telegram.org",
            "http_timeout_seconds": 10.0,
            "bot_token": None,
            "webhook_secret": None,
        },
        "wecom": {
            "enabled": True,
            "webhook_secret": None,
            "webhook_secret_header": "X-WorkBot-Webhook-Secret",
            "webhook_secret_query_param": "token",
            "bot_webhook_base_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send",
            "bot_webhook_key": None,
            "http_timeout_seconds": 10.0,
        },
        "feishu": {
            "enabled": True,
            "webhook_secret": None,
            "webhook_secret_header": "X-WorkBot-Webhook-Secret",
            "webhook_secret_query_param": "token",
            "bot_webhook_base_url": "https://open.feishu.cn/open-apis/bot/v2/hook",
            "bot_webhook_key": None,
            "http_timeout_seconds": 10.0,
        },
        "dingtalk": {
            "enabled": True,
            "api_base_url": "https://oapi.dingtalk.com",
            "http_timeout_seconds": 10.0,
            "webhook_secret": None,
            "webhook_secret_header": "X-WorkBot-Webhook-Secret",
            "webhook_secret_query_param": "token",
        },
    }


@pytest.fixture(autouse=True)
def default_enabled_channel_integrations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        webhooks,
        "get_channel_integration_runtime_settings",
        lambda: _runtime_channel_settings(),
    )


@pytest.fixture
def client(default_enabled_channel_integrations) -> TestClient:
    existing_users = {
        str(user.get("id") or "").strip(): store.clone(user)
        for user in store.users
        if str(user.get("id") or "").strip()
    }
    existing_profiles = {
        str(profile_id): store.clone(profile)
        for profile_id, profile in store.user_profiles.items()
    }
    persistence_service.initialize()
    session_factory = getattr(persistence_service, "_session_factory", None)
    if session_factory is not None:
        with session_factory() as session:
            session.execute(delete(SecuritySubjectStateRecord))
            session.commit()
    for user_id, user in existing_users.items():
        if not any(str(candidate.get("id") or "").strip() == user_id for candidate in store.users):
            store.users.append(user)
    for profile_id, profile in existing_profiles.items():
        store.user_profiles.setdefault(profile_id, profile)
    ensure_mandatory_workflows_registered()
    ensure_mandatory_agents_registered()
    return TestClient(app)


def _settings_with_webhook_rate_limit(*, max_requests: int, window_seconds: int):
    return type(
        "Settings",
        (),
        {
            "telegram_webhook_secret": None,
            "wecom_webhook_secret": None,
            "wecom_webhook_secret_header": "X-WorkBot-Webhook-Secret",
            "wecom_webhook_secret_query_param": "token",
            "feishu_webhook_secret": None,
            "feishu_webhook_secret_header": "X-WorkBot-Webhook-Secret",
            "feishu_webhook_secret_query_param": "token",
            "dingtalk_webhook_secret": None,
            "dingtalk_webhook_secret_header": "X-WorkBot-Webhook-Secret",
            "dingtalk_webhook_secret_query_param": "token",
            "webhook_rate_limit_max_requests": max_requests,
            "webhook_rate_limit_window_seconds": window_seconds,
            "webhook_max_payload_bytes": 128 * 1024,
        },
    )()


def _settings_with_webhook_payload_limit(*, max_payload_bytes: int):
    return type(
        "Settings",
        (),
        {
            "telegram_webhook_secret": None,
            "wecom_webhook_secret": None,
            "wecom_webhook_secret_header": "X-WorkBot-Webhook-Secret",
            "wecom_webhook_secret_query_param": "token",
            "feishu_webhook_secret": None,
            "feishu_webhook_secret_header": "X-WorkBot-Webhook-Secret",
            "feishu_webhook_secret_query_param": "token",
            "dingtalk_webhook_secret": None,
            "dingtalk_webhook_secret_header": "X-WorkBot-Webhook-Secret",
            "dingtalk_webhook_secret_query_param": "token",
            "webhook_rate_limit_max_requests": 120,
            "webhook_rate_limit_window_seconds": 60,
            "webhook_max_payload_bytes": max_payload_bytes,
        },
    )()


def test_telegram_webhook_converts_payload_to_unified_message(client: TestClient, auth_headers) -> None:
    del auth_headers
    before_task_ids = {str(task.get("id") or "").strip() for task in store.tasks}
    payload = {
        "update_id": 1001,
        "message": {
            "message_id": 777,
            "date": 1710000000,
            "text": "请帮我搜索产品技术规格",
            "from": {
                "id": 90001,
                "is_bot": False,
                "first_name": "Alice",
                "username": "alice_telegram",
                "language_code": "zh",
            },
            "chat": {
                "id": 80001,
                "type": "private",
                "username": "alice_telegram",
            },
        },
    }

    response = client.post("/api/webhooks/telegram", json=payload)
    assert response.status_code == 200

    body = response.json()
    assert body["ok"] is True
    assert body["entrypoint"] == "master_bot.dispatch"
    assert body["intent"] == "search"
    assert body["unifiedMessage"]["channel"] == "telegram"
    assert body["unifiedMessage"]["platformUserId"] == "90001"
    assert body["unifiedMessage"]["chatId"] == "80001"
    assert body["unifiedMessage"]["text"] == "请帮我搜索产品技术规格"
    task_id = str(body["taskId"] or "").strip()
    assert task_id
    assert task_id not in before_task_ids
    assert any(str(task.get("id") or "").strip() == task_id for task in store.tasks)


def test_telegram_webhook_preserves_router_workflow_mode_for_chat_route(client: TestClient) -> None:
    payload = {
        "update_id": 1005,
        "message": {
            "message_id": 780,
            "date": 1710000003,
            "text": "今天广州天气怎么样",
            "from": {
                "id": 90004,
                "is_bot": False,
                "first_name": "Dave",
                "username": "dave_telegram",
                "language_code": "zh",
            },
            "chat": {
                "id": 80004,
                "type": "private",
                "username": "dave_telegram",
            },
        },
    }

    response = client.post("/api/webhooks/telegram", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["interactionMode"] == "chat"
    assert body["receptionMode"] == "direct_question"
    assert _payload_value(body["routeDecision"], "workflowMode") == "free_workflow"


def test_telegram_webhook_rejects_non_message_update(client: TestClient) -> None:
    response = client.post("/api/webhooks/telegram", json={"update_id": 1002})

    assert response.status_code == 400
    assert response.json()["detail"] == "Telegram payload does not contain message"


def test_telegram_webhook_validates_secret_header_when_configured(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        webhooks,
        "get_channel_integration_runtime_settings",
        lambda: {
            **_runtime_channel_settings(),
            "telegram": {
                **_runtime_channel_settings()["telegram"],
                "webhook_secret": "expected-secret",
            },
        },
    )

    payload = {
        "update_id": 1003,
        "message": {
            "message_id": 778,
            "date": 1710000001,
            "text": "请帮我搜索 webhook 配置",
            "from": {
                "id": 90002,
                "is_bot": False,
                "first_name": "Bob",
                "username": "bob_telegram",
                "language_code": "zh",
            },
            "chat": {
                "id": 80002,
                "type": "private",
                "username": "bob_telegram",
            },
        },
    }

    rejected = client.post("/api/webhooks/telegram", json=payload)
    accepted = client.post(
        "/api/webhooks/telegram",
        json=payload,
        headers={"X-Telegram-Bot-Api-Secret-Token": "expected-secret"},
    )

    assert rejected.status_code == 401
    assert rejected.json()["detail"] == "Invalid Telegram webhook secret"
    assert accepted.status_code == 200


def test_telegram_webhook_rate_limits_requests_when_configured(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings_with_webhook_rate_limit(max_requests=1, window_seconds=60)
    monkeypatch.setattr(webhook_guard_service, "get_settings", lambda: settings)
    monkeypatch.setattr(webhook_guard_service.redis_provider, "get_client", lambda: None)
    webhook_guard_service.reset_webhook_guard_state()

    payload = {
        "update_id": 1004,
        "message": {
            "message_id": 779,
            "date": 1710000002,
            "text": "请帮我搜索 webhook 限流",
            "from": {
                "id": 90003,
                "is_bot": False,
                "first_name": "Carol",
                "username": "carol_telegram",
                "language_code": "zh",
            },
            "chat": {
                "id": 80003,
                "type": "private",
                "username": "carol_telegram",
            },
        },
    }

    first = client.post(
        "/api/webhooks/telegram",
        json=payload,
        headers={"X-Forwarded-For": "198.51.100.231"},
    )
    second = client.post(
        "/api/webhooks/telegram",
        json=payload,
        headers={"X-Forwarded-For": "198.51.100.231"},
    )

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["detail"] == "Webhook rate limit exceeded"
    rate_limit_audit = next(
        (item for item in store.audit_logs if item["action"] == "Webhook 限流拦截"),
        None,
    )
    assert rate_limit_audit is not None
    assert rate_limit_audit["resource"] == "webhook:channel:telegram"
    assert rate_limit_audit["metadata"]["trace"]["layer"] == "webhook_guard"
    assert rate_limit_audit["metadata"]["webhook_guard"]["route_key"] == "channel:telegram"


def test_channel_webhook_rejects_oversized_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings_with_webhook_payload_limit(max_payload_bytes=220)
    monkeypatch.setattr(webhook_guard_service, "get_settings", lambda: settings)

    response = client.post(
        "/api/webhooks/wecom",
        json={
            "msgid": "wecom-oversized-1",
            "from": {"userid": "wecom-user-oversized"},
            "chatid": "wecom-room-oversized",
            "msgtype": "text",
            "text": {"content": "x" * 800},
        },
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "Webhook payload too large"
    payload_audit = next(
        (item for item in store.audit_logs if item["action"] == "Webhook 载荷超限拦截"),
        None,
    )
    assert payload_audit is not None
    assert payload_audit["resource"] == "webhook:channel:wecom"
    assert payload_audit["metadata"]["webhook_guard"]["payload_limit_bytes"] == 220


@pytest.mark.parametrize(
    ("channel", "display_name"),
    [
        ("wecom", "WeCom"),
        ("feishu", "Feishu"),
        ("dingtalk", "DingTalk"),
    ],
)
def test_channel_webhook_validates_secret_when_configured(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    channel: str,
    display_name: str,
) -> None:
    monkeypatch.setattr(
        webhooks,
        "get_channel_integration_runtime_settings",
        lambda: _settings_with_channel_secret(channel, "expected-secret"),
    )
    payload = _channel_payload(channel)

    rejected = client.post(f"/api/webhooks/{channel}", json=payload)
    rejected_wrong_header = client.post(
        f"/api/webhooks/{channel}",
        json=payload,
        headers={"X-WorkBot-Webhook-Secret": "wrong-secret"},
    )
    accepted_header = client.post(
        f"/api/webhooks/{channel}",
        json=payload,
        headers={"X-WorkBot-Webhook-Secret": "expected-secret"},
    )
    accepted_query = client.post(
        f"/api/webhooks/{channel}?token=expected-secret",
        json=payload,
    )

    assert rejected.status_code == 401
    assert rejected.json()["detail"] == f"Invalid {display_name} webhook secret"
    assert rejected_wrong_header.status_code == 401
    assert rejected_wrong_header.json()["detail"] == f"Invalid {display_name} webhook secret"
    assert accepted_header.status_code == 200
    assert accepted_query.status_code == 200


def test_channel_webhook_returns_503_when_channel_integration_disabled(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_settings = _runtime_channel_settings()
    runtime_settings["wecom"]["enabled"] = False
    monkeypatch.setattr(webhooks, "get_channel_integration_runtime_settings", lambda: runtime_settings)

    response = client.post("/api/webhooks/wecom", json=_channel_payload("wecom"))

    assert response.status_code == 503
    assert response.json()["detail"] == "wecom channel integration is disabled"


@pytest.mark.parametrize(
    ("channel", "payload", "expected_user", "expected_chat", "expected_text", "expected_intent"),
    [
        (
            "wecom",
            {
                "msgid": "wecom-msg-1",
                "from": {"userid": "wecom-user-1", "name": "张三"},
                "chatid": "wecom-room-1",
                "msgtype": "text",
                "text": {"content": "请帮我搜索企业微信适配方案"},
            },
            "wecom-user-1",
            "wecom-room-1",
            "请帮我搜索企业微信适配方案",
            "search",
        ),
        (
            "feishu",
            {
                "header": {"event_type": "im.message.receive_v1"},
                "event": {
                    "sender": {
                        "sender_id": {"open_id": "ou_feishu_user_1"},
                        "sender_type": "user",
                    },
                    "message": {
                        "message_id": "om_feishu_1",
                        "chat_id": "oc_feishu_chat_1",
                        "message_type": "text",
                        "content": "{\"text\":\"请帮我写一段飞书通知\"}",
                    },
                },
            },
            "ou_feishu_user_1",
            "oc_feishu_chat_1",
            "请帮我写一段飞书通知",
            "write",
        ),
        (
            "dingtalk",
            {
                "msgId": "ding-msg-1",
                "senderStaffId": "ding-user-1",
                "conversationId": "ding-conv-1",
                "conversationType": "2",
                "msgtype": "text",
                "text": {"content": "请生成会议纪要"},
            },
            "ding-user-1",
            "ding-conv-1",
            "请生成会议纪要",
            "write",
        ),
    ],
)
def test_channel_webhook_converts_payload_to_unified_message(
    client: TestClient,
    auth_headers,
    channel: str,
    payload: dict,
    expected_user: str,
    expected_chat: str,
    expected_text: str,
    expected_intent: str,
) -> None:
    del auth_headers
    before = len(store.tasks)

    response = client.post(f"/api/webhooks/{channel}", json=payload)
    assert response.status_code == 200

    body = response.json()
    assert body["ok"] is True
    assert body["entrypoint"] == "master_bot.dispatch"
    assert body["intent"] == expected_intent
    assert body["unifiedMessage"]["channel"] == channel
    assert body["unifiedMessage"]["platformUserId"] == expected_user
    assert body["unifiedMessage"]["chatId"] == expected_chat
    assert body["unifiedMessage"]["text"] == expected_text

    after = len(store.tasks)
    assert after == before + 1


@pytest.mark.parametrize(
    ("channel", "payload", "expected_detail"),
    [
        ("wecom", {"chatid": "wecom-room-1"}, "WeCom payload missing platform user id"),
        (
            "feishu",
            {"header": {"event_type": "im.message.receive_v1"}},
            "Feishu payload missing platform user id",
        ),
        ("dingtalk", {"conversationId": "ding-conv-1"}, "DingTalk payload missing platform user id"),
    ],
)
def test_channel_webhook_rejects_invalid_payload(
    client: TestClient,
    channel: str,
    payload: dict,
    expected_detail: str,
) -> None:
    response = client.post(f"/api/webhooks/{channel}", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == expected_detail


def test_sanitize_webhook_payload_limits_depth_and_collection_size() -> None:
    nested_payload: dict[str, object] = {"root": {}}
    pointer = nested_payload["root"]
    for depth in range(12):
        assert isinstance(pointer, dict)
        pointer[f"level_{depth}"] = {}
        pointer = pointer[f"level_{depth}"]

    oversized_payload = {
        "nested": nested_payload,
        "items": [f"item-{index}" for index in range(130)],
        "text": "x" * 5000,
    }
    sanitized = webhook_guard_service.sanitize_webhook_payload(oversized_payload)

    assert isinstance(sanitized, dict)
    assert isinstance(sanitized["nested"], dict)
    assert "[TRUNCATED_DEPTH]" in str(sanitized["nested"])
    assert isinstance(sanitized["items"], list)
    assert sanitized["items"][-1] == "[TRUNCATED_LIST_ITEMS]"
    assert isinstance(sanitized["text"], str)
    assert sanitized["text"].endswith("[TRUNCATED]")
