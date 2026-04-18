from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import logging
import re
from typing import Any

import httpx

from app.core.brain_payload_fields import (
    alias_text,
    dispatch_context_from_run,
    execution_plan_from_payload,
    route_decision_from_payload,
    route_decision_from_task,
)
from app.services.agent_config_service import agent_config_service, build_agent_config_summary
from app.services.document_search_service import document_search_service
from app.services.language_service import detect_language
from app.services.professional_workflow_service import professional_workflow_service
from app.services.settings_service import get_agent_api_runtime_settings
from app.services.store import store


logger = logging.getLogger(__name__)
INTENT_CAPABILITY_HINTS = {
    "search": {"web_search", "document_retrieval", "fact_checking", "lookup", "research"},
    "write": {"drafting", "rewriting", "summarization"},
    "help": {
        "response_formatting",
        "channel_adaptation",
        "summarization",
        "drafting",
        "translation",
        "localization",
        "bilingual_reply",
    },
}
AGENT_TYPE_INTENT_COMPAT = {
    "search": {"search"},
    "write": {"write", "help"},
    "output": {"help"},
}
GREETING_EXACT_MATCHES = {
    "hi",
    "hello",
    "hey",
    "你好",
    "您好",
    "嗨",
    "哈喽",
    "在吗",
}
PROVIDER_SELECTION_ORDER = (
    "openapi",
    "openai",
    "codex",
    "kimi",
    "deepseek",
    "gemini",
    "claude",
    "minimax",
)
RESULT_KIND_BY_MODE = {
    "chat": "chat_reply",
    "search": "search_report",
    "write": "draft_message",
    "help": "help_note",
}
CHAT_CAPABILITY_HINTS = (
    "你能做什么",
    "你会什么",
    "你是谁",
    "你是干嘛的",
    "can you do",
    "what can you do",
    "who are you",
    "what are you",
)
SMALL_TALK_HINTS = (
    "聊天",
    "聊聊",
    "简单聊",
    "闲聊",
    "陪我说",
    "说说话",
    "和我聊",
    "talk to me",
    "chat with me",
    "small talk",
)
TASK_DIRECTIVE_HINTS = (
    "写",
    "生成",
    "总结",
    "整理",
    "检索",
    "搜索",
    "查",
    "create",
    "write",
    "draft",
    "summarize",
    "search",
    "find",
    "lookup",
)
PROJECT_DOMAIN_HINTS = (
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
    "任务",
)
LIVE_INFORMATION_HINTS = (
    "天气",
    "气温",
    "温度",
    "下雨",
    "预报",
    "新闻",
    "股价",
    "股票",
    "汇率",
    "路况",
    "航班",
    "weather",
    "forecast",
    "temperature",
    "news",
    "stock",
    "exchange rate",
    "traffic",
    "flight",
)
CANONICAL_ROUTING_STRATEGY_WORKFLOW_OR_AGENT_DISPATCH_FALLBACK = (
    "workflow_or_agent_dispatch_fallback"
)
LEGACY_ROUTING_STRATEGY_WORKFLOW_OR_AGENT_FALLBACK = "_".join(
    ("workflow", "or", "direct", "agent", "fallback")
)
LEGACY_ROUTING_STRATEGY_ALIASES = {
    LEGACY_ROUTING_STRATEGY_WORKFLOW_OR_AGENT_FALLBACK: CANONICAL_ROUTING_STRATEGY_WORKFLOW_OR_AGENT_DISPATCH_FALLBACK,
}


def _normalize_language(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"zh", "en"}:
        return normalized
    return None


def _normalize_intent(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"search", "write", "help", "manual"}:
        return normalized
    return None


def _string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [item for item in (str(value or "").strip() for value in values) if item]


def _task_description_lines(task: dict) -> list[str]:
    return [
        line.strip()
        for line in str(task.get("description") or "").splitlines()
        if line.strip()
    ]


def _task_with_added_context(task: dict, *lines: str) -> dict:
    cloned_task = dict(task)
    existing_description = str(task.get("description") or "").rstrip()
    additions = [line.strip() for line in lines if str(line or "").strip()]
    if additions:
        cloned_task["description"] = "\n".join(
            item for item in [existing_description, *additions] if item
        )
    return cloned_task


def _selected_workflow_node_config(run: dict) -> dict[str, Any]:
    dispatch_context = dispatch_context_from_run(run)
    if not isinstance(dispatch_context, dict):
        return {}
    config = dispatch_context.get("selected_node_config") or dispatch_context.get("selectedNodeConfig")
    return store.clone(config) if isinstance(config, dict) else {}


def _selected_workflow_node_guidance(run: dict) -> list[str]:
    dispatch_context = dispatch_context_from_run(run)
    if not isinstance(dispatch_context, dict):
        return []

    label = str(
        dispatch_context.get("selected_node_label") or dispatch_context.get("selectedNodeLabel") or "当前工作流节点"
    ).strip()
    description = str(
        dispatch_context.get("selected_node_description") or dispatch_context.get("selectedNodeDescription") or ""
    ).strip()
    config = _selected_workflow_node_config(run)
    instruction = str(config.get("instruction") or "").strip()
    input_schema = str(config.get("inputSchema") or config.get("input_schema") or "").strip()

    lines: list[str] = []
    if description:
        lines.append(f"{label} 节点说明：{description}")
    if instruction:
        lines.append(f"{label} 执行要求：{instruction}")
    if input_schema:
        lines.append(f"{label} 输入约束：{input_schema}")
    return lines


def _combined_references(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for result in results:
        for reference in result.get("references") or []:
            if not isinstance(reference, dict):
                continue
            title = str(reference.get("title") or "").strip()
            detail = str(reference.get("detail") or "").strip()
            if not title:
                continue
            signature = (title, detail)
            if signature in seen:
                continue
            seen.add(signature)
            merged.append({"title": title, "detail": detail or None})
    return merged


def _planned_execution(run: dict) -> dict[str, Any] | None:
    dispatch_context = dispatch_context_from_run(run)
    if dispatch_context is None:
        return None
    candidate = execution_plan_from_payload(dispatch_context)
    if isinstance(candidate, dict):
        steps = candidate.get("steps")
        if isinstance(steps, list) and len(steps) > 1:
            return candidate
    route_decision = route_decision_from_payload(dispatch_context)
    if route_decision is not None:
        candidate = execution_plan_from_payload(route_decision)
        if isinstance(candidate, dict):
            steps = candidate.get("steps")
            if isinstance(steps, list) and len(steps) > 1:
                return candidate
    return None


def _find_agent_by_id(agent_id: str | None) -> dict | None:
    normalized_agent_id = str(agent_id or "").strip()
    if not normalized_agent_id:
        return None
    for agent in store.agents:
        if str(agent.get("id") or "").strip() == normalized_agent_id:
            return agent
    return None


def _append_orchestration_bullet(
    bullets: list[str],
    text_zh: str,
    text_en: str,
    *,
    language: str,
) -> None:
    bullets.insert(0, text_en if language == "en" else text_zh)


def _primary_request_text(task: dict) -> str:
    for line in _task_description_lines(task):
        if not line.startswith("补充上下文:") and not line.startswith("记忆注入:"):
            return line
    return str(task.get("description") or task.get("title") or "当前任务")


def _context_notes(task: dict) -> list[str]:
    return [
        line.split("补充上下文:", maxsplit=1)[1].strip()
        for line in _task_description_lines(task)
        if line.startswith("补充上下文:")
    ]


def _memory_notes(task: dict) -> list[str]:
    return [
        line.split("记忆注入:", maxsplit=1)[1].strip()
        for line in _task_description_lines(task)
        if line.startswith("记忆注入:")
    ]


def _truncate_text(value: str, limit: int = 20) -> str:
    cleaned = value.strip()
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit]}..."


def _is_greeting_message(text: str) -> bool:
    normalized = " ".join(str(text or "").strip().lower().split())
    if not normalized:
        return False
    return normalized in GREETING_EXACT_MATCHES


def _looks_like_live_information_request(text: str) -> bool:
    normalized = " ".join(str(text or "").strip().lower().split())
    if not normalized:
        return False
    return any(hint in normalized for hint in LIVE_INFORMATION_HINTS) and not any(
        hint in normalized for hint in PROJECT_DOMAIN_HINTS
    )


