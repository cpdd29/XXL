from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.models import UserProfileRecord, UserRecord
from app.main import app
import app.modules.organization.application.profile_service as profile_service
import app.platform.auth.auth_service as auth_service
from app.platform.persistence.persistence_service import StatePersistenceService
from app.platform.persistence.runtime_store import InMemoryStore, store


client = TestClient(app)


def _replace_global_store(seeded_store: InMemoryStore) -> None:
    store.__dict__.clear()
    store.__dict__.update(store.clone(seeded_store.__dict__))


def _sqlite_service(tmp_path: Path, seeded_store: InMemoryStore) -> StatePersistenceService:
    database_path = tmp_path / "auth-tests.db"
    _replace_global_store(seeded_store)
    service = StatePersistenceService(
        runtime_store=store,
        database_url=f"sqlite:///{database_path}",
    )
    assert service.initialize() is True
    return service


def _bind_persistence_services(monkeypatch, service: StatePersistenceService) -> None:
    monkeypatch.setattr(auth_service, "persistence_service", service)
    monkeypatch.setattr(profile_service, "persistence_service", service)


def _demo_admin_actor() -> dict[str, str]:
    return {
        "id": "admin-1",
        "name": "管理员",
        "email": "admin@workbot.ai",
        "role": "admin",
        "status": "active",
    }


def test_login_prefers_database_user_over_demo_fallback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    seeded_store = InMemoryStore()
    seeded_store.users = [
        {
            "id": "db-admin",
            "name": "数据库管理员",
            "email": "admin@workbot.ai",
            "role": "admin",
            "status": "active",
            "last_login": "2026-04-03T09:30:00+00:00",
            "total_interactions": 88,
            "created_at": "2026-04-01",
        }
    ]
    seeded_store.user_profiles = {
        "db-admin": {
            **seeded_store.users[0],
            "tags": ["数据库"],
            "notes": "数据库管理员画像",
            "preferred_language": "zh",
            "source_channels": ["console"],
            **auth_service.build_password_record("db-only-password"),
        }
    }

    service = _sqlite_service(tmp_path, seeded_store)
    _bind_persistence_services(monkeypatch, service)

    try:
        payload = auth_service.login("admin@workbot.ai", "db-only-password")
        persisted_user = service.get_user("db-admin")
        audit_logs = service.list_audit_logs()
    finally:
        service.close()

    assert payload["user"]["id"] == "db-admin"
    assert payload["user"]["name"] == "数据库管理员"
    assert payload["access_token"].count(".") == 2
    assert persisted_user is not None
    assert persisted_user["last_login"] != "2026-04-03T09:30:00+00:00"
    assert audit_logs is not None
    assert audit_logs[0]["action"] == "用户登录"
    assert audit_logs[0]["status"] == "success"


def test_login_falls_back_to_demo_admin_without_creating_visible_profile_or_tenant_data(
    tmp_path: Path,
    monkeypatch,
) -> None:
    seeded_store = InMemoryStore()
    seeded_store.users = []
    seeded_store.user_profiles = {}

    service = _sqlite_service(tmp_path, seeded_store)
    _bind_persistence_services(monkeypatch, service)

    try:
        payload = auth_service.login("admin@workbot.ai", "workbot123")
        persisted_user = service.get_user_by_email("admin@workbot.ai")
        persisted_profile = service.get_user_profile("admin-1")
        visible_profiles = profile_service.list_profiles(current_user=_demo_admin_actor())
        visible_tenants = profile_service.list_profile_tenants(
            _demo_admin_actor(),
            management_view=True,
        )
    finally:
        service.close()

    assert payload["user"]["email"] == "admin@workbot.ai"
    assert payload["user"]["role"] == "admin"
    assert persisted_user is not None
    assert persisted_user["email"] == "admin@workbot.ai"
    assert persisted_user["status"] == "active"
    assert persisted_profile is None
    assert "admin-1" not in store.user_profiles
    assert visible_profiles["total"] == 0
    assert visible_tenants["total"] == 0


