from __future__ import annotations

from copy import deepcopy
import json
import logging
from typing import Any

import httpx

from app.config import get_settings
from app.modules.agent_config.protocol_bindings.schemas import HermesProtocolResponse, RetrievedLongTermMemory
from app.modules.agent_config.protocol_bindings.service import (
    build_hermes_protocol_request,
    get_protocol_binding,
)
from app.modules.agent_config.registries.external_agent_registry_service import external_agent_registry_service
from app.modules.organization.application.memory_service import memory_service
from app.modules.reception.application.attachment_enrichment_service import attachment_enrichment_service
from app.modules.reception.schemas.messages import UnifiedMessage
from app.platform.persistence.persistence_service import persistence_service
from app.platform.persistence.runtime_store import store


DEFAULT_RECEPTION_AGENT_FAMILY = "hermes-reception"
DEFAULT_RECEPTION_AGENT_ID = "hermes-reception-v1"
DEFAULT_TIMEOUT_SECONDS = 45.0

logger = logging.getLogger(__name__)
_ALLOWED_RECEPTION_ATTACHMENT_EXTENSIONS = {
    ".md",
    ".pdf",
    ".docx",
    ".xlsx",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".bmp",
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".webm",
}
_ATTACHMENT_EXCERPT_FIELDS = (
    "transcript",
    "ocr_text",
    "ocrText",
    "excerpt",
    "summary",
    "content",
    "text_content",
    "textContent",
    "description",
)
_MAX_ATTACHMENT_EXCERPT_CHARS = 240


def _text(value: object) -> str:
    return str(value or "").strip()


def _normalize_requirement_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    normalized = str(value).strip()
    return normalized or None


def _normalize_requirement_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    normalized = deepcopy(payload)
    metadata = normalized.get("metadata")
    metadata_dict = deepcopy(metadata) if isinstance(metadata, dict) else {}
    raw_fields: dict[str, Any] = {}

    for field in ("summary", "details", "category", "urgency"):
        raw_value = normalized.get(field)
        if isinstance(raw_value, (dict, list)):
            raw_fields[field] = deepcopy(raw_value)
        normalized[field] = _normalize_requirement_text(raw_value)

    if raw_fields:
        metadata_dict["raw_fields"] = raw_fields
    if metadata_dict:
        normalized["metadata"] = metadata_dict
    elif "metadata" in normalized:
        normalized["metadata"] = {}
    return normalized


def _message_attachment_summary(metadata: dict[str, Any]) -> str | None:
    raw_items = metadata.get("attachments")
    if not isinstance(raw_items, list):
        return None

    kind_labels = {
        "image": "图片",
        "file": "文件",
        "audio": "音频",
        "voice": "语音",
        "video": "视频",
    }
    parts: list[str] = []
    for item in raw_items[:3]:
        if not isinstance(item, dict):
            continue
        kind = kind_labels.get(str(item.get("kind") or "").strip().lower(), "附件")
        name = _text(item.get("name") or item.get("title") or item.get("file_name"))
        parts.append(f"{kind}{f'“{name}”' if name else ''}")
    if not parts:
        return None
    suffix = " 等附件" if len(raw_items) > 3 else ""
    return "、".join(parts) + suffix


def _attachment_excerpt_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = " ".join(value.strip().split())
    elif isinstance(value, (dict, list)):
        normalized = " ".join(json.dumps(value, ensure_ascii=False).split())
    else:
        normalized = " ".join(str(value).strip().split())
    if not normalized:
        return None
    if len(normalized) <= _MAX_ATTACHMENT_EXCERPT_CHARS:
        return normalized
    return normalized[: _MAX_ATTACHMENT_EXCERPT_CHARS - 1].rstrip() + "…"


def _attachment_inline_excerpt(item: dict[str, Any]) -> str | None:
    for field in _ATTACHMENT_EXCERPT_FIELDS:
        excerpt = _attachment_excerpt_text(item.get(field))
        if excerpt:
            return excerpt
    return None


def _message_attachment_context_block(metadata: dict[str, Any]) -> str | None:
    raw_items = metadata.get("attachments")
    if not isinstance(raw_items, list) or not raw_items:
        return None

    summary = _message_attachment_summary(metadata)
    lines = [f"客户本轮附带：{summary}" if summary else "客户本轮附带了附件", "附件详情："]
    saw_image = False
    for item in raw_items[:3]:
        if not isinstance(item, dict):
            continue
        kind = {
            "image": "图片",
            "file": "文件",
            "audio": "音频",
            "voice": "语音",
            "video": "视频",
        }.get(str(item.get("kind") or "").strip().lower(), "附件")
        if kind == "图片":
            saw_image = True
        name = _text(item.get("name") or item.get("title") or item.get("file_name"))
        detail_parts: list[str] = []
        mime_type = _text(item.get("mime_type") or item.get("mimeType"))
        if mime_type:
            detail_parts.append(f"mime={mime_type}")
        url = _text(item.get("url") or item.get("download_url") or item.get("downloadUrl"))
        if url:
            detail_parts.append(f"url={url}")
        duration_ms = item.get("duration_ms") if isinstance(item.get("duration_ms"), int) else item.get("durationMs")
        if isinstance(duration_ms, int):
            detail_parts.append(f"duration_ms={duration_ms}")
        head = f"- {kind}{f'“{name}”' if name else ''}"
        if detail_parts:
            head += "；" + "；".join(detail_parts)
        lines.append(head)
        excerpt = _attachment_inline_excerpt(item)
        if excerpt:
            lines.append(f"附件节选：{excerpt}")
    if len(raw_items) > 3:
        lines.append(f"其余附件：还有 {len(raw_items) - 3} 个未展开。")
    if saw_image:
        lines.append(
            "图片/截图接待规则：优先基于附件里的 OCR 文本或可见文字判断客户诉求；"
            "如果文字不清晰、OCR 片段不足或只能看出局部内容，就直接说明你只能确认到这些信息，并追问客户要看的页面、位置或具体问题，"
            "不要自行脑补图片内容。"
        )
    return "\n".join(lines)


