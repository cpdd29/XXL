from fastapi.testclient import TestClient

from app.main import app
from app.modules.reception.channel_binding import service as channel_binding_service_module
from app.modules.reception.channel_binding.service import wecom_channel_binding_service
from app.platform.auth.authz import require_authenticated_user


def _admin_user_override():
    return {
        "id": "test-admin",
        "email": "test-admin@example.test",
        "name": "Test Admin",
        "role": "admin",
    }


def test_wecom_bind_session_uses_real_qr_and_auto_binds(monkeypatch) -> None:
    app.dependency_overrides[require_authenticated_user] = _admin_user_override

    monkeypatch.setattr(
        channel_binding_service_module,
        "_fetch_ilink_login_qr",
        lambda bot_type="3": {
            "qr_code_token": "qr-token-001",
            "qr_code_url": "https://liteapp.weixin.qq.com/q/mock-login?qrcode=qr-token-001&bot_type=3",
        },
    )

    poll_statuses = iter(
        [
            {"status": "wait", "ret": 0},
            {
                "status": "confirmed",
                "ret": 0,
                "ilink_bot_id": "wx-bot-001",
                "bot_token": "wx-token-001",
                "baseurl": "https://ilinkai.weixin.qq.com",
                "ilink_user_id": "wx-user-001",
            },
        ]
    )

    monkeypatch.setattr(
        channel_binding_service_module,
        "_fetch_ilink_qr_status",
        lambda qr_code_token, base_url=None: next(poll_statuses),
    )

    try:
        with TestClient(app) as client:
            create_response = client.post(
                "/api/settings/channel-integration/wecom/bind-sessions",
                json={
                    "tenantId": "tenant-wechat-a",
                    "tenantName": "微信接入租户A",
                },
            )
            assert create_response.status_code == 200
            create_body = create_response.json()
            assert create_body["ok"] is True
            assert create_body["state"]["tenantId"] == "tenant-wechat-a"
            assert create_body["state"]["activeSession"]["status"] == "pending"
            assert create_body["state"]["activeSession"]["qrCodeUrl"].startswith("https://liteapp.weixin.qq.com/")
            assert create_body["state"]["activeSession"]["scanStatus"] == "wait"

            state_response = client.get(
                "/api/settings/channel-integration/wecom/binding-state",
                params={"tenant_id": "tenant-wechat-a", "tenant_name": "微信接入租户A"},
            )
            assert state_response.status_code == 200
            state_body = state_response.json()
            assert state_body["tenantId"] == "tenant-wechat-a"
            assert state_body["binding"] is None
            assert state_body["activeSession"] is not None
            assert state_body["activeSession"]["status"] == "pending"
            assert state_body["activeSession"]["scanStatus"] == "wait"

            confirmed_response = client.get(
                "/api/settings/channel-integration/wecom/binding-state",
                params={"tenant_id": "tenant-wechat-a", "tenant_name": "微信接入租户A"},
            )
            assert confirmed_response.status_code == 200
            confirmed_body = confirmed_response.json()
            assert confirmed_body["tenantId"] == "tenant-wechat-a"
            assert confirmed_body["binding"] is not None
            assert confirmed_body["binding"]["displayName"] == "微信接入租户A 微信接入"
            assert confirmed_body["binding"]["externalAccount"] == "wx-user-001"
            assert confirmed_body["activeSession"] is None

        state = wecom_channel_binding_service.get_binding_state("tenant-wechat-a", "微信接入租户A")
        assert state.tenant_id == "tenant-wechat-a"
        assert state.binding is not None
        assert state.binding.display_name == "微信接入租户A 微信接入"
        assert state.binding.external_account == "wx-user-001"
        assert state.active_session is None

        cleared = wecom_channel_binding_service.clear_binding("tenant-wechat-a", "微信接入租户A")
        assert cleared.tenant_id == "tenant-wechat-a"
        assert cleared.binding is None
        assert cleared.active_session is None
    finally:
        app.dependency_overrides.clear()


def test_manual_confirm_is_rejected_for_real_qr_sessions(monkeypatch) -> None:
    app.dependency_overrides[require_authenticated_user] = _admin_user_override

    monkeypatch.setattr(
        channel_binding_service_module,
        "_fetch_ilink_login_qr",
        lambda bot_type="3": {
            "qr_code_token": "qr-token-002",
            "qr_code_url": "https://liteapp.weixin.qq.com/q/mock-login?qrcode=qr-token-002&bot_type=3",
        },
    )
    monkeypatch.setattr(
        channel_binding_service_module,
        "_fetch_ilink_qr_status",
        lambda qr_code_token, base_url=None: {"status": "wait", "ret": 0},
    )

    try:
        with TestClient(app) as client:
            create_response = client.post(
                "/api/settings/channel-integration/wecom/bind-sessions",
                json={
                    "tenantId": "tenant-wechat-b",
                    "tenantName": "微信接入租户B",
                },
            )
            assert create_response.status_code == 200
            bind_path = str(create_response.json()["state"]["activeSession"]["bindPath"])
            token = bind_path.split("token=", 1)[-1]

            confirm_response = client.post(
                f"/api/channel-bind/wecom/{token}/confirm",
                json={
                    "displayName": "市场部客服微信",
                    "externalAccount": "wx-market-service",
                },
            )
            assert confirm_response.status_code == 409
            assert "真实微信扫码绑定" in confirm_response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_remote_expired_status_does_not_clear_pending_qr_session(monkeypatch) -> None:
    app.dependency_overrides[require_authenticated_user] = _admin_user_override

    monkeypatch.setattr(
        channel_binding_service_module,
        "_fetch_ilink_login_qr",
        lambda bot_type="3": {
            "qr_code_token": "qr-token-003",
            "qr_code_url": "https://liteapp.weixin.qq.com/q/mock-login?qrcode=qr-token-003&bot_type=3",
        },
    )
    monkeypatch.setattr(
        channel_binding_service_module,
        "_fetch_ilink_qr_status",
        lambda qr_code_token, base_url=None: {"status": "expired", "ret": 0},
    )

    try:
        with TestClient(app) as client:
            create_response = client.post(
                "/api/settings/channel-integration/wecom/bind-sessions",
                json={
                    "tenantId": "tenant-wechat-c",
                    "tenantName": "微信接入租户C",
                },
            )
            assert create_response.status_code == 200
            create_body = create_response.json()
            assert create_body["state"]["activeSession"]["status"] == "pending"
            assert create_body["state"]["activeSession"]["scanStatus"] == "wait"

            state_response = client.get(
                "/api/settings/channel-integration/wecom/binding-state",
                params={"tenant_id": "tenant-wechat-c", "tenant_name": "微信接入租户C"},
            )
            assert state_response.status_code == 200
            state_body = state_response.json()
            assert state_body["activeSession"] is not None
            assert state_body["activeSession"]["status"] == "pending"
            assert state_body["activeSession"]["scanStatus"] == "expired"

        state = wecom_channel_binding_service.get_binding_state("tenant-wechat-c", "微信接入租户C")
        assert state.active_session is not None
        assert state.active_session.status == "pending"
        assert state.active_session.scan_status == "expired"
    finally:
        app.dependency_overrides.clear()