def test_login_rejects_invalid_password_for_existing_database_user(
    tmp_path: Path,
    monkeypatch,
) -> None:
    seeded_store = InMemoryStore()
    seeded_store.users = [
        {
            "id": "db-admin",
            "name": "数据库管理员",
            "email": "admin@workbot.ai",
            "role": "admin",
            "status": "active",
            "last_login": "2026-04-03T09:30:00+00:00",
            "total_interactions": 88,
            "created_at": "2026-04-01",
        }
    ]
    seeded_store.user_profiles = {
        "db-admin": {
            **seeded_store.users[0],
            "tags": ["数据库"],
            "notes": "数据库管理员画像",
            "preferred_language": "zh",
            "source_channels": ["console"],
            **auth_service.build_password_record("db-only-password"),
        }
    }

    service = _sqlite_service(tmp_path, seeded_store)
    _bind_persistence_services(monkeypatch, service)

    try:
        with pytest.raises(HTTPException) as exc_info:
            auth_service.login("admin@workbot.ai", "wrong-password")
        audit_logs = service.list_audit_logs()
    finally:
        service.close()

    assert exc_info.value.status_code == 401
    assert audit_logs is not None
    assert audit_logs[0]["action"] == "登录失败"
    assert audit_logs[0]["status"] == "error"


def test_login_rejects_demo_password_for_existing_database_user_without_profile(
    tmp_path: Path,
    monkeypatch,
) -> None:
    seeded_store = InMemoryStore()
    seeded_store.users = [
        {
            "id": "db-admin-real",
            "name": "数据库管理员",
            "email": "admin@workbot.ai",
            "role": "admin",
            "status": "active",
            "last_login": "2026-04-03T09:30:00+00:00",
            "total_interactions": 88,
            "created_at": "2026-04-01",
        }
    ]
    seeded_store.user_profiles = {}

    service = _sqlite_service(tmp_path, seeded_store)
    _bind_persistence_services(monkeypatch, service)

    try:
        with pytest.raises(HTTPException) as exc_info:
            auth_service.login("admin@workbot.ai", "workbot123")
        persisted_profile = service.get_user_profile("db-admin-real")
        audit_logs = service.list_audit_logs()
    finally:
        service.close()

    assert exc_info.value.status_code == 401
    assert persisted_profile is None
    assert audit_logs is not None
    assert audit_logs[0]["action"] == "登录失败"
    assert audit_logs[0]["status"] == "error"


def test_login_keeps_default_demo_admin_user_without_profile_when_database_only_has_user(
    tmp_path: Path,
    monkeypatch,
) -> None:
    seeded_store = InMemoryStore()
    seeded_store.users = [
        {
            "id": "admin-1",
            "name": "管理员",
            "email": "admin@workbot.ai",
            "role": "admin",
            "status": "active",
            "last_login": "",
            "total_interactions": 0,
            "created_at": "2026-04-01",
        }
    ]
    seeded_store.user_profiles = {}

    service = _sqlite_service(tmp_path, seeded_store)
    _bind_persistence_services(monkeypatch, service)

    try:
        payload = auth_service.login("admin@workbot.ai", "workbot123")
        persisted_profile = service.get_user_profile("admin-1")
        visible_profiles = profile_service.list_profiles(current_user=_demo_admin_actor())
        visible_tenants = profile_service.list_profile_tenants(
            _demo_admin_actor(),
            management_view=True,
        )
    finally:
        service.close()

    assert payload["user"]["id"] == "admin-1"
    assert persisted_profile is None
    assert "admin-1" not in store.user_profiles
    assert visible_profiles["total"] == 0
    assert visible_tenants["total"] == 0


def test_login_hides_existing_default_demo_admin_profile_from_profile_and_tenant_views(
    tmp_path: Path,
    monkeypatch,
) -> None:
    seeded_store = InMemoryStore()
    seeded_store.users = [
        {
            "id": "admin-1",
            "name": "管理员",
            "email": "admin@workbot.ai",
            "role": "admin",
            "status": "active",
            "last_login": "",
            "total_interactions": 0,
            "created_at": "2026-04-01",
        }
    ]
    seeded_store.user_profiles = {
        "admin-1": {
            **seeded_store.users[0],
            "tenant_id": "default",
            "tenant_name": "默认租户",
            "tags": ["系统管理员", "控制台入口"],
            "notes": "旧版 demo admin 画像。",
            "preferred_language": "zh",
            "source_channels": ["console"],
            "platform_accounts": [{"platform": "console", "account_id": "admin-1"}],
            **auth_service.build_password_record("workbot123"),
        }
    }

    service = _sqlite_service(tmp_path, seeded_store)
    _bind_persistence_services(monkeypatch, service)

    try:
        payload = auth_service.login("admin@workbot.ai", "workbot123")
        persisted_profile = service.get_user_profile("admin-1")
        visible_profiles = profile_service.list_profiles(current_user=_demo_admin_actor())
        visible_tenants = profile_service.list_profile_tenants(
            _demo_admin_actor(),
            management_view=True,
        )
    finally:
        service.close()

    assert payload["user"]["id"] == "admin-1"
    assert persisted_profile is None
    assert "admin-1" not in store.user_profiles
    assert visible_profiles["total"] == 0
    assert visible_tenants["total"] == 0


