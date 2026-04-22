from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from app.services import (
    mandatory_agent_registry_service,
    mandatory_workflow_module_registry_service,
    mandatory_workflow_registry_service,
)
from app.services import workflow_execution_service, workflow_service
from app.services.agent_config_service import AgentConfigService
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


def _expected_mandatory_workflow_ids() -> list[str]:
    return [
        str(spec["id"])
        for spec in mandatory_workflow_registry_service._active_mandatory_workflow_specs()
    ]


def _apply_foundation_module_bindings_by_module_key(nodes: object) -> list[dict[str, Any]]:
    if not isinstance(nodes, list):
        return []

    bindings = mandatory_workflow_module_registry_service.foundation_workflow_module_bindings_by_key()
    patched_nodes = deepcopy(nodes)
    for node in patched_nodes:
        if not isinstance(node, dict):
            continue
        config = node.get("config")
        if not isinstance(config, dict):
            continue
        module_key = str(config.get("moduleKey") or "").strip()
        binding = bindings.get(module_key)
        if not isinstance(binding, dict):
            continue
        merged_config = deepcopy(config)
        merged_config.update(deepcopy(binding))
        node["config"] = merged_config
    return patched_nodes


@pytest.fixture(autouse=True)
def _patch_foundation_module_binding_application(monkeypatch) -> None:
    monkeypatch.setattr(
        mandatory_workflow_registry_service,
        "_apply_foundation_module_interface_bindings",
        _apply_foundation_module_bindings_by_module_key,
    )


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
        module_blueprint = mandatory_workflow_module_registry_service.foundation_workflow_module_blueprint()
        module_workflows_by_id = {
            item["workflow_id"]: service.get_workflow(item["workflow_id"])
            for item in module_blueprint
        }
        foundation = service.get_workflow("mandatory-workflow-brain-foundation")
        free_agent_workflow = service.get_workflow(
            mandatory_workflow_registry_service.FREE_AGENT_WORKFLOW_ID
        )
        professional_agent_workflow = service.get_workflow(
            mandatory_workflow_registry_service.PROFESSIONAL_AGENT_WORKFLOW_ID
        )
        external_tentacle = service.get_workflow("mandatory-workflow-external-tentacle-dispatch")
        conversation = service.get_workflow("mandatory-workflow-conversation")
        conversation_pipeline = service.get_workflow(
            mandatory_workflow_registry_service.CONVERSATION_AGENT_PIPELINE_WORKFLOW_ID
        )
        general_assistant_pipeline = service.get_workflow(
            mandatory_workflow_registry_service.GENERAL_ASSISTANT_AGENT_PIPELINE_WORKFLOW_ID
        )
        requirement_dispatch_pipeline = service.get_workflow(
            mandatory_workflow_registry_service.REQUIREMENT_DISPATCH_AGENT_PIPELINE_WORKFLOW_ID
        )
        security = service.get_workflow("mandatory-workflow-security")
        security_pipeline = service.get_workflow(
            mandatory_workflow_registry_service.SECURITY_AGENT_PIPELINE_WORKFLOW_ID
        )
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

    expected_ids = _expected_mandatory_workflow_ids()
    module_blueprint_by_key = {item["key"]: item for item in module_blueprint}
    module_specs_by_id = {
        item["id"]: item for item in mandatory_workflow_module_registry_service.foundation_workflow_module_specs()
    }

    assert payload["ok"] is True
    assert payload["created"] == expected_ids
    assert payload["updated"] == []
    assert persisted_ids == expected_ids

    assert foundation is not None
    assert foundation["name"] == mandatory_workflow_registry_service.FOUNDATION_BRAIN_WORKFLOW_NAME
    assert foundation["node_count"] == 6
    assert foundation["edge_count"] == 5
    assert foundation["trigger"]["type"] == "message"
    assert foundation["trigger"]["description"] == "默认渠道入口，所有渠道消息优先进入基础工作流 · v2.0。"
    assert foundation["trigger"]["channels"] == ["telegram", "dingtalk", "wecom", "feishu"]
    assert foundation["trigger"]["priority"] == mandatory_workflow_registry_service.DEFAULT_MESSAGE_ENTRY_PRIORITY
    assert foundation["agent_bindings"] == []
    assert [(node["id"], node["label"], node["type"]) for node in foundation["nodes"]] == [
        ("1", "渠道输入", "trigger"),
        ("2", "安全agent", "workflow"),
        ("3", "对话agent", "workflow"),
        ("4", "对话agent", "workflow"),
        ("5", "安全agent", "workflow"),
        ("6", "渠道输出", "output"),
    ]

    foundation_nodes_by_id = {node["id"]: node for node in foundation["nodes"]}
    expected_foundation_module_keys = {
        "1": "channel_input",
        "2": "security_ingress",
        "3": "conversation_ingress",
        "4": "conversation_egress",
        "5": "security_egress",
        "6": "channel_output",
    }

    for node_id, module_key in expected_foundation_module_keys.items():
        foundation_node = foundation_nodes_by_id[node_id]
        foundation_config = foundation_node["config"]
        assert foundation_config["moduleKey"] == module_key
        assert foundation_config["moduleWorkflowId"] == module_blueprint_by_key[module_key]["workflow_id"]
        assert foundation_config["moduleInvokeMode"] == module_blueprint_by_key[module_key]["invoke_mode"]
        assert foundation_config["moduleNextKeys"] == module_blueprint_by_key[module_key]["next_module_keys"]
        expected_wiring_status = (
            mandatory_workflow_module_registry_service.FOUNDATION_MODULE_INTERFACE_STATUS
            if module_key == "channel_input"
            else mandatory_workflow_module_registry_service.FOUNDATION_MODULE_WRAPPED_STATUS
        )
        assert foundation_config["moduleWiringStatus"] == expected_wiring_status

    assert foundation_nodes_by_id["2"]["workflow_id"] == module_blueprint_by_key["security_ingress"]["workflow_id"]
    assert foundation_nodes_by_id["3"]["workflow_id"] == module_blueprint_by_key["conversation_ingress"]["workflow_id"]
    assert foundation_nodes_by_id["4"]["workflow_id"] == module_blueprint_by_key["conversation_egress"]["workflow_id"]
    assert foundation_nodes_by_id["5"]["workflow_id"] == module_blueprint_by_key["security_egress"]["workflow_id"]
    assert (
        foundation_nodes_by_id["4"]["config"]["plannedChannelOutputWorkflowId"]
        == module_blueprint_by_key["channel_output"]["workflow_id"]
    )
    assert (
        foundation_nodes_by_id["5"]["config"]["plannedChannelOutputWorkflowId"]
        == module_blueprint_by_key["channel_output"]["workflow_id"]
    )
    assert foundation_nodes_by_id["3"]["label"] == foundation_nodes_by_id["4"]["label"] == "对话agent"
    assert foundation_nodes_by_id["3"]["config"]["moduleKey"] == "conversation_ingress"
    assert foundation_nodes_by_id["4"]["config"]["moduleKey"] == "conversation_egress"
    assert (
        foundation_nodes_by_id["3"]["config"]["moduleWorkflowId"]
        != foundation_nodes_by_id["4"]["config"]["moduleWorkflowId"]
    )
    assert foundation_nodes_by_id["2"]["label"] == foundation_nodes_by_id["5"]["label"] == "安全agent"
    assert foundation_nodes_by_id["2"]["config"]["moduleKey"] == "security_ingress"
    assert foundation_nodes_by_id["5"]["config"]["moduleKey"] == "security_egress"
    assert (
        foundation_nodes_by_id["2"]["config"]["moduleWorkflowId"]
        != foundation_nodes_by_id["5"]["config"]["moduleWorkflowId"]
    )
    assert [(edge["id"], edge["source"], edge["target"]) for edge in foundation["edges"]] == [
        ("e1-2", "1", "2"),
        ("e2-3", "2", "3"),
        ("e3-4", "3", "4"),
        ("e4-5", "4", "5"),
        ("e5-6", "5", "6"),
    ]

    assert free_agent_workflow is not None
    assert free_agent_workflow["name"] == mandatory_workflow_registry_service.FREE_AGENT_WORKFLOW_NAME
    assert free_agent_workflow["trigger"]["type"] == "manual"
    assert free_agent_workflow["trigger"]["internal_event"] is None
    assert free_agent_workflow["agent_bindings"] == []
    assert [node["label"] for node in free_agent_workflow["nodes"]] == [
        "自由工作流",
        "自由工作流下发任务",
        "在外接触手库中找寻对应的角色来",
        "执行自由工作流",
        "返回进程",
    ]
    assert [node["type"] for node in free_agent_workflow["nodes"]] == [
        "trigger",
        "transform",
        "transform",
        "transform",
        "output",
    ]
    assert [edge["id"] for edge in free_agent_workflow["edges"]] == [
        "e1-2",
        "e2-3",
        "e3-4",
        "e4-5",
    ]

    assert professional_agent_workflow is not None
    assert professional_agent_workflow["name"] == mandatory_workflow_registry_service.PROFESSIONAL_AGENT_WORKFLOW_NAME
    assert professional_agent_workflow["trigger"]["type"] == "manual"
    assert professional_agent_workflow["trigger"]["internal_event"] is None
    assert professional_agent_workflow["agent_bindings"] == []
    assert [node["label"] for node in professional_agent_workflow["nodes"]] == [
        "专业工作流",
        "专业工作流下发任务",
        "找寻专业工作流",
        "执行专业工作流",
        "返回进程",
    ]
    assert [node["type"] for node in professional_agent_workflow["nodes"]] == [
        "trigger",
        "transform",
        "transform",
        "transform",
        "output",
    ]
    assert [edge["id"] for edge in professional_agent_workflow["edges"]] == [
        "e1-2",
        "e2-3",
        "e3-4",
        "e4-5",
    ]

    assert external_tentacle is None
    assert conversation is None

    assert conversation_pipeline is not None
    assert (
        conversation_pipeline["name"]
        == mandatory_workflow_registry_service.CONVERSATION_AGENT_PIPELINE_WORKFLOW_NAME
    )
    assert conversation_pipeline["version"] == "v1.0"
    assert (
        conversation_pipeline["trigger"]["internal_event"]
        == "mandatory.agent.conversation.pipeline_requested"
    )
    assert conversation_pipeline["agent_bindings"] == ["conversation"]
    assert [node["label"] for node in conversation_pipeline["nodes"]] == [
        "输入",
        "判断是不是渠道输入",
        "判断需求类型",
        "查询类",
        "确认客户需求",
        "输出给万事通Agent",
        "下发任务类",
        "确认客户需求",
        "输出给需求分发agent",
        "接收最终处理信息，进行语义化处理",
        "输出结果给下一步",
    ]
    assert [node["type"] for node in conversation_pipeline["nodes"]] == [
        "trigger",
        "condition",
        "condition",
        "agent",
        "agent",
        "output",
        "agent",
        "agent",
        "output",
        "agent",
        "output",
    ]
    assert [edge["id"] for edge in conversation_pipeline["edges"]] == [
        "e1-2",
        "e2-3",
        "e2-10",
        "e3-4",
        "e3-7",
        "e4-5",
        "e5-6",
        "e7-8",
        "e8-9",
        "e10-11",
    ]

    assert general_assistant_pipeline is not None
    assert (
        general_assistant_pipeline["name"]
        == mandatory_workflow_registry_service.GENERAL_ASSISTANT_AGENT_PIPELINE_WORKFLOW_NAME
    )
    assert general_assistant_pipeline["version"] == "v1.0"
    assert (
        general_assistant_pipeline["trigger"]["internal_event"]
        == "mandatory.agent.general_assistant.pipeline_requested"
    )
    assert general_assistant_pipeline["agent_bindings"] == ["general_assistant"]
    assert [node["label"] for node in general_assistant_pipeline["nodes"]] == [
        "输入",
        "判断是不是'专业查询'",
        "查询系统内专业知识库和专业流程",
        "联网查询",
        "输出",
    ]
    assert [node["type"] for node in general_assistant_pipeline["nodes"]] == [
        "trigger",
        "condition",
        "agent",
        "agent",
        "output",
    ]
    assert [edge["id"] for edge in general_assistant_pipeline["edges"]] == [
        "e1-2",
        "e2-3",
        "e2-4",
        "e3-5",
        "e4-5",
    ]
    assert general_assistant_pipeline["nodes"][0]["config"]["contractVersion"] == (
        mandatory_workflow_registry_service.GENERAL_ASSISTANT_AGENT_PIPELINE_CONTRACT_VERSION
    )
    assert general_assistant_pipeline["nodes"][0]["config"]["inputContract"] == (
        mandatory_workflow_registry_service.GENERAL_ASSISTANT_AGENT_PIPELINE_INPUT_CONTRACT
    )
    assert general_assistant_pipeline["nodes"][1]["config"]["expression"] == "professional_query"
    assert general_assistant_pipeline["nodes"][1]["config"]["result_key"] == "general_assistant_query_gate"
    assert general_assistant_pipeline["nodes"][2]["agent_id"] == "general_assistant"
    assert general_assistant_pipeline["nodes"][3]["agent_id"] == "general_assistant"
    assert general_assistant_pipeline["nodes"][4]["config"]["handoffTarget"] == "next_step"
    assert general_assistant_pipeline["nodes"][4]["config"]["contractVersion"] == (
        mandatory_workflow_registry_service.GENERAL_ASSISTANT_AGENT_PIPELINE_CONTRACT_VERSION
    )
    assert general_assistant_pipeline["nodes"][4]["config"]["outputContract"] == (
        mandatory_workflow_registry_service.GENERAL_ASSISTANT_AGENT_PIPELINE_OUTPUT_CONTRACT
    )

    assert requirement_dispatch_pipeline is None

    assert security is None

    assert security_pipeline is not None
    assert security_pipeline["name"] == mandatory_workflow_registry_service.SECURITY_AGENT_PIPELINE_WORKFLOW_NAME
    assert security_pipeline["version"] == "v1.0"
    assert security_pipeline["trigger"]["internal_event"] == "mandatory.agent.security.pipeline_requested"
    assert security_pipeline["agent_bindings"] == []
    assert [node["label"] for node in security_pipeline["nodes"]] == [
        "安全请求输入",
        "限流",
        "认证 / RBAC 权限校验",
        "Prompt Injection 双检",
        "内容策略 / 数据脱敏改写",
        "审计追踪",
        "安全结果输出",
    ]
    assert [node["type"] for node in security_pipeline["nodes"]] == [
        "trigger",
        "condition",
        "condition",
        "condition",
        "transform",
        "transform",
        "output",
    ]
    assert [edge["id"] for edge in security_pipeline["edges"]] == [
        "e1-2",
        "e2-3",
        "e3-4",
        "e4-5",
        "e5-6",
        "e6-7",
    ]

    assert workflow_designer is None
    assert memory is None

    for module in module_blueprint:
        module_workflow = module_workflows_by_id[module["workflow_id"]]
        expected_spec = module_specs_by_id[module["workflow_id"]]
        assert module_workflow is not None
        assert module_workflow["name"] == module["workflow_name"]
        assert module_workflow["description"] == expected_spec["description"]
        assert module_workflow["version"] == expected_spec["version"]
        assert module_workflow["trigger"]["type"] == "internal"
        assert module_workflow["trigger"]["internal_event"] == module["internal_event"]
        assert [node["label"] for node in module_workflow["nodes"]] == [node["label"] for node in expected_spec["nodes"]]
        assert [node["type"] for node in module_workflow["nodes"]] == [node["type"] for node in expected_spec["nodes"]]
        assert [edge["id"] for edge in module_workflow["edges"]] == ["e1-2"]

        expected_agent_bindings: list[str] = []
        for expected_node in expected_spec["nodes"]:
            expected_agent_id = str(expected_node.get("agent_id") or "").strip()
            if expected_agent_id and expected_agent_id not in expected_agent_bindings:
                expected_agent_bindings.append(expected_agent_id)
        assert module_workflow["agent_bindings"] == expected_agent_bindings

        trigger_node = module_workflow["nodes"][0]
        module_node = module_workflow["nodes"][1]
        expected_module_node = expected_spec["nodes"][1]
        expected_wiring_status = (
            mandatory_workflow_module_registry_service.FOUNDATION_MODULE_INTERFACE_STATUS
            if module["key"] == "channel_input"
            else mandatory_workflow_module_registry_service.FOUNDATION_MODULE_WRAPPED_STATUS
        )

        assert trigger_node["label"] == "模块接口触发"
        assert trigger_node["config"]["summary"] == module["internal_event"]
        assert trigger_node["config"]["moduleKey"] == module["key"]
        assert module_node["label"] == expected_module_node["label"]
        assert module_node["type"] == expected_module_node["type"]
        assert module_node.get("agent_id") == expected_module_node.get("agent_id")
        assert module_node.get("workflow_id") == expected_module_node.get("workflow_id")
        assert module_node.get("tool_id") == expected_module_node.get("tool_id")

        interface_config = module_node["config"]
        assert interface_config["interfaceOnly"] is (module["key"] == "channel_input")
        assert interface_config["moduleKey"] == module["key"]
        assert interface_config["moduleLabel"] == module["display_name"]
        assert interface_config["invokeMode"] == module["invoke_mode"]
        assert interface_config["wiringStatus"] == expected_wiring_status
        assert interface_config["inputContract"] == module["input_contract"]
        assert interface_config["outputContract"] == module["output_contract"]
        assert interface_config["nextModuleKeys"] == module["next_module_keys"]


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
        conversation_pipeline = next(
            workflow
            for workflow in runtime_store.workflows
            if workflow["id"] == mandatory_workflow_registry_service.CONVERSATION_AGENT_PIPELINE_WORKFLOW_ID
        )
        conversation_pipeline["description"] = "临时描述"
        service.persist_workflow_state(workflow=conversation_pipeline)

        payload = mandatory_workflow_registry_service.ensure_mandatory_workflows_registered()
        persisted = service.get_workflow(
            mandatory_workflow_registry_service.CONVERSATION_AGENT_PIPELINE_WORKFLOW_ID
        )
    finally:
        monkeypatch.setattr(
            mandatory_workflow_registry_service,
            "persistence_service",
            original_persistence_service,
        )
        monkeypatch.setattr(mandatory_workflow_registry_service, "store", original_store)
        service.close()

    assert payload["created"] == []
    assert payload["updated"] == _expected_mandatory_workflow_ids()
    assert persisted is not None
    expected_specs_by_id = {
        str(spec["id"]): spec
        for spec in mandatory_workflow_registry_service._active_mandatory_workflow_specs()
    }
    assert (
        persisted["description"]
        == expected_specs_by_id[
            mandatory_workflow_registry_service.CONVERSATION_AGENT_PIPELINE_WORKFLOW_ID
        ]["description"]
    )


