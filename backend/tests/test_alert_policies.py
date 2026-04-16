from fastapi.testclient import TestClient

from app.main import app
from app.services import alert_center_service
from app.services.store import store


client = TestClient(app)


class _FakeAdapter:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def send_message(self, *, chat_id: str, text: str) -> dict:
        self.calls.append({"chat_id": chat_id, "text": text})
        return {"ok": True}


class _FakeAdapterRegistry:
    def __init__(self, adapters: dict[str, _FakeAdapter]) -> None:
        self.adapters = adapters

    def get(self, channel: str):
        adapter = self.adapters.get(str(channel))
        if adapter is None:
            raise ValueError(f"Unsupported channel: {channel}")
        return adapter


def _scope_headers(auth_headers_factory) -> dict[str, str]:
    return {
        **auth_headers_factory(role="operator", email="ops@example.test"),
        "X-WorkBot-Tenant-Id": "tenant-alerts",
        "X-WorkBot-Project-Id": "project-policy",
        "X-WorkBot-Environment": "staging",
    }


def _seed_warning_alert() -> str:
    store.audit_logs = [
        {
            "id": "audit-policy-1",
            "timestamp": "2026-04-13T09:00:00+00:00",
            "action": "安全网关拦截:prompt_injection",
            "user": "telegram:user-policy",
            "resource": "security_penalty",
            "status": "warning",
            "ip": "127.0.0.1",
            "details": "策略测试告警",
            "metadata": {
                "trace": {"layer": "prompt_injection"},
                "scope": {
                    "tenant_id": "tenant-alerts",
                    "project_id": "project-policy",
                    "environment": "staging",
                },
            },
        }
    ]
    return "audit:audit-policy-1"


def _create_subscriptions(headers: dict[str, str]) -> None:
    client.post(
        "/api/alerts/subscriptions",
        json={"channel": "dingtalk", "target": "dingtalk-room", "severityScope": ["warning"]},
        headers=headers,
    )
    client.post(
        "/api/alerts/subscriptions",
        json={"channel": "telegram", "target": "telegram-room", "severityScope": ["warning"]},
        headers=headers,
    )
    client.post(
        "/api/alerts/subscriptions",
        json={"channel": "wecom", "target": "wecom-room", "severityScope": ["warning"]},
        headers=headers,
    )


def _upsert_warning_policy(headers: dict[str, str]) -> None:
    response = client.put(
        "/api/alerts/escalation-policy",
        json={
            "policies": [
                {
                    "severity": "warning",
                    "orderedChannels": ["wecom", "telegram"],
                    "sendAll": False,
                    "maxDeliveries": 2,
                    "suppressionMinutes": 30,
                }
            ]
        },
        headers=headers,
    )
    assert response.status_code == 200


def test_alert_escalation_policy_get_put_roundtrip_with_scope_headers(auth_headers_factory) -> None:
    scoped_headers = _scope_headers(auth_headers_factory)
    put_response = client.put(
        "/api/alerts/escalation-policy",
        json={
            "policies": [
                {
                    "severity": "warning",
                    "orderedChannels": ["wecom", "telegram"],
                    "sendAll": False,
                    "maxDeliveries": 2,
                    "suppressionMinutes": 45,
                },
                {
                    "severity": "critical",
                    "orderedChannels": ["dingtalk"],
                    "sendAll": True,
                    "suppressionMinutes": 60,
                },
            ]
        },
        headers=scoped_headers,
    )
    assert put_response.status_code == 200
    put_body = put_response.json()
    assert put_body["ok"] is True
    assert put_body["policy"]["tenantId"] == "tenant-alerts"
    assert put_body["policy"]["projectId"] == "project-policy"
    assert put_body["policy"]["environment"] == "staging"
    assert {item["severity"] for item in put_body["policy"]["policies"]} == {"warning", "critical"}

    get_response = client.get("/api/alerts/escalation-policy", headers=scoped_headers)
    assert get_response.status_code == 200
    get_body = get_response.json()
    assert get_body["policy"]["id"] == put_body["policy"]["id"]
    assert get_body["policy"]["tenantId"] == "tenant-alerts"
    warning_policy = next(item for item in get_body["policy"]["policies"] if item["severity"] == "warning")
    assert warning_policy["orderedChannels"] == ["wecom", "telegram"]
    assert warning_policy["sendAll"] is False
    assert warning_policy["maxDeliveries"] == 2

    default_scope_response = client.get(
        "/api/alerts/escalation-policy",
        headers=auth_headers_factory(role="operator", email="ops@example.test"),
    )
    assert default_scope_response.status_code == 200
    default_policy = default_scope_response.json()["policy"]
    assert default_policy["tenantId"]
    assert default_policy["policies"] == []


