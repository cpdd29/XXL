from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.services import workflow_execution_service
from app.services.agent_config_service import agent_config_service
from app.services.workflow_execution_service import (
    INTENT_AGENT_TYPE_MAP,
    select_workflow_candidates_for_message,
)


INTENT_SIGNAL_RULES: dict[str, tuple[tuple[str, int], ...]] = {
    "search": (
        ("search", 4),
        ("find", 4),
        ("lookup", 4),
        ("research", 4),
        ("查", 4),
        ("搜索", 4),
        ("检索", 4),
        ("文档", 2),
        ("资料", 2),
        ("规范", 2),
        ("知识库", 2),
    ),
    "write": (
        ("write", 4),
        ("draft", 4),
        ("reply", 4),
        ("email", 4),
        ("announcement", 4),
        ("写", 4),
        ("生成", 3),
        ("草稿", 3),
        ("回复", 3),
        ("邮件", 3),
        ("公告", 3),
        ("总结", 2),
    ),
    "help": (
        ("help", 3),
        ("how", 3),
        ("what", 2),
        ("why", 2),
        ("explain", 3),
        ("guide", 2),
        ("帮助", 3),
        ("如何", 3),
        ("怎么", 3),
        ("为什么", 2),
        ("说明", 2),
        ("解释", 2),
    ),
}
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
CHAT_GREETING_HINTS = {
    "hi",
    "hello",
    "hey",
    "你好",
    "您好",
    "嗨",
    "哈喽",
    "在吗",
}
CHAT_SMALL_TALK_HINTS = {
    "你是谁",
    "你是干嘛的",
    "你能做什么",
    "你可以做什么",
    "介绍一下你自己",
    "how are you",
    "what can you do",
    "who are you",
}
CHAT_CLARIFICATION_HINTS = {
    "什么意思",
    "啥意思",
    "再说一遍",
    "说清楚点",
    "解释一下",
    "详细一点",
    "具体一点",
    "why",
    "what do you mean",
    "clarify",
}
CHAT_FOLLOW_UP_HINTS = {
    "继续",
    "接着",
    "顺着这个",
    "补充一下",
    "follow up",
    "continue",
}
DIRECT_QUESTION_HINTS = {
    "怎么",
    "怎么样",
    "如何",
    "为啥",
    "为什么",
    "多少",
    "几号",
    "几点",
    "哪里",
    "哪儿",
    "有没有",
    "是否",
    "行不行",
    "可不可以",
    "吗",
    "呢",
    "what",
    "why",
    "how",
    "when",
    "where",
    "which",
    "is it",
    "can it",
}
RECEPTION_CLARIFY_HINTS = {
    "想聊",
    "想聊聊",
    "想请教",
    "想问问",
    "想咨询",
    "想了解",
    "想看看",
    "能不能",
    "可以吗",
    "方便吗",
    "帮我看看",
    "聊一下",
    "说一下",
    "talk",
    "chat",
    "can you",
    "could you",
}
WORKFLOW_OR_DIRECT_HINTS = {
    "工作流",
    "workflow",
    "agent",
    "执行",
    "调度",
    "路由",
    "dispatch",
}
PROJECT_DOMAIN_HINTS = {
    "workbot",
    "workflow",
    "agent",
    "钉钉",
    "dingtalk",
    "机器人",
    "接入",
    "配置",
    "日志",
    "文档",
    "资料",
    "知识库",
    "项目",
    "代码",
    "仓库",
    "接口",
    "api",
    "redis",
    "nats",
    "chroma",
    "webhook",
    "模板",
    "模版",
    "路由",
    "调度",
    "执行",
    "排查",
    "修复",
    "问题定位",
    "任务",
    "工作流",
}
LIVE_INFORMATION_HINTS = {
    "天气",
    "气温",
    "温度",
    "下雨",
    "预报",
    "台风",
    "新闻",
    "股价",
    "股票",
    "汇率",
    "路况",
    "航班",
    "hot search",
    "weather",
    "forecast",
    "temperature",
    "news",
    "stock",
    "exchange rate",
    "traffic",
    "flight",
}
HARD_TASK_REQUEST_HINTS = {
    "写一个",
    "写一段",
    "写一版",
    "写一封",
    "写一份",
    "写个",
    "生成",
    "整理",
    "总结",
    "翻译",
    "排查",
    "修复",
    "debug",
    "fix",
    "write",
    "draft",
    "generate",
    "summarize",
    "translate",
}
SEARCH_TASK_HINTS = {
    "search",
    "find",
    "lookup",
    "research",
    "查",
    "查一下",
    "查看",
    "搜",
    "搜索",
    "检索",
    "找一下",
}
SOFT_TASK_REQUEST_HINTS = {
    "请帮我",
    "帮我",
    "请你",
    "请",
    "帮忙",
    "please",
    "help me",
}


