from __future__ import annotations

from pathlib import Path

from app.services import mandatory_agent_registry_service
from app.services.agent_config_service import AgentConfigService
from app.services.persistence_service import StatePersistenceService
from app.services.store import InMemoryStore


def _sqlite_service(tmp_path: Path, seeded_store: InMemoryStore) -> StatePersistenceService:
    database_path = tmp_path / "mandatory-agents.db"
    service = StatePersistenceService(
        runtime_store=seeded_store,
        database_url=f"sqlite:///{database_path}",
    )
    assert service.initialize() is True
    return service


def test_ensure_mandatory_agents_registered_creates_all_agents(tmp_path: Path, monkeypatch) -> None:
    runtime_store = InMemoryStore()
    runtime_store.agents = []
    service = _sqlite_service(tmp_path, runtime_store)
    config_root = Path(__file__).resolve().parents[2] / "agents"

    original_persistence_service = mandatory_agent_registry_service.persistence_service
    original_agent_config_service = mandatory_agent_registry_service.agent_config_service
    original_store = mandatory_agent_registry_service.store
    monkeypatch.setattr(mandatory_agent_registry_service, "persistence_service", service)
    monkeypatch.setattr(
        mandatory_agent_registry_service,
        "agent_config_service",
        AgentConfigService(config_root=config_root),
    )
    monkeypatch.setattr(mandatory_agent_registry_service, "store", runtime_store)

    try:
        payload = mandatory_agent_registry_service.ensure_mandatory_agents_registered()
        persisted_ids = [item["id"] for item in service.list_agents() or []]
        conversation = service.get_agent("conversation")
        requirement_dispatcher = service.get_agent("requirement_dispatcher")
        security = service.get_agent("security")
        security_guardian = service.get_agent("security-guardian")
        workflow_designer = service.get_agent("workflow_designer")
        memory = service.get_agent("memory")
    finally:
        monkeypatch.setattr(mandatory_agent_registry_service, "persistence_service", original_persistence_service)
        monkeypatch.setattr(
            mandatory_agent_registry_service,
            "agent_config_service",
            original_agent_config_service,
        )
        monkeypatch.setattr(mandatory_agent_registry_service, "store", original_store)
        service.close()

    assert payload["ok"] is True
    assert payload["created"] == [
        "conversation",
        "requirement_dispatcher",
        "security",
        "security-guardian",
        "workflow_designer",
        "memory",
    ]
    assert payload["updated"] == []
    assert persisted_ids == [
        "conversation",
        "requirement_dispatcher",
        "security",
        "security-guardian",
        "workflow_designer",
        "memory",
    ]
    assert conversation is not None
    assert conversation["type"] == "conversation"
    assert conversation["config_snapshot"]["status"] == "loaded"
    assert conversation["config_snapshot"]["agent"]["agent_family"] == "conversation"
    assert "help" in conversation["config_snapshot"]["agent"]["trigger_intents"]
    assert requirement_dispatcher is not None
    assert requirement_dispatcher["type"] == "task_dispatcher"
    assert requirement_dispatcher["config_snapshot"]["status"] == "loaded"
    assert requirement_dispatcher["config_snapshot"]["agent"]["agent_family"] == "task_dispatcher"
    assert security is not None
    assert security["config_snapshot"]["agent"]["agent_family"] == "security"
    assert security_guardian is not None
    assert security_guardian["type"] == "security_guardian"
    assert security_guardian["config_snapshot"]["status"] == "loaded"
    assert security_guardian["config_snapshot"]["agent"]["agent_family"] == "security_guardian"
    assert workflow_designer is not None
    assert workflow_designer["config_snapshot"]["agent"]["approval_required"] is True
    assert memory is not None
    assert memory["config_snapshot"]["agent"]["agent_family"] == "memory"


def test_ensure_mandatory_agents_registered_is_idempotent_and_keeps_runtime_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime_store = InMemoryStore()
    runtime_store.agents = []
    service = _sqlite_service(tmp_path, runtime_store)
    config_root = Path(__file__).resolve().parents[2] / "agents"

    original_persistence_service = mandatory_agent_registry_service.persistence_service
    original_agent_config_service = mandatory_agent_registry_service.agent_config_service
    original_store = mandatory_agent_registry_service.store
    monkeypatch.setattr(mandatory_agent_registry_service, "persistence_service", service)
    monkeypatch.setattr(
        mandatory_agent_registry_service,
        "agent_config_service",
        AgentConfigService(config_root=config_root),
    )
    monkeypatch.setattr(mandatory_agent_registry_service, "store", runtime_store)

    try:
        mandatory_agent_registry_service.ensure_mandatory_agents_registered()
        security = next(agent for agent in runtime_store.agents if agent["id"] == "security")
        security["status"] = "running"
        security["last_active"] = "刚刚"
        security["config_snapshot"]["runtime"] = {
            "last_heartbeat_at": "2026-04-18T00:00:00+00:00",
            "heartbeat_interval_seconds": 10,
            "heartbeat_timeout_seconds": 60,
        }
        service.persist_agent_state(agent=security)

        payload = mandatory_agent_registry_service.ensure_mandatory_agents_registered()
        persisted = service.get_agent("security")
    finally:
        monkeypatch.setattr(mandatory_agent_registry_service, "persistence_service", original_persistence_service)
        monkeypatch.setattr(
            mandatory_agent_registry_service,
            "agent_config_service",
            original_agent_config_service,
        )
        monkeypatch.setattr(mandatory_agent_registry_service, "store", original_store)
        service.close()

    assert payload["created"] == []
    assert payload["updated"] == [
        "conversation",
        "requirement_dispatcher",
        "security",
        "security-guardian",
        "workflow_designer",
        "memory",
    ]
    assert persisted is not None
    assert persisted["status"] == "running"
    assert persisted["config_snapshot"]["runtime"]["heartbeat_interval_seconds"] == 10
