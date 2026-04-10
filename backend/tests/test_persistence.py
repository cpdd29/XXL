from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from app.db.models import (
    AuditLogRecord,
    ConversationMessageRecord,
    OperationalLogRecord,
    TaskRecord,
    TaskStepRecord,
    UserProfileRecord,
    WorkflowRunRecord,
)
from app.services.persistence_service import StatePersistenceService
from app.services.store import InMemoryStore


def test_persistence_service_round_trips_runtime_state(tmp_path: Path) -> None:
    database_path = tmp_path / "workbot-state.db"
    database_url = f"sqlite:///{database_path}"

    source_store = InMemoryStore()
    source_store.agents[0]["status"] = "maintenance"
    source_store.tasks.append(
        {
            "id": "task-persisted",
            "title": "数据库持久化验证",
            "description": "验证任务状态是否能从数据库恢复",
            "status": "completed",
            "priority": "high",
            "created_at": "2026-04-02T09:00:00Z",
            "completed_at": "2026-04-02T09:03:00Z",
            "agent": "测试Agent",
            "tokens": 256,
            "duration": "180s",
            "workflow_id": "workflow-1",
            "workflow_run_id": "run-persisted",
            "trace_id": "trace-persisted",
            "channel": "telegram",
            "session_id": "session-persisted",
            "user_key": "telegram:user-1",
            "result": {
                "kind": "draft_message",
                "title": "数据库持久化结果",
                "content": "这是一条需要被恢复的任务结果。",
            },
        }
    )
    source_store.task_steps["task-persisted"] = [
        {
            "id": "step-persisted-1",
            "title": "写入数据库",
            "status": "done",
            "agent": "测试Agent",
            "started_at": "2026-04-02T09:00:00Z",
            "finished_at": "2026-04-02T09:01:00Z",
            "message": "步骤已写入数据库",
            "tokens": 64,
        }
    ]
    source_store.workflow_runs.append(
        {
            "id": "run-persisted",
            "workflow_id": "workflow-1",
            "workflow_name": "客户服务工作流",
            "task_id": "task-persisted",
            "trigger": "message",
            "intent": "help",
            "status": "completed",
            "created_at": "2026-04-02T09:00:00Z",
            "updated_at": "2026-04-02T09:03:00Z",
            "started_at": "2026-04-02T09:00:05Z",
            "completed_at": "2026-04-02T09:03:00Z",
            "next_dispatch_at": "2026-04-02T09:01:00Z",
            "dispatch_failure_count": 2,
            "last_dispatch_error": "temporary dispatch timeout",
            "current_stage": "output",
            "active_edges": ["e7-8"],
            "nodes": [{"id": "8", "status": "done"}],
            "logs": [{"message": "workflow finished"}],
            "dispatch_context": {
                "type": "message_dispatch",
                "state": "completed",
                "trace_id": "trace-persisted",
                "route_decision": {
                    "intent": "help",
                    "workflow_id": "workflow-1",
                    "workflow_name": "客户服务工作流",
                    "execution_agent": "输出Agent",
                },
            },
            "memory_hits": 2,
            "warnings": ["test warning"],
        }
    )
    source_store.users[0]["role"] = "super-admin"
    source_store.user_profiles["1"]["notes"] = "这条备注应从数据库恢复。"
    source_store.audit_logs.insert(
        0,
        {
            "id": "audit-persisted",
            "timestamp": "2026-04-02T09:04:00Z",
            "action": "持久化测试",
            "user": "tester",
            "resource": "Persistence",
            "status": "success",
            "ip": "127.0.0.1",
            "details": "验证安全审计日志持久化",
            "metadata": {
                "trace": {"trace_id": "trace-persisted", "layer": "security_pass"},
                "prompt_injection_assessment": {"verdict": "allow"},
            },
        },
    )
    source_store.security_rules[0]["hit_count"] = 2048

    writer = StatePersistenceService(runtime_store=source_store, database_url=database_url)
    assert writer.initialize() is True
    assert writer.enabled is True
    assert database_path.exists() is True
    assert writer._session_factory is not None

    with writer._session_factory() as session:
        persisted_profile = session.get(UserProfileRecord, "1")
        persisted_task = session.get(TaskRecord, "task-persisted")
        persisted_run = session.get(WorkflowRunRecord, "run-persisted")
        persisted_step = session.get(TaskStepRecord, "step-persisted-1")
        persisted_audit = session.get(AuditLogRecord, "audit-persisted")

    assert persisted_profile is not None
    assert persisted_profile.payload != source_store.user_profiles["1"]
    assert "__encrypted_v1__" in persisted_profile.payload
    assert persisted_task is not None
    assert persisted_task.description != source_store.tasks[0]["description"]
    assert persisted_task.description.startswith("enc:v1:")
    assert persisted_task.result is not None
    assert "__encrypted_v1__" in persisted_task.result
    assert persisted_run is not None
    assert persisted_run.message_dispatch_context is not None
    assert "__encrypted_v1__" in persisted_run.message_dispatch_context
    assert persisted_step is not None
    assert persisted_step.message != source_store.task_steps["task-persisted"][0]["message"]
    assert persisted_step.message.startswith("enc:v1:")
    assert persisted_audit is not None
    assert persisted_audit.details != source_store.audit_logs[0]["details"]
    assert persisted_audit.details.startswith("enc:v1:")
    assert persisted_audit.metadata_payload is not None
    assert "__encrypted_v1__" in persisted_audit.metadata_payload

    loaded_store = InMemoryStore()
    loaded_store.agents = []
    loaded_store.tasks = []
    loaded_store.task_steps = {}
    loaded_store.workflows = []
    loaded_store.workflow_runs = []
    loaded_store.users = []
    loaded_store.user_profiles = {}
    loaded_store.audit_logs = []
    loaded_store.security_rules = []

    reader = StatePersistenceService(runtime_store=loaded_store, database_url=database_url)
    assert reader.initialize() is True
    assert reader.enabled is True

    restored_task = next(task for task in loaded_store.tasks if task["id"] == "task-persisted")
    assert restored_task["result"]["title"] == "数据库持久化结果"
    assert loaded_store.task_steps["task-persisted"][0]["message"] == "步骤已写入数据库"
    assert loaded_store.agents[0]["status"] == "maintenance"
    assert loaded_store.users[0]["role"] == "super-admin"
    assert loaded_store.user_profiles["1"]["notes"] == "这条备注应从数据库恢复。"
    assert loaded_store.workflow_runs[0]["id"] == "run-persisted"
    assert loaded_store.workflow_runs[0]["next_dispatch_at"] == "2026-04-02T09:01:00Z"
    assert loaded_store.workflow_runs[0]["dispatch_failure_count"] == 2
    assert loaded_store.workflow_runs[0]["last_dispatch_error"] == "temporary dispatch timeout"
    assert loaded_store.workflow_runs[0]["dispatch_context"]["trace_id"] == "trace-persisted"
    assert loaded_store.workflow_runs[0]["dispatch_context"]["state"] == "completed"
    assert loaded_store.audit_logs[0]["id"] == "audit-persisted"
    assert loaded_store.audit_logs[0]["details"] == "验证安全审计日志持久化"
    assert loaded_store.audit_logs[0]["metadata"]["trace"]["trace_id"] == "trace-persisted"
    assert loaded_store.security_rules[0]["hit_count"] == 2048

    reader.close()
    writer.close()