def _normalize_intent(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"search", "write", "help"}:
        return normalized
    return None


def _string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [item for item in (str(value or "").strip().lower() for value in values) if item]


def _contains_any(text: str, keywords: set[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _normalize_text(text: str) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _is_direct_question(text: str) -> bool:
    normalized_text = _normalize_text(text)
    if not normalized_text:
        return False
    return (
        "?" in normalized_text
        or "？" in normalized_text
        or _contains_any(normalized_text, DIRECT_QUESTION_HINTS)
    )


def _classify_interaction_mode(text: str, *, intent: str) -> str:
    normalized_text = _normalize_text(text)
    if not normalized_text:
        return "chat"

    is_project_domain = _contains_any(normalized_text, PROJECT_DOMAIN_HINTS)
    is_live_information_request = _contains_any(normalized_text, LIVE_INFORMATION_HINTS)
    is_direct_question = _is_direct_question(normalized_text)

    if len(normalized_text) <= 40 and (
        _contains_any(normalized_text, CHAT_GREETING_HINTS)
        or _contains_any(normalized_text, CHAT_SMALL_TALK_HINTS)
    ):
        return "chat"

    if len(normalized_text) <= 80 and _contains_any(normalized_text, CHAT_FOLLOW_UP_HINTS):
        return "chat"

    if _contains_any(normalized_text, CHAT_CLARIFICATION_HINTS):
        return "chat"

    if _contains_any(normalized_text, HARD_TASK_REQUEST_HINTS):
        return "task"

    if is_direct_question and not is_project_domain:
        return "chat"

    if _contains_any(normalized_text, SEARCH_TASK_HINTS):
        if is_live_information_request and not is_project_domain:
            return "chat"
        if is_direct_question and not is_project_domain:
            return "chat"
        return "task"

    if intent == "write" and not is_direct_question:
        return "task"

    if len(normalized_text) <= 48 and _contains_any(normalized_text, SOFT_TASK_REQUEST_HINTS):
        return "chat"

    if _contains_any(normalized_text, WORKFLOW_OR_DIRECT_HINTS):
        return "workflow_or_direct"

    if intent in {"search", "write"} and len(normalized_text) >= 36:
        return "task"

    if intent == "help" and len(normalized_text) <= 36:
        return "chat"

    return "workflow_or_direct"


def _classify_reception_mode(text: str, *, intent: str, interaction_mode: str) -> str:
    normalized_text = _normalize_text(text)
    if not normalized_text:
        return "welcome"

    is_live_information_request = _contains_any(normalized_text, LIVE_INFORMATION_HINTS)
    is_project_domain = _contains_any(normalized_text, PROJECT_DOMAIN_HINTS)

    if interaction_mode != "chat":
        return "task_handoff"

    if _contains_any(normalized_text, CHAT_GREETING_HINTS):
        return "welcome"

    if _contains_any(normalized_text, CHAT_FOLLOW_UP_HINTS):
        return "continuation"

    if _contains_any(normalized_text, CHAT_SMALL_TALK_HINTS):
        return "small_talk"

    if _is_direct_question(normalized_text):
        return "direct_question"

    if is_live_information_request and not is_project_domain:
        return "direct_question"

    if len(normalized_text) <= 48 and _contains_any(normalized_text, RECEPTION_CLARIFY_HINTS):
        return "clarify"

    if intent in {"search", "write"}:
        return "task_handoff"

    if len(normalized_text) <= 24:
        return "clarify"

    return "continuation"


def _resolve_chat_execution_agent(intent: str) -> tuple[str, dict[str, Any], dict[str, Any]]:
    preferred_intents = ("help", intent, "write", "search")
    seen: set[str] = set()

    for candidate_intent in preferred_intents:
        normalized_intent = _normalize_intent(candidate_intent)
        if not normalized_intent or normalized_intent in seen:
            continue
        seen.add(normalized_intent)
        execution_agent = workflow_execution_service.resolve_direct_execution_agent(normalized_intent)
        support = _execution_agent_support(execution_agent, normalized_intent)
        if execution_agent is not None and support.get("supports_intent") is not False:
            return normalized_intent, execution_agent, support

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="No enabled direct execution agent available for chat interaction",
    )


def _resolve_planned_agent(intent: str) -> dict[str, Any] | None:
    execution_agent = workflow_execution_service.resolve_direct_execution_agent(intent)
    if not isinstance(execution_agent, dict):
        return None
    support = _execution_agent_support(execution_agent, intent)
    if support.get("supports_intent") is False:
        return None
    return {
        "intent": intent,
        "execution_agent_id": str(execution_agent.get("id") or "").strip() or None,
        "execution_agent": str(execution_agent.get("name") or "").strip() or target_agent_name(intent),
        "agent_type": str(execution_agent.get("type") or "").strip().lower() or None,
        "support": support,
    }


def _build_dynamic_execution_plan(text: str, intent: str) -> dict[str, Any] | None:
    normalized_intent = _normalize_intent(intent)
    normalized_text = " ".join(str(text or "").strip().lower().split())
    if normalized_intent not in {"search", "write", "help"} or not normalized_text:
        return None

    wants_research = _contains_any(normalized_text, RESEARCH_HINTS)
    wants_synthesis = normalized_intent in {"write", "help"} or _contains_any(normalized_text, SYNTHESIS_HINTS)
    if not wants_research or not wants_synthesis:
        return None

    coordination_mode = "parallel" if _contains_any(normalized_text, PARALLEL_HINTS) else "serial"
    plan_steps: list[dict[str, Any]] = []
    search_agent = _resolve_planned_agent("search")
    synthesis_agent = _resolve_planned_agent(normalized_intent)
    if search_agent is None or synthesis_agent is None:
        return None

    plan_steps.append(
        {
            "id": "research",
            "intent": "search",
            "role": "grounding",
            "execution_agent_id": search_agent["execution_agent_id"],
            "execution_agent": search_agent["execution_agent"],
            "agent_type": search_agent["agent_type"],
        }
    )
    plan_steps.append(
        {
            "id": "synthesis",
            "intent": normalized_intent,
            "role": "final_response",
            "execution_agent_id": synthesis_agent["execution_agent_id"],
            "execution_agent": synthesis_agent["execution_agent"],
            "agent_type": synthesis_agent["agent_type"],
        }
    )
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
        "summary": plan_summary,
        "steps": plan_steps,
        "planned_agent_count": len(plan_steps),
        "support_summary": support_summary,
    }


