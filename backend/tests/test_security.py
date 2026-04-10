from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
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
            "metadata": {"rewrite_notes": ["masked phone number"]},
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
    assert body["topResources"][0]["label"] == "消息入口"
    assert body["topActions"][0]["label"] in {"安全网关放行", "敏感词检测", "安全网关拦截:prompt_injection"}
    assert any(item["label"] == "Prompt Injection 拦截" for item in body["topRules"])
    assert {item["status"] for item in body["recentIncidents"]} == {"warning", "error"}


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
        response = client.post(
            "/api/security/penalties/telegram:release-target/release",
            headers=auth_headers,
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
