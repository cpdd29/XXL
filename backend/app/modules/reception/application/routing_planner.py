from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.modules.reception.application import routing_rules as rules
from app.modules.agent_config.registries.agent_config_service import agent_config_service
from app.modules.dispatch.workflow_runtime import execution_directory_service


INTENT_CAPABILITY_HINTS = {
    "search": {"web_search", "document_retrieval", "fact_checking", "lookup", "research"},
    "write": {"drafting", "rewriting", "summarization"},
    "help": {
        "response_formatting",
        "channel_adaptation",
        "summarization",
        "translation",
        "localization",
        "bilingual_reply",
    },
}
RESEARCH_HINTS = {
    "search",
    "find",
    "lookup",
    "research",
    "查",
    "搜索",
    "检索",
    "文档",
    "资料",
    "规范",
    "知识库",
    "based on",
    "according to",
    "根据",
    "基于",
    "引用",
}
SYNTHESIS_HINTS = {
    "write",
    "draft",
    "reply",
    "email",
    "announcement",
    "总结",
    "整理",
    "生成",
    "输出",
    "回复",
    "邮件",
    "公告",
    "说明",
    "汇总",
}
PARALLEL_HINTS = {"parallel", "同时", "并行", "simultaneously"}


def execution_agent_support(execution_agent: dict | None, intent: str) -> dict[str, Any]:
    normalized_intent = rules.normalize_intent(intent)
    if not isinstance(execution_agent, dict) or not normalized_intent:
        return {
            "supports_intent": None,
            "support_source": "missing",
            "supported_intents": [],
            "capabilities": [],
            "warnings": [],
        }

    warnings: list[str] = []
    snapshot = execution_agent.get("config_snapshot")
    if not isinstance(snapshot, dict):
        try:
            snapshot = agent_config_service.load_agent_config(execution_agent)
        except Exception as exc:  # pragma: no cover
            snapshot = None
            warnings.append(f"agent_config_load_failed:{exc}")

    agent_doc = snapshot.get("agent") if isinstance(snapshot, dict) and isinstance(snapshot.get("agent"), dict) else {}
    supported_intents = rules.string_list(agent_doc.get("trigger_intents"))
    capabilities = rules.string_list(agent_doc.get("capabilities"))
    agent_type = str(execution_agent.get("type") or "").strip().lower()
    expected_agent_type = str(
        execution_directory_service.INTENT_AGENT_TYPE_MAP.get(normalized_intent) or ""
    ).strip().lower()

    if normalized_intent in supported_intents:
        return {
            "supports_intent": True,
            "support_source": "trigger_intents",
            "supported_intents": supported_intents,
            "capabilities": capabilities,
            "warnings": warnings,
        }
    if set(capabilities) & INTENT_CAPABILITY_HINTS.get(normalized_intent, set()):
        return {
            "supports_intent": True,
            "support_source": "capabilities",
            "supported_intents": supported_intents,
            "capabilities": capabilities,
            "warnings": warnings,
        }
    if expected_agent_type and agent_type == expected_agent_type:
        return {
            "supports_intent": True,
            "support_source": "agent_type",
            "supported_intents": supported_intents,
            "capabilities": capabilities,
            "warnings": warnings,
        }
    if supported_intents or capabilities:
        return {
            "supports_intent": False,
            "support_source": "config_mismatch",
            "supported_intents": supported_intents,
            "capabilities": capabilities,
            "warnings": warnings,
        }
    return {
        "supports_intent": None,
        "support_source": "unknown",
        "supported_intents": supported_intents,
        "capabilities": capabilities,
        "warnings": warnings,
    }


def resolve_chat_execution_agent(intent: str) -> tuple[str, dict[str, Any], dict[str, Any]]:
    preferred_intents = ("help", intent, "write", "search")
    seen: set[str] = set()

    for candidate_intent in preferred_intents:
        normalized_intent = rules.normalize_intent(candidate_intent)
        if not normalized_intent or normalized_intent in seen:
            continue
        seen.add(normalized_intent)
        execution_agent = execution_directory_service.resolve_agent_dispatch_execution_agent(normalized_intent)
        support = execution_agent_support(execution_agent, normalized_intent)
        if execution_agent is not None and support.get("supports_intent") is not False:
            return normalized_intent, execution_agent, support

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="No enabled direct execution agent available for chat interaction",
    )


