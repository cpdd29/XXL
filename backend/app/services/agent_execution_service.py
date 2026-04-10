from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from app.services.agent_config_service import agent_config_service, build_agent_config_summary
from app.services.document_search_service import document_search_service
from app.services.language_service import detect_language
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
    dispatch_context = run.get("dispatch_context")
    if not isinstance(dispatch_context, dict):
        return None
    for key in ("execution_plan", "executionPlan"):
        candidate = dispatch_context.get(key)
        if isinstance(candidate, dict):
            steps = candidate.get("steps")
            if isinstance(steps, list) and len(steps) > 1:
                return candidate
    route_decision = dispatch_context.get("route_decision") or dispatch_context.get("routeDecision")
    if isinstance(route_decision, dict):
        candidate = route_decision.get("execution_plan") or route_decision.get("executionPlan")
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
    if normalized in {"chat", "conversation", "dialog", "dialogue"}:
        return "chat"
    if normalized in {
        "task",
        "workflow",
        "workflow_or_direct",
        "workflow_or_direct_agent",
        "workflow_or_direct_agent_fallback",
        "direct_agent",
        "direct",
    }:
        return "task"
    return None


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
    dispatch_context = run.get("dispatch_context")
    if isinstance(dispatch_context, dict):
        payload_candidates.append(dispatch_context)
        route_decision = dispatch_context.get("route_decision") or dispatch_context.get("routeDecision")
        if isinstance(route_decision, dict):
            payload_candidates.append(route_decision)

    task_route_decision = task.get("route_decision") or task.get("routeDecision")
    if isinstance(task_route_decision, dict):
        payload_candidates.append(task_route_decision)

    for payload in payload_candidates:
        mode = _normalize_interaction_mode(
            payload.get("interaction_mode") or payload.get("interactionMode")
        )
        if mode:
            return mode
    return None


def _resolve_reception_mode(task: dict, run: dict) -> str | None:
    payload_candidates: list[dict[str, Any]] = []
    dispatch_context = run.get("dispatch_context")
    if isinstance(dispatch_context, dict):
        payload_candidates.append(dispatch_context)
        route_decision = dispatch_context.get("route_decision") or dispatch_context.get("routeDecision")
        if isinstance(route_decision, dict):
            payload_candidates.append(route_decision)

    task_route_decision = task.get("route_decision") or task.get("routeDecision")
    if isinstance(task_route_decision, dict):
        payload_candidates.append(task_route_decision)

    for payload in payload_candidates:
        mode = _normalize_reception_mode(
            payload.get("reception_mode") or payload.get("receptionMode")
        )
        if mode:
            return mode
    return None


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
    agent_doc = snapshot.get("agent") if isinstance(snapshot, dict) and isinstance(snapshot.get("agent"), dict) else {}
    explicit_provider = str(
        agent_doc.get("provider") or (execution_agent or {}).get("provider") or ""
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
    return str(provider.get("model") or profile.get("model") or "").strip()


def _provider_prompt(
    *,
    mode: str,
    language: str,
    request_text: str,
    reception_mode: str | None,
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
    execution_settings = agent_doc.get("execution") if isinstance(agent_doc.get("execution"), dict) else {}
    supported_intents = [item.lower() for item in _string_list(agent_doc.get("trigger_intents"))]
    capabilities = [item.lower() for item in _string_list(agent_doc.get("capabilities"))]
    warnings = _string_list((snapshot or {}).get("warnings"))
    if warning:
        warnings.append(warning)

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
        "model": str(agent_doc.get("model") or "").strip() or None,
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
    agent_type = str((execution_agent or {}).get("type") or "").strip().lower()
    intent = str(run.get("intent") or "").strip().lower()
    interaction_mode = _resolve_interaction_mode(runtime_task, run)
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
            knowledge_hits=knowledge_hits,
            context_notes=context_notes,
            memory_notes=memory_notes,
        )

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
            result = agent_result["result"]
            agent_name = str(step.get("execution_agent") or step.get("agent") or f"Agent {index}").strip()
            entries.append(
                {
                    "stage": f"planned_agent_{index}",
                    "title": f"{agent_name} 执行" if language != "en" else f"{agent_name} execution",
                    "status": "completed",
                    "detail": (
                        f"{agent_name} 已完成 {step.get('intent')} 子任务：{result.get('summary')}"
                        if language != "en"
                        else f"{agent_name} completed the {step.get('intent')} subtask: {result.get('summary')}"
                    ),
                    "metadata": {
                        "intent": str(step.get("intent") or ""),
                        "agent": agent_name,
                        "result_kind": str(result.get("kind") or ""),
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
            result = agent_result["result"]
            agent_name = str(step.get("execution_agent") or step.get("agent") or "Agent").strip()
            steps.append(
                {
                    "title": f"{agent_name} 协同执行",
                    "status": "completed",
                    "agent": agent_name,
                    "message": str(result.get("summary") or "").strip() or f"{agent_name} 已完成子任务",
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
        final_agent_result = agent_results[-1]
        final_result = store.clone(final_agent_result["result"])
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
        references = _combined_references([item["result"] for item in agent_results])
        bullets = [str(item).strip() for item in final_result.get("bullets") or [] if str(item).strip()]
        if str(final_result.get("kind") or "").strip().lower() != "chat_reply":
            synthesis_note = (
                "已综合多轮分析结果，生成统一回复。"
                if language != "en"
                else "Combined multiple intermediate analyses into one final response."
            )
            if synthesis_note not in bullets:
                bullets.insert(0, synthesis_note)

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
        return final_result

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
        agent_results: list[dict[str, Any]] = []
        working_task = dict(task)
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            planned_agent = self._resolve_planned_agent(step, fallback_agent=execution_agent)
            step_result = self._build_planned_step_result(
                task=working_task,
                run=run,
                step=step,
                execution_agent=planned_agent,
            )
            agent_results.append({"step": step, "result": step_result})
            if coordination_mode == "serial" and index < len(steps) - 1:
                working_task = _task_with_added_context(
                    working_task,
                    f"补充上下文: 上一子任务摘要：{step_result.get('summary')}",
                    *[
                        f"补充上下文: {bullet}"
                        for bullet in (step_result.get("bullets") or [])[:2]
                    ],
                )
        if not agent_results:
            return self.build_task_result(task=task, run=run, execution_agent=execution_agent)
        return self._aggregate_planned_results(
            task=task,
            run=run,
            execution_plan=execution_plan,
            agent_results=agent_results,
        )

    def execute_task(
        self,
        *,
        task: dict,
        run: dict,
        execution_agent: dict | None,
    ) -> dict:
        execution_plan = _planned_execution(run)
        if execution_plan is not None:
            return self._execute_multi_agent(
                task=task,
                run=run,
                execution_agent=execution_agent,
                execution_plan=execution_plan,
            )
        profile = _safe_execution_profile(execution_agent, run)
        execution_mode = _resolve_execution_mode(task, execution_agent, run, profile)
        if execution_mode == "chat":
            return self._execute_chat(task=task, run=run, execution_agent=execution_agent)
        if execution_mode == "search":
            return self._execute_search(task=task, run=run, execution_agent=execution_agent)
        if execution_mode == "write":
            return self._execute_write(task=task, run=run, execution_agent=execution_agent)
        if execution_mode == "help":
            return self._execute_help(task=task, run=run, execution_agent=execution_agent)
        return self._execute_default(task=task, run=run, execution_agent=execution_agent)

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
        bullets.extend(_execution_profile_bullets(resolved_profile, language=language))
        execution_trace = _execution_trace_entries(
            language=language,
            mode="write",
            request_text=request_text,
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
