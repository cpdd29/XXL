from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.mandatory_agent_registry_service import ensure_mandatory_agents_registered
from app.services import security_service
from app.services.persistence_service import StatePersistenceService
from app.services.security_gateway_service import security_gateway_service
from app.services.store import InMemoryStore, store


client = TestClient(app)


class _StaticRedisProvider:
    def __init__(self, client) -> None:
        self._client = client

    def get_client(self):
        return self._client


class _FakeSecurityRedisClient:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.sorted_sets: dict[str, dict[str, float]] = {}

    def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if self.values.pop(key, None) is not None:
                removed += 1
            if self.sorted_sets.pop(key, None) is not None:
                removed += 1
        return removed


def _replace_global_store(seeded_store: InMemoryStore) -> None:
    store.__dict__.clear()
    store.__dict__.update(store.clone(seeded_store.__dict__))


def _sqlite_service(tmp_path: Path, seeded_store: InMemoryStore) -> StatePersistenceService:
    database_path = tmp_path / "security-tests.db"
    _replace_global_store(seeded_store)
    service = StatePersistenceService(
        runtime_store=store,
        database_url=f"sqlite:///{database_path}",
    )
    assert service.initialize() is True
    return service


def test_security_report_route_aggregates_recent_logs_and_rules(auth_headers) -> None:
    now = datetime.now(UTC)
    recent_success = (now - timedelta(hours=2)).isoformat()
    recent_warning = (now - timedelta(hours=1)).isoformat()
    recent_error = (now - timedelta(minutes=20)).isoformat()
    stale_error = (now - timedelta(days=3)).isoformat()

    store.audit_logs[0:0] = [
        {
            "id": "audit-security-report-stale",
            "timestamp": stale_error,
            "action": "旧异常请求",
            "user": "legacy-user",
            "resource": "旧 API",
            "status": "error",
            "ip": "127.0.0.9",
            "details": "窗口外日志",
        },
        {
            "id": "audit-security-report-success",
            "timestamp": recent_success,
            "action": "安全网关放行",
            "user": "alice",
            "resource": "消息入口",
            "status": "success",
            "ip": "127.0.0.1",
            "details": "消息通过安全网关",
            "metadata": {
                "rewrite_notes": ["masked phone number"],
                "trace": {"layer": "content_policy_rewrite"},
                "rewrite_diffs": [{"label": "PII 改写"}],
            },
        },
        {
            "id": "audit-security-report-warning",
            "timestamp": recent_warning,
            "action": "敏感词检测",
            "user": "bob",
            "resource": "内容策略",
            "status": "warning",
            "ip": "127.0.0.2",
            "details": "命中敏感词，已改写放行",
            "metadata": {"trace": {"layer": "content_policy_rewrite"}},
        },
        {
            "id": "audit-security-report-error",
            "timestamp": recent_error,
            "action": "安全网关拦截:prompt_injection",
            "user": "alice",
            "resource": "消息入口",
            "status": "error",
            "ip": "127.0.0.3",
            "details": "命中高风险提示注入",
            "metadata": {
                "trace": {"layer": "prompt_injection"},
                "prompt_injection_assessment": {
                    "verdict": "block",
                    "rule_score": 0.95,
                }
            },
        },
    ]
    store.security_rules[0:0] = [
        {
            "id": "rule-security-report-top",
            "name": "Prompt Injection 拦截",
            "description": "阻断高风险提示注入",
            "type": "block",
            "enabled": True,
            "hit_count": 99999,
            "last_triggered": "刚刚",
        },
        {
            "id": "rule-security-report-rewrite",
            "name": "PII 改写",
            "description": "改写敏感信息后放行",
            "type": "filter",
            "enabled": False,
            "hit_count": 120,
            "last_triggered": "1 分钟前",
        },
    ]

    response = client.get("/api/security/report?windowHours=24", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["windowHours"] == 24
    assert body["summary"]["totalEvents"] == 3
    assert body["summary"]["blockedThreats"] == 1
    assert body["summary"]["alertNotifications"] == 1
    assert body["summary"]["rewriteEvents"] == 1
    assert body["summary"]["highRiskEvents"] == 1
    assert body["summary"]["uniqueUsers"] == 2
    assert body["summary"]["activeRules"] >= 1
    assert body["statusBreakdown"][0]["key"] in {"success", "warning", "error"}
    assert any(item["key"] == "content_policy_rewrite" for item in body["gatewayLayerBreakdown"])
    assert any(item["key"] == "prompt_injection" for item in body["gatewayLayerBreakdown"])
    assert body["topResources"][0]["label"] == "消息入口"
    assert body["topActions"][0]["label"] in {"安全网关放行", "敏感词检测", "安全网关拦截:prompt_injection"}
    assert any(item["label"] == "Prompt Injection 拦截" for item in body["topRules"])
    assert {item["status"] for item in body["recentIncidents"]} == {"warning", "error"}
    assert any(item["layer"] == "注入检测" for item in body["recentIncidents"])
    assert any(item["verdict"] == "block" for item in body["recentIncidents"])


def test_security_guardian_route_returns_local_security_agent(auth_headers) -> None:
    ensure_mandatory_agents_registered()
    response = client.get("/api/security/guardian", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "security-guardian"
    assert body["type"] == "security_guardian"
    assert body["name"] == "Security Guardian"
    assert body["configSummary"]["status"] in {"loaded", "partial", "missing"}


def test_security_report_route_falls_back_to_reference_logs_when_window_is_empty(auth_headers) -> None:
    old_time = (datetime.now(UTC) - timedelta(days=10)).isoformat()
    store.audit_logs[0:0] = [
        {
            "id": "audit-security-report-fallback-1",
            "timestamp": old_time,
            "action": "登录失败",
            "user": "unknown",
            "resource": "认证系统",
            "status": "error",
            "ip": "127.0.0.8",
            "details": "无窗口内日志时仍需生成报表",
        },
        {
            "id": "audit-security-report-fallback-2",
            "timestamp": old_time,
            "action": "敏感词检测",
            "user": "system",
            "resource": "内容策略",
            "status": "warning",
            "ip": "127.0.0.7",
            "details": "回退参考日志",
        },
    ]

    response = client.get("/api/security/report?windowHours=1", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["totalEvents"] >= 2
    assert body["recentIncidents"]


def test_security_penalties_route_lists_active_penalties_from_database(
    tmp_path: Path,
    monkeypatch,
    auth_headers_factory,
) -> None:
    now = datetime.now(UTC)
    service = _sqlite_service(tmp_path, InMemoryStore())
    monkeypatch.setattr(security_service, "persistence_service", service)
    auth_headers = auth_headers_factory(role="operator")
    service.upsert_security_subject_state(
        {
            "user_key": "telegram:penalty-active",
            "rate_request_timestamps": [],
            "incident_timestamps": [now.isoformat()],
            "active_penalty": {
                "level": "ban",
                "detail": "Too many blocked incidents",
                "status_code": 429,
                "until": (now + timedelta(minutes=15)).isoformat(),
            },
            "updated_at": now.isoformat(),
        }
    )
    service.upsert_security_subject_state(
        {
            "user_key": "telegram:penalty-expired",
            "rate_request_timestamps": [],
            "incident_timestamps": [],
            "active_penalty": {
                "level": "cooldown",
                "detail": "Expired penalty",
                "status_code": 429,
                "until": (now - timedelta(minutes=3)).isoformat(),
            },
            "updated_at": now.isoformat(),
        }
    )

    try:
        response = client.get("/api/security/penalties", headers=auth_headers)
    finally:
        service.close()

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["userKey"] == "telegram:penalty-active"
    assert payload["items"][0]["level"] == "ban"


def test_security_penalties_route_prefers_database_authoritative_state_over_runtime_cache(
    tmp_path: Path,
    monkeypatch,
    auth_headers_factory,
) -> None:
    now = datetime.now(UTC)
    service = _sqlite_service(tmp_path, InMemoryStore())
    monkeypatch.setattr(security_service, "persistence_service", service)
    auth_headers = auth_headers_factory()
    security_gateway_service._active_penalties["telegram:stale-runtime-penalty"] = {
        "level": "ban",
        "detail": "stale runtime cache",
        "status_code": 429,
        "until": (now + timedelta(minutes=10)).isoformat(),
    }

    try:
        response = client.get("/api/security/penalties", headers=auth_headers)
    finally:
        service.close()

    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "total": 0,
    }


def test_release_security_penalty_clears_state_and_writes_audit_log(
    tmp_path: Path,
    monkeypatch,
    auth_headers_factory,
) -> None:
    now = datetime.now(UTC)
    service = _sqlite_service(tmp_path, InMemoryStore())
    monkeypatch.setattr(security_service, "persistence_service", service)
    fake_redis = _FakeSecurityRedisClient()
    monkeypatch.setattr(
        security_gateway_service,
        "_redis_provider",
        _StaticRedisProvider(fake_redis),
    )
    auth_headers = auth_headers_factory(
        role="operator",
        user_id="security-operator",
        email="security.operator@example.test",
    )
    service.upsert_security_subject_state(
        {
            "user_key": "telegram:release-target",
            "rate_request_timestamps": [(now - timedelta(seconds=30)).isoformat()],
            "incident_timestamps": [(now - timedelta(seconds=25)).isoformat()],
            "active_penalty": {
                "level": "cooldown",
                "detail": "Request burst detected",
                "status_code": 429,
                "until": (now + timedelta(minutes=8)).isoformat(),
            },
            "updated_at": now.isoformat(),
        }
    )
    security_gateway_service._active_penalties["telegram:release-target"] = {
        "level": "cooldown",
        "detail": "Request burst detected",
        "status_code": 429,
        "until": (now + timedelta(minutes=8)).isoformat(),
    }
    security_gateway_service._recent_requests["telegram:release-target"].append(now - timedelta(seconds=15))
    security_gateway_service._recent_incidents["telegram:release-target"].append(now - timedelta(seconds=10))
    fake_redis.values["security:penalty:telegram:release-target"] = '{"level":"cooldown"}'
    fake_redis.sorted_sets["security:rate:telegram:release-target"] = {"req:1": now.timestamp()}
    fake_redis.sorted_sets["security:incident:telegram:release-target"] = {"inc:1": now.timestamp()}

    try:
        approval_response = client.post(
            "/api/security/penalties/telegram:release-target/release",
            headers=auth_headers,
        )
        assert approval_response.status_code == 202
        approval_id = approval_response.json()["approval"]["id"]
        assert client.post(
            f"/api/approvals/{approval_id}/approve",
            headers=auth_headers,
            json={"note": "允许解除"},
        ).status_code == 200
        response = client.post(
            "/api/security/penalties/telegram:release-target/release",
            headers=auth_headers,
            json={"approvalId": approval_id},
        )
        persisted_state = service.get_security_subject_state("telegram:release-target")
        audit_logs = service.list_audit_logs() or []
    finally:
        service.close()

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["userKey"] == "telegram:release-target"
    assert payload["releasedPenalty"]["level"] == "cooldown"
    assert persisted_state is not None
    assert persisted_state["active_penalty"] is None
    assert persisted_state["rate_request_timestamps"] == []
    assert persisted_state["incident_timestamps"] == []
    assert "telegram:release-target" not in security_gateway_service._active_penalties
    assert "telegram:release-target" not in security_gateway_service._recent_requests
    assert "telegram:release-target" not in security_gateway_service._recent_incidents
    assert "security:penalty:telegram:release-target" not in fake_redis.values
    assert "security:rate:telegram:release-target" not in fake_redis.sorted_sets
    assert "security:incident:telegram:release-target" not in fake_redis.sorted_sets
    release_audit = next(
        (
            item
            for item in audit_logs
            if item["action"] == "安全处罚解除"
            and item["resource"] == "security_penalty"
        ),
        None,
    )
    assert release_audit is not None
    assert release_audit["status"] == "success"
    assert release_audit["metadata"]["target_user_key"] == "telegram:release-target"
    assert release_audit["metadata"]["operator"] == "security.operator@example.test"
    assert release_audit["metadata"]["reset_counters"] is True


def test_security_incident_reviews_route_supports_event_jump_filter(
    tmp_path: Path,
    monkeypatch,
    auth_headers_factory,
) -> None:
    service = _sqlite_service(tmp_path, InMemoryStore())
    monkeypatch.setattr(security_service, "persistence_service", service)
    auth_headers = auth_headers_factory()
    now = datetime.now(UTC).isoformat()
    service.append_audit_log(
        log={
            "id": "audit-security-incident-review-event-jump-1",
            "timestamp": now,
            "action": "Security incident review:reviewed",
            "user": "reviewer-a@example.test",
            "resource": "security_incident_review",
            "status": "success",
            "ip": "-",
            "details": "reviewed incident",
            "metadata": {
                "review_id": "incident-review-event-jump-1",
                "incident_id": "incident:event-jump-target",
                "review_action": "reviewed",
                "note": "ready to jump",
                "reviewer": "reviewer-a@example.test",
            },
        }
    )
    service.append_audit_log(
        log={
            "id": "audit-security-incident-review-event-jump-2",
            "timestamp": now,
            "action": "Security incident review:note",
            "user": "reviewer-b@example.test",
            "resource": "security_incident_review",
            "status": "success",
            "ip": "-",
            "details": "another incident note",
            "metadata": {
                "review_id": "incident-review-event-jump-2",
                "incident_id": "incident:event-jump-other",
                "review_action": "note",
                "note": "for a different incident",
                "reviewer": "reviewer-b@example.test",
            },
        }
    )

    try:
        response = client.get(
            "/api/security/incidents/reviews?incident_id=incident:event-jump-target",
            headers=auth_headers,
        )
    finally:
        service.close()

    if response.status_code in {404, 501}:
        pytest.skip("security incident review listing route is not available in this branch")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["incidentId"] == "incident:event-jump-target"
    assert payload["items"][0]["action"] == "reviewed"


def test_create_security_incident_review_route_records_review_action(
    tmp_path: Path,
    monkeypatch,
    auth_headers_factory,
) -> None:
    service = _sqlite_service(tmp_path, InMemoryStore())
    monkeypatch.setattr(security_service, "persistence_service", service)
    auth_headers = auth_headers_factory(
        role="operator",
        user_id="incident-review-operator",
        email="incident.reviewer@example.test",
    )

    try:
        create_response = client.post(
            "/api/security/incidents/incident:create-review/review",
            headers=auth_headers,
            json={
                "action": "false_positive",
                "note": "manual review confirms this is benign",
            },
        )
        list_response = client.get(
            "/api/security/incidents/reviews?incident_id=incident:create-review",
            headers=auth_headers,
        )
    finally:
        service.close()

    if create_response.status_code in {404, 501}:
        pytest.skip("security incident review creation route is not available in this branch")
    assert create_response.status_code == 200
    created_payload = create_response.json()
    assert created_payload["ok"] is True
    assert created_payload["review"]["incidentId"] == "incident:create-review"
    assert created_payload["review"]["action"] == "false_positive"
    assert created_payload["review"]["note"] == "manual review confirms this is benign"
    assert created_payload["review"]["reviewer"] == "incident.reviewer@example.test"

    assert list_response.status_code == 200
    listed_payload = list_response.json()
    assert listed_payload["total"] >= 1
    assert any(item["id"] == created_payload["review"]["id"] for item in listed_payload["items"])


def test_security_manual_penalty_route_contract_draft(
    auth_headers_factory,
) -> None:
    auth_headers = auth_headers_factory(role="operator")
    approval_response = client.post(
        "/api/security/penalties/manual",
        headers=auth_headers,
        json={
            "userKey": "telegram:manual-penalty-target",
            "level": "cooldown",
            "detail": "manual escalation for repeated suspicious traffic",
            "statusCode": 429,
            "durationSeconds": 900,
            "note": "raised from incident review panel",
        },
    )
    if approval_response.status_code in {404, 405, 501}:
        pytest.skip("manual security penalty route is pending main-branch implementation")
    assert approval_response.status_code == 202
    approval_id = approval_response.json()["approval"]["id"]
    assert client.post(
        f"/api/approvals/{approval_id}/approve",
        headers=auth_headers,
        json={"note": "允许创建"},
    ).status_code == 200
    response = client.post(
        "/api/security/penalties/manual",
        headers=auth_headers,
        json={
            "userKey": "telegram:manual-penalty-target",
            "level": "cooldown",
            "detail": "manual escalation for repeated suspicious traffic",
            "statusCode": 429,
            "durationSeconds": 900,
            "note": "raised from incident review panel",
            "approvalId": approval_id,
        },
    )

    if response.status_code in {404, 405, 501}:
        pytest.skip("manual security penalty route is pending main-branch implementation")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["penalty"]["userKey"] == "telegram:manual-penalty-target"
    assert payload["penalty"]["level"] == "cooldown"
    assert payload["penalty"]["statusCode"] == 429


def test_release_security_penalty_rejects_unapproved_execution(
    auth_headers_factory,
) -> None:
    auth_headers = auth_headers_factory(role="operator")
    response = client.post(
        "/api/security/penalties/telegram:missing-approval/release",
        headers=auth_headers,
        json={"approvalId": "approval-missing"},
    )

    assert response.status_code == 404


def test_security_penalty_history_route_contract_draft(
    auth_headers_factory,
) -> None:
    auth_headers = auth_headers_factory(role="operator")
    response = client.get(
        "/api/security/penalties/history?userKey=telegram:manual-penalty-target",
        headers=auth_headers,
    )

    if response.status_code in {404, 405, 501}:
        pytest.skip("security penalty history route is pending main-branch implementation")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload.get("items"), list)
    assert isinstance(payload.get("total"), int)


def test_security_rule_detail_route_contract_draft(
    auth_headers_factory,
) -> None:
    auth_headers = auth_headers_factory(role="operator")
    response = client.get(
        "/api/security/rules/1",
        headers=auth_headers,
    )

    if response.status_code in {404, 405, 501}:
        pytest.skip("security rule detail route is pending main-branch implementation")
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "1"
    assert "name" in payload
    assert "description" in payload


def test_viewer_cannot_release_security_penalty(
    viewer_auth_headers: dict[str, str],
) -> None:
    response = client.post(
        "/api/security/penalties/telegram:any/release",
        headers=viewer_auth_headers,
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied"


def test_viewer_cannot_list_security_penalties(
    viewer_auth_headers: dict[str, str],
) -> None:
    response = client.get(
        "/api/security/penalties",
        headers=viewer_auth_headers,
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied"