def resolve_planned_agent(intent: str) -> dict[str, Any] | None:
    execution_agent = execution_directory_service.resolve_agent_dispatch_execution_agent(intent)
    if not isinstance(execution_agent, dict):
        return None
    support = execution_agent_support(execution_agent, intent)
    if support.get("supports_intent") is False:
        return None
    return {
        "intent": intent,
        "execution_agent_id": str(execution_agent.get("id") or "").strip() or None,
        "execution_agent": str(execution_agent.get("name") or "").strip() or rules.target_agent_name(intent),
        "agent_type": str(execution_agent.get("type") or "").strip().lower() or None,
        "support": support,
    }


def build_dynamic_execution_plan(text: str, intent: str) -> dict[str, Any] | None:
    normalized_intent = rules.normalize_intent(intent)
    normalized_text = rules.normalize_text(text)
    if normalized_intent not in {"search", "write", "help"} or not normalized_text:
        return None

    wants_research = rules.contains_any(normalized_text, RESEARCH_HINTS)
    wants_synthesis = normalized_intent in {"write", "help"} or rules.contains_any(normalized_text, SYNTHESIS_HINTS)
    if not wants_research or not wants_synthesis:
        return None

    coordination_mode = "parallel" if rules.contains_any(normalized_text, PARALLEL_HINTS) else "serial"
    search_agent = resolve_planned_agent("search")
    synthesis_agent = resolve_planned_agent(normalized_intent)
    if search_agent is None or synthesis_agent is None:
        return None

    plan_steps = [
        {
            "id": "research",
            "branch_id": "branch-research",
            "intent": "search",
            "role": "grounding",
            "completion_policy": "required",
            "execution_agent_id": search_agent["execution_agent_id"],
            "execution_agent": search_agent["execution_agent"],
            "agent_type": search_agent["agent_type"],
        },
        {
            "id": "synthesis",
            "branch_id": "branch-synthesis",
            "intent": normalized_intent,
            "role": "final_response",
            "completion_policy": "required",
            "depends_on": [] if coordination_mode == "parallel" else ["research"],
            "execution_agent_id": synthesis_agent["execution_agent_id"],
            "execution_agent": synthesis_agent["execution_agent"],
            "agent_type": synthesis_agent["agent_type"],
        },
    ]
    support_summary = [search_agent["support"], synthesis_agent["support"]]
    plan_summary = (
        f"{search_agent['execution_agent']} -> {synthesis_agent['execution_agent']}"
        if coordination_mode == "serial"
        else f"{search_agent['execution_agent']} + {synthesis_agent['execution_agent']}"
    )
    return {
        "plan_type": "multi_agent",
        "coordination_mode": coordination_mode,
        "planner": "master_bot",
        "aggregator": "master_bot",
        "fan_out": {
            "mode": coordination_mode,
            "branch_count": len(plan_steps),
            "branches": [
                {
                    "id": step["branch_id"],
                    "step_id": step["id"],
                    "intent": step["intent"],
                    "role": step["role"],
                    "execution_agent": step["execution_agent"],
                    "execution_agent_id": step["execution_agent_id"],
                    "completion_policy": step["completion_policy"],
                }
                for step in plan_steps
            ],
        },
        "fan_in": {
            "strategy": "ordered_synthesis" if coordination_mode == "serial" else "merge_summary",
            "aggregator": "master_bot",
            "output_contract": "structured_result",
        },
        "merge_strategy": "append_bullets_and_references",
        "winner_strategy": "first_acceptable",
        "quorum": {
            "min_success_count": 1 if coordination_mode == "parallel" else len(plan_steps),
            "count_failed_as_terminal": coordination_mode == "serial",
        },
        "cancel_policy": {
            "cancel_remaining_on_winner": coordination_mode == "race",
            "cancel_remaining_on_quorum": False,
        },
        "summary": plan_summary,
        "steps": plan_steps,
        "planned_agent_count": len(plan_steps),
        "support_summary": support_summary,
    }
