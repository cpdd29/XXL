from __future__ import annotations

import app.modules.organization.application.profile_service as profile_service
from app.modules.organization.application.profile_service import TENANT_DIRECTORY_SETTING_KEY
from app.platform.persistence.runtime_store import store


def test_load_tenant_catalog_prefers_persisted_setting_and_syncs_runtime_cache(monkeypatch) -> None:
    persisted_payload = {
        "items": [
            {
                "id": "tenant-persisted",
                "name": "Persisted Tenant",
                "status": "active",
                "description": "来自数据库",
            }
        ],
        "updated_at": "2026-05-05T12:00:00+08:00",
    }

    monkeypatch.setattr(
        profile_service.persistence_service,
        "read_system_setting",
        lambda key: (
            {"key": key, "payload": persisted_payload, "updated_at": persisted_payload["updated_at"]},
            True,
        ),
    )

    previous = store.system_settings.pop(TENANT_DIRECTORY_SETTING_KEY, None)
    try:
        items = profile_service._load_tenant_catalog()
        assert items == [
            {
                "id": "tenant-persisted",
                "name": "Persisted Tenant",
                "status": "active",
                "description": "来自数据库",
                "service_registration": {
                    "status": None,
                    "code_hash": None,
                    "issued_at": None,
                    "consumed_at": None,
                    "history": [],
                },
            }
        ]
        assert store.system_settings[TENANT_DIRECTORY_SETTING_KEY] == persisted_payload
    finally:
        if previous is None:
            store.system_settings.pop(TENANT_DIRECTORY_SETTING_KEY, None)
        else:
            store.system_settings[TENANT_DIRECTORY_SETTING_KEY] = previous
