from __future__ import annotations

from copy import deepcopy
from typing import Any


FOUNDATION_MODULE_INTERFACE_STATUS = "interface_only"
FOUNDATION_MODULE_WRAPPED_STATUS = "wrapped"
FOUNDATION_MODULE_INTERFACE_VERSION = "v0.1"

MANDATORY_CONVERSATION_WORKFLOW_ID = "mandatory-workflow-agent-conversation-pipeline"
MANDATORY_SECURITY_WORKFLOW_ID = "mandatory-workflow-agent-security-pipeline"

FOUNDATION_MODULE_CHANNEL_INPUT_WORKFLOW_ID = "mandatory-workflow-module-foundation-channel-input"
FOUNDATION_MODULE_SECURITY_INGRESS_WORKFLOW_ID = "mandatory-workflow-module-foundation-security-ingress"
FOUNDATION_MODULE_CONVERSATION_INGRESS_WORKFLOW_ID = "mandatory-workflow-module-foundation-conversation-ingress"
FOUNDATION_MODULE_CONVERSATION_EGRESS_WORKFLOW_ID = "mandatory-workflow-module-foundation-conversation-egress"
FOUNDATION_MODULE_SECURITY_EGRESS_WORKFLOW_ID = "mandatory-workflow-module-foundation-security-egress"
FOUNDATION_MODULE_CHANNEL_OUTPUT_WORKFLOW_ID = "mandatory-workflow-module-foundation-channel-output"

FOUNDATION_WORKFLOW_MODULE_BLUEPRINT: tuple[dict[str, Any], ...] = (
    {
        "key": "channel_input",
        "workflow_id": FOUNDATION_MODULE_CHANNEL_INPUT_WORKFLOW_ID,
        "display_name": "渠道输入",
        "workflow_name": "基础工作流模块 · 渠道输入",
        "description": "接收渠道消息并统一为基础工作流可消费的请求上下文。",
        "internal_event": "mandatory.foundation.module.channel_input.requested",
        "invoke_mode": "sync",
        "input_contract": {
            "fields": ["channel", "platform_user_id", "chat_id", "message_text", "request_context"],
        },
        "output_contract": {
            "fields": ["normalized_message", "request_context", "tenant_context", "security_context"],
        },
        "next_module_keys": ["security_ingress"],
        "current_node_labels": ["渠道输入"],
    },
    {
        "key": "security_ingress",
        "workflow_id": FOUNDATION_MODULE_SECURITY_INGRESS_WORKFLOW_ID,
        "display_name": "安全agent",
        "workflow_name": "基础工作流模块 · 安全agent（入站）",
        "description": "承接入站安全审查、脱敏改写与风险放行结果。",
        "internal_event": "mandatory.foundation.module.security_ingress.requested",
        "invoke_mode": "sync",
        "input_contract": {
            "fields": ["normalized_message", "request_context", "tenant_context", "security_context"],
        },
        "output_contract": {
            "fields": ["security_verdict", "security_context", "audit_trace_id", "allowed_message"],
        },
        "next_module_keys": ["conversation_ingress"],
        "current_node_labels": ["安全agent"],
    },
    {
        "key": "conversation_ingress",
        "workflow_id": FOUNDATION_MODULE_CONVERSATION_INGRESS_WORKFLOW_ID,
        "display_name": "对话agent",
        "workflow_name": "基础工作流模块 · 对话agent（接待）",
        "description": "负责第一轮接待、需求理解和可继续派工的摘要整理。",
        "internal_event": "mandatory.foundation.module.conversation_ingress.requested",
        "invoke_mode": "sync",
        "input_contract": {
            "fields": ["allowed_message", "security_context", "tenant_context", "message_history"],
        },
        "output_contract": {
            "fields": ["structured_request_packet", "clarification_state", "handoff_summary"],
        },
        "next_module_keys": ["conversation_egress"],
        "current_node_labels": ["对话agent"],
    },
    {
        "key": "conversation_egress",
        "workflow_id": FOUNDATION_MODULE_CONVERSATION_EGRESS_WORKFLOW_ID,
        "display_name": "对话agent",
        "workflow_name": "基础工作流模块 · 对话agent（回传）",
        "description": "统一整理模块结果，形成面向用户的自然语言回传草稿。",
        "internal_event": "mandatory.foundation.module.conversation_egress.requested",
        "invoke_mode": "sync",
        "input_contract": {
            "fields": ["professional_result", "free_workflow_result", "assistant_reply", "execution_evidence"],
        },
        "output_contract": {
            "fields": ["response_draft", "response_summary", "delivery_payload"],
        },
        "next_module_keys": ["security_egress"],
        "current_node_labels": ["对话agent"],
    },
    {
        "key": "security_egress",
        "workflow_id": FOUNDATION_MODULE_SECURITY_EGRESS_WORKFLOW_ID,
        "display_name": "安全agent",
        "workflow_name": "基础工作流模块 · 安全agent（出站）",
        "description": "负责出站前的脱敏、越权和渠道发布复核。",
        "internal_event": "mandatory.foundation.module.security_egress.requested",
        "invoke_mode": "sync",
        "input_contract": {
            "fields": ["response_draft", "delivery_payload", "tenant_context", "security_context"],
        },
        "output_contract": {
            "fields": ["outbound_payload", "security_verdict", "audit_trace_id"],
        },
        "next_module_keys": ["channel_output"],
        "current_node_labels": ["安全agent"],
    },
    {
        "key": "channel_output",
        "workflow_id": FOUNDATION_MODULE_CHANNEL_OUTPUT_WORKFLOW_ID,
        "display_name": "渠道输出",
        "workflow_name": "基础工作流模块 · 渠道输出",
        "description": "预留统一渠道回传接口，后续再接入不同渠道的具体出站事件。",
        "internal_event": "mandatory.foundation.module.channel_output.requested",
        "invoke_mode": "sync",
        "input_contract": {
            "fields": ["outbound_payload", "channel", "delivery_target", "delivery_mode"],
        },
        "output_contract": {
            "fields": ["delivery_receipt", "delivery_status", "channel_trace_id"],
        },
        "next_module_keys": [],
        "current_node_labels": ["渠道输出"],
    },
)


