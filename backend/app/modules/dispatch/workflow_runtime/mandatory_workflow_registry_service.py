from __future__ import annotations

from copy import deepcopy
import logging
from typing import Any

from app.modules.dispatch.workflow_runtime.mandatory_workflow_module_registry_service import (
    FOUNDATION_MODULE_CHANNEL_OUTPUT_WORKFLOW_ID,
    FOUNDATION_MODULE_CONVERSATION_EGRESS_WORKFLOW_ID,
    FOUNDATION_MODULE_CONVERSATION_INGRESS_WORKFLOW_ID,
    FOUNDATION_MODULE_SECURITY_EGRESS_WORKFLOW_ID,
    FOUNDATION_MODULE_SECURITY_INGRESS_WORKFLOW_ID,
    foundation_workflow_module_specs,
    foundation_workflow_module_bindings_by_key,
)
from app.platform.persistence.persistence_service import persistence_service
from app.platform.persistence.runtime_store import LEGACY_WORKFLOW_IDS, store


logger = logging.getLogger(__name__)

FOUNDATION_BRAIN_WORKFLOW_ID = "mandatory-workflow-brain-foundation"
FOUNDATION_BRAIN_WORKFLOW_NAME = "基础工作流 · v2.0"
PROFESSIONAL_AGENT_WORKFLOW_ID = "mandatory-workflow-professional-agent"
PROFESSIONAL_AGENT_WORKFLOW_NAME = "专业agent工作流"
FREE_AGENT_WORKFLOW_ID = "mandatory-workflow-free-agent"
FREE_AGENT_WORKFLOW_NAME = "自由agent工作流"
EXTERNAL_TENTACLE_WORKFLOW_ID = "mandatory-workflow-external-tentacle-dispatch"
LEGACY_WORKFLOW_COMPATIBILITY_ID = "workflow-1"
CONVERSATION_AGENT_PIPELINE_WORKFLOW_ID = "mandatory-workflow-agent-conversation-pipeline"
CONVERSATION_AGENT_PIPELINE_WORKFLOW_NAME = "对话流agent工作流"
CONVERSATION_AGENT_PIPELINE_CONTRACT_VERSION = "agent-workflow-contract-v1"
CONVERSATION_AGENT_PIPELINE_INPUT_CONTRACT: dict[str, Any] = {
    "fields": [
        "trace_id",
        "tenant_context",
        "request_context",
        "security_context",
        "normalized_message",
        "message_history",
        "input_source",
        "requirement_type",
        "upstream_result",
    ],
    "required": ["trace_id", "input_source"],
}
CONVERSATION_AGENT_PIPELINE_OUTPUT_CONTRACT: dict[str, Any] = {
    "fields": [
        "handoff_target",
        "conversation_stage",
        "structured_request_packet",
        "clarification_state",
        "semantic_response",
        "next_step",
    ],
    "required": ["handoff_target", "conversation_stage"],
}
GENERAL_ASSISTANT_AGENT_PIPELINE_WORKFLOW_ID = "mandatory-workflow-agent-general-assistant-pipeline"
GENERAL_ASSISTANT_AGENT_PIPELINE_WORKFLOW_NAME = "万事通agent工作流"
GENERAL_ASSISTANT_AGENT_PIPELINE_CONTRACT_VERSION = "agent-workflow-contract-v1"
GENERAL_ASSISTANT_AGENT_PIPELINE_INPUT_CONTRACT: dict[str, Any] = {
    "fields": [
        "trace_id",
        "tenant_context",
        "request_context",
        "security_context",
        "normalized_message",
        "structured_request_packet",
        "query_scope",
        "professional_query",
        "search_hints",
    ],
    "required": ["trace_id", "normalized_message"],
}
GENERAL_ASSISTANT_AGENT_PIPELINE_OUTPUT_CONTRACT: dict[str, Any] = {
    "fields": [
        "assistant_reply",
        "references",
        "query_mode",
        "response_summary",
        "handoff_target",
    ],
    "required": ["assistant_reply", "query_mode"],
}
REQUIREMENT_DISPATCH_AGENT_PIPELINE_WORKFLOW_ID = "mandatory-workflow-agent-requirement-dispatch-pipeline"
REQUIREMENT_DISPATCH_AGENT_PIPELINE_WORKFLOW_NAME = "需求分发流agent工作流"
REQUIREMENT_DISPATCH_AGENT_PIPELINE_CONTRACT_VERSION = "agent-workflow-contract-v1"
REQUIREMENT_DISPATCH_AGENT_PIPELINE_INPUT_CONTRACT: dict[str, Any] = {
    "fields": [
        "trace_id",
        "tenant_context",
        "request_context",
        "security_context",
        "structured_request_packet",
        "clarification_state",
        "goal_state",
        "scope_state",
        "route_hints",
    ],
    "required": ["trace_id", "structured_request_packet"],
}
REQUIREMENT_DISPATCH_AGENT_PIPELINE_OUTPUT_CONTRACT: dict[str, Any] = {
    "fields": [
        "route_decision",
        "dispatch_packet",
        "target_workflow_type",
        "handoff_target",
        "route_reason_summary",
        "professional_workflow_selection",
    ],
    "required": ["route_decision", "dispatch_packet", "target_workflow_type"],
}
SECURITY_AGENT_PIPELINE_WORKFLOW_ID = "mandatory-workflow-agent-security-pipeline"
SECURITY_AGENT_PIPELINE_WORKFLOW_NAME = "安全流agent工作流"
SECURITY_AGENT_PIPELINE_CONTRACT_VERSION = "agent-workflow-contract-v1"
SECURITY_AGENT_PIPELINE_INPUT_CONTRACT: dict[str, Any] = {
    "fields": [
        "trace_id",
        "tenant_context",
        "security_context",
        "normalized_message",
        "auth_scope",
        "request_context",
    ],
    "required": ["trace_id", "tenant_context", "normalized_message", "auth_scope"],
}
SECURITY_AGENT_PIPELINE_OUTPUT_CONTRACT: dict[str, Any] = {
    "fields": [
        "allowed",
        "allowed_message",
        "security_verdict",
        "security_context",
        "rewrite_diffs_count",
        "warning_count",
        "audit_trace_id",
    ],
    "required": ["allowed", "security_verdict", "audit_trace_id"],
}
DEFAULT_MESSAGE_TRIGGER_CHANNELS = ["telegram", "dingtalk", "wecom", "feishu"]
DEFAULT_MESSAGE_ENTRY_PRIORITY = 620
LEGACY_WORKFLOW_COMPATIBILITY_SPECS: dict[str, dict[str, Any]] = {
    LEGACY_WORKFLOW_COMPATIBILITY_ID: {
        "id": LEGACY_WORKFLOW_COMPATIBILITY_ID,
        "name": "客户服务工作流",
        "description": "处理用户咨询并聚合结果",
        "version": "v2.1",
        "status": "active",
        "trigger": {
            "type": "message",
            "keyword": "搜索, 写作, 帮助",
            "cron": None,
            "webhook_path": None,
            "description": "默认消息入口，按关键词进入客户服务工作流",
            "step_delay_seconds": 0.1,
            "max_dispatch_retry": 6,
            "dispatch_retry_backoff_seconds": 2.0,
            "execution_timeout_seconds": 45.0,
        },
        "agent_bindings": ["2", "1", "3", "6"],
        "nodes": [
            {"id": "1", "type": "trigger", "label": "消息触发", "x": 50, "y": 200},
            {"id": "2", "type": "agent", "label": "安全检测", "x": 280, "y": 120, "agent_id": "2"},
            {"id": "3", "type": "agent", "label": "意图识别", "x": 280, "y": 280, "agent_id": "1"},
            {"id": "4", "type": "condition", "label": "意图分支", "x": 520, "y": 200},
            {"id": "5", "type": "agent", "label": "搜索 Agent", "x": 760, "y": 120, "agent_id": "3"},
            {
                "id": "6",
                "type": "workflow",
                "label": "外接触手执行",
                "x": 760,
                "y": 280,
                "description": "进入外接触手执行子工作流，按意图选择外接检索或写作能力。",
                "workflow_id": EXTERNAL_TENTACLE_WORKFLOW_ID,
                "config": {
                    "handoffNote": "沿用父流程意图，将需求交给外接触手执行层继续完成。",
                },
            },
            {"id": "7", "type": "merge", "label": "结果合流", "x": 1000, "y": 200},
            {"id": "8", "type": "output", "label": "发送结果", "x": 1240, "y": 200, "agent_id": "6"},
        ],
        "edges": [
            {"id": "e1-2", "source": "1", "target": "2", "source_handle": None},
            {"id": "e1-3", "source": "1", "target": "3", "source_handle": None},
            {"id": "e2-4", "source": "2", "target": "4", "source_handle": None},
            {"id": "e3-4", "source": "3", "target": "4", "source_handle": None},
            {"id": "e4-5", "source": "4", "target": "5", "source_handle": "true"},
            {"id": "e4-6", "source": "4", "target": "6", "source_handle": "false"},
            {"id": "e5-7", "source": "5", "target": "7", "source_handle": None},
            {"id": "e6-7", "source": "6", "target": "7", "source_handle": None},
            {"id": "e7-8", "source": "7", "target": "8", "source_handle": None},
        ],
    },
    EXTERNAL_TENTACLE_WORKFLOW_ID: {
        "id": EXTERNAL_TENTACLE_WORKFLOW_ID,
        "name": "外接触手执行工作流",
        "description": "承接主脑分发结果，并按意图选择外接检索或写作能力执行。",
        "version": "v1.0",
        "status": "active",
        "trigger": {
            "type": "manual",
            "keyword": None,
            "cron": None,
            "webhook_path": None,
            "internal_event": None,
            "description": "由基础工作流 · v2.0 的分发节点或运维手动触发。",
            "priority": 180,
            "channels": [],
            "preferred_language": None,
            "step_delay_seconds": 0.1,
            "max_dispatch_retry": 6,
            "dispatch_retry_backoff_seconds": 2.0,
            "execution_timeout_seconds": 45.0,
            "natural_language_rule": None,
            "schedule_plan": None,
        },
        "agent_bindings": ["search", "write"],
        "nodes": [
            {
                "id": "1",
                "type": "trigger",
                "label": "分发触发",
                "x": 60,
                "y": 180,
                "description": "接收来自基础工作流 · v2.0 的 handoff 请求。",
                "config": {"summary": "brain orchestrator handoff"},
            },
            {
                "id": "2",
                "type": "condition",
                "label": "执行意图路由",
                "x": 300,
                "y": 180,
                "description": "根据需求分析结果决定走外接检索还是外接写作触手。",
            },
            {
                "id": "3",
                "type": "agent",
                "label": "外接检索触手",
                "x": 580,
                "y": 100,
                "description": "优先选择外部已注册的 search agent/skill/mcp 执行能力。",
                "agent_id": "search",
                "config": {
                    "instruction": "优先调用外接检索触手，返回可引用结果。",
                    "result_kind": "search_report",
                },
            },
            {
                "id": "4",
                "type": "agent",
                "label": "外接写作触手",
                "x": 580,
                "y": 260,
                "description": "优先选择外部已注册的 write agent/skill/mcp 执行能力。",
                "agent_id": "write",
                "config": {
                    "instruction": "优先调用外接写作触手，输出可直接交付草稿。",
                    "result_kind": "draft_message",
                },
            },
        ],
        "edges": [
            {"id": "e1-2", "source": "1", "target": "2"},
            {"id": "e2-3", "source": "2", "target": "3"},
            {"id": "e2-4", "source": "2", "target": "4"},
        ],
    },
}

