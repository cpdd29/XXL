from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services import dashboard_service
from app.services.persistence_service import StatePersistenceService
from app.services.store import InMemoryStore, store


client = TestClient(app)


def _sqlite_service(tmp_path: Path, seeded_store: InMemoryStore) -> StatePersistenceService:
    database_path = tmp_path / "dashboard-logs.db"
    service = StatePersistenceService(
        runtime_store=seeded_store,
        database_url=f"sqlite:///{database_path}",
    )
    assert service.initialize() is True
    return service


def test_dashboard_logs_support_server_side_filters_and_pagination(auth_headers) -> None:
    store.audit_logs = [
        {
            "id": "log-1",
            "timestamp": "2026-04-03 10:00:00",
            "action": "安全告警",
            "user": "system",
            "resource": "API 网关",
            "status": "warning",
            "ip": "127.0.0.1",
            "details": "命中第一条告警规则",
        },
        {
            "id": "log-2",
            "timestamp": "2026-04-03 09:58:00",
            "action": "安全告警",
            "user": "system",
            "resource": "安全中心",
            "status": "warning",
            "ip": "127.0.0.2",
            "details": "命中第二条告警规则",
        },
        {
            "id": "log-3",
            "timestamp": "2026-04-03 09:50:00",
            "action": "用户登录",
            "user": "alice",
            "resource": "认证系统",
            "status": "success",
            "ip": "127.0.0.3",
            "details": "管理员登录成功",
        },
    ]

    first_page = client.get(
        "/api/dashboard/logs",
        params={
            "search": "告警",
            "status": "warning",
            "user": "system",
            "limit": 1,
            "offset": 0,
        },
        headers=auth_headers,
    )
    second_page = client.get(
        "/api/dashboard/logs",
        params={
            "search": "告警",
            "status": "warning",
            "user": "system",
            "limit": 1,
            "offset": 1,
        },
        headers=auth_headers,
    )
    resource_filtered = client.get(
        "/api/dashboard/logs",
        params={
            "resource": "认证",
            "limit": 10,
            "offset": 0,
        },
        headers=auth_headers,
    )

    assert first_page.status_code == 200
    assert second_page.status_code == 200
    assert resource_filtered.status_code == 200

    first_body = first_page.json()
    second_body = second_page.json()
    resource_body = resource_filtered.json()

    assert first_body["total"] == 2
    assert first_body["limit"] == 1
    assert first_body["offset"] == 0
    assert first_body["hasMore"] is True
    assert [item["id"] for item in first_body["items"]] == ["log-1"]

    assert second_body["total"] == 2
    assert second_body["offset"] == 1
    assert second_body["hasMore"] is False
    assert [item["id"] for item in second_body["items"]] == ["log-2"]

    assert resource_body["total"] == 1
    assert [item["id"] for item in resource_body["items"]] == ["log-3"]


def test_dashboard_logs_prefer_database_reads_over_runtime_store(
    tmp_path: Path,
    monkeypatch,
    auth_headers,
) -> None:
    seeded_store = InMemoryStore()
    seeded_store.audit_logs = [
        {
            "id": "db-log-1",
            "timestamp": "2026-04-03 11:00:00",
            "action": "数据库告警",
            "user": "system",
            "resource": "数据库审计",
            "status": "warning",
            "ip": "10.0.0.1",
            "details": "应优先从数据库读取",
            "metadata": {"trace": {"trace_id": "trace-db-log-1"}},
        }
    ]

    service = _sqlite_service(tmp_path, seeded_store)
    monkeypatch.setattr(dashboard_service, "persistence_service", service)

    store.audit_logs = [
        {
            "id": "store-log-1",
            "timestamp": "2026-04-03 12:00:00",
            "action": "内存告警",
            "user": "store-user",
            "resource": "内存审计",
            "status": "error",
            "ip": "10.0.0.2",
            "details": "不应被优先返回",
        }
    ]

    try:
        response = client.get(
            "/api/dashboard/logs",
            params={"search": "数据库"},
            headers=auth_headers,
        )
    finally:
        service.close()

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["hasMore"] is False
    assert [item["id"] for item in body["items"]] == ["db-log-1"]
    assert body["items"][0]["metadata"]["trace"]["trace_id"] == "trace-db-log-1"


def test_dashboard_logs_export_returns_filtered_csv(auth_headers) -> None:
    store.audit_logs = [
        {
            "id": "log-export-1",
            "timestamp": "2026-04-03 10:00:00",
            "action": "安全告警",
            "user": "system",
            "resource": "API 网关",
            "status": "warning",
            "ip": "127.0.0.1",
            "details": "命中第一条告警规则",
        },
        {
            "id": "log-export-2",
            "timestamp": "2026-04-03 09:50:00",
            "action": "用户登录",
            "user": "alice",
            "resource": "认证系统",
            "status": "success",
            "ip": "127.0.0.2",
            "details": "管理员登录成功",
        },
    ]

    response = client.get(
        "/api/dashboard/logs/export",
        params={
            "status": "warning",
            "user": "system",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "attachment;" in response.headers["content-disposition"]
    text = response.text
    assert "时间,动作,用户,资源,状态,IP,详情" in text
    assert "安全告警" in text
    assert "命中第一条告警规则" in text
    assert "用户登录" not in text


def test_dashboard_logs_export_prefers_database_reads_over_runtime_store(
    tmp_path: Path,
    monkeypatch,
    auth_headers,
) -> None:
    seeded_store = InMemoryStore()
    seeded_store.audit_logs = [
        {
            "id": "db-log-export-1",
            "timestamp": "2026-04-03 11:00:00",
            "action": "数据库导出告警",
            "user": "system",
            "resource": "数据库审计",
            "status": "warning",
            "ip": "10.0.0.1",
            "details": "导出应优先读取数据库日志",
        }
    ]

    service = _sqlite_service(tmp_path, seeded_store)
    monkeypatch.setattr(dashboard_service, "persistence_service", service)
    store.audit_logs = [
        {
            "id": "store-log-export-1",
            "timestamp": "2026-04-03 12:00:00",
            "action": "内存导出告警",
            "user": "store-user",
            "resource": "内存审计",
            "status": "error",
            "ip": "10.0.0.2",
            "details": "不应被导出",
        }
    ]

    try:
        response = client.get(
            "/api/dashboard/logs/export",
            params={"search": "数据库导出"},
            headers=auth_headers,
        )
    finally:
        service.close()

    assert response.status_code == 200
    text = response.text
    assert "数据库导出告警" in text
    assert "导出应优先读取数据库日志" in text
    assert "内存导出告警" not in text
