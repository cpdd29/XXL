from __future__ import annotations

from copy import deepcopy
import logging
from typing import Any

from app.services.persistence_service import persistence_service
from app.services.store import store


logger = logging.getLogger(__name__)

MAIN_BRAIN_WORKFLOW_ID = "workflow-1"
EXTERNAL_TENTACLE_WORKFLOW_ID = "mandatory-workflow-external-tentacle-dispatch"

MANDATORY_WORKFLOW_SPECS: tuple[dict[str, Any], ...] = (
    {
        "id": MAIN_BRAIN_WORKFLOW_ID,
        "name": "主脑整体工作流",
        "description": "统一承接渠道消息，串联安全审查、对话澄清、需求分发与外接触手执行。",
        "version": "v3.0",
        "status": "active",
        "trigger": {
            "type": "message",
            "keyword": None,
            "cron": None,
            "webhook_path": None,
            "internal_event": None,
            "description": "默认渠道入口，所有渠道消息统一先进入主脑整体工作流。",
            "priority": 520,
            "channels": ["telegram", "dingtalk", "wecom", "feishu"],
            "preferred_language": None,
            "step_delay_seconds": 0.6,
            "max_dispatch_retry": 6,
            "dispatch_retry_backoff_seconds": 2.0,
            "execution_timeout_seconds": 45.0,
            "natural_language_rule": "所有渠道消息默认先经过安全、对话与需求分发，再进入外接触手执行层。",
            "schedule_plan": None,
        },
        "nodes": [
            {
                "id": "1",
                "type": "trigger",
                "label": "渠道触发",
                "x": 60,
                "y": 180,
                "description": "统一接收 Telegram、DingTalk、WeCom、Feishu 等渠道消息。",
                "config": {
                    "summary": "channel message ingress",
                },
            },
            {
                "id": "2",
                "type": "agent",
                "label": "安全 Agent",
                "x": 280,
                "y": 180,
                "description": "完成入站安全审查、越权检测与风险说明。",
                "agent_id": "security",
                "config": {
                    "instruction": "先完成安全审查，再决定是否允许进入后续编排。",
                    "result_kind": "risk_assessment",
                },
            },
            {
                "id": "3",
                "type": "agent",
                "label": "对话 Agent",
                "x": 520,
                "y": 180,
                "description": "负责澄清需求并整理结构化 handoff summary。",
                "agent_id": "conversation",
                "config": {
                    "instruction": "先接住用户需求，必要时做最小澄清，再生成可分发摘要。",
                    "result_kind": "conversation_handoff",
                },
            },
            {
                "id": "4",
                "type": "agent",
                "label": "需求分析任务分发 Agent",
                "x": 780,
                "y": 180,
                "description": "负责整理执行意图并将任务分发到外接触手执行层。",
                "agent_id": "requirement_dispatcher",
                "config": {
                    "instruction": "根据澄清摘要生成执行方向和 handoff packet。",
                    "result_kind": "execution_route_plan",
                },
            },
            {
                "id": "5",
                "type": "workflow",
                "label": "外接触手执行层",
                "x": 1060,
                "y": 180,
                "description": "进入外接触手执行子工作流，按意图选择外接检索或写作能力。",
                "workflow_id": EXTERNAL_TENTACLE_WORKFLOW_ID,
                "config": {
                    "handoffNote": "已完成安全、对话和需求分发，请外接触手执行层按当前意图继续处理并回传结果。",
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
            "description": "由主脑整体工作流或运维手动触发。",
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
                "description": "接收来自主脑整体工作流的 handoff 请求。",
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
        "description": "负责接待用户、澄清需求并整理结构化交接摘要。",
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
                "label": "对话 Agent",
                "x": 280,
                "y": 120,
                "description": "执行接待、澄清与结构化 handoff。",
                "agent_id": "conversation",
                "config": {
                    "instruction": "先澄清需求，再输出 handoff summary。",
                    "result_kind": "structured_request_packet",
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


def _build_workflow_payload(spec: dict[str, Any]) -> dict[str, Any]:
    nodes = _clone(spec["nodes"])
    edges = _clone(spec["edges"])
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
        "agent_bindings": [
            str(node.get("agent_id") or "").strip()
            for node in nodes
            if str(node.get("agent_id") or "").strip()
        ],
    }


def ensure_mandatory_workflows_registered() -> dict[str, Any]:
    created: list[str] = []
    updated: list[str] = []
    items: list[dict[str, Any]] = []

    for spec in MANDATORY_WORKFLOW_SPECS:
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