MANDATORY_WORKFLOW_SPECS: tuple[dict[str, Any], ...] = (
    {
        "id": FOUNDATION_BRAIN_WORKFLOW_ID,
        "name": FOUNDATION_BRAIN_WORKFLOW_NAME,
        "description": "系统主工作流已收口为可视化基础主链：渠道输入、安全agent（入站）、对话agent（接待）、对话agent（回传）、安全agent（出站）、渠道输出。",
        "version": "v2.0",
        "status": "active",
        "trigger": {
            "type": "message",
            "keyword": None,
            "cron": None,
            "webhook_path": None,
            "internal_event": None,
            "description": "默认渠道入口，所有渠道消息优先进入基础工作流 · v2.0。",
            "priority": DEFAULT_MESSAGE_ENTRY_PRIORITY,
            "channels": DEFAULT_MESSAGE_TRIGGER_CHANNELS,
            "preferred_language": None,
            "step_delay_seconds": 0.1,
            "max_dispatch_retry": 6,
            "dispatch_retry_backoff_seconds": 2.0,
            "execution_timeout_seconds": 45.0,
            "natural_language_rule": "所有渠道消息默认先进入基础工作流主链，按渠道输入、安全agent（入站）、对话agent（接待）、对话agent（回传）、安全agent（出站）、渠道输出顺序轮转。",
            "schedule_plan": None,
        },
        "nodes": [
            {
                "id": "1",
                "type": "trigger",
                "label": "渠道输入",
                "x": 120,
                "y": 40,
                "description": "统一接收渠道消息，作为基础工作流的唯一图上入口。",
                "config": {
                    "summary": "channel ingress -> foundation workflow",
                    "moduleKey": "channel_input",
                },
            },
            {
                "id": "2",
                "type": "agent",
                "label": "安全agent",
                "x": 120,
                "y": 180,
                "description": "进入安全agent模块，执行入站安全检查。",
                "agent_id": "security",
                "config": {
                    "moduleKey": "security_ingress",
                    "handoffNote": "当前处于基础工作流入站安全阶段，请完成安全审查后继续流转。",
                },
            },
            {
                "id": "3",
                "type": "agent",
                "label": "对话agent",
                "x": 120,
                "y": 320,
                "description": "进入对话agent模块，负责接住用户并理解需求。",
                "agent_id": "conversation",
                "config": {
                    "moduleKey": "conversation_ingress",
                    "handoffNote": "当前处于基础工作流接待阶段，请完成需求理解与首轮对话承接。",
                },
            },
            {
                "id": "4",
                "type": "agent",
                "label": "对话agent",
                "x": 120,
                "y": 500,
                "description": "接待阶段完成后，进入对话agent统一整理回复。",
                "agent_id": "conversation",
                "config": {
                    "moduleKey": "conversation_egress",
                    "handoffNote": "请读取上游对话结果，整理为统一对外回复。",
                },
            },
            {
                "id": "5",
                "type": "agent",
                "label": "安全agent",
                "x": 120,
                "y": 680,
                "description": "最终回传前进入安全agent模块完成出站复核。",
                "agent_id": "security",
                "config": {
                    "moduleKey": "security_egress",
                    "handoffNote": "请在最终回传前完成安全出站复核。",
                },
            },
            {
                "id": "6",
                "type": "output",
                "label": "渠道输出",
                "x": 120,
                "y": 860,
                "description": "渠道出站节点，负责完成最终结果回传。",
                "config": {
                    "moduleKey": "channel_output",
                    "handoffNote": "请将已通过安全复核的结果回传到对应渠道。",
                },
            },
        ],
        "edges": [
            {"id": "e1-2", "source": "1", "target": "2"},
            {"id": "e2-3", "source": "2", "target": "3"},
            {"id": "e3-4", "source": "3", "target": "4"},
            {"id": "e4-5", "source": "4", "target": "5"},
            {"id": "e5-6", "source": "5", "target": "6"},
        ],
    },
    {
        "id": PROFESSIONAL_AGENT_WORKFLOW_ID,
        "name": PROFESSIONAL_AGENT_WORKFLOW_NAME,
        "description": "专业工作流的占位接口，当前仅保留专业任务下发、找寻专业工作流、执行专业工作流与返回进程的可视化骨架，默认通过。",
        "version": "v1.0",
        "status": "active",
        "trigger": {
            "type": "manual",
            "keyword": None,
            "cron": None,
            "webhook_path": None,
            "internal_event": None,
            "description": "专业工作流总入口，占位保留接口，后续在这里挂接具体专业事件。",
            "priority": 210,
            "channels": [],
            "preferred_language": None,
            "step_delay_seconds": 0.6,
            "max_dispatch_retry": 6,
            "dispatch_retry_backoff_seconds": 2.0,
            "execution_timeout_seconds": 45.0,
            "natural_language_rule": "专业agent工作流只按可视化链路中的专业工作流下发任务、找寻专业工作流、执行专业工作流、返回进程顺序轮转。",
            "schedule_plan": None,
        },
        "nodes": [
            {
                "id": "1",
                "type": "trigger",
                "label": "专业工作流",
                "x": 760,
                "y": 60,
                "description": "专业工作流占位入口，统一接收后续专业场景任务。",
                "config": {
                    "summary": "professional.agent.workflow.manual_entry",
                },
            },
            {
                "id": "2",
                "type": "transform",
                "label": "专业工作流下发任务",
                "x": 760,
                "y": 220,
                "description": "接收专业任务并保留后续挂接专业事件的接口。",
                "config": {
                    "transform_note": "已完成专业工作流下发任务占位接口，当前默认通过。",
                },
            },
            {
                "id": "3",
                "type": "transform",
                "label": "找寻专业工作流",
                "x": 760,
                "y": 380,
                "description": "当前先保留专业工作流查找接口，后续在此挂接真实专业流选择逻辑。",
                "config": {
                    "transform_note": "已完成找寻专业工作流占位接口，当前默认通过。",
                },
            },
            {
                "id": "4",
                "type": "transform",
                "label": "执行专业工作流",
                "x": 760,
                "y": 540,
                "description": "当前先保留专业工作流执行接口，暂不挂接具体专业事件。",
                "config": {
                    "transform_note": "已完成执行专业工作流占位接口，当前默认通过。",
                },
            },
            {
                "id": "5",
                "type": "output",
                "label": "返回进程",
                "x": 760,
                "y": 700,
                "description": "返回当前专业工作流占位结果，后续由具体专业事件覆盖。",
                "config": {
                    "handoffTarget": "next_step",
                },
            },
        ],
        "edges": [
            {"id": "e1-2", "source": "1", "target": "2"},
            {"id": "e2-3", "source": "2", "target": "3"},
            {"id": "e3-4", "source": "3", "target": "4"},
            {"id": "e4-5", "source": "4", "target": "5"},
        ],
    },
    {
        "id": FREE_AGENT_WORKFLOW_ID,
        "name": FREE_AGENT_WORKFLOW_NAME,
        "description": "自由工作流的占位接口，当前仅保留自由任务下发、在外接触手库中找寻对应角色、执行自由工作流与返回进程的可视化骨架，默认通过。",
        "version": "v1.0",
        "status": "active",
        "trigger": {
            "type": "manual",
            "keyword": None,
            "cron": None,
            "webhook_path": None,
            "internal_event": None,
            "description": "自由工作流总入口，占位保留接口，后续在这里挂接具体自由事件。",
            "priority": 211,
            "channels": [],
            "preferred_language": None,
            "step_delay_seconds": 0.6,
            "max_dispatch_retry": 6,
            "dispatch_retry_backoff_seconds": 2.0,
            "execution_timeout_seconds": 45.0,
            "natural_language_rule": "自由agent工作流只按可视化链路中的自由工作流下发任务、在外接触手库中找寻对应的角色来、执行自由工作流、返回进程顺序轮转。",
            "schedule_plan": None,
        },
        "nodes": [
            {
                "id": "1",
                "type": "trigger",
                "label": "自由工作流",
                "x": 760,
                "y": 60,
                "description": "自由工作流占位入口，统一接收后续自由场景任务。",
                "config": {
                    "summary": "free.agent.workflow.manual_entry",
                },
            },
            {
                "id": "2",
                "type": "transform",
                "label": "自由工作流下发任务",
                "x": 760,
                "y": 220,
                "description": "接收自由任务并保留后续挂接自由事件的接口。",
                "config": {
                    "transform_note": "已完成自由工作流下发任务占位接口，当前默认通过。",
                },
            },
            {
                "id": "3",
                "type": "transform",
                "label": "在外接触手库中找寻对应的角色来",
                "x": 760,
                "y": 380,
                "description": "当前先保留外接触手角色查找接口，后续在此挂接真实自由角色选择逻辑。",
                "config": {
                    "transform_note": "已完成外接触手角色查找占位接口，当前默认通过。",
                },
            },
            {
                "id": "4",
                "type": "transform",
                "label": "执行自由工作流",
                "x": 760,
                "y": 540,
                "description": "当前先保留自由工作流执行接口，暂不挂接具体自由事件。",
                "config": {
                    "transform_note": "已完成执行自由工作流占位接口，当前默认通过。",
                },
            },
            {
                "id": "5",
                "type": "output",
                "label": "返回进程",
                "x": 760,
                "y": 700,
                "description": "返回当前自由工作流占位结果，后续由具体自由事件覆盖。",
                "config": {
                    "handoffTarget": "next_step",
                },
            },
        ],
        "edges": [
            {"id": "e1-2", "source": "1", "target": "2"},
            {"id": "e2-3", "source": "2", "target": "3"},
            {"id": "e3-4", "source": "3", "target": "4"},
            {"id": "e4-5", "source": "4", "target": "5"},
        ],
    },
    {
        "id": EXTERNAL_TENTACLE_WORKFLOW_ID,
        "name": "外接触手执行工作流",
        "description": "承接主脑分发结果，并按意图选择外接检索或写作能力执行。",
        "version": "v1.0",
        "status": "active",
        "trigger": {
            "type": "manual",
            "keyword": None,
            "cron": None,
            "webhook_path": None,
            "internal_event": None,
            "description": "由基础工作流 · v2.0 的分发节点或运维手动触发。",
            "priority": 180,
            "channels": [],
            "preferred_language": None,
            "step_delay_seconds": 0.6,
            "max_dispatch_retry": 6,
            "dispatch_retry_backoff_seconds": 2.0,
            "execution_timeout_seconds": 45.0,
            "natural_language_rule": None,
            "schedule_plan": None,
        },
        "nodes": [
            {
                "id": "1",
                "type": "trigger",
                "label": "分发触发",
                "x": 60,
                "y": 180,
                "description": "接收来自基础工作流 · v2.0 的 handoff 请求。",
                "config": {
                    "summary": "brain orchestrator handoff",
                },
            },
            {
                "id": "2",
                "type": "condition",
                "label": "执行意图路由",
                "x": 300,
                "y": 180,
                "description": "根据需求分析结果决定走外接检索还是外接写作触手。",
            },
            {
                "id": "3",
                "type": "agent",
                "label": "外接检索触手",
                "x": 580,
                "y": 100,
                "description": "优先选择外部已注册的 search agent/skill/mcp 执行能力。",
                "agent_id": "search",
                "config": {
                    "instruction": "优先调用外接检索触手，返回可引用结果。",
                    "result_kind": "search_report",
                },
            },
            {
                "id": "4",
                "type": "agent",
                "label": "外接写作触手",
                "x": 580,
                "y": 260,
                "description": "优先选择外部已注册的 write agent/skill/mcp 执行能力。",
                "agent_id": "write",
                "config": {
                    "instruction": "优先调用外接写作触手，输出可直接交付草稿。",
                    "result_kind": "draft_message",
                },
            },
        ],
        "edges": [
            {
                "id": "e1-2",
                "source": "1",
                "target": "2",
            },
            {
                "id": "e2-3",
                "source": "2",
                "target": "3",
            },
            {
                "id": "e2-4",
                "source": "2",
                "target": "4",
            },
        ],
    },
    {
        "id": "mandatory-workflow-conversation",
        "name": "对话 Agent 工作流",
        "description": "负责理解客户需求并确认客户需求，再整理结构化交接摘要。",
        "version": "v1.0",
        "status": "active",
        "trigger": {
            "type": "internal",
            "keyword": None,
            "cron": None,
            "webhook_path": None,
            "internal_event": "mandatory.agent.conversation.requested",
            "description": "对话 Agent 内部编排入口",
            "priority": 220,
            "channels": [],
            "preferred_language": None,
            "step_delay_seconds": 0.6,
            "max_dispatch_retry": 6,
            "dispatch_retry_backoff_seconds": 2.0,
            "execution_timeout_seconds": 45.0,
            "natural_language_rule": None,
            "schedule_plan": None,
        },
        "nodes": [
            {
                "id": "1",
                "type": "trigger",
                "label": "内部触发",
                "x": 60,
                "y": 120,
                "description": "接收对话 Agent 的内部编排触发事件。",
                "config": {
                    "summary": "mandatory.agent.conversation.requested",
                },
            },
            {
                "id": "2",
                "type": "agent",
                "label": "对话 Agent · 理解客户需求",
                "x": 300,
                "y": 120,
                "description": "先理解客户目标、背景、约束与期望交付物，形成需求理解摘要。",
                "agent_id": "conversation",
                "config": {
                    "instruction": "优先复述并结构化理解客户需求，不做派工。",
                    "result_kind": "requirement_understanding",
                },
            },
            {
                "id": "3",
                "type": "agent",
                "label": "对话 Agent · 确认客户需求",
                "x": 580,
                "y": 120,
                "description": "基于理解摘要向客户做需求确认，明确边界后输出可交接信息。",
                "agent_id": "conversation",
                "config": {
                    "instruction": "确认客户需求、范围与完成标准，再输出交接摘要。",
                    "result_kind": "structured_request_packet",
                },
            },
        ],
        "edges": [
            {
                "id": "e1-2",
                "source": "1",
                "target": "2",
            },
            {
                "id": "e2-3",
                "source": "2",
                "target": "3",
            }
        ],
    },
    {
        "id": CONVERSATION_AGENT_PIPELINE_WORKFLOW_ID,
        "name": CONVERSATION_AGENT_PIPELINE_WORKFLOW_NAME,
        "description": "把对话agent收口为输入识别、需求分流、客户确认与结果交接的可视化对话链路。",
        "version": "v1.0",
        "status": "active",
        "trigger": {
            "type": "internal",
            "keyword": None,
            "cron": None,
            "webhook_path": None,
            "internal_event": "mandatory.agent.conversation.pipeline_requested",
            "description": "对话流 agent 工作流内部入口",
            "priority": 235,
            "channels": [],
            "preferred_language": None,
            "step_delay_seconds": 0.6,
            "max_dispatch_retry": 6,
            "dispatch_retry_backoff_seconds": 2.0,
            "execution_timeout_seconds": 45.0,
            "natural_language_rule": "对话agent只按可视化工作流中展示的输入判断、需求分类、客户确认和结果交接节点顺序轮转。",
            "schedule_plan": None,
        },
        "nodes": [
            {
                "id": "1",
                "type": "trigger",
                "label": "输入",
                "x": 920,
                "y": 40,
                "description": "统一接收渠道消息或上游最终处理结果。",
                "config": {
                    "summary": "mandatory.agent.conversation.pipeline_requested",
                    "contractVersion": CONVERSATION_AGENT_PIPELINE_CONTRACT_VERSION,
                    "inputContract": deepcopy(CONVERSATION_AGENT_PIPELINE_INPUT_CONTRACT),
                },
            },
            {
                "id": "2",
                "type": "condition",
                "label": "判断是不是'渠道输入'",
                "x": 920,
                "y": 200,
                "description": "区分当前输入来自渠道接待，还是来自上游最终处理结果。",
                "config": {
                    "expression": "channel_input",
                    "result_key": "input_source_gate",
                },
            },
            {
                "id": "3",
                "type": "condition",
                "label": "判断需求类型",
                "x": 500,
                "y": 360,
                "description": "渠道输入进入需求分类，区分查询诉求和下发任务诉求。",
                "config": {
                    "expression": "query_request",
                    "result_key": "requirement_type_gate",
                },
            },
            {
                "id": "4",
                "type": "transform",
                "label": "查询类",
                "x": 180,
                "y": 520,
                "description": "识别为查询诉求后，整理问题、目标和查询上下文。",
                "config": {
                    "transform_note": "将当前诉求整理为查询类需求，不做任务分发。",
                    "result_key": "query_request_packet",
                },
            },
            {
                "id": "5",
                "type": "transform",
                "label": "确认客户需求",
                "x": 180,
                "y": 680,
                "description": "确认查询目标、范围和交付期待。",
                "config": {
                    "transform_note": "面向查询类诉求确认客户需求，并补齐必要上下文。",
                    "result_key": "conversation_confirmation",
                },
            },
            {
                "id": "6",
                "type": "output",
                "label": "输出给万事通Agent",
                "x": 180,
                "y": 840,
                "description": "把确认后的查询类需求交给万事通agent继续处理。",
                "config": {
                    "handoffTarget": "general_assistant",
                    "conversationStage": "query_confirmed",
                    "contractVersion": CONVERSATION_AGENT_PIPELINE_CONTRACT_VERSION,
                    "outputContract": deepcopy(CONVERSATION_AGENT_PIPELINE_OUTPUT_CONTRACT),
                },
            },
            {
                "id": "7",
                "type": "transform",
                "label": "下发任务类",
                "x": 620,
                "y": 520,
                "description": "识别为下发任务诉求后，整理目标、边界和执行信息。",
                "config": {
                    "transform_note": "将当前诉求整理为下发任务类需求，准备进入需求分发。",
                    "result_key": "dispatch_request_packet",
                },
            },
            {
                "id": "8",
                "type": "transform",
                "label": "确认客户需求",
                "x": 620,
                "y": 680,
                "description": "确认任务目标、范围和交付标准。",
                "config": {
                    "transform_note": "面向下发任务类诉求确认客户需求，并补齐执行边界。",
                    "result_key": "conversation_confirmation",
                },
            },
            {
                "id": "9",
                "type": "output",
                "label": "输出给需求分发agent",
                "x": 620,
                "y": 840,
                "description": "把确认后的任务类需求交给需求分发agent继续处理。",
                "config": {
                    "handoffTarget": "requirement_dispatcher",
                    "conversationStage": "dispatch_confirmed",
                    "contractVersion": CONVERSATION_AGENT_PIPELINE_CONTRACT_VERSION,
                    "outputContract": deepcopy(CONVERSATION_AGENT_PIPELINE_OUTPUT_CONTRACT),
                },
            },
            {
                "id": "10",
                "type": "transform",
                "label": "接收最终处理信息，进行语义化处理",
                "x": 1320,
                "y": 520,
                "description": "接收上游最终处理信息并整理成面向下一步的自然语言结果。",
                "config": {
                    "transform_note": "将上游最终处理信息语义化整理，输出清晰自然的结果摘要。",
                    "result_key": "semantic_response",
                },
            },
            {
                "id": "11",
                "type": "output",
                "label": "输出结果给下一步",
                "x": 1320,
                "y": 760,
                "description": "输出语义化结果，继续交给下一步工作流节点。",
                "config": {
                    "handoffTarget": "next_step",
                    "conversationStage": "final_result_semanticized",
                    "contractVersion": CONVERSATION_AGENT_PIPELINE_CONTRACT_VERSION,
                    "outputContract": deepcopy(CONVERSATION_AGENT_PIPELINE_OUTPUT_CONTRACT),
                },
            },
        ],
        "edges": [
            {
                "id": "e1-2",
                "source": "1",
                "target": "2",
            },
            {
                "id": "e2-3",
                "source": "2",
                "source_handle": "true",
                "target": "3",
            },
            {
                "id": "e2-10",
                "source": "2",
                "source_handle": "false",
                "target": "10",
            },
            {
                "id": "e3-4",
                "source": "3",
                "source_handle": "true",
                "target": "4",
            },
            {
                "id": "e3-7",
                "source": "3",
                "source_handle": "false",
                "target": "7",
            },
            {
                "id": "e4-5",
                "source": "4",
                "target": "5",
            },
            {
                "id": "e5-6",
                "source": "5",
                "target": "6",
            },
            {
                "id": "e7-8",
                "source": "7",
                "target": "8",
            },
            {
                "id": "e8-9",
                "source": "8",
                "target": "9",
            },
            {
                "id": "e10-11",
                "source": "10",
                "target": "11",
            },
        ],
    },
    {
        "id": GENERAL_ASSISTANT_AGENT_PIPELINE_WORKFLOW_ID,
        "name": GENERAL_ASSISTANT_AGENT_PIPELINE_WORKFLOW_NAME,
        "description": "把万事通agent收口为输入识别、专业查询判断、专业知识查询或联网查询，再统一输出结果的可视化问答链路。",
        "version": "v1.0",
        "status": "active",
        "trigger": {
            "type": "internal",
            "keyword": None,
            "cron": None,
            "webhook_path": None,
            "internal_event": "mandatory.agent.general_assistant.pipeline_requested",
            "description": "万事通 agent 工作流内部入口",
            "priority": 238,
            "channels": [],
            "preferred_language": None,
            "step_delay_seconds": 0.6,
            "max_dispatch_retry": 6,
            "dispatch_retry_backoff_seconds": 2.0,
            "execution_timeout_seconds": 45.0,
            "natural_language_rule": "万事通agent只按可视化工作流中展示的专业查询判断、专业知识查询、联网查询和统一输出节点顺序轮转。",
            "schedule_plan": None,
        },
        "nodes": [
            {
                "id": "1",
                "type": "trigger",
                "label": "输入",
                "x": 760,
                "y": 60,
                "description": "统一接收查询诉求、需求包和必要上下文。",
                "config": {
                    "summary": "mandatory.agent.general_assistant.pipeline_requested",
                    "contractVersion": GENERAL_ASSISTANT_AGENT_PIPELINE_CONTRACT_VERSION,
                    "inputContract": deepcopy(GENERAL_ASSISTANT_AGENT_PIPELINE_INPUT_CONTRACT),
                },
            },
            {
                "id": "2",
                "type": "condition",
                "label": "判断是不是'专业查询'",
                "x": 760,
                "y": 240,
                "description": "判断当前查询是否属于专业查询，决定走系统内专业知识与流程，还是走联网查询。",
                "config": {
                    "expression": "professional_query",
                    "result_key": "general_assistant_query_gate",
                },
            },
            {
                "id": "3",
                "type": "agent",
                "label": "查询系统内专业知识库和专业流程",
                "x": 360,
                "y": 440,
                "description": "命中专业查询后，优先读取系统内专业知识库和专业流程资料并组织结果。",
                "agent_id": "general_assistant",
                "config": {
                    "instruction": "优先查询系统内专业知识库和专业流程，不做联网搜索，并输出可直接交付的专业查询结果。",
                    "result_kind": "professional_query_response",
                },
            },
            {
                "id": "4",
                "type": "agent",
                "label": "联网查询",
                "x": 1160,
                "y": 440,
                "description": "未命中专业查询时，改走联网查询并整理可引用结果。",
                "agent_id": "general_assistant",
                "config": {
                    "instruction": "执行联网查询，整理结果与引用来源，输出可直接交付的查询答复。",
                    "result_kind": "web_query_response",
                },
            },
            {
                "id": "5",
                "type": "output",
                "label": "输出",
                "x": 760,
                "y": 680,
                "description": "统一输出查询结果，交给下一步工作流节点。",
                "config": {
                    "handoffTarget": "next_step",
                    "contractVersion": GENERAL_ASSISTANT_AGENT_PIPELINE_CONTRACT_VERSION,
                    "outputContract": deepcopy(GENERAL_ASSISTANT_AGENT_PIPELINE_OUTPUT_CONTRACT),
                },
            },
        ],
        "edges": [
            {
                "id": "e1-2",
                "source": "1",
                "target": "2",
            },
            {
                "id": "e2-3",
                "source": "2",
                "source_handle": "true",
                "target": "3",
            },
            {
                "id": "e2-4",
                "source": "2",
                "source_handle": "false",
                "target": "4",
            },
            {
                "id": "e3-5",
                "source": "3",
                "target": "5",
            },
            {
                "id": "e4-5",
                "source": "4",
                "target": "5",
            },
        ],
    },
    {
        "id": "mandatory-workflow-security",
        "name": "安全 Agent 工作流",
        "description": "负责语义级安全审查、风险说明与审批升级建议。",
        "version": "v1.0",
        "status": "active",
        "trigger": {
            "type": "internal",
            "keyword": None,
            "cron": None,
            "webhook_path": None,
            "internal_event": "mandatory.agent.security.review_requested",
            "description": "安全 Agent 内部风险审查入口",
            "priority": 260,
            "channels": [],
            "preferred_language": None,
            "step_delay_seconds": 0.6,
            "max_dispatch_retry": 6,
            "dispatch_retry_backoff_seconds": 2.0,
            "execution_timeout_seconds": 45.0,
            "natural_language_rule": None,
            "schedule_plan": None,
        },
        "nodes": [
            {
                "id": "1",
                "type": "trigger",
                "label": "内部触发",
                "x": 60,
                "y": 120,
                "description": "接收安全审查内部事件。",
                "config": {
                    "summary": "mandatory.agent.security.review_requested",
                },
            },
            {
                "id": "2",
                "type": "agent",
                "label": "安全 Agent",
                "x": 280,
                "y": 120,
                "description": "输出风险标签、原因与审批建议。",
                "agent_id": "security",
                "config": {
                    "instruction": "只做风险审查和说明，不替代本地安全真相源。",
                    "result_kind": "risk_assessment",
                },
            },
        ],
        "edges": [
            {
                "id": "e1-2",
                "source": "1",
                "target": "2",
            }
        ],
    },
    {
        "id": SECURITY_AGENT_PIPELINE_WORKFLOW_ID,
        "name": SECURITY_AGENT_PIPELINE_WORKFLOW_NAME,
        "description": "把安全agent收口为五层安全链路：限流、认证 / RBAC 权限校验、Prompt Injection 双检、内容策略 / 数据脱敏改写、审计追踪，并保留明确输入与输出。",
        "version": "v1.0",
        "status": "active",
        "trigger": {
            "type": "internal",
            "keyword": None,
            "cron": None,
            "webhook_path": None,
            "internal_event": "mandatory.agent.security.pipeline_requested",
            "description": "安全流 agent 工作流内部入口",
            "priority": 255,
            "channels": [],
            "preferred_language": None,
            "step_delay_seconds": 0.6,
            "max_dispatch_retry": 6,
            "dispatch_retry_backoff_seconds": 2.0,
            "execution_timeout_seconds": 45.0,
            "natural_language_rule": "安全agent只按可视化工作流中展示的五层安全链路顺序轮转。",
            "schedule_plan": None,
        },
        "nodes": [
            {
                "id": "1",
                "type": "trigger",
                "label": "安全请求输入",
                "x": 60,
                "y": 160,
                "description": "统一接收待审查文本、租户上下文、权限上下文与安全追踪信息。",
                "config": {
                    "summary": "mandatory.agent.security.pipeline_requested",
                    "contractVersion": SECURITY_AGENT_PIPELINE_CONTRACT_VERSION,
                    "inputContract": deepcopy(SECURITY_AGENT_PIPELINE_INPUT_CONTRACT),
                },
            },
            {
                "id": "2",
                "type": "condition",
                "label": "限流",
                "x": 280,
                "y": 160,
                "description": "先做速率限制判断，拦截异常高频或超配额请求。",
                "config": {
                    "gate": "rate_limit",
                    "result_key": "rate_limit_verdict",
                },
            },
            {
                "id": "3",
                "type": "condition",
                "label": "认证 / RBAC 权限校验",
                "x": 540,
                "y": 160,
                "description": "校验调用身份、auth scope 与租户内 RBAC 权限边界。",
                "config": {
                    "gate": "auth_scope_rbac",
                    "result_key": "auth_scope_verdict",
                },
            },
            {
                "id": "4",
                "type": "condition",
                "label": "Prompt Injection 双检",
                "x": 860,
                "y": 160,
                "description": "先做规则检测，再做模型级判定，统一形成注入风险结论。",
                "config": {
                    "gate": "prompt_injection_dual_check",
                    "detectors": ["rule_based", "model_based"],
                    "result_key": "prompt_injection_assessment",
                },
            },
            {
                "id": "5",
                "type": "transform",
                "label": "内容策略 / 数据脱敏改写",
                "x": 1160,
                "y": 160,
                "description": "按内容策略执行脱敏、改写或原样放行，产出可继续流转的安全文本。",
                "config": {
                    "transform_note": "content policy enforcement with redaction and rewrite",
                    "result_key": "content_policy_result",
                },
            },
            {
                "id": "6",
                "type": "transform",
                "label": "审计追踪",
                "x": 1460,
                "y": 160,
                "description": "落审计记录、追踪 trace 元数据，并保留 append-only 安全证据。",
                "config": {
                    "transform_note": "append-only audit trail with trace metadata",
                    "result_key": "audit_trace",
                },
            },
            {
                "id": "7",
                "type": "output",
                "label": "安全结果输出",
                "x": 1740,
                "y": 160,
                "description": "输出安全判定、脱敏结果、告警计数与审计追踪信息。",
                "config": {
                    "contractVersion": SECURITY_AGENT_PIPELINE_CONTRACT_VERSION,
                    "outputContract": deepcopy(SECURITY_AGENT_PIPELINE_OUTPUT_CONTRACT),
                    "output_requirement": "必须返回 allowed、安全上下文、rewrite 结果与 audit_trace_id。",
                },
            },
        ],
        "edges": [
            {
                "id": "e1-2",
                "source": "1",
                "target": "2",
            },
            {
                "id": "e2-3",
                "source": "2",
                "target": "3",
            },
            {
                "id": "e3-4",
                "source": "3",
                "target": "4",
            },
            {
                "id": "e4-5",
                "source": "4",
                "target": "5",
            },
            {
                "id": "e5-6",
                "source": "5",
                "target": "6",
            },
            {
                "id": "e6-7",
                "source": "6",
                "target": "7",
            },
        ],
    },
    {
        "id": "mandatory-workflow-workflow-designer",
        "name": "创建工作流 Agent 工作流",
        "description": "负责读取可见能力并生成需要人工审批的工作流提案。",
        "version": "v1.0",
        "status": "active",
        "trigger": {
            "type": "internal",
            "keyword": None,
            "cron": None,
            "webhook_path": None,
            "internal_event": "mandatory.agent.workflow_designer.proposal_requested",
            "description": "创建工作流 Agent 内部提案入口",
            "priority": 200,
            "channels": [],
            "preferred_language": None,
            "step_delay_seconds": 0.6,
            "max_dispatch_retry": 6,
            "dispatch_retry_backoff_seconds": 2.0,
            "execution_timeout_seconds": 45.0,
            "natural_language_rule": None,
            "schedule_plan": None,
        },
        "nodes": [
            {
                "id": "1",
                "type": "trigger",
                "label": "内部触发",
                "x": 60,
                "y": 120,
                "description": "接收工作流提案内部事件。",
                "config": {
                    "summary": "mandatory.agent.workflow_designer.proposal_requested",
                },
            },
            {
                "id": "2",
                "type": "agent",
                "label": "创建工作流 Agent",
                "x": 280,
                "y": 120,
                "description": "只生成提案，不自动发布工作流。",
                "agent_id": "workflow_designer",
                "config": {
                    "instruction": "显式输出审批点、依赖、回滚方案。",
                    "result_kind": "workflow_proposal",
                    "approval_required": True,
                },
            },
        ],
        "edges": [
            {
                "id": "e1-2",
                "source": "1",
                "target": "2",
            }
        ],
    },
    {
        "id": "mandatory-workflow-memory",
        "name": "记忆 Agent 工作流",
        "description": "负责租户内人员画像蒸馏、偏好抽取与记忆治理。",
        "version": "v1.0",
        "status": "active",
        "trigger": {
            "type": "internal",
            "keyword": None,
            "cron": None,
            "webhook_path": None,
            "internal_event": "mandatory.agent.memory.distill_requested",
            "description": "记忆 Agent 内部蒸馏入口",
            "priority": 180,
            "channels": [],
            "preferred_language": None,
            "step_delay_seconds": 0.6,
            "max_dispatch_retry": 6,
            "dispatch_retry_backoff_seconds": 2.0,
            "execution_timeout_seconds": 45.0,
            "natural_language_rule": None,
            "schedule_plan": None,
        },
        "nodes": [
            {
                "id": "1",
                "type": "trigger",
                "label": "内部触发",
                "x": 60,
                "y": 120,
                "description": "接收记忆蒸馏内部事件。",
                "config": {
                    "summary": "mandatory.agent.memory.distill_requested",
                },
            },
            {
                "id": "2",
                "type": "agent",
                "label": "记忆 Agent",
                "x": 280,
                "y": 120,
                "description": "执行画像蒸馏、偏好抽取与记忆治理。",
                "agent_id": "memory",
                "config": {
                    "instruction": "只写 distillation 结果，不写原始敏感内容。",
                    "result_kind": "memory_summary",
                },
            },
        ],
        "edges": [
            {
                "id": "e1-2",
                "source": "1",
                "target": "2",
            }
        ],
    },
    *foundation_workflow_module_specs(),
)
MANDATORY_WORKFLOW_SPECS = tuple(
    spec
    for spec in MANDATORY_WORKFLOW_SPECS
    if str(spec.get("id") or "").strip() not in LEGACY_WORKFLOW_IDS
)


