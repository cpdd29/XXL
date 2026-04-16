from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import app
from app.services.encryption_service import ENCRYPTED_TEXT_PREFIX
from app.services import settings_service
from app.services.persistence_service import StatePersistenceService
from app.services.store import InMemoryStore, store


client = TestClient(app)


def test_settings_accepts_extra_workbot_env_vars(monkeypatch) -> None:
    monkeypatch.setenv("WORKBOT_ENVIRONMENT", "test")
    monkeypatch.setenv("WORKBOT_TOOL_SOURCES_MODE", "external_only")
    monkeypatch.setenv("WORKBOT_ENABLE_LOCAL_MCP_SOURCE", "false")

    settings = Settings()

    assert settings.environment == "test"


def test_settings_default_database_url_uses_psycopg_driver() -> None:
    settings = Settings(_env_file=None)

    assert settings.database_url.startswith("postgresql+psycopg://")


def test_settings_still_validates_critical_field_types(monkeypatch) -> None:
    monkeypatch.setenv("WORKBOT_MESSAGE_RATE_LIMIT_PER_MINUTE", "not-an-int")

    try:
        Settings()
        assert False, "Expected Settings() to fail on invalid integer env value"
    except ValidationError as exc:
        assert "message_rate_limit_per_minute" in str(exc)


def _replace_global_store(seeded_store: InMemoryStore) -> None:
    store.__dict__.clear()
    store.__dict__.update(store.clone(seeded_store.__dict__))


def _sqlite_service(tmp_path: Path, seeded_store: InMemoryStore) -> StatePersistenceService:
    database_path = tmp_path / "settings-tests.db"
    _replace_global_store(seeded_store)
    service = StatePersistenceService(
        runtime_store=store,
        database_url=f"sqlite:///{database_path}",
    )
    assert service.initialize() is True
    return service


