from __future__ import annotations

import app.modules.reception.channel_binding.service as channel_binding_service_module
from app.platform.config.settings_service import get_channel_integration_runtime_settings
from app.modules.reception.channel_binding.service import (
    WECOM_CHANNEL_BINDING_SETTING_KEY,
    wecom_channel_binding_service,
)
from app.platform.persistence.persistence_service import persistence_service
from app.platform.persistence.runtime_store import store


def test_list_credentials_does_not_persist_empty_state_when_setting_is_missing(monkeypatch) -> None:
    persisted_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        channel_binding_service_module.persistence_service,
        "read_system_setting",
        lambda key: (None, True),
    )
    monkeypatch.setattr(
        channel_binding_service_module.persistence_service,
        "persist_system_setting",
        lambda **kwargs: persisted_calls.append(kwargs) or True,
    )

    previous = store.system_settings.pop(WECOM_CHANNEL_BINDING_SETTING_KEY, None)
    try:
        credentials = wecom_channel_binding_service.list_credentials()
        assert credentials == []
        assert persisted_calls == []
    finally:
        if previous is None:
            store.system_settings.pop(WECOM_CHANNEL_BINDING_SETTING_KEY, None)
        else:
            store.system_settings[WECOM_CHANNEL_BINDING_SETTING_KEY] = previous


def test_list_credentials_auto_syncs_confirmed_pending_session(monkeypatch) -> None:
    monkeypatch.setattr(
        channel_binding_service_module,
        "_fetch_ilink_login_qr",
        lambda bot_type="3": {
            "qr_code_token": "qr-token-004",
            "qr_code_url": "https://liteapp.weixin.qq.com/q/mock-login?qrcode=qr-token-004&bot_type=3",
        },
    )
    monkeypatch.setattr(
        channel_binding_service_module,
        "_fetch_ilink_qr_status",
        lambda qr_code_token, base_url=None: {
            "status": "confirmed",
            "ret": 0,
            "ilink_bot_id": "wx-bot-004",
            "bot_token": "wx-token-004",
            "baseurl": "https://ilinkai.weixin.qq.com",
            "ilink_user_id": "wx-user-004",
        },
    )

    previous = store.system_settings.pop(WECOM_CHANNEL_BINDING_SETTING_KEY, None)
    try:
        state = wecom_channel_binding_service.create_bind_session(
            tenant_id="tenant-wechat-d",
            tenant_name="微信接入租户D",
        )
        assert state.active_session is not None
        assert state.binding is None

        credentials = wecom_channel_binding_service.list_credentials()
        assert len(credentials) == 1
        assert credentials[0].tenant_id == "tenant-wechat-d"
        assert credentials[0].account_id == "wx-bot-004"
        assert credentials[0].access_token == "wx-token-004"
        assert credentials[0].user_id == "wx-user-004"
    finally:
        if previous is None:
            store.system_settings.pop(WECOM_CHANNEL_BINDING_SETTING_KEY, None)
        else:
            store.system_settings[WECOM_CHANNEL_BINDING_SETTING_KEY] = previous