def _clone(value: object) -> object:
    clone = getattr(store, "clone", None)
    if callable(clone):
        return clone(value)
    return deepcopy(value)


def _find_runtime_workflow(workflow_id: str) -> dict[str, Any] | None:
    for workflow in getattr(store, "workflows", []):
        if str(workflow.get("id") or "").strip() == workflow_id:
            return workflow
    return None


def _upsert_runtime_workflow(workflow_payload: dict[str, Any]) -> dict[str, Any]:
    cloned = _clone(workflow_payload)
    existing = _find_runtime_workflow(str(workflow_payload.get("id") or "").strip())
    if existing is None:
        getattr(store, "workflows", []).append(cloned)
        return cloned

    existing.clear()
    existing.update(cloned)
    return existing


def _active_mandatory_workflow_specs() -> tuple[dict[str, Any], ...]:
    return tuple(
        spec
        for spec in MANDATORY_WORKFLOW_SPECS
        if str(spec.get("id") or "").strip() not in LEGACY_WORKFLOW_IDS
    )


def _purge_legacy_workflows() -> None:
    delete_workflows = getattr(store, "delete_workflows", None)
    removed_runtime: list[str] = []
    if callable(delete_workflows):
        removed_runtime = list(delete_workflows(LEGACY_WORKFLOW_IDS))
    else:
        retained_workflows = []
        for workflow in getattr(store, "workflows", []):
            workflow_id = str(workflow.get("id") or "").strip()
            if workflow_id in LEGACY_WORKFLOW_IDS:
                removed_runtime.append(workflow_id)
                continue
            retained_workflows.append(workflow)
        store.workflows = retained_workflows
        store.workflow_runs = [
            run
            for run in getattr(store, "workflow_runs", [])
            if str(run.get("workflow_id") or "").strip() not in LEGACY_WORKFLOW_IDS
        ]

    removed_persistence = persistence_service.delete_workflow_states(
        workflow_ids=list(LEGACY_WORKFLOW_IDS)
    )
    from app.modules.agent_config.registries.mandatory_agent_registry_service import purge_removed_workflow_agent_bindings

    cleaned_bindings = purge_removed_workflow_agent_bindings(workflow_ids=LEGACY_WORKFLOW_IDS)
    if removed_runtime:
        logger.info(
            "Purged legacy mandatory workflows from runtime store: %s",
            ", ".join(removed_runtime),
        )
    if removed_persistence:
        logger.info("Purged %s legacy mandatory workflows from persistence", removed_persistence)
    if cleaned_bindings["total"]:
        logger.info(
            "Cleared %s agent workflow bindings referencing removed workflows",
            cleaned_bindings["total"],
        )