def _message_text_with_attachment_context(message: UnifiedMessage) -> str:
    metadata = message.metadata if isinstance(message.metadata, dict) else {}
    attachment_context = _message_attachment_context_block(metadata)
    if not attachment_context:
        return _text(message.text)
    base_text = _text(message.text)
    if not base_text:
        return attachment_context
    return f"{base_text}\n\n{attachment_context}"


def _enrich_message_attachments(message: UnifiedMessage) -> None:
    metadata = message.metadata if isinstance(message.metadata, dict) else None
    if not isinstance(metadata, dict):
        return
    attachments = metadata.get("attachments")
    if not isinstance(attachments, list) or not attachments:
        return
    enriched_attachments, warnings = attachment_enrichment_service.enrich_attachments(attachments)
    metadata["attachments"] = enriched_attachments
    if warnings:
        metadata["attachment_enrichment_warnings"] = warnings
        logger.warning(
            "Reception attachment enrichment warnings: message_id=%s warnings=%s",
            _text(message.message_id),
            warnings,
        )


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _metadata_from_agent(agent: dict[str, Any]) -> dict[str, Any]:
    snapshot = agent.get("config_snapshot")
    if isinstance(snapshot, dict):
        metadata = snapshot.get("metadata")
        if isinstance(metadata, dict):
            return deepcopy(metadata)
    return {}


def _invocation_from_agent(agent: dict[str, Any]) -> dict[str, Any]:
    summary = agent.get("config_summary")
    if isinstance(summary, dict):
        invocation = summary.get("invocation")
        if isinstance(invocation, dict):
            return deepcopy(invocation)
    snapshot = agent.get("config_snapshot")
    if isinstance(snapshot, dict):
        runtime = snapshot.get("runtime")
        if isinstance(runtime, dict):
            invocation = runtime.get("invocation")
            if isinstance(invocation, dict):
                return deepcopy(invocation)
        metadata = snapshot.get("metadata")
        if isinstance(metadata, dict):
            invocation = metadata.get("invocation")
            if isinstance(invocation, dict):
                return deepcopy(invocation)
    return {}


def _auth_headers(metadata: dict[str, Any]) -> dict[str, str]:
    auth = metadata.get("auth") if isinstance(metadata.get("auth"), dict) else {}
    bearer_token = _text(
        auth.get("bearer_token")
        or auth.get("bearerToken")
        or metadata.get("auth_token")
        or metadata.get("authToken")
        or metadata.get("api_key")
        or metadata.get("apiKey")
    )
    if not bearer_token:
        return {}
    return {"Authorization": f"Bearer {bearer_token}"}


def _load_profile(profile_id: str | None) -> dict[str, Any] | None:
    normalized_profile_id = _text(profile_id)
    if not normalized_profile_id:
        return None

    persisted = persistence_service.get_user_profile(normalized_profile_id)
    if isinstance(persisted, dict):
        return deepcopy(persisted)

    runtime_profile = store.user_profiles.get(normalized_profile_id)
    if isinstance(runtime_profile, dict):
        return deepcopy(runtime_profile)
    return None


def _profile_id_from_metadata(metadata: dict[str, Any]) -> str | None:
    return _text(
        metadata.get("user_profile_id")
        or metadata.get("profile_id")
        or metadata.get("profileId")
    ) or None


def _legacy_customer_id_from_metadata(
    metadata: dict[str, Any],
    profile: dict[str, Any] | None,
) -> str | None:
    if isinstance(profile, dict):
        profile_customer_id = _text(profile.get("customer_id") or profile.get("customerId")) or None
    else:
        profile_customer_id = None
    return _text(metadata.get("customer_id") or metadata.get("customerId")) or profile_customer_id


def _resolved_customer_identifier(
    *,
    metadata: dict[str, Any],
    profile: dict[str, Any] | None,
    platform_user_id: str | None,
) -> str | None:
    profile_id = _profile_id_from_metadata(metadata) or (
        _text(profile.get("id")) or None if isinstance(profile, dict) else None
    )
    if profile_id:
        return profile_id

    legacy_customer_id = _legacy_customer_id_from_metadata(metadata, profile)
    if legacy_customer_id:
        return legacy_customer_id

    return _text(platform_user_id) or None


