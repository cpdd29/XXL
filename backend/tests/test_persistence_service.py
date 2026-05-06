from __future__ import annotations

from pathlib import Path

from app.platform.persistence.persistence_service import StatePersistenceService
from app.platform.persistence.runtime_store import InMemoryStore


def _sqlite_service(database_path: Path, runtime_store: InMemoryStore) -> StatePersistenceService:
    return StatePersistenceService(
        runtime_store=runtime_store,
        database_url=f"sqlite:///{database_path}",
    )


def test_read_system_setting_lazily_initializes_database_connection(tmp_path: Path) -> None:
    database_path = tmp_path / "persistence-lazy-read.db"
    writer_store = InMemoryStore()
    writer = _sqlite_service(database_path, writer_store)
    assert writer.initialize() is True
    assert writer.persist_system_setting(
        key="control_plane_approvals",
        payload={"items": [{"id": "approval-lazy-read-001", "status": "pending"}]},
        updated_at="2026-05-03T10:00:00+00:00",
    )
    writer.close()

    reader = _sqlite_service(database_path, InMemoryStore())
    payload, authoritative = reader.read_system_setting("control_plane_approvals")
    reader.close()

    assert authoritative is True
    assert payload is not None
    assert payload["payload"]["items"][0]["id"] == "approval-lazy-read-001"


def test_persist_system_setting_lazily_initializes_database_connection(tmp_path: Path) -> None:
    database_path = tmp_path / "persistence-lazy-write.db"
    writer = _sqlite_service(database_path, InMemoryStore())

    assert writer.persist_system_setting(
        key="security_policy",
        payload={"keyword_blocklist_enabled": True, "keyword_blocklist": ["机密词"]},
        updated_at="2026-05-03T10:05:00+00:00",
    )

    payload, authoritative = writer.read_system_setting("security_policy")
    writer.close()

    assert authoritative is True
    assert payload is not None
    assert payload["payload"]["keyword_blocklist_enabled"] is True
    assert payload["payload"]["keyword_blocklist"] == ["机密词"]


def test_persist_all_preserves_existing_system_settings_when_runtime_cache_is_partial(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "persistence-preserve-system-settings.db"

    seed_store = InMemoryStore()
    seed = _sqlite_service(database_path, seed_store)
    assert seed.initialize() is True
    assert seed.persist_system_setting(
        key="profile_tenants",
        payload={"items": [{"id": "tenant-001", "name": "测试租户"}]},
        updated_at="2026-05-05T10:00:00+00:00",
    )
    assert seed.persist_system_setting(
        key="channel_integrations",
        payload={
            "wecom": {
                "enabled": True,
                "tenant_id": "tenant-001",
                "tenant_name": "测试租户",
            }
        },
        updated_at="2026-05-05T10:01:00+00:00",
    )
    seed.close()

    runtime_store = InMemoryStore()
    service = _sqlite_service(database_path, runtime_store)
    assert service.initialize() is True

    runtime_store.system_settings = {
        "general": {
            "dashboard_auto_refresh": False,
            "show_system_status": True,
        },
        "agent_api": runtime_store.clone(runtime_store.system_settings.get("agent_api")),
    }

    assert service.persist_all() is True

    profile_tenants, profile_tenants_authoritative = service.read_system_setting("profile_tenants")
    channel_integrations, channel_integrations_authoritative = service.read_system_setting(
        "channel_integrations"
    )
    general, general_authoritative = service.read_system_setting("general")
    service.close()

    assert profile_tenants_authoritative is True
    assert profile_tenants is not None
    assert profile_tenants["payload"]["items"][0]["id"] == "tenant-001"

    assert channel_integrations_authoritative is True
    assert channel_integrations is not None
    assert channel_integrations["payload"]["wecom"]["enabled"] is True
    assert channel_integrations["payload"]["wecom"]["tenant_id"] == "tenant-001"

    assert general_authoritative is True
    assert general is not None
    assert general["payload"]["dashboard_auto_refresh"] is False