def _build_workflow_payload(spec: dict[str, Any]) -> dict[str, Any]:
    nodes = _clone(spec["nodes"])
    if str(spec.get("id") or "").strip() == FOUNDATION_BRAIN_WORKFLOW_ID:
        nodes = _apply_foundation_module_interface_bindings(nodes)
    edges = _clone(spec["edges"])
    agent_bindings: list[str] = []
    for node in nodes:
        agent_id = str(node.get("agent_id") or "").strip()
        if not agent_id or agent_id in agent_bindings:
            continue
        agent_bindings.append(agent_id)
    return {
        "id": spec["id"],
        "name": spec["name"],
        "description": spec["description"],
        "version": spec["version"],
        "status": spec["status"],
        "updated_at": store.now_string(),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
        "trigger": _clone(spec["trigger"]),
        "agent_bindings": agent_bindings,
    }


def get_hidden_legacy_workflow_compatibility_payload(
    workflow_id: str | None,
) -> dict[str, Any] | None:
    normalized_workflow_id = str(workflow_id or "").strip()
    spec = LEGACY_WORKFLOW_COMPATIBILITY_SPECS.get(normalized_workflow_id)
    if spec is None:
        return None

    payload = _clone(spec)
    assert isinstance(payload, dict)
    payload["updated_at"] = store.now_string()
    payload["node_count"] = len(payload.get("nodes") or [])
    payload["edge_count"] = len(payload.get("edges") or [])
    payload["_legacy_hidden_compatibility"] = True
    return payload