def test_alert_delivery_preview_route_applies_policy_ordering_and_truncation(auth_headers_factory) -> None:
    scoped_headers = _scope_headers(auth_headers_factory)
    alert_id = _seed_warning_alert()
    _create_subscriptions(scoped_headers)
    _upsert_warning_policy(scoped_headers)

    preview_response = client.get(f"/api/alerts/{alert_id}/delivery-preview", headers=scoped_headers)
    assert preview_response.status_code == 200
    body = preview_response.json()
    assert body["matchedSubscriptions"] == 3
    assert body["selectedSubscriptions"] == 2
    assert body["policy"]["severity"] == "warning"
    assert body["policy"]["sendAll"] is False
    assert body["policy"]["maxDeliveries"] == 2
    assert [item["channel"] for item in body["deliveries"]] == ["wecom", "telegram", "dingtalk"]
    assert [item["selected"] for item in body["deliveries"]] == [True, True, False]
    assert [item["reason"] for item in body["deliveries"]] == [
        "policy_selected",
        "policy_selected",
        "policy_skipped_limit",
    ]


def test_alert_manual_send_respects_policy_ordering_and_max_deliveries(
    auth_headers_factory,
    monkeypatch,
) -> None:
    scoped_headers = _scope_headers(auth_headers_factory)
    alert_id = _seed_warning_alert()
    _create_subscriptions(scoped_headers)
    _upsert_warning_policy(scoped_headers)

    adapters = {
        "dingtalk": _FakeAdapter(),
        "telegram": _FakeAdapter(),
        "wecom": _FakeAdapter(),
    }
    monkeypatch.setattr(alert_center_service, "channel_adapter_registry", _FakeAdapterRegistry(adapters))

    send_response = client.post(
        f"/api/alerts/{alert_id}/send",
        json={"note": "manual policy send"},
        headers=scoped_headers,
    )
    assert send_response.status_code == 200
    body = send_response.json()
    assert body["matchedSubscriptions"] == 3
    assert body["selectedSubscriptions"] == 2
    assert body["sent"] == 2
    assert body["failed"] == 0
    assert [item["channel"] for item in body["deliveries"]] == ["wecom", "telegram"]
    assert len(adapters["wecom"].calls) == 1
    assert len(adapters["telegram"].calls) == 1
    assert len(adapters["dingtalk"].calls) == 0


def test_alert_manual_send_without_policy_keeps_matched_equal_selected(
    auth_headers_factory,
    monkeypatch,
) -> None:
    scoped_headers = _scope_headers(auth_headers_factory)
    alert_id = _seed_warning_alert()
    client.post(
        "/api/alerts/subscriptions",
        json={"channel": "telegram", "target": "telegram-room", "severityScope": ["warning"]},
        headers=scoped_headers,
    )
    client.post(
        "/api/alerts/subscriptions",
        json={"channel": "wecom", "target": "wecom-room", "severityScope": ["warning"]},
        headers=scoped_headers,
    )

    adapters = {"telegram": _FakeAdapter(), "wecom": _FakeAdapter()}
    monkeypatch.setattr(alert_center_service, "channel_adapter_registry", _FakeAdapterRegistry(adapters))

    send_response = client.post(
        f"/api/alerts/{alert_id}/send",
        json={"note": "manual no policy"},
        headers=scoped_headers,
    )
    assert send_response.status_code == 200
    body = send_response.json()
    assert body["matchedSubscriptions"] == 2
    assert body["selectedSubscriptions"] == 2
    assert body["sent"] == 2
    assert body["failed"] == 0
    assert [item["channel"] for item in body["deliveries"]] == ["wecom", "telegram"]
