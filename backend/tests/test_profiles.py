from fastapi.testclient import TestClient

from app.main import app
from app.modules.organization.application.memory_service import memory_service
from app.modules.organization.application.profile_service import TENANT_DIRECTORY_SETTING_KEY
from app.platform.persistence.runtime_store import store


client = TestClient(app)


def _seed_profile(profile_id: str, *, tenant_id: str, tenant_name: str, name: str, channel: str, account_id: str) -> None:
    store.user_profiles[profile_id] = {
        "id": profile_id,
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        "tenant_status": "active",
        "name": name,
        "tags": ["重点画像"] if tenant_id == "tenant-alpha" else ["服务画像"],
        "notes": f"{name} 的备注",
        "preferred_language": "zh" if tenant_id == "tenant-alpha" else "en",
        "source_channels": [channel],
        "platform_accounts": [{"platform": channel, "account_id": account_id}],
        "last_active_at": "2026-04-17 09:30:00",
        "total_interactions": 12 if tenant_id == "tenant-alpha" else 5,
        "created_at": "2026-04-01",
        "identity_mapping_status": "manually_verified",
        "identity_mapping_source": "manual_override",
        "identity_mapping_confidence": 1.0,
        "last_identity_sync_at": "2026-04-17 09:30:00",
    }


def _seed_tenant_catalog(*items: dict[str, str]) -> None:
    store.system_settings[TENANT_DIRECTORY_SETTING_KEY] = {
        "items": list(items),
        "updated_at": "2026-04-18T12:00:00+00:00",
    }