def _merge_node_config(
    config: dict[str, Any] | None,
    patch: dict[str, Any],
) -> dict[str, Any]:
    merged = _clone(config) if isinstance(config, dict) else {}
    assert isinstance(merged, dict)
    merged.update(_clone(patch))
    return merged


def _apply_foundation_module_interface_bindings(nodes: object) -> list[dict[str, Any]]:
    if not isinstance(nodes, list):
        return []

    bindings = foundation_workflow_module_bindings_by_key()
    patched_nodes = _clone(nodes)
    assert isinstance(patched_nodes, list)
    for node in patched_nodes:
        if not isinstance(node, dict):
            continue
        config = node.get("config")
        if not isinstance(config, dict):
            continue
        module_key = str(config.get("moduleKey") or config.get("module_key") or "").strip()
        if not module_key:
            continue
        binding = bindings.get(module_key)
        if not isinstance(binding, dict):
            continue
        node["config"] = _merge_node_config(config, binding)
    return patched_nodes


def ensure_mandatory_workflows_registered() -> dict[str, Any]:
    _purge_legacy_workflows()

    created: list[str] = []
    updated: list[str] = []
    items: list[dict[str, Any]] = []

    for spec in _active_mandatory_workflow_specs():
        workflow_id = str(spec["id"]).strip()
        existing = _find_runtime_workflow(workflow_id)
        payload = _build_workflow_payload(spec)
        persisted = _upsert_runtime_workflow(payload)
        if existing is None:
            created.append(workflow_id)
            logger.info("Registered mandatory workflow %s", workflow_id)
        else:
            updated.append(workflow_id)
            logger.info("Refreshed mandatory workflow %s", workflow_id)
        persistence_service.persist_workflow_state(workflow=persisted)
        items.append(_clone(persisted))

    return {
        "ok": True,
        "created": created,
        "updated": updated,
        "items": items,
        "total": len(items),
    }