def test_ensure_mandatory_workflows_registered_purges_removed_workflows_and_clears_agent_bindings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime_store = InMemoryStore()
    runtime_store.workflows = []
    runtime_store.agents = []
    service = _sqlite_service(tmp_path, runtime_store)
    removed_workflow_id = "mandatory-workflow-delivery-note-export-and-send"

    dirty_workflow = {
        "id": removed_workflow_id,
        "name": "专业工作流 · 送货单导出并发送客户",
        "description": "历史残留",
        "version": "v1.0",
        "status": "active",
        "updated_at": runtime_store.now_string(),
        "node_count": 1,
        "edge_count": 0,
        "trigger": {"type": "internal", "internal_event": "legacy.removed.workflow"},
        "agent_bindings": ["custom-dispatch-agent"],
        "nodes": [{"id": "1", "type": "trigger", "label": "输入"}],
        "edges": [],
    }
    dirty_agent = {
        "id": "custom-dispatch-agent",
        "name": "自定义派发 Agent",
        "description": "清理绑定测试",
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
        "config_snapshot": {
            "status": "loaded",
            "agent": {
                "agent_id": "custom-dispatch-agent",
                "name": "自定义派发 Agent",
                "agent_workflow_id": removed_workflow_id,
            },
            "runtime": {
                "agent_workflow_binding": {
                    "agent_workflow_id": removed_workflow_id,
                    "source": "manual",
                }
            },
        },
    }
    runtime_store.workflows.append(dirty_workflow)
    runtime_store.agents.append(dirty_agent)
    assert service.persist_workflow_state(workflow=dirty_workflow) is True
    assert service.persist_agent_state(agent=dirty_agent) is True

    original_workflow_persistence = mandatory_workflow_registry_service.persistence_service
    original_workflow_store = mandatory_workflow_registry_service.store
    original_agent_persistence = mandatory_agent_registry_service.persistence_service
    original_agent_store = mandatory_agent_registry_service.store
    monkeypatch.setattr(mandatory_workflow_registry_service, "persistence_service", service)
    monkeypatch.setattr(mandatory_workflow_registry_service, "store", runtime_store)
    monkeypatch.setattr(mandatory_agent_registry_service, "persistence_service", service)
    monkeypatch.setattr(mandatory_agent_registry_service, "store", runtime_store)

    try:
        payload = mandatory_workflow_registry_service.ensure_mandatory_workflows_registered()
        persisted_removed_workflow = service.get_workflow(removed_workflow_id)
        persisted_agent = service.get_agent("custom-dispatch-agent")
    finally:
        monkeypatch.setattr(
            mandatory_workflow_registry_service,
            "persistence_service",
            original_workflow_persistence,
        )
        monkeypatch.setattr(mandatory_workflow_registry_service, "store", original_workflow_store)
        monkeypatch.setattr(mandatory_agent_registry_service, "persistence_service", original_agent_persistence)
        monkeypatch.setattr(mandatory_agent_registry_service, "store", original_agent_store)
        service.close()

    assert payload["ok"] is True
    assert persisted_removed_workflow is None
    assert persisted_agent is not None
    assert "agent_workflow_id" not in persisted_agent["config_snapshot"]["agent"]
    runtime = persisted_agent["config_snapshot"].get("runtime") or {}
    assert "agent_workflow_binding" not in runtime


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
            "mandatory.agent.conversation.pipeline_requested",
            {
                "source": "Conversation Agent",
                "tenantId": "tenant-alpha",
                "traceId": "trace-1",
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

    expected_ids = _expected_mandatory_workflow_ids()
    expected_internal_events = {
        item["workflow_id"]: item["internal_event"]
        for item in mandatory_workflow_module_registry_service.foundation_workflow_module_blueprint()
    }

    assert payload["ok"] is True
    assert payload["created"] == expected_ids
    assert payload["updated"] == []
    assert payload["total"] == len(expected_ids)
    assert [item["id"] for item in persisted_workflows] == expected_ids
    expected_trigger_map = {
        str(spec["id"]): ((spec.get("trigger") or {}).get("internal_event"))
        for spec in mandatory_workflow_registry_service._active_mandatory_workflow_specs()
    }
    assert triggers_by_id == {**expected_trigger_map, **expected_internal_events}
    assert response["workflow"]["id"] == mandatory_workflow_registry_service.CONVERSATION_AGENT_PIPELINE_WORKFLOW_ID
    assert response["triggered_count"] == 1
    assert response["triggered_workflow_ids"] == [
        mandatory_workflow_registry_service.CONVERSATION_AGENT_PIPELINE_WORKFLOW_ID
    ]
    assert persisted_run is not None
    assert (
        persisted_run["workflow_id"]
        == mandatory_workflow_registry_service.CONVERSATION_AGENT_PIPELINE_WORKFLOW_ID
    )
    assert persisted_run["trigger"] == "internal:mandatory.agent.conversation.pipeline_requested"
    assert persisted_task is not None
    assert (
        persisted_task["workflow_id"]
        == mandatory_workflow_registry_service.CONVERSATION_AGENT_PIPELINE_WORKFLOW_ID
    )
    assert persisted_delivery is not None
    assert persisted_delivery["triggered_workflow_ids"] == [
        mandatory_workflow_registry_service.CONVERSATION_AGENT_PIPELINE_WORKFLOW_ID
    ]


def test_ensure_mandatory_workflows_registered_prefers_foundation_workflow_for_message_routing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime_store = InMemoryStore()
    runtime_store.workflows = []
    service = _sqlite_service(tmp_path, runtime_store)

    original_registry_persistence = mandatory_workflow_registry_service.persistence_service
    original_execution_persistence = workflow_execution_service.persistence_service
    original_registry_store = mandatory_workflow_registry_service.store
    monkeypatch.setattr(mandatory_workflow_registry_service, "persistence_service", service)
    monkeypatch.setattr(workflow_execution_service, "persistence_service", service)
    monkeypatch.setattr(mandatory_workflow_registry_service, "store", runtime_store)

    try:
        mandatory_workflow_registry_service.ensure_mandatory_workflows_registered()
        candidates = workflow_execution_service.select_workflow_candidates_for_message(
            "write",
            "请帮我写一份项目周报",
            channel="telegram",
        )
    finally:
        monkeypatch.setattr(
            mandatory_workflow_registry_service,
            "persistence_service",
            original_registry_persistence,
        )
        monkeypatch.setattr(workflow_execution_service, "persistence_service", original_execution_persistence)
        monkeypatch.setattr(mandatory_workflow_registry_service, "store", original_registry_store)
        service.close()

    assert candidates
    assert candidates[0][0]["id"] == "mandatory-workflow-brain-foundation"
    assert candidates[0][0]["trigger"]["type"] == "message"
    assert "message 默认兜底" in candidates[0][1]


def test_foundation_module_workflows_wrap_current_visible_chain_targets(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime_store = InMemoryStore()
    runtime_store.workflows = []
    runtime_store.agents = []
    service = _sqlite_service(tmp_path, runtime_store)
    config_root = Path(__file__).resolve().parents[2] / "agents"

    original_workflow_persistence = mandatory_workflow_registry_service.persistence_service
    original_agent_persistence = mandatory_agent_registry_service.persistence_service
    original_execution_persistence = workflow_execution_service.persistence_service
    original_agent_config_service = mandatory_agent_registry_service.agent_config_service
    original_workflow_store = mandatory_workflow_registry_service.store
    original_agent_store = mandatory_agent_registry_service.store
    monkeypatch.setattr(mandatory_workflow_registry_service, "persistence_service", service)
    monkeypatch.setattr(mandatory_agent_registry_service, "persistence_service", service)
    monkeypatch.setattr(workflow_execution_service, "persistence_service", service)
    monkeypatch.setattr(
        mandatory_agent_registry_service,
        "agent_config_service",
        AgentConfigService(config_root=config_root),
    )
    monkeypatch.setattr(mandatory_workflow_registry_service, "store", runtime_store)
    monkeypatch.setattr(mandatory_agent_registry_service, "store", runtime_store)

    try:
        mandatory_agent_registry_service.ensure_mandatory_agents_registered()
        mandatory_workflow_registry_service.ensure_mandatory_workflows_registered()
        security_ingress = service.get_workflow(
            mandatory_workflow_module_registry_service.FOUNDATION_MODULE_SECURITY_INGRESS_WORKFLOW_ID
        )
        conversation_ingress = service.get_workflow(
            mandatory_workflow_module_registry_service.FOUNDATION_MODULE_CONVERSATION_INGRESS_WORKFLOW_ID
        )
        conversation_egress = service.get_workflow(
            mandatory_workflow_module_registry_service.FOUNDATION_MODULE_CONVERSATION_EGRESS_WORKFLOW_ID
        )
        security_egress = service.get_workflow(
            mandatory_workflow_module_registry_service.FOUNDATION_MODULE_SECURITY_EGRESS_WORKFLOW_ID
        )
    finally:
        monkeypatch.setattr(
            mandatory_workflow_registry_service,
            "persistence_service",
            original_workflow_persistence,
        )
        monkeypatch.setattr(
            mandatory_agent_registry_service,
            "persistence_service",
            original_agent_persistence,
        )
        monkeypatch.setattr(workflow_execution_service, "persistence_service", original_execution_persistence)
        monkeypatch.setattr(
            mandatory_agent_registry_service,
            "agent_config_service",
            original_agent_config_service,
        )
        monkeypatch.setattr(mandatory_workflow_registry_service, "store", original_workflow_store)
        monkeypatch.setattr(mandatory_agent_registry_service, "store", original_agent_store)
        service.close()

    assert security_ingress is not None
    assert conversation_ingress is not None
    assert conversation_egress is not None
    assert security_egress is not None
    assert security_ingress["nodes"][1]["workflow_id"] == mandatory_workflow_registry_service.SECURITY_AGENT_PIPELINE_WORKFLOW_ID
    assert (
        conversation_ingress["nodes"][1]["workflow_id"]
        == mandatory_workflow_registry_service.CONVERSATION_AGENT_PIPELINE_WORKFLOW_ID
    )
    assert (
        conversation_egress["nodes"][1]["agent_id"]
        == "conversation"
    )
    assert security_egress["nodes"][1]["type"] == "transform"
