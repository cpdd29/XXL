from fastapi.testclient import TestClient

from app.main import app
from app.platform.persistence.runtime_store import store


client = TestClient(app)


def test_user_profile_returns_fallback_for_regular_user(auth_headers) -> None:
    response = client.get("/api/users/2/profile", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "2"
    assert payload["preferredLanguage"] == "zh"
    assert "dingtalk" in payload["sourceChannels"]
    assert payload["platformAccounts"] == []


def test_user_activity_returns_timeline_items(auth_headers) -> None:
    response = client.get("/api/users/1/activity", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 5
    assert payload["items"][0]["title"]
    assert payload["items"][0]["source"]


def test_user_profile_exposes_platform_accounts(auth_headers) -> None:
    response = client.get("/api/users/1/profile", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert {"platform": "dingtalk", "accountId": "ding-zhang-admin"} in payload["platformAccounts"]
    assert {"platform": "telegram", "accountId": "tg_zhang_admin"} in payload["platformAccounts"]
    assert payload["identityMappingStatus"] in {"auto_mapped", "merged"}
    assert payload["identityMappingSource"] in {"system_auto_bind", "unknown"}
    assert payload["identityMappingConfidence"] >= 0


def test_update_user_profile_route_supports_crm_fields(auth_headers) -> None:
    response = client.put(
        "/api/users/2/profile",
        headers=auth_headers,
        json={
            "tags": ["重点客户", "已跟进", "重点客户"],
            "notes": "需要英文周报。",
            "preferredLanguage": "en",
        },
    )
    read_response = client.get("/api/users/2/profile", headers=auth_headers)

    assert response.status_code == 200
    assert read_response.status_code == 200

    payload = response.json()
    read_payload = read_response.json()

    assert payload["ok"] is True
    assert payload["user"]["id"] == "2"
    assert payload["user"]["tags"] == ["重点客户", "已跟进"]
    assert payload["user"]["notes"] == "需要英文周报。"
    assert payload["user"]["preferredLanguage"] == "en"
    assert read_payload["tags"] == ["重点客户", "已跟进"]
    assert read_payload["notes"] == "需要英文周报。"
    assert read_payload["preferredLanguage"] == "en"


def test_viewer_cannot_update_user_profile(viewer_auth_headers: dict[str, str]) -> None:
    response = client.put(
        "/api/users/1/profile",
        headers=viewer_auth_headers,
        json={
            "tags": ["只读"],
            "notes": "viewer 无权修改。",
            "preferredLanguage": "zh",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied"


def test_bind_user_platform_account_route_updates_profile(auth_headers) -> None:
    response = client.post(
        "/api/users/2/platform-accounts/bind",
        headers=auth_headers,
        json={
            "platform": "wecom",
            "accountId": "wecom-user-2",
            "confidence": 0.97,
            "source": "manual_override",
        },
    )
    read_response = client.get("/api/users/2/profile", headers=auth_headers)

    assert response.status_code == 200
    assert read_response.status_code == 200
    payload = response.json()
    read_payload = read_response.json()
    assert payload["ok"] is True
    assert {"platform": "wecom", "accountId": "wecom-user-2"} in payload["user"]["platformAccounts"]
    assert "wecom" in payload["user"]["sourceChannels"]
    assert payload["user"]["identityMappingStatus"] == "manually_verified"
    assert payload["user"]["identityMappingSource"] == "manual_override"
    assert payload["user"]["identityMappingConfidence"] == 0.97
    assert {"platform": "wecom", "accountId": "wecom-user-2"} in read_payload["platformAccounts"]
    assert read_payload["identityMappingStatus"] == "manually_verified"


def test_unbind_user_platform_account_route_removes_mapping(auth_headers) -> None:
    bind_response = client.post(
        "/api/users/2/platform-accounts/bind",
        headers=auth_headers,
        json={"platform": "telegram", "accountId": "tg-user-2"},
    )
    assert bind_response.status_code == 200

    response = client.post(
        "/api/users/2/platform-accounts/unbind",
        headers=auth_headers,
        json={"platform": "telegram", "accountId": "tg-user-2"},
    )
    read_response = client.get("/api/users/2/profile", headers=auth_headers)

    assert response.status_code == 200
    assert read_response.status_code == 200
    payload = response.json()
    read_payload = read_response.json()
    assert payload["ok"] is True
    assert {"platform": "telegram", "accountId": "tg-user-2"} not in payload["user"]["platformAccounts"]
    assert "telegram" not in payload["user"]["sourceChannels"]
    assert payload["user"]["identityMappingStatus"] == "unmapped"
    assert read_payload["identityMappingStatus"] == "unmapped"


def test_viewer_cannot_bind_platform_account(viewer_auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/users/1/platform-accounts/bind",
        headers=viewer_auth_headers,
        json={"platform": "wecom", "accountId": "viewer-bind"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied"


def test_power_user_cannot_update_user_role(auth_headers_factory) -> None:
    response = client.put(
        "/api/users/2/role",
        headers=auth_headers_factory(role="power_user"),
        json={"role": "viewer"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied"


def test_update_user_role_rejects_unknown_role(auth_headers) -> None:
    response = client.put(
        "/api/users/2/role",
        headers=auth_headers,
        json={"role": "not-a-real-role"},
    )

    assert response.status_code == 422


def test_bind_user_platform_account_rejects_cross_user_conflict(auth_headers) -> None:
    response = client.post(
        "/api/users/2/platform-accounts/bind",
        headers=auth_headers,
        json={"platform": "telegram", "accountId": "tg_zhang_admin"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Platform account already bound to user 1"


def test_user_list_search_matches_platform_account_and_channel(auth_headers) -> None:
    by_account = client.get("/api/users", params={"search": "tg_zhang_admin"}, headers=auth_headers)
    by_channel = client.get("/api/users", params={"search": "dingtalk"}, headers=auth_headers)

    assert by_account.status_code == 200
    assert by_channel.status_code == 200
    assert by_account.json()["total"] == 1
    assert by_account.json()["items"][0]["id"] == "1"
    assert by_channel.json()["total"] == 1
    assert by_channel.json()["items"][0]["id"] == "1"


def test_user_list_supports_role_and_status_filters(auth_headers) -> None:
    current_admin = next(user for user in store.users if user["id"] == "test-admin-user")
    store.users = [
        current_admin,
        {
            "id": "user-filter-1",
            "name": "运营管理员",
            "email": "admin-filter@example.com",
            "role": "admin",
            "status": "active",
            "last_login": "2026-04-06 09:00:00",
            "total_interactions": 20,
            "created_at": "2026-04-01",
        },
        {
            "id": "user-filter-2",
            "name": "运营运维",
            "email": "operator-filter@example.com",
            "role": "operator",
            "status": "active",
            "last_login": "2026-04-06 09:10:00",
            "total_interactions": 12,
            "created_at": "2026-04-01",
        },
        {
            "id": "user-filter-3",
            "name": "停用查看者",
            "email": "viewer-filter@example.com",
            "role": "viewer",
            "status": "suspended",
            "last_login": "2026-04-06 09:20:00",
            "total_interactions": 5,
            "created_at": "2026-04-01",
        },
    ]

    response = client.get(
        "/api/users",
        params={
            "role": "operator",
            "status": "active",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == "user-filter-2"
    assert payload["items"][0]["role"] == "operator"
    assert payload["items"][0]["status"] == "active"


def test_user_list_export_returns_filtered_csv_with_crm_fields(auth_headers) -> None:
    current_admin = next(user for user in store.users if user["id"] == "test-admin-user")
    store.users = [
        current_admin,
        {
            "id": "user-export-1",
            "name": "导出用户一",
            "email": "user-export-1@example.com",
            "role": "operator",
            "status": "active",
            "last_login": "2026-04-06 10:00:00",
            "total_interactions": 11,
            "created_at": "2026-04-01",
        },
        {
            "id": "user-export-2",
            "name": "导出用户二",
            "email": "user-export-2@example.com",
            "role": "viewer",
            "status": "suspended",
            "last_login": "2026-04-06 10:10:00",
            "total_interactions": 3,
            "created_at": "2026-04-01",
        },
    ]
    store.user_profiles["user-export-1"] = {
        "id": "user-export-1",
        "tags": ["重点客户", "英文偏好"],
        "notes": "需要每周同步一次。",
        "preferred_language": "en",
        "source_channels": ["telegram", "wecom"],
        "platform_accounts": [
            {"platform": "telegram", "account_id": "tg-export-1"},
            {"platform": "wecom", "account_id": "wecom-export-1"},
        ],
    }

    response = client.get(
        "/api/users/export",
        params={
            "role": "operator",
            "status": "active",
            "search": "导出用户一",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "attachment;" in response.headers["content-disposition"]
    text = response.text
    assert "用户ID,姓名,邮箱,角色,状态,最后登录,交互次数,创建时间,标签,偏好语言,来源渠道,平台账号,备注" in text
    assert "导出用户一" in text
    assert "重点客户 | 英文偏好" in text
    assert "telegram | wecom" in text
    assert "telegram:tg-export-1 | wecom:wecom-export-1" in text
    assert "需要每周同步一次。" in text
    assert "导出用户二" not in text