def _customer_context_from_profile(profile: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(profile, dict):
        return None

    context = {
        "company_name": _text(profile.get("company_name") or profile.get("companyName")) or None,
        "contact_name": _text(profile.get("contact_name") or profile.get("contactName")) or None,
        "mobile": _text(profile.get("mobile")) or None,
        "service_status": _text(profile.get("service_status") or profile.get("serviceStatus")) or None,
        "tags": [
            str(tag).strip()
            for tag in (profile.get("tags") or [])
            if str(tag).strip()
        ],
        "profile_summary": _text(profile.get("profile_summary") or profile.get("profileSummary")) or None,
        "preferences": [
            str(item).strip()
            for item in (profile.get("preferences") or [])
            if str(item).strip()
        ],
        "business_background": [
            str(item).strip()
            for item in (
                profile.get("business_background")
                or profile.get("businessBackground")
                or []
            )
            if str(item).strip()
        ],
        "decision_history": [
            str(item).strip()
            for item in (
                profile.get("decision_history")
                or profile.get("decisionHistory")
                or []
            )
            if str(item).strip()
        ],
    }
    if not any(
        value
        for key, value in context.items()
        if key != "tags"
    ) and not context["tags"]:
        return None
    return context


def _profile_retrieved_long_term_memories(
    *,
    profile: dict[str, Any] | None,
    customer_id: str | None,
) -> list[RetrievedLongTermMemory]:
    if not isinstance(profile, dict):
        return []

    normalized_customer_id = _text(customer_id) or _text(profile.get("customer_id") or profile.get("customerId")) or None
    collected: list[RetrievedLongTermMemory] = []

    profile_summary = _text(profile.get("profile_summary") or profile.get("profileSummary"))
    if profile_summary:
        collected.append(
            RetrievedLongTermMemory(
                memory_id=None,
                memory_type="profile_summary",
                scope="tenant",
                subject_id=normalized_customer_id,
                title="客户画像摘要",
                summary=profile_summary,
                source="profile",
                metadata={"origin": "customer_profile"},
            )
        )

    typed_lists = (
        (
            "customer_preference",
            "客户偏好",
            profile.get("preferences") or [],
        ),
        (
            "business_fact",
            "业务背景",
            profile.get("business_background") or profile.get("businessBackground") or [],
        ),
        (
            "decision",
            "历史决策",
            profile.get("decision_history") or profile.get("decisionHistory") or [],
        ),
    )
    for memory_type, title, items in typed_lists:
        if not isinstance(items, list):
            continue
        for item in items[:4]:
            summary = _text(item)
            if not summary:
                continue
            collected.append(
                RetrievedLongTermMemory(
                    memory_id=None,
                    memory_type=memory_type,
                    scope="tenant",
                    subject_id=normalized_customer_id,
                    title=title,
                    summary=summary,
                    source="profile",
                    metadata={"origin": "customer_profile"},
                )
            )
    return collected


def _active_task_context_from_metadata(metadata: dict[str, Any]) -> dict[str, Any] | None:
    task_context = metadata.get("active_task_context") or metadata.get("activeTaskContext")
    if not isinstance(task_context, dict):
        return None

    task_id = _text(task_context.get("task_id") or task_context.get("taskId"))
    if not task_id:
        return None

    return {
        "task_id": task_id,
        "title": _text(task_context.get("title")) or None,
        "status": _text(task_context.get("status")) or None,
        "summary": _text(task_context.get("summary")) or None,
        "updated_at": _text(task_context.get("updated_at") or task_context.get("updatedAt")) or None,
    }


def _knowledge_hits_from_metadata(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    raw_hits = metadata.get("knowledge_hits") or metadata.get("knowledgeHits")
    if not isinstance(raw_hits, list):
        return []

    hits: list[dict[str, Any]] = []
    for item in raw_hits[:5]:
        if not isinstance(item, dict):
            continue
        summary = _text(item.get("summary") or item.get("content") or item.get("excerpt"))
        if not summary:
            continue
        hits.append(
            {
                "title": _text(item.get("title")) or None,
                "summary": summary,
                "source": _text(item.get("source")) or None,
                "metadata": deepcopy(item.get("metadata")) if isinstance(item.get("metadata"), dict) else {},
            }
        )
    return hits


def _tenant_scope(tenant_id: str | None) -> dict[str, str] | None:
    normalized_tenant_id = _text(tenant_id)
    if not normalized_tenant_id:
        return None
    return {"tenant_id": normalized_tenant_id}


def _tenant_soul_from_platform(*, tenant_id: str | None) -> str | None:
    scope = _tenant_scope(tenant_id)
    if scope is None:
        return None
    try:
        result = memory_service.list_long_term_memories(
            scope=scope,
            subject_id=str(scope["tenant_id"]),
            subject_type="tenant",
            memory_type="tenant_soul",
            limit=1,
            memory_scope="tenant",
        )
    except Exception as exc:  # pragma: no cover - defensive path
        logger.warning("Load tenant_soul from platform memory failed: tenant_id=%s error=%s", tenant_id, exc)
        return None

    items = result.get("items") if isinstance(result, dict) else None
    first_item = items[0] if isinstance(items, list) and items else None
    if not isinstance(first_item, dict):
        return None
    return _text(first_item.get("summary") or first_item.get("memory_text")) or None


def _retrieved_long_term_memories(
    *,
    profile: dict[str, Any] | None,
    tenant_id: str | None,
    customer_id: str | None,
    fallback_customer_id: str | None = None,
    query: str,
    limit: int = 4,
) -> list[RetrievedLongTermMemory]:
    scope = _tenant_scope(tenant_id)
    normalized_customer_id = _text(customer_id)
    normalized_fallback_customer_id = _text(fallback_customer_id)
    normalized_query = _text(query)
    derived_memories = _profile_retrieved_long_term_memories(profile=profile, customer_id=customer_id)
    customer_subject_ids = [
        candidate
        for candidate in (normalized_customer_id, normalized_fallback_customer_id)
        if candidate
    ]
    deduped_subject_ids: list[str] = []
    for subject_id in customer_subject_ids:
        if subject_id not in deduped_subject_ids:
            deduped_subject_ids.append(subject_id)

    if scope is None or not deduped_subject_ids or not normalized_query:
        return derived_memories[:limit]

    items: list[dict[str, Any]] | None = None
    for subject_id in deduped_subject_ids:
        try:
            result = memory_service.retrieve(
                user_id=subject_id,
                query=normalized_query,
                limit=limit,
                scope=scope,
                memory_scope="tenant",
            )
        except Exception as exc:  # pragma: no cover - defensive path
            logger.warning(
                "Retrieve platform long-term memory failed: tenant_id=%s customer_id=%s error=%s",
                tenant_id,
                subject_id,
                exc,
            )
            continue
        items = result.get("items") if isinstance(result, dict) else None
        if isinstance(items, list) and items:
            break

        try:
            fallback_result = memory_service.list_long_term_memories(
                scope=scope,
                subject_id=subject_id,
                subject_type="customer",
                limit=limit,
                memory_scope="tenant",
            )
        except Exception as exc:  # pragma: no cover - defensive path
            logger.warning(
                "Fallback list for platform long-term memory failed: tenant_id=%s customer_id=%s error=%s",
                tenant_id,
                subject_id,
                exc,
            )
            items = None
            continue
        items = fallback_result.get("items") if isinstance(fallback_result, dict) else None
        if isinstance(items, list) and items:
            break

    if not isinstance(items, list):
        return derived_memories[:limit]

    retrieved: list[RetrievedLongTermMemory] = list(derived_memories)
    seen_pairs = {
        (item.memory_type.strip().lower(), item.summary.strip().lower())
        for item in retrieved
    }
    for item in items:
        if not isinstance(item, dict):
            continue
        summary = _text(item.get("summary") or item.get("memory_text"))
        if not summary:
            continue
        dedupe_pair = (_text(item.get("memory_type")).lower() or "business_fact", summary.lower())
        if dedupe_pair in seen_pairs:
            continue
        try:
            retrieved.append(
                RetrievedLongTermMemory(
                    memory_id=_text(item.get("memory_id") or item.get("id")) or None,
                    memory_type=_text(item.get("memory_type")) or "business_fact",
                    scope=_text(item.get("memory_scope")) or "tenant",
                    subject_id=_text(item.get("subject_id")) or None,
                    title=_text(item.get("title")) or None,
                    summary=summary,
                    importance=float(item.get("score")) if item.get("score") is not None else None,
                    source=_text(item.get("source")) or None,
                    metadata={
                        "score": item.get("score"),
                        "matched_terms": item.get("matched_terms") or [],
                        "memory_layer_kind": item.get("memory_layer_kind"),
                    },
                )
            )
            seen_pairs.add(dedupe_pair)
        except Exception:  # pragma: no cover - defensive validation path
            continue
    return retrieved[:limit]


def _remote_model_name(agent: dict[str, Any], metadata: dict[str, Any]) -> str:
    return (
        _text(metadata.get("remote_model"))
        or _text(metadata.get("model"))
        or _text((agent.get("config_summary") or {}).get("version"))
        or "hermes-agent"
    )


def _structured_reception_system_prompt(
    *,
    tenant_soul: str | None,
    customer_context: dict[str, Any] | None,
    retrieved_memories: list[RetrievedLongTermMemory],
    knowledge_hits: list[dict[str, Any]],
    active_task_context: dict[str, Any] | None,
) -> str:
    sections = [
        "你是平台外接接待智能体。",
        "你负责与客户接待对话，并在内部判断当前消息属于 continuation、chat、task 哪一种。",
        "你必须只输出一个 JSON object，不要输出 Markdown、代码块或额外解释。",
        "reply_text 写给最终客户，保持自然、专业、简洁。",
        "interaction_mode 只能取 continuation、chat、task 之一。",
        "task_signal 只能取 stay_in_reception、dispatch_task 之一。",
        "needs_clarification 为 true 时，clarify_question 必须是下一句要问客户的话。",
        "如果当前消息是在补充、修改、推进当前活跃任务，优先判断为 continuation，并保持 task_signal=stay_in_reception。",
        "如果只是咨询、知识问答、售前说明或实时信息查询（如天气、热点、新闻、日期、价格），判断为 chat。",
        "如果需要实时外部信息，优先调用已启用工具核实后再回复，不要编造事实。",
        "如果平台已提供知识命中且足够回答，优先基于知识命中回复，不要误判为 task。",
        "如果客户明确提出新的执行性需求、项目、开发、制作、排期、报价、交付或需要平台后续跟进的工作，判断为 task。",
        "如果 interaction_mode=task，task_signal 应为 dispatch_task，并尽量提炼 requirement_payload.summary 和 requirement_payload.details。",
        (
            '返回字段固定为: {"reply_text": "...", "interaction_mode": "chat", '
            '"task_signal": "stay_in_reception", "needs_clarification": false, '
            '"clarify_question": null, "requirement_payload": null, '
            '"safety_signal": null, "confidence": null, "metadata": {}}'
        ),
    ]

    if tenant_soul:
        sections.append(f"租户设定：{tenant_soul}")

    if isinstance(customer_context, dict):
        customer_lines = []
        for key in ("company_name", "contact_name", "mobile", "service_status"):
            value = _text(customer_context.get(key))
            if value:
                customer_lines.append(f"{key}={value}")
        tags = customer_context.get("tags")
        if isinstance(tags, list):
            normalized_tags = [str(tag).strip() for tag in tags if str(tag).strip()]
            if normalized_tags:
                customer_lines.append(f"tags={', '.join(normalized_tags)}")
        if customer_lines:
            sections.append("客户画像：" + "；".join(customer_lines))

    if active_task_context is not None:
        task_lines = [f"task_id={active_task_context['task_id']}"]
        for key in ("title", "status", "summary"):
            value = _text(active_task_context.get(key))
            if value:
                task_lines.append(f"{key}={value}")
        sections.append("当前活跃任务：" + "；".join(task_lines))

    if retrieved_memories:
        sections.append(
            "平台长期记忆：\n"
            + "\n".join(
                f"- {item.memory_type}: {item.summary}"
                for item in retrieved_memories[:5]
            )
        )

    if knowledge_hits:
        sections.append(
            "租户知识命中：\n"
            + "\n".join(
                f"- {(_text(item.get('title')) or '知识片段')}: {_text(item.get('summary'))}"
                for item in knowledge_hits[:5]
            )
        )

    return "\n\n".join(sections)


def _parse_response_text(*, endpoint_path: str, payload: dict[str, Any]) -> str:
    direct_reply = _text(payload.get("reply_text") or payload.get("replyText"))
    if direct_reply:
        return direct_reply

    normalized_path = endpoint_path.rstrip("/").lower()
    if normalized_path.endswith("/responses"):
        output = payload.get("output")
        if isinstance(output, list):
            texts: list[str] = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for content_item in content:
                    if not isinstance(content_item, dict):
                        continue
                    if str(content_item.get("type") or "").strip() in {"output_text", "text"}:
                        text = _text(content_item.get("text"))
                        if text:
                            texts.append(text)
            return "\n".join(texts).strip()

    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first_choice = choices[0] if isinstance(choices[0], dict) else {}
        message = first_choice.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                texts = [
                    _text(item.get("text"))
                    for item in content
                    if isinstance(item, dict) and _text(item.get("text"))
                ]
                if texts:
                    return "\n".join(texts).strip()

    content = payload.get("content")
    if isinstance(content, list):
        texts = [
            _text(item.get("text"))
            for item in content
            if isinstance(item, dict) and _text(item.get("text"))
        ]
        if texts:
            return "\n".join(texts).strip()

    return _text(payload.get("output_text") or payload.get("text"))


def _extract_json_object(text: str) -> dict[str, Any] | None:
    normalized = str(text or "").strip()
    if not normalized:
        return None
    if normalized.startswith("```"):
        lines = normalized.splitlines()
        if len(lines) >= 3 and lines[-1].strip().startswith("```"):
            normalized = "\n".join(lines[1:-1]).strip()
            if normalized.lower().startswith("json"):
                normalized = normalized[4:].strip()
    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _response_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata")
    return deepcopy(metadata) if isinstance(metadata, dict) else {}


def _parse_memory_writeback_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = payload.get("memory_writeback") or payload.get("memoryWriteback")
    if not isinstance(raw_items, list):
        return []

    items: list[dict[str, Any]] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        summary = _text(raw_item.get("summary"))
        if not summary:
            continue
        item = {
            "scope": _text(raw_item.get("scope")) or "customer",
            "memory_type": _text(raw_item.get("memory_type") or raw_item.get("memoryType")) or "business_fact",
            "subject_id": _text(raw_item.get("subject_id") or raw_item.get("subjectId")) or None,
            "title": _text(raw_item.get("title")) or None,
            "summary": summary,
            "importance": raw_item.get("importance"),
            "metadata": deepcopy(raw_item.get("metadata")) if isinstance(raw_item.get("metadata"), dict) else {},
        }
        items.append(item)
    return items


def _parse_attachments(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = payload.get("attachments") or payload.get("artifacts")
    if not isinstance(raw_items, list):
        return []

    items: list[dict[str, Any]] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        file_path = _text(raw_item.get("file_path") or raw_item.get("filePath"))
        file_name = _text(raw_item.get("file_name") or raw_item.get("fileName"))
        if not file_path or not file_name:
            continue
        ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
        if ext and f".{ext}" not in _ALLOWED_RECEPTION_ATTACHMENT_EXTENSIONS:
            continue
        item = {
            "title": _text(raw_item.get("title")) or file_name,
            "file_name": file_name,
            "file_path": file_path,
            "mime_type": _text(raw_item.get("mime_type") or raw_item.get("mimeType")) or "application/octet-stream",
            "kind": _text(raw_item.get("kind")) or None,
            "format": _text(raw_item.get("format")) or None,
            "size_bytes": raw_item.get("size_bytes") if isinstance(raw_item.get("size_bytes"), int) else raw_item.get("sizeBytes"),
        }
        items.append(item)
    return items


def _normalize_interaction_mode(payload: dict[str, Any]) -> str:
    interaction_mode = _text(payload.get("interaction_mode") or payload.get("interactionMode")).lower()
    if interaction_mode in {"continuation", "chat", "task"}:
        return interaction_mode

    task_signal = _text(payload.get("task_signal") or payload.get("taskSignal")).lower()
    if task_signal in {"dispatch_task", "handoff_human"}:
        return "task"
    return "chat"


def _normalize_task_signal(payload: dict[str, Any]) -> str:
    task_signal = _text(payload.get("task_signal") or payload.get("taskSignal")).lower()
    if task_signal == "handoff_human":
        return "dispatch_task"
    if task_signal in {"stay_in_reception", "dispatch_task"}:
        return task_signal
    return "stay_in_reception"


class HermesReceptionAgentService:
    def _normalize_protocol_response(
        self,
        *,
        endpoint_path: str,
        payload: dict[str, Any],
        request_id: str,
    ) -> HermesProtocolResponse:
        candidate = payload if any(key in payload for key in ("reply_text", "replyText")) else None
        if candidate is None:
            candidate = _extract_json_object(_parse_response_text(endpoint_path=endpoint_path, payload=payload))
        if candidate is None:
            candidate = {
                "request_id": request_id,
                "reply_text": _parse_response_text(endpoint_path=endpoint_path, payload=payload),
                "task_signal": "stay_in_reception",
                "memory_writeback": [],
                "metadata": {},
            }
        normalized = dict(candidate)
        normalized.setdefault("request_id", request_id)
        normalized.setdefault("reply_text", _text(normalized.get("reply_text") or normalized.get("replyText")))
        normalized["interaction_mode"] = _normalize_interaction_mode(normalized)
        normalized["task_signal"] = _normalize_task_signal(normalized)
        requirement_payload = normalized.get("requirement_payload")
        if not isinstance(requirement_payload, dict):
            requirement_payload = normalized.get("requirementPayload")
        normalized["requirement_payload"] = _normalize_requirement_payload(requirement_payload)
        normalized.setdefault("memory_writeback", [])
        normalized["attachments"] = _parse_attachments(normalized)
        normalized.setdefault("metadata", {})
        return HermesProtocolResponse.model_validate(normalized)

    def _resolve_agent(self) -> dict[str, Any]:
        settings = get_settings()
        configured_id = _text(getattr(settings, "reception_agent_id", None))
        if configured_id:
            agent = external_agent_registry_service.get_agent(configured_id)
            if agent is not None and bool(agent.get("routable")):
                return agent

        family_candidates = [DEFAULT_RECEPTION_AGENT_FAMILY, DEFAULT_RECEPTION_AGENT_ID]
        agents = external_agent_registry_service.list_agents(include_offline=False)
        for candidate in agents:
            family = _text(candidate.get("agent_family")).lower()
            agent_id = _text(candidate.get("id")).lower()
            if family in family_candidates or agent_id == DEFAULT_RECEPTION_AGENT_ID:
                return candidate

        selected = external_agent_registry_service.select_agent(agent_type="write")
        if selected is not None:
            return selected
        raise RuntimeError("未找到可用的接待外部智能体，请先接入 Hermes")

    def _build_request_payload(
        self,
        *,
        message: UnifiedMessage,
        remote_model: str,
        endpoint_path: str,
    ) -> dict[str, Any]:
        _enrich_message_attachments(message)
        metadata = message.metadata if isinstance(message.metadata, dict) else {}
        tenant_id = _text(metadata.get("tenant_id") or metadata.get("tenantId")) or None
        profile = _load_profile(_profile_id_from_metadata(metadata))
        customer_id = _resolved_customer_identifier(
            metadata=metadata,
            profile=profile,
            platform_user_id=message.platform_user_id,
        )
        legacy_customer_id = _legacy_customer_id_from_metadata(metadata, profile)
        tenant_soul = _text(metadata.get("tenant_soul") or metadata.get("tenantSoul")) or _tenant_soul_from_platform(
            tenant_id=tenant_id
        )
        retrieved_memories = _retrieved_long_term_memories(
            profile=profile,
            tenant_id=tenant_id,
            customer_id=customer_id,
            fallback_customer_id=legacy_customer_id,
            query=_message_text_with_attachment_context(message),
        )
        active_task_context = _active_task_context_from_metadata(metadata)
        knowledge_hits = _knowledge_hits_from_metadata(metadata)

        system_prompt = _structured_reception_system_prompt(
            tenant_soul=tenant_soul,
            customer_context=_customer_context_from_profile(profile),
            retrieved_memories=retrieved_memories,
            knowledge_hits=knowledge_hits,
            active_task_context=active_task_context,
        )
        context_lines = [
            f"channel={message.channel.value}",
            f"tenant_id={tenant_id or 'unknown'}",
            f"customer_id={customer_id or 'unknown'}",
            f"session_id={_text(message.session_id) or 'unknown'}",
            f"detected_lang={_text(message.detected_lang) or 'unknown'}",
        ]
        user_prompt = f"{chr(10).join(context_lines)}\n\n用户消息：{_message_text_with_attachment_context(message)}"

        normalized_path = endpoint_path.rstrip("/").lower()
        if normalized_path.endswith("/responses"):
            return {
                "model": remote_model,
                "input": [
                    {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
                    {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
                ],
            }
        return {
            "model": remote_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
            "stream": False,
        }

    def _tenant_id_from_message(self, message: UnifiedMessage) -> str | None:
        metadata = message.metadata if isinstance(message.metadata, dict) else {}
        return _text(metadata.get("tenant_id") or metadata.get("tenantId")) or None

    def _binding_request_mode(self, binding_metadata: dict[str, Any]) -> str:
        return _text(binding_metadata.get("request_mode") or binding_metadata.get("requestMode") or "openai_compatible").lower()

    def _binding_invoke_path(self, binding_metadata: dict[str, Any], fallback: str) -> str:
        return _text(binding_metadata.get("invoke_path") or binding_metadata.get("invokePath") or fallback) or fallback

    def _build_protocol_payload(
        self,
        *,
        binding_metadata: dict[str, Any],
        binding,
        agent: dict[str, Any],
        message: UnifiedMessage,
    ) -> dict[str, Any]:
        _enrich_message_attachments(message)
        metadata = message.metadata if isinstance(message.metadata, dict) else {}
        profile_id = _profile_id_from_metadata(metadata)
        profile = _load_profile(profile_id)
        customer_id = _resolved_customer_identifier(
            metadata=metadata,
            profile=profile,
            platform_user_id=message.platform_user_id,
        )
        legacy_customer_id = _legacy_customer_id_from_metadata(metadata, profile)
        tenant_soul = _text(metadata.get("tenant_soul") or metadata.get("tenantSoul")) or _tenant_soul_from_platform(
            tenant_id=binding.tenant_id
        )
        retrieved_memories = _retrieved_long_term_memories(
            profile=profile,
            tenant_id=binding.tenant_id,
            customer_id=customer_id,
            fallback_customer_id=legacy_customer_id,
            query=_message_text_with_attachment_context(message),
        )
        knowledge_hits = _knowledge_hits_from_metadata(metadata)
        active_task_context = _active_task_context_from_metadata(metadata)
        request = build_hermes_protocol_request(
            binding=binding,
            request_id=_text(metadata.get("request_id")) or f"reception:{message.message_id}",
            tenant_id=binding.tenant_id,
            customer_id=customer_id,
            profile_id=profile_id,
            agent_id=_text(agent.get("id")) or binding.agent_id,
            protocol_id=binding.protocol_id,
            protocol_version=binding.protocol_version,
            session_id=_text(message.session_id),
            task_id=_text(metadata.get("task_id") or metadata.get("taskId")) or None,
            channel=message.channel.value,
            channel_user_id=_text(message.platform_user_id),
            channel_chat_id=_text(message.chat_id) or None,
            message_id=_text(message.message_id),
            message_text=_message_text_with_attachment_context(message),
            message_language=_text(message.detected_lang) or None,
            tenant_soul=tenant_soul,
            retrieved_long_term_memories=retrieved_memories,
            knowledge_hits=knowledge_hits,
            active_task_context=active_task_context,
            runtime_memory_mode=binding.runtime_memory_mode,
            security_flags=[
                str(flag).strip()
                for flag in (metadata.get("security_flags") or metadata.get("securityFlags") or [])
                if str(flag).strip()
            ],
            admission_status="bound",
            customer_context=_customer_context_from_profile(profile),
            metadata={
                "source": "xxl_reception",
                "attachments": deepcopy(metadata.get("attachments")) if isinstance(metadata.get("attachments"), list) else [],
            },
        )
        return request.model_dump(mode="json", by_alias=True)

    def reply(
        self,
        *,
        message: UnifiedMessage,
    ) -> dict[str, Any]:
        agent = self._resolve_agent()
        invocation = _invocation_from_agent(agent)
        metadata = _metadata_from_agent(agent)

        base_url = _text(invocation.get("base_url") or invocation.get("baseUrl"))
        endpoint_path = _text(invocation.get("invoke_path") or invocation.get("invokePath") or "/v1/chat/completions")
        method = _text(invocation.get("method") or "POST").upper() or "POST"
        if method != "POST":
            raise RuntimeError(f"当前仅支持 POST 外部接待 Agent，实际为 {method}")
        if not base_url:
            logger.error(
                "Hermes reception invocation missing base_url: agent_id=%s config_summary=%s config_snapshot=%s",
                _text(agent.get("id")),
                agent.get("config_summary"),
                agent.get("config_snapshot"),
            )
            raise RuntimeError("外部接待智能体未配置 base_url")

        tenant_id = self._tenant_id_from_message(message)
        binding = get_protocol_binding(tenant_id=tenant_id, agent_id=_text(agent.get("id"))) if tenant_id else None
        binding_metadata = deepcopy(binding.metadata) if binding is not None else {}
        if binding is not None:
            if binding.target_base_url:
                base_url = binding.target_base_url
            endpoint_path = self._binding_invoke_path(binding_metadata, endpoint_path)

        remote_model = _remote_model_name(agent, metadata)
        request_mode = self._binding_request_mode(binding_metadata)
        if binding is not None and request_mode == "protocol":
            payload = self._build_protocol_payload(
                binding_metadata=binding_metadata,
                binding=binding,
                agent=agent,
                message=message,
            )
        else:
            payload = self._build_request_payload(
                message=message,
                remote_model=remote_model,
                endpoint_path=endpoint_path,
            )
        message_metadata = message.metadata if isinstance(message.metadata, dict) else {}
        profile = _load_profile(_profile_id_from_metadata(message_metadata))
        customer_id = _resolved_customer_identifier(
            metadata=message_metadata,
            profile=profile,
            platform_user_id=message.platform_user_id,
        )
        headers = _auth_headers(metadata)
        headers.setdefault("X-Hermes-Reception-Mode", "reception")
        headers.setdefault("X-Hermes-Tenant-Id", _text(binding.tenant_id if binding is not None else tenant_id or ""))
        headers.setdefault("X-Hermes-Customer-Id", _text(customer_id))
        headers.setdefault("X-Hermes-Session-Id", _text(message.session_id))
        headers = {key: value for key, value in headers.items() if value}

        try:
            with httpx.Client(timeout=DEFAULT_TIMEOUT_SECONDS, trust_env=False) as client:
                response = client.post(
                    _join_url(base_url, endpoint_path),
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                response_payload = response.json()
        except Exception as exc:  # pragma: no cover - network path
            logger.exception(
                "Hermes reception invoke failed: agent_id=%s target=%s",
                _text(agent.get("id")),
                _join_url(base_url, endpoint_path),
            )
            raise RuntimeError(f"Hermes 调用失败：{exc}") from exc

        if not isinstance(response_payload, dict):
            raise RuntimeError("Hermes 返回格式无效")

        protocol_request_id = _text(payload.get("request_id") or payload.get("requestId")) or f"reception:{message.message_id}"
        protocol_response = self._normalize_protocol_response(
            endpoint_path=endpoint_path,
            payload=response_payload,
            request_id=protocol_request_id,
        )
        response_payload = protocol_response.model_dump(mode="json", by_alias=True)
        reply_text = _parse_response_text(endpoint_path=endpoint_path, payload=response_payload)
        if not reply_text:
            raise RuntimeError("Hermes 未返回可用文本")
        response_metadata = _response_metadata(response_payload)

        return {
            "request_id": protocol_request_id,
            "agent_id": _text(agent.get("id")),
            "agent_name": _text(agent.get("name")) or "Hermes",
            "reply_text": reply_text,
            "remote_model": remote_model,
            "binding_id": binding.binding_id if binding is not None else None,
            "protocol_mode": request_mode if binding is not None else "structured_openai_compatible",
            "interaction_mode": _text(response_payload.get("interaction_mode") or response_payload.get("interactionMode")) or "chat",
            "intent": _text(response_payload.get("intent")) or None,
            "needs_clarification": bool(response_payload.get("needs_clarification") or response_payload.get("needsClarification")),
            "clarify_question": _text(response_payload.get("clarify_question") or response_payload.get("clarifyQuestion")) or None,
            "task_signal": _text(response_payload.get("task_signal") or response_payload.get("taskSignal")) or None,
            "requirement_payload": deepcopy(response_payload.get("requirement_payload"))
            if isinstance(response_payload.get("requirement_payload"), dict)
            else deepcopy(response_payload.get("requirementPayload"))
            if isinstance(response_payload.get("requirementPayload"), dict)
            else None,
            "memory_writeback": _parse_memory_writeback_items(response_payload),
            "attachments": _parse_attachments(response_payload),
            "safety_signal": _text(response_payload.get("safety_signal") or response_payload.get("safetySignal")) or None,
            "confidence": response_payload.get("confidence"),
            "protocol_response_metadata": response_metadata,
        }


hermes_reception_agent_service = HermesReceptionAgentService()
