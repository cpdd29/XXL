from __future__ import annotations

from app.platform.observability.dashboard_service import export_audit_logs_csv, get_audit_logs
from app.platform.persistence.runtime_store import store


def test_audit_logs_include_operator_friendly_fields_for_external_registry_events() -> None:
    store.audit_logs[:] = [
        {
            "id": "audit-ext-agent-001",
            "timestamp": "2026-05-03T14:40:00+00:00",
            "action": "external_agent_registry.registered",
            "user": "system",
            "resource": "external_agent_registry",
            "status": "success",
            "ip": "-",
            "details": "id=hermes-reception-v1; version=1.0.0; release_channel=stable; deprecated=False",
            "metadata": {
                "agent_id": "hermes-reception-v1",
                "agent_family": "hermes-reception",
                "version": "1.0.0",
                "release_channel": "stable",
                "default_version": True,
            },
        }
    ]

    result = get_audit_logs()

    assert result["total"] == 1
    item = result["items"][0]
    assert item["action_label"] == "外接智能体已注册"
    assert item["resource_label"] == "外接智能体注册表"
    assert item["module_label"] == "外接智能体治理"
    assert "hermes-reception-v1" in str(item["operator_summary"])
    assert "正式" in str(item["operator_summary"])


def test_audit_logs_search_matches_operator_friendly_labels() -> None:
    store.audit_logs[:] = [
        {
            "id": "audit-ext-agent-002",
            "timestamp": "2026-05-03T14:41:00+00:00",
            "action": "external_agent_registry.registered",
            "user": "system",
            "resource": "external_agent_registry",
            "status": "success",
            "ip": "-",
            "details": "id=hermes-reception-v1; version=1.0.0; release_channel=stable; deprecated=False",
            "metadata": {
                "agent_id": "hermes-reception-v1",
                "version": "1.0.0",
                "release_channel": "stable",
            },
        }
    ]

    result = get_audit_logs(search="外接智能体已注册")

    assert result["total"] == 1
    assert result["items"][0]["id"] == "audit-ext-agent-002"


def test_audit_log_csv_export_prefers_operator_friendly_columns() -> None:
    store.audit_logs[:] = [
        {
            "id": "audit-ext-agent-003",
            "timestamp": "2026-05-03T14:42:00+00:00",
            "action": "external_agent_registry.registered",
            "user": "system",
            "resource": "external_agent_registry",
            "status": "success",
            "ip": "-",
            "details": "id=hermes-reception-v1; version=1.0.0; release_channel=stable; deprecated=False",
            "metadata": {
                "agent_id": "hermes-reception-v1",
                "version": "1.0.0",
                "release_channel": "stable",
            },
        }
    ]

    csv_content = export_audit_logs_csv()

    assert "事件类型" in csv_content
    assert "运营摘要" in csv_content
    assert "外接智能体已注册" in csv_content
    assert "外接智能体注册表" in csv_content