def _clone(value: object) -> object:
    return deepcopy(value)


def _build_module_output_config(module: dict[str, Any], *, wiring_status: str) -> dict[str, Any]:
    return {
        "interfaceOnly": wiring_status == FOUNDATION_MODULE_INTERFACE_STATUS,
        "moduleKey": module["key"],
        "moduleLabel": module["display_name"],
        "invokeMode": module["invoke_mode"],
        "wiringStatus": wiring_status,
        "inputContract": _clone(module["input_contract"]),
        "outputContract": _clone(module["output_contract"]),
        "nextModuleKeys": list(module["next_module_keys"]),
        "currentNodeLabels": list(module["current_node_labels"]),
    }


def _build_internal_trigger(module: dict[str, Any], *, description: str) -> dict[str, Any]:
    return {
        "type": "internal",
        "keyword": None,
        "cron": None,
        "webhook_path": None,
        "internal_event": module["internal_event"],
        "description": description,
        "priority": 120,
        "channels": [],
        "preferred_language": None,
        "step_delay_seconds": 0.6,
        "max_dispatch_retry": 2,
        "dispatch_retry_backoff_seconds": 1.0,
        "execution_timeout_seconds": 15.0,
        "natural_language_rule": None,
        "schedule_plan": None,
    }


def _build_interface_only_module_workflow_spec(module: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": module["workflow_id"],
        "name": module["workflow_name"],
        "description": f"{module['description']} 当前阶段只保留模块接口骨架，后续再接入具体事件与运行语义。",
        "version": FOUNDATION_MODULE_INTERFACE_VERSION,
        "status": "active",
        "trigger": _build_internal_trigger(
            module,
            description=f"{module['display_name']}模块接口入口（预留）",
        ),
        "nodes": [
            {
                "id": "1",
                "type": "trigger",
                "label": "模块接口触发",
                "x": 60,
                "y": 120,
                "description": f"预留 {module['display_name']} 模块的统一触发入口。",
                "config": {
                    "summary": module["internal_event"],
                    "moduleKey": module["key"],
                    "wiringStatus": FOUNDATION_MODULE_INTERFACE_STATUS,
                },
            },
            {
                "id": "2",
                "type": "output",
                "label": "模块接口占位",
                "x": 320,
                "y": 120,
                "description": "当前只注册接口，不承接真实事件执行。",
                "config": _build_module_output_config(
                    module,
                    wiring_status=FOUNDATION_MODULE_INTERFACE_STATUS,
                ),
            },
        ],
        "edges": [
            {
                "id": "e1-2",
                "source": "1",
                "target": "2",
            }
        ],
    }