def test_list_credentials_reconciles_stale_tenant_id_against_current_catalog() -> None:
    previous_binding_state = store.system_settings.pop(WECOM_CHANNEL_BINDING_SETTING_KEY, None)
    previous_tenant_catalog = store.system_settings.pop("profile_tenants", None)
    try:
        persistence_service.persist_system_setting(
            key="profile_tenants",
            payload={
                "items": [
                    {
                        "id": "tenant-wechat-live",
                        "name": "微信接入租户D",
                        "status": "active",
                        "description": "当前有效租户",
                    }
                ],
                "updated_at": "2026-05-05T12:00:00+08:00",
            },
            updated_at="2026-05-05T12:00:00+08:00",
        )
        persistence_service.persist_system_setting(
            key=WECOM_CHANNEL_BINDING_SETTING_KEY,
            payload={
                "bindings": [
                    {
                        "tenant_id": "tenant-wechat-stale",
                        "tenant_name": "微信接入租户D",
                        "channel": "wecom",
                        "display_name": "微信接入租户D 微信接入",
                        "external_account": "wx-user-004",
                        "status": "bound",
                        "bound_at": "2026-05-05T12:00:00+08:00",
                        "updated_at": "2026-05-05T12:00:00+08:00",
                    }
                ],
                "sessions": [],
                "credentials": [
                    {
                        "tenant_id": "tenant-wechat-stale",
                        "tenant_name": "微信接入租户D",
                        "channel": "wecom",
                        "account_id": "wx-bot-004",
                        "access_token": "wx-token-004",
                        "base_url": "https://ilinkai.weixin.qq.com",
                        "user_id": "wx-user-004",
                        "updated_at": "2026-05-05T12:00:00+08:00",
                    }
                ],
                "updated_at": "2026-05-05T12:00:00+08:00",
            },
            updated_at="2026-05-05T12:00:00+08:00",
        )

        credentials = wecom_channel_binding_service.list_credentials()
        binding_state = wecom_channel_binding_service.get_binding_state(
            "tenant-wechat-live",
            "微信接入租户D",
        )

        assert len(credentials) == 1
        assert credentials[0].tenant_id == "tenant-wechat-live"
        assert credentials[0].tenant_name == "微信接入租户D"
        assert binding_state.binding is not None
        assert binding_state.binding.tenant_id == "tenant-wechat-live"
        assert binding_state.binding.tenant_name == "微信接入租户D"
    finally:
        if previous_binding_state is None:
            store.system_settings.pop(WECOM_CHANNEL_BINDING_SETTING_KEY, None)
        else:
            store.system_settings[WECOM_CHANNEL_BINDING_SETTING_KEY] = previous_binding_state
        if previous_tenant_catalog is None:
            store.system_settings.pop("profile_tenants", None)
        else:
            store.system_settings["profile_tenants"] = previous_tenant_catalog


def test_channel_integration_runtime_settings_reconcile_stale_tenant_id_against_current_catalog() -> None:
    previous_tenant_catalog = store.system_settings.pop("profile_tenants", None)
    previous_channel_integrations = store.system_settings.pop("channel_integrations", None)
    try:
        persistence_service.persist_system_setting(
            key="profile_tenants",
            payload={
                "items": [
                    {
                        "id": "tenant-wechat-live",
                        "name": "微信接入租户D",
                        "status": "active",
                        "description": "当前有效租户",
                    }
                ],
                "updated_at": "2026-05-05T12:00:00+08:00",
            },
            updated_at="2026-05-05T12:00:00+08:00",
        )
        persistence_service.persist_system_setting(
            key="channel_integrations",
            payload={
                "wecom": {
                    "enabled": True,
                    "tenant_id": "tenant-wechat-stale",
                    "tenant_name": "微信接入租户D",
                    "webhook_secret_header": "X-WorkBot-Webhook-Secret",
                    "webhook_secret_query_param": "token",
                    "bot_webhook_base_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send",
                    "http_timeout_seconds": 10.0,
                    "bot_webhook_key": None,
                    "webhook_secret": None,
                }
            },
            updated_at="2026-05-05T12:00:00+08:00",
        )

        settings = get_channel_integration_runtime_settings()

        assert settings["wecom"]["tenant_id"] == "tenant-wechat-live"
        assert settings["wecom"]["tenant_name"] == "微信接入租户D"
    finally:
        if previous_tenant_catalog is None:
            store.system_settings.pop("profile_tenants", None)
        else:
            store.system_settings["profile_tenants"] = previous_tenant_catalog
        if previous_channel_integrations is None:
            store.system_settings.pop("channel_integrations", None)
        else:
            store.system_settings["channel_integrations"] = previous_channel_integrations
