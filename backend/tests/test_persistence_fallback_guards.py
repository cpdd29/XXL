from __future__ import annotations

import app.services.agent_service as agent_service_module
import app.services.message_ingestion_service as message_ingestion_service_module
import app.services.task_service as task_service_module
import app.services.workflow_dispatcher_service as workflow_dispatcher_service_module
import app.services.workflow_execution_service as workflow_execution_service_module
import app.services.workflow_recovery_service as workflow_recovery_service_module
import app.services.workflow_scheduler_service as workflow_scheduler_service_module
import app.services.workflow_service as workflow_service_module
from app.services.store import store


class FailingPersistence:
    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = enabled
        self.snapshot_calls = 0
        self.execution_payloads: list[dict[str, object]] = []
        self.agent_payloads: list[dict] = []
        self.workflow_payloads: list[dict] = []

    def persist_runtime_state(self) -> bool:
        self.snapshot_calls += 1
        return False

    def persist_execution_state(
        self,
        *,
        task: dict | None = None,
        task_steps: list[dict] | None = None,
        workflow_run: dict | None = None,
    ) -> bool:
        self.execution_payloads.append(
            {
                "task": task,
                "task_steps": task_steps,
                "workflow_run": workflow_run,
            }
        )
        return False

    def persist_agent_state(self, *, agent: dict) -> bool:
        self.agent_payloads.append(agent)
        return False

    def persist_workflow_state(self, *, workflow: dict) -> bool:
        self.workflow_payloads.append(workflow)
        return False


def test_workflow_execution_execution_persist_skips_runtime_snapshot_when_database_write_fails(
    monkeypatch,
) -> None:
    persistence = FailingPersistence(enabled=True)
    monkeypatch.setattr(workflow_execution_service_module, "persistence_service", persistence)

    workflow_execution_service_module._persist_execution_state(
        task={"id": "task-1"},
        steps=[{"id": "step-1"}],
        run={"id": "run-1"},
    )

    assert persistence.snapshot_calls == 0
    assert persistence.execution_payloads == [
        {
            "task": {"id": "task-1"},
            "task_steps": [{"id": "step-1"}],
            "workflow_run": {"id": "run-1"},
        }
    ]


def test_workflow_execution_agent_persist_skips_runtime_snapshot_when_database_write_fails(
    monkeypatch,
) -> None:
    persistence = FailingPersistence(enabled=True)
    monkeypatch.setattr(workflow_execution_service_module, "persistence_service", persistence)

    workflow_execution_service_module._persist_agent_state({"id": "agent-1"})

    assert persistence.snapshot_calls == 0
    assert persistence.agent_payloads == [{"id": "agent-1"}]


def test_message_ingestion_persist_skips_runtime_snapshot_when_database_write_fails(
    monkeypatch,
) -> None:
    persistence = FailingPersistence(enabled=True)
    monkeypatch.setattr(message_ingestion_service_module, "persistence_service", persistence)

    message_ingestion_service_module._persist_execution_state(
        task={"id": "task-1"},
        steps=[{"id": "step-1"}],
        run={"id": "run-1"},
    )

    assert persistence.snapshot_calls == 0
    assert persistence.execution_payloads[0]["workflow_run"] == {"id": "run-1"}


def test_task_service_persist_skips_runtime_snapshot_when_database_write_fails(
    monkeypatch,
) -> None:
    persistence = FailingPersistence(enabled=True)
    monkeypatch.setattr(task_service_module, "persistence_service", persistence)
    store.task_steps["task-1"] = [{"id": "step-1"}]

    task_service_module._persist_task_execution_state({"id": "task-1"})

    assert persistence.snapshot_calls == 0
    assert persistence.execution_payloads == [
        {
            "task": {"id": "task-1"},
            "task_steps": [{"id": "step-1"}],
            "workflow_run": None,
        }
    ]


def test_workflow_scheduler_persist_run_skips_runtime_snapshot_when_database_write_fails() -> None:
    persistence = FailingPersistence(enabled=True)
    service = workflow_scheduler_service_module.WorkflowSchedulerService(persistence=persistence)

    service._persist_run({"id": "run-1"})

    assert persistence.snapshot_calls == 0
    assert persistence.execution_payloads == [
        {
            "task": None,
            "task_steps": None,
            "workflow_run": {"id": "run-1"},
        }
    ]


def test_workflow_scheduler_persist_runs_skips_runtime_snapshot_when_database_write_fails() -> None:
    persistence = FailingPersistence(enabled=True)
    service = workflow_scheduler_service_module.WorkflowSchedulerService(persistence=persistence)

    service._persist_runs([{"id": "run-1"}, {"id": "run-2"}])

    assert persistence.snapshot_calls == 0
    assert [payload["workflow_run"]["id"] for payload in persistence.execution_payloads] == [
        "run-1",
        "run-2",
    ]


def test_workflow_dispatcher_persist_run_skips_runtime_snapshot_when_database_write_fails() -> None:
    persistence = FailingPersistence(enabled=True)

    class _EventBus:
        def subscribe(self, *_args, **_kwargs) -> None:
            return None

        def publish_json(self, *_args, **_kwargs) -> bool:
            return True

    service = workflow_dispatcher_service_module.WorkflowDispatcherService(
        event_bus=_EventBus(),
        persistence=persistence,
        dispatcher_id="dispatcher-test",
    )

    service._persist_run({"id": "run-1"})

    assert persistence.snapshot_calls == 0
    assert persistence.execution_payloads[0]["workflow_run"] == {"id": "run-1"}


def test_workflow_recovery_persist_runs_skips_runtime_snapshot_when_database_write_fails() -> None:
    persistence = FailingPersistence(enabled=True)
    service = workflow_recovery_service_module.WorkflowRecoveryService(persistence=persistence)

    service._persist_runs([{"id": "run-1"}, {"id": "run-2"}])

    assert persistence.snapshot_calls == 0
    assert [payload["workflow_run"]["id"] for payload in persistence.execution_payloads] == [
        "run-1",
        "run-2",
    ]


def test_workflow_service_persist_skips_runtime_snapshot_when_database_write_fails(
    monkeypatch,
) -> None:
    persistence = FailingPersistence(enabled=True)
    monkeypatch.setattr(workflow_service_module, "persistence_service", persistence)

    workflow_service_module._persist_workflow({"id": "workflow-1"})

    assert persistence.snapshot_calls == 0
    assert persistence.workflow_payloads == [{"id": "workflow-1"}]


def test_agent_service_persist_skips_runtime_snapshot_when_database_write_fails(
    monkeypatch,
) -> None:
    persistence = FailingPersistence(enabled=True)
    monkeypatch.setattr(agent_service_module, "persistence_service", persistence)

    agent_service_module._persist_agent({"id": "agent-1"})

    assert persistence.snapshot_calls == 0
    assert persistence.agent_payloads == [{"id": "agent-1"}]


def test_workflow_execution_still_falls_back_to_runtime_snapshot_in_memory_mode(
    monkeypatch,
) -> None:
    persistence = FailingPersistence(enabled=False)
    monkeypatch.setattr(workflow_execution_service_module, "persistence_service", persistence)

    workflow_execution_service_module._persist_execution_state(task={"id": "task-legacy"})

    assert persistence.snapshot_calls == 1