def test_general_settings_route_returns_defaults(auth_headers) -> None:
    response = client.get("/api/settings/general", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["key"] == "general"
    assert payload["settings"] == {
        "dashboardAutoRefresh": True,
        "showSystemStatus": True,
    }


def test_config_governance_route_returns_sectioned_snapshot(auth_headers) -> None:
    response = client.get("/api/settings/governance", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["totalSections"] >= 4
    assert payload["summary"]["runtimeMutableSections"] >= 4
    assert payload["readPriorityModel"]["runtimeMutable"] == [
        "database_system_settings",
        "runtime_cache",
        "deployment_defaults",
    ]
    section_keys = {item["key"] for item in payload["sections"]}
    assert "general" in section_keys
    assert "security_policy" in section_keys
    assert "agent_api" in section_keys
    assert "channel_integrations" in section_keys
    assert "auth_runtime" in section_keys


def test_config_governance_route_exposes_settings_change_audits(
    auth_headers_factory,
) -> None:
    update_response = client.put(
        "/api/settings/general",
        headers=auth_headers_factory(role="operator", email="governance.audit@example.com"),
        json={"dashboardAutoRefresh": False},
    )
    assert update_response.status_code == 200

    response = client.get("/api/settings/governance", headers=auth_headers_factory())

    assert response.status_code == 200
    audits = response.json()["recentChangeAudits"]
    assert audits
    assert audits[0]["action"] == "settings.general.updated"
    assert audits[0]["user"] == "governance.audit@example.com"


def test_config_governance_route_flags_runtime_risks(auth_headers) -> None:
    response = client.get("/api/settings/governance", headers=auth_headers)

    assert response.status_code == 200
    sections = {item["key"]: item for item in response.json()["sections"]}
    assert sections["auth_runtime"]["riskLevel"] == "warning"
    assert sections["auth_runtime"]["warnings"]


def test_update_general_settings_persists_round_trip(
    tmp_path: Path,
    monkeypatch,
    auth_headers_factory,
) -> None:
    service = _sqlite_service(tmp_path, InMemoryStore())
    monkeypatch.setattr(settings_service, "persistence_service", service)
    auth_headers = auth_headers_factory()

    try:
        update_response = client.put(
            "/api/settings/general",
            headers=auth_headers,
            json={
                "dashboardAutoRefresh": False,
                "showSystemStatus": False,
            },
        )
        read_response = client.get("/api/settings/general", headers=auth_headers)
        persisted_setting = service.get_system_setting("general")
    finally:
        service.close()

    assert update_response.status_code == 200
    assert read_response.status_code == 200

    update_payload = update_response.json()
    read_payload = read_response.json()

    assert update_payload["settings"] == {
        "dashboardAutoRefresh": False,
        "showSystemStatus": False,
    }
    assert update_payload["updatedAt"]
    assert read_payload["settings"] == update_payload["settings"]
    assert persisted_setting is not None
    assert persisted_setting["payload"] == {
        "dashboard_auto_refresh": False,
        "show_system_status": False,
    }


def test_update_general_settings_merges_partial_payload_with_persisted_values(
    tmp_path: Path,
    monkeypatch,
    auth_headers_factory,
) -> None:
    seeded_store = InMemoryStore()
    service = _sqlite_service(tmp_path, seeded_store)
    monkeypatch.setattr(settings_service, "persistence_service", service)
    auth_headers = auth_headers_factory()
    service.persist_system_setting(
        key="general",
        payload={
            "dashboard_auto_refresh": True,
            "show_system_status": False,
        },
        updated_at="2026-04-06T00:00:00+00:00",
    )

    try:
        update_response = client.put(
            "/api/settings/general",
            headers=auth_headers,
            json={
                "dashboardAutoRefresh": False,
            },
        )
        read_response = client.get("/api/settings/general", headers=auth_headers)
        persisted_setting = service.get_system_setting("general")
    finally:
        service.close()

    assert update_response.status_code == 200
    assert read_response.status_code == 200

    update_payload = update_response.json()
    read_payload = read_response.json()

    assert update_payload["settings"] == {
        "dashboardAutoRefresh": False,
        "showSystemStatus": False,
    }
    assert read_payload["settings"] == update_payload["settings"]
    assert persisted_setting is not None
    assert persisted_setting["payload"] == {
        "dashboard_auto_refresh": False,
        "show_system_status": False,
    }


def test_general_settings_ignores_stale_runtime_cache_when_database_setting_is_missing(
    tmp_path: Path,
    monkeypatch,
    auth_headers_factory,
) -> None:
    service = _sqlite_service(tmp_path, InMemoryStore())
    monkeypatch.setattr(settings_service, "persistence_service", service)
    auth_headers = auth_headers_factory()
    store.system_settings["general"] = {
        "dashboard_auto_refresh": False,
        "show_system_status": False,
    }

    try:
        response = client.get("/api/settings/general", headers=auth_headers)
    finally:
        service.close()

    assert response.status_code == 200
    assert response.json()["settings"] == {
        "dashboardAutoRefresh": True,
        "showSystemStatus": True,
    }
    assert store.system_settings["general"] == {
        "dashboard_auto_refresh": True,
        "show_system_status": True,
    }


def test_update_general_settings_merges_partial_payload_with_defaults_when_database_setting_is_missing(
    tmp_path: Path,
    monkeypatch,
    auth_headers_factory,
) -> None:
    service = _sqlite_service(tmp_path, InMemoryStore())
    monkeypatch.setattr(settings_service, "persistence_service", service)
    auth_headers = auth_headers_factory()
    store.system_settings["general"] = {
        "dashboard_auto_refresh": False,
        "show_system_status": False,
    }

    try:
        update_response = client.put(
            "/api/settings/general",
            headers=auth_headers,
            json={
                "dashboardAutoRefresh": False,
            },
        )
        persisted_setting = service.get_system_setting("general")
    finally:
        service.close()

    assert update_response.status_code == 200
    assert update_response.json()["settings"] == {
        "dashboardAutoRefresh": False,
        "showSystemStatus": True,
    }
    assert persisted_setting is not None
    assert persisted_setting["payload"] == {
        "dashboard_auto_refresh": False,
        "show_system_status": True,
    }


def test_viewer_cannot_update_general_settings(
    viewer_auth_headers: dict[str, str],
) -> None:
    response = client.put(
        "/api/settings/general",
        headers=viewer_auth_headers,
        json={
            "dashboardAutoRefresh": False,
            "showSystemStatus": False,
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied"


def test_power_user_cannot_update_general_settings(
    auth_headers_factory,
) -> None:
    response = client.put(
        "/api/settings/general",
        headers=auth_headers_factory(role="power_user"),
        json={
            "dashboardAutoRefresh": False,
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied"


def test_update_general_settings_appends_control_plane_audit_log(
    auth_headers_factory,
) -> None:
    response = client.put(
        "/api/settings/general",
        headers=auth_headers_factory(role="operator", email="ops.settings@example.test"),
        json={
            "dashboardAutoRefresh": False,
        },
    )

    assert response.status_code == 200
    assert store.audit_logs[0]["action"] == "settings.general.updated"
    assert store.audit_logs[0]["user"] == "ops.settings@example.test"


def test_security_policy_route_returns_defaults(auth_headers) -> None:
    response = client.get("/api/settings/security-policy", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["key"] == "security_policy"
    assert payload["settings"] == {
        "messageRateLimitPerMinute": settings_service.DEFAULT_SECURITY_POLICY_SETTINGS["message_rate_limit_per_minute"],
        "messageRateLimitCooldownSeconds": settings_service.DEFAULT_SECURITY_POLICY_SETTINGS["message_rate_limit_cooldown_seconds"],
        "messageRateLimitBanThreshold": settings_service.DEFAULT_SECURITY_POLICY_SETTINGS["message_rate_limit_ban_threshold"],
        "messageRateLimitBanSeconds": settings_service.DEFAULT_SECURITY_POLICY_SETTINGS["message_rate_limit_ban_seconds"],
        "securityIncidentWindowSeconds": settings_service.DEFAULT_SECURITY_POLICY_SETTINGS["security_incident_window_seconds"],
        "promptRuleBlockThreshold": settings_service.DEFAULT_SECURITY_POLICY_SETTINGS["prompt_rule_block_threshold"],
        "promptClassifierBlockThreshold": settings_service.DEFAULT_SECURITY_POLICY_SETTINGS["prompt_classifier_block_threshold"],
        "promptInjectionEnabled": settings_service.DEFAULT_SECURITY_POLICY_SETTINGS["prompt_injection_enabled"],
        "contentRedactionEnabled": settings_service.DEFAULT_SECURITY_POLICY_SETTINGS["content_redaction_enabled"],
    }


def test_update_security_policy_persists_round_trip(
    tmp_path: Path,
    monkeypatch,
    auth_headers_factory,
) -> None:
    service = _sqlite_service(tmp_path, InMemoryStore())
    monkeypatch.setattr(settings_service, "persistence_service", service)
    auth_headers = auth_headers_factory()

    try:
        approval_response = client.put(
            "/api/settings/security-policy",
            headers=auth_headers,
            json={
                "messageRateLimitPerMinute": 9,
                "messageRateLimitCooldownSeconds": 45,
                "messageRateLimitBanThreshold": 4,
                "messageRateLimitBanSeconds": 600,
                "securityIncidentWindowSeconds": 900,
                "promptRuleBlockThreshold": 5,
                "promptClassifierBlockThreshold": 4,
                "promptInjectionEnabled": False,
                "contentRedactionEnabled": False,
            },
        )
        assert approval_response.status_code == 202
        approval_id = approval_response.json()["approval"]["id"]
        approve_response = client.post(
            f"/api/approvals/{approval_id}/approve",
            headers=auth_headers,
            json={"note": "允许执行安全策略更新"},
        )
        assert approve_response.status_code == 200
        update_response = client.put(
            "/api/settings/security-policy",
            headers=auth_headers,
            json={
                "messageRateLimitPerMinute": 9,
                "messageRateLimitCooldownSeconds": 45,
                "messageRateLimitBanThreshold": 4,
                "messageRateLimitBanSeconds": 600,
                "securityIncidentWindowSeconds": 900,
                "promptRuleBlockThreshold": 5,
                "promptClassifierBlockThreshold": 4,
                "promptInjectionEnabled": False,
                "contentRedactionEnabled": False,
                "approvalId": approval_id,
            },
        )
        read_response = client.get("/api/settings/security-policy", headers=auth_headers)
        persisted_setting = service.get_system_setting("security_policy")
    finally:
        service.close()

    assert update_response.status_code == 200
    assert read_response.status_code == 200
    assert update_response.json()["settings"] == {
        "messageRateLimitPerMinute": 9,
        "messageRateLimitCooldownSeconds": 45,
        "messageRateLimitBanThreshold": 4,
        "messageRateLimitBanSeconds": 600,
        "securityIncidentWindowSeconds": 900,
        "promptRuleBlockThreshold": 5,
        "promptClassifierBlockThreshold": 4,
        "promptInjectionEnabled": False,
        "contentRedactionEnabled": False,
    }
    assert read_response.json()["settings"] == update_response.json()["settings"]
    assert persisted_setting is not None
    assert persisted_setting["payload"] == {
        "message_rate_limit_per_minute": 9,
        "message_rate_limit_cooldown_seconds": 45,
        "message_rate_limit_ban_threshold": 4,
        "message_rate_limit_ban_seconds": 600,
        "security_incident_window_seconds": 900,
        "prompt_rule_block_threshold": 5,
        "prompt_classifier_block_threshold": 4,
        "prompt_injection_enabled": False,
        "content_redaction_enabled": False,
    }


def test_update_security_policy_merges_partial_payload_with_defaults_when_missing(
    tmp_path: Path,
    monkeypatch,
    auth_headers_factory,
) -> None:
    service = _sqlite_service(tmp_path, InMemoryStore())
    monkeypatch.setattr(settings_service, "persistence_service", service)
    auth_headers = auth_headers_factory()

    try:
        approval_response = client.put(
            "/api/settings/security-policy",
            headers=auth_headers,
            json={
                "messageRateLimitPerMinute": 11,
                "promptInjectionEnabled": False,
            },
        )
        assert approval_response.status_code == 202
        approval_id = approval_response.json()["approval"]["id"]
        assert client.post(
            f"/api/approvals/{approval_id}/approve",
            headers=auth_headers,
            json={"note": "允许执行"},
        ).status_code == 200
        update_response = client.put(
            "/api/settings/security-policy",
            headers=auth_headers,
            json={
                "messageRateLimitPerMinute": 11,
                "promptInjectionEnabled": False,
                "approvalId": approval_id,
            },
        )
        persisted_setting = service.get_system_setting("security_policy")
    finally:
        service.close()

    assert update_response.status_code == 200
    assert update_response.json()["settings"]["messageRateLimitPerMinute"] == 11
    assert update_response.json()["settings"]["promptInjectionEnabled"] is False
    assert update_response.json()["settings"]["contentRedactionEnabled"] is True
    assert persisted_setting is not None
    assert persisted_setting["payload"]["message_rate_limit_per_minute"] == 11
    assert persisted_setting["payload"]["prompt_injection_enabled"] is False
    assert (
        persisted_setting["payload"]["message_rate_limit_cooldown_seconds"]
        == settings_service.DEFAULT_SECURITY_POLICY_SETTINGS["message_rate_limit_cooldown_seconds"]
    )


def test_viewer_cannot_update_security_policy(
    viewer_auth_headers: dict[str, str],
) -> None:
    response = client.put(
        "/api/settings/security-policy",
        headers=viewer_auth_headers,
        json={
            "messageRateLimitPerMinute": 10,
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied"


def test_update_security_policy_requires_approval_and_prevents_replay(
    tmp_path: Path,
    monkeypatch,
    auth_headers_factory,
) -> None:
    service = _sqlite_service(tmp_path, InMemoryStore())
    monkeypatch.setattr(settings_service, "persistence_service", service)
    auth_headers = auth_headers_factory(role="operator", email="security.policy@example.test")

    try:
        approval_response = client.put(
            "/api/settings/security-policy",
            headers=auth_headers,
            json={
                "messageRateLimitPerMinute": 12,
                "approvalReason": "需要提高风控强度",
            },
        )
        approval_id = approval_response.json()["approval"]["id"]
        approve_response = client.post(
            f"/api/approvals/{approval_id}/approve",
            headers=auth_headers,
            json={"note": "批准"},
        )
        first_execute = client.put(
            "/api/settings/security-policy",
            headers=auth_headers,
            json={
                "messageRateLimitPerMinute": 12,
                "approvalId": approval_id,
            },
        )
        replay_execute = client.put(
            "/api/settings/security-policy",
            headers=auth_headers,
            json={
                "messageRateLimitPerMinute": 12,
                "approvalId": approval_id,
            },
        )
    finally:
        service.close()

    assert approval_response.status_code == 202
    assert approval_response.json()["approvalRequired"] is True
    assert approve_response.status_code == 200
    assert first_execute.status_code == 200
    assert replay_execute.status_code == 409


def test_agent_api_settings_route_returns_defaults(auth_headers) -> None:
    response = client.get("/api/settings/agent-api", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["key"] == "agent_api"
    assert set(payload["settings"]["providers"]) == {
        "claude",
        "codex",
        "openai",
        "kimi",
        "minimax",
        "gemini",
        "deepseek",
        "openapi",
    }
    assert payload["settings"]["providers"]["openai"]["hasApiKey"] is False
    assert payload["settings"]["providers"]["openai"]["apiKeyMasked"] is None


def test_update_agent_api_settings_persists_encrypted_keys_and_returns_masked_values(
    tmp_path: Path,
    monkeypatch,
    auth_headers_factory,
) -> None:
    service = _sqlite_service(tmp_path, InMemoryStore())
    monkeypatch.setattr(settings_service, "persistence_service", service)
    auth_headers = auth_headers_factory()

    try:
        update_response = client.put(
            "/api/settings/agent-api",
            headers=auth_headers,
            json={
                "providers": {
                    "openai": {
                        "enabled": True,
                        "baseUrl": "https://api.openai.com/v1",
                        "model": "gpt-5",
                        "organizationId": "org-workbot",
                        "projectId": "proj-workbot",
                        "apiKey": "sk-openai-secret-123456",
                    },
                    "claude": {
                        "enabled": True,
                        "baseUrl": "https://api.anthropic.com",
                        "model": "claude-sonnet",
                        "apiKey": "sk-ant-secret-654321",
                    },
                }
            },
        )
        read_response = client.get("/api/settings/agent-api", headers=auth_headers)
        persisted_setting = service.get_system_setting("agent_api")
    finally:
        service.close()

    assert update_response.status_code == 200
    assert read_response.status_code == 200

    openai_settings = update_response.json()["settings"]["providers"]["openai"]
    assert openai_settings["enabled"] is True
    assert openai_settings["hasApiKey"] is True
    assert openai_settings["apiKeyMasked"].startswith("sk-o")
    assert openai_settings["apiKeyMasked"].endswith("3456")

    assert persisted_setting is not None
    encrypted_key = persisted_setting["payload"]["providers"]["openai"]["api_key"]
    assert isinstance(encrypted_key, str)
    assert encrypted_key.startswith(ENCRYPTED_TEXT_PREFIX)
    assert read_response.json()["settings"]["providers"]["claude"]["hasApiKey"] is True


def test_update_agent_api_settings_partial_update_keeps_existing_key(
    tmp_path: Path,
    monkeypatch,
    auth_headers_factory,
) -> None:
    service = _sqlite_service(tmp_path, InMemoryStore())
    monkeypatch.setattr(settings_service, "persistence_service", service)
    auth_headers = auth_headers_factory()
    service.persist_system_setting(
        key="agent_api",
        payload={
            "providers": {
                "openai": {
                    "enabled": True,
                    "base_url": "https://api.openai.com/v1",
                    "model": "gpt-4.1",
                    "organization_id": None,
                    "project_id": None,
                    "api_key": settings_service.encryption_service.encrypt_text("sk-existing-openai-1111"),
                }
            }
        },
        updated_at="2026-04-08T00:00:00+00:00",
    )

    try:
        update_response = client.put(
            "/api/settings/agent-api",
            headers=auth_headers,
            json={
                "providers": {
                    "openai": {
                        "model": "gpt-5.1",
                    }
                }
            },
        )
        persisted_setting = service.get_system_setting("agent_api")
    finally:
        service.close()

    assert update_response.status_code == 200
    assert update_response.json()["settings"]["providers"]["openai"]["model"] == "gpt-5.1"
    assert update_response.json()["settings"]["providers"]["openai"]["hasApiKey"] is True
    assert persisted_setting is not None
    assert persisted_setting["payload"]["providers"]["openai"]["api_key"].startswith(ENCRYPTED_TEXT_PREFIX)


def test_update_agent_api_settings_can_clear_existing_key(
    tmp_path: Path,
    monkeypatch,
    auth_headers_factory,
) -> None:
    service = _sqlite_service(tmp_path, InMemoryStore())
    monkeypatch.setattr(settings_service, "persistence_service", service)
    auth_headers = auth_headers_factory()
    service.persist_system_setting(
        key="agent_api",
        payload={
            "providers": {
                "kimi": {
                    "enabled": True,
                    "base_url": "https://api.moonshot.cn/v1",
                    "model": "moonshot",
                    "organization_id": None,
                    "project_id": None,
                    "api_key": settings_service.encryption_service.encrypt_text("sk-kimi-existing-8888"),
                }
            }
        },
        updated_at="2026-04-08T00:00:00+00:00",
    )

    try:
        update_response = client.put(
            "/api/settings/agent-api",
            headers=auth_headers,
            json={
                "providers": {
                    "kimi": {
                        "clearApiKey": True,
                    }
                }
            },
        )
        persisted_setting = service.get_system_setting("agent_api")
    finally:
        service.close()

    assert update_response.status_code == 200
    assert update_response.json()["settings"]["providers"]["kimi"]["hasApiKey"] is False
    assert update_response.json()["settings"]["providers"]["kimi"]["apiKeyMasked"] is None
    assert persisted_setting is not None
    assert persisted_setting["payload"]["providers"]["kimi"]["api_key"] is None


def test_viewer_cannot_update_agent_api_settings(
    viewer_auth_headers: dict[str, str],
) -> None:
    response = client.put(
        "/api/settings/agent-api",
        headers=viewer_auth_headers,
        json={
            "providers": {
                "openai": {
                    "enabled": True,
                }
            }
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied"


def test_channel_integrations_route_returns_defaults(auth_headers) -> None:
    response = client.get("/api/settings/channel-integrations", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["key"] == "channel_integrations"
    assert payload["settings"]["telegram"] == {
        "enabled": settings_service.DEFAULT_CHANNEL_INTEGRATION_SETTINGS["telegram"]["enabled"],
        "apiBaseUrl": settings_service.DEFAULT_CHANNEL_INTEGRATION_SETTINGS["telegram"]["api_base_url"],
        "httpTimeoutSeconds": settings_service.DEFAULT_CHANNEL_INTEGRATION_SETTINGS["telegram"][
            "http_timeout_seconds"
        ],
        "hasBotToken": bool(settings_service.DEFAULT_CHANNEL_INTEGRATION_SETTINGS["telegram"]["bot_token"]),
        "botTokenMasked": settings_service._mask_secret_value(
            settings_service.DEFAULT_CHANNEL_INTEGRATION_SETTINGS["telegram"]["bot_token"]
        ),
        "hasWebhookSecret": bool(
            settings_service.DEFAULT_CHANNEL_INTEGRATION_SETTINGS["telegram"]["webhook_secret"]
        ),
        "webhookSecretMasked": settings_service._mask_secret_value(
            settings_service.DEFAULT_CHANNEL_INTEGRATION_SETTINGS["telegram"]["webhook_secret"]
        ),
    }
    assert payload["settings"]["wecom"]["enabled"] is True
    assert payload["settings"]["dingtalk"]["enabled"] is True
    assert payload["settings"]["dingtalk"]["appId"] == settings_service.DEFAULT_CHANNEL_INTEGRATION_SETTINGS["dingtalk"]["app_id"]
    assert payload["settings"]["dingtalk"]["agentId"] == settings_service.DEFAULT_CHANNEL_INTEGRATION_SETTINGS["dingtalk"]["agent_id"]
    assert payload["settings"]["dingtalk"]["clientId"] == settings_service.DEFAULT_CHANNEL_INTEGRATION_SETTINGS["dingtalk"]["client_id"]
    assert payload["settings"]["dingtalk"]["corpId"] == settings_service.DEFAULT_CHANNEL_INTEGRATION_SETTINGS["dingtalk"]["corp_id"]
    assert payload["settings"]["dingtalk"]["hasClientSecret"] is bool(
        settings_service.DEFAULT_CHANNEL_INTEGRATION_SETTINGS["dingtalk"]["client_secret"]
    )


def test_update_channel_integrations_persists_encrypted_secrets_and_returns_masked_values(
    tmp_path: Path,
    monkeypatch,
    auth_headers_factory,
) -> None:
    service = _sqlite_service(tmp_path, InMemoryStore())
    monkeypatch.setattr(settings_service, "persistence_service", service)
    monkeypatch.setattr(
        "app.api.routes.settings.dingtalk_stream_service.reconcile_runtime",
        lambda: True,
    )
    auth_headers = auth_headers_factory()

    try:
        update_response = client.put(
            "/api/settings/channel-integrations",
            headers=auth_headers,
            json={
                "telegram": {
                    "enabled": True,
                    "apiBaseUrl": "https://telegram.example.com",
                    "httpTimeoutSeconds": 22.5,
                    "botToken": "tg-secret-1234567890",
                    "webhookSecret": "tg-webhook-secret-1234",
                },
                "wecom": {
                    "enabled": False,
                    "webhookSecretHeader": "X-WeCom-Secret",
                    "webhookSecretQueryParam": "access_token",
                    "botWebhookBaseUrl": "https://qyapi.example.com/webhook/send",
                    "httpTimeoutSeconds": 18,
                    "botWebhookKey": "wecom-key-abcdef",
                    "webhookSecret": "wecom-secret-1234",
                },
                "dingtalk": {
                    "enabled": True,
                    "appId": "123456",
                    "agentId": "100001",
                    "clientId": "ding-client-id",
                    "clientSecret": "ding-client-secret-1234",
                    "corpId": "ding-corp-001",
                    "apiBaseUrl": "https://oapi.dingtalk.example.com",
                    "httpTimeoutSeconds": 25,
                    "webhookSecret": "ding-webhook-secret-8888",
                },
            },
        )
        read_response = client.get("/api/settings/channel-integrations", headers=auth_headers)
        persisted_setting = service.get_system_setting("channel_integrations")
    finally:
        service.close()

    assert update_response.status_code == 200
    assert read_response.status_code == 200

    telegram_settings = update_response.json()["settings"]["telegram"]
    assert telegram_settings["enabled"] is True
    assert telegram_settings["apiBaseUrl"] == "https://telegram.example.com"
    assert telegram_settings["hasBotToken"] is True
    assert telegram_settings["botTokenMasked"].startswith("tg-s")
    assert telegram_settings["hasWebhookSecret"] is True

    wecom_settings = update_response.json()["settings"]["wecom"]
    assert wecom_settings["enabled"] is False
    assert wecom_settings["webhookSecretHeader"] == "X-WeCom-Secret"
    assert wecom_settings["botWebhookBaseUrl"] == "https://qyapi.example.com/webhook/send"
    assert wecom_settings["hasBotWebhookKey"] is True
    assert wecom_settings["hasWebhookSecret"] is True

    dingtalk_settings = update_response.json()["settings"]["dingtalk"]
    assert dingtalk_settings["enabled"] is True
    assert dingtalk_settings["appId"] == "123456"
    assert dingtalk_settings["agentId"] == "100001"
    assert dingtalk_settings["clientId"] == "ding-client-id"
    assert dingtalk_settings["corpId"] == "ding-corp-001"
    assert dingtalk_settings["apiBaseUrl"] == "https://oapi.dingtalk.example.com"
    assert dingtalk_settings["hasClientSecret"] is True
    assert dingtalk_settings["hasWebhookSecret"] is True

    assert persisted_setting is not None
    persisted_payload = persisted_setting["payload"]
    assert persisted_payload["telegram"]["bot_token"].startswith(ENCRYPTED_TEXT_PREFIX)
    assert persisted_payload["telegram"]["webhook_secret"].startswith(ENCRYPTED_TEXT_PREFIX)
    assert persisted_payload["wecom"]["bot_webhook_key"].startswith(ENCRYPTED_TEXT_PREFIX)
    assert persisted_payload["wecom"]["webhook_secret"].startswith(ENCRYPTED_TEXT_PREFIX)
    assert persisted_payload["dingtalk"]["client_secret"].startswith(ENCRYPTED_TEXT_PREFIX)
    assert persisted_payload["dingtalk"]["webhook_secret"].startswith(ENCRYPTED_TEXT_PREFIX)


def test_update_channel_integrations_partial_update_keeps_existing_secret(
    tmp_path: Path,
    monkeypatch,
    auth_headers_factory,
) -> None:
    service = _sqlite_service(tmp_path, InMemoryStore())
    monkeypatch.setattr(settings_service, "persistence_service", service)
    auth_headers = auth_headers_factory()
    service.persist_system_setting(
        key="channel_integrations",
        payload={
            "telegram": {
                "enabled": True,
                "api_base_url": "https://api.telegram.org",
                "http_timeout_seconds": 10.0,
                "bot_token": settings_service.encryption_service.encrypt_text("tg-existing-secret-1111"),
                "webhook_secret": settings_service.encryption_service.encrypt_text(
                    "tg-existing-webhook-2222"
                ),
            }
        },
        updated_at="2026-04-08T00:00:00+00:00",
    )

    try:
        update_response = client.put(
            "/api/settings/channel-integrations",
            headers=auth_headers,
            json={
                "telegram": {
                    "httpTimeoutSeconds": 33,
                }
            },
        )
        persisted_setting = service.get_system_setting("channel_integrations")
    finally:
        service.close()

    assert update_response.status_code == 200
    assert update_response.json()["settings"]["telegram"]["httpTimeoutSeconds"] == 33.0
    assert update_response.json()["settings"]["telegram"]["hasBotToken"] is True
    assert update_response.json()["settings"]["telegram"]["hasWebhookSecret"] is True
    assert persisted_setting is not None
    assert persisted_setting["payload"]["telegram"]["bot_token"].startswith(ENCRYPTED_TEXT_PREFIX)
    assert persisted_setting["payload"]["telegram"]["webhook_secret"].startswith(ENCRYPTED_TEXT_PREFIX)


def test_update_channel_integrations_can_clear_existing_secret(
    tmp_path: Path,
    monkeypatch,
    auth_headers_factory,
) -> None:
    service = _sqlite_service(tmp_path, InMemoryStore())
    monkeypatch.setattr(settings_service, "persistence_service", service)
    auth_headers = auth_headers_factory()
    service.persist_system_setting(
        key="channel_integrations",
        payload={
            "wecom": {
                "enabled": True,
                "webhook_secret_header": "X-WorkBot-Webhook-Secret",
                "webhook_secret_query_param": "token",
                "bot_webhook_base_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send",
                "http_timeout_seconds": 10.0,
                "bot_webhook_key": settings_service.encryption_service.encrypt_text("wecom-existing-key-1111"),
                "webhook_secret": settings_service.encryption_service.encrypt_text("wecom-existing-secret"),
            }
        },
        updated_at="2026-04-08T00:00:00+00:00",
    )

    try:
        update_response = client.put(
            "/api/settings/channel-integrations",
            headers=auth_headers,
            json={
                "wecom": {
                    "clearBotWebhookKey": True,
                    "clearWebhookSecret": True,
                }
            },
        )
        persisted_setting = service.get_system_setting("channel_integrations")
    finally:
        service.close()

    assert update_response.status_code == 200
    assert update_response.json()["settings"]["wecom"]["hasBotWebhookKey"] is False
    assert update_response.json()["settings"]["wecom"]["botWebhookKeyMasked"] is None
    assert update_response.json()["settings"]["wecom"]["hasWebhookSecret"] is False
    assert update_response.json()["settings"]["wecom"]["webhookSecretMasked"] is None
    assert persisted_setting is not None
    assert persisted_setting["payload"]["wecom"]["bot_webhook_key"] is None
    assert persisted_setting["payload"]["wecom"]["webhook_secret"] is None


def test_channel_integration_singular_route_reads_legacy_key(
    tmp_path: Path,
    monkeypatch,
    auth_headers_factory,
) -> None:
    service = _sqlite_service(tmp_path, InMemoryStore())
    monkeypatch.setattr(settings_service, "persistence_service", service)
    auth_headers = auth_headers_factory()
    service.persist_system_setting(
        key="channel_integration",
        payload={
            "dingtalk": {
                "enabled": False,
                "api_base_url": "https://dingtalk.example.com",
                "http_timeout_seconds": 15.0,
                "webhook_secret_header": "X-Ding-Secret",
                "webhook_secret_query_param": "token",
                "webhook_secret": settings_service.encryption_service.encrypt_text("ding-secret-legacy"),
            }
        },
        updated_at="2026-04-08T00:00:00+00:00",
    )

    try:
        response = client.get("/api/settings/channel-integration", headers=auth_headers)
    finally:
        service.close()

    assert response.status_code == 200
    payload = response.json()
    assert payload["key"] == "channel_integrations"
    assert payload["settings"]["dingtalk"]["enabled"] is False
    assert payload["settings"]["dingtalk"]["apiBaseUrl"] == "https://dingtalk.example.com"
    assert payload["settings"]["dingtalk"]["hasWebhookSecret"] is True