def _build_security_ingress_module_workflow_spec(module: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": module["workflow_id"],
        "name": module["workflow_name"],
        "description": f"{module['description']} 当前先通过薄封装模块承接安全流 agent pipeline。",
        "version": "v0.2",
        "status": "active",
        "trigger": _build_internal_trigger(module, description="安全agent模块入口"),
        "nodes": [
            {
                "id": "1",
                "type": "trigger",
                "label": "模块接口触发",
                "x": 60,
                "y": 120,
                "description": "接收基础工作流的安全模块转入请求。",
                "config": {"summary": module["internal_event"], "moduleKey": module["key"]},
            },
            {
                "id": "2",
                "type": "workflow",
                "label": "安全agent",
                "x": 320,
                "y": 120,
                "description": "进入当前安全流 agent pipeline。",
                "workflow_id": MANDATORY_SECURITY_WORKFLOW_ID,
                "config": {
                    **_build_module_output_config(module, wiring_status=FOUNDATION_MODULE_WRAPPED_STATUS),
                    "handoffNote": "当前处于基础工作流入站安全阶段，请完成风险审查并回传结果。",
                },
            },
        ],
        "edges": [{"id": "e1-2", "source": "1", "target": "2"}],
    }


def _build_conversation_ingress_module_workflow_spec(module: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": module["workflow_id"],
        "name": module["workflow_name"],
        "description": f"{module['description']} 当前先封装现有对话流 agent pipeline 能力。",
        "version": "v0.2",
        "status": "active",
        "trigger": _build_internal_trigger(module, description="对话agent接待模块入口"),
        "nodes": [
            {
                "id": "1",
                "type": "trigger",
                "label": "模块接口触发",
                "x": 60,
                "y": 120,
                "description": "接收基础工作流的对话接待阶段转入。",
                "config": {"summary": module["internal_event"], "moduleKey": module["key"]},
            },
            {
                "id": "2",
                "type": "workflow",
                "label": "对话agent",
                "x": 320,
                "y": 120,
                "description": "进入当前对话流 agent pipeline。",
                "workflow_id": MANDATORY_CONVERSATION_WORKFLOW_ID,
                "config": {
                    **_build_module_output_config(module, wiring_status=FOUNDATION_MODULE_WRAPPED_STATUS),
                    "handoffNote": "当前处于基础工作流接待阶段，请理解并确认用户需求。",
                },
            },
        ],
        "edges": [{"id": "e1-2", "source": "1", "target": "2"}],
    }


def _build_conversation_egress_module_workflow_spec(module: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": module["workflow_id"],
        "name": module["workflow_name"],
        "description": f"{module['description']} 当前通过薄封装模块整理最终对话回复。",
        "version": "v0.2",
        "status": "active",
        "trigger": _build_internal_trigger(module, description="对话agent回传模块入口"),
        "nodes": [
            {
                "id": "1",
                "type": "trigger",
                "label": "模块接口触发",
                "x": 60,
                "y": 120,
                "description": "接收专业/自由路径返回后的统一回传请求。",
                "config": {"summary": module["internal_event"], "moduleKey": module["key"]},
            },
            {
                "id": "2",
                "type": "agent",
                "label": "对话agent",
                "x": 320,
                "y": 120,
                "description": "根据上游结果整理最终对外回复。",
                "agent_id": "conversation",
                "config": {
                    **_build_module_output_config(module, wiring_status=FOUNDATION_MODULE_WRAPPED_STATUS),
                    "instruction": "读取上游执行结果，整理成统一自然语言回复。",
                    "result_kind": "chat_reply",
                },
            },
        ],
        "edges": [{"id": "e1-2", "source": "1", "target": "2"}],
    }


def _build_security_egress_module_workflow_spec(module: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": module["workflow_id"],
        "name": module["workflow_name"],
        "description": f"{module['description']} 当前通过薄封装模块执行出站复核并保留原结果。",
        "version": "v0.2",
        "status": "active",
        "trigger": _build_internal_trigger(module, description="安全agent出站模块入口"),
        "nodes": [
            {
                "id": "1",
                "type": "trigger",
                "label": "模块接口触发",
                "x": 60,
                "y": 120,
                "description": "接收最终回复前的安全复核请求。",
                "config": {"summary": module["internal_event"], "moduleKey": module["key"]},
            },
            {
                "id": "2",
                "type": "transform",
                "label": "安全agent · 出站复核",
                "x": 320,
                "y": 120,
                "description": "执行出站复核，但不改写已生成的用户回复主体。",
                "config": {
                    **_build_module_output_config(module, wiring_status=FOUNDATION_MODULE_WRAPPED_STATUS),
                    "transform_note": "outbound security review before delivery",
                },
            },
        ],
        "edges": [{"id": "e1-2", "source": "1", "target": "2"}],
    }


