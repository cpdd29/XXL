from fastapi.testclient import TestClient

from app.main import app
from app.services import alert_center_service
from app.services.store import store


client = TestClient(app)


class _FakeAdapter:
    def __init__(self, *, raises: str | None = None) -> None:
        self.raises = raises
        self.calls: list[dict[str, str]] = []

    def send_message(self, *, chat_id: str, text: str) -> dict:
        self.calls.append({"chat_id": chat_id, "text": text})
        if self.raises:
            raise RuntimeError(self.raises)
        return {"ok": True}


class _FakeAdapterRegistry:
    def __init__(self, adapters: dict[str, _FakeAdapter]) -> None:
        self.adapters = adapters

    def get(self, channel: str):
        adapter = self.adapters.get(str(channel))
        if adapter is None:
            raise ValueError(f"Unsupported channel: {channel}")
        return adapter


def test_alert_center_lists_audit_operational_and_runtime_alerts(auth_headers) -> None:
    store.audit_logs = [
        {
            "id": "audit-alert-1",
            "timestamp": "2026-04-13T10:00:00+00:00",
            "action": "安全网关拦截:prompt_injection",
            "user": "telegram:user-1",
            "resource": "security_penalty",
            "status": "error",
            "ip": "127.0.0.1",
            "details": "命中高风险注入",
            "metadata": {"trace": {"layer": "prompt_injection"}},
        }
    ]
    store.workflows = [{"id": "workflow-1", "status": "active"}]
    store.tasks = [
        {
            "id": "task-runtime-alert",
            "status": "failed",
            "tokens": 20,
            "created_at": "2026-04-13T10:00:00+00:00",
            "completed_at": "2026-04-13T10:00:20+00:00",
        }
    ]
    store.workflow_runs = [
        {
            "id": "run-runtime-alert",
            "workflow_id": "workflow-1",
            "workflow_name": "客户服务工作流",
            "task_id": "task-runtime-alert",
            "trigger": "message",
            "intent": "search",
            "status": "failed",
            "created_at": "2026-04-13T10:00:00+00:00",
            "updated_at": "2026-04-13T10:00:20+00:00",
            "started_at": "2026-04-13T10:00:00+00:00",
            "completed_at": "2026-04-13T10:00:20+00:00",
            "dispatch_context": {
                "state": "execution_timeout",
                "failure_stage": "execution",
                "run_metrics": {"tokens_total": 20, "duration_ms": 20_000, "step_count": 2},
                "fallback_history": [{"id": "fallback-1", "reason": "execution_timeout"}],
            },
        }
    ]
    store.operational_logs = [
        {
        "id": "op-alert-1",
        "timestamp": "2026-04-13T10:01:00+00:00",
        "type": "warning",
        "agent": "Workflow Runtime",
        "message": "Dispatch lease is close to expiry",
        "source": "runtime",
        "workflow_run_id": "run-runtime-alert",
        }
    ]
    store.realtime_logs = []

    response = client.get("/api/alerts", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 2
    ids = {item["id"] for item in body["items"]}
    assert "audit:audit-alert-1" in ids
    assert any(item_id.startswith("runtime:") for item_id in ids)


def test_alert_center_can_acknowledge_resolve_and_suppress(auth_headers_factory) -> None:
    headers = auth_headers_factory(role="operator", email="ops@example.test")
    store.audit_logs = [
        {
            "id": "audit-alert-2",
            "timestamp": "2026-04-13T09:00:00+00:00",
            "action": "安全网关拦截:prompt_injection",
            "user": "telegram:user-2",
            "resource": "security_penalty",
            "status": "warning",
            "ip": "127.0.0.1",
            "details": "命中可疑注入",
            "metadata": {"trace": {"layer": "prompt_injection"}},
        }
    ]

    ack = client.post(
        "/api/alerts/audit:audit-alert-2/ack",
        json={"note": "已人工确认"},
        headers=headers,
    )
    assert ack.status_code == 200
    assert ack.json()["alert"]["status"] == "acknowledged"

    resolve = client.post(
        "/api/alerts/audit:audit-alert-2/resolve",
        json={"note": "已处理"},
        headers=headers,
    )
    assert resolve.status_code == 200
    assert resolve.json()["alert"]["status"] == "resolved"

    suppress = client.post(
        "/api/alerts/audit:audit-alert-2/suppress",
        json={"durationMinutes": 30, "note": "半小时静默"},
        headers=headers,
    )
    assert suppress.status_code == 200
    assert suppress.json()["alert"]["status"] == "suppressed"
    assert suppress.json()["alert"]["suppressedUntil"] is not None


def test_alert_center_aggregates_duplicate_alerts_and_applies_suppression(auth_headers_factory) -> None:
    headers = auth_headers_factory(role="operator", email="ops@example.test")
    store.audit_logs = [
        {
            "id": "audit-agg-1",
            "timestamp": "2026-04-13T09:00:00+00:00",
            "action": "安全网关拦截:prompt_injection",
            "user": "telegram:user-agg",
            "resource": "security_penalty",
            "status": "warning",
            "ip": "127.0.0.1",
            "details": "命中可疑注入",
            "metadata": {"trace": {"layer": "prompt_injection"}},
        },
        {
            "id": "audit-agg-2",
            "timestamp": "2026-04-13T09:10:00+00:00",
            "action": "安全网关拦截:prompt_injection",
            "user": "telegram:user-agg",
            "resource": "security_penalty",
            "status": "error",
            "ip": "127.0.0.1",
            "details": "再次命中高风险注入",
            "metadata": {"trace": {"layer": "prompt_injection"}},
        },
    ]

    response = client.get("/api/alerts", headers=headers)
    assert response.status_code == 200
    body = response.json()
    aggregate = next(item for item in body["items"] if item["source"] == "security")
    assert aggregate["aggregateCount"] == 2
    assert aggregate["dedupeKey"]
    assert aggregate["aggregateStrategy"] == "resource_actor_window"
    assert aggregate["severity"] == "critical"

    suppress = client.post(
        f"/api/alerts/{aggregate['id']}/suppress",
        json={"durationMinutes": 45, "note": "聚合静默"},
        headers=headers,
    )
    assert suppress.status_code == 200
    suppressed_alert = suppress.json()["alert"]
    assert suppressed_alert["status"] == "suppressed"
    assert suppressed_alert["suppressedUntil"] is not None

    follow_up = client.get("/api/alerts", headers=headers)
    assert follow_up.status_code == 200
    aggregate_after = next(item for item in follow_up.json()["items"] if item["dedupeKey"] == aggregate["dedupeKey"])
    assert aggregate_after["status"] == "suppressed"
    assert aggregate_after["aggregateCount"] == 2


def test_alert_center_write_requires_permission(auth_headers_factory) -> None:
    store.audit_logs = [
        {
            "id": "audit-alert-3",
            "timestamp": "2026-04-13T09:00:00+00:00",
            "action": "安全网关拦截:prompt_injection",
            "user": "telegram:user-3",
            "resource": "security_penalty",
            "status": "warning",
            "ip": "127.0.0.1",
            "details": "命中可疑注入",
            "metadata": {"trace": {"layer": "prompt_injection"}},
        }
    ]

    read_response = client.get(
        "/api/alerts",
        headers=auth_headers_factory(role="viewer", email="viewer@example.test"),
    )
    assert read_response.status_code == 200

    write_response = client.post(
        "/api/alerts/audit:audit-alert-3/ack",
        json={"note": "viewer should fail"},
        headers=auth_headers_factory(role="viewer", email="viewer@example.test"),
    )
    assert write_response.status_code == 403


def test_alert_subscriptions_list_create_update_and_permissions(auth_headers_factory) -> None:
    operator_headers = auth_headers_factory(role="operator", email="ops@example.test")
    viewer_headers = auth_headers_factory(role="viewer", email="viewer@example.test")

    create_response = client.post(
        "/api/alerts/subscriptions",
        json={
            "channel": "telegram",
            "target": "chat-1",
            "enabled": True,
            "severityScope": ["warning", "critical"],
        },
        headers=operator_headers,
    )
    assert create_response.status_code == 200
    subscription = create_response.json()["subscription"]
    assert subscription["channel"] == "telegram"
    assert subscription["target"] == "chat-1"

    list_response = client.get("/api/alerts/subscriptions", headers=viewer_headers)
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1

    update_response = client.patch(
        f"/api/alerts/subscriptions/{subscription['id']}",
        json={"enabled": False, "target": "chat-2", "severityScope": ["critical"]},
        headers=operator_headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["subscription"]["enabled"] is False
    assert update_response.json()["subscription"]["target"] == "chat-2"
    assert update_response.json()["subscription"]["severityScope"] == ["critical"]

    forbidden_create = client.post(
        "/api/alerts/subscriptions",
        json={"channel": "wecom", "target": "session-1"},
        headers=viewer_headers,
    )
    assert forbidden_create.status_code == 403


def test_alert_manual_send_routes_to_matching_subscriptions_with_fake_adapter(
    auth_headers_factory,
    monkeypatch,
) -> None:
    operator_headers = auth_headers_factory(role="operator", email="ops@example.test")
    store.audit_logs = [
        {
            "id": "audit-send-1",
            "timestamp": "2026-04-13T09:00:00+00:00",
            "action": "安全网关拦截:prompt_injection",
            "user": "telegram:user-send",
            "resource": "security_penalty",
            "status": "warning",
            "ip": "127.0.0.1",
            "details": "命中可疑注入",
            "metadata": {"trace": {"layer": "prompt_injection"}},
        }
    ]
    client.post(
        "/api/alerts/subscriptions",
        json={
            "channel": "telegram",
            "target": "chat-send-1",
            "enabled": True,
            "severityScope": ["warning"],
        },
        headers=operator_headers,
    )
    client.post(
        "/api/alerts/subscriptions",
        json={
            "channel": "wecom",
            "target": "session-not-match",
            "enabled": True,
            "severityScope": ["critical"],
        },
        headers=operator_headers,
    )
    telegram_adapter = _FakeAdapter()
    monkeypatch.setattr(
        alert_center_service,
        "channel_adapter_registry",
        _FakeAdapterRegistry({"telegram": telegram_adapter}),
    )

    send_response = client.post(
        "/api/alerts/audit:audit-send-1/send",
        json={"note": "manual trigger"},
        headers=operator_headers,
    )
    assert send_response.status_code == 200
    body = send_response.json()
    assert body["matchedSubscriptions"] == 1
    assert body["sent"] == 1
    assert body["failed"] == 0
    assert len(telegram_adapter.calls) == 1
    assert telegram_adapter.calls[0]["chat_id"] == "chat-send-1"


def test_alert_manual_send_failure_and_permission(auth_headers_factory, monkeypatch) -> None:
    operator_headers = auth_headers_factory(role="operator", email="ops@example.test")
    viewer_headers = auth_headers_factory(role="viewer", email="viewer@example.test")
    store.audit_logs = [
        {
            "id": "audit-send-2",
            "timestamp": "2026-04-13T09:00:00+00:00",
            "action": "安全网关拦截:prompt_injection",
            "user": "telegram:user-send",
            "resource": "security_penalty",
            "status": "error",
            "ip": "127.0.0.1",
            "details": "命中高风险注入",
            "metadata": {"trace": {"layer": "prompt_injection"}},
        }
    ]
    client.post(
        "/api/alerts/subscriptions",
        json={
            "channel": "telegram",
            "target": "chat-send-2",
            "enabled": True,
            "severityScope": ["critical"],
        },
        headers=operator_headers,
    )
    monkeypatch.setattr(
        alert_center_service,
        "channel_adapter_registry",
        _FakeAdapterRegistry({"telegram": _FakeAdapter(raises="network down")}),
    )

    send_response = client.post(
        "/api/alerts/audit:audit-send-2/send",
        headers=operator_headers,
    )
    assert send_response.status_code == 200
    body = send_response.json()
    assert body["matchedSubscriptions"] == 1
    assert body["sent"] == 0
    assert body["failed"] == 1
    assert body["deliveries"][0]["status"] == "failed"

    forbidden_send = client.post(
        "/api/alerts/audit:audit-send-2/send",
        headers=viewer_headers,
    )
    assert forbidden_send.status_code == 403


def test_alert_subscriptions_and_manual_send_respect_scope_headers(
    auth_headers_factory,
    monkeypatch,
) -> None:
    scoped_headers = {
        **auth_headers_factory(role="operator", email="ops@example.test"),
        "X-WorkBot-Tenant-Id": "tenant-a",
        "X-WorkBot-Project-Id": "project-a",
        "X-WorkBot-Environment": "prod",
    }
    other_scope_headers = {
        **auth_headers_factory(role="operator", email="ops@example.test"),
        "X-WorkBot-Tenant-Id": "tenant-b",
        "X-WorkBot-Project-Id": "project-a",
        "X-WorkBot-Environment": "prod",
    }
    store.audit_logs = [
        {
            "id": "audit-send-scope",
            "timestamp": "2026-04-13T09:00:00+00:00",
            "action": "安全网关拦截:prompt_injection",
            "user": "telegram:user-scope",
            "resource": "security_penalty",
            "status": "warning",
            "ip": "127.0.0.1",
            "details": "命中可疑注入",
            "metadata": {
                "trace": {"layer": "prompt_injection"},
                "scope": {
                    "tenant_id": "tenant-a",
                    "project_id": "project-a",
                    "environment": "prod",
                },
            },
        }
    ]
    create = client.post(
        "/api/alerts/subscriptions",
        json={
            "channel": "telegram",
            "target": "tenant-a-chat",
            "enabled": True,
            "severityScope": ["warning"],
        },
        headers=scoped_headers,
    )
    assert create.status_code == 200

    scoped_list = client.get("/api/alerts/subscriptions", headers=scoped_headers)
    assert scoped_list.status_code == 200
    assert scoped_list.json()["total"] == 1

    other_scope_list = client.get("/api/alerts/subscriptions", headers=other_scope_headers)
    assert other_scope_list.status_code == 200
    assert other_scope_list.json()["total"] == 0

    telegram_adapter = _FakeAdapter()
    monkeypatch.setattr(
        alert_center_service,
        "channel_adapter_registry",
        _FakeAdapterRegistry({"telegram": telegram_adapter}),
    )

    wrong_scope_send = client.post(
        "/api/alerts/audit:audit-send-scope/send",
        headers=other_scope_headers,
    )
    assert wrong_scope_send.status_code == 404

    matched_scope_send = client.post(
        "/api/alerts/audit:audit-send-scope/send",
        headers=scoped_headers,
    )
    assert matched_scope_send.status_code == 200
    assert matched_scope_send.json()["matchedSubscriptions"] == 1
    assert len(telegram_adapter.calls) == 1