def classify_intent(text: str) -> dict[str, Any]:
    normalized_text = " ".join(str(text or "").strip().lower().split())
    scores = {"search": 0, "write": 0, "help": 0}
    reasons: dict[str, list[str]] = {intent: [] for intent in scores}

    for intent, rules in INTENT_SIGNAL_RULES.items():
        for keyword, weight in rules:
            if keyword in normalized_text:
                scores[intent] += weight
                reasons[intent].append(keyword)

    if not any(scores.values()):
        scores["help"] = 1
        reasons["help"].append("default_help_fallback")

    ordered = sorted(scores.items(), key=lambda item: (item[1], item[0] == "help"), reverse=True)
    best_intent, best_score = ordered[0]
    total_score = sum(max(score, 0) for score in scores.values())
    confidence = round(best_score / max(total_score, 1), 3)

    return {
        "intent": best_intent,
        "scores": scores,
        "reasons": reasons,
        "confidence": confidence,
    }


def dispatch_intent(text: str) -> str:
    return str(classify_intent(text)["intent"])


def target_agent_name(intent: str) -> str:
    return {
        "search": "搜索 Agent",
        "write": "写作 Agent",
        "help": "写作 Agent",
    }[intent]


def _execution_agent_support(execution_agent: dict | None, intent: str) -> dict[str, Any]:
    normalized_intent = _normalize_intent(intent)
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
        except Exception as exc:  # pragma: no cover - defensive fail-open path
            snapshot = None
            warnings.append(f"agent_config_load_failed:{exc}")

    agent_doc = snapshot.get("agent") if isinstance(snapshot, dict) and isinstance(snapshot.get("agent"), dict) else {}
    supported_intents = _string_list(agent_doc.get("trigger_intents"))
    capabilities = _string_list(agent_doc.get("capabilities"))
    agent_type = str(execution_agent.get("type") or "").strip().lower()
    expected_agent_type = str(INTENT_AGENT_TYPE_MAP.get(normalized_intent) or "").strip().lower()

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