def test_login_accepts_password_only_demo_admin_profile_without_exposing_visible_data(
    tmp_path: Path,
    monkeypatch,
) -> None:
    seeded_store = InMemoryStore()
    seeded_store.users = [
        {
            "id": "admin-1",
            "name": "管理员",
            "email": "admin@workbot.ai",
            "role": "admin",
            "status": "active",
            "last_login": "",
            "total_interactions": 0,
            "created_at": "2026-04-01",
        }
    ]
    seeded_store.user_profiles = {
        "admin-1": {
            "id": "admin-1",
            "user_id": "admin-1",
            **auth_service.build_password_record("workbot123"),
        }
    }

    service = _sqlite_service(tmp_path, seeded_store)
    _bind_persistence_services(monkeypatch, service)

    try:
        payload = auth_service.login("admin@workbot.ai", "workbot123")
        persisted_profile = service.get_user_profile("admin-1")
        visible_profiles = profile_service.list_profiles(current_user=_demo_admin_actor())
        visible_tenants = profile_service.list_profile_tenants(
            _demo_admin_actor(),
            management_view=True,
        )
    finally:
        service.close()

    assert payload["user"]["id"] == "admin-1"
    assert persisted_profile is None
    assert "admin-1" not in store.user_profiles
    assert visible_profiles["total"] == 0
    assert visible_tenants["total"] == 0


def test_login_rejects_stale_runtime_user_when_database_is_enabled_but_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = _sqlite_service(tmp_path, InMemoryStore())
    _bind_persistence_services(monkeypatch, service)

    store.users = [
        {
            "id": "runtime-only-user",
            "name": "旧缓存用户",
            "email": "runtime-only@example.com",
            "role": "admin",
            "status": "active",
            "last_login": "2026-04-03T09:30:00+00:00",
            "total_interactions": 9,
            "created_at": "2026-04-01",
        }
    ]
    store.user_profiles = {
        "runtime-only-user": {
            **store.users[0],
            "tags": ["runtime-only"],
            "notes": "仅存在于运行时缓存中。",
            "preferred_language": "zh",
            "source_channels": ["console"],
            **auth_service.build_password_record("runtime-password"),
        }
    }

    try:
        with pytest.raises(HTTPException) as exc_info:
            auth_service.login("runtime-only@example.com", "runtime-password")
    finally:
        service.close()

    assert exc_info.value.status_code == 401


def test_refresh_and_authenticate_reject_deleted_database_user_even_if_runtime_cache_is_stale(
    tmp_path: Path,
    monkeypatch,
) -> None:
    seeded_store = InMemoryStore()
    seeded_store.users = [
        {
            "id": "db-admin",
            "name": "数据库管理员",
            "email": "admin@workbot.ai",
            "role": "admin",
            "status": "active",
            "last_login": "2026-04-03T09:30:00+00:00",
            "total_interactions": 88,
            "created_at": "2026-04-01",
        }
    ]
    seeded_store.user_profiles = {
        "db-admin": {
            **seeded_store.users[0],
            "tags": ["数据库"],
            "notes": "数据库管理员画像",
            "preferred_language": "zh",
            "source_channels": ["console"],
            **auth_service.build_password_record("db-only-password"),
        }
    }

    service = _sqlite_service(tmp_path, seeded_store)
    _bind_persistence_services(monkeypatch, service)

    try:
        login_payload = auth_service.login("admin@workbot.ai", "db-only-password")

        assert service._session_factory is not None
        with service._session_factory() as session:
            session.execute(delete(UserProfileRecord).where(UserProfileRecord.user_id == "db-admin"))
            session.execute(delete(UserRecord).where(UserRecord.id == "db-admin"))
            session.commit()

        with pytest.raises(HTTPException) as refresh_exc:
            auth_service.refresh(login_payload["refresh_token"])
        with pytest.raises(HTTPException) as access_exc:
            auth_service.authenticate_access_token(login_payload["access_token"])
    finally:
        service.close()

    assert refresh_exc.value.status_code == 401
    assert access_exc.value.status_code == 401


def test_auth_login_route_preserves_response_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = _sqlite_service(tmp_path, InMemoryStore())
    _bind_persistence_services(monkeypatch, service)

    try:
        response = client.post(
            "/api/auth/login",
            json={"email": "admin@workbot.ai", "password": "workbot123"},
        )
    finally:
        service.close()

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"accessToken", "refreshToken", "expiresIn", "user"}
    assert payload["accessToken"]
    assert payload["refreshToken"]
    assert payload["expiresIn"] > 0
    assert set(payload["user"]) == {"id", "name", "email", "role"}