def _build_channel_output_module_workflow_spec(module: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": module["workflow_id"],
        "name": module["workflow_name"],
        "description": f"{module['description']} 当前通过统一输出节点占位回收最终结果。",
        "version": "v0.2",
        "status": "active",
        "trigger": _build_internal_trigger(module, description="渠道输出模块入口"),
        "nodes": [
            {
                "id": "1",
                "type": "trigger",
                "label": "模块接口触发",
                "x": 60,
                "y": 120,
                "description": "接收最终出站阶段的回传请求。",
                "config": {"summary": module["internal_event"], "moduleKey": module["key"]},
            },
            {
                "id": "2",
                "type": "output",
                "label": "渠道输出",
                "x": 320,
                "y": 120,
                "description": "当前先统一回收结果，后续再接具体渠道事件。",
                "config": _build_module_output_config(
                    module,
                    wiring_status=FOUNDATION_MODULE_WRAPPED_STATUS,
                ),
            },
        ],
        "edges": [{"id": "e1-2", "source": "1", "target": "2"}],
    }


def _build_module_workflow_spec(module: dict[str, Any]) -> dict[str, Any]:
    key = str(module["key"]).strip()
    if key == "channel_input":
        return _build_interface_only_module_workflow_spec(module)
    if key == "security_ingress":
        return _build_security_ingress_module_workflow_spec(module)
    if key == "conversation_ingress":
        return _build_conversation_ingress_module_workflow_spec(module)
    if key == "conversation_egress":
        return _build_conversation_egress_module_workflow_spec(module)
    if key == "security_egress":
        return _build_security_egress_module_workflow_spec(module)
    if key == "channel_output":
        return _build_channel_output_module_workflow_spec(module)
    return _build_interface_only_module_workflow_spec(module)


def foundation_workflow_module_specs() -> tuple[dict[str, Any], ...]:
    return tuple(_build_module_workflow_spec(module) for module in FOUNDATION_WORKFLOW_MODULE_BLUEPRINT)


def foundation_workflow_module_blueprint() -> tuple[dict[str, Any], ...]:
    return tuple(_clone(module) for module in FOUNDATION_WORKFLOW_MODULE_BLUEPRINT)


def foundation_workflow_module_bindings_by_key() -> dict[str, dict[str, Any]]:
    modules = {str(module["key"]).strip(): module for module in FOUNDATION_WORKFLOW_MODULE_BLUEPRINT}
    return {
        "channel_input": {
            "moduleKey": "channel_input",
            "moduleWorkflowId": modules["channel_input"]["workflow_id"],
            "moduleInvokeMode": modules["channel_input"]["invoke_mode"],
            "moduleNextKeys": list(modules["channel_input"]["next_module_keys"]),
            "moduleWiringStatus": FOUNDATION_MODULE_INTERFACE_STATUS,
        },
        "security_ingress": {
            "moduleKey": "security_ingress",
            "moduleWorkflowId": modules["security_ingress"]["workflow_id"],
            "moduleInvokeMode": modules["security_ingress"]["invoke_mode"],
            "moduleNextKeys": list(modules["security_ingress"]["next_module_keys"]),
            "moduleWiringStatus": FOUNDATION_MODULE_WRAPPED_STATUS,
        },
        "conversation_ingress": {
            "moduleKey": "conversation_ingress",
            "moduleWorkflowId": modules["conversation_ingress"]["workflow_id"],
            "moduleInvokeMode": modules["conversation_ingress"]["invoke_mode"],
            "moduleNextKeys": list(modules["conversation_ingress"]["next_module_keys"]),
            "moduleWiringStatus": FOUNDATION_MODULE_WRAPPED_STATUS,
        },
        "conversation_egress": {
            "moduleKey": "conversation_egress",
            "moduleWorkflowId": modules["conversation_egress"]["workflow_id"],
            "moduleInvokeMode": modules["conversation_egress"]["invoke_mode"],
            "moduleNextKeys": list(modules["conversation_egress"]["next_module_keys"]),
            "moduleWiringStatus": FOUNDATION_MODULE_WRAPPED_STATUS,
            "plannedChannelOutputWorkflowId": modules["channel_output"]["workflow_id"],
        },
        "security_egress": {
            "moduleKey": "security_egress",
            "moduleWorkflowId": modules["security_egress"]["workflow_id"],
            "moduleInvokeMode": modules["security_egress"]["invoke_mode"],
            "moduleNextKeys": list(modules["security_egress"]["next_module_keys"]),
            "moduleWiringStatus": FOUNDATION_MODULE_WRAPPED_STATUS,
            "plannedChannelOutputWorkflowId": modules["channel_output"]["workflow_id"],
        },
        "channel_output": {
            "moduleKey": "channel_output",
            "moduleWorkflowId": modules["channel_output"]["workflow_id"],
            "moduleInvokeMode": modules["channel_output"]["invoke_mode"],
            "moduleNextKeys": list(modules["channel_output"]["next_module_keys"]),
            "moduleWiringStatus": FOUNDATION_MODULE_WRAPPED_STATUS,
        },
    }


def foundation_workflow_node_interface_bindings() -> dict[str, dict[str, Any]]:
    return foundation_workflow_module_bindings_by_key()
