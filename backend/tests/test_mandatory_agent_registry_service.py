from __future__ import annotations

from pathlib import Path

from app.services import agent_service, mandatory_agent_registry_service, mandatory_workflow_registry_service
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


def _expected_mandatory_agent_ids() -> list[str]:
    return [
        str(spec["id"])
        for spec in mandatory_agent_registry_service._active_mandatory_agent_specs()
    ]


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
        general_assistant = service.get_agent("general_assistant")
        requirement_dispatcher = service.get_agent("requirement_dispatcher")
        security = service.get_agent("security")
        security_guardian = service.get_agent("security-guardian")
        workflow_designer = service.get_agent("workflow_designer")
        memory = service.get_agent("memory")
        search = service.get_agent("search")
        write = service.get_agent("write")
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
    assert payload["created"] == _expected_mandatory_agent_ids()
    assert payload["updated"] == []
    assert persisted_ids == _expected_mandatory_agent_ids()
    assert conversation is not None
    assert conversation["type"] == "conversation"
    assert conversation["config_snapshot"]["status"] == "loaded"
    assert conversation["config_snapshot"]["agent"]["agent_family"] == "conversation"
    assert "help" in conversation["config_snapshot"]["agent"]["trigger_intents"]
    conversation_workflow_binding = (
        (conversation["config_snapshot"].get("runtime") or {}).get("agent_workflow_binding")
        if isinstance(conversation.get("config_snapshot"), dict)
        else None
    )
    if (
        conversation["config_snapshot"]["agent"].get("agent_workflow_id")
        or isinstance(conversation_workflow_binding, dict)
    ):
        assert (
            conversation["config_snapshot"]["agent"]["agent_workflow_id"]
            == mandatory_workflow_registry_service.CONVERSATION_AGENT_PIPELINE_WORKFLOW_ID
        )
        assert (
            conversation["config_snapshot"]["agent"]["input_contract"]
            == mandatory_workflow_registry_service.CONVERSATION_AGENT_PIPELINE_INPUT_CONTRACT
        )
        assert (
            conversation["config_snapshot"]["agent"]["output_contract"]
            == mandatory_workflow_registry_service.CONVERSATION_AGENT_PIPELINE_OUTPUT_CONTRACT
        )
        assert (
            conversation["config_snapshot"]["agent"]["contract_version"]
            == mandatory_workflow_registry_service.CONVERSATION_AGENT_PIPELINE_CONTRACT_VERSION
        )
        assert conversation_workflow_binding is not None
        assert (
            conversation_workflow_binding["agent_workflow_id"]
            == mandatory_workflow_registry_service.CONVERSATION_AGENT_PIPELINE_WORKFLOW_ID
        )
    assert general_assistant is not None
    assert general_assistant["type"] == "default"
    assert general_assistant["config_snapshot"]["status"] == "loaded"
    assert general_assistant["config_snapshot"]["agent"]["agent_family"] == "default"
    assert (
        general_assistant["config_snapshot"]["agent"]["agent_workflow_id"]
        == mandatory_workflow_registry_service.GENERAL_ASSISTANT_AGENT_PIPELINE_WORKFLOW_ID
    )
    assert (
        general_assistant["config_snapshot"]["agent"]["input_contract"]
        == mandatory_workflow_registry_service.GENERAL_ASSISTANT_AGENT_PIPELINE_INPUT_CONTRACT
    )
    assert (
        general_assistant["config_snapshot"]["agent"]["output_contract"]
        == mandatory_workflow_registry_service.GENERAL_ASSISTANT_AGENT_PIPELINE_OUTPUT_CONTRACT
    )
    assert (
        general_assistant["config_snapshot"]["agent"]["contract_version"]
        == mandatory_workflow_registry_service.GENERAL_ASSISTANT_AGENT_PIPELINE_CONTRACT_VERSION
    )
    assert (
        general_assistant["config_snapshot"]["runtime"]["agent_workflow_binding"]["agent_workflow_id"]
        == mandatory_workflow_registry_service.GENERAL_ASSISTANT_AGENT_PIPELINE_WORKFLOW_ID
    )
    assert requirement_dispatcher is not None
    assert requirement_dispatcher["type"] == "task_dispatcher"
    assert requirement_dispatcher["config_snapshot"]["status"] == "loaded"
    assert requirement_dispatcher["config_snapshot"]["agent"]["agent_family"] == "task_dispatcher"
    assert "agent_workflow_id" not in requirement_dispatcher["config_snapshot"]["agent"]
    assert "input_contract" not in requirement_dispatcher["config_snapshot"]["agent"]
    assert "output_contract" not in requirement_dispatcher["config_snapshot"]["agent"]
    assert "contract_version" not in requirement_dispatcher["config_snapshot"]["agent"]
    runtime = requirement_dispatcher["config_snapshot"].get("runtime") or {}
    assert "agent_workflow_binding" not in runtime
    assert security is not None
    assert security["config_snapshot"]["agent"]["agent_family"] == "security"
    assert (
        security["config_snapshot"]["agent"]["agent_workflow_id"]
        == mandatory_workflow_registry_service.SECURITY_AGENT_PIPELINE_WORKFLOW_ID
    )
    assert (
        security["config_snapshot"]["agent"]["input_contract"]
        == mandatory_workflow_registry_service.SECURITY_AGENT_PIPELINE_INPUT_CONTRACT
    )
    assert (
        security["config_snapshot"]["agent"]["output_contract"]
        == mandatory_workflow_registry_service.SECURITY_AGENT_PIPELINE_OUTPUT_CONTRACT
    )
    assert (
        security["config_snapshot"]["agent"]["contract_version"]
        == mandatory_workflow_registry_service.SECURITY_AGENT_PIPELINE_CONTRACT_VERSION
    )
    assert (
        security["config_snapshot"]["runtime"]["agent_workflow_binding"]["agent_workflow_id"]
        == mandatory_workflow_registry_service.SECURITY_AGENT_PIPELINE_WORKFLOW_ID
    )
    assert security_guardian is None
    assert workflow_designer is None
    assert memory is None
    assert search is None
    assert write is None


