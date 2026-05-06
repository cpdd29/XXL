from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import logging
import re
from typing import Any

from app.modules.organization.application import profile_service as organization_profile_service
from app.modules.reception.schemas.messages import UnifiedMessage
from app.platform.persistence.runtime_store import store
from app.platform.security.content_policy import apply_content_policy


PROFILE_CONTEXT_BUDGET_CHARS = 512 * 1024
PROFILE_LIST_LIMIT = 12
PROFILE_ENTRY_MAX_CHARS = 240
PROFILE_SUMMARY_MAX_CHARS = 1200
PROFILE_WRITEBACK_ACTOR = {
    "id": "reception-profile-writeback",
    "email": "reception-profile-writeback@workbot.local",
    "role": "super_admin",
    "platform_admin": True,
}
PREFERENCE_HINTS = (
    "偏好",
    "希望",
    "更关注",
    "优先",
    "习惯",
    "先给",
    "先看",
    "中文",
    "英文",
    "排期",
    "交付周期",
)
DECISION_HINTS = (
    "确定",
    "决定",
    "必须",
    "只做",
    "先做",
    "不做",
    "截止",
    "预算",
    "优先级",
)
BACKGROUND_HINTS = (
    "我们要做",
    "需要做",
    "想做",
    "项目",
    "方案",
    "系统",
    "产品",
    "官网",
    "门户",
    "小程序",
    "改版",
    "接入",
    "上线",
)
SENTENCE_SPLIT_PATTERN = re.compile(r"[。！？!?；;\n]+")
WHITESPACE_PATTERN = re.compile(r"\s+")

logger = logging.getLogger(__name__)


def _text(value: object) -> str:
    return str(value or "").strip()