class MasterBotService:
    def route_message(
        self,
        *,
        text: str,
        channel: str | None = None,
        detected_lang: str | None = None,
    ) -> dict:
        intent_assessment = classify_intent(text)
        intent = str(intent_assessment["intent"])
        interaction_mode = _classify_interaction_mode(text, intent=intent)
        reception_mode = _classify_reception_mode(
            text,
            intent=intent,
            interaction_mode=interaction_mode,
        )
        if interaction_mode == "chat":
            chat_agent_intent, execution_agent, execution_support = _resolve_chat_execution_agent(intent)
            execution_agent_name = (
                str(execution_agent.get("name") or "").strip()
                or target_agent_name(chat_agent_intent)
            )
            route_message = f"已识别为接待式对话；直接交由对话 Agent 回复: {execution_agent_name}"
            return {
                "intent": intent,
                "workflow": None,
                "route_message": route_message,
                "route_decision": {
                    "intent": intent,
                    "workflow_id": workflow_execution_service.DIRECT_AGENT_FALLBACK_WORKFLOW_ID,
                    "workflow_name": workflow_execution_service.DIRECT_AGENT_FALLBACK_WORKFLOW_NAME,
                    "execution_agent_id": str(execution_agent.get("id") or "").strip() or None,
                    "execution_agent": execution_agent_name,
                    "selected_by_message_trigger": False,
                    "route_message": route_message,
                    "intent_confidence": intent_assessment["confidence"],
                    "intent_scores": intent_assessment["scores"],
                    "intent_reasons": intent_assessment["reasons"],
                    "candidate_workflows": [],
                    "skipped_workflows": [],
                    "routing_strategy": "chat_direct_agent",
                    "interaction_mode": interaction_mode,
                    "interactionMode": interaction_mode,
                    "reception_mode": reception_mode,
                    "receptionMode": reception_mode,
                    "execution_support": {
                        **execution_support,
                        "chat_agent_intent": chat_agent_intent,
                    },
                },
            }
        dynamic_execution_plan = _build_dynamic_execution_plan(text, intent)
        if dynamic_execution_plan is not None:
            execution_steps = dynamic_execution_plan["steps"]
            execution_agent_name = " + ".join(
                str(step.get("execution_agent") or "").strip()
                for step in execution_steps
                if str(step.get("execution_agent") or "").strip()
            )
            route_message = (
                f"已识别意图: {intent}；检测到复合任务；"
                f"已启用 Master Bot 动态编排 ({dynamic_execution_plan['coordination_mode']})："
                f"{dynamic_execution_plan['summary']}"
            )
            return {
                "intent": intent,
                "workflow": None,
                "route_message": route_message,
                "route_decision": {
                    "intent": intent,
                    "workflow_id": workflow_execution_service.DIRECT_AGENT_FALLBACK_WORKFLOW_ID,
                    "workflow_name": workflow_execution_service.DIRECT_AGENT_FALLBACK_WORKFLOW_NAME,
                    "execution_agent_id": execution_steps[0].get("execution_agent_id"),
                    "execution_agent": execution_agent_name or "Master Bot Planner",
                    "execution_plan": dynamic_execution_plan,
                    "selected_by_message_trigger": False,
                    "route_message": route_message,
                    "intent_confidence": intent_assessment["confidence"],
                    "intent_scores": intent_assessment["scores"],
                    "intent_reasons": intent_assessment["reasons"],
                    "candidate_workflows": [],
                    "skipped_workflows": [],
                    "routing_strategy": "dynamic_multi_agent_dispatch",
                    "interaction_mode": interaction_mode,
                    "interactionMode": interaction_mode,
                    "reception_mode": reception_mode,
                    "receptionMode": reception_mode,
                    "execution_support": {
                        "mode": "multi_agent",
                        "coordination_mode": dynamic_execution_plan["coordination_mode"],
                        "planned_agent_count": dynamic_execution_plan["planned_agent_count"],
                        "agents": [
                            {
                                "intent": step["intent"],
                                "execution_agent_id": step.get("execution_agent_id"),
                                "execution_agent": step.get("execution_agent"),
                                "agent_type": step.get("agent_type"),
                            }
                            for step in execution_steps
                        ],
                    },
                },
            }
        workflow_candidates: list[tuple[dict, str]] = []
        no_workflow_available = False
        try:
            workflow_candidates = select_workflow_candidates_for_message(
                intent,
                text,
                channel=channel,
                detected_lang=detected_lang,
            )
        except HTTPException as exc:
            if exc.status_code != status.HTTP_404_NOT_FOUND or exc.detail != "Workflow not found":
                raise
            no_workflow_available = True

        skipped_workflows: list[dict[str, str]] = []
        candidate_workflows: list[dict[str, Any]] = []
        execution_agent = None
        execution_support: dict[str, Any] | None = None
        selected_route_message = ""
        selected_workflow = None

        for candidate_workflow, base_route_message in workflow_candidates:
            candidate_execution_agent = workflow_execution_service.resolve_workflow_execution_agent(
                candidate_workflow,
                intent,
            )
            candidate_agent_name = (
                str((candidate_execution_agent or {}).get("name") or "").strip()
                or target_agent_name(intent)
            )
            support = _execution_agent_support(candidate_execution_agent, intent)
            candidate_workflows.append(
                {
                    "workflow_id": str(candidate_workflow.get("id") or ""),
                    "workflow_name": str(candidate_workflow.get("name") or ""),
                    "route_message": base_route_message,
                    "execution_agent": candidate_agent_name,
                    "supports_intent": support.get("supports_intent"),
                    "support_source": str(support.get("support_source") or "unknown"),
                }
            )
            if candidate_execution_agent is None:
                skipped_workflows.append(
                    {
                        "workflow_id": str(candidate_workflow.get("id") or ""),
                        "workflow_name": str(candidate_workflow.get("name") or ""),
                        "reason": "missing_execution_agent",
                    }
                )
                continue
            if support.get("supports_intent") is False:
                skipped_workflows.append(
                    {
                        "workflow_id": str(candidate_workflow.get("id") or ""),
                        "workflow_name": str(candidate_workflow.get("name") or ""),
                        "reason": "execution_agent_config_mismatch",
                    }
                )
                continue
            execution_agent = candidate_execution_agent
            execution_support = support
            selected_workflow = candidate_workflow
            selected_route_message = base_route_message
            break

        if execution_agent is None or selected_workflow is None:
            execution_agent = workflow_execution_service.resolve_direct_execution_agent(intent)
            execution_support = _execution_agent_support(execution_agent, intent)
            if execution_agent is None:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="No enabled direct execution agent available for intent",
                )

            execution_agent_name = str(execution_agent.get("name") or "").strip() or target_agent_name(intent)
            fallback_reason = "未找到可用工作流" if no_workflow_available else "工作流不可执行"
            route_message = f"已识别意图: {intent}；{fallback_reason}；已切换为直达 Agent 执行: {execution_agent_name}"
            if skipped_workflows:
                route_message = (
                    f"{route_message}；已跳过不可执行工作流: "
                    f"{', '.join(item['workflow_name'] for item in skipped_workflows if item.get('workflow_name'))}"
                )
            return {
                "intent": intent,
                "workflow": None,
                "route_message": route_message,
                "route_decision": {
                    "intent": intent,
                    "workflow_id": workflow_execution_service.DIRECT_AGENT_FALLBACK_WORKFLOW_ID,
                    "workflow_name": workflow_execution_service.DIRECT_AGENT_FALLBACK_WORKFLOW_NAME,
                    "execution_agent_id": str(execution_agent.get("id") or "").strip() or None,
                    "execution_agent": execution_agent_name,
                    "selected_by_message_trigger": False,
                    "route_message": route_message,
                    "intent_confidence": intent_assessment["confidence"],
                    "intent_scores": intent_assessment["scores"],
                    "intent_reasons": intent_assessment["reasons"],
                    "candidate_workflows": candidate_workflows[:5],
                    "skipped_workflows": skipped_workflows,
                    "routing_strategy": "workflow_or_direct_agent_fallback",
                    "interaction_mode": interaction_mode,
                    "interactionMode": interaction_mode,
                    "reception_mode": reception_mode,
                    "receptionMode": reception_mode,
                    "execution_support": execution_support,
                },
            }

        execution_agent_name = str(execution_agent.get("name") or "").strip() or target_agent_name(intent)
        route_message = f"{selected_route_message}；执行代理: {execution_agent_name}"
        if skipped_workflows:
            route_message = (
                f"{route_message}；已跳过不可执行工作流: "
                f"{', '.join(item['workflow_name'] for item in skipped_workflows if item.get('workflow_name'))}"
            )

        return {
            "intent": intent,
            "workflow": selected_workflow,
            "route_message": route_message,
            "route_decision": {
                "intent": intent,
                "workflow_id": str(selected_workflow["id"]),
                "workflow_name": str(selected_workflow["name"]),
                "execution_agent_id": str(execution_agent.get("id") or "").strip() or None,
                "execution_agent": execution_agent_name,
                "selected_by_message_trigger": "路由依据: intent fallback" not in selected_route_message,
                "route_message": route_message,
                "intent_confidence": intent_assessment["confidence"],
                "intent_scores": intent_assessment["scores"],
                "intent_reasons": intent_assessment["reasons"],
                "candidate_workflows": candidate_workflows[:5],
                "skipped_workflows": skipped_workflows,
                "routing_strategy": "workflow_trigger+execution_agent_support",
                "interaction_mode": interaction_mode,
                "interactionMode": interaction_mode,
                "reception_mode": reception_mode,
                "receptionMode": reception_mode,
                "execution_support": execution_support,
            },
        }


master_bot_service = MasterBotService()
