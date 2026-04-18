from __future__ import annotations

from pathlib import Path

from app.services import mandatory_workflow_registry_service
from app.services import workflow_execution_service, workflow_service
from app.services.persistence_service import StatePersistenceService
from app.services.store import InMemoryStore, store


def _replace_global_store(seeded_store: InMemoryStore) -> None:
    store.__dict__.clear()
    store.__dict__.update(store.clone(seeded_store.__dict__))


def _sqlite_service(tmp_path: Path, seeded_store: InMemoryStore) -> StatePersistenceService:
    database_path = tmp_path / "mandatory-workflows.db"
    _replace_global_store(seeded_store)
    service = StatePersistenceService(
        runtime_store=store,
        database_url=f"sqlite:///{database_path}",
    )
    assert service.initialize() is True
    return service


def test_ensure_mandatory_workflows_registered_creates_all_workflows(tmp_path: Path, monkeypatch) -> None:
    runtime_store = InMemoryStore()
    runtime_store.workflows = []
    service = _sqlite_service(tmp_path, runtime_store)

    original_persistence_service = mandatory_workflow_registry_service.persistence_service
    original_store = mandatory_workflow_registry_service.store
    monkeypatch.setattr(mandatory_workflow_registry_service, "persistence_service", service)
    monkeypatch.setattr(mandatory_workflow_registry_service, "store", runtime_store)

    try:
        payload = mandatory_workflow_registry_service.ensure_mandatory_workflows_registered()
        persisted_ids = [item["id"] for item in service.list_workflows() or []]
        brain_orchestrator = service.get_workflow("workflow-1")
        external_tentacle = service.get_workflow("mandatory-workflow-external-tentacle-dispatch")
        conversation = service.get_workflow("mandatory-workflow-conversation")
        security = service.get_workflow("mandatory-workflow-security")
        workflow_designer = service.get_workflow("mandatory-workflow-workflow-designer")
        memory = service.get_workflow("mandatory-workflow-memory")
    finally:
        monkeypatch.setattr(
            mandatory_workflow_registry_service,
            "persistence_service",
            original_persistence_service,
        )
        monkeypatch.setattr(mandatory_workflow_registry_service, "store", original_store)
        service.close()

    assert payload["ok"] is True
    assert payload["created"] == [
        "workflow-1",
        "mandatory-workflow-external-tentacle-dispatch",
        "mandatory-workflow-conversation",
        "mandatory-workflow-security",
        "mandatory-workflow-workflow-designer",
        "mandatory-workflow-memory",
    ]
    assert payload["updated"] == []
    assert persisted_ids == [
        "workflow-1",
        "mandatory-workflow-external-tentacle-dispatch",
        "mandatory-workflow-conversation",
        "mandatory-workflow-security",
        "mandatory-workflow-workflow-designer",
        "mandatory-workflow-memory",
    ]
    assert brain_orchestrator is not None
    assert brain_orchestrator["name"] == "主脑整体工作流"
    assert brain_orchestrator["trigger"]["type"] == "message"
    assert brain_orchestrator["trigger"]["channels"] == ["telegram", "dingtalk", "wecom", "feishu"]
    assert brain_orchestrator["nodes"][4]["workflow_id"] == "mandatory-workflow-external-tentacle-dispatch"
    assert brain_orchestrator["agent_bindings"] == ["security", "conversation", "requirement_dispatcher"]
    assert external_tentacle is not None
    assert external_tentacle["trigger"]["type"] == "manual"
    assert external_tentacle["agent_bindings"] == ["search", "write"]
    assert conversation is not None
    assert conversation["status"] == "active"
    assert conversation["agent_bindings"] == ["conversation"]
    assert conversation["trigger"]["internal_event"] == "mandatory.agent.conversation.requested"
    assert security is not None
    assert security["agent_bindings"] == ["security"]
    assert security["nodes"][1]["agent_id"] == "security"
    assert workflow_designer is not None
    assert workflow_designer["agent_bindings"] == ["workflow_designer"]
    assert workflow_designer["nodes"][1]["config"]["approval_required"] is True
    assert memory is not None
    assert memory["agent_bindings"] == ["memory"]
    assert memory["trigger"]["internal_event"] == "mandatory.agent.memory.distill_requested"