def test_profiles_route_filters_by_tenant_and_search_for_admin(auth_headers) -> None:
    _seed_profile(
        "profile-alpha-1",
        tenant_id="tenant-alpha",
        tenant_name="Alpha Corp",
        name="张小甲",
        channel="telegram",
        account_id="alpha-telegram-user",
    )
    _seed_profile(
        "profile-beta-1",
        tenant_id="tenant-beta",
        tenant_name="Beta Inc",
        name="李小乙",
        channel="wecom",
        account_id="beta-wecom-user",
    )

    response = client.get(
        "/api/profiles",
        params={"tenantId": "tenant-alpha", "search": "telegram"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["appliedTenantId"] == "tenant-alpha"
    assert payload["items"][0]["id"] == "profile-alpha-1"
    assert payload["items"][0]["tenantName"] == "Alpha Corp"


def test_profiles_route_prevents_cross_tenant_access_for_scoped_operator(auth_headers_factory) -> None:
    store.user_profiles["tenant-operator"] = {
        "id": "tenant-operator",
        "tenant_id": "tenant-alpha",
        "tenant_name": "Alpha Corp",
    }
    _seed_profile(
        "profile-alpha-2",
        tenant_id="tenant-alpha",
        tenant_name="Alpha Corp",
        name="王租户",
        channel="dingtalk",
        account_id="alpha-ding-user",
    )

    response = client.get(
        "/api/profiles",
        params={"tenantId": "tenant-beta"},
        headers=auth_headers_factory(
            role="operator",
            user_id="tenant-operator",
            email="tenant.operator@example.test",
        ),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Cross-tenant access denied for profile scope"


def test_profile_detail_honors_scope_and_returns_activity(auth_headers_factory) -> None:
    store.user_profiles["tenant-viewer"] = {
        "id": "tenant-viewer",
        "tenant_id": "tenant-alpha",
        "tenant_name": "Alpha Corp",
    }
    _seed_profile(
        "profile-alpha-3",
        tenant_id="tenant-alpha",
        tenant_name="Alpha Corp",
        name="赵画像",
        channel="feishu",
        account_id="alpha-feishu-user",
    )
    _seed_profile(
        "profile-beta-3",
        tenant_id="tenant-beta",
        tenant_name="Beta Inc",
        name="跨租户画像",
        channel="wecom",
        account_id="beta-wecom-user-3",
    )

    allowed = client.get(
        "/api/profiles/profile-alpha-3",
        headers=auth_headers_factory(
            role="viewer",
            user_id="tenant-viewer",
            email="tenant.viewer@example.test",
        ),
    )
    blocked = client.get(
        "/api/profiles/profile-beta-3",
        headers=auth_headers_factory(
            role="viewer",
            user_id="tenant-viewer",
            email="tenant.viewer@example.test",
        ),
    )
    activity = client.get(
        "/api/profiles/profile-alpha-3/activity",
        headers=auth_headers_factory(
            role="viewer",
            user_id="tenant-viewer",
            email="tenant.viewer@example.test",
        ),
    )

    assert allowed.status_code == 200
    assert allowed.json()["tenantId"] == "tenant-alpha"
    assert blocked.status_code == 403
    assert activity.status_code == 200
    assert activity.json()["total"] >= 4


def test_update_profile_route_updates_tags_notes_and_language(auth_headers_factory) -> None:
    store.user_profiles["tenant-operator-update"] = {
        "id": "tenant-operator-update",
        "tenant_id": "tenant-alpha",
        "tenant_name": "Alpha Corp",
    }
    _seed_profile(
        "profile-alpha-update",
        tenant_id="tenant-alpha",
        tenant_name="Alpha Corp",
        name="待更新画像",
        channel="telegram",
        account_id="alpha-update-user",
    )

    response = client.put(
        "/api/profiles/profile-alpha-update",
        headers=auth_headers_factory(
            role="operator",
            user_id="tenant-operator-update",
            email="tenant.operator.update@example.test",
        ),
        json={
            "tags": ["高价值", "英文偏好", "高价值"],
            "notes": "需要优先给出最接近的解决办法。",
            "preferredLanguage": "en",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["profile"]["tags"] == ["高价值", "英文偏好"]
    assert payload["profile"]["notes"] == "需要优先给出最接近的解决办法。"
    assert payload["profile"]["preferredLanguage"] == "en"
    assert store.user_profiles["profile-alpha-update"]["tenant_id"] == "tenant-alpha"


def test_profiles_export_is_scoped_to_current_tenant(auth_headers_factory) -> None:
    store.user_profiles["tenant-operator-export"] = {
        "id": "tenant-operator-export",
        "tenant_id": "tenant-alpha",
        "tenant_name": "Alpha Corp",
    }
    _seed_profile(
        "profile-alpha-export",
        tenant_id="tenant-alpha",
        tenant_name="Alpha Corp",
        name="导出画像甲",
        channel="telegram",
        account_id="alpha-export-user",
    )
    _seed_profile(
        "profile-beta-export",
        tenant_id="tenant-beta",
        tenant_name="Beta Inc",
        name="导出画像乙",
        channel="wecom",
        account_id="beta-export-user",
    )

    response = client.get(
        "/api/profiles/export",
        headers=auth_headers_factory(
            role="operator",
            user_id="tenant-operator-export",
            email="tenant.operator.export@example.test",
        ),
    )

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "workbot-profiles-tenant-alpha" in response.headers["content-disposition"]
    text = response.text
    assert "租户ID,租户名称,画像ID,人员名称,来源渠道,平台账号,标签,语言偏好,最近活跃,累计交互次数,备注" in text
    assert "导出画像甲" in text
    assert "导出画像乙" not in text


def test_profile_tenants_route_returns_default_scope_for_scoped_user(auth_headers_factory) -> None:
    store.user_profiles["tenant-operator-tenants"] = {
        "id": "tenant-operator-tenants",
        "tenant_id": "tenant-alpha",
        "tenant_name": "Alpha Corp",
    }

    response = client.get(
        "/api/profiles/tenants",
        headers=auth_headers_factory(
            role="operator",
            user_id="tenant-operator-tenants",
            email="tenant.operator.tenants@example.test",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["canViewAllTenants"] is False
    assert payload["defaultTenantId"] == "tenant-alpha"
    assert payload["items"][0]["id"] == "tenant-alpha"


def test_profile_tenant_routes_support_create_and_delete_for_platform_scope(auth_headers) -> None:
    create_response = client.post(
        "/api/profiles/tenants",
        headers=auth_headers,
        json={
            "name": "Gamma Labs",
            "description": "Gamma 租户说明",
        },
    )

    assert create_response.status_code == 200
    create_payload = create_response.json()
    assert create_payload["ok"] is True
    assert create_payload["tenant"]["id"] == "tenant-gamma-labs"
    assert create_payload["tenant"]["name"] == "Gamma Labs"
    assert create_payload["tenant"]["description"] == "Gamma 租户说明"
    assert create_payload["tenant"]["profileCount"] == 0

    list_response = client.get("/api/profiles/tenants", headers=auth_headers)
    assert list_response.status_code == 200
    tenant_ids = [item["id"] for item in list_response.json()["items"]]
    assert "tenant-gamma-labs" in tenant_ids

    delete_response = client.delete("/api/profiles/tenants/tenant-gamma-labs", headers=auth_headers)
    assert delete_response.status_code == 200
    delete_payload = delete_response.json()
    assert delete_payload["ok"] is True
    assert delete_payload["deletedTenantId"] == "tenant-gamma-labs"

    refreshed_response = client.get("/api/profiles/tenants", headers=auth_headers)
    assert refreshed_response.status_code == 200
    refreshed_ids = [item["id"] for item in refreshed_response.json()["items"]]
    assert "tenant-gamma-labs" not in refreshed_ids


def test_profiles_management_view_allows_cross_tenant_preview_for_tenant_management(auth_headers_factory) -> None:
    _seed_profile(
        "profile-beta-management",
        tenant_id="tenant-beta",
        tenant_name="Beta Inc",
        name="Beta 管理视图用户",
        channel="wecom",
        account_id="beta-management-user",
    )

    response = client.get(
        "/api/profiles",
        params={"tenantId": "tenant-beta", "management": "true"},
        headers=auth_headers_factory(role="admin", user_id="admin-1", email="admin@workbot.ai"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["appliedTenantId"] == "tenant-beta"
    assert payload["total"] == 1
    assert payload["items"][0]["tenantId"] == "tenant-beta"


def test_profile_tenants_management_view_exposes_directory_for_scoped_admin(auth_headers_factory) -> None:
    _seed_tenant_catalog(
        {
            "id": "tenant-alpha",
            "name": "Alpha Corp",
            "status": "active",
            "description": "Alpha 租户目录",
        },
        {
            "id": "tenant-gamma",
            "name": "Gamma Labs",
            "status": "active",
            "description": "Gamma 租户目录",
        },
    )
    _seed_profile(
        "profile-tenant-mgmt-1",
        tenant_id="tenant-alpha",
        tenant_name="Alpha Corp",
        name="Alpha 用户",
        channel="telegram",
        account_id="alpha-user",
    )
    _seed_profile(
        "profile-tenant-mgmt-beta",
        tenant_id="tenant-beta",
        tenant_name="Beta Inc",
        name="Beta 用户",
        channel="wecom",
        account_id="beta-user",
    )
    store.user_profiles["profile-tenant-mgmt-unbound"] = {
        "id": "profile-tenant-mgmt-unbound",
        "tenant_id": "",
        "tenant_name": "",
        "name": "未绑定用户",
    }

    response = client.get(
        "/api/profiles/tenants",
        params={"management": "true"},
        headers=auth_headers_factory(role="admin", user_id="admin-1", email="admin@workbot.ai"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["canViewAllTenants"] is True
    assert payload["items"] == [
        {
            "id": "tenant-alpha",
            "name": "Alpha Corp",
            "status": "active",
            "profileCount": 1,
            "description": "Alpha 租户目录",
        },
        {
            "id": "tenant-gamma",
            "name": "Gamma Labs",
            "status": "active",
            "profileCount": 0,
            "description": "Gamma 租户目录",
        },
    ]


def test_profile_tenant_delete_cascades_linked_profiles(auth_headers) -> None:
    _seed_tenant_catalog(
        {
            "id": "tenant-locked",
            "name": "Locked Corp",
            "status": "active",
            "description": "Locked 租户目录",
        },
        {
            "id": "tenant-safe",
            "name": "Safe Corp",
            "status": "active",
            "description": "Safe 租户目录",
        },
    )
    _seed_profile(
        "profile-linked-delete",
        tenant_id="tenant-locked",
        tenant_name="Locked Corp",
        name="待级联删除画像",
        channel="telegram",
        account_id="locked-user",
    )
    _seed_profile(
        "profile-safe-keep",
        tenant_id="tenant-safe",
        tenant_name="Safe Corp",
        name="保留画像",
        channel="wecom",
        account_id="safe-user",
    )
    memory_service._short_term["profile-linked-delete"] = [
        {
            "id": "msg-linked-1",
            "user_id": "profile-linked-delete",
            "session_id": "session-linked",
            "role": "user",
            "content": "待清理消息",
            "created_at": "2026-04-18T10:00:00+00:00",
        }
    ]
    memory_service._short_term["profile-safe-keep"] = [
        {
            "id": "msg-safe-1",
            "user_id": "profile-safe-keep",
            "session_id": "session-safe",
            "role": "user",
            "content": "保留消息",
            "created_at": "2026-04-18T10:01:00+00:00",
        }
    ]
    memory_service._mid_term["profile-linked-delete"] = [
        {
            "id": "mid-linked-1",
            "user_id": "profile-linked-delete",
            "tenant_id": "tenant-locked",
        }
    ]
    memory_service._mid_term["profile-safe-keep"] = [
        {
            "id": "mid-safe-1",
            "user_id": "profile-safe-keep",
            "tenant_id": "tenant-safe",
        }
    ]
    memory_service._long_term["profile-linked-delete"] = [
        {
            "id": "long-linked-1",
            "user_id": "profile-linked-delete",
            "tenant_id": "tenant-locked",
        }
    ]
    memory_service._long_term["profile-safe-keep"] = [
        {
            "id": "long-safe-1",
            "user_id": "profile-safe-keep",
            "tenant_id": "tenant-safe",
        }
    ]
    memory_service._session_state_cache[("profile-linked-delete", "session-linked")] = {
        "user_id": "profile-linked-delete",
        "session_id": "session-linked",
        "last_distilled_message_created_at": "2026-04-18T10:00:00+00:00",
        "last_distilled_message_ids_at_created_at": ["msg-linked-1"],
        "updated_at": "2026-04-18T10:00:01+00:00",
    }
    memory_service._session_state_cache[("profile-safe-keep", "session-safe")] = {
        "user_id": "profile-safe-keep",
        "session_id": "session-safe",
        "last_distilled_message_created_at": "2026-04-18T10:01:00+00:00",
        "last_distilled_message_ids_at_created_at": ["msg-safe-1"],
        "updated_at": "2026-04-18T10:01:01+00:00",
    }

    response = client.delete("/api/profiles/tenants/tenant-locked", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["deletedTenantId"] == "tenant-locked"
    assert "profile-linked-delete" not in store.user_profiles
    assert "profile-safe-keep" in store.user_profiles
    assert "profile-linked-delete" not in memory_service._short_term
    assert "profile-linked-delete" not in memory_service._mid_term
    assert "profile-linked-delete" not in memory_service._long_term
    assert ("profile-linked-delete", "session-linked") not in memory_service._session_state_cache
    assert "profile-safe-keep" in memory_service._short_term
    assert "profile-safe-keep" in memory_service._mid_term
    assert "profile-safe-keep" in memory_service._long_term
    assert ("profile-safe-keep", "session-safe") in memory_service._session_state_cache

    refreshed_tenants = client.get(
        "/api/profiles/tenants",
        params={"management": "true"},
        headers=auth_headers,
    )
    assert refreshed_tenants.status_code == 200
    tenant_ids = [item["id"] for item in refreshed_tenants.json()["items"]]
    assert "tenant-locked" not in tenant_ids
    assert "tenant-safe" in tenant_ids


def test_profile_tenants_management_view_does_not_inject_default_tenant_without_data(auth_headers) -> None:
    store.user_profiles.clear()
    store.user_profiles["admin-1"] = {
        "id": "admin-1",
        "exclude_from_profiles": True,
        "platform_admin": True,
    }
    store.system_settings.pop(TENANT_DIRECTORY_SETTING_KEY, None)

    response = client.get(
        "/api/profiles/tenants",
        params={"management": "true"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == []
    assert payload["total"] == 0


def test_profile_tenant_delete_allows_default_tenant_when_empty(auth_headers) -> None:
    store.user_profiles.clear()
    store.system_settings[TENANT_DIRECTORY_SETTING_KEY] = {
        "items": [
            {
                "id": "default",
                "name": "默认租户",
                "status": "active",
                "description": "默认租户目录",
            }
        ],
        "updated_at": "2026-04-18T10:00:00+00:00",
    }

    response = client.delete("/api/profiles/tenants/default", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["deletedTenantId"] == "default"

    refreshed_response = client.get("/api/profiles/tenants", headers=auth_headers)
    assert refreshed_response.status_code == 200
    assert all(item["id"] != "default" for item in refreshed_response.json()["items"])
