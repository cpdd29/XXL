from __future__ import annotations

from pathlib import Path

import app.modules.agent_config.registries.external_agent_registry_service as registry_module
from app.platform.persistence.persistence_service import StatePersistenceService
from app.platform.persistence.runtime_store import InMemoryStore


def _sqlite_service(database_path: Path, runtime_store: InMemoryStore) -> StatePersistenceService:
    return StatePersistenceService(
        runtime_store=runtime_store,
        database_url=f"sqlite:///{database_path}",
    )


def test_external_agent_registry_bootstraps_from_persistence_after_restart(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "external-agent-registry.db"
    runtime_store = InMemoryStore()
    service = _sqlite_service(database_path, runtime_store)
    assert service.initialize() is True

    monkeypatch.setattr(registry_module, "persistence_service", service)
    monkeypatch.setattr(registry_module, "store", runtime_store)
    registry_module.reset_external_agent_registry_state()

    try:
        created = registry_module.external_agent_registry_service.register_agent(
            {
                "id": "hermes-reception-v1",
                "name": "Hermes Reception",
                "type": "write",
                "agent_family": "hermes-reception",
                "base_url": "http://host.docker.internal:8642",
                "invoke_path": "/v1/chat/completions",
                "health_path": "/health",
                "method": "POST",
                "version": "1.0.0",
                "enabled": True,
            }
        )
        heartbeat = registry_module.external_agent_registry_service.report_heartbeat(
            created["id"],
            status="online",
            load=0.12,
            queue_depth=1,
            metadata={"source": "pytest"},
        )
        persisted, authoritative = service.read_system_setting(
            registry_module.EXTERNAL_AGENT_REGISTRY_SETTING_KEY
        )

        registry_module.external_agent_registry_service.clear()
        bootstrapped_count = registry_module.external_agent_registry_service.bootstrap()
        restored = registry_module.external_agent_registry_service.get_agent(created["id"])
        restarted_heartbeat = registry_module.external_agent_registry_service.report_heartbeat(
            created["id"],
            status="degraded",
            queue_depth=3,
        )
    finally:
        service.close()

    assert authoritative is True
    assert persisted is not None
    assert persisted["payload"]["items"][0]["id"] == created["id"]
    assert heartbeat["runtime_status"] == "online"
    assert heartbeat["routable"] is True
    assert bootstrapped_count == 1
    assert restored is not None
    assert restored["id"] == created["id"]
    assert restored["runtime_status"] == "online"
    assert restored["runtime_metrics"]["metadata"]["source"] == "pytest"
    assert restarted_heartbeat["id"] == created["id"]
    assert restarted_heartbeat["runtime_status"] == "degraded"
    assert restarted_heartbeat["routable"] is True


def test_external_agent_registry_reconciles_missing_invocation_from_persistence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "external-agent-registry-reconcile.db"
    runtime_store = InMemoryStore()
    service = _sqlite_service(database_path, runtime_store)
    assert service.initialize() is True

    monkeypatch.setattr(registry_module, "persistence_service", service)
    monkeypatch.setattr(registry_module, "store", runtime_store)
    registry_module.reset_external_agent_registry_state()

    try:
        created = registry_module.external_agent_registry_service.register_agent(
            {
                "id": "hermes-reception-v1",
                "name": "Hermes Reception",
                "type": "write",
                "agent_family": "hermes-reception",
                "base_url": "http://host.docker.internal:8642",
                "invoke_path": "/v1/chat/completions",
                "health_path": "/health",
                "method": "POST",
                "version": "1.0.0",
                "enabled": True,
                "metadata": {
                    "source": "control_plane",
                    "tags": ["外部 · 单智能体"],
                },
            }
        )
        corrupted = registry_module.external_agent_registry_service._agents[created["id"]]
        corrupted["config_summary"]["invocation"]["base_url"] = ""
        corrupted["config_summary"]["invocation"]["invoke_path"] = "/execute"
        corrupted["config_snapshot"]["runtime"]["invocation"]["base_url"] = ""
        corrupted["config_snapshot"]["runtime"]["invocation"]["invoke_path"] = "/execute"
        corrupted["config_snapshot"]["metadata"]["invocation"]["base_url"] = ""
        corrupted["config_snapshot"]["metadata"]["invocation"]["invoke_path"] = "/execute"

        restored = registry_module.external_agent_registry_service.get_agent(created["id"])
        heartbeat = registry_module.external_agent_registry_service.report_heartbeat(
            created["id"],
            status="online",
        )
    finally:
        service.close()

    assert restored is not None
    assert restored["config_summary"]["invocation"]["base_url"] == "http://host.docker.internal:8642"
    assert restored["config_summary"]["invocation"]["invoke_path"] == "/v1/chat/completions"
    assert restored["config_snapshot"]["metadata"]["tags"] == ["外部 · 单智能体"]
    assert heartbeat["config_summary"]["invocation"]["base_url"] == "http://host.docker.internal:8642"


def test_external_agent_registry_register_preserves_existing_invocation_when_payload_is_partial(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "external-agent-registry-merge.db"
    runtime_store = InMemoryStore()
    service = _sqlite_service(database_path, runtime_store)
    assert service.initialize() is True

    monkeypatch.setattr(registry_module, "persistence_service", service)
    monkeypatch.setattr(registry_module, "store", runtime_store)
    registry_module.reset_external_agent_registry_state()

    try:
        registry_module.external_agent_registry_service.register_agent(
            {
                "id": "hermes-reception-v1",
                "name": "Hermes Reception",
                "type": "write",
                "agent_family": "hermes-reception",
                "base_url": "http://host.docker.internal:8642",
                "invoke_path": "/v1/chat/completions",
                "health_path": "/health",
                "method": "POST",
                "version": "1.0.0",
                "enabled": True,
                "metadata": {
                    "source": "control_plane",
                    "tags": ["外部 · 单智能体"],
                },
            }
        )
        updated = registry_module.external_agent_registry_service.register_agent(
            {
                "id": "hermes-reception-v1",
                "name": "Hermes Reception",
                "type": "write",
                "version": "1.0.0",
                "metadata": {
                    "source": "hermes-agent",
                    "model": "hermes-agent",
                },
            }
        )
    finally:
        service.close()

    assert updated["config_summary"]["invocation"]["base_url"] == "http://host.docker.internal:8642"
    assert updated["config_summary"]["invocation"]["invoke_path"] == "/v1/chat/completions"
    assert updated["config_snapshot"]["metadata"]["tags"] == ["外部 · 单智能体"]
    assert updated["config_snapshot"]["metadata"]["model"] == "hermes-agent"