def test_list_agents_exposes_mandatory_agent_projections_when_database_is_empty(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime_store = InMemoryStore()
    runtime_store.agents = []
    service = _sqlite_service(tmp_path, runtime_store)
    config_root = Path(__file__).resolve().parents[2] / "agents"

    original_agent_service_persistence = agent_service.persistence_service
    original_agent_service_store = agent_service.store
    original_registry_agent_config_service = mandatory_agent_registry_service.agent_config_service
    original_registry_store = mandatory_agent_registry_service.store
    monkeypatch.setattr(agent_service, "persistence_service", service)
    monkeypatch.setattr(agent_service, "store", runtime_store)
    monkeypatch.setattr(
        mandatory_agent_registry_service,
        "agent_config_service",
        AgentConfigService(config_root=config_root),
    )
    monkeypatch.setattr(mandatory_agent_registry_service, "store", runtime_store)

    try:
        payload = agent_service.list_agents()
        fetched_security = agent_service.get_agent("security")
        persisted_agents = service.list_agents() or []
    finally:
        monkeypatch.setattr(agent_service, "persistence_service", original_agent_service_persistence)
        monkeypatch.setattr(agent_service, "store", original_agent_service_store)
        monkeypatch.setattr(
            mandatory_agent_registry_service,
            "agent_config_service",
            original_registry_agent_config_service,
        )
        monkeypatch.setattr(mandatory_agent_registry_service, "store", original_registry_store)
        service.close()

    assert [item["id"] for item in payload["items"]] == _expected_mandatory_agent_ids()
    assert fetched_security["id"] == "security"
    assert fetched_security["agent_workflow_id"] == mandatory_workflow_registry_service.SECURITY_AGENT_PIPELINE_WORKFLOW_ID
    assert persisted_agents == []


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
    assert payload["updated"] == _expected_mandatory_agent_ids()
    assert persisted is not None
    assert persisted["status"] == "running"
    assert persisted["config_snapshot"]["runtime"]["heartbeat_interval_seconds"] == 10


def test_ensure_mandatory_agents_registered_clears_removed_workflow_bindings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime_store = InMemoryStore()
    runtime_store.agents = []
    service = _sqlite_service(tmp_path, runtime_store)
    config_root = Path(__file__).resolve().parents[2] / "agents"
    removed_workflow_id = "mandatory-workflow-delivery-note-export-and-send"

    dirty_agent = {
        "id": "requirement_dispatcher",
        "name": "需求分析任务分发 Agent",
        "description": "旧绑定清理测试",
        "type": "task_dispatcher",
        "status": "idle",
        "enabled": True,
        "tasks_completed": 0,
        "tasks_total": 0,
        "avg_response_time": "--",
        "tokens_used": 0,
        "tokens_limit": 0,
        "success_rate": 0.0,
        "last_active": "未运行",
        "agent_workflow_id": removed_workflow_id,
        "input_contract": {
            "fields": ["structured_request_packet"],
            "required": ["structured_request_packet"],
        },
        "output_contract": {
            "fields": ["route_decision"],
            "required": ["route_decision"],
        },
        "contract_version": "agent-workflow-contract-v1",
        "config_snapshot": {
            "status": "loaded",
            "agent": {
                "agent_id": "requirement_dispatcher",
                "name": "需求分析任务分发 Agent",
                "agent_family": "task_dispatcher",
                "type": "task_dispatcher",
                "agent_workflow_id": removed_workflow_id,
                "input_contract": {
                    "fields": ["structured_request_packet"],
                    "required": ["structured_request_packet"],
                },
                "output_contract": {
                    "fields": ["route_decision"],
                    "required": ["route_decision"],
                },
                "contract_version": "agent-workflow-contract-v1",
            },
            "runtime": {
                "agent_workflow_binding": {
                    "agent_workflow_id": removed_workflow_id,
                    "input_contract": {
                        "fields": ["structured_request_packet"],
                        "required": ["structured_request_packet"],
                    },
                    "output_contract": {
                        "fields": ["route_decision"],
                        "required": ["route_decision"],
                    },
                    "contract_version": "agent-workflow-contract-v1",
                    "source": "manual",
                }
            },
        },
    }
    runtime_store.agents.append(dirty_agent)
    assert service.persist_agent_state(agent=dirty_agent) is True

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
        persisted = service.get_agent("requirement_dispatcher")
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
    assert persisted is not None
    assert persisted["config_snapshot"]["agent"]["agent_family"] == "task_dispatcher"
    assert "agent_workflow_id" not in persisted["config_snapshot"]["agent"]
    assert "input_contract" not in persisted["config_snapshot"]["agent"]
    assert "output_contract" not in persisted["config_snapshot"]["agent"]
    assert "contract_version" not in persisted["config_snapshot"]["agent"]
    runtime = persisted["config_snapshot"].get("runtime") or {}
    assert "agent_workflow_binding" not in runtime


def test_ensure_mandatory_agents_registered_preserves_builtin_runtime_bindings(
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
        general_assistant = next(
            agent for agent in runtime_store.agents if agent["id"] == "general_assistant"
        )
        general_assistant["config_snapshot"]["runtime"] = {
            "last_heartbeat_at": "2026-04-18T00:00:00+00:00",
            "heartbeat_interval_seconds": 12,
            "heartbeat_timeout_seconds": 60,
            "agent_binding": {
                "provider_key": "openai",
                "model": "gpt-5-mini",
                "source": "manual",
            },
        }
        service.persist_agent_state(agent=general_assistant)

        payload = mandatory_agent_registry_service.ensure_mandatory_agents_registered()
        persisted = service.get_agent("general_assistant")
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
    assert persisted is not None
    assert persisted["config_snapshot"]["status"] == "loaded"
    assert persisted["config_snapshot"]["runtime"]["heartbeat_interval_seconds"] == 12
    assert persisted["config_snapshot"]["runtime"]["agent_binding"]["model"] == "gpt-5-mini"


def test_ensure_mandatory_agents_registered_exposes_security_agent_workflow_binding(
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
    original_agent_service_persistence = agent_service.persistence_service
    original_agent_service_store = agent_service.store
    monkeypatch.setattr(mandatory_agent_registry_service, "persistence_service", service)
    monkeypatch.setattr(
        mandatory_agent_registry_service,
        "agent_config_service",
        AgentConfigService(config_root=config_root),
    )
    monkeypatch.setattr(mandatory_agent_registry_service, "store", runtime_store)
    monkeypatch.setattr(agent_service, "persistence_service", service)
    monkeypatch.setattr(agent_service, "store", runtime_store)

    try:
        mandatory_agent_registry_service.ensure_mandatory_agents_registered()
        decorated_security = next(
            agent for agent in (agent_service.list_agents().get("items") or []) if agent["id"] == "security"
        )
    finally:
        monkeypatch.setattr(mandatory_agent_registry_service, "persistence_service", original_persistence_service)
        monkeypatch.setattr(
            mandatory_agent_registry_service,
            "agent_config_service",
            original_agent_config_service,
        )
        monkeypatch.setattr(mandatory_agent_registry_service, "store", original_store)
        monkeypatch.setattr(agent_service, "persistence_service", original_agent_service_persistence)
        monkeypatch.setattr(agent_service, "store", original_agent_service_store)
        service.close()

    assert (
        decorated_security["agent_workflow_id"]
        == mandatory_workflow_registry_service.SECURITY_AGENT_PIPELINE_WORKFLOW_ID
    )
    assert (
        decorated_security["input_contract"]
        == mandatory_workflow_registry_service.SECURITY_AGENT_PIPELINE_INPUT_CONTRACT
    )
    assert (
        decorated_security["output_contract"]
        == mandatory_workflow_registry_service.SECURITY_AGENT_PIPELINE_OUTPUT_CONTRACT
    )
    assert (
        decorated_security["contract_version"]
        == mandatory_workflow_registry_service.SECURITY_AGENT_PIPELINE_CONTRACT_VERSION
    )


def test_ensure_mandatory_agents_registered_exposes_conversation_agent_workflow_binding(
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
    original_agent_service_persistence = agent_service.persistence_service
    original_agent_service_store = agent_service.store
    monkeypatch.setattr(mandatory_agent_registry_service, "persistence_service", service)
    monkeypatch.setattr(
        mandatory_agent_registry_service,
        "agent_config_service",
        AgentConfigService(config_root=config_root),
    )
    monkeypatch.setattr(mandatory_agent_registry_service, "store", runtime_store)
    monkeypatch.setattr(agent_service, "persistence_service", service)
    monkeypatch.setattr(agent_service, "store", runtime_store)

    try:
        mandatory_agent_registry_service.ensure_mandatory_agents_registered()
        decorated_conversation = next(
            agent for agent in (agent_service.list_agents().get("items") or []) if agent["id"] == "conversation"
        )
    finally:
        monkeypatch.setattr(mandatory_agent_registry_service, "persistence_service", original_persistence_service)
        monkeypatch.setattr(
            mandatory_agent_registry_service,
            "agent_config_service",
            original_agent_config_service,
        )
        monkeypatch.setattr(mandatory_agent_registry_service, "store", original_store)
        monkeypatch.setattr(agent_service, "persistence_service", original_agent_service_persistence)
        monkeypatch.setattr(agent_service, "store", original_agent_service_store)
        service.close()

    assert (
        decorated_conversation["agent_workflow_id"]
        == mandatory_workflow_registry_service.CONVERSATION_AGENT_PIPELINE_WORKFLOW_ID
    )
    assert (
        decorated_conversation["input_contract"]
        == mandatory_workflow_registry_service.CONVERSATION_AGENT_PIPELINE_INPUT_CONTRACT
    )
    assert (
        decorated_conversation["output_contract"]
        == mandatory_workflow_registry_service.CONVERSATION_AGENT_PIPELINE_OUTPUT_CONTRACT
    )
    assert (
        decorated_conversation["contract_version"]
        == mandatory_workflow_registry_service.CONVERSATION_AGENT_PIPELINE_CONTRACT_VERSION
    )


def test_ensure_mandatory_agents_registered_exposes_general_assistant_agent_workflow_binding(
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
    original_agent_service_persistence = agent_service.persistence_service
    original_agent_service_store = agent_service.store
    monkeypatch.setattr(mandatory_agent_registry_service, "persistence_service", service)
    monkeypatch.setattr(
        mandatory_agent_registry_service,
        "agent_config_service",
        AgentConfigService(config_root=config_root),
    )
    monkeypatch.setattr(mandatory_agent_registry_service, "store", runtime_store)
    monkeypatch.setattr(agent_service, "persistence_service", service)
    monkeypatch.setattr(agent_service, "store", runtime_store)

    try:
        mandatory_agent_registry_service.ensure_mandatory_agents_registered()
        decorated_general_assistant = next(
            agent for agent in (agent_service.list_agents().get("items") or []) if agent["id"] == "general_assistant"
        )
    finally:
        monkeypatch.setattr(mandatory_agent_registry_service, "persistence_service", original_persistence_service)
        monkeypatch.setattr(
            mandatory_agent_registry_service,
            "agent_config_service",
            original_agent_config_service,
        )
        monkeypatch.setattr(mandatory_agent_registry_service, "store", original_store)
        monkeypatch.setattr(agent_service, "persistence_service", original_agent_service_persistence)
        monkeypatch.setattr(agent_service, "store", original_agent_service_store)
        service.close()

    assert (
        decorated_general_assistant["agent_workflow_id"]
        == mandatory_workflow_registry_service.GENERAL_ASSISTANT_AGENT_PIPELINE_WORKFLOW_ID
    )
    assert (
        decorated_general_assistant["input_contract"]
        == mandatory_workflow_registry_service.GENERAL_ASSISTANT_AGENT_PIPELINE_INPUT_CONTRACT
    )
    assert (
        decorated_general_assistant["output_contract"]
        == mandatory_workflow_registry_service.GENERAL_ASSISTANT_AGENT_PIPELINE_OUTPUT_CONTRACT
    )
    assert (
        decorated_general_assistant["contract_version"]
        == mandatory_workflow_registry_service.GENERAL_ASSISTANT_AGENT_PIPELINE_CONTRACT_VERSION
    )