def _normalize_items(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    seen: set[str] = set()
    for raw in value:
        normalized = _text(raw)
        if not normalized:
            continue
        dedupe_key = WHITESPACE_PATTERN.sub("", normalized).lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        items.append(normalized)
    return items


def _sanitize_snippet(value: object) -> str:
    normalized = _text(value)
    if not normalized:
        return ""
    rewritten, _, _, _ = apply_content_policy(normalized)
    compacted = WHITESPACE_PATTERN.sub(" ", str(rewritten or "")).strip()
    if not compacted or "脱敏" in compacted:
        return ""
    if len(compacted) > PROFILE_ENTRY_MAX_CHARS:
        return compacted[: PROFILE_ENTRY_MAX_CHARS - 3].rstrip() + "..."
    return compacted


def _split_sentences(*values: object) -> list[str]:
    sentences: list[str] = []
    for value in values:
        normalized = _text(value)
        if not normalized:
            continue
        parts = [part.strip() for part in SENTENCE_SPLIT_PATTERN.split(normalized) if part.strip()]
        if not parts:
            parts = [normalized]
        sentences.extend(parts)
    return sentences


def _ordered_merge(existing: list[str], incoming: list[str], *, limit: int = PROFILE_LIST_LIMIT) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for raw in [*existing, *incoming]:
        normalized = _sanitize_snippet(raw)
        if not normalized:
            continue
        dedupe_key = WHITESPACE_PATTERN.sub("", normalized).lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        merged.append(normalized)
    if len(merged) <= limit:
        return merged
    return merged[-limit:]


def _extract_by_hints(sentences: list[str], hints: tuple[str, ...]) -> list[str]:
    matched: list[str] = []
    for sentence in sentences:
        normalized = _sanitize_snippet(sentence)
        if not normalized:
            continue
        lowered = normalized.lower()
        if any(hint.lower() in lowered for hint in hints):
            matched.append(normalized)
    return matched


def _compress_profile_context(
    *,
    summary: str | None,
    preferences: list[str],
    business_background: list[str],
    decision_history: list[str],
) -> tuple[str | None, list[str], list[str], list[str]]:
    normalized_summary = _sanitize_snippet(summary) if summary else None
    current_preferences = list(preferences)
    current_background = list(business_background)
    current_decisions = list(decision_history)

    def total_chars() -> int:
        return (
            len(normalized_summary or "")
            + sum(len(item) for item in current_preferences)
            + sum(len(item) for item in current_background)
            + sum(len(item) for item in current_decisions)
        )

    while total_chars() > PROFILE_CONTEXT_BUDGET_CHARS:
        if len(current_background) >= len(current_preferences) and len(current_background) >= len(current_decisions):
            if len(current_background) > 1:
                current_background.pop(0)
                continue
        if len(current_preferences) >= len(current_decisions):
            if len(current_preferences) > 1:
                current_preferences.pop(0)
                continue
        if len(current_decisions) > 1:
            current_decisions.pop(0)
            continue
        break

    if normalized_summary and len(normalized_summary) > PROFILE_SUMMARY_MAX_CHARS:
        normalized_summary = normalized_summary[: PROFILE_SUMMARY_MAX_CHARS - 3].rstrip() + "..."

    return normalized_summary, current_preferences, current_background, current_decisions


def _build_profile_summary(
    *,
    profile: dict[str, Any],
    preferences: list[str],
    business_background: list[str],
    decision_history: list[str],
    last_reception_at: str,
) -> str | None:
    segments: list[str] = []
    company_name = _text(profile.get("company_name") or profile.get("companyName"))
    contact_name = _text(profile.get("contact_name") or profile.get("contactName"))
    if company_name and contact_name:
        segments.append(f"{company_name}，主要联系人 {contact_name}")
    elif company_name:
        segments.append(company_name)
    elif contact_name:
        segments.append(f"联系人 {contact_name}")

    if business_background:
        segments.append(f"长期需求背景：{'；'.join(business_background[:3])}")
    if preferences:
        segments.append(f"业务偏好：{'；'.join(preferences[:3])}")
    if decision_history:
        segments.append(f"历史明确决策：{'；'.join(decision_history[:3])}")
    if last_reception_at:
        segments.append(f"最近接待时间：{last_reception_at}")
    if not segments:
        return None
    return "。".join(segments) + "。"


@dataclass(slots=True)
class ProfileWritebackResult:
    profile_id: str
    updated_fields: list[str]


class CustomerProfileWritebackService:
    def apply_reception_writeback(
        self,
        *,
        message: UnifiedMessage,
        hermes_result: dict[str, Any],
        interaction_mode: str,
    ) -> ProfileWritebackResult | None:
        metadata = message.metadata if isinstance(message.metadata, dict) else {}
        profile_id = _text(
            metadata.get("user_profile_id") or metadata.get("profile_id") or metadata.get("profileId")
        )
        if not profile_id:
            return None

        profile = organization_profile_service.get_profile(
            profile_id,
            current_user=PROFILE_WRITEBACK_ACTOR,
        )
        if not isinstance(profile, dict):
            return None

        requirement_payload = hermes_result.get("requirement_payload")
        if not isinstance(requirement_payload, dict):
            requirement_payload = hermes_result.get("requirementPayload")
        requirement_payload = deepcopy(requirement_payload) if isinstance(requirement_payload, dict) else {}

        source_sentences = _split_sentences(
            message.text,
            requirement_payload.get("summary"),
            requirement_payload.get("details"),
        )
        preference_candidates = _extract_by_hints(source_sentences, PREFERENCE_HINTS)
        background_candidates = _extract_by_hints(source_sentences, BACKGROUND_HINTS)
        decision_candidates = _extract_by_hints(source_sentences, DECISION_HINTS)

        if interaction_mode == "task":
            task_summary = _sanitize_snippet(requirement_payload.get("summary"))
            task_details = _sanitize_snippet(requirement_payload.get("details"))
            if task_summary:
                background_candidates.append(task_summary)
            if task_details:
                background_candidates.append(task_details)

        existing_preferences = _normalize_items(profile.get("preferences"))
        existing_background = _normalize_items(
            profile.get("business_background") or profile.get("businessBackground")
        )
        existing_decisions = _normalize_items(
            profile.get("decision_history") or profile.get("decisionHistory")
        )
        next_preferences = _ordered_merge(existing_preferences, preference_candidates)
        next_background = _ordered_merge(existing_background, background_candidates)
        next_decisions = _ordered_merge(existing_decisions, decision_candidates)

        last_reception_at = _text(message.received_at) or store.now_string()
        next_summary = _build_profile_summary(
            profile=profile,
            preferences=next_preferences,
            business_background=next_background,
            decision_history=next_decisions,
            last_reception_at=last_reception_at,
        )
        next_summary, next_preferences, next_background, next_decisions = _compress_profile_context(
            summary=next_summary,
            preferences=next_preferences,
            business_background=next_background,
            decision_history=next_decisions,
        )

        updates = {
            "profile_summary": next_summary,
            "preferences": next_preferences,
            "business_background": next_background,
            "decision_history": next_decisions,
            "last_reception_at": last_reception_at,
            "last_updated_by": "reception.platform_stateless",
        }
        updated_fields = [
            field_name
            for field_name, value in updates.items()
            if value != profile.get(field_name)
            and value != profile.get(
                "".join(
                    [part.capitalize() if index else part for index, part in enumerate(field_name.split("_"))]
                )
            )
        ]
        if not updated_fields:
            return ProfileWritebackResult(profile_id=profile_id, updated_fields=[])

        organization_profile_service.update_profile(
            profile_id,
            current_user=PROFILE_WRITEBACK_ACTOR,
            changes=updates,
        )
        logger.info(
            "Customer profile writeback applied: profile_id=%s interaction_mode=%s updated_fields=%s",
            profile_id,
            interaction_mode,
            ",".join(updated_fields),
        )
        return ProfileWritebackResult(profile_id=profile_id, updated_fields=updated_fields)


customer_profile_writeback_service = CustomerProfileWritebackService()