def test_persistence_service_bootstrap_clears_stale_runtime_collections_when_database_tables_are_empty(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "workbot-bootstrap-clears-empty-tables.db"
    database_url = f"sqlite:///{database_path}"

    source_store = InMemoryStore()
    source_store.agents = []
    source_store.tasks = [
        {
            "id": "task-bootstrap-only",
            "title": "仅数据库任务",
            "description": "用于验证空表会清掉旧 runtime 集合",
            "status": "running",
            "priority": "medium",
            "created_at": "2026-04-06T12:00:00+00:00",
            "completed_at": None,
            "agent": "搜索Agent",
            "tokens": 12,
            "duration": None,
            "workflow_id": None,
            "workflow_run_id": None,
            "trace_id": "trace-bootstrap-only",
            "channel": "telegram",
            "session_id": "telegram:bootstrap-only",
            "user_key": "telegram:bootstrap-only",
            "result": None,
        }
    ]
    source_store.task_steps = {}
    source_store.workflows = []
    source_store.workflow_runs = []
    source_store.users = []
    source_store.user_profiles = {}
    source_store.audit_logs = []
    source_store.security_rules = []
    source_store.system_settings = {}

    writer = StatePersistenceService(runtime_store=source_store, database_url=database_url)
    assert writer.initialize() is True

    runtime_store = InMemoryStore()
    assert runtime_store.workflows
    assert runtime_store.users
    assert runtime_store.security_rules
    assert runtime_store.system_settings

    reader = StatePersistenceService(runtime_store=runtime_store, database_url=database_url)
    assert reader.initialize() is True

    try:
        assert [task["id"] for task in runtime_store.tasks] == ["task-bootstrap-only"]
        assert runtime_store.agents == []
        assert runtime_store.task_steps == {}
        assert runtime_store.workflows == []
        assert runtime_store.workflow_runs == []
        assert runtime_store.users == []
        assert runtime_store.user_profiles == {}
        assert runtime_store.audit_logs == []
        assert runtime_store.security_rules == []
        assert runtime_store.system_settings == {}
    finally:
        reader.close()
        writer.close()


def test_persistence_service_persists_execution_state_without_replacing_unrelated_rows(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "workbot-execution-state.db"
    database_url = f"sqlite:///{database_path}"

    runtime_store = InMemoryStore()
    runtime_store.tasks = [
        {
            "id": "task-target",
            "title": "目标任务",
            "description": "目标任务原始描述",
            "status": "running",
            "priority": "high",
            "created_at": "2026-04-03T15:00:00+00:00",
            "completed_at": None,
            "agent": "搜索Agent",
            "tokens": 21,
            "duration": None,
            "workflow_id": "workflow-1",
            "workflow_run_id": "run-target",
            "trace_id": "trace-target",
            "channel": "telegram",
            "session_id": "telegram:target-chat",
            "user_key": "telegram:target-user",
            "result": None,
        },
        {
            "id": "task-other",
            "title": "保留任务",
            "description": "不应被定点写入误删",
            "status": "completed",
            "priority": "low",
            "created_at": "2026-04-03T15:01:00+00:00",
            "completed_at": "2026-04-03T15:03:00+00:00",
            "agent": "输出Agent",
            "tokens": 8,
            "duration": "120s",
            "workflow_id": "workflow-1",
            "workflow_run_id": "run-other",
            "trace_id": "trace-other",
            "channel": "telegram",
            "session_id": "telegram:other-chat",
            "user_key": "telegram:other-user",
            "result": {"kind": "help_note", "title": "保留结果"},
        },
    ]
    runtime_store.task_steps = {
        "task-target": [
            {
                "id": "task-target-1",
                "title": "原始步骤",
                "status": "running",
                "agent": "搜索Agent",
                "started_at": "2026-04-03T15:00:00+00:00",
                "finished_at": None,
                "message": "原始执行中",
                "tokens": 10,
            }
        ],
        "task-other": [
            {
                "id": "task-other-1",
                "title": "保留步骤",
                "status": "completed",
                "agent": "输出Agent",
                "started_at": "2026-04-03T15:01:00+00:00",
                "finished_at": "2026-04-03T15:02:00+00:00",
                "message": "不应被误删",
                "tokens": 4,
            }
        ],
    }
    runtime_store.workflow_runs = [
        {
            "id": "run-target",
            "workflow_id": "workflow-1",
            "workflow_name": "客户服务工作流",
            "task_id": "task-target",
            "trigger": "message",
            "intent": "search",
            "status": "running",
            "created_at": "2026-04-03T15:00:00+00:00",
            "updated_at": "2026-04-03T15:00:00+00:00",
            "started_at": "2026-04-03T15:00:00+00:00",
            "completed_at": None,
            "next_dispatch_at": None,
            "dispatch_failure_count": 0,
            "last_dispatch_error": None,
            "current_stage": "执行节点",
            "active_edges": [],
            "nodes": [],
            "logs": [],
            "memory_hits": 0,
            "warnings": [],
        },
        {
            "id": "run-other",
            "workflow_id": "workflow-1",
            "workflow_name": "客户服务工作流",
            "task_id": "task-other",
            "trigger": "message",
            "intent": "help",
            "status": "completed",
            "created_at": "2026-04-03T15:01:00+00:00",
            "updated_at": "2026-04-03T15:03:00+00:00",
            "started_at": "2026-04-03T15:01:00+00:00",
            "completed_at": "2026-04-03T15:03:00+00:00",
            "next_dispatch_at": None,
            "dispatch_failure_count": 0,
            "last_dispatch_error": None,
            "current_stage": "执行完成",
            "active_edges": [],
            "nodes": [],
            "logs": [],
            "memory_hits": 0,
            "warnings": [],
        },
    ]

    service = StatePersistenceService(runtime_store=runtime_store, database_url=database_url)
    assert service.initialize() is True

    updated_target_task = {
        "id": "task-target",
        "title": "目标任务",
        "description": "目标任务已改成定点直写后的描述",
        "status": "completed",
        "priority": "high",
        "created_at": "2026-04-03T15:00:00+00:00",
        "completed_at": "2026-04-03T15:04:00+00:00",
        "agent": "搜索Agent",
        "tokens": 55,
        "duration": "240s",
        "workflow_id": "workflow-1",
        "workflow_run_id": "run-target",
        "trace_id": "trace-target",
        "channel": "telegram",
        "session_id": "telegram:target-chat",
        "user_key": "telegram:target-user",
        "result": {"kind": "search_report", "title": "目标任务结果"},
    }
    updated_target_steps = [
        {
            "id": "task-target-1",
            "title": "原始步骤",
            "status": "completed",
            "agent": "搜索Agent",
            "started_at": "2026-04-03T15:00:00+00:00",
            "finished_at": "2026-04-03T15:02:00+00:00",
            "message": "步骤已完成",
            "tokens": 18,
        },
        {
            "id": "task-target-2",
            "title": "发送结果",
            "status": "completed",
            "agent": "输出Agent",
            "started_at": "2026-04-03T15:04:00+00:00",
            "finished_at": "2026-04-03T15:04:00+00:00",
            "message": "已完成结果回传",
            "tokens": 6,
        },
    ]
    updated_target_run = {
        "id": "run-target",
        "workflow_id": "workflow-1",
        "workflow_name": "客户服务工作流",
        "task_id": "task-target",
        "trigger": "message",
        "intent": "search",
        "status": "completed",
        "created_at": "2026-04-03T15:00:00+00:00",
        "updated_at": "2026-04-03T15:04:00+00:00",
        "started_at": "2026-04-03T15:00:00+00:00",
        "completed_at": "2026-04-03T15:04:00+00:00",
        "next_dispatch_at": None,
        "dispatch_failure_count": 0,
        "last_dispatch_error": None,
        "current_stage": "执行完成",
        "active_edges": ["e2-3"],
        "nodes": [{"id": "2", "status": "completed"}],
        "logs": [{"message": "run completed"}],
        "dispatch_context": {
            "type": "message_dispatch",
            "state": "completed",
            "trace_id": "trace-target",
            "execution_agent_id": "agent-search",
        },
        "memory_hits": 1,
        "warnings": [],
    }

    runtime_store.tasks = [updated_target_task]
    runtime_store.task_steps = {"task-target": updated_target_steps}
    runtime_store.workflow_runs = [updated_target_run]

    try:
        assert (
            service.persist_execution_state(
                task=updated_target_task,
                task_steps=updated_target_steps,
                workflow_run=updated_target_run,
            )
            is True
        )
        assert service._session_factory is not None
        with service._session_factory() as session:
            persisted_target_task = session.get(TaskRecord, "task-target")
            persisted_target_run = session.get(WorkflowRunRecord, "run-target")
            persisted_target_step = session.get(TaskStepRecord, "task-target-1")
        loaded_tasks = service.list_tasks()
        loaded_target_steps = service.get_task_steps("task-target")
        loaded_other_steps = service.get_task_steps("task-other")
        loaded_runs = service.list_workflow_runs()
    finally:
        service.close()

    assert persisted_target_task is not None
    assert persisted_target_task.description != updated_target_task["description"]
    assert persisted_target_task.description.startswith("enc:v1:")
    assert persisted_target_task.result is not None
    assert "__encrypted_v1__" in persisted_target_task.result
    assert persisted_target_run is not None
    assert persisted_target_run.message_dispatch_context is not None
    assert "__encrypted_v1__" in persisted_target_run.message_dispatch_context
    assert persisted_target_run.logs is not None
    assert "__encrypted_v1__" in persisted_target_run.logs
    assert persisted_target_step is not None
    assert persisted_target_step.message != updated_target_steps[0]["message"]
    assert persisted_target_step.message.startswith("enc:v1:")
    assert loaded_tasks is not None
    assert [task["id"] for task in loaded_tasks] == ["task-target", "task-other"]
    assert loaded_tasks[0]["description"] == "目标任务已改成定点直写后的描述"
    assert loaded_tasks[1]["description"] == "不应被定点写入误删"
    assert loaded_target_steps is not None
    assert [step["id"] for step in loaded_target_steps] == ["task-target-1", "task-target-2"]
    assert loaded_other_steps is not None
    assert loaded_other_steps[0]["id"] == "task-other-1"
    assert loaded_runs is not None
    assert [run["id"] for run in loaded_runs] == ["run-target", "run-other"]
    assert loaded_runs[0]["status"] == "completed"
    assert loaded_runs[0]["dispatch_context"]["state"] == "completed"
    assert loaded_runs[1]["status"] == "completed"


def test_persistence_service_persists_single_agent_without_replacing_unrelated_rows(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "workbot-agent-state.db"
    database_url = f"sqlite:///{database_path}"

    runtime_store = InMemoryStore()
    runtime_store.agents = [
        {
            "id": "agent-target",
            "name": "目标 Agent",
            "description": "只更新这一条 Agent",
            "type": "search",
            "status": "running",
            "enabled": True,
            "tasks_completed": 12,
            "tasks_total": 20,
            "avg_response_time": "120ms",
            "tokens_used": 320,
            "tokens_limit": 4096,
            "success_rate": 92.5,
            "last_active": "5 分钟前",
        },
        {
            "id": "agent-other",
            "name": "保留 Agent",
            "description": "不应被定点写入误删",
            "type": "write",
            "status": "idle",
            "enabled": True,
            "tasks_completed": 3,
            "tasks_total": 4,
            "avg_response_time": "340ms",
            "tokens_used": 90,
            "tokens_limit": 2048,
            "success_rate": 75.0,
            "last_active": "昨天",
        },
    ]

    service = StatePersistenceService(runtime_store=runtime_store, database_url=database_url)
    assert service.initialize() is True

    updated_target_agent = {
        "id": "agent-target",
        "name": "目标 Agent",
        "description": "定点写入后已刷新状态",
        "type": "search",
        "status": "idle",
        "enabled": True,
        "tasks_completed": 13,
        "tasks_total": 21,
        "avg_response_time": "98ms",
        "tokens_used": 360,
        "tokens_limit": 4096,
        "success_rate": 95.0,
        "last_active": "刚刚",
    }
    runtime_store.agents = [updated_target_agent]

    try:
        assert service.persist_agent_state(agent=updated_target_agent) is True

        loaded_agents = service.list_agents()
        assert loaded_agents is not None
        agents_by_id = {agent["id"]: agent for agent in loaded_agents}

        assert set(agents_by_id) == {"agent-target", "agent-other"}
        assert agents_by_id["agent-target"]["status"] == "idle"
        assert agents_by_id["agent-target"]["description"] == "定点写入后已刷新状态"
        assert agents_by_id["agent-other"]["name"] == "保留 Agent"
        assert agents_by_id["agent-other"]["status"] == "idle"
    finally:
        service.close()


def test_persistence_service_persists_single_workflow_without_replacing_unrelated_rows(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "workbot-workflow-state.db"
    database_url = f"sqlite:///{database_path}"

    runtime_store = InMemoryStore()
    runtime_store.workflows = [
        {
            "id": "workflow-target",
            "name": "目标工作流",
            "description": "只更新这一条工作流",
            "version": "v1",
            "status": "draft",
            "updated_at": "2026-04-04T09:00:00+00:00",
            "node_count": 2,
            "edge_count": 1,
            "trigger": {"type": "message", "keyword": "目标"},
            "agent_bindings": ["agent-target"],
            "nodes": [
                {"id": "1", "type": "trigger", "label": "消息触发"},
                {"id": "2", "type": "agent", "label": "搜索 Agent", "agent_id": "agent-target"},
            ],
            "edges": [{"id": "e1-2", "source": "1", "target": "2"}],
        },
        {
            "id": "workflow-other",
            "name": "保留工作流",
            "description": "不应被定点写入误删",
            "version": "v1",
            "status": "active",
            "updated_at": "2026-04-04T08:50:00+00:00",
            "node_count": 1,
            "edge_count": 0,
            "trigger": {"type": "manual"},
            "agent_bindings": [],
            "nodes": [{"id": "1", "type": "trigger", "label": "手动触发"}],
            "edges": [],
        },
    ]
    runtime_store.workflow_runs = [
        {
            "id": "run-other",
            "workflow_id": "workflow-other",
            "workflow_name": "保留工作流",
            "task_id": "task-other",
            "trigger": "manual",
            "intent": "help",
            "status": "completed",
            "created_at": "2026-04-04T08:51:00+00:00",
            "updated_at": "2026-04-04T08:52:00+00:00",
            "started_at": "2026-04-04T08:51:00+00:00",
            "completed_at": "2026-04-04T08:52:00+00:00",
            "next_dispatch_at": None,
            "dispatch_failure_count": 0,
            "last_dispatch_error": None,
            "current_stage": "执行完成",
            "active_edges": [],
            "nodes": [],
            "logs": [{"message": "不应被误删的运行"}],
            "memory_hits": 0,
            "warnings": [],
        }
    ]

    service = StatePersistenceService(runtime_store=runtime_store, database_url=database_url)
    assert service.initialize() is True

    updated_target_workflow = {
        "id": "workflow-target",
        "name": "目标工作流",
        "description": "定点写入后已更新",
        "version": "v2",
        "status": "running",
        "updated_at": "2026-04-04T09:10:00+00:00",
        "node_count": 2,
        "edge_count": 1,
        "trigger": {"type": "schedule", "cron": "0 * * * *"},
        "agent_bindings": ["agent-target"],
        "nodes": [
            {"id": "1", "type": "trigger", "label": "定时触发"},
            {"id": "2", "type": "agent", "label": "搜索 Agent", "agent_id": "agent-target"},
        ],
        "edges": [{"id": "e1-2", "source": "1", "target": "2"}],
    }
    runtime_store.workflows = [updated_target_workflow]

    try:
        assert service.persist_workflow_state(workflow=updated_target_workflow) is True

        loaded_workflows = service.list_workflows()
        assert loaded_workflows is not None
        workflows_by_id = {workflow["id"]: workflow for workflow in loaded_workflows}

        assert set(workflows_by_id) == {"workflow-target", "workflow-other"}
        assert workflows_by_id["workflow-target"]["version"] == "v2"
        assert workflows_by_id["workflow-target"]["status"] == "running"
        assert workflows_by_id["workflow-other"]["name"] == "保留工作流"

        loaded_other_run = service.get_workflow_run("run-other")
        assert loaded_other_run is not None
        assert loaded_other_run["workflow_id"] == "workflow-other"
        assert loaded_other_run["logs"][0]["message"] == "不应被误删的运行"
    finally:
        service.close()


def test_persistence_service_fails_open_when_database_init_errors() -> None:
    service = StatePersistenceService(
        runtime_store=InMemoryStore(),
        database_url="not-a-real-database-driver://workbot",
    )

    assert service.initialize() is False
    assert service.enabled is False
    assert service.persist_all() is False


def test_persistence_service_keeps_audit_logs_append_only_across_security_persists(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "workbot-security-append-only.db"
    database_url = f"sqlite:///{database_path}"

    runtime_store = InMemoryStore()
    runtime_store.audit_logs = [
        {
            "id": "audit-old",
            "timestamp": "2026-04-02T09:00:00Z",
            "action": "旧审计事件",
            "user": "tester",
            "resource": "Security Gateway",
            "status": "warning",
            "ip": "127.0.0.1",
            "details": "older log should stay in database",
        }
    ]

    writer = StatePersistenceService(runtime_store=runtime_store, database_url=database_url)
    assert writer.initialize() is True

    runtime_store.audit_logs = [
        {
            "id": "audit-new",
            "timestamp": "2026-04-02T10:00:00Z",
            "action": "新审计事件",
            "user": "tester",
            "resource": "Security Gateway",
            "status": "success",
            "ip": "127.0.0.1",
            "details": "new log should be appended without removing history",
            "metadata": {"trace": {"trace_id": "trace-new"}},
        }
    ]

    assert writer.persist_security_state() is True

    reader = StatePersistenceService(runtime_store=InMemoryStore(), database_url=database_url)
    assert reader.initialize() is True

    try:
        assert reader._session_factory is not None
        with reader._session_factory() as session:
            persisted_new_audit = session.get(AuditLogRecord, "audit-new")
        loaded_logs = reader.list_audit_logs()
    finally:
        reader.close()
        writer.close()

    assert persisted_new_audit is not None
    assert persisted_new_audit.details.startswith("enc:v1:")
    assert persisted_new_audit.metadata_payload is not None
    assert "__encrypted_v1__" in persisted_new_audit.metadata_payload
    assert loaded_logs is not None
    assert [log["id"] for log in loaded_logs[:2]] == ["audit-new", "audit-old"]
    assert loaded_logs[0]["details"] == "new log should be appended without removing history"
    assert loaded_logs[0]["metadata"]["trace"]["trace_id"] == "trace-new"


def test_persistence_service_upserts_single_user_without_replacing_others(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "workbot-user-upsert.db"
    database_url = f"sqlite:///{database_path}"

    runtime_store = InMemoryStore()
    runtime_store.users = [
        {
            "id": "user-1",
            "name": "原始用户一",
            "email": "user-1@example.com",
            "role": "viewer",
            "status": "active",
            "last_login": "2026-04-02T09:00:00+00:00",
            "total_interactions": 12,
            "created_at": "2026-04-01",
        },
        {
            "id": "user-2",
            "name": "原始用户二",
            "email": "user-2@example.com",
            "role": "operator",
            "status": "active",
            "last_login": "2026-04-02T10:00:00+00:00",
            "total_interactions": 24,
            "created_at": "2026-04-01",
        },
    ]
    runtime_store.user_profiles = {
        "user-1": {
            **runtime_store.users[0],
            "tags": ["原始"],
            "notes": "原始画像一",
            "preferred_language": "zh",
            "source_channels": ["console"],
        },
        "user-2": {
            **runtime_store.users[1],
            "tags": ["保留"],
            "notes": "原始画像二",
            "preferred_language": "en",
            "source_channels": ["telegram"],
        },
    }

    writer = StatePersistenceService(runtime_store=runtime_store, database_url=database_url)
    assert writer.initialize() is True

    updated_user = {
        **runtime_store.users[0],
        "name": "已更新用户一",
        "role": "admin",
    }
    updated_profile = {
        **runtime_store.user_profiles["user-1"],
        "name": "已更新用户一",
        "role": "admin",
        "notes": "只更新 user-1",
    }
    runtime_store.users[0] = updated_user
    runtime_store.user_profiles["user-1"] = updated_profile

    assert writer.persist_user_state(user=updated_user, profile=updated_profile) is True

    reader = StatePersistenceService(runtime_store=InMemoryStore(), database_url=database_url)
    assert reader.initialize() is True

    try:
        persisted_user_1 = reader.get_user("user-1")
        persisted_user_2 = reader.get_user("user-2")
        persisted_profile_1 = reader.get_user_profile("user-1")
        persisted_profile_2 = reader.get_user_profile("user-2")
    finally:
        reader.close()
        writer.close()

    assert persisted_user_1 is not None
    assert persisted_user_1["name"] == "已更新用户一"
    assert persisted_user_1["role"] == "admin"
    assert persisted_profile_1 is not None
    assert persisted_profile_1["notes"] == "只更新 user-1"
    assert persisted_user_2 is not None
    assert persisted_user_2["name"] == "原始用户二"
    assert persisted_profile_2 is not None
    assert persisted_profile_2["notes"] == "原始画像二"


def test_persistence_service_lists_due_workflow_runs(tmp_path: Path) -> None:
    database_path = tmp_path / "workbot-due-runs.db"
    database_url = f"sqlite:///{database_path}"

    source_store = InMemoryStore()
    source_store.workflow_runs = [
        {
            "id": "run-due",
            "workflow_id": "workflow-1",
            "workflow_name": "客户服务工作流",
            "task_id": "task-due",
            "trigger": "message",
            "intent": "search",
            "status": "running",
            "created_at": "2026-04-02T09:00:00+00:00",
            "updated_at": "2026-04-02T09:00:00+00:00",
            "started_at": "2026-04-02T09:00:00+00:00",
            "completed_at": None,
            "next_dispatch_at": "2026-04-02T09:01:00+00:00",
            "current_stage": "执行节点",
            "active_edges": [],
            "nodes": [],
            "logs": [],
            "memory_hits": 0,
            "warnings": [],
        },
        {
            "id": "run-future",
            "workflow_id": "workflow-1",
            "workflow_name": "客户服务工作流",
            "task_id": "task-future",
            "trigger": "message",
            "intent": "search",
            "status": "running",
            "created_at": "2026-04-02T09:00:00+00:00",
            "updated_at": "2026-04-02T09:00:00+00:00",
            "started_at": "2026-04-02T09:00:00+00:00",
            "completed_at": None,
            "next_dispatch_at": "2026-04-02T09:03:00+00:00",
            "current_stage": "执行节点",
            "active_edges": [],
            "nodes": [],
            "logs": [],
            "memory_hits": 0,
            "warnings": [],
        },
        {
            "id": "run-terminal",
            "workflow_id": "workflow-1",
            "workflow_name": "客户服务工作流",
            "task_id": "task-terminal",
            "trigger": "message",
            "intent": "search",
            "status": "completed",
            "created_at": "2026-04-02T09:00:00+00:00",
            "updated_at": "2026-04-02T09:02:00+00:00",
            "started_at": "2026-04-02T09:00:00+00:00",
            "completed_at": "2026-04-02T09:02:00+00:00",
            "next_dispatch_at": "2026-04-02T09:01:30+00:00",
            "current_stage": "完成",
            "active_edges": [],
            "nodes": [],
            "logs": [],
            "memory_hits": 0,
            "warnings": [],
        },
    ]

    service = StatePersistenceService(runtime_store=source_store, database_url=database_url)
    assert service.initialize() is True

    try:
        due_runs = service.list_due_workflow_runs(due_before="2026-04-02T09:01:30+00:00")
    finally:
        service.close()

    assert due_runs is not None
    assert [run["id"] for run in due_runs] == ["run-due"]


def test_persistence_service_claim_due_workflow_runs_claims_only_eligible_runs(tmp_path: Path) -> None:
    database_path = tmp_path / "workbot-claim-due-runs.db"
    database_url = f"sqlite:///{database_path}"

    def _workflow_run(
        run_id: str,
        *,
        status: str = "running",
        next_dispatch_at: str | None,
        dispatcher_id: str | None = None,
        dispatch_claimed_at: str | None = None,
        dispatch_lease_expires_at: str | None = None,
        completed_at: str | None = None,
    ) -> dict:
        return {
            "id": run_id,
            "workflow_id": "workflow-1",
            "workflow_name": "客户服务工作流",
            "task_id": f"task-{run_id}",
            "trigger": "message",
            "intent": "search",
            "status": status,
            "created_at": "2026-04-02T09:00:00+00:00",
            "updated_at": "2026-04-02T09:00:00+00:00",
            "started_at": "2026-04-02T09:00:00+00:00",
            "completed_at": completed_at,
            "next_dispatch_at": next_dispatch_at,
            "dispatch_failure_count": 0,
            "last_dispatch_error": None,
            "dispatcher_id": dispatcher_id,
            "dispatch_claimed_at": dispatch_claimed_at,
            "dispatch_lease_expires_at": dispatch_lease_expires_at,
            "current_stage": "执行节点",
            "active_edges": [],
            "nodes": [],
            "logs": [],
            "memory_hits": 0,
            "warnings": [],
        }

    source_store = InMemoryStore()
    source_store.workflow_runs = [
        _workflow_run(
            "run-due-free",
            next_dispatch_at="2026-04-02T09:01:00+00:00",
        ),
        _workflow_run(
            "run-due-expired-lease",
            next_dispatch_at="2026-04-02T09:01:05+00:00",
            dispatcher_id="dispatcher-stale",
            dispatch_claimed_at="2026-04-02T09:00:10+00:00",
            dispatch_lease_expires_at="2026-04-02T09:00:40+00:00",
        ),
        _workflow_run(
            "run-due-active-foreign",
            next_dispatch_at="2026-04-02T09:01:10+00:00",
            dispatcher_id="dispatcher-other",
            dispatch_claimed_at="2026-04-02T09:01:00+00:00",
            dispatch_lease_expires_at="2026-04-02T09:02:00+00:00",
        ),
        _workflow_run(
            "run-future",
            next_dispatch_at="2026-04-02T09:03:00+00:00",
        ),
        _workflow_run(
            "run-terminal",
            status="completed",
            next_dispatch_at="2026-04-02T09:01:15+00:00",
            completed_at="2026-04-02T09:01:16+00:00",
        ),
    ]

    service = StatePersistenceService(runtime_store=source_store, database_url=database_url)
    assert service.initialize() is True

    try:
        claimed_runs = service.claim_due_workflow_runs(
            due_before="2026-04-02T09:01:30+00:00",
            limit=10,
            dispatcher_id="dispatcher-db",
            claimed_at="2026-04-02T09:01:30+00:00",
            lease_expires_at="2026-04-02T09:02:15+00:00",
        )
        claimed_due_free = service.get_workflow_run("run-due-free")
        claimed_due_expired = service.get_workflow_run("run-due-expired-lease")
        skipped_active_foreign = service.get_workflow_run("run-due-active-foreign")
        skipped_future = service.get_workflow_run("run-future")
        skipped_terminal = service.get_workflow_run("run-terminal")
    finally:
        service.close()

    assert claimed_runs is not None
    assert [run["id"] for run in claimed_runs] == ["run-due-free", "run-due-expired-lease"]

    for claimed_run in claimed_runs:
        assert claimed_run["dispatcher_id"] == "dispatcher-db"
        assert claimed_run["dispatch_claimed_at"] == "2026-04-02T09:01:30+00:00"
        assert claimed_run["dispatch_lease_expires_at"] == "2026-04-02T09:02:15+00:00"

    assert claimed_due_free is not None
    assert claimed_due_free["dispatcher_id"] == "dispatcher-db"
    assert claimed_due_free["dispatch_claimed_at"] == "2026-04-02T09:01:30+00:00"
    assert claimed_due_free["dispatch_lease_expires_at"] == "2026-04-02T09:02:15+00:00"

    assert claimed_due_expired is not None
    assert claimed_due_expired["dispatcher_id"] == "dispatcher-db"
    assert claimed_due_expired["dispatch_claimed_at"] == "2026-04-02T09:01:30+00:00"
    assert claimed_due_expired["dispatch_lease_expires_at"] == "2026-04-02T09:02:15+00:00"

    assert skipped_active_foreign is not None
    assert skipped_active_foreign["dispatcher_id"] == "dispatcher-other"
    assert skipped_active_foreign["dispatch_claimed_at"] == "2026-04-02T09:01:00+00:00"
    assert skipped_active_foreign["dispatch_lease_expires_at"] == "2026-04-02T09:02:00+00:00"

    assert skipped_future is not None
    assert skipped_future["dispatcher_id"] is None
    assert skipped_future["dispatch_claimed_at"] is None
    assert skipped_future["dispatch_lease_expires_at"] is None

    assert skipped_terminal is not None
    assert skipped_terminal["status"] == "completed"
    assert skipped_terminal["dispatcher_id"] is None


def _claimable_workflow_run(
    run_id: str,
    *,
    dispatcher_id: str | None = None,
    dispatch_claimed_at: str | None = None,
    dispatch_lease_expires_at: str | None = None,
    status: str = "running",
) -> dict[str, str | None]:
    return {
        "id": run_id,
        "workflow_id": "workflow-claim",
        "workflow_name": "理赔工作流",
        "task_id": f"task-{run_id}",
        "trigger": "message",
        "intent": "dispatch",
        "status": status,
        "created_at": "2026-04-02T09:00:00+00:00",
        "updated_at": "2026-04-02T09:00:00+00:00",
        "started_at": "2026-04-02T09:00:00+00:00",
        "completed_at": None,
        "next_dispatch_at": "2026-04-02T09:01:00+00:00",
        "dispatch_failure_count": 0,
        "last_dispatch_error": None,
        "dispatcher_id": dispatcher_id,
        "dispatch_claimed_at": dispatch_claimed_at,
        "dispatch_lease_expires_at": dispatch_lease_expires_at,
        "current_stage": "执行节点",
        "active_edges": [],
        "nodes": [],
        "logs": [],
        "memory_hits": 0,
        "warnings": [],
    }


def test_persistence_service_claim_workflow_run_respects_existing_leases(tmp_path: Path) -> None:
    database_path = tmp_path / "workbot-single-claim.db"
    database_url = f"sqlite:///{database_path}"

    source_store = InMemoryStore()
    source_store.workflow_runs = [
        _claimable_workflow_run(
            "run-active-foreign",
            dispatcher_id="dispatcher-other",
            dispatch_claimed_at="2026-04-02T09:00:45+00:00",
            dispatch_lease_expires_at="2026-04-02T09:05:00+00:00",
        ),
        _claimable_workflow_run(
            "run-expired",
            dispatcher_id="dispatcher-stale",
            dispatch_claimed_at="2026-04-02T09:00:10+00:00",
            dispatch_lease_expires_at="2026-04-02T09:01:00+00:00",
        ),
        _claimable_workflow_run("run-free"),
        _claimable_workflow_run(
            "run-self-owned",
            dispatcher_id="dispatcher-db",
            dispatch_claimed_at="2026-04-02T09:00:20+00:00",
            dispatch_lease_expires_at="2026-04-02T09:06:00+00:00",
        ),
    ]

    service = StatePersistenceService(runtime_store=source_store, database_url=database_url)
    assert service.initialize() is True

    try:
        blocked = service.claim_workflow_run(
            run_id="run-active-foreign",
            dispatcher_id="dispatcher-db",
            claimed_at="2026-04-02T09:02:00+00:00",
            lease_expires_at="2026-04-02T09:03:00+00:00",
        )
        assert blocked is None
        assert (
            service.get_workflow_run("run-active-foreign")["dispatcher_id"]
            == "dispatcher-other"
        )

        claimed_expired = service.claim_workflow_run(
            run_id="run-expired",
            dispatcher_id="dispatcher-db",
            claimed_at="2026-04-02T09:02:10+00:00",
            lease_expires_at="2026-04-02T09:07:00+00:00",
        )
        assert claimed_expired is not None
        assert claimed_expired["dispatcher_id"] == "dispatcher-db"
        assert claimed_expired["dispatch_claimed_at"] == "2026-04-02T09:02:10+00:00"

        claimed_free = service.claim_workflow_run(
            run_id="run-free",
            dispatcher_id="dispatcher-db",
            claimed_at="2026-04-02T09:02:30+00:00",
            lease_expires_at="2026-04-02T09:08:00+00:00",
        )
        assert claimed_free is not None
        assert claimed_free["dispatcher_id"] == "dispatcher-db"

        claimed_self = service.claim_workflow_run(
            run_id="run-self-owned",
            dispatcher_id="dispatcher-db",
            claimed_at="2026-04-02T09:02:45+00:00",
            lease_expires_at="2026-04-02T09:09:00+00:00",
        )
        assert claimed_self is not None
        assert claimed_self["dispatcher_id"] == "dispatcher-db"
    finally:
        service.close()


def test_persistence_service_release_workflow_run_claim_checks_owner(tmp_path: Path) -> None:
    database_path = tmp_path / "workbot-single-release.db"
    database_url = f"sqlite:///{database_path}"

    source_store = InMemoryStore()
    source_store.workflow_runs = [
        _claimable_workflow_run(
            "run-active-foreign",
            dispatcher_id="dispatcher-other",
            dispatch_claimed_at="2026-04-02T09:00:45+00:00",
            dispatch_lease_expires_at="2026-04-02T09:05:00+00:00",
        ),
        _claimable_workflow_run(
            "run-self-owned",
            dispatcher_id="dispatcher-db",
            dispatch_claimed_at="2026-04-02T09:00:46+00:00",
            dispatch_lease_expires_at="2026-04-02T09:06:00+00:00",
        ),
        _claimable_workflow_run(
            "run-terminal",
            dispatcher_id="dispatcher-other",
            dispatch_claimed_at="2026-04-02T09:00:40+00:00",
            dispatch_lease_expires_at="2026-04-02T09:02:00+00:00",
            status="completed",
        ),
    ]

    service = StatePersistenceService(runtime_store=source_store, database_url=database_url)
    assert service.initialize() is True

    try:
        blocked_release = service.release_workflow_run_claim(
            run_id="run-active-foreign",
            dispatcher_id="dispatcher-db",
        )
        assert blocked_release is not None
        assert blocked_release["dispatcher_id"] == "dispatcher-other"
        assert (
            service.get_workflow_run("run-active-foreign")["dispatcher_id"] == "dispatcher-other"
        )

        self_release = service.release_workflow_run_claim(
            run_id="run-self-owned",
            dispatcher_id="dispatcher-db",
        )
        assert self_release is not None
        assert self_release["dispatcher_id"] is None
        assert self_release["dispatch_claimed_at"] is None
        assert self_release["dispatch_lease_expires_at"] is None

        terminal_release = service.release_workflow_run_claim(
            run_id="run-terminal",
            dispatcher_id="dispatcher-db",
        )
        assert terminal_release is not None
        assert terminal_release["status"] == "completed"
        assert terminal_release["dispatcher_id"] is None
    finally:
        service.close()


def test_persistence_service_upsert_and_claim_workflow_dispatch_jobs(tmp_path: Path) -> None:
    database_path = tmp_path / "workbot-dispatch-jobs.db"
    database_url = f"sqlite:///{database_path}"

    service = StatePersistenceService(runtime_store=InMemoryStore(), database_url=database_url)
    assert service.initialize() is True

    try:
        first = service.upsert_workflow_dispatch_job(
            "run-queue",
            available_at="2026-04-03T14:00:01+00:00",
            queued_at="2026-04-03T14:00:00+00:00",
        )
        second = service.upsert_workflow_dispatch_job(
            "run-queue",
            available_at="2026-04-03T14:00:02+00:00",
            queued_at="2026-04-03T14:00:01+00:00",
        )
        other = service.upsert_workflow_dispatch_job(
            "run-other",
            available_at="2026-04-03T14:00:05+00:00",
            queued_at="2026-04-03T14:00:00+00:00",
        )
        claimed_jobs = service.claim_due_workflow_dispatch_jobs(
            due_before="2026-04-03T14:00:03+00:00",
            limit=10,
            dispatcher_id="dispatcher-db",
            claimed_at="2026-04-03T14:00:03+00:00",
            lease_expires_at="2026-04-03T14:00:30+00:00",
        )
        claimed = service.get_workflow_dispatch_job("run-queue")
        unclaimed = service.get_workflow_dispatch_job("run-other")
    finally:
        service.close()

    assert first is not None
    assert second is not None
    assert other is not None
    assert second["available_at"] == "2026-04-03T14:00:02+00:00"
    assert second["dispatcher_id"] is None

    assert claimed_jobs is not None
    assert [job["run_id"] for job in claimed_jobs] == ["run-queue"]
    assert claimed is not None
    assert claimed["dispatcher_id"] == "dispatcher-db"
    assert claimed["claimed_at"] == "2026-04-03T14:00:03+00:00"
    assert claimed["lease_expires_at"] == "2026-04-03T14:00:30+00:00"
    assert unclaimed is not None
    assert unclaimed["dispatcher_id"] is None


def test_persistence_service_release_and_delete_workflow_dispatch_job_claims(tmp_path: Path) -> None:
    database_path = tmp_path / "workbot-dispatch-job-release.db"
    database_url = f"sqlite:///{database_path}"

    service = StatePersistenceService(runtime_store=InMemoryStore(), database_url=database_url)
    assert service.initialize() is True

    try:
        service.upsert_workflow_dispatch_job(
            "run-release",
            available_at="2026-04-03T14:00:01+00:00",
            queued_at="2026-04-03T14:00:00+00:00",
        )
        service.claim_due_workflow_dispatch_jobs(
            due_before="2026-04-03T14:00:02+00:00",
            limit=10,
            dispatcher_id="dispatcher-db",
            claimed_at="2026-04-03T14:00:02+00:00",
            lease_expires_at="2026-04-03T14:00:30+00:00",
        )
        blocked_release = service.release_workflow_dispatch_job_claim(
            "run-release",
            dispatcher_id="dispatcher-other",
            claimed_at="2026-04-03T14:00:02+00:00",
        )
        self_release = service.release_workflow_dispatch_job_claim(
            "run-release",
            dispatcher_id="dispatcher-db",
            claimed_at="2026-04-03T14:00:02+00:00",
        )
        service.claim_due_workflow_dispatch_jobs(
            due_before="2026-04-03T14:00:03+00:00",
            limit=10,
            dispatcher_id="dispatcher-db",
            claimed_at="2026-04-03T14:00:03+00:00",
            lease_expires_at="2026-04-03T14:00:31+00:00",
        )
        stale_delete = service.delete_workflow_dispatch_job(
            "run-release",
            dispatcher_id="dispatcher-db",
            claimed_at="2026-04-03T14:00:02+00:00",
        )
        claimed_delete = service.delete_workflow_dispatch_job(
            "run-release",
            dispatcher_id="dispatcher-db",
            claimed_at="2026-04-03T14:00:03+00:00",
        )
        deleted_job = service.get_workflow_dispatch_job("run-release")
    finally:
        service.close()

    assert blocked_release is not None
    assert blocked_release["dispatcher_id"] == "dispatcher-db"
    assert self_release is not None
    assert self_release["dispatcher_id"] is None
    assert self_release["claimed_at"] is None
    assert self_release["lease_expires_at"] is None
    assert stale_delete is False
    assert claimed_delete is True
    assert deleted_job is None


def test_persistence_service_upsert_and_claim_workflow_execution_jobs(tmp_path: Path) -> None:
    database_path = tmp_path / "workbot-execution-jobs.db"
    database_url = f"sqlite:///{database_path}"

    service = StatePersistenceService(runtime_store=InMemoryStore(), database_url=database_url)
    assert service.initialize() is True

    try:
        first = service.upsert_workflow_execution_job(
            "run-execution-queue",
            available_at="2026-04-03T14:10:01+00:00",
            queued_at="2026-04-03T14:10:00+00:00",
        )
        second = service.upsert_workflow_execution_job(
            "run-execution-queue",
            available_at="2026-04-03T14:10:02+00:00",
            queued_at="2026-04-03T14:10:01+00:00",
        )
        other = service.upsert_workflow_execution_job(
            "run-execution-other",
            available_at="2026-04-03T14:10:05+00:00",
            queued_at="2026-04-03T14:10:00+00:00",
        )
        claimed_jobs = service.claim_due_workflow_execution_jobs(
            due_before="2026-04-03T14:10:03+00:00",
            limit=10,
            worker_id="worker-db",
            claimed_at="2026-04-03T14:10:03+00:00",
            lease_expires_at="2026-04-03T14:10:30+00:00",
        )
        claimed = service.get_workflow_execution_job("run-execution-queue")
        unclaimed = service.get_workflow_execution_job("run-execution-other")
        blocked_release = service.release_workflow_execution_job_claim(
            "run-execution-queue",
            worker_id="worker-other",
            claimed_at="2026-04-03T14:10:03+00:00",
        )
        self_release = service.release_workflow_execution_job_claim(
            "run-execution-queue",
            worker_id="worker-db",
            claimed_at="2026-04-03T14:10:03+00:00",
        )
        service.claim_due_workflow_execution_jobs(
            due_before="2026-04-03T14:10:04+00:00",
            limit=10,
            worker_id="worker-db",
            claimed_at="2026-04-03T14:10:04+00:00",
            lease_expires_at="2026-04-03T14:10:31+00:00",
        )
        stale_delete = service.delete_workflow_execution_job(
            "run-execution-queue",
            worker_id="worker-db",
            claimed_at="2026-04-03T14:10:03+00:00",
        )
        claimed_delete = service.delete_workflow_execution_job(
            "run-execution-queue",
            worker_id="worker-db",
            claimed_at="2026-04-03T14:10:04+00:00",
        )
        deleted_job = service.get_workflow_execution_job("run-execution-queue")
    finally:
        service.close()

    assert first is not None
    assert second is not None
    assert other is not None
    assert second["available_at"] == "2026-04-03T14:10:02+00:00"
    assert second["worker_id"] is None
    assert claimed_jobs is not None
    assert [job["run_id"] for job in claimed_jobs] == ["run-execution-queue"]
    assert claimed is not None
    assert claimed["worker_id"] == "worker-db"
    assert claimed["claimed_at"] == "2026-04-03T14:10:03+00:00"
    assert claimed["lease_expires_at"] == "2026-04-03T14:10:30+00:00"
    assert unclaimed is not None
    assert unclaimed["worker_id"] is None
    assert blocked_release is not None
    assert blocked_release["worker_id"] == "worker-db"
    assert self_release is not None
    assert self_release["worker_id"] is None
    assert self_release["claimed_at"] is None
    assert self_release["lease_expires_at"] is None
    assert stale_delete is False
    assert claimed_delete is True
    assert deleted_job is None


def test_persistence_service_upsert_and_claim_agent_execution_jobs(tmp_path: Path) -> None:
    database_path = tmp_path / "workbot-agent-execution-jobs.db"
    database_url = f"sqlite:///{database_path}"

    service = StatePersistenceService(runtime_store=InMemoryStore(), database_url=database_url)
    assert service.initialize() is True

    try:
        first = service.upsert_agent_execution_job(
            "run-agent-queue",
            task_id="task-agent-1",
            workflow_id="workflow-agent-1",
            execution_agent_id="agent-search-1",
            available_at="2026-04-08T01:10:01+00:00",
            queued_at="2026-04-08T01:10:00+00:00",
            step_delay_seconds=0.6,
        )
        second = service.upsert_agent_execution_job(
            "run-agent-queue",
            task_id="task-agent-2",
            workflow_id="workflow-agent-2",
            execution_agent_id="agent-write-1",
            available_at="2026-04-08T01:10:02+00:00",
            queued_at="2026-04-08T01:10:01+00:00",
            step_delay_seconds=1.2,
        )
        other = service.upsert_agent_execution_job(
            "run-agent-other",
            task_id="task-agent-other",
            workflow_id="workflow-agent-other",
            execution_agent_id=None,
            available_at="2026-04-08T01:10:05+00:00",
            queued_at="2026-04-08T01:10:00+00:00",
        )
        claimed_jobs = service.claim_due_agent_execution_jobs(
            due_before="2026-04-08T01:10:03+00:00",
            limit=10,
            worker_id="agent-worker-db",
            claimed_at="2026-04-08T01:10:03+00:00",
            lease_expires_at="2026-04-08T01:10:30+00:00",
        )
        claimed = service.get_agent_execution_job("run-agent-queue")
        unclaimed = service.get_agent_execution_job("run-agent-other")
        blocked_release = service.release_agent_execution_job_claim(
            "run-agent-queue",
            worker_id="agent-worker-other",
            claimed_at="2026-04-08T01:10:03+00:00",
        )
        self_release = service.release_agent_execution_job_claim(
            "run-agent-queue",
            worker_id="agent-worker-db",
            claimed_at="2026-04-08T01:10:03+00:00",
        )
        service.claim_agent_execution_job(
            "run-agent-queue",
            worker_id="agent-worker-db",
            claimed_at="2026-04-08T01:10:04+00:00",
            lease_expires_at="2026-04-08T01:10:31+00:00",
            due_before="2026-04-08T01:10:04+00:00",
        )
        stale_delete = service.delete_agent_execution_job(
            "run-agent-queue",
            worker_id="agent-worker-db",
            claimed_at="2026-04-08T01:10:03+00:00",
        )
        claimed_delete = service.delete_agent_execution_job(
            "run-agent-queue",
            worker_id="agent-worker-db",
            claimed_at="2026-04-08T01:10:04+00:00",
        )
        deleted_job = service.get_agent_execution_job("run-agent-queue")
    finally:
        service.close()

    assert first is not None
    assert second is not None
    assert other is not None
    assert second["task_id"] == "task-agent-2"
    assert second["workflow_id"] == "workflow-agent-2"
    assert second["execution_agent_id"] == "agent-write-1"
    assert second["step_delay_seconds"] == 1.2
    assert second["worker_id"] is None
    assert claimed_jobs is not None
    assert [job["run_id"] for job in claimed_jobs] == ["run-agent-queue"]
    assert claimed is not None
    assert claimed["worker_id"] == "agent-worker-db"
    assert claimed["claimed_at"] == "2026-04-08T01:10:03+00:00"
    assert claimed["lease_expires_at"] == "2026-04-08T01:10:30+00:00"
    assert unclaimed is not None
    assert unclaimed["worker_id"] is None
    assert blocked_release is not None
    assert blocked_release["worker_id"] == "agent-worker-db"
    assert self_release is not None
    assert self_release["worker_id"] is None
    assert self_release["claimed_at"] is None
    assert self_release["lease_expires_at"] is None
    assert stale_delete is False
    assert claimed_delete is True
    assert deleted_job is None


def test_persistence_service_appends_and_lists_conversation_messages(tmp_path: Path) -> None:
    database_path = tmp_path / "workbot-conversation-logs.db"
    database_url = f"sqlite:///{database_path}"

    service = StatePersistenceService(runtime_store=InMemoryStore(), database_url=database_url)
    assert service.initialize() is True

    try:
        assert (
            service.append_conversation_message(
                {
                    "id": "msg-raw-1",
                    "user_id": "telegram:conversation-user",
                    "session_id": "session-a",
                    "role": "user",
                    "content": "第一条原始消息",
                    "detected_lang": "zh",
                    "created_at": "2026-04-03T09:00:00+00:00",
                }
            )
            is True
        )
        assert (
            service.append_conversation_message(
                {
                    "id": "msg-raw-2",
                    "user_id": "telegram:conversation-user",
                    "session_id": "session-a",
                    "role": "assistant",
                    "content": "第二条原始消息",
                    "detected_lang": "zh",
                    "created_at": "2026-04-03T09:00:05+00:00",
                }
            )
            is True
        )
        assert (
            service.append_conversation_message(
                {
                    "id": "msg-raw-3",
                    "user_id": "telegram:conversation-user",
                    "session_id": "session-b",
                    "role": "user",
                    "content": "其他会话消息",
                    "detected_lang": "zh",
                    "created_at": "2026-04-03T09:01:00+00:00",
                }
            )
            is True
        )

        session_a = service.list_conversation_messages(
            user_id="telegram:conversation-user",
            session_id="session-a",
        )
        latest_two = service.list_conversation_messages(
            user_id="telegram:conversation-user",
            limit=2,
        )
    finally:
        service.close()

    assert session_a is not None
    assert [item["id"] for item in session_a] == ["msg-raw-1", "msg-raw-2"]
    assert latest_two is not None
    assert [item["id"] for item in latest_two] == ["msg-raw-2", "msg-raw-3"]


def test_persistence_service_encrypts_sensitive_conversation_and_profile_storage(tmp_path: Path) -> None:
    database_path = tmp_path / "workbot-encrypted-storage.db"
    database_url = f"sqlite:///{database_path}"

    runtime_store = InMemoryStore()
    runtime_store.user_profiles["secure-user"] = {
        "id": "secure-user",
        "name": "敏感用户",
        "notes": "这条备注不应该以明文落库",
        "platform_accounts": [{"platform": "telegram", "account_id": "secure-account"}],
    }

    service = StatePersistenceService(runtime_store=runtime_store, database_url=database_url)
    assert service.initialize() is True

    try:
        assert service.persist_user_state(profile=runtime_store.user_profiles["secure-user"]) is True
        assert (
            service.append_conversation_message(
                {
                    "id": "secure-msg-1",
                    "user_id": "secure-user",
                    "session_id": "session-secure",
                    "role": "user",
                    "content": "这是一条不应该明文存库的原始消息",
                    "detected_lang": "zh",
                    "created_at": "2026-04-08T12:00:00+00:00",
                }
            )
            is True
        )

        assert service._session_factory is not None
        with service._session_factory() as session:
            persisted_message = session.scalars(
                select(ConversationMessageRecord).where(ConversationMessageRecord.id == "secure-msg-1")
            ).one()
            persisted_profile = session.get(UserProfileRecord, "secure-user")

        messages = service.list_conversation_messages(user_id="secure-user")
        profile = service.get_user_profile("secure-user")
        profile_by_account = service.find_user_profile_by_platform_account(
            platform="telegram",
            account_id="secure-account",
        )
    finally:
        service.close()

    assert persisted_message.content != "这是一条不应该明文存库的原始消息"
    assert persisted_message.content.startswith("enc:v1:")
    assert persisted_profile is not None
    assert persisted_profile.payload != runtime_store.user_profiles["secure-user"]
    assert "__encrypted_v1__" in persisted_profile.payload
    assert messages is not None
    assert messages[0]["content"] == "这是一条不应该明文存库的原始消息"
    assert profile is not None
    assert profile["notes"] == "这条备注不应该以明文落库"
    assert profile_by_account is not None
    assert profile_by_account["id"] == "secure-user"


def test_persistence_service_appends_and_lists_operational_logs(tmp_path: Path) -> None:
    database_path = tmp_path / "workbot-operational-logs.db"
    database_url = f"sqlite:///{database_path}"

    service = StatePersistenceService(runtime_store=InMemoryStore(), database_url=database_url)
    assert service.initialize() is True

    try:
        assert (
            service.append_operational_log(
                log={
                    "id": "op-log-1",
                    "timestamp": "2026-04-08T13:00:00+00:00",
                    "type": "success",
                    "agent": "Dispatcher Agent",
                    "message": "任务 task-op-1 已创建",
                    "source": "message_ingestion",
                    "trace_id": "trace-op-1",
                    "task_id": "task-op-1",
                    "workflow_run_id": "run-op-1",
                    "metadata": {"event": "task_created"},
                }
            )
            is True
        )
        assert service._session_factory is not None
        with service._session_factory() as session:
            persisted_log = session.get(OperationalLogRecord, "op-log-1")
        logs = service.list_operational_logs(limit=10)
    finally:
        service.close()

    assert persisted_log is not None
    assert persisted_log.message != "任务 task-op-1 已创建"
    assert persisted_log.message.startswith("enc:v1:")
    assert persisted_log.metadata_payload is not None
    assert "__encrypted_v1__" in persisted_log.metadata_payload
    assert logs is not None
    assert logs[0]["id"] == "op-log-1"
    assert logs[0]["source"] == "message_ingestion"
    assert logs[0]["trace_id"] == "trace-op-1"
    assert logs[0]["task_id"] == "task-op-1"
    assert logs[0]["workflow_run_id"] == "run-op-1"
    assert logs[0]["metadata"]["event"] == "task_created"