def test_auth_refresh_route_returns_new_token_pair(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = _sqlite_service(tmp_path, InMemoryStore())
    _bind_persistence_services(monkeypatch, service)

    try:
        login_response = client.post(
            "/api/auth/login",
            json={"email": "admin@workbot.ai", "password": "workbot123"},
        )
        refresh_response = client.post(
            "/api/auth/refresh",
            json={"refreshToken": login_response.json()["refreshToken"]},
        )
    finally:
        service.close()

    assert login_response.status_code == 200
    assert refresh_response.status_code == 200
    payload = refresh_response.json()
    assert payload["accessToken"]
    assert payload["refreshToken"]
    assert payload["user"]["email"] == "admin@workbot.ai"


def test_auth_session_route_returns_permission_snapshot(auth_headers_factory) -> None:
    response = client.get(
        "/api/auth/session",
        headers=auth_headers_factory(role="operator", email="ops@example.com"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["email"] == "ops@example.com"
    assert payload["roleSummary"]["key"] == "operator"
    assert "settings:agent-api:write" in payload["permissions"]
    assert "settings:security-policy:write" in payload["permissions"]
    assert any(group["key"] == "security" for group in payload["permissionGroups"])


def test_login_fails_closed_when_database_user_lookup_is_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = _sqlite_service(tmp_path, InMemoryStore())
    _bind_persistence_services(monkeypatch, service)
    monkeypatch.setattr(service, "get_user_by_email", lambda email: None)
    monkeypatch.setattr(service, "list_users", lambda *, search=None: None)

    store.users = [
        {
            "id": "runtime-auth-unavailable-login",
            "name": "Runtime Login",
            "email": "runtime-login@example.com",
            "role": "admin",
            "status": "active",
            "last_login": "2026-04-03T09:30:00+00:00",
            "total_interactions": 9,
            "created_at": "2026-04-01",
        }
    ]
    store.user_profiles = {
        "runtime-auth-unavailable-login": {
            **store.users[0],
            "tags": ["runtime-only"],
            "notes": "数据库不可用时不应继续放行 runtime 用户。",
            "preferred_language": "zh",
            "source_channels": ["console"],
            **auth_service.build_password_record("runtime-password"),
        }
    }

    try:
        with pytest.raises(HTTPException) as exc_info:
            auth_service.login("runtime-login@example.com", "runtime-password")
    finally:
        service.close()

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Authentication service temporarily unavailable"


def test_refresh_fails_closed_when_database_user_lookup_is_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = _sqlite_service(tmp_path, InMemoryStore())
    _bind_persistence_services(monkeypatch, service)
    monkeypatch.setattr(service, "get_user", lambda user_id: None)
    monkeypatch.setattr(service, "list_users", lambda *, search=None: None)

    runtime_user = {
        "id": "runtime-auth-unavailable-refresh",
        "name": "Runtime Refresh",
        "email": "runtime-refresh@example.com",
        "role": "admin",
        "status": "active",
        "last_login": "2026-04-03T09:30:00+00:00",
        "total_interactions": 9,
        "created_at": "2026-04-01",
    }
    store.users = [runtime_user]
    store.user_profiles = {
        runtime_user["id"]: {
            **runtime_user,
            "tags": ["runtime-only"],
            "notes": "数据库不可用时不应继续放行 runtime 用户。",
            "preferred_language": "zh",
            "source_channels": ["console"],
            **auth_service.build_password_record("runtime-password"),
        }
    }
    refresh_token = auth_service._issue_token_pair(runtime_user)["refresh_token"]

    try:
        with pytest.raises(HTTPException) as exc_info:
            auth_service.refresh(refresh_token)
    finally:
        service.close()

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Authentication service temporarily unavailable"


def test_authenticate_access_token_fails_closed_when_database_user_lookup_is_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = _sqlite_service(tmp_path, InMemoryStore())
    _bind_persistence_services(monkeypatch, service)
    monkeypatch.setattr(service, "get_user", lambda user_id: None)
    monkeypatch.setattr(service, "list_users", lambda *, search=None: None)

    runtime_user = {
        "id": "runtime-auth-unavailable-access",
        "name": "Runtime Access",
        "email": "runtime-access@example.com",
        "role": "admin",
        "status": "active",
        "last_login": "2026-04-03T09:30:00+00:00",
        "total_interactions": 9,
        "created_at": "2026-04-01",
    }
    store.users = [runtime_user]
    access_token = auth_service._issue_token_pair(runtime_user)["access_token"]

    try:
        with pytest.raises(HTTPException) as exc_info:
            auth_service.authenticate_access_token(access_token)
    finally:
        service.close()

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Authentication service temporarily unavailable"