def test_ensure_mandatory_workflows_registered_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    runtime_store = InMemoryStore()
    runtime_store.workflows = []
    service = _sqlite_service(tmp_path, runtime_store)

    original_persistence_service = mandatory_workflow_registry_service.persistence_service
    original_store = mandatory_workflow_registry_service.store
    monkeypatch.setattr(mandatory_workflow_registry_service, "persistence_service", service)
    monkeypatch.setattr(mandatory_workflow_registry_service, "store", runtime_store)

    try:
        mandatory_workflow_registry_service.ensure_mandatory_workflows_registered()
        conversation = next(
            workflow
            for workflow in runtime_store.workflows
            if workflow["id"] == "mandatory-workflow-conversation"
        )
        conversation["description"] = "临时描述"
        service.persist_workflow_state(workflow=conversation)

        payload = mandatory_workflow_registry_service.ensure_mandatory_workflows_registered()
        persisted = service.get_workflow("mandatory-workflow-conversation")
    finally:
        monkeypatch.setattr(
            mandatory_workflow_registry_service,
            "persistence_service",
            original_persistence_service,
        )
        monkeypatch.setattr(mandatory_workflow_registry_service, "store", original_store)
        service.close()

    assert payload["created"] == []
    assert payload["updated"] == [
        "workflow-1",
        "mandatory-workflow-external-tentacle-dispatch",
        "mandatory-workflow-conversation",
        "mandatory-workflow-security",
        "mandatory-workflow-workflow-designer",
        "mandatory-workflow-memory",
    ]
    assert persisted is not None
    assert persisted["description"] == "负责接待用户、澄清需求并整理结构化交接摘要。"


def test_ensure_mandatory_workflows_registered_persists_explicit_ids_and_internal_trigger_uses_them(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime_store = InMemoryStore()
    runtime_store.workflows = []
    runtime_store.tasks = []
    runtime_store.task_steps = {}
    runtime_store.workflow_runs = []
    service = _sqlite_service(tmp_path, runtime_store)

    original_registry_persistence = mandatory_workflow_registry_service.persistence_service
    original_workflow_persistence = workflow_service.persistence_service
    original_execution_persistence = workflow_execution_service.persistence_service
    monkeypatch.setattr(mandatory_workflow_registry_service, "persistence_service", service)
    monkeypatch.setattr(workflow_service, "persistence_service", service)
    monkeypatch.setattr(workflow_execution_service, "persistence_service", service)
    monkeypatch.setattr(workflow_execution_service, "_schedule_manual_auto_progress", lambda run_id: None)
    workflow_service._INTERNAL_EVENT_DELIVERIES_BY_ID.clear()
    workflow_service._INTERNAL_EVENT_DELIVERIES_BY_KEY.clear()

    try:
        payload = mandatory_workflow_registry_service.ensure_mandatory_workflows_registered()
        persisted_workflows = service.list_workflows() or []
        triggers_by_id = {
            item["id"]: ((item.get("trigger") or {}).get("internal_event"))
            for item in persisted_workflows
        }
        response = workflow_service.trigger_workflow_internal(
            "mandatory.agent.memory.distill_requested",
            {
                "source": "Memory Service",
                "tenantId": "tenant-alpha",
                "profileId": "profile-1",
            },
        )
        persisted_run = service.get_workflow_run(str(response["run_id"]))
        persisted_task = service.get_task(str(response["task_id"]))
        persisted_delivery = service.get_internal_event_delivery(str(response["internal_event_id"]))
    finally:
        monkeypatch.setattr(
            mandatory_workflow_registry_service,
            "persistence_service",
            original_registry_persistence,
        )
        monkeypatch.setattr(workflow_service, "persistence_service", original_workflow_persistence)
        monkeypatch.setattr(
            workflow_execution_service,
            "persistence_service",
            original_execution_persistence,
        )
        workflow_service._INTERNAL_EVENT_DELIVERIES_BY_ID.clear()
        workflow_service._INTERNAL_EVENT_DELIVERIES_BY_KEY.clear()
        service.close()

    assert payload["ok"] is True
    assert payload["created"] == [
        "workflow-1",
        "mandatory-workflow-external-tentacle-dispatch",
        "mandatory-workflow-conversation",
        "mandatory-workflow-security",
        "mandatory-workflow-workflow-designer",
        "mandatory-workflow-memory",
    ]
    assert payload["updated"] == []
    assert payload["total"] == 6
    assert [item["id"] for item in persisted_workflows] == [
        "workflow-1",
        "mandatory-workflow-external-tentacle-dispatch",
        "mandatory-workflow-conversation",
        "mandatory-workflow-security",
        "mandatory-workflow-workflow-designer",
        "mandatory-workflow-memory",
    ]
    assert triggers_by_id == {
        "workflow-1": None,
        "mandatory-workflow-external-tentacle-dispatch": None,
        "mandatory-workflow-conversation": "mandatory.agent.conversation.requested",
        "mandatory-workflow-security": "mandatory.agent.security.review_requested",
        "mandatory-workflow-workflow-designer": "mandatory.agent.workflow_designer.proposal_requested",
        "mandatory-workflow-memory": "mandatory.agent.memory.distill_requested",
    }
    assert response["workflow"]["id"] == "mandatory-workflow-memory"
    assert response["triggered_count"] == 1
    assert response["triggered_workflow_ids"] == ["mandatory-workflow-memory"]
    assert persisted_run is not None
    assert persisted_run["workflow_id"] == "mandatory-workflow-memory"
    assert persisted_run["trigger"] == "internal:mandatory.agent.memory.distill_requested"
    assert persisted_task is not None
    assert persisted_task["workflow_id"] == "mandatory-workflow-memory"
    assert persisted_delivery is not None
    assert persisted_delivery["triggered_workflow_ids"] == ["mandatory-workflow-memory"]