def _normalize_interaction_mode(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    normalized = _canonical_routing_strategy(normalized) or normalized
    if normalized in {"chat", "conversation", "dialog", "dialogue"}:
        return "chat"
    if normalized in {
        "task",
        "workflow",
        "workflow_or_direct",
        "workflow_or_direct_agent",
        CANONICAL_ROUTING_STRATEGY_WORKFLOW_OR_AGENT_DISPATCH_FALLBACK,
        "direct_agent",
        "direct",
    }:
        return "task"
    return None


def _canonical_routing_strategy(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    return LEGACY_ROUTING_STRATEGY_ALIASES.get(normalized, normalized)


def _normalize_reception_mode(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {
        "welcome",
        "small_talk",
        "clarify",
        "continuation",
        "task_handoff",
        "direct_question",
    }:
        return normalized
    return None


def _resolve_interaction_mode(task: dict, run: dict) -> str | None:
    payload_candidates: list[dict[str, Any]] = []
    dispatch_context = dispatch_context_from_run(run)
    if dispatch_context is not None:
        payload_candidates.append(dispatch_context)
        route_decision = route_decision_from_payload(dispatch_context)
        if route_decision is not None:
            payload_candidates.append(route_decision)

    task_route_decision = route_decision_from_task(task)
    if task_route_decision is not None:
        payload_candidates.append(task_route_decision)

    for payload in payload_candidates:
        mode = _normalize_interaction_mode(alias_text(payload, "interaction_mode", "interactionMode"))
        if mode:
            return mode
    return None


def _resolve_reception_mode(task: dict, run: dict) -> str | None:
    payload_candidates: list[dict[str, Any]] = []
    dispatch_context = dispatch_context_from_run(run)
    if dispatch_context is not None:
        payload_candidates.append(dispatch_context)
        route_decision = route_decision_from_payload(dispatch_context)
        if route_decision is not None:
            payload_candidates.append(route_decision)

    task_route_decision = route_decision_from_task(task)
    if task_route_decision is not None:
        payload_candidates.append(task_route_decision)

    for payload in payload_candidates:
        mode = _normalize_reception_mode(alias_text(payload, "reception_mode", "receptionMode"))
        if mode:
            return mode
    return None


def _resolve_route_decision(task: dict, run: dict) -> dict[str, Any] | None:
    payload_candidates: list[dict[str, Any]] = []
    dispatch_context = dispatch_context_from_run(run)
    if dispatch_context is not None:
        route_decision = route_decision_from_payload(dispatch_context)
        if route_decision is not None:
            payload_candidates.append(route_decision)
    task_route_decision = route_decision_from_task(task)
    if task_route_decision is not None:
        payload_candidates.append(task_route_decision)
    return payload_candidates[0] if payload_candidates else None


def _resolve_manager_packet(task: dict, run: dict) -> dict[str, Any] | None:
    payload_candidates: list[dict[str, Any]] = []
    dispatch_context = run.get("dispatch_context")
    if isinstance(dispatch_context, dict):
        manager_packet = dispatch_context.get("manager_packet")
        if isinstance(manager_packet, dict):
            payload_candidates.append(manager_packet)
    task_manager_packet = task.get("manager_packet")
    if isinstance(task_manager_packet, dict):
        payload_candidates.append(task_manager_packet)
    return payload_candidates[0] if payload_candidates else None


def _resolve_brain_dispatch_summary(task: dict, run: dict) -> dict[str, Any] | None:
    payload_candidates: list[dict[str, Any]] = []
    dispatch_context = run.get("dispatch_context")
    if isinstance(dispatch_context, dict):
        brain_dispatch_summary = dispatch_context.get("brain_dispatch_summary")
        if isinstance(brain_dispatch_summary, dict):
            payload_candidates.append(brain_dispatch_summary)
    task_dispatch_summary = task.get("brain_dispatch_summary")
    if isinstance(task_dispatch_summary, dict):
        payload_candidates.append(task_dispatch_summary)
    return payload_candidates[0] if payload_candidates else None


def _resolve_manager_field(task: dict, run: dict, key: str) -> str | None:
    manager_packet = _resolve_manager_packet(task, run)
    if not isinstance(manager_packet, dict):
        return None
    value = str(manager_packet.get(key) or "").strip()
    return value or None


def _normalize_workflow_mode(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"chat", "free_workflow", "professional_workflow"}:
        return normalized
    return None


def _resolve_workflow_mode(task: dict, run: dict) -> str | None:
    route_decision = _resolve_route_decision(task, run)
    if not isinstance(route_decision, dict):
        return None
    return _normalize_workflow_mode(
        route_decision.get("workflow_mode") or route_decision.get("workflowMode")
    )


def _resolve_required_capabilities(task: dict, run: dict) -> list[str]:
    route_decision = _resolve_route_decision(task, run)
    if not isinstance(route_decision, dict):
        return []
    raw = route_decision.get("required_capabilities") or route_decision.get("requiredCapabilities")
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _resolve_requires_permission(task: dict, run: dict) -> bool:
    route_decision = _resolve_route_decision(task, run)
    if not isinstance(route_decision, dict):
        return False
    value = route_decision.get("requires_permission")
    if isinstance(value, bool):
        return value
    value = route_decision.get("requiresPermission")
    return bool(value) if isinstance(value, bool) else False


def _free_workflow_payload(task: dict, run: dict) -> dict[str, Any]:
    return {
        "task_id": str(task.get("id") or ""),
        "request_text": _primary_request_text(task),
        "user_key": str(task.get("user_key") or "").strip() or None,
        "session_id": str(task.get("session_id") or "").strip() or None,
        "preferred_language": _output_language(task),
        "metadata": store.clone(task.get("metadata") or {}),
        "route_decision": store.clone(_resolve_route_decision(task, run) or {}),
        "manager_packet": store.clone(_resolve_manager_packet(task, run) or {}),
        "requires_permission": _resolve_requires_permission(task, run),
        "required_capabilities": _resolve_required_capabilities(task, run),
        "file_path": task.get("file_path") or task.get("filePath"),
        "document_text": task.get("document_text") or task.get("documentText"),
    }


def _should_use_free_workflow_runtime(task: dict, run: dict) -> bool:
    capabilities = set(_resolve_required_capabilities(task, run))
    if capabilities & {"task_status_lookup", "task_listing", "weather_lookup"}:
        return True
    if capabilities & {"pdf_processing", "document_conversion"}:
        return bool(
            task.get("file_path")
            or task.get("filePath")
            or task.get("document_text")
            or task.get("documentText")
        )
    return False


def _is_capability_question(text: str) -> bool:
    normalized = " ".join(str(text or "").strip().lower().split())
    if not normalized:
        return False
    return any(hint in normalized for hint in CHAT_CAPABILITY_HINTS)


def _is_small_talk_request(text: str) -> bool:
    normalized = " ".join(str(text or "").strip().lower().split())
    if not normalized:
        return False
    return any(hint in normalized for hint in SMALL_TALK_HINTS)


def _looks_like_chat_message(text: str) -> bool:
    normalized = " ".join(str(text or "").strip().lower().split())
    if not normalized:
        return False
    if (
        _is_greeting_message(normalized)
        or _is_capability_question(normalized)
        or _is_small_talk_request(normalized)
    ):
        return True
    if any(hint in normalized for hint in TASK_DIRECTIVE_HINTS):
        return False
    # Keep project/domain questions in the structured task/help branch
    # so they continue to use executor-oriented handling instead of casual chat fallback.
    if any(hint in normalized for hint in PROJECT_DOMAIN_HINTS):
        return False
    return len(normalized) <= 24


def _chat_fallback_text(
    *,
    request_text: str,
    language: str,
    context_notes: list[str],
    reception_mode: str | None,
) -> str:
    normalized = " ".join(str(request_text or "").strip().lower().split())
    if language == "en":
        if reception_mode == "welcome":
            return "Hello, I'm here. Tell me what you want to talk about or what you want me to help with, and I'll stay with you on it."
        if reception_mode == "small_talk":
            return "Of course. We can just talk here normally. Say whatever is on your mind."
        if reception_mode == "direct_question":
            if _looks_like_live_information_request(request_text):
                return (
                    f'You are asking about "{_truncate_text(request_text, 36)}", right? '
                    "I have not been connected to a verified live data source for this kind of question yet, "
                    "so I should not guess. If you want, I can tell you the fastest way to check it, "
                    "or you can send me the result and I will help you read it."
                )
            return (
                f'You are asking about "{_truncate_text(request_text, 36)}", right? '
                "I will stay on this exact question with you. If you want the short answer first, I can start there."
            )
        if reception_mode == "clarify":
            return "Sure. Tell me what is bothering you most right now, and I'll follow your meaning from there."
        if reception_mode == "continuation":
            return "Okay, I'll stay on this thread with you. Send the next detail and I'll continue."
        if reception_mode == "task_handoff":
            return "Understood. I can take this on with you. Tell me the specific goal or current blocker first."
        if _is_greeting_message(normalized):
            return "Hello, I'm here. Tell me what you want to do and I'll take it from there."
        if _is_capability_question(normalized):
            return (
                "I can help you troubleshoot issues, summarize information, draft replies, "
                "and keep working through follow-up context."
            )
        if _is_small_talk_request(normalized):
            return "Yes. We can keep this simple and just chat here. Say whatever is on your mind."
        if context_notes:
            return (
                f"I've incorporated your latest context: {_truncate_text(context_notes[-1], 48)}. "
                "Tell me the next step you want."
            )
        return "Understood. Share your goal in one sentence and I will continue from there."

    if reception_mode == "welcome":
        return "你好呀，我在呢。你想聊什么，或者想让我帮你看看什么，都可以直接跟我说。"
    if reception_mode == "small_talk":
        return "当然可以呀。我们就正常聊，你想到什么就直接跟我说就好。"
    if reception_mode == "direct_question":
        if _looks_like_live_information_request(request_text):
            return (
                f"你是在问「{_truncate_text(request_text, 24)}」呀。"
                "先跟你说一声，我这边现在还没接上这类实时外部数据源，所以不能装作查到了再回答你。"
                "你要是愿意，我可以告诉你最快怎么查，或者你把查到的结果发我，我再帮你一起看。"
            )
        return (
            f"你是在问「{_truncate_text(request_text, 24)}」呀。"
            "我就按这个问题直接陪你往下说，你要是想先听结论，我就先给结论；想展开一点，我也可以慢慢说。"
        )
    if reception_mode == "clarify":
        return "可以呀。你先把你现在最想解决的那一块直接告诉我，我会顺着你的意思慢慢接住。"
    if reception_mode == "continuation":
        return "好呀，你继续往下说。我会顺着这条对话接着跟，不用你重新起个头。"
    if reception_mode == "task_handoff":
        return "可以呀，这件事我先陪你一起接住。你把目标、场景或者现在卡住的地方直接告诉我就行。"
    if _is_greeting_message(normalized):
        return "你好，我在。你把现在要处理的事情直接发我，我会继续往下做。"
    if _is_capability_question(normalized):
        return "我可以帮你排查问题、整理信息、写回复，也可以根据你的补充持续跟进同一件事。"
    if _is_small_talk_request(normalized):
        return "可以。我们就正常聊，你想说什么就直接发我，不用整理成任务。"
    if context_notes:
        return f"我已经吸收你刚补充的上下文：{_truncate_text(context_notes[-1], 36)}。你希望我下一步先做哪一块？"
    return "明白了。你直接说目标或当前卡点，我会按对话方式继续推进。"


def _extract_json_object(text: str) -> dict[str, Any] | None:
    normalized = str(text or "").strip()
    if not normalized:
        return None
    fenced_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", normalized, flags=re.DOTALL)
    if fenced_match:
        normalized = fenced_match.group(1).strip()
    try:
        parsed = json.loads(normalized)
    except json.JSONDecodeError:
        start = normalized.find("{")
        end = normalized.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(normalized[start : end + 1])
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def _stringify_message_content(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        chunks: list[str] = []
        for item in value:
            if isinstance(item, str):
                if item.strip():
                    chunks.append(item.strip())
                continue
            if isinstance(item, dict):
                text = str(item.get("text") or item.get("content") or "").strip()
                if text:
                    chunks.append(text)
        return "\n".join(chunk for chunk in chunks if chunk).strip()
    if isinstance(value, dict):
        return str(value.get("text") or value.get("content") or "").strip()
    return str(value or "").strip()


def _output_language(task: dict) -> str:
    preferred_language = _normalize_language(
        task.get("preferred_language") or task.get("preferredLanguage")
    )
    if preferred_language:
        return preferred_language

    detected_lang = _normalize_language(task.get("detected_lang") or task.get("detectedLang"))
    if detected_lang:
        return detected_lang

    return detect_language(_primary_request_text(task))


def _knowledge_query(task: dict, intent: str) -> str:
    parts = [_primary_request_text(task), *_context_notes(task)[-2:], *_memory_notes(task)[:2]]
    if intent == "write":
        parts.append("WorkBot 项目背景 产品目标 核心特性 MVP")
    elif intent == "help":
        parts.append("开发指南补充 接入 安全网关 工作流 语言支持")
    return " ".join(part for part in parts if part).strip()


def _knowledge_hits(task: dict, intent: str) -> list[dict]:
    query = _knowledge_query(task, intent) or _primary_request_text(task)
    limit = 5 if intent == "search" else 3
    return document_search_service.search(query, intent=intent, limit=limit)


def _knowledge_label(hit: dict) -> str:
    return f"{hit['source_name']} / {hit['section']}"


def _knowledge_references(hits: list[dict], *, language: str = "zh") -> list[dict]:
    keywords_label = "关键词" if language == "zh" else "Keywords"
    excerpt_label = "摘录" if language == "zh" else "Excerpt"
    return [
        {
            "title": _knowledge_label(hit),
            "detail": (
                f"{keywords_label}: {', '.join(hit.get('matched_terms', [])[:4])}; {excerpt_label}: {hit['excerpt']}"
                if hit.get("matched_terms")
                else hit["excerpt"]
            ),
        }
        for hit in hits
    ]


def _provider_payloads() -> dict[str, Any]:
    runtime_settings = get_agent_api_runtime_settings()
    providers = runtime_settings.get("providers")
    return providers if isinstance(providers, dict) else {}


def _enabled_provider_keys(providers: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for provider_key in PROVIDER_SELECTION_ORDER:
        candidate = providers.get(provider_key)
        if not isinstance(candidate, dict):
            continue
        if not bool(candidate.get("enabled")):
            continue
        if not str(candidate.get("api_key") or "").strip():
            continue
        result.append(provider_key)
    return result


def _resolve_provider_key(execution_agent: dict | None, profile: dict[str, Any]) -> str | None:
    providers = _provider_payloads()
    enabled_provider_keys = _enabled_provider_keys(providers)
    if not enabled_provider_keys:
        return None

    snapshot = execution_agent.get("config_snapshot") if isinstance(execution_agent, dict) else None
    runtime = snapshot.get("runtime") if isinstance(snapshot, dict) and isinstance(snapshot.get("runtime"), dict) else {}
    binding = (
        runtime.get("agent_binding")
        if isinstance(runtime, dict) and isinstance(runtime.get("agent_binding"), dict)
        else {}
    )
    agent_doc = snapshot.get("agent") if isinstance(snapshot, dict) and isinstance(snapshot.get("agent"), dict) else {}
    explicit_provider = str(
        binding.get("provider_key")
        or binding.get("providerKey")
        or agent_doc.get("provider")
        or (execution_agent or {}).get("provider")
        or ""
    ).strip().lower()
    if explicit_provider in enabled_provider_keys:
        return explicit_provider

    model_name = str(profile.get("model") or "").strip().lower()
    if "claude" in model_name and "claude" in enabled_provider_keys:
        return "claude"
    if "kimi" in model_name and "kimi" in enabled_provider_keys:
        return "kimi"
    if "deepseek" in model_name and "deepseek" in enabled_provider_keys:
        return "deepseek"
    if "gemini" in model_name and "gemini" in enabled_provider_keys:
        return "gemini"
    if "codex" in model_name and "codex" in enabled_provider_keys:
        return "codex"
    if model_name.startswith("gpt") and "openai" in enabled_provider_keys:
        return "openai"

    return enabled_provider_keys[0]


def _resolve_provider_settings(provider_key: str | None) -> dict[str, Any] | None:
    if not provider_key:
        return None
    provider = _provider_payloads().get(provider_key)
    return provider if isinstance(provider, dict) else None


def _join_url(base_url: str, endpoint_path: str) -> str:
    return f"{base_url.rstrip('/')}/{endpoint_path.lstrip('/')}"


def _provider_headers(provider_key: str, provider: dict[str, Any]) -> dict[str, str]:
    api_key = str(provider.get("api_key") or "").strip()
    headers = {
        "content-type": "application/json",
        "accept": "application/json",
    }
    if provider_key == "claude":
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
    else:
        headers["authorization"] = f"Bearer {api_key}"
    organization_id = str(provider.get("organization_id") or "").strip()
    project_id = str(provider.get("project_id") or "").strip()
    if organization_id:
        headers["OpenAI-Organization"] = organization_id
    if project_id:
        headers["OpenAI-Project"] = project_id
    return headers


def _provider_model(profile: dict[str, Any], provider: dict[str, Any]) -> str:
    if str(profile.get("model_source") or "").strip().lower() == "manual_binding":
        return str(profile.get("model") or provider.get("model") or "").strip()
    return str(provider.get("model") or profile.get("model") or "").strip()


def _provider_prompt(
    *,
    mode: str,
    language: str,
    request_text: str,
    reception_mode: str | None,
    manager_packet: dict[str, Any] | None,
    knowledge_hits: list[dict],
    context_notes: list[str],
    memory_notes: list[str],
    profile: dict[str, Any],
) -> tuple[str, str]:
    context_lines = [f"- {note}" for note in context_notes[:3]] or ["- none"]
    memory_lines = [f"- {note}" for note in memory_notes[:3]] or ["- none"]
    grounding_lines = [
        f"- {_knowledge_label(hit)}: {hit['excerpt']}"
        for hit in knowledge_hits[:5]
    ] or ["- none"]
    manager_lines = []
    if isinstance(manager_packet, dict) and manager_packet:
        manager_lines = [
            f"- user_goal: {manager_packet.get('user_goal') or '-'}",
            f"- response_contract: {manager_packet.get('response_contract') or '-'}",
            f"- delivery_mode: {manager_packet.get('delivery_mode') or '-'}",
            f"- decomposition_hint: {manager_packet.get('decomposition_hint') or '-'}",
            f"- manager_action: {manager_packet.get('manager_action') or '-'}",
            f"- next_owner: {manager_packet.get('next_owner') or '-'}",
            f"- handoff_summary: {manager_packet.get('handoff_summary') or '-'}",
        ]
        clarify_question = str(manager_packet.get("clarify_question") or "").strip()
        if clarify_question:
            manager_lines.append(f"- clarify_question: {clarify_question}")
    else:
        manager_lines = ["- none"]

    if mode == "chat":
        if language == "en":
            system_prompt = (
                "You are WorkBot's receptionist-style conversational agent. "
                "First understand the user's current state, then reply like a capable human operator. "
                "Reply in a natural chat tone and output strict JSON with one key: text."
            )
            user_prompt = "\n".join(
                [
                    f"request: {request_text}",
                    f"reception_mode: {reception_mode or 'auto'}",
                    f"agent_name: {profile.get('agent_name') or 'Agent'}",
                    "context_notes:",
                    *context_lines,
                    "memory_notes:",
                    *memory_lines,
                    "manager_packet:",
                    *manager_lines,
                    "optional_grounding_sources:",
                    *grounding_lines[:3],
                    "requirements:",
                    "- First infer whether the user is greeting, making small talk, asking vaguely for help, continuing an earlier thread, or giving a concrete task.",
                    "- Speak like a single receptionist-style assistant, not like a workflow engine.",
                    "- Keep it conversational and concise.",
                    "- Do not expose internal orchestration terms, retrieved-source phrasing, or execution pipeline names.",
                    "- If the user asks for live or externally verified facts and you do not have grounded evidence here, do not guess. State the limitation plainly and offer the next best help.",
                    "- For vague asks, ask one short clarifying question.",
                    "- For small talk, reply naturally and do not turn it into a task.",
                    "- For concrete tasks, acknowledge naturally and say what you will do next without mentioning workflows.",
                    '- Output JSON only, like: {"text":"..."}',
                ]
            )
            return system_prompt, user_prompt

        system_prompt = (
            "你是 WorkBot 的接待员式对话 Agent。"
            "先理解用户此刻是在打招呼、闲聊、模糊求助、继续补充，还是明确下达任务，"
            "再像一个成熟的接待员一样自然回复。"
            "请用自然聊天口吻回复，并严格输出 JSON，只包含一个字段：text。"
        )
        user_prompt = "\n".join(
            [
                f"request: {request_text}",
                f"reception_mode: {reception_mode or 'auto'}",
                f"agent_name: {profile.get('agent_name') or 'Agent'}",
                "context_notes:",
                *context_lines,
                "memory_notes:",
                *memory_lines,
                "manager_packet:",
                *manager_lines,
                "optional_grounding_sources:",
                *grounding_lines[:3],
                "requirements:",
                "- 先判断用户当前是打招呼、闲聊、模糊求助、续聊补充，还是明确任务。",
                "- 像一个接待员一样先把用户接住，再决定是继续聊、先澄清，还是自然承接任务。",
                "- 语气自然、简洁、像即时聊天。",
                "- 不要暴露内部调度、编排、执行管线术语，也不要说“资料线索”“我先按这件事往下看”这类系统腔。",
                "- 如果用户问的是实时信息或外部事实，而你手头没有已验证的依据，就直接说明限制，不要编造结果。",
                "- 用户意图不清时先提一个简短澄清问题。",
                "- 用户只是想聊天时，就正常聊天，不要任务化。",
                "- 用户任务明确时，自然确认并说明下一步，不要直接念流程。",
                '- 只输出 JSON，例如：{"text":"..."}',
            ]
        )
        return system_prompt, user_prompt

    if language == "en":
        system_prompt = (
            "You are WorkBot's execution agent. "
            "Answer the user's request directly and output strict JSON with keys: "
            "title, summary, content, bullets. bullets must be an array of 2-5 strings."
        )
        user_prompt = "\n".join(
            [
                f"mode: {mode}",
                f"request: {request_text}",
                f"agent_name: {profile.get('agent_name') or 'Agent'}",
                f"agent_type: {profile.get('agent_type') or '-'}",
                f"agent_model: {profile.get('model') or '-'}",
                "context_notes:",
                *context_lines,
                "memory_notes:",
                *memory_lines,
                "manager_packet:",
                *manager_lines,
                "grounding_sources:",
                *grounding_lines,
                "requirements:",
                "- Keep the answer grounded in the provided sources when sources exist.",
                "- For search mode, summarize findings and mention the matched sources naturally.",
                "- For write mode, produce a polished ready-to-send response.",
                "- For help mode, produce concise actionable guidance.",
                "- Output JSON only. No markdown fences.",
            ]
        )
        return system_prompt, user_prompt

    system_prompt = (
        "你是 WorkBot 的执行 Agent。"
        "请直接完成用户请求，并严格输出 JSON，对象只包含：title、summary、content、bullets。"
        "其中 bullets 必须是 2-5 条字符串数组。"
    )
    user_prompt = "\n".join(
        [
            f"mode: {mode}",
            f"request: {request_text}",
            f"agent_name: {profile.get('agent_name') or 'Agent'}",
            f"agent_type: {profile.get('agent_type') or '-'}",
            f"agent_model: {profile.get('model') or '-'}",
            "context_notes:",
            *context_lines,
            "memory_notes:",
            *memory_lines,
            "manager_packet:",
            *manager_lines,
            "grounding_sources:",
            *grounding_lines,
            "requirements:",
            "- 有资料时优先基于资料作答，不要脱离上下文胡编。",
            "- search 模式输出检索结论，尽量自然提到命中资料。",
            "- write 模式输出可直接发送的成稿。",
            "- help 模式输出简洁、可执行的说明。",
            "- 只输出 JSON，不要 markdown 代码块。",
        ]
    )
    return system_prompt, user_prompt


def _parse_provider_text(provider_key: str, endpoint_path: str, payload: dict[str, Any]) -> str:
    normalized_path = endpoint_path.rstrip("/").lower()
    if normalized_path.endswith("/responses"):
        output_text = _stringify_message_content(payload.get("output_text"))
        if output_text:
            return output_text
        output = payload.get("output")
        if isinstance(output, list):
            chunks: list[str] = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if isinstance(content, list):
                    for content_item in content:
                        if not isinstance(content_item, dict):
                            continue
                        text = _stringify_message_content(
                            content_item.get("text") or content_item.get("content")
                        )
                        if text:
                            chunks.append(text)
            return "\n".join(chunk for chunk in chunks if chunk).strip()
        return ""

    if provider_key == "claude" or normalized_path.endswith("/messages"):
        content = payload.get("content")
        return _stringify_message_content(content)

    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict):
            return _stringify_message_content(message.get("content"))
        text = choices[0].get("text") if isinstance(choices[0], dict) else None
        return _stringify_message_content(text)
    return ""


def _build_provider_result_payload(
    *,
    mode: str,
    language: str,
    raw_text: str,
    knowledge_hits: list[dict],
    profile: dict[str, Any],
    provider_key: str,
    provider_model_name: str,
) -> dict[str, Any] | None:
    parsed = _extract_json_object(raw_text)
    if mode == "chat":
        text = ""
        if isinstance(parsed, dict):
            text = str(
                parsed.get("text")
                or parsed.get("content")
                or parsed.get("reply")
                or ""
            ).strip()
        if not text:
            text = str(raw_text or "").strip()
        if not text:
            return None
        return {
            "kind": "chat_reply",
            "text": text,
            "content": text,
            "bullets": [],
            "references": [],
            "execution_trace": [
                {
                    "stage": "provider_inference",
                    "title": "真实 Agent 推理" if language != "en" else "Provider inference",
                    "status": "completed",
                    "detail": (
                        f"已通过 {provider_key} / {provider_model_name or '-'} 生成聊天回复。"
                        if language != "en"
                        else f"Generated conversational reply via {provider_key} / {provider_model_name or '-'}."
                    ),
                    "metadata": {
                        "provider": provider_key,
                        "model": provider_model_name or None,
                        "mode": "chat",
                    },
                }
            ],
        }

    if parsed is None:
        return None
    title = str(parsed.get("title") or "").strip()
    summary = str(parsed.get("summary") or "").strip()
    content = str(parsed.get("content") or "").strip()
    bullets_raw = parsed.get("bullets")
    bullets = [str(item).strip() for item in bullets_raw if str(item).strip()] if isinstance(bullets_raw, list) else []
    if not content:
        return None
    return {
        "kind": RESULT_KIND_BY_MODE.get(mode, "help_note"),
        "title": title or (
            "问候回复" if mode == "help" and language != "en" else
            "Greeting" if mode == "help" and language == "en" else
            ("检索结果" if mode == "search" and language != "en" else "Search Result") if mode == "search" else
            ("写作结果" if language != "en" else "Draft Result")
        ),
        "summary": summary or (
            "已由真实 Agent 生成回复" if language != "en" else "Generated by real agent provider"
        ),
        "content": content,
        "bullets": bullets[:5] or [
            (
                f"已通过 {provider_key} / {provider_model_name or '-'} 生成真实回复。"
                if language != "en"
                else f"Generated by {provider_key} / {provider_model_name or '-'}."
            )
        ],
        "references": _knowledge_references(knowledge_hits, language=language),
        "execution_trace": [
            {
                "stage": "provider_inference",
                "title": "真实 Agent 推理" if language != "en" else "Provider inference",
                "status": "completed",
                "detail": (
                    f"已通过 {provider_key} / {provider_model_name or '-'} 完成真实 Agent 推理。"
                    if language != "en"
                    else f"Completed real agent inference via {provider_key} / {provider_model_name or '-'}."
                ),
                "metadata": {
                    "provider": provider_key,
                    "model": provider_model_name or None,
                },
            },
            {
                "stage": "execution_profile",
                "title": "执行画像" if language != "en" else "Execution profile",
                "status": "completed",
                "detail": (
                    f"执行画像已解析：status=provider_live；model={provider_model_name or '-'}。"
                    if language != "en"
                    else f"Executor profile resolved: status=provider_live; model={provider_model_name or '-'}."
                ),
                "metadata": {
                    "profile_status": "provider_live",
                    "model": provider_model_name or None,
                    "tool_count": len(profile.get("tools") or []),
                    "supports_intent": profile.get("supports_intent"),
                    "provider": provider_key,
                },
            },
        ],
    }


def _extract_tool_names(config_snapshot: dict[str, Any] | None) -> list[str]:
    if not isinstance(config_snapshot, dict):
        return []
    tools_payload = config_snapshot.get("tools")
    if isinstance(tools_payload, dict):
        tools_payload = tools_payload.get("tools", tools_payload)
    if not isinstance(tools_payload, list):
        return []
    return [
        name
        for name in (
            str(item.get("name") or "").strip()
            for item in tools_payload
            if isinstance(item, dict)
        )
        if name
    ]


def _agent_type_supports_intent(agent_type: Any, intent: str | None) -> bool:
    normalized_type = str(agent_type or "").strip().lower()
    return bool(intent) and intent in AGENT_TYPE_INTENT_COMPAT.get(normalized_type, set())


def _intent_capability_supports_intent(capabilities: list[str], intent: str | None) -> bool:
    if not intent:
        return False
    normalized_capabilities = {item.lower() for item in capabilities}
    return bool(normalized_capabilities & INTENT_CAPABILITY_HINTS.get(intent, set()))


def _safe_execution_profile(execution_agent: dict | None, run: dict) -> dict[str, Any]:
    intent = _normalize_intent(run.get("intent"))
    if not isinstance(execution_agent, dict):
        return {
            "status": "missing",
            "agent_name": None,
            "agent_type": None,
            "model": None,
            "version": None,
            "supported_intents": [],
            "capabilities": [],
            "tools": [],
            "warnings": [],
            "supports_intent": None,
            "max_iterations": None,
            "timeout_seconds": None,
            "examples_count": 0,
        }

    snapshot = execution_agent.get("config_snapshot")
    warning: str | None = None
    if not isinstance(snapshot, dict):
        try:
            snapshot = agent_config_service.load_agent_config(execution_agent)
            if isinstance(snapshot, dict):
                execution_agent["config_snapshot"] = snapshot
                execution_agent["config_summary"] = build_agent_config_summary(snapshot)
        except Exception as exc:  # pragma: no cover - defensive fail-open path
            snapshot = None
            warning = f"Agent config load failed: {exc}"

    summary = build_agent_config_summary(snapshot) if isinstance(snapshot, dict) else None
    agent_doc = snapshot.get("agent") if isinstance(snapshot, dict) else None
    if not isinstance(agent_doc, dict):
        agent_doc = {}
    runtime = snapshot.get("runtime") if isinstance(snapshot, dict) and isinstance(snapshot.get("runtime"), dict) else {}
    runtime_binding = (
        runtime.get("agent_binding")
        if isinstance(runtime, dict) and isinstance(runtime.get("agent_binding"), dict)
        else {}
    )
    execution_settings = agent_doc.get("execution") if isinstance(agent_doc.get("execution"), dict) else {}
    supported_intents = [item.lower() for item in _string_list(agent_doc.get("trigger_intents"))]
    capabilities = [item.lower() for item in _string_list(agent_doc.get("capabilities"))]
    warnings = _string_list((snapshot or {}).get("warnings"))
    if warning:
        warnings.append(warning)
    model = str(
        runtime_binding.get("model")
        or agent_doc.get("model")
        or ""
    ).strip() or None
    model_source = (
        "manual_binding"
        if str(runtime_binding.get("model") or "").strip()
        else ("agent_config" if model else None)
    )

    supports_intent: bool | None = None
    if intent:
        supports_intent = (
            intent in supported_intents
            or _intent_capability_supports_intent(capabilities, intent)
            or _agent_type_supports_intent(execution_agent.get("type"), intent)
        )
        if supports_intent is False:
            warnings.append(f'当前意图 "{intent}" 未在 Agent 配置中显式声明，已按兼容模式继续执行。')

    return {
        "status": str((summary or {}).get("status") or ("error" if warning else "missing")),
        "agent_name": str(execution_agent.get("name") or "").strip() or None,
        "agent_type": str(execution_agent.get("type") or "").strip().lower() or None,
        "model": model,
        "model_source": model_source,
        "version": str(agent_doc.get("version") or (snapshot or {}).get("version") or "").strip() or None,
        "supported_intents": supported_intents,
        "capabilities": capabilities,
        "tools": _extract_tool_names(snapshot),
        "warnings": warnings,
        "supports_intent": supports_intent,
        "max_iterations": execution_settings.get("max_iterations"),
        "timeout_seconds": execution_settings.get("timeout_seconds"),
        "examples_count": int((summary or {}).get("examples_count") or 0),
    }


def _execution_profile_bullets(profile: dict[str, Any], *, language: str) -> list[str]:
    agent_name = str(profile.get("agent_name") or "").strip() or "Agent executor"
    model = str(profile.get("model") or "").strip()
    tools = [str(item).strip() for item in profile.get("tools") or [] if str(item).strip()]
    warnings = [str(item).strip() for item in profile.get("warnings") or [] if str(item).strip()]
    status = str(profile.get("status") or "missing")
    examples_count = int(profile.get("examples_count") or 0)

    detail_parts: list[str] = []
    if model:
        detail_parts.append(f"model={model}")
    if tools:
        detail_parts.append(f"tools={', '.join(tools[:3])}")
    if profile.get("max_iterations") is not None:
        detail_parts.append(f"max_iterations={profile['max_iterations']}")
    if profile.get("timeout_seconds") is not None:
        detail_parts.append(f"timeout={profile['timeout_seconds']}s")

    if language == "en":
        bullet = f"Execution profile: {agent_name}"
        if detail_parts:
            bullet += f" ({'; '.join(detail_parts)})"
        bullet += f"; config={status}; examples={examples_count}."
        notes = [bullet]
        if warnings:
            notes.append(f"Config note: {warnings[0]}")
        return notes

    bullet = f"执行画像：{agent_name}"
    if detail_parts:
        bullet += f"（{'; '.join(detail_parts)}）"
    bullet += f"；配置状态={status}；示例数={examples_count}。"
    notes = [bullet]
    if warnings:
        notes.append(f"配置提示：{warnings[0]}")
    return notes


def _resolve_execution_mode(
    task: dict | None,
    execution_agent: dict | None,
    run: dict,
    profile: dict[str, Any] | None = None,
) -> str:
    runtime_task = task if isinstance(task, dict) else {}
    delivery_mode = _resolve_manager_field(runtime_task, run, "delivery_mode")
    agent_type = str((execution_agent or {}).get("type") or "").strip().lower()
    intent = str(run.get("intent") or "").strip().lower()
    interaction_mode = _resolve_interaction_mode(runtime_task, run)
    if delivery_mode == "conversational":
        return "chat"
    if interaction_mode == "chat":
        return "chat"
    request_text = _primary_request_text(runtime_task) if runtime_task else ""
    if _looks_like_chat_message(request_text) and intent in {"", "help", "manual"}:
        return "chat"
    if intent == "help":
        return "help"
    if agent_type == "search" or intent == "search":
        return "search"
    if agent_type == "write" or intent == "write":
        return "write"

    supported_intents = [_normalize_intent(item) for item in (profile or {}).get("supported_intents") or []]
    for candidate in ("search", "write", "help"):
        if candidate in supported_intents:
            return candidate
    if agent_type == "output":
        return "help"
    return intent or agent_type or "default"


def _execution_trace_entries(
    *,
    language: str,
    mode: str,
    request_text: str,
    manager_packet: dict[str, Any] | None,
    knowledge_hits: list[dict],
    context_notes: list[str],
    memory_notes: list[str],
    profile: dict[str, Any],
) -> list[dict[str, Any]]:
    mode_label = {
        "chat": ("Chat", "对话"),
        "search": ("Search", "检索"),
        "write": ("Write", "写作"),
        "help": ("Help", "帮助"),
    }.get(mode, ("Task", "任务"))
    matched_sources = [_knowledge_label(hit) for hit in knowledge_hits[:2]]
    matched_sources_text = ", ".join(matched_sources) if matched_sources else "-"
    profile_model = str(profile.get("model") or "").strip() or "-"
    profile_tools = [str(item).strip() for item in profile.get("tools") or [] if str(item).strip()]
    profile_status = str(profile.get("status") or "missing")
    supports_intent = profile.get("supports_intent")
    manager_action = str((manager_packet or {}).get("manager_action") or "").strip()
    next_owner = str((manager_packet or {}).get("next_owner") or "").strip()
    delivery_mode = str((manager_packet or {}).get("delivery_mode") or "").strip()
    decomposition_hint = str((manager_packet or {}).get("decomposition_hint") or "").strip()
    workflow_admission = str((manager_packet or {}).get("workflow_admission") or "").strip()

    if language == "en":
        context_detail = (
            f"Applied latest context patch: {_truncate_text(context_notes[-1], 42)}."
            if context_notes
            else "No context patch was provided for this run."
        )
        memory_detail = (
            f"Injected memory clue: {_truncate_text(memory_notes[0], 42)}."
            if memory_notes
            else "No long-term memory clue was injected."
        )
        return [
            {
                "stage": "request_analysis",
                "title": "Request analysis",
                "status": "completed",
                "detail": (
                    f'Parsed request "{_truncate_text(request_text, 56)}" and selected mode '
                    f"{mode_label[0].lower()}."
                ),
                "metadata": {
                    "mode": mode,
                    "language": language,
                    "request_chars": len(request_text),
                },
            },
            {
                "stage": "knowledge_retrieval",
                "title": "Knowledge retrieval",
                "status": "completed",
                "detail": f"Retrieved {len(knowledge_hits)} local references. Top matches: {matched_sources_text}.",
                "metadata": {
                    "hits": len(knowledge_hits),
                    "top_source": matched_sources[0] if matched_sources else None,
                },
            },
            {
                "stage": "context_memory_injection",
                "title": "Context & memory injection",
                "status": "completed",
                "detail": f"{context_detail} {memory_detail}",
                "metadata": {
                    "context_notes": len(context_notes),
                    "memory_notes": len(memory_notes),
                },
            },
            {
                "stage": "manager_directive",
                "title": "Manager directive",
                "status": "completed",
                "detail": (
                    "Applied brain manager decision: "
                    f"action={manager_action or '-'}; next_owner={next_owner or '-'}; "
                    f"delivery_mode={delivery_mode or '-'}; decomposition_hint={decomposition_hint or '-'}."
                ),
                "metadata": {
                    "manager_action": manager_action or None,
                    "next_owner": next_owner or None,
                    "delivery_mode": delivery_mode or None,
                    "decomposition_hint": decomposition_hint or None,
                    "workflow_admission": workflow_admission or None,
                },
            },
            {
                "stage": "result_rendering",
                "title": "Result rendering",
                "status": "completed",
                "detail": (
                    f"Rendered a {mode_label[0].lower()} result with references, "
                    "summary bullets, and deliverable content."
                ),
                "metadata": {
                    "result_mode": mode,
                    "bullet_count": 0,
                    "reference_count": len(knowledge_hits),
                },
            },
            {
                "stage": "execution_profile",
                "title": "Execution profile",
                "status": "completed",
                "detail": (
                    f"Executor profile resolved: status={profile_status}; model={profile_model}; "
                    f"tools={', '.join(profile_tools[:3]) if profile_tools else '-'}."
                ),
                "metadata": {
                    "profile_status": profile_status,
                    "model": profile_model,
                    "tool_count": len(profile_tools),
                    "supports_intent": supports_intent,
                },
            },
        ]

    context_detail = (
        f"已应用最近一次补充上下文：{_truncate_text(context_notes[-1], 42)}。"
        if context_notes
        else "本轮没有追加补充上下文。"
    )
    memory_detail = (
        f"已注入历史记忆线索：{_truncate_text(memory_notes[0], 42)}。"
        if memory_notes
        else "本轮没有注入长期记忆线索。"
    )
    return [
        {
            "stage": "request_analysis",
            "title": "请求解析",
            "status": "completed",
            "detail": f'已解析请求「{_truncate_text(request_text, 56)}」，并选择{mode_label[1]}模式。',
            "metadata": {
                "mode": mode,
                "language": language,
                "request_chars": len(request_text),
            },
        },
        {
            "stage": "knowledge_retrieval",
            "title": "知识检索",
            "status": "completed",
            "detail": f"已检索到 {len(knowledge_hits)} 条本地资料，核心命中：{matched_sources_text}。",
            "metadata": {
                "hits": len(knowledge_hits),
                "top_source": matched_sources[0] if matched_sources else None,
            },
        },
        {
            "stage": "context_memory_injection",
            "title": "上下文与记忆注入",
            "status": "completed",
            "detail": f"{context_detail}{memory_detail}",
            "metadata": {
                "context_notes": len(context_notes),
                "memory_notes": len(memory_notes),
            },
        },
        {
            "stage": "manager_directive",
            "title": "项目经理指令",
            "status": "completed",
            "detail": (
                f"已应用项目经理决策：action={manager_action or '-'}；"
                f"next_owner={next_owner or '-'}；delivery_mode={delivery_mode or '-'}；"
                f"decomposition_hint={decomposition_hint or '-'}。"
            ),
            "metadata": {
                "manager_action": manager_action or None,
                "next_owner": next_owner or None,
                "delivery_mode": delivery_mode or None,
                "decomposition_hint": decomposition_hint or None,
                "workflow_admission": workflow_admission or None,
            },
        },
        {
            "stage": "result_rendering",
            "title": "结果渲染",
            "status": "completed",
            "detail": f"已完成{mode_label[1]}结果渲染，包含摘要、正文与参考线索。",
            "metadata": {
                "result_mode": mode,
                "bullet_count": 0,
                "reference_count": len(knowledge_hits),
            },
        },
        {
            "stage": "execution_profile",
            "title": "执行画像",
            "status": "completed",
            "detail": (
                f"执行画像已解析：status={profile_status}；model={profile_model}；"
                f"tools={', '.join(profile_tools[:3]) if profile_tools else '-'}。"
            ),
            "metadata": {
                "profile_status": profile_status,
                "model": profile_model,
                "tool_count": len(profile_tools),
                "supports_intent": supports_intent,
            },
        },
    ]


class AgentExecutionService:
    def _call_provider(
        self,
        *,
        provider_key: str,
        provider: dict[str, Any],
        profile: dict[str, Any],
        mode: str,
        language: str,
        request_text: str,
        reception_mode: str | None,
        manager_packet: dict[str, Any] | None,
        knowledge_hits: list[dict],
        context_notes: list[str],
        memory_notes: list[str],
    ) -> dict[str, Any] | None:
        base_url = str(provider.get("base_url") or "").strip()
        endpoint_path = str(provider.get("endpoint_path") or "").strip()
        api_key = str(provider.get("api_key") or "").strip()
        model_name = _provider_model(profile, provider)
        if not base_url or not endpoint_path or not api_key or not model_name:
            return None

        system_prompt, user_prompt = _provider_prompt(
            mode=mode,
            language=language,
            request_text=request_text,
            reception_mode=reception_mode,
            manager_packet=manager_packet,
            knowledge_hits=knowledge_hits,
            context_notes=context_notes,
            memory_notes=memory_notes,
            profile=profile,
        )

        normalized_path = endpoint_path.rstrip("/").lower()
        if provider_key == "claude" or normalized_path.endswith("/messages"):
            payload = {
                "model": model_name,
                "max_tokens": 1200,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            }
        elif normalized_path.endswith("/responses"):
            payload = {
                "model": model_name,
                "input": [
                    {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
                    {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
                ],
            }
        else:
            payload = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.3,
            }

        try:
            with httpx.Client(timeout=45.0, trust_env=False) as client:
                response = client.post(
                    _join_url(base_url, endpoint_path),
                    headers=_provider_headers(provider_key, provider),
                    json=payload,
                )
                response.raise_for_status()
                response_payload = response.json()
        except Exception as exc:  # pragma: no cover - real network path
            logger.warning("Agent provider request failed for %s: %s", provider_key, exc)
            return None

        if not isinstance(response_payload, dict):
            return None

        raw_text = _parse_provider_text(provider_key, endpoint_path, response_payload)
        if not raw_text:
            return None
        return _build_provider_result_payload(
            mode=mode,
            language=language,
            raw_text=raw_text,
            knowledge_hits=knowledge_hits,
            profile=profile,
            provider_key=provider_key,
            provider_model_name=model_name,
        )

    def _try_provider_result(
        self,
        *,
        task: dict,
        run: dict,
        execution_agent: dict | None,
        profile: dict[str, Any],
        mode: str,
        knowledge_hits: list[dict],
        context_notes: list[str],
        memory_notes: list[str],
    ) -> dict[str, Any] | None:
        provider_key = _resolve_provider_key(execution_agent, profile)
        provider = _resolve_provider_settings(provider_key)
        if not provider_key or provider is None:
            return None
        return self._call_provider(
            provider_key=provider_key,
            provider=provider,
            profile=profile,
            mode=mode,
            language=_output_language(task),
            request_text=_primary_request_text(task),
            reception_mode=_resolve_reception_mode(task, run),
            manager_packet=_resolve_manager_packet(task, run),
            knowledge_hits=knowledge_hits,
            context_notes=context_notes,
            memory_notes=memory_notes,
        )

    def _dispatch_contract(
        self,
        *,
        task: dict,
        run: dict,
        execution_agent: dict | None,
        result: dict[str, Any],
        execution_plan: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        route_decision = _resolve_route_decision(task, run) or {}
        manager_packet = _resolve_manager_packet(task, run) or {}
        summary = _resolve_brain_dispatch_summary(task, run) or {}
        resolved_execution_plan = execution_plan or _planned_execution(run) or (
            route_decision.get("execution_plan") or route_decision.get("executionPlan") or {}
        )
        if not isinstance(resolved_execution_plan, dict):
            resolved_execution_plan = {}
        fallback_policy = route_decision.get("fallback_policy") or route_decision.get("fallbackPolicy") or {}
        if not isinstance(fallback_policy, dict):
            fallback_policy = {}
        route_rationale = route_decision.get("route_rationale") or route_decision.get("routeRationale") or {}
        if not isinstance(route_rationale, dict):
            route_rationale = {}
        execution_agent_name = (
            str(summary.get("execution_agent") or summary.get("executionAgent") or "").strip()
            or str((execution_agent or {}).get("name") or "").strip()
            or str(route_decision.get("execution_agent") or route_decision.get("executionAgent") or "").strip()
            or None
        )
        routing_strategy = _canonical_routing_strategy(
            summary.get("routing_strategy")
            or summary.get("routingStrategy")
            or route_decision.get("routing_strategy")
            or route_decision.get("routingStrategy")
        )
        return {
            "contract_version": "brain-core-v1",
            "workflow_mode": _resolve_workflow_mode(task, run),
            "interaction_mode": _resolve_interaction_mode(task, run),
            "reception_mode": _resolve_reception_mode(task, run),
            "routing_strategy": routing_strategy,
            "execution_topology": str(
                summary.get("execution_topology")
                or summary.get("executionTopology")
                or resolved_execution_plan.get("plan_type")
                or resolved_execution_plan.get("coordination_mode")
                or ""
            ).strip()
            or None,
            "execution_agent": execution_agent_name,
            "delivery_mode": str(
                manager_packet.get("delivery_mode")
                or summary.get("delivery_mode")
                or summary.get("deliveryMode")
                or ""
            ).strip()
            or None,
            "response_contract": str(
                manager_packet.get("response_contract")
                or summary.get("response_contract")
                or summary.get("responseContract")
                or ""
            ).strip()
            or None,
            "session_state": str(
                manager_packet.get("session_state")
                or summary.get("session_state")
                or summary.get("sessionState")
                or ""
            ).strip()
            or None,
            "state_label": str(
                manager_packet.get("state_label")
                or summary.get("state_label")
                or summary.get("stateLabel")
                or ""
            ).strip()
            or None,
            "execution_scope": str(
                route_decision.get("execution_scope")
                or route_decision.get("executionScope")
                or summary.get("execution_scope")
                or summary.get("executionScope")
                or ""
            ).strip()
            or None,
            "fallback_mode": str(
                summary.get("fallback_mode")
                or summary.get("fallbackMode")
                or fallback_policy.get("mode")
                or ""
            ).strip()
            or None,
            "route_reason_summary": str(
                summary.get("route_reason_summary")
                or summary.get("routeReasonSummary")
                or route_rationale.get("route_reason_summary")
                or ""
            ).strip()
            or None,
            "planned_step_count": int(
                resolved_execution_plan.get("step_count")
                or len(resolved_execution_plan.get("steps") or [])
                or 0
            ),
            "result_kind": str(result.get("kind") or "").strip() or None,
        }

    def _fallback_contract(
        self,
        *,
        task: dict,
        run: dict,
        stage: str,
        activated: bool,
        resolution: str,
        detail: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        route_decision = _resolve_route_decision(task, run) or {}
        policy = route_decision.get("fallback_policy") or route_decision.get("fallbackPolicy") or {}
        if not isinstance(policy, dict):
            policy = {}
        return {
            "mode": str(policy.get("mode") or "").strip() or None,
            "target": str(policy.get("target") or "").strip() or None,
            "on_failure": str(policy.get("on_failure") or policy.get("onFailure") or "").strip() or None,
            "summary": str(policy.get("summary") or "").strip() or None,
            "stage": stage,
            "activated": activated,
            "resolution": resolution,
            "detail": str(detail or "").strip() or None,
            "metadata": store.clone(metadata or {}),
        }

    def _aggregation_contract(
        self,
        *,
        execution_plan: dict[str, Any],
        agent_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        completed_agents = sum(1 for item in agent_results if item.get("status") == "completed")
        failed_agents = sum(1 for item in agent_results if item.get("status") == "failed")
        cancelled_agents = sum(1 for item in agent_results if item.get("status") == "cancelled")
        return {
            "mode": str(execution_plan.get("coordination_mode") or "serial").strip().lower() or "serial",
            "plan_type": str(execution_plan.get("plan_type") or "multi_agent").strip() or "multi_agent",
            "planner": str(execution_plan.get("planner") or "").strip() or None,
            "aggregator": str(execution_plan.get("aggregator") or "").strip() or None,
            "step_count": int(execution_plan.get("step_count") or len(execution_plan.get("steps") or []) or 0),
            "branch_count": len(agent_results),
            "completed_agents": completed_agents,
            "successful_agents": completed_agents,
            "failed_agents": failed_agents,
            "cancelled_agents": cancelled_agents,
            "fan_in": store.clone(
                execution_plan.get("fan_in") or execution_plan.get("fanIn") or {}
            ),
            "winner_strategy": str(
                execution_plan.get("winner_strategy") or execution_plan.get("winnerStrategy") or ""
            ).strip()
            or None,
            "quorum": store.clone(execution_plan.get("quorum") or {}),
            "merge_strategy": str(
                execution_plan.get("merge_strategy") or execution_plan.get("mergeStrategy") or ""
            ).strip()
            or None,
            "cancel_policy": store.clone(
                execution_plan.get("cancel_policy") or execution_plan.get("cancelPolicy") or {}
            ),
            "branch_results": [
                {
                    "step_id": str((item.get("step") or {}).get("id") or "").strip() or None,
                    "branch_id": str((item.get("step") or {}).get("branch_id") or "").strip() or None,
                    "intent": str((item.get("step") or {}).get("intent") or "").strip() or None,
                    "agent": str(
                        (item.get("step") or {}).get("execution_agent")
                        or (item.get("step") or {}).get("agent")
                        or ""
                    ).strip()
                    or None,
                    "status": str(item.get("status") or "").strip() or None,
                    "score": int(item.get("score") or 0),
                }
                for item in agent_results
            ],
        }

    def _result_is_acceptable(self, result: dict[str, Any] | None) -> bool:
        if not isinstance(result, dict):
            return False
        if str(result.get("kind") or "").strip():
            return True
        for key in ("summary", "content", "text", "title"):
            if str(result.get(key) or "").strip():
                return True
        return False

    def _result_quality_score(self, result: dict[str, Any] | None) -> int:
        if not isinstance(result, dict):
            return 0
        score = 0
        if str(result.get("summary") or "").strip():
            score += 3
        if str(result.get("content") or result.get("text") or "").strip():
            score += 3
        score += min(len(result.get("bullets") or []), 4)
        score += min(len(result.get("references") or []), 4)
        return score

    def _resolve_quorum_min_success(self, execution_plan: dict[str, Any], total_steps: int) -> int:
        quorum = execution_plan.get("quorum") or {}
        if isinstance(quorum, dict):
            try:
                resolved = int(quorum.get("min_success_count") or quorum.get("minSuccessCount") or 0)
            except (TypeError, ValueError):
                resolved = 0
            if resolved > 0:
                return resolved
        return max(1, total_steps)

    def _select_multi_agent_result(
        self,
        *,
        execution_plan: dict[str, Any],
        agent_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        coordination_mode = str(execution_plan.get("coordination_mode") or "serial").strip().lower()
        winner_strategy = str(
            execution_plan.get("winner_strategy") or execution_plan.get("winnerStrategy") or "first_acceptable"
        ).strip().lower() or "first_acceptable"
        successful_results = [item for item in agent_results if item.get("status") == "completed"]
        candidate_pool = successful_results or [
            item for item in agent_results if isinstance(item.get("result"), dict)
        ]
        if not candidate_pool:
            return {}
        if coordination_mode == "serial":
            return candidate_pool[-1]
        if winner_strategy == "highest_score":
            return max(candidate_pool, key=lambda item: int(item.get("score") or 0))
        return candidate_pool[0]

    def _attach_execution_contracts(
        self,
        *,
        task: dict,
        run: dict,
        execution_agent: dict | None,
        result: dict[str, Any],
        execution_plan: dict[str, Any] | None = None,
        fallback_contract: dict[str, Any] | None = None,
        aggregation_contract: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        wrapped = store.clone(result)
        wrapped["dispatch_contract"] = self._dispatch_contract(
            task=task,
            run=run,
            execution_agent=execution_agent,
            result=wrapped,
            execution_plan=execution_plan,
        )
        if fallback_contract is not None:
            wrapped["fallback_contract"] = store.clone(fallback_contract)
        elif isinstance(wrapped.get("fallback_contract"), dict):
            wrapped["fallback_contract"] = store.clone(wrapped["fallback_contract"])
        if aggregation_contract is not None:
            wrapped["aggregation_contract"] = store.clone(aggregation_contract)
        elif isinstance(wrapped.get("aggregation_contract"), dict):
            wrapped["aggregation_contract"] = store.clone(wrapped["aggregation_contract"])
        return wrapped

    def build_greeting_result(
        self,
        *,
        task: dict,
    ) -> dict:
        language = _output_language(task)
        if language == "en":
            text = "Hello, I'm here. Tell me what you want to handle and I'll continue with you."
        else:
            text = "你好，我在。你把要处理的事情直接发我，我会继续往下做。"
        return {
            "kind": "chat_reply",
            "text": text,
            "content": text,
            "bullets": [],
            "references": [],
            "execution_trace": [],
        }

    def build_chat_result(
        self,
        *,
        task: dict,
        run: dict,
        execution_agent: dict | None = None,
        profile: dict[str, Any] | None = None,
    ) -> dict:
        resolved_profile = profile or _safe_execution_profile(execution_agent, run)
        language = _output_language(task)
        request_text = _primary_request_text(task)
        reception_mode = _resolve_reception_mode(task, run)
        manager_packet = _resolve_manager_packet(task, run) or {}
        context_notes = _context_notes(task)
        memory_notes = _memory_notes(task)
        knowledge_hits = _knowledge_hits(task, "help")
        provider_result = self._try_provider_result(
            task=task,
            run=run,
            execution_agent=execution_agent,
            profile=resolved_profile,
            mode="chat",
            knowledge_hits=knowledge_hits,
            context_notes=context_notes,
            memory_notes=memory_notes,
        )
        if provider_result is not None:
            return provider_result

        references: list[dict[str, Any]] = []
        if str(manager_packet.get("response_contract") or "") == "clarify_first" and str(
            manager_packet.get("clarify_question") or ""
        ).strip():
            text = str(manager_packet.get("clarify_question") or "").strip()
        else:
            text = _chat_fallback_text(
                request_text=request_text,
                language=language,
                context_notes=context_notes,
                reception_mode=reception_mode,
            )

        execution_trace = _execution_trace_entries(
            language=language,
            mode="chat",
            request_text=request_text,
            manager_packet=manager_packet,
            knowledge_hits=knowledge_hits,
            context_notes=context_notes,
            memory_notes=memory_notes,
            profile=resolved_profile,
        )
        execution_trace[3]["detail"] = (
            "Rendered a natural conversational reply."
            if language == "en"
            else "已渲染为自然对话回复。"
        )
        execution_trace[3]["metadata"]["bullet_count"] = 0
        return {
            "kind": "chat_reply",
            "text": text,
            "content": text,
            "bullets": [],
            "references": references,
            "execution_trace": execution_trace,
        }

    def _resolve_planned_agent(
        self,
        step: dict[str, Any],
        *,
        fallback_agent: dict | None,
    ) -> dict | None:
        return (
            _find_agent_by_id(step.get("execution_agent_id") or step.get("executionAgentId"))
            or fallback_agent
        )

    def _build_planned_step_result(
        self,
        *,
        task: dict,
        run: dict,
        step: dict[str, Any],
        execution_agent: dict | None,
    ) -> dict[str, Any]:
        sub_run = dict(run)
        sub_run["intent"] = str(step.get("intent") or run.get("intent") or "").strip()
        return self.build_task_result(task=task, run=sub_run, execution_agent=execution_agent)

    def _orchestration_trace_entries(
        self,
        *,
        language: str,
        execution_plan: dict[str, Any],
        agent_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        coordination_mode = str(execution_plan.get("coordination_mode") or "serial").strip().lower()
        summary = str(execution_plan.get("summary") or "").strip()
        entries: list[dict[str, Any]] = [
            {
                "stage": "dynamic_planning",
                "title": "动态规划" if language != "en" else "Dynamic planning",
                "status": "completed",
                "detail": (
                    f"Master Bot 已生成 {coordination_mode} 多 Agent 编排：{summary}。"
                    if language != "en"
                    else f"Master Bot generated a {coordination_mode} multi-agent plan: {summary}."
                ),
                "metadata": {
                    "coordination_mode": coordination_mode,
                    "planned_agent_count": len(agent_results),
                },
            }
        ]
        for index, agent_result in enumerate(agent_results, start=1):
            step = agent_result["step"]
            result = agent_result.get("result") or {}
            branch_status = str(agent_result.get("status") or "completed").strip() or "completed"
            agent_name = str(step.get("execution_agent") or step.get("agent") or f"Agent {index}").strip()
            if branch_status == "cancelled":
                detail = (
                    f"{agent_name} 分支已提前取消，等待主脑收口。"
                    if language != "en"
                    else f"{agent_name} branch was cancelled early after brain convergence."
                )
            elif branch_status == "failed":
                detail = (
                    f"{agent_name} 未产出合格结果，主脑已记录失败分支。"
                    if language != "en"
                    else f"{agent_name} did not produce an acceptable result; the brain recorded a failed branch."
                )
            else:
                detail = (
                    f"{agent_name} 已完成 {step.get('intent')} 子任务：{result.get('summary')}"
                    if language != "en"
                    else f"{agent_name} completed the {step.get('intent')} subtask: {result.get('summary')}"
                )
            entries.append(
                {
                    "stage": f"planned_agent_{index}",
                    "title": f"{agent_name} 执行" if language != "en" else f"{agent_name} execution",
                    "status": branch_status,
                    "detail": detail,
                    "metadata": {
                        "intent": str(step.get("intent") or ""),
                        "agent": agent_name,
                        "result_kind": str(result.get("kind") or ""),
                        "branch_id": str(step.get("branch_id") or "").strip() or None,
                        "score": int(agent_result.get("score") or 0),
                    },
                }
            )
        entries.append(
            {
                "stage": "result_aggregation",
                "title": "结果聚合" if language != "en" else "Result aggregation",
                "status": "completed",
                "detail": (
                    "Master Bot 已聚合多 Agent 结果并生成最终回复。"
                    if language != "en"
                    else "Master Bot aggregated the multi-agent outputs into the final response."
                ),
                "metadata": {
                    "coordination_mode": coordination_mode,
                    "agent_count": len(agent_results),
                    "successful_agents": sum(
                        1 for item in agent_results if item.get("status") == "completed"
                    ),
                },
            }
        )
        return entries

    def _build_orchestration_steps(
        self,
        *,
        language: str,
        execution_plan: dict[str, Any],
        agent_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        coordination_mode = str(execution_plan.get("coordination_mode") or "serial").strip().lower()
        summary = str(execution_plan.get("summary") or "").strip()
        steps = [
            {
                "title": "动态规划",
                "status": "completed",
                "agent": "Master Bot Planner",
                "message": (
                    f"已生成 {coordination_mode} 多 Agent 计划：{summary}"
                    if language != "en"
                    else f"Built a {coordination_mode} multi-agent plan: {summary}"
                ),
                "tokens": 12,
            }
        ]
        for agent_result in agent_results:
            step = agent_result["step"]
            result = agent_result.get("result") or {}
            agent_name = str(step.get("execution_agent") or step.get("agent") or "Agent").strip()
            branch_status = str(agent_result.get("status") or "completed").strip() or "completed"
            steps.append(
                {
                    "title": f"{agent_name} 协同执行",
                    "status": branch_status,
                    "agent": agent_name,
                    "message": (
                        str(result.get("summary") or "").strip()
                        or (
                            f"{agent_name} 分支已取消"
                            if branch_status == "cancelled"
                            else f"{agent_name} 子任务未产出合格结果"
                            if branch_status == "failed"
                            else f"{agent_name} 已完成子任务"
                        )
                    ),
                    "tokens": 24,
                }
            )
        steps.append(
            {
                "title": "结果聚合",
                "status": "completed",
                "agent": "Master Bot Planner",
                "message": "已聚合多 Agent 结果并生成统一回复"
                if language != "en"
                else "Aggregated the multi-agent results into one final response",
                "tokens": 12,
            }
        )
        return steps

    def _aggregate_planned_results(
        self,
        *,
        task: dict,
        run: dict,
        execution_plan: dict[str, Any],
        agent_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        language = _output_language(task)
        coordination_mode = str(execution_plan.get("coordination_mode") or "serial").strip().lower()
        selected_agent_result = self._select_multi_agent_result(
            execution_plan=execution_plan,
            agent_results=agent_results,
        )
        final_result = store.clone(selected_agent_result.get("result") or {})
        successful_results = [item for item in agent_results if item.get("status") == "completed"]
        executed_results = [
            item for item in agent_results if isinstance(item.get("result"), dict)
        ]
        merge_strategy = str(
            execution_plan.get("merge_strategy") or execution_plan.get("mergeStrategy") or "append_bullets_and_references"
        ).strip().lower() or "append_bullets_and_references"
        orchestration_trace = self._orchestration_trace_entries(
            language=language,
            execution_plan=execution_plan,
            agent_results=agent_results,
        )
        orchestration_steps = self._build_orchestration_steps(
            language=language,
            execution_plan=execution_plan,
            agent_results=agent_results,
        )
        references = _combined_references([item["result"] for item in executed_results])
        bullets = [str(item).strip() for item in final_result.get("bullets") or [] if str(item).strip()]
        if merge_strategy == "append_bullets_and_references":
            for item in successful_results:
                if item is selected_agent_result:
                    continue
                for bullet in item.get("result", {}).get("bullets") or []:
                    normalized_bullet = str(bullet).strip()
                    if normalized_bullet and normalized_bullet not in bullets:
                        bullets.append(normalized_bullet)
        if str(final_result.get("kind") or "").strip().lower() != "chat_reply":
            synthesis_note = (
                "已综合多轮分析结果，生成统一回复。"
                if language != "en"
                else "Combined multiple intermediate analyses into one final response."
            )
            if synthesis_note not in bullets:
                bullets.insert(0, synthesis_note)
        if coordination_mode == "race" and selected_agent_result:
            winner_agent = str(
                (selected_agent_result.get("step") or {}).get("execution_agent")
                or (selected_agent_result.get("step") or {}).get("agent")
                or "Agent"
            ).strip()
            winner_note = (
                f"本轮采用竞速收敛，winner={winner_agent}。"
                if language != "en"
                else f"Race convergence selected winner={winner_agent}."
            )
            if winner_note not in bullets:
                bullets.insert(0, winner_note)

        final_result["content"] = str(final_result.get("content") or "").rstrip()
        final_result["bullets"] = bullets
        final_result["references"] = references
        final_result["execution_trace"] = [
            *orchestration_trace,
            *[
                entry
                for entry in final_result.get("execution_trace") or []
                if isinstance(entry, dict)
            ],
        ]
        final_result["orchestration_steps"] = orchestration_steps
        final_result["aggregation_notes"] = {
            "coordination_mode": coordination_mode,
            "selected_branch_id": str(
                (selected_agent_result.get("step") or {}).get("branch_id") or ""
            ).strip()
            or None,
            "selected_agent": str(
                (selected_agent_result.get("step") or {}).get("execution_agent")
                or (selected_agent_result.get("step") or {}).get("agent")
                or ""
            ).strip()
            or None,
            "successful_agents": len(successful_results),
            "failed_agents": sum(1 for item in agent_results if item.get("status") == "failed"),
        }
        return self._attach_execution_contracts(
            task=task,
            run=run,
            execution_agent=None,
            result=final_result,
            execution_plan=execution_plan,
            fallback_contract=self._fallback_contract(
                task=task,
                run=run,
                stage="multi_agent_orchestration",
                activated=False,
                resolution="planner_completed",
                detail=str(execution_plan.get("summary") or "").strip() or None,
                metadata={
                    "coordination_mode": coordination_mode,
                    "completed_agents": len(successful_results),
                },
            ),
            aggregation_contract=self._aggregation_contract(
                execution_plan=execution_plan,
                agent_results=agent_results,
            ),
        )

    def _execute_multi_agent(
        self,
        *,
        task: dict,
        run: dict,
        execution_agent: dict | None,
        execution_plan: dict[str, Any],
    ) -> dict[str, Any]:
        coordination_mode = str(execution_plan.get("coordination_mode") or "serial").strip().lower()
        steps = execution_plan.get("steps") or []
        cancel_policy = execution_plan.get("cancel_policy") or execution_plan.get("cancelPolicy") or {}
        if not isinstance(cancel_policy, dict):
            cancel_policy = {}
        quorum_min_success = self._resolve_quorum_min_success(execution_plan, len(steps))
        planned_steps = [(index, step) for index, step in enumerate(steps) if isinstance(step, dict)]
        agent_results: list[dict[str, Any]] = []

        if coordination_mode == "serial":
            working_task = dict(task)
            success_count = 0
            stop_dispatch = False
            for index, step in planned_steps:
                if stop_dispatch:
                    agent_results.append(
                        {
                            "step": step,
                            "result": None,
                            "status": "cancelled",
                            "score": 0,
                        }
                    )
                    continue
                planned_agent = self._resolve_planned_agent(step, fallback_agent=execution_agent)
                step_result = self._build_planned_step_result(
                    task=working_task,
                    run=run,
                    step=step,
                    execution_agent=planned_agent,
                )
                is_acceptable = self._result_is_acceptable(step_result)
                branch_status = "completed" if is_acceptable else "failed"
                agent_results.append(
                    {
                        "step": step,
                        "result": step_result,
                        "status": branch_status,
                        "score": self._result_quality_score(step_result),
                    }
                )
                if is_acceptable:
                    success_count += 1
                if index < len(planned_steps) - 1:
                    working_task = _task_with_added_context(
                        working_task,
                        f"补充上下文: 上一子任务摘要：{step_result.get('summary')}",
                        *[
                            f"补充上下文: {bullet}"
                            for bullet in (step_result.get("bullets") or [])[:2]
                        ],
                    )
                if coordination_mode == "race" and is_acceptable:
                    stop_dispatch = bool(cancel_policy.get("cancel_remaining_on_winner", True))
                if coordination_mode == "quorum" and success_count >= quorum_min_success:
                    stop_dispatch = bool(cancel_policy.get("cancel_remaining_on_quorum", True))
        else:
            result_by_index: dict[int, dict[str, Any]] = {}
            ignored_indexes: set[int] = set()
            success_count = 0
            max_workers = max(1, min(len(planned_steps), 4))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_map = {
                    executor.submit(
                        self._build_planned_step_result,
                        task=dict(task),
                        run=run,
                        step=step,
                        execution_agent=self._resolve_planned_agent(step, fallback_agent=execution_agent),
                    ): (index, step)
                    for index, step in planned_steps
                }
                for future in as_completed(future_map):
                    index, step = future_map[future]
                    if index in ignored_indexes:
                        result_by_index[index] = {
                            "step": step,
                            "result": None,
                            "status": "cancelled",
                            "score": 0,
                        }
                        continue
                    try:
                        step_result = future.result()
                    except Exception as exc:  # pragma: no cover - defensive path
                        step_result = {
                            "kind": None,
                            "summary": str(exc),
                            "content": str(exc),
                            "bullets": [],
                            "references": [],
                        }
                    is_acceptable = self._result_is_acceptable(step_result)
                    branch_status = "completed" if is_acceptable else "failed"
                    result_by_index[index] = {
                        "step": step,
                        "result": step_result,
                        "status": branch_status,
                        "score": self._result_quality_score(step_result),
                    }
                    if is_acceptable:
                        success_count += 1
                    should_cancel_remaining = False
                    if coordination_mode == "race" and is_acceptable:
                        should_cancel_remaining = bool(
                            cancel_policy.get("cancel_remaining_on_winner", True)
                        )
                    elif coordination_mode == "quorum" and success_count >= quorum_min_success:
                        should_cancel_remaining = bool(
                            cancel_policy.get("cancel_remaining_on_quorum", True)
                        )
                    if should_cancel_remaining:
                        for pending_future, pending_meta in future_map.items():
                            pending_index, pending_step = pending_meta
                            if pending_future is future or pending_index in result_by_index:
                                continue
                            ignored_indexes.add(pending_index)
                            pending_future.cancel()
                            result_by_index.setdefault(
                                pending_index,
                                {
                                    "step": pending_step,
                                    "result": None,
                                    "status": "cancelled",
                                    "score": 0,
                                },
                            )
            agent_results = [result_by_index[index] for index, _step in planned_steps if index in result_by_index]
        if not agent_results:
            return self.build_task_result(task=task, run=run, execution_agent=execution_agent)
        return self._aggregate_planned_results(
            task=task,
            run=run,
            execution_plan=execution_plan,
            agent_results=agent_results,
        )

    def _execute_free_workflow(
        self,
        *,
        task: dict,
        run: dict,
        execution_agent: dict | None,
    ) -> dict[str, Any]:
        capabilities = _resolve_required_capabilities(task, run)
        payload = _free_workflow_payload(task, run)
        request_text = _primary_request_text(task)
        trace_context = {
            "task_id": str(task.get("id") or ""),
            "run_id": str(run.get("id") or ""),
            "workflow_mode": "free_workflow",
        }
        try:
            from app.services.free_workflow_service import free_workflow_service

            result = free_workflow_service.run(
                text=request_text,
                required_capabilities=capabilities,
                payload=payload,
                context=trace_context,
            )
        except Exception as exc:
            return self._attach_execution_contracts(
                task=task,
                run=run,
                execution_agent=execution_agent,
                result={
                    "kind": "help_note",
                    "title": "自由工作流执行失败",
                    "summary": "自由工作流技能执行失败",
                    "content": f"自由工作流已命中，但执行失败：{exc}",
                    "bullets": [
                        "路由层已正确识别为自由工作流。",
                        "当前失败已被统一收敛到 Free Workflow 异常语义。",
                    ],
                    "references": [],
                    "execution_trace": [
                        {
                            "stage": "free_workflow_runtime",
                            "title": "自由工作流运行时",
                            "status": "failed",
                            "detail": str(exc),
                            "metadata": {"required_capabilities": capabilities},
                        }
                    ],
                },
                fallback_contract=self._fallback_contract(
                    task=task,
                    run=run,
                    stage="free_workflow_runtime",
                    activated=True,
                    resolution="terminal_failure",
                    detail=str(exc),
                    metadata={"required_capabilities": capabilities},
                ),
            )

        selected_skill = str(result.get("selected_skill") or "unknown_skill")
        if not bool(result.get("ok", False)):
            error_message = str((result.get("error") or {}).get("message") or "free_workflow_failed")
            return self._attach_execution_contracts(
                task=task,
                run=run,
                execution_agent=execution_agent,
                result={
                    "kind": "help_note",
                    "title": "自由工作流执行失败",
                    "summary": "自由工作流技能执行失败",
                    "content": f"自由工作流已命中，但技能执行失败：{error_message}",
                    "bullets": [
                        f"selected_skill: {selected_skill}",
                        "路由层已正确识别为自由工作流。",
                    ],
                    "references": [],
                    "execution_trace": [
                        {
                            "stage": "free_workflow_runtime",
                            "title": "自由工作流运行时",
                            "status": "failed",
                            "detail": error_message,
                            "metadata": {
                                "required_capabilities": capabilities,
                                "selected_skill": selected_skill,
                            },
                        }
                    ],
                },
                fallback_contract=self._fallback_contract(
                    task=task,
                    run=run,
                    stage="free_workflow_runtime",
                    activated=True,
                    resolution="skill_failure",
                    detail=error_message,
                    metadata={
                        "required_capabilities": capabilities,
                        "selected_skill": selected_skill,
                    },
                ),
            )

        execution_trace = [
            {
                "stage": "free_workflow_runtime",
                "title": "自由工作流运行时",
                "status": "completed",
                "detail": f"已调用 {selected_skill} 处理自由工作流请求。",
                "metadata": {
                    "skill_id": selected_skill,
                    "required_capabilities": capabilities,
                },
            },
            *[
                entry
                for entry in result.get("execution_trace") or []
                if isinstance(entry, dict)
            ],
        ]
        wrapped_result = store.clone(result.get("wrapped_result") or {})
        wrapped_result.setdefault(
            "kind",
            {
                "web_search_skill": "search_report",
                "general_writer_skill": "draft_message",
                "speech_writer_skill": "draft_message",
            }.get(selected_skill, "help_note"),
        )
        wrapped_result.setdefault("title", selected_skill or "自由工作流结果")
        wrapped_result.setdefault("summary", str(result.get("result_summary") or "自由工作流已执行"))
        wrapped_result.setdefault("content", str(result.get("result_summary") or "自由工作流已执行"))
        wrapped_result.setdefault("bullets", [])
        wrapped_result.setdefault("references", [])
        wrapped_result["execution_trace"] = execution_trace
        migration_runtime = result.get("migration_runtime")
        if isinstance(migration_runtime, dict):
            wrapped_result["bullets"] = [
                *wrapped_result.get("bullets", []),
                f"runtime mode: {migration_runtime.get('mode') or 'builtin_primary'}",
            ]
        return self._attach_execution_contracts(
            task=task,
            run=run,
            execution_agent=execution_agent,
            result=wrapped_result,
            fallback_contract=self._fallback_contract(
                task=task,
                run=run,
                stage="free_workflow_runtime",
                activated=str((migration_runtime or {}).get("selected_path") or "runtime") != "runtime",
                resolution=(
                    "runtime_completed"
                    if str((migration_runtime or {}).get("selected_path") or "runtime") == "runtime"
                    else "degraded_runtime_path"
                ),
                detail=str(result.get("result_summary") or "").strip() or None,
                metadata={
                    "selected_skill": selected_skill,
                    "migration_runtime": store.clone(migration_runtime or {}),
                    "required_capabilities": capabilities,
                },
            ),
        )

    def _execute_professional_workflow(
        self,
        *,
        task: dict,
        run: dict,
        execution_agent: dict | None,
    ) -> dict[str, Any]:
        result = professional_workflow_service.execute(task=task, run=run, execution_agent=execution_agent)
        result["execution_trace"] = [
            {
                "stage": "professional_workflow_runtime",
                "title": "专业工作流运行时",
                "status": "completed",
                "detail": "已进入专业工作流准入与角色拆解。",
                "metadata": {
                    "required_capabilities": _resolve_required_capabilities(task, run),
                    "requires_permission": _resolve_requires_permission(task, run),
                },
            },
            *[
                entry
                for entry in result.get("execution_trace") or []
                if isinstance(entry, dict)
            ],
        ]
        execution_result = result.get("structured_data", {}).get("execution_result", {})
        if not isinstance(execution_result, dict):
            execution_result = {}
        return self._attach_execution_contracts(
            task=task,
            run=run,
            execution_agent=execution_agent,
            result=result,
            fallback_contract=self._fallback_contract(
                task=task,
                run=run,
                stage="professional_workflow_runtime",
                activated=not bool(execution_result.get("ok", False)),
                resolution=(
                    "connector_execution"
                    if bool(execution_result.get("ok", False))
                    else "professional_runtime_failed"
                ),
                detail=str(execution_result.get("status") or result.get("summary") or "").strip() or None,
                metadata={
                    "required_capabilities": _resolve_required_capabilities(task, run),
                    "requires_permission": _resolve_requires_permission(task, run),
                    "selected_runtime_tool_id": execution_result.get("selected_runtime_tool_id"),
                },
            ),
        )

    def execute_task(
        self,
        *,
        task: dict,
        run: dict,
        execution_agent: dict | None,
    ) -> dict:
        effective_task = _task_with_added_context(task, *_selected_workflow_node_guidance(run))
        execution_plan = _planned_execution(run)
        if execution_plan is not None:
            return self._execute_multi_agent(
                task=effective_task,
                run=run,
                execution_agent=execution_agent,
                execution_plan=execution_plan,
            )
        workflow_mode = _resolve_workflow_mode(effective_task, run)
        if workflow_mode == "free_workflow" and _should_use_free_workflow_runtime(effective_task, run):
            return self._execute_free_workflow(
                task=effective_task,
                run=run,
                execution_agent=execution_agent,
            )
        if workflow_mode == "professional_workflow":
            return self._execute_professional_workflow(
                task=effective_task,
                run=run,
                execution_agent=execution_agent,
            )
        profile = _safe_execution_profile(execution_agent, run)
        execution_mode = _resolve_execution_mode(effective_task, execution_agent, run, profile)
        if execution_mode == "chat":
            return self._attach_execution_contracts(
                task=effective_task,
                run=run,
                execution_agent=execution_agent,
                result=self._execute_chat(task=effective_task, run=run, execution_agent=execution_agent),
            )
        if execution_mode == "search":
            return self._attach_execution_contracts(
                task=effective_task,
                run=run,
                execution_agent=execution_agent,
                result=self._execute_search(task=effective_task, run=run, execution_agent=execution_agent),
            )
        if execution_mode == "write":
            return self._attach_execution_contracts(
                task=effective_task,
                run=run,
                execution_agent=execution_agent,
                result=self._execute_write(task=effective_task, run=run, execution_agent=execution_agent),
            )
        if execution_mode == "help":
            return self._attach_execution_contracts(
                task=effective_task,
                run=run,
                execution_agent=execution_agent,
                result=self._execute_help(task=effective_task, run=run, execution_agent=execution_agent),
            )
        return self._attach_execution_contracts(
            task=effective_task,
            run=run,
            execution_agent=execution_agent,
            result=self._execute_default(task=effective_task, run=run, execution_agent=execution_agent),
        )

    def build_search_result(
        self,
        *,
        task: dict,
        run: dict,
        execution_agent: dict | None = None,
        profile: dict[str, Any] | None = None,
    ) -> dict:
        resolved_profile = profile or _safe_execution_profile(execution_agent, run)
        language = _output_language(task)
        request_text = _primary_request_text(task)
        manager_packet = _resolve_manager_packet(task, run) or {}
        decomposition_hint = str(manager_packet.get("decomposition_hint") or "").strip()
        delivery_mode = str(manager_packet.get("delivery_mode") or "").strip()
        context_notes = _context_notes(task)
        memory_notes = _memory_notes(task)
        knowledge_hits = _knowledge_hits(task, str(run.get("intent") or "search").lower())
        provider_result = self._try_provider_result(
            task=task,
            run=run,
            execution_agent=execution_agent,
            profile=resolved_profile,
            mode="search",
            knowledge_hits=knowledge_hits,
            context_notes=context_notes,
            memory_notes=memory_notes,
        )
        if provider_result is not None:
            return provider_result
        bullets = [
            (
                f"Retrieved {len(knowledge_hits)} relevant project references for \"{_truncate_text(request_text, 24)}\"."
                if language == "en"
                else f"已围绕「{_truncate_text(request_text, 24)}」检索到当前项目目录中的 {len(knowledge_hits)} 条相关资料。"
            ),
            *(
                [
                    f"Matched {_knowledge_label(hit)}: {hit['excerpt']}"
                    for hit in knowledge_hits[:2]
                ]
                if language == "en"
                else [
                    f"命中 {_knowledge_label(hit)}：{hit['excerpt']}"
                    for hit in knowledge_hits[:2]
                ]
            ),
        ]
        if decomposition_hint:
            bullets.insert(
                1,
                (
                    f"Execution plan hint: {decomposition_hint}."
                    if language == "en"
                    else f"项目经理拆解提示：{decomposition_hint}。"
                ),
            )
        bullets.append(
            "If you need a deeper pass, follow the collaboration view logs and rerun with extra context."
            if language == "en"
            else "如需继续深挖，可结合协作页日志继续补充上下文后重新执行。"
        )
        if context_notes:
            bullets.append(
                f"Absorbed extra context: {_truncate_text(context_notes[-1], 28)}."
                if language == "en"
                else f"已吸收补充要求：{_truncate_text(context_notes[-1], 28)}。"
            )
        if memory_notes:
            bullets.append(
                f"Applied memory context: {_truncate_text(memory_notes[0], 28)}."
                if language == "en"
                else f"已结合历史记忆：{_truncate_text(memory_notes[0], 28)}。"
            )
        bullets.extend(_execution_profile_bullets(resolved_profile, language=language))

        content_lines = [
            f"Search target: {request_text}" if language == "en" else f"检索目标：{request_text}",
            "",
            (
                f"Delivery mode: {delivery_mode or 'structured_result'}"
                if language == "en"
                else f"交付模式：{delivery_mode or 'structured_result'}"
            ),
            (
                f"Decomposition hint: {decomposition_hint or 'direct_execute'}"
                if language == "en"
                else f"拆解提示：{decomposition_hint or 'direct_execute'}"
            ),
            "",
            "Matched local project materials:" if language == "en" else "命中的本地项目资料：",
        ]
        for index, hit in enumerate(knowledge_hits, start=1):
            content_lines.append(f"{index}. {_knowledge_label(hit)}")
            content_lines.append(
                f"   Summary: {hit['excerpt']}" if language == "en" else f"   摘要：{hit['excerpt']}"
            )
            if hit.get("matched_terms"):
                content_lines.append(
                    f"   Keywords: {', '.join(hit['matched_terms'][:4])}"
                    if language == "en"
                    else f"   关键词：{', '.join(hit['matched_terms'][:4])}"
                )
        content_lines.extend(
            [
                "",
                "Next steps:" if language == "en" else "建议下一步：",
                "1. Verify the matched sections for the entry path, configuration and trigger pattern."
                if language == "en"
                else "1. 先核对命中章节里的入口路径、配置项和触发方式。",
                "2. If the issue remains, compare the workflow logs against those excerpts to narrow the fault layer."
                if language == "en"
                else "2. 若问题仍未定位，可把工作流日志和这些摘录逐项对照，缩小故障层级。",
                "3. If you need an SOP, convert the referenced sections directly into workflow notes or an operations checklist."
                if language == "en"
                else "3. 如果要沉淀成 SOP，可以把这些章节直接整理成工作流说明或运维检查清单。",
            ]
        )
        execution_trace = _execution_trace_entries(
            language=language,
            mode="search",
            request_text=request_text,
            manager_packet=manager_packet,
            knowledge_hits=knowledge_hits,
            context_notes=context_notes,
            memory_notes=memory_notes,
            profile=resolved_profile,
        )
        execution_trace[3]["metadata"]["bullet_count"] = len(bullets)
        return {
            "kind": "search_report",
            "title": (
                f"Search Summary - {_truncate_text(request_text, 16)}"
                if language == "en"
                else f"检索摘要 - {_truncate_text(request_text, 16)}"
            ),
            "summary": (
                f"Generated a grounded search summary for \"{_truncate_text(request_text, 18)}\" from local project materials"
                if language == "en"
                else f"已基于本地开发文档生成关于「{_truncate_text(request_text, 18)}」的检索结论"
            ),
            "content": "\n".join(content_lines),
            "bullets": bullets,
            "references": _knowledge_references(knowledge_hits, language=language),
            "execution_trace": execution_trace,
        }

    def build_write_result(
        self,
        *,
        task: dict,
        run: dict,
        execution_agent: dict | None = None,
        profile: dict[str, Any] | None = None,
    ) -> dict:
        resolved_profile = profile or _safe_execution_profile(execution_agent, run)
        language = _output_language(task)
        request_text = _primary_request_text(task)
        manager_packet = _resolve_manager_packet(task, run) or {}
        decomposition_hint = str(manager_packet.get("decomposition_hint") or "").strip()
        delivery_mode = str(manager_packet.get("delivery_mode") or "").strip()
        context_notes = _context_notes(task)
        memory_notes = _memory_notes(task)
        knowledge_hits = _knowledge_hits(task, str(run.get("intent") or "write").lower())
        provider_result = self._try_provider_result(
            task=task,
            run=run,
            execution_agent=execution_agent,
            profile=resolved_profile,
            mode="write",
            knowledge_hits=knowledge_hits,
            context_notes=context_notes,
            memory_notes=memory_notes,
        )
        if provider_result is not None:
            return provider_result
        tone_hint = (
            context_notes[-1]
            if context_notes
            else ("keep it professional, clear, and ready to send" if language == "en" else "保持专业、清晰、可直接发送")
        )
        content_lines = [
            "Hello," if language == "en" else "您好，",
            "",
            (
                f"[delivery_mode={delivery_mode or 'structured_result'}; decomposition_hint={decomposition_hint or 'direct_execute'}]"
                if language == "en"
                else f"[交付模式={delivery_mode or 'structured_result'}；拆解提示={decomposition_hint or 'direct_execute'}]"
            ),
            "",
            (
                f"For \"{request_text}\", we prepared a grounded draft based on the local project guide and architecture materials in this workspace."
                if language == "en"
                else f"关于「{request_text}」，我们结合当前项目目录中的开发指南与架构资料整理了一版可直接使用的回复草稿。"
            ),
            "",
            "Primary references used in this draft:" if language == "en" else "本次写作主要参考：",
            *[
                (
                    f"- {_knowledge_label(hit)}: {hit['excerpt']}"
                    if language == "en"
                    else f"- {_knowledge_label(hit)}：{hit['excerpt']}"
                )
                for hit in knowledge_hits
            ],
        ]
        if memory_notes:
            content_lines.extend(
                [
                    "",
                    "Memory hints:" if language == "en" else "历史记忆提示：",
                    *[f"- {note}" for note in memory_notes[:2]],
                ]
            )
        content_lines.extend(
            [
                "",
                "Suggested wording:" if language == "en" else "建议表述如下：",
                (
                    "1. WorkBot is structured around a unified intake layer, security gateway, Master Bot dispatch, agent collaboration, and visual workflow operations."
                    if language == "en"
                    else "1. WorkBot 当前方案以统一接入层、安全网关、Master Bot 调度、Agent 协作和可视化工作流为主链路。"
                ),
                (
                    "2. The current stage already provides a runnable admin console and workflow linkage, while deeper infrastructure is still being completed along the MVP roadmap."
                    if language == "en"
                    else "2. 当前阶段已经具备可运行的后台与工作流联调能力，但底层仍以 MVP 路线逐步补齐真实基础设施与执行引擎。"
                ),
                (
                    f"3. The tone has been aligned with the instruction to \"{tone_hint}\", and the draft is ready for direct use or further refinement."
                    if language == "en"
                    else f"3. 语气和措辞已按“{tone_hint}”处理，可直接发送或继续润色。"
                ),
                "",
                (
                    "If needed, I can also rewrite this into a more formal email, announcement, or weekly project update."
                    if language == "en"
                    else "如果您愿意，我也可以继续把这份内容改成更正式的邮件版、公告版或项目周报版。"
                ),
                "",
                "Regards," if language == "en" else "此致",
                "WorkBot",
            ]
        )
        bullets = [
            (
                "The output has been organized as a deliverable draft based on the current task context."
                if language == "en"
                else "输出内容已按当前任务上下文整理成可直接交付的文稿。"
            ),
            (
                f"The draft is grounded in {len(knowledge_hits)} local project references."
                if language == "en"
                else f"当前草稿已结合 {len(knowledge_hits)} 条本地资料线索做 grounding。"
            ),
            *[
                (
                    f"Referenced {_knowledge_label(hit)} as writing support."
                    if language == "en"
                    else f"已引用 {_knowledge_label(hit)} 作为写作依据。"
                )
                for hit in knowledge_hits[:2]
            ],
            (
                "If tone, audience, or format changes later, you can continue refining it through context patch."
                if language == "en"
                else "如果后续还有语气、篇幅、对象变化，可以继续通过 context patch 追加要求。"
            ),
        ]
        if decomposition_hint:
            bullets.insert(
                1,
                (
                    f"Execution hint: {decomposition_hint}."
                    if language == "en"
                    else f"项目经理拆解提示：{decomposition_hint}。"
                ),
            )
        bullets.extend(_execution_profile_bullets(resolved_profile, language=language))
        execution_trace = _execution_trace_entries(
            language=language,
            mode="write",
            request_text=request_text,
            manager_packet=manager_packet,
            knowledge_hits=knowledge_hits,
            context_notes=context_notes,
            memory_notes=memory_notes,
            profile=resolved_profile,
        )
        execution_trace[3]["metadata"]["bullet_count"] = len(bullets)
        return {
            "kind": "draft_message",
            "title": (
                f"Draft Message - {_truncate_text(request_text, 16)}"
                if language == "en"
                else f"写作草稿 - {_truncate_text(request_text, 16)}"
            ),
            "summary": (
                f"Generated a grounded English draft for \"{_truncate_text(request_text, 18)}\""
                if language == "en"
                else f"已结合本地项目资料生成一版围绕「{_truncate_text(request_text, 18)}」的文本草稿"
            ),
            "content": "\n".join(content_lines),
            "bullets": bullets,
            "references": _knowledge_references(knowledge_hits, language=language),
            "execution_trace": execution_trace,
        }

    def build_help_result(
        self,
        *,
        task: dict,
        run: dict,
        execution_agent: dict | None = None,
        profile: dict[str, Any] | None = None,
    ) -> dict:
        resolved_profile = profile or _safe_execution_profile(execution_agent, run)
        language = _output_language(task)
        request_text = _primary_request_text(task)
        manager_packet = _resolve_manager_packet(task, run) or {}
        decomposition_hint = str(manager_packet.get("decomposition_hint") or "").strip()
        delivery_mode = str(manager_packet.get("delivery_mode") or "").strip()
        memory_notes = _memory_notes(task)
        knowledge_hits = _knowledge_hits(task, str(run.get("intent") or "help").lower())
        provider_result = self._try_provider_result(
            task=task,
            run=run,
            execution_agent=execution_agent,
            profile=resolved_profile,
            mode="help",
            knowledge_hits=knowledge_hits,
            context_notes=[],
            memory_notes=memory_notes,
        )
        if provider_result is not None:
            return provider_result
        content_lines = [
            f"Topic: {request_text}" if language == "en" else f"问题主题：{request_text}",
            "",
            (
                f"Delivery mode: {delivery_mode or 'structured_result'}"
                if language == "en"
                else f"交付模式：{delivery_mode or 'structured_result'}"
            ),
            (
                f"Decomposition hint: {decomposition_hint or 'direct_execute'}"
                if language == "en"
                else f"拆解提示：{decomposition_hint or 'direct_execute'}"
            ),
            "",
            "Primary references:" if language == "en" else "优先参考资料：",
            *[
                (
                    f"- {_knowledge_label(hit)}: {hit['excerpt']}"
                    if language == "en"
                    else f"- {_knowledge_label(hit)}：{hit['excerpt']}"
                )
                for hit in knowledge_hits
            ],
        ]
        if memory_notes:
            content_lines.extend(
                [
                    "",
                    "Memory hints:" if language == "en" else "历史记忆线索：",
                    *[f"- {note}" for note in memory_notes[:2]],
                ]
            )
        content_lines.extend(
            [
                "",
                "Suggested response:" if language == "en" else "建议回复：",
                (
                    "1. Start by verifying the matched sections for the current step, trigger style, and configuration."
                    if language == "en"
                    else "1. 先按命中的章节确认当前所处步骤、触发方式和配置项。"
                ),
                (
                    "2. Then combine permission, security, or workflow logs to identify which layer is failing."
                    if language == "en"
                    else "2. 再结合权限、安全或工作流日志判断问题发生在哪一层。"
                ),
                (
                    "3. If the issue is still unresolved, move to the collaboration view and continue tracing with extra context."
                    if language == "en"
                    else "3. 如仍无法解决，可转入协作视图继续追踪节点状态并追加上下文。"
                ),
            ]
        )
        bullets = [
            (
                "This is a guidance-style result that can be reused as a FAQ or support response."
                if language == "en"
                else "这是一份偏说明型的帮助结果，适合继续转成 FAQ 或运营回复。"
            ),
            (
                f"Execution hint: {decomposition_hint}."
                if language == "en"
                else f"项目经理拆解提示：{decomposition_hint}。"
            ) if decomposition_hint else (
                "Execution hint: direct_execute."
                if language == "en"
                else "项目经理拆解提示：direct_execute。"
            ),
            *[
                (
                    f"Referenced {_knowledge_label(hit)}."
                    if language == "en"
                    else f"已参考 {_knowledge_label(hit)}。"
                )
                for hit in knowledge_hits[:2]
            ],
            (
                "If the user provides more detail, the same task context can continue absorbing it."
                if language == "en"
                else "如果用户再次补充信息，可以直接继续合并到当前任务上下文。"
            ),
        ]
        bullets.extend(_execution_profile_bullets(resolved_profile, language=language))
        execution_trace = _execution_trace_entries(
            language=language,
            mode="help",
            request_text=request_text,
            manager_packet=manager_packet,
            knowledge_hits=knowledge_hits,
            context_notes=[],
            memory_notes=memory_notes,
            profile=resolved_profile,
        )
        execution_trace[3]["metadata"]["bullet_count"] = len(bullets)
        return {
            "kind": "help_note",
            "title": (
                f"Help Note - {_truncate_text(request_text, 16)}"
                if language == "en"
                else f"帮助说明 - {_truncate_text(request_text, 16)}"
            ),
            "summary": (
                "Generated an English guidance note grounded in local project materials"
                if language == "en"
                else "已结合本地项目资料生成一份可直接回复用户的帮助说明"
            ),
            "content": "\n".join(content_lines),
            "bullets": bullets,
            "references": _knowledge_references(knowledge_hits, language=language),
            "execution_trace": execution_trace,
        }

    def build_task_result(
        self,
        *,
        task: dict,
        run: dict,
        execution_agent: dict | None = None,
        profile: dict[str, Any] | None = None,
    ) -> dict:
        execution_mode = _resolve_execution_mode(task, execution_agent, run, profile)
        if execution_mode == "chat":
            return self.build_chat_result(task=task, run=run, execution_agent=execution_agent, profile=profile)
        if execution_mode == "search":
            return self.build_search_result(task=task, run=run, execution_agent=execution_agent, profile=profile)
        if execution_mode == "write":
            return self.build_write_result(task=task, run=run, execution_agent=execution_agent, profile=profile)
        return self.build_help_result(task=task, run=run, execution_agent=execution_agent, profile=profile)

    def _execute_chat(
        self,
        *,
        task: dict,
        run: dict,
        execution_agent: dict | None,
    ) -> dict:
        return self.build_chat_result(task=task, run=run, execution_agent=execution_agent)

    def _execute_search(
        self,
        *,
        task: dict,
        run: dict,
        execution_agent: dict | None,
    ) -> dict:
        return self.build_search_result(task=task, run=run, execution_agent=execution_agent)

    def _execute_write(
        self,
        *,
        task: dict,
        run: dict,
        execution_agent: dict | None,
    ) -> dict:
        return self.build_write_result(task=task, run=run, execution_agent=execution_agent)

    def _execute_help(
        self,
        *,
        task: dict,
        run: dict,
        execution_agent: dict | None,
    ) -> dict:
        return self.build_help_result(task=task, run=run, execution_agent=execution_agent)

    def _execute_default(
        self,
        *,
        task: dict,
        run: dict,
        execution_agent: dict | None,
    ) -> dict:
        return self.build_task_result(task=task, run=run, execution_agent=execution_agent)


agent_execution_service = AgentExecutionService()
