from __future__ import annotations

from copy import deepcopy
import json
import logging
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException

from app.config import get_settings
from app.platform.security.content_policy import apply_content_policy
from app.modules.organization.memory_store.chroma_memory_store import chroma_long_term_memory_store
from app.platform.messaging.redis_client import redis_provider
from app.modules.organization.memory_store.sqlite_memory_store import sqlite_mid_term_memory_store
from app.modules.organization.application.tenancy_service import attach_scope, default_scope
from app.platform.persistence.persistence_service import persistence_service


SHORT_TERM_MAX_TURNS = 20
SHORT_TERM_TTL = timedelta(hours=24)
KEYWORD_LIMIT = 10
DEFAULT_RETRIEVE_LIMIT = 5
SUMMARY_HIGHLIGHT_LIMIT = 4
MIN_DYNAMIC_RETRIEVE_LIMIT = 5
MAX_DYNAMIC_RETRIEVE_LIMIT = 10
MIN_RETRIEVE_SCORE = 0.18
QUERY_PHRASE_BOOST_CAP = 0.14

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}")
DEDUP_WHITESPACE_PATTERN = re.compile(r"[\s\u3000]+")
DEDUP_PUNCTUATION_PATTERN = re.compile(
    r"[`'\"“”‘’，。！？!?,;；:：、（）()\[\]{}<>《》·…—\-_\\/]+"
)
SESSION_TOKEN_PATTERN = re.compile(r"session[a-z0-9_]*")
STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "this",
    "that",
    "from",
    "have",
    "are",
    "you",
    "your",
    "请问",
    "我们",
    "你们",
    "这个",
    "那个",
    "一下",
    "需要",
    "希望",
    "脱敏",
}
MEMORY_REDACTED_PLACEHOLDER_PATTERN = re.compile(r"\[REDACTED_[A-Z_]+\]")
MEMORY_REDACTED_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|session[_-]?token|secret|token)\s*[:=]\s*脱敏\b",
    re.IGNORECASE,
)
MEMORY_REDACTED_BEARER_PATTERN = re.compile(r"\bBearer\s+脱敏\b", re.IGNORECASE)
MEMORY_REDACTED_OTP_PATTERN = re.compile(
    r"(?:(?:验证码|校验码|动态码|otp|one[- ]time password|verification code))(\s*[:：]?\s*)脱敏",
    re.IGNORECASE,
)
MEMORY_LOCAL_ONLY_PASSWORD_PATTERN = re.compile(
    r"\b(?:password|passwd|passcode|pin)\b\s*[:=：]\s*[^\s,;，；]{4,}",
    re.IGNORECASE,
)
MEMORY_LOCAL_ONLY_PASSWORD_CN_PATTERN = re.compile(
    r"(?:密码|口令|口令码)\s*[:=：]\s*[^\s,;，；]{4,}",
    re.IGNORECASE,
)
MEMORY_LOCAL_ONLY_PRIVATE_KEY_PATTERN = re.compile(
    r"(?:-----BEGIN [A-Z ]*PRIVATE KEY-----|私钥|private key)",
    re.IGNORECASE,
)
MEMORY_LOCAL_ONLY_MNEMONIC_PATTERN = re.compile(
    r"(?:助记词|mnemonic|seed phrase)",
    re.IGNORECASE,
)
MEMORY_LOCAL_ONLY_SESSION_SECRET_PATTERN = re.compile(
    r"(?:session[_ -]?(?:key|token)|会话(?:密钥|令牌)|授权码|authorization code|auth code)\s*[:=：]?\s*[A-Za-z0-9._-]{6,}",
    re.IGNORECASE,
)
MEMORY_LOCAL_ONLY_DEBUG_CONTEXT_PATTERN = re.compile(
    r"(?:Traceback \(most recent call last\)|stack trace|Exception:|错误堆栈|调试日志|日志片段|临时调试密钥|仅本地排障(?:使用|日志片段)?|local-debug-secret|trace-debug-token|debug secret|debug token|DEBUG\s+\d{4}-\d{2}-\d{2}|ERROR\s+\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)
MEMORY_GOVERNANCE_FRAGMENT_SPLIT_PATTERN = re.compile(r"[。！？!?；;\n]+")
RETENTION_POLICY_DISTILLABLE = "distillable"
RETENTION_POLICY_LOCAL_ONLY = "local_only"
LOCAL_ONLY_REWRITE_RULE_REASONS = {
    "credential_openai_key": "credential_api_key",
    "credential_telegram_bot_token": "credential_bot_token",
    "credential_bearer_token": "credential_bearer_token",
    "credential_secret_assignment": "credential_secret_assignment",
    "otp_code": "credential_otp",
    "pii_cn_id_card": "pii_cn_id_card",
    "financial_bank_card": "financial_bank_card",
}
LOCAL_ONLY_CONTENT_REASON_PATTERNS = (
    ("credential_password", MEMORY_LOCAL_ONLY_PASSWORD_PATTERN),
    ("credential_password", MEMORY_LOCAL_ONLY_PASSWORD_CN_PATTERN),
    ("credential_session_secret", MEMORY_LOCAL_ONLY_SESSION_SECRET_PATTERN),
    ("secret_private_key", MEMORY_LOCAL_ONLY_PRIVATE_KEY_PATTERN),
    ("secret_mnemonic", MEMORY_LOCAL_ONLY_MNEMONIC_PATTERN),
    ("debug_log_fragment", MEMORY_LOCAL_ONLY_DEBUG_CONTEXT_PATTERN),
)
QUERY_TOKEN_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "周报": ("weekly report", "weekly update", "weekly"),
    "weekly": ("周报", "每周", "周一"),
    "安全": ("security", "secure", "risk control", "风控"),
    "security": ("安全", "secure", "risk"),
    "偏好": ("preference", "prefer", "习惯"),
    "preference": ("偏好", "prefer", "习惯"),
    "中文": ("zh", "chinese"),
    "english": ("en", "英文"),
    "workflow": ("工作流", "调度", "dispatch"),
    "dispatch": ("调度", "workflow", "路由"),
}
MEMORY_TYPE_QUERY_HINTS: dict[str, tuple[str, ...]] = {
    "user_preference": ("偏好", "喜欢", "习惯", "语言", "中文", "英文", "提醒", "每周", "周一", "prefer"),
    "agent_decision": ("决策", "决定", "后续", "将会", "会优先", "计划", "安排", "will"),
    "task_result": ("结果", "完成", "输出", "发送", "草稿", "总结", "生成", "report"),
    "event_digest": ("事件", "发生", "进展", "提醒", "会议", "时间", "weekly"),
}
PREFERENCE_HINTS = (
    "偏好",
    "优先",
    "喜欢",
    "习惯",
    "希望",
    "提醒",
    "每周",
    "周一",
    "language",
    "prefer",
    "preference",
    "weekly",
)
DECISION_HINTS = (
    "我会",
    "将会",
    "会优先",
    "会保持",
    "我将",
    "后续会",
    "后续将",
    "will",
    "i'll",
    "we will",
    "keep",
)
TASK_RESULT_HINTS = (
    "已完成",
    "完成",
    "整理",
    "发送",
    "生成",
    "输出",
    "草稿",
    "总结",
    "安排",
    "write",
    "draft",
    "send",
)

MEMORY_SCOPE_TENANT = "tenant"
MEMORY_SCOPE_GLOBAL = "global"
MEMORY_LAYER_CONVERSATION = "conversation"
MEMORY_LAYER_WORKING = "working"
MEMORY_LAYER_FACT = "fact"
WRITE_SOURCE_BRAIN_INTERNAL = "brain_internal"
WRITE_SOURCE_USER_MESSAGE = "user_message"
WRITE_SOURCE_EXTERNAL_SKILL = "external_skill"
WRITE_SOURCE_EXTERNAL_AGENT = "external_agent"
WRITE_SOURCE_DISTILLATION = "distillation"
TRUST_LEVEL_TRUSTED = "trusted"
TRUST_LEVEL_REVIEWABLE = "reviewable"
TRUST_LEVEL_UNTRUSTED = "untrusted"
MEMORY_STATUS_ACTIVE = "active"
MEMORY_STATUS_ARCHIVED = "archived"
MEMORY_STATUS_DELETED = "deleted"
REVIEW_STATUS_PENDING = "pending"
REVIEW_STATUS_APPROVED = "approved"
REVIEW_STATUS_REJECTED = "rejected"
EXTERNAL_WRITE_SOURCES = {WRITE_SOURCE_EXTERNAL_SKILL, WRITE_SOURCE_EXTERNAL_AGENT}
FACT_MEMORY_TYPES = {"user_preference", "task_result"}
WORKING_MEMORY_TYPES = {"agent_decision"}
CONVERSATION_MEMORY_TYPES = {"session_summary", "event_digest"}
MEMORY_LAYER_RETENTION_DAYS = {
    MEMORY_LAYER_CONVERSATION: 7,
    MEMORY_LAYER_WORKING: 30,
}
LONG_TERM_MEMORY_TYPE_POLICY = {
    "session_summary": {
        "label": "会话摘要",
        "memory_layer_kind": MEMORY_LAYER_CONVERSATION,
        "retention_days": MEMORY_LAYER_RETENTION_DAYS.get(MEMORY_LAYER_CONVERSATION),
        "allowed_scopes": (MEMORY_SCOPE_TENANT, MEMORY_SCOPE_GLOBAL),
        "allowed_write_sources": (WRITE_SOURCE_DISTILLATION,),
    },
    "user_preference": {
        "label": "用户偏好",
        "memory_layer_kind": MEMORY_LAYER_FACT,
        "retention_days": None,
        "allowed_scopes": (MEMORY_SCOPE_TENANT, MEMORY_SCOPE_GLOBAL),
        "allowed_write_sources": (WRITE_SOURCE_DISTILLATION,),
    },
    "agent_decision": {
        "label": "执行决策",
        "memory_layer_kind": MEMORY_LAYER_WORKING,
        "retention_days": MEMORY_LAYER_RETENTION_DAYS.get(MEMORY_LAYER_WORKING),
        "allowed_scopes": (MEMORY_SCOPE_TENANT, MEMORY_SCOPE_GLOBAL),
        "allowed_write_sources": (WRITE_SOURCE_DISTILLATION,),
    },
    "task_result": {
        "label": "任务结果",
        "memory_layer_kind": MEMORY_LAYER_FACT,
        "retention_days": None,
        "allowed_scopes": (MEMORY_SCOPE_TENANT, MEMORY_SCOPE_GLOBAL),
        "allowed_write_sources": (WRITE_SOURCE_DISTILLATION,),
    },
    "event_digest": {
        "label": "关键事件",
        "memory_layer_kind": MEMORY_LAYER_CONVERSATION,
        "retention_days": MEMORY_LAYER_RETENTION_DAYS.get(MEMORY_LAYER_CONVERSATION),
        "allowed_scopes": (MEMORY_SCOPE_TENANT, MEMORY_SCOPE_GLOBAL),
        "allowed_write_sources": (WRITE_SOURCE_DISTILLATION,),
    },
}
LOCAL_ONLY_REASON_DESCRIPTIONS = {
    "credential_api_key": "命中 API Key 等凭据脱敏规则，不允许进入中长期记忆。",
    "credential_bot_token": "命中 Bot Token 脱敏规则，不允许进入中长期记忆。",
    "credential_bearer_token": "命中 Bearer Token 脱敏规则，不允许进入中长期记忆。",
    "credential_secret_assignment": "命中 secret/token 赋值规则，不允许进入中长期记忆。",
    "credential_otp": "命中一次性验证码规则，不允许进入中长期记忆。",
    "pii_cn_id_card": "命中身份证类敏感标识规则，不允许进入中长期记忆。",
    "financial_bank_card": "命中银行卡类敏感标识规则，不允许进入中长期记忆。",
    "credential_password": "命中密码/口令模式，不允许进入中长期记忆。",
    "credential_session_secret": "命中会话密钥/授权码模式，不允许进入中长期记忆。",
    "secret_private_key": "命中私钥内容模式，不允许进入中长期记忆。",
    "secret_mnemonic": "命中助记词/seed phrase 模式，不允许进入中长期记忆。",
    "debug_log_fragment": "命中临时调试日志/排障片段模式，不允许进入中长期记忆。",
}


logger = logging.getLogger(__name__)


def _normalize_identifier_list(values: list[str] | tuple[str, ...] | set[str] | None) -> list[str]:
    if not values:
        return []
    items: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        items.append(normalized)
    return items


class MemoryService:
    def __init__(
        self,
        *,
        redis_provider_override=None,
        mid_term_store_override=None,
        long_term_store_override=None,
        raw_message_store_override=None,
        session_idle_seconds_override: int | None = None,
        weekly_distill_seconds_override: int | None = None,
    ) -> None:
        self._short_term: dict[str, list[dict]] = {}
        self._mid_term: dict[str, list[dict]] = {}
        self._long_term: dict[str, list[dict]] = {}
        self._session_state_cache: dict[tuple[str, str], dict] = {}
        self._redis_provider = redis_provider_override or redis_provider
        self._mid_term_store = mid_term_store_override or sqlite_mid_term_memory_store
        self._long_term_store = long_term_store_override or chroma_long_term_memory_store
        self._raw_message_store = raw_message_store_override or persistence_service
        self._session_idle_seconds = (
            session_idle_seconds_override
            if session_idle_seconds_override is not None
            else int(get_settings().memory_session_idle_seconds)
        )
        self._weekly_distill_seconds = (
            weekly_distill_seconds_override
            if weekly_distill_seconds_override is not None
            else int(get_settings().memory_weekly_distill_seconds)
        )

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _to_iso(dt: datetime) -> str:
        return dt.isoformat()

    @staticmethod
    def _from_iso(value: str) -> datetime:
        return datetime.fromisoformat(value)

    def _get_redis_client(self):
        return self._redis_provider.get_client() if self._redis_provider is not None else None

    def _load_mid_term_bucket(self, user_id: str) -> list[dict]:
        stored_items = (
            self._mid_term_store.list_summaries(user_id)
            if self._mid_term_store is not None
            else None
        )
        if stored_items is None:
            return list(self._mid_term.get(user_id, []))

        authoritative_items = sorted(
            deepcopy(list(stored_items)),
            key=lambda item: (item.get("created_at", ""), item["id"]),
        )
        if authoritative_items:
            self._mid_term[user_id] = deepcopy(authoritative_items)
        else:
            self._mid_term.pop(user_id, None)
        return authoritative_items

    def _load_long_term_bucket(self, user_id: str) -> list[dict]:
        runtime_items = list(self._long_term.get(user_id, []))
        stored_items = (
            self._long_term_store.list_memories(user_id)
            if self._long_term_store is not None
            else None
        )
        if stored_items is None:
            return runtime_items

        authoritative_items = sorted(
            [
                deepcopy(item)
                for item in stored_items
                if str(item.get("id") or "").strip()
            ],
            key=lambda item: (item.get("created_at", ""), item["id"]),
        )
        if authoritative_items:
            self._long_term[user_id] = deepcopy(authoritative_items)
            return authoritative_items
        if runtime_items:
            return deepcopy(runtime_items)
        self._long_term.pop(user_id, None)
        return authoritative_items

    @staticmethod
    def _short_term_key(user_id: str) -> str:
        return f"memory:short:{user_id}"

    def _append_raw_message(self, item: dict) -> None:
        append_message = getattr(self._raw_message_store, "append_conversation_message", None)
        if append_message is None:
            return
        try:
            append_message(item)
        except Exception as exc:  # pragma: no cover - defensive fallback for external stores
            logger.warning("Raw conversation log append failed: %s", exc)

    @staticmethod
    def _session_state_key(user_id: str, session_id: str) -> tuple[str, str]:
        return (user_id, session_id)

    def _load_persisted_memory_session_state(
        self,
        *,
        user_id: str,
        session_id: str,
    ) -> tuple[dict | None, bool]:
        get_state = getattr(self._raw_message_store, "get_memory_session_state", None)
        if get_state is None:
            return None, False

        cache_key = self._session_state_key(user_id, session_id)
        try:
            persisted_state = get_state(
                user_id=user_id,
                session_id=session_id,
            )
        except Exception as exc:  # pragma: no cover - defensive fallback for external stores
            logger.warning(
                "Memory session state load failed for user %s session %s: %s",
                user_id,
                session_id,
                exc,
            )
            return None, False

        if persisted_state is None:
            self._session_state_cache.pop(cache_key, None)
            return None, True
        if not isinstance(persisted_state, dict):
            return None, False

        normalized_state = dict(persisted_state)
        self._session_state_cache[cache_key] = normalized_state
        return dict(normalized_state), True

    def _get_memory_session_state(
        self,
        *,
        user_id: str,
        session_id: str,
    ) -> dict | None:
        normalized_user_id = str(user_id or "").strip()
        normalized_session_id = str(session_id or "").strip()
        if not normalized_user_id or not normalized_session_id:
            return None

        cache_key = self._session_state_key(normalized_user_id, normalized_session_id)
        persisted_state, persisted_authoritative = self._load_persisted_memory_session_state(
            user_id=normalized_user_id,
            session_id=normalized_session_id,
        )
        if persisted_authoritative:
            return dict(persisted_state) if persisted_state is not None else None

        cached_state = self._session_state_cache.get(cache_key)
        if cached_state is not None:
            return dict(cached_state)
        return None

    def _set_memory_session_state(self, state: dict) -> None:
        normalized_user_id = str(state.get("user_id") or "").strip()
        normalized_session_id = str(state.get("session_id") or "").strip()
        if not normalized_user_id or not normalized_session_id:
            return

        normalized_state = {
            "user_id": normalized_user_id,
            "session_id": normalized_session_id,
            "last_distilled_message_created_at": str(
                state.get("last_distilled_message_created_at") or ""
            ).strip(),
            "last_distilled_message_ids_at_created_at": [
                str(item).strip()
                for item in state.get("last_distilled_message_ids_at_created_at", [])
                if str(item).strip()
            ],
            "updated_at": str(state.get("updated_at") or "").strip(),
        }
        self._session_state_cache[
            self._session_state_key(normalized_user_id, normalized_session_id)
        ] = dict(normalized_state)

        upsert_state = getattr(self._raw_message_store, "upsert_memory_session_state", None)
        if upsert_state is None:
            return

        try:
            upsert_state(dict(normalized_state))
        except Exception as exc:  # pragma: no cover - defensive fallback for external stores
            logger.warning(
                "Memory session state persist failed for user %s session %s: %s",
                normalized_user_id,
                normalized_session_id,
                exc,
            )

    def _is_after_distill_watermark(self, item: dict, state: dict | None) -> bool:
        if not isinstance(state, dict):
            return True

        boundary_created_at = str(state.get("last_distilled_message_created_at") or "").strip()
        if not boundary_created_at:
            return True

        item_created_at = str(item.get("created_at") or "").strip()
        if not item_created_at:
            return True

        item_created_dt = self._from_iso(item_created_at)
        boundary_created_dt = self._from_iso(boundary_created_at)
        if item_created_dt > boundary_created_dt:
            return True
        if item_created_dt < boundary_created_dt:
            return False

        consumed_ids = {
            str(message_id).strip()
            for message_id in state.get("last_distilled_message_ids_at_created_at", [])
            if str(message_id).strip()
        }
        return str(item.get("id") or "").strip() not in consumed_ids

    def _apply_session_watermark(
        self,
        *,
        user_id: str,
        session_id: str,
        items: list[dict],
    ) -> list[dict]:
        state = self._get_memory_session_state(user_id=user_id, session_id=session_id)
        if state is None:
            return list(items)
        return [item for item in items if self._is_after_distill_watermark(item, state)]

    def _emit_distill_internal_event(
        self,
        *,
        user_id: str,
        session_id: str,
        trigger: str,
        source_items: list[dict],
        mid_term: dict,
        long_term: dict,
        long_term_items: list[dict] | None = None,
    ) -> None:
        from app.modules.dispatch.workflow_runtime.workflow_service import (
            has_internal_event_subscribers,
            trigger_workflow_internal,
        )

        normalized_long_term_items = list(long_term_items or [long_term])
        payload = {
            "userId": user_id,
            "sessionId": session_id,
            "trigger": trigger,
            "midTermId": mid_term["id"],
            "longTermId": long_term["id"],
            "longTermIds": [str(item.get("id") or "") for item in normalized_long_term_items],
            "longTermCount": len(normalized_long_term_items),
            "memoryTypes": [
                str(item.get("memory_type") or "session_summary")
                for item in normalized_long_term_items
                if str(item.get("memory_type") or "session_summary")
            ],
            "sourceCount": len(source_items),
        }
        keywords = list(mid_term.get("keywords") or [])
        if keywords:
            payload["keywords"] = keywords[:6]

        try:
            if not has_internal_event_subscribers("memory.distilled"):
                logger.debug(
                    "Skipping memory.distilled internal event because no workflow subscribers are configured"
                )
                return
            trigger_workflow_internal(
                "memory.distilled",
                payload,
                source="Memory Service",
                idempotency_key=f"memory.distilled:{mid_term['id']}:{long_term['id']}",
            )
        except HTTPException as exc:
            if exc.status_code == 404 and str(exc.detail) == "Workflow internal trigger not found":
                logger.debug(
                    "Skipping memory.distilled internal event because no workflow subscribers are configured"
                )
                return
            logger.warning(
                "Memory distill internal event emission failed for user %s session %s: %s",
                user_id,
                session_id,
                exc,
            )
        except Exception as exc:  # pragma: no cover - fail-open for workflow integration
            logger.warning(
                "Memory distill internal event emission failed for user %s session %s: %s",
                user_id,
                session_id,
                exc,
            )

    def _load_raw_session_messages(
        self,
        *,
        user_id: str,
        session_id: str,
        include_consumed: bool = False,
    ) -> list[dict]:
        list_messages = getattr(self._raw_message_store, "list_conversation_messages", None)
        if list_messages is None:
            return []
        try:
            items = list_messages(
                user_id=user_id,
                session_id=session_id,
                limit=SHORT_TERM_MAX_TURNS,
            )
        except Exception as exc:  # pragma: no cover - defensive fallback for external stores
            logger.warning("Raw conversation log load failed: %s", exc)
            return []
        if items is None:
            return []
        loaded_items = list(items)
        if include_consumed:
            return loaded_items
        return self._apply_session_watermark(
            user_id=user_id,
            session_id=session_id,
            items=loaded_items,
        )

    def _load_raw_session_messages_full(
        self,
        *,
        user_id: str,
        session_id: str,
        include_consumed: bool = False,
    ) -> list[dict]:
        list_messages = getattr(self._raw_message_store, "list_conversation_messages", None)
        if list_messages is None:
            return []
        try:
            items = list_messages(
                user_id=user_id,
                session_id=session_id,
                limit=None,
            )
        except Exception as exc:  # pragma: no cover - defensive fallback for external stores
            logger.warning("Raw conversation full session load failed: %s", exc)
            return []
        if items is None:
            return []
        loaded_items = list(items)
        if include_consumed:
            return loaded_items
        return self._apply_session_watermark(
            user_id=user_id,
            session_id=session_id,
            items=loaded_items,
        )

    def _load_persisted_short_term_bucket(
        self,
        user_id: str,
        *,
        now: datetime | None = None,
    ) -> tuple[list[dict], bool]:
        persistence_enabled = bool(getattr(self._raw_message_store, "enabled", False))
        list_messages = getattr(self._raw_message_store, "list_conversation_messages", None)
        if list_messages is None:
            return [], persistence_enabled

        try:
            items = list_messages(
                user_id=user_id,
                session_id=None,
                limit=None,
            )
        except Exception as exc:  # pragma: no cover - defensive fallback for external stores
            logger.warning("Raw conversation short-term load failed: %s", exc)
            return [], persistence_enabled

        if items is None:
            return [], persistence_enabled

        current = now or self._now()
        threshold = current - SHORT_TERM_TTL
        kept: list[dict] = []
        session_state_cache: dict[str, dict | None] = {}
        for item in list(items):
            if self._from_iso(str(item.get("created_at") or "")) < threshold:
                continue

            session_id = str(item.get("session_id") or "").strip()
            if session_id:
                if session_id not in session_state_cache:
                    session_state_cache[session_id] = self._get_memory_session_state(
                        user_id=user_id,
                        session_id=session_id,
                    )
                if not self._is_after_distill_watermark(item, session_state_cache[session_id]):
                    continue

            kept.append(item)
        return kept[-SHORT_TERM_MAX_TURNS:], True

    def _write_redis_short_term(self, user_id: str, items: list[dict]) -> bool:
        client = self._get_redis_client()
        if client is None:
            return False

        key = self._short_term_key(user_id)
        trimmed_items = items[-SHORT_TERM_MAX_TURNS:]
        try:
            client.delete(key)
            if trimmed_items:
                payloads = [json.dumps(item, ensure_ascii=False) for item in trimmed_items]
                client.rpush(key, *payloads)
                client.expire(key, int(SHORT_TERM_TTL.total_seconds()))
            return True
        except Exception as exc:
            logger.warning("Redis short-term memory write failed, using in-memory fallback: %s", exc)
            return False

    def _read_redis_short_term(self, user_id: str) -> list[dict] | None:
        client = self._get_redis_client()
        if client is None:
            return None

        try:
            raw_items = client.lrange(self._short_term_key(user_id), 0, -1)
        except Exception as exc:
            logger.warning("Redis short-term memory read failed, using in-memory fallback: %s", exc)
            return None

        parsed_items: list[dict] = []
        for raw_item in raw_items:
            try:
                parsed_items.append(json.loads(raw_item))
            except json.JSONDecodeError:
                continue
        return parsed_items

    @staticmethod
    def _normalize_scope(scope: dict | None) -> dict[str, str]:
        resolved = default_scope()
        if not isinstance(scope, dict):
            return resolved
        for key in ("tenant_id", "project_id", "environment"):
            value = str(scope.get(key) or "").strip()
            if value:
                resolved[key] = value
        return resolved

    @staticmethod
    def _normalize_memory_scope(value: str | None) -> str:
        normalized = str(value or "").strip().lower()
        if normalized == MEMORY_SCOPE_GLOBAL:
            return MEMORY_SCOPE_GLOBAL
        return MEMORY_SCOPE_TENANT

    @staticmethod
    def _normalize_write_source(value: str | None, *, default: str = WRITE_SOURCE_BRAIN_INTERNAL) -> str:
        normalized = str(value or "").strip().lower()
        if normalized in {
            WRITE_SOURCE_BRAIN_INTERNAL,
            WRITE_SOURCE_USER_MESSAGE,
            WRITE_SOURCE_EXTERNAL_SKILL,
            WRITE_SOURCE_EXTERNAL_AGENT,
            WRITE_SOURCE_DISTILLATION,
        }:
            return normalized
        return default

    @staticmethod
    def _normalize_trust_level(value: str | None, *, default: str = TRUST_LEVEL_TRUSTED) -> str:
        normalized = str(value or "").strip().lower()
        if normalized in {TRUST_LEVEL_TRUSTED, TRUST_LEVEL_REVIEWABLE, TRUST_LEVEL_UNTRUSTED}:
            return normalized
        return default

    @classmethod
    def _long_term_memory_type_policy(cls, memory_type: str) -> dict[str, object]:
        normalized = str(memory_type or "").strip().lower()
        policy = LONG_TERM_MEMORY_TYPE_POLICY.get(normalized)
        if policy is None:
            raise HTTPException(status_code=422, detail=f"Unsupported long-term memory type: {memory_type}")
        return dict(policy)

    @classmethod
    def _memory_layer_kind_for_long_term_type(cls, memory_type: str) -> str:
        policy = cls._long_term_memory_type_policy(memory_type)
        return str(policy["memory_layer_kind"])

    @classmethod
    def governance_snapshot(cls) -> dict[str, object]:
        long_term_whitelist = [
            {
                "memory_type": memory_type,
                "label": str(policy.get("label") or memory_type),
                "memory_layer_kind": str(policy.get("memory_layer_kind") or MEMORY_LAYER_CONVERSATION),
                "retention_days": policy.get("retention_days"),
                "allowed_scopes": list(policy.get("allowed_scopes") or (MEMORY_SCOPE_TENANT,)),
                "allowed_write_sources": list(policy.get("allowed_write_sources") or (WRITE_SOURCE_DISTILLATION,)),
            }
            for memory_type, policy in sorted(LONG_TERM_MEMORY_TYPE_POLICY.items())
        ]
        return {
            "long_term_whitelist": long_term_whitelist,
            "local_only_reason_codes": [
                {
                    "code": code,
                    "description": LOCAL_ONLY_REASON_DESCRIPTIONS.get(code, ""),
                }
                for code in sorted(
                    {
                        *LOCAL_ONLY_REWRITE_RULE_REASONS.values(),
                        *(reason for reason, _pattern in LOCAL_ONLY_CONTENT_REASON_PATTERNS),
                    }
                )
            ],
            "supported_memory_scopes": [MEMORY_SCOPE_TENANT, MEMORY_SCOPE_GLOBAL],
            "restricted_external_write_sources": sorted(EXTERNAL_WRITE_SOURCES),
            "retention_days": dict(MEMORY_LAYER_RETENTION_DAYS),
            "review_flow": [REVIEW_STATUS_PENDING, REVIEW_STATUS_APPROVED, REVIEW_STATUS_REJECTED],
            "lifecycle_statuses": [MEMORY_STATUS_ACTIVE, MEMORY_STATUS_ARCHIVED, MEMORY_STATUS_DELETED],
        }

    def _memory_expiry(self, memory_layer_kind: str, *, created_at: str) -> str | None:
        retention_days = MEMORY_LAYER_RETENTION_DAYS.get(memory_layer_kind)
        if retention_days is None:
            return None
        try:
            created_dt = self._from_iso(created_at)
        except ValueError:
            return None
        return self._to_iso(created_dt + timedelta(days=retention_days))

    def _governance_defaults(
        self,
        *,
        scope: dict | None,
        memory_scope: str,
        memory_layer_kind: str,
        write_source: str,
        trust_level: str,
        created_at: str,
    ) -> dict:
        normalized_scope = self._normalize_scope(scope)
        normalized_memory_scope = self._normalize_memory_scope(memory_scope)
        normalized_write_source = self._normalize_write_source(write_source)
        normalized_trust = self._normalize_trust_level(trust_level)
        return {
            **normalized_scope,
            "memory_scope": normalized_memory_scope,
            "memory_layer_kind": memory_layer_kind,
            "write_source": normalized_write_source,
            "trust_level": normalized_trust,
            "retention_policy": RETENTION_POLICY_DISTILLABLE,
            "local_only_reasons": [],
            "local_only_filtered_count": 0,
            "memory_status": MEMORY_STATUS_ACTIVE,
            "review_status": (
                REVIEW_STATUS_PENDING
                if normalized_trust in {TRUST_LEVEL_REVIEWABLE, TRUST_LEVEL_UNTRUSTED}
                else REVIEW_STATUS_APPROVED
            ),
            "reviewed_by": None,
            "reviewed_at": None,
            "review_note": None,
            "expires_at": self._memory_expiry(memory_layer_kind, created_at=created_at),
            "archived_at": None,
            "deleted_at": None,
            "corrected_at": None,
        }

    def _apply_governance_defaults(
        self,
        item: dict,
        *,
        scope: dict | None,
        memory_scope: str,
        memory_layer_kind: str,
        write_source: str,
        trust_level: str,
    ) -> dict:
        payload = attach_scope(item, scope=self._normalize_scope(scope))
        payload.update(
            self._governance_defaults(
                scope=scope,
                memory_scope=memory_scope,
                memory_layer_kind=memory_layer_kind,
                write_source=write_source,
                trust_level=trust_level,
                created_at=str(payload.get("created_at") or self._to_iso(self._now())),
            )
        )
        return payload

    def _enforce_memory_write_policy(
        self,
        *,
        target_layer: str,
        write_source: str,
        trust_level: str,
        memory_scope: str,
    ) -> None:
        normalized_source = self._normalize_write_source(write_source)
        normalized_trust = self._normalize_trust_level(trust_level)
        normalized_scope = self._normalize_memory_scope(memory_scope)
        if target_layer in {"mid_term", "long_term"} and normalized_source in EXTERNAL_WRITE_SOURCES:
            raise HTTPException(
                status_code=403,
                detail="External skills/agents cannot write governed mid/long-term memory",
            )
        if normalized_source in EXTERNAL_WRITE_SOURCES and normalized_trust == TRUST_LEVEL_TRUSTED:
            raise HTTPException(
                status_code=403,
                detail="External skills/agents cannot create trusted memory directly",
            )
        if normalized_scope == MEMORY_SCOPE_GLOBAL and normalized_source != WRITE_SOURCE_BRAIN_INTERNAL:
            raise HTTPException(
                status_code=403,
                detail="Global memory is reserved for brain-internal governance paths",
            )

    @staticmethod
    def _memory_visible_in_scope(item: dict, scope: dict) -> bool:
        normalized_scope = MemoryService._normalize_scope(scope)
        memory_scope = str(item.get("memory_scope") or MEMORY_SCOPE_TENANT).strip().lower()
        has_explicit_scope = any(
            str(item.get(key) or "").strip()
            for key in ("tenant_id", "project_id", "environment")
        )
        if not has_explicit_scope:
            return True
        item_environment = str(item.get("environment") or normalized_scope["environment"]).strip()
        if item_environment and item_environment != normalized_scope["environment"]:
            return False
        if memory_scope == MEMORY_SCOPE_GLOBAL:
            return True
        return (
            str(item.get("tenant_id") or "").strip() == normalized_scope["tenant_id"]
            and str(item.get("project_id") or "").strip() == normalized_scope["project_id"]
            and item_environment == normalized_scope["environment"]
        )

    def _memory_active_for_retrieval(self, item: dict, *, include_untrusted: bool = False) -> bool:
        status = str(item.get("memory_status") or MEMORY_STATUS_ACTIVE).strip().lower()
        review_status = str(item.get("review_status") or REVIEW_STATUS_APPROVED).strip().lower()
        trust_level = str(item.get("trust_level") or TRUST_LEVEL_TRUSTED).strip().lower()
        if status != MEMORY_STATUS_ACTIVE:
            return False
        if review_status == REVIEW_STATUS_REJECTED:
            return False
        if not include_untrusted and trust_level != TRUST_LEVEL_TRUSTED:
            return False
        return True

    def _filter_memory_items(
        self,
        items: list[dict],
        *,
        scope: dict | None,
        memory_scope: str | None = None,
        include_inactive: bool = False,
        include_untrusted: bool = False,
    ) -> list[dict]:
        normalized_scope = self._normalize_scope(scope)
        requested_memory_scope = self._normalize_memory_scope(memory_scope) if memory_scope else None
        filtered: list[dict] = []
        for item in items:
            if not self._memory_visible_in_scope(item, normalized_scope):
                continue
            item_memory_scope = str(item.get("memory_scope") or MEMORY_SCOPE_TENANT).strip().lower()
            if requested_memory_scope is not None and item_memory_scope != requested_memory_scope:
                continue
            if not include_inactive and not self._memory_active_for_retrieval(
                item,
                include_untrusted=include_untrusted,
            ):
                continue
            filtered.append(item)
        return filtered

    @staticmethod
    def _scope_breakdown(items: list[dict]) -> dict[str, int]:
        tenant_count = 0
        global_count = 0
        for item in items:
            memory_scope = str(item.get("memory_scope") or MEMORY_SCOPE_TENANT).strip().lower()
            if memory_scope == MEMORY_SCOPE_GLOBAL:
                global_count += 1
            else:
                tenant_count += 1
        return {
            "tenant": tenant_count,
            "global": global_count,
            "total": tenant_count + global_count,
        }

    def _tokenize(self, text: str) -> list[str]:
        tokens = TOKEN_PATTERN.findall(text.lower())
        filtered: list[str] = []
        for token in tokens:
            is_chinese_token = all("\u4e00" <= ch <= "\u9fff" for ch in token)
            if is_chinese_token and len(token) > 2:
                # Keep phrase token and split into bi-grams for simple semantic overlap.
                filtered.append(token)
                for idx in range(len(token) - 1):
                    part = token[idx : idx + 2]
                    if part not in STOPWORDS:
                        filtered.append(part)
                continue

            if len(token) < 2:
                continue
            if token in STOPWORDS:
                continue
            filtered.append(token)
        return filtered

    def _extract_keywords(self, texts: list[str]) -> list[str]:
        counter: Counter[str] = Counter()
        for text in texts:
            for token in self._tokenize(text):
                counter[token] += 1
        return [token for token, _ in counter.most_common(KEYWORD_LIMIT)]

    def _extract_entities(self, texts: list[str]) -> list[str]:
        counter: Counter[str] = Counter()
        for text in texts:
            for token in self._tokenize(text):
                if token.isdigit():
                    continue
                counter[token] += 1
        return [token for token, _ in counter.most_common(5)]

    @staticmethod
    def _normalize_sentence(text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text.strip())
        return cleaned.strip("。；;，, ")

    @staticmethod
    def _canonicalize_for_dedupe(value: object) -> str:
        normalized = str(value or "").strip().lower()
        if not normalized:
            return ""
        normalized = DEDUP_WHITESPACE_PATTERN.sub(" ", normalized)
        normalized = DEDUP_PUNCTUATION_PATTERN.sub("", normalized)
        return normalized.replace(" ", "").strip()

    def _split_sentences(self, text: str) -> list[str]:
        chunks = re.split(r"[\n。！？!?；;]+", text)
        items = [self._normalize_sentence(chunk) for chunk in chunks]
        return [item for item in items if item]

    @staticmethod
    def _ordered_unique(items: list[str], *, limit: int = SUMMARY_HIGHLIGHT_LIMIT) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for item in items:
            normalized = item.strip()
            dedupe_key = MemoryService._canonicalize_for_dedupe(normalized) or normalized
            if not normalized or dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            ordered.append(normalized)
            if len(ordered) >= limit:
                break
        return ordered

    @staticmethod
    def _merge_matched_terms(
        existing_terms: list[object] | None,
        extra_terms: list[object] | None,
        *,
        limit: int = 8,
    ) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for raw_term in [*(existing_terms or []), *(extra_terms or [])]:
            normalized = str(raw_term).strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            merged.append(normalized)
            if len(merged) >= limit:
                break
        return merged

    @staticmethod
    def _matches_hint(sentence: str, hints: tuple[str, ...]) -> bool:
        lowered = sentence.lower()
        return any(hint in lowered for hint in hints)

    def _extract_structured_highlights(self, source_items: list[dict]) -> dict[str, list[str]]:
        preferences: list[str] = []
        decisions: list[str] = []
        task_results: list[str] = []
        events: list[str] = []

        for item in source_items:
            role = str(item.get("role") or "user").lower()
            content = str(item.get("content") or "").strip()
            if not content:
                continue

            sentences = self._split_sentences(content) or [self._normalize_sentence(content)]
            for sentence in sentences:
                if not sentence:
                    continue
                if role == "user" and self._matches_hint(sentence, PREFERENCE_HINTS):
                    preferences.append(sentence)
                if role == "assistant" and self._matches_hint(sentence, DECISION_HINTS):
                    decisions.append(sentence)
                if self._matches_hint(sentence, TASK_RESULT_HINTS):
                    task_results.append(sentence)
                events.append(sentence[:80])

        return {
            "preferences": self._ordered_unique(preferences),
            "decisions": self._ordered_unique(decisions),
            "task_results": self._ordered_unique(task_results),
            "events": self._ordered_unique(events),
        }

    @staticmethod
    def _sanitize_memory_text(value: str) -> str:
        cleaned = str(value or "").strip()
        if not cleaned:
            return ""
        rewritten, _, _, rewrite_diffs = apply_content_policy(cleaned)
        if not rewrite_diffs:
            return cleaned
        sanitized = MEMORY_REDACTED_PLACEHOLDER_PATTERN.sub("脱敏", rewritten)
        sanitized = MEMORY_REDACTED_BEARER_PATTERN.sub("脱敏", sanitized)
        sanitized = MEMORY_REDACTED_SECRET_ASSIGNMENT_PATTERN.sub("脱敏", sanitized)
        sanitized = MEMORY_REDACTED_OTP_PATTERN.sub(r"\1脱敏", sanitized)
        sanitized = re.sub(r"\s+", " ", sanitized).strip()
        return sanitized or "脱敏"

    @staticmethod
    def _memory_governance_fragments(value: str) -> list[str]:
        raw_text = str(value or "").strip()
        if not raw_text:
            return []
        fragments = [
            fragment.strip()
            for fragment in MEMORY_GOVERNANCE_FRAGMENT_SPLIT_PATTERN.split(raw_text)
            if fragment.strip()
        ]
        return fragments or [raw_text]

    def _memory_governance_subfragments(self, fragment: str) -> list[str]:
        normalized_fragment = str(fragment or "").strip()
        if not normalized_fragment:
            return []
        if "，" not in normalized_fragment and "," not in normalized_fragment:
            return [normalized_fragment]
        if not self._local_only_reasons_for_content(normalized_fragment):
            return [normalized_fragment]
        subfragments = [
            part.strip()
            for part in re.split(r"[，,]+", normalized_fragment)
            if part.strip()
        ]
        return subfragments or [normalized_fragment]

    def _local_only_reasons_for_content(self, value: str) -> list[str]:
        raw_text = str(value or "").strip()
        if not raw_text:
            return []
        _, _, _, rewrite_diffs = apply_content_policy(raw_text)
        reasons: list[str] = []
        for diff in rewrite_diffs:
            rule = str(diff.get("rule") or "").strip()
            reason = LOCAL_ONLY_REWRITE_RULE_REASONS.get(rule)
            if reason:
                reasons.append(reason)
        for reason, pattern in LOCAL_ONLY_CONTENT_REASON_PATTERNS:
            if pattern.search(raw_text):
                reasons.append(reason)
        return self._ordered_unique(reasons, limit=max(len(reasons), 1))

    def _retention_policy_for_content(self, value: str) -> tuple[str, list[str]]:
        reasons = self._local_only_reasons_for_content(value)
        if reasons:
            return RETENTION_POLICY_LOCAL_ONLY, reasons
        return RETENTION_POLICY_DISTILLABLE, []

    def _govern_source_items_for_distillation(
        self,
        source_items: list[dict],
    ) -> tuple[list[dict], dict[str, object]]:
        governed_items: list[dict] = []
        filtered_items: list[dict[str, object]] = []
        filtered_reason_counts: Counter[str] = Counter()
        for item in source_items:
            raw_content = str(item.get("content") or "")
            retained_fragments: list[str] = []
            item_filtered_count = 0
            item_reason_counts: Counter[str] = Counter()

            for fragment in self._memory_governance_fragments(raw_content):
                for subfragment in self._memory_governance_subfragments(fragment):
                    retention_policy, reasons = self._retention_policy_for_content(subfragment)
                    if retention_policy == RETENTION_POLICY_LOCAL_ONLY:
                        item_filtered_count += 1
                        item_reason_counts.update(reasons)
                        filtered_reason_counts.update(reasons)
                        filtered_items.append(
                            {
                                "message_id": str(item.get("id") or ""),
                                "session_id": str(item.get("session_id") or ""),
                                "fragment": subfragment,
                                "reasons": list(reasons),
                            }
                        )
                        continue
                    sanitized_fragment = self._sanitize_memory_text(subfragment)
                    if sanitized_fragment:
                        retained_fragments.append(sanitized_fragment)

            if not retained_fragments:
                continue

            sanitized_item = dict(item)
            sanitized_item["content"] = "。".join(retained_fragments)
            sanitized_item["retention_policy"] = RETENTION_POLICY_DISTILLABLE
            sanitized_item["local_only_reasons"] = sorted(item_reason_counts.keys())
            sanitized_item["local_only_filtered_count"] = item_filtered_count
            governed_items.append(sanitized_item)

        return governed_items, {
            "local_only_filtered_count": len(filtered_items),
            "local_only_reasons": sorted(filtered_reason_counts.keys()),
            "local_only_reason_counts": dict(filtered_reason_counts),
            "local_only_filtered_items": filtered_items,
        }

    def _build_hierarchical_summary(
        self,
        *,
        session_id: str,
        source_count: int,
        entities: list[str],
        keywords: list[str],
        highlights: dict[str, list[str]],
    ) -> str:
        summary_segments = [f"会话 {session_id} 共沉淀 {source_count} 轮消息"]
        if highlights["preferences"]:
            summary_segments.append(f"偏好：{'；'.join(highlights['preferences'][:3])}")
        if highlights["decisions"]:
            summary_segments.append(f"决策：{'；'.join(highlights['decisions'][:3])}")
        if highlights["task_results"]:
            summary_segments.append(f"任务结果：{'；'.join(highlights['task_results'][:3])}")
        if highlights["events"]:
            summary_segments.append(f"关键事件：{'；'.join(highlights['events'][:3])}")
        if entities:
            summary_segments.append(f"实体：{', '.join(entities[:4])}")
        if keywords:
            summary_segments.append(f"关键词：{', '.join(keywords[:6])}")
        return "。".join(summary_segments) + "。"

    def _build_long_term_memories(
        self,
        *,
        user_id: str,
        session_id: str,
        source_mid_term_id: str,
        summary_text: str,
        keywords: list[str],
        highlights: dict[str, list[str]],
        created_at: str,
        scope: dict | None,
        memory_scope: str,
        trust_level: str,
    ) -> list[dict]:
        session_sections = [summary_text]
        if highlights["preferences"]:
            session_sections.append(f"偏好：{'；'.join(highlights['preferences'][:3])}")
        if highlights["decisions"]:
            session_sections.append(f"决策：{'；'.join(highlights['decisions'][:3])}")
        if highlights["task_results"]:
            session_sections.append(f"任务结果：{'；'.join(highlights['task_results'][:3])}")
        if highlights["events"]:
            session_sections.append(f"关键事件：{'；'.join(highlights['events'][:3])}")

        memories: list[dict] = [
            self._apply_governance_defaults(
                {
                    "id": f"lng-{uuid4().hex[:12]}",
                    "user_id": user_id,
                    "source_mid_term_id": source_mid_term_id,
                    "memory_type": "session_summary",
                    "summary": summary_text,
                    "memory_text": "\n".join(session_sections),
                    "keywords": keywords,
                    "created_at": created_at,
                },
                scope=scope,
                memory_scope=memory_scope,
                memory_layer_kind=self._memory_layer_kind_for_long_term_type("session_summary"),
                write_source=WRITE_SOURCE_DISTILLATION,
                trust_level=trust_level,
            )
        ]

        typed_sections = [
            ("user_preference", "用户偏好", highlights["preferences"]),
            ("agent_decision", "执行决策", highlights["decisions"]),
            ("task_result", "任务结果", highlights["task_results"]),
            ("event_digest", "关键事件", highlights["events"]),
        ]
        for memory_type, label, items in typed_sections:
            if not items:
                continue
            section_keywords = self._extract_keywords([summary_text, *items])
            memories.append(
                self._apply_governance_defaults(
                    {
                        "id": f"lng-{uuid4().hex[:12]}",
                        "user_id": user_id,
                        "source_mid_term_id": source_mid_term_id,
                        "memory_type": memory_type,
                        "summary": f"{label}：{'；'.join(items[:3])}",
                        "memory_text": f"{label}（会话 {session_id}）：{'；'.join(items[:4])}",
                        "keywords": section_keywords,
                        "created_at": created_at,
                    },
                    scope=scope,
                    memory_scope=memory_scope,
                    memory_layer_kind=self._memory_layer_kind_for_long_term_type(memory_type),
                    write_source=WRITE_SOURCE_DISTILLATION,
                    trust_level=trust_level,
                )
            )

        return memories

    @staticmethod
    def _memory_type_boost(memory_type: str, query: str) -> float:
        normalized_type = str(memory_type or "").strip().lower()
        if normalized_type == "session_summary":
            return 0.0
        lowered_query = str(query or "").strip().lower()
        hints = MEMORY_TYPE_QUERY_HINTS.get(normalized_type, ())
        if any(hint in lowered_query for hint in hints):
            return 0.08
        return 0.02

    def _session_latest_timestamps(self, items: list[dict]) -> dict[str, datetime]:
        timestamps: dict[str, datetime] = {}
        for item in items:
            session_id = str(item.get("session_id") or "").strip()
            created_at = self._from_iso(item["created_at"])
            if not session_id:
                continue
            known = timestamps.get(session_id)
            if known is None or created_at > known:
                timestamps[session_id] = created_at
        return timestamps

    def _latest_mid_term_timestamp(
        self,
        user_id: str,
        *,
        trigger: str | None = None,
        session_id: str | None = None,
    ) -> datetime | None:
        latest: datetime | None = None
        for item in self._load_mid_term_bucket(user_id):
            if trigger is not None and str(item.get("trigger") or "") != trigger:
                continue
            if session_id is not None and str(item.get("session_id") or "") != session_id:
                continue
            created_at = self._from_iso(str(item.get("created_at") or ""))
            if latest is None or created_at > latest:
                latest = created_at
        return latest

    @staticmethod
    def _merge_distilled_message_ids(existing_ids: list[str], extra_ids: list[str]) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for candidate in [*existing_ids, *extra_ids]:
            normalized = str(candidate).strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)
        return ordered

    def _build_session_state_updates(
        self,
        *,
        user_id: str,
        source_items: list[dict],
        updated_at: str,
    ) -> list[dict]:
        latest_by_session: dict[str, dict] = {}

        for item in source_items:
            session_id = str(item.get("session_id") or "").strip()
            item_id = str(item.get("id") or "").strip()
            created_at = str(item.get("created_at") or "").strip()
            if not session_id or not item_id or not created_at:
                continue

            current_state = latest_by_session.get(session_id)
            if current_state is None:
                latest_by_session[session_id] = {
                    "user_id": user_id,
                    "session_id": session_id,
                    "last_distilled_message_created_at": created_at,
                    "last_distilled_message_ids_at_created_at": [item_id],
                    "updated_at": updated_at,
                }
                continue

            current_created_at = str(current_state["last_distilled_message_created_at"])
            item_created_dt = self._from_iso(created_at)
            current_created_dt = self._from_iso(current_created_at)
            if item_created_dt > current_created_dt:
                latest_by_session[session_id] = {
                    "user_id": user_id,
                    "session_id": session_id,
                    "last_distilled_message_created_at": created_at,
                    "last_distilled_message_ids_at_created_at": [item_id],
                    "updated_at": updated_at,
                }
                continue

            if item_created_dt == current_created_dt:
                current_state["last_distilled_message_ids_at_created_at"] = (
                    self._merge_distilled_message_ids(
                        list(current_state["last_distilled_message_ids_at_created_at"]),
                        [item_id],
                    )
                )

        updates: list[dict] = []
        for session_id, state in latest_by_session.items():
            existing_state = self._get_memory_session_state(user_id=user_id, session_id=session_id)
            if existing_state is None:
                updates.append(state)
                continue

            existing_created_at = str(
                existing_state.get("last_distilled_message_created_at") or ""
            ).strip()
            if not existing_created_at:
                updates.append(state)
                continue

            existing_created_dt = self._from_iso(existing_created_at)
            state_created_dt = self._from_iso(str(state["last_distilled_message_created_at"]))
            if existing_created_dt > state_created_dt:
                updates.append(dict(existing_state))
                continue

            if existing_created_dt == state_created_dt:
                state["last_distilled_message_ids_at_created_at"] = self._merge_distilled_message_ids(
                    list(existing_state.get("last_distilled_message_ids_at_created_at", [])),
                    list(state["last_distilled_message_ids_at_created_at"]),
                )

            updates.append(state)

        return updates

    def _auto_distill_rollover_sessions(
        self,
        *,
        user_id: str,
        session_id: str,
        now: datetime,
    ) -> list[str]:
        bucket = self._get_short_term_bucket(user_id, now=now)
        if not bucket:
            return []

        latest_by_session = self._session_latest_timestamps(bucket)
        sessions_to_distill = [
            candidate_session_id
            for candidate_session_id in latest_by_session
            if candidate_session_id != session_id
        ]

        current_latest = latest_by_session.get(session_id)
        if current_latest is not None:
            idle_seconds = (now - current_latest).total_seconds()
            if idle_seconds >= self._session_idle_seconds:
                sessions_to_distill.append(session_id)

        created_sessions: list[str] = []
        for candidate_session_id in self._ordered_unique(sessions_to_distill, limit=len(sessions_to_distill) or 1):
            result = self.distill(
                user_id=user_id,
                trigger="session_rollover",
                session_id=candidate_session_id,
            )
            if result["created"]:
                created_sessions.append(candidate_session_id)
        return created_sessions

    def _auto_distill_weekly_session(
        self,
        *,
        user_id: str,
        session_id: str,
        now: datetime,
    ) -> bool:
        if self._weekly_distill_seconds <= 0:
            return False

        raw_session_items = self._load_raw_session_messages_full(
            user_id=user_id,
            session_id=session_id,
            include_consumed=True,
        )
        if raw_session_items:
            baseline = self._latest_mid_term_timestamp(
                user_id,
                trigger="weekly",
                session_id=session_id,
            ) or self._from_iso(str(raw_session_items[0]["created_at"]))
        else:
            session_bucket = [
                item
                for item in self._get_short_term_bucket(user_id, now=now)
                if item["session_id"] == session_id
            ]
            if not session_bucket:
                return False
            baseline = self._latest_mid_term_timestamp(
                user_id,
                trigger="weekly",
                session_id=session_id,
            ) or self._from_iso(str(session_bucket[0]["created_at"]))

        if (now - baseline).total_seconds() < self._weekly_distill_seconds:
            return False

        result = self.distill(
            user_id=user_id,
            trigger="weekly",
            session_id=session_id,
        )
        return bool(result["created"])

    def _prune_short_term_local(self, user_id: str, now: datetime | None = None) -> None:
        if user_id not in self._short_term:
            return
        current = now or self._now()
        threshold = current - SHORT_TERM_TTL
        kept = [
            item
            for item in self._short_term[user_id]
            if self._from_iso(item["created_at"]) >= threshold
        ]
        self._short_term[user_id] = kept[-SHORT_TERM_MAX_TURNS:]

    def _get_short_term_bucket(self, user_id: str, now: datetime | None = None) -> list[dict]:
        current = now or self._now()
        threshold = current - SHORT_TERM_TTL
        redis_bucket = self._read_redis_short_term(user_id)
        if redis_bucket is not None:
            kept = [
                item
                for item in redis_bucket
                if self._from_iso(item["created_at"]) >= threshold
            ]
            kept = kept[-SHORT_TERM_MAX_TURNS:]
            if kept != redis_bucket:
                self._write_redis_short_term(user_id, kept)
            return kept

        persisted_bucket, persisted_authoritative = self._load_persisted_short_term_bucket(
            user_id,
            now=current,
        )
        if persisted_authoritative:
            if persisted_bucket:
                self._short_term[user_id] = list(persisted_bucket)
                return list(persisted_bucket)
            self._short_term.pop(user_id, None)
            return []

        self._prune_short_term_local(user_id, now=current)
        local_bucket = list(self._short_term.get(user_id, []))
        if local_bucket:
            return local_bucket

        return []

    def should_distill_short_term(
        self,
        user_id: str,
        *,
        now: datetime | None = None,
    ) -> bool:
        bucket = self._get_short_term_bucket(user_id, now=now)
        if not bucket:
            return False
        return len(bucket) >= int(SHORT_TERM_MAX_TURNS * 0.8)

    def ingest_message(
        self,
        user_id: str,
        session_id: str,
        role: str,
        content: str,
        detected_lang: str = "zh",
        *,
        allow_session_rollover: bool = True,
        scope: dict | None = None,
        write_source: str = WRITE_SOURCE_USER_MESSAGE,
        trust_level: str | None = None,
        memory_scope: str = MEMORY_SCOPE_TENANT,
    ) -> dict:
        now = self._now()
        normalized_scope = self._normalize_scope(scope)
        normalized_source = self._normalize_write_source(
            write_source,
            default=WRITE_SOURCE_USER_MESSAGE,
        )
        normalized_trust = self._normalize_trust_level(
            trust_level,
            default=(
                TRUST_LEVEL_REVIEWABLE
                if normalized_source in EXTERNAL_WRITE_SOURCES
                else TRUST_LEVEL_TRUSTED
            ),
        )
        normalized_memory_scope = self._normalize_memory_scope(memory_scope)
        self._enforce_memory_write_policy(
            target_layer="short_term",
            write_source=normalized_source,
            trust_level=normalized_trust,
            memory_scope=normalized_memory_scope,
        )
        auto_distilled_sessions = (
            self._auto_distill_rollover_sessions(
                user_id=user_id,
                session_id=session_id,
                now=now,
            )
            if allow_session_rollover
            else []
        )
        auto_weekly_distilled = (
            self._auto_distill_weekly_session(
                user_id=user_id,
                session_id=session_id,
                now=now,
            )
            if allow_session_rollover
            else False
        )
        item = self._apply_governance_defaults(
            {
                "id": f"msg-{uuid4().hex[:12]}",
                "user_id": user_id,
                "session_id": session_id,
                "role": role,
                "content": content.strip(),
                "detected_lang": detected_lang,
                "created_at": self._to_iso(now),
            },
            scope=normalized_scope,
            memory_scope=normalized_memory_scope,
            memory_layer_kind=MEMORY_LAYER_CONVERSATION,
            write_source=normalized_source,
            trust_level=normalized_trust,
        )
        retention_policy, local_only_reasons = self._retention_policy_for_content(item["content"])
        item["retention_policy"] = retention_policy
        item["local_only_reasons"] = local_only_reasons
        item["local_only_filtered_count"] = 0
        self._append_raw_message(item)

        client = self._get_redis_client()
        if client is not None:
            try:
                key = self._short_term_key(user_id)
                client.rpush(key, json.dumps(item, ensure_ascii=False))
                client.ltrim(key, -SHORT_TERM_MAX_TURNS, -1)
                client.expire(key, int(SHORT_TERM_TTL.total_seconds()))
                short_term_count = int(client.llen(key))
                return {
                    "ok": True,
                    "message": "Memory message ingested",
                    "item": item,
                    "short_term_count": short_term_count,
                    "distill_recommended": short_term_count >= int(SHORT_TERM_MAX_TURNS * 0.8),
                    "auto_distilled_sessions": auto_distilled_sessions,
                    "auto_weekly_distilled": auto_weekly_distilled,
                }
            except Exception as exc:
                logger.warning("Redis short-term memory ingest failed, using in-memory fallback: %s", exc)

        bucket = self._short_term.setdefault(user_id, [])
        bucket.append(item)
        self._prune_short_term_local(user_id, now=now)

        return {
            "ok": True,
            "message": "Memory message ingested",
            "item": item,
            "short_term_count": len(self._short_term[user_id]),
            "distill_recommended": self.should_distill_short_term(user_id, now=now),
            "auto_distilled_sessions": auto_distilled_sessions,
            "auto_weekly_distilled": auto_weekly_distilled,
        }

    def distill(
        self,
        user_id: str,
        trigger: str = "daily",
        session_id: str | None = None,
        *,
        scope: dict | None = None,
        write_source: str = WRITE_SOURCE_BRAIN_INTERNAL,
        trust_level: str | None = None,
        memory_scope: str = MEMORY_SCOPE_TENANT,
    ) -> dict:
        normalized_scope = self._normalize_scope(scope)
        caller_source = self._normalize_write_source(write_source)
        stored_trust = self._normalize_trust_level(trust_level, default=TRUST_LEVEL_TRUSTED)
        normalized_memory_scope = self._normalize_memory_scope(memory_scope)
        self._enforce_memory_write_policy(
            target_layer="mid_term",
            write_source=caller_source,
            trust_level=stored_trust,
            memory_scope=normalized_memory_scope,
        )
        self._enforce_memory_write_policy(
            target_layer="long_term",
            write_source=caller_source,
            trust_level=stored_trust,
            memory_scope=normalized_memory_scope,
        )
        short_bucket = self._filter_memory_items(
            self._get_short_term_bucket(user_id),
            scope=normalized_scope,
            include_inactive=False,
            include_untrusted=True,
        )
        if session_id:
            source_items = [item for item in short_bucket if item["session_id"] == session_id]
            raw_session_items = self._load_raw_session_messages(
                user_id=user_id,
                session_id=session_id,
            )
            raw_session_items = self._filter_memory_items(
                raw_session_items,
                scope=normalized_scope,
                include_inactive=False,
                include_untrusted=True,
            )
            if len(raw_session_items) > len(source_items):
                source_items = raw_session_items
        else:
            source_items = short_bucket

        if not source_items:
            return {
                "ok": True,
                "message": "No short-term memory to distill",
                "created": False,
                "mid_term": None,
                "long_term": None,
                "short_term_remaining": len(short_bucket),
            }

        governed_source_items, distill_audit = self._govern_source_items_for_distillation(source_items)
        effective_session = session_id or source_items[-1]["session_id"]
        if not governed_source_items:
            if session_id:
                remaining_items = [
                    item for item in short_bucket if item["session_id"] != session_id
                ]
            else:
                remaining_items = []

            updated_at = self._to_iso(self._now())
            for state in self._build_session_state_updates(
                user_id=user_id,
                source_items=source_items,
                updated_at=updated_at,
            ):
                self._set_memory_session_state(state)

            if not self._write_redis_short_term(user_id, remaining_items):
                self._short_term[user_id] = remaining_items

            return {
                "ok": True,
                "message": "All source items were retained as local-only and excluded from distillation",
                "created": False,
                "mid_term": None,
                "long_term": None,
                "long_term_items": [],
                "short_term_remaining": len(remaining_items),
                "distill_audit": distill_audit,
            }
        texts = [item["content"] for item in governed_source_items]
        highlights = self._extract_structured_highlights(governed_source_items)
        preferences = highlights["preferences"]
        decisions = highlights["decisions"]
        task_results = highlights["task_results"]
        events = highlights["events"][-3:]
        keywords = self._extract_keywords(texts + preferences + decisions + task_results)
        entities = self._extract_entities(texts + preferences + decisions + task_results)
        now = self._to_iso(self._now())
        summary_text = self._build_hierarchical_summary(
            session_id=effective_session,
            source_count=len(governed_source_items),
            entities=entities,
            keywords=keywords,
            highlights={
                "preferences": preferences,
                "decisions": decisions,
                "task_results": task_results,
                "events": events,
            },
        )

        mid_term = self._apply_governance_defaults(
            {
                "id": f"mid-{uuid4().hex[:12]}",
                "user_id": user_id,
                "session_id": effective_session,
                "trigger": trigger,
                "source_count": len(governed_source_items),
                "summary": summary_text,
                "entities": entities,
                "events": events,
                "keywords": keywords,
                "preferences": preferences,
                "decisions": decisions,
                "task_results": task_results,
                "created_at": now,
                "retention_policy": RETENTION_POLICY_DISTILLABLE,
                "local_only_reasons": list(distill_audit.get("local_only_reasons") or []),
                "local_only_filtered_count": int(distill_audit.get("local_only_filtered_count") or 0),
            },
            scope=normalized_scope,
            memory_scope=normalized_memory_scope,
            memory_layer_kind=MEMORY_LAYER_WORKING,
            write_source=WRITE_SOURCE_DISTILLATION,
            trust_level=stored_trust,
        )
        mid_term["retention_policy"] = RETENTION_POLICY_DISTILLABLE
        mid_term["local_only_reasons"] = list(distill_audit.get("local_only_reasons") or [])
        mid_term["local_only_filtered_count"] = int(distill_audit.get("local_only_filtered_count") or 0)
        self._mid_term.setdefault(user_id, []).append(mid_term)
        if self._mid_term_store is not None:
            self._mid_term_store.save_summary(mid_term)

        long_term_items = self._build_long_term_memories(
            user_id=user_id,
            session_id=effective_session,
            source_mid_term_id=mid_term["id"],
            summary_text=summary_text,
            keywords=keywords,
            highlights={
                "preferences": preferences,
                "decisions": decisions,
                "task_results": task_results,
                "events": events,
            },
            created_at=now,
            scope=normalized_scope,
            memory_scope=normalized_memory_scope,
            trust_level=stored_trust,
        )
        for item in long_term_items:
            item["retention_policy"] = RETENTION_POLICY_DISTILLABLE
            item["local_only_reasons"] = list(distill_audit.get("local_only_reasons") or [])
            item["local_only_filtered_count"] = int(distill_audit.get("local_only_filtered_count") or 0)
        long_term = long_term_items[0]
        long_bucket = self._long_term.setdefault(user_id, [])
        long_bucket.extend(long_term_items)
        if self._long_term_store is not None:
            for item in long_term_items:
                self._long_term_store.save_memory(item)

        if session_id:
            remaining_items = [
                item for item in short_bucket if item["session_id"] != session_id
            ]
        else:
            remaining_items = []

        for state in self._build_session_state_updates(
            user_id=user_id,
            source_items=source_items,
            updated_at=now,
        ):
            self._set_memory_session_state(state)

        if not self._write_redis_short_term(user_id, remaining_items):
            self._short_term[user_id] = remaining_items

        self._emit_distill_internal_event(
            user_id=user_id,
            session_id=effective_session,
            trigger=trigger,
            source_items=source_items,
            mid_term=mid_term,
            long_term=long_term,
            long_term_items=long_term_items,
        )

        return {
            "ok": True,
            "message": "Memory distilled to mid-term and long-term layers",
            "created": True,
            "mid_term": mid_term,
            "long_term": long_term,
            "long_term_items": long_term_items,
            "short_term_remaining": len(remaining_items),
            "distill_audit": distill_audit,
        }

    def _query_phrases(self, query: str, query_tokens: list[str]) -> list[str]:
        phrases: list[str] = []
        seen: set[str] = set()

        for raw_chunk in re.split(r"[，,。！？!?；;\n]+", query.lower()):
            chunk = raw_chunk.strip()
            if len(chunk) < 4:
                continue
            normalized = re.sub(r"\s+", " ", chunk)
            if normalized and normalized not in seen:
                phrases.append(normalized)
                seen.add(normalized)

        for index in range(len(query_tokens) - 1):
            left = query_tokens[index]
            right = query_tokens[index + 1]
            if left.isascii() and right.isascii():
                phrase = f"{left} {right}"
            else:
                phrase = f"{left}{right}"
            if len(phrase) < 4 or phrase in seen:
                continue
            phrases.append(phrase)
            seen.add(phrase)

        return phrases[:8]

    def _query_token_weights(self, query: str) -> tuple[dict[str, float], list[str], list[str]]:
        query_tokens = self._tokenize(query)
        token_weights: dict[str, float] = {}
        expanded_terms: list[str] = []

        for token in query_tokens:
            token_weights[token] = token_weights.get(token, 0.0) + 1.0

        query_phrases = self._query_phrases(query, query_tokens)
        for phrase in query_phrases:
            token_weights[phrase] = max(token_weights.get(phrase, 0.0), 1.4)

        for token in list(token_weights):
            aliases = QUERY_TOKEN_EXPANSIONS.get(token, ())
            for alias in aliases:
                for expanded in self._tokenize(alias):
                    if expanded == token:
                        continue
                    token_weights[expanded] = token_weights.get(expanded, 0.0) + 0.35
                    if expanded not in expanded_terms:
                        expanded_terms.append(expanded)

        return token_weights, query_phrases, expanded_terms

    def _entry_tokens(self, entry: dict) -> set[str]:
        combined_text = " ".join(
            [
                str(entry.get("memory_text") or ""),
                str(entry.get("summary") or ""),
                " ".join(str(keyword) for keyword in entry.get("keywords", [])),
            ]
        )
        return set(self._tokenize(combined_text))

    def _lexical_features(
        self,
        *,
        entry: dict,
        token_weights: dict[str, float],
        query_phrases: list[str],
    ) -> tuple[float, list[str], int]:
        if not token_weights:
            return 0.0, [], 0

        entry_tokens = self._entry_tokens(entry)
        if not entry_tokens:
            return 0.0, [], 0

        matched_terms = [
            token
            for token, _ in sorted(
                token_weights.items(),
                key=lambda item: item[1],
                reverse=True,
            )
            if token in entry_tokens
        ]
        matched_weight = sum(token_weights[token] for token in matched_terms)
        total_weight = sum(token_weights.values())
        lexical_score = matched_weight / total_weight if total_weight > 0 else 0.0

        memory_text = " ".join(
            [
                str(entry.get("memory_text") or "").lower(),
                str(entry.get("summary") or "").lower(),
            ]
        )
        phrase_hits = sum(1 for phrase in query_phrases if phrase in memory_text)
        phrase_boost = min(QUERY_PHRASE_BOOST_CAP, 0.035 * phrase_hits)
        keyword_boost = min(0.08, 0.012 * len(matched_terms))
        lexical_score = min(1.0, lexical_score + phrase_boost + keyword_boost)

        return lexical_score, matched_terms[:8], phrase_hits

    @staticmethod
    def _safe_float(value: object) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _retrieve_cap(self, limit: int) -> int:
        normalized_limit = max(1, int(limit))
        if normalized_limit < MIN_DYNAMIC_RETRIEVE_LIMIT:
            return normalized_limit
        if normalized_limit == DEFAULT_RETRIEVE_LIMIT:
            return MAX_DYNAMIC_RETRIEVE_LIMIT
        return min(MAX_DYNAMIC_RETRIEVE_LIMIT, normalized_limit)

    def _target_retrieve_count(
        self,
        *,
        cap: int,
        eligible_count: int,
        token_weight_count: int,
    ) -> int:
        if eligible_count <= 0:
            return 0
        if cap <= 3:
            return min(cap, eligible_count)
        if eligible_count <= 3:
            return eligible_count

        density_bonus = min(3, max(0, (token_weight_count - 4) // 2))
        baseline = MIN_DYNAMIC_RETRIEVE_LIMIT + density_bonus
        if eligible_count >= 8:
            baseline = max(baseline, 8)
        if eligible_count >= 10:
            baseline = max(baseline, 10)
        baseline = min(baseline, cap)

        return min(eligible_count, max(MIN_DYNAMIC_RETRIEVE_LIMIT, baseline))

    def _diversity_rerank(self, candidates: list[dict], count: int) -> list[dict]:
        if count <= 0 or not candidates:
            return []

        remaining = sorted(
            [dict(candidate) for candidate in candidates],
            key=lambda item: float(item.get("score") or 0.0),
            reverse=True,
        )
        selected: list[dict] = []
        source_counts: Counter[str] = Counter()
        type_counts: Counter[str] = Counter()

        while remaining and len(selected) < count:
            best_index = 0
            best_score = float("-inf")
            for index, item in enumerate(remaining):
                source_key = str(item.get("source_mid_term_id") or "").strip()
                type_key = str(item.get("memory_type") or "").strip()
                penalty = (0.09 * source_counts[source_key]) + (0.05 * type_counts[type_key])
                adjusted = float(item.get("score") or 0.0) - penalty
                if adjusted > best_score:
                    best_score = adjusted
                    best_index = index

            selected_item = remaining.pop(best_index)
            source_key = str(selected_item.get("source_mid_term_id") or "").strip()
            type_key = str(selected_item.get("memory_type") or "").strip()
            source_counts[source_key] += 1
            type_counts[type_key] += 1
            selected_item["rerank_score"] = round(max(best_score, 0.0), 4)
            selected.append(selected_item)

        return selected

    def _candidate_dedupe_fingerprint(self, candidate: dict) -> str:
        memory_type = str(candidate.get("memory_type") or "session_summary").strip().lower()
        summary_key = self._canonicalize_for_dedupe(candidate.get("summary"))
        memory_key = self._canonicalize_for_dedupe(candidate.get("memory_text"))
        if len(memory_key) > 140:
            memory_key = memory_key[:140]
        if memory_key:
            memory_key = SESSION_TOKEN_PATTERN.sub("session", memory_key)
        keyword_keys = self._ordered_unique(
            [
                self._canonicalize_for_dedupe(keyword)
                for keyword in (candidate.get("keywords") or [])
                if self._canonicalize_for_dedupe(keyword)
            ],
            limit=4,
        )
        if summary_key or memory_key or keyword_keys:
            return "|".join([memory_type, summary_key, memory_key, ",".join(keyword_keys)])
        return str(candidate.get("memory_id") or "").strip().lower()

    def _dedupe_scored_candidates(self, candidates: list[dict]) -> list[dict]:
        deduped: list[dict] = []
        seen_fingerprints: set[str] = set()
        for candidate in candidates:
            fingerprint = self._candidate_dedupe_fingerprint(candidate)
            if fingerprint and fingerprint in seen_fingerprints:
                continue
            if fingerprint:
                seen_fingerprints.add(fingerprint)
            deduped.append(candidate)
        return deduped

    def retrieve(
        self,
        user_id: str,
        query: str,
        limit: int = DEFAULT_RETRIEVE_LIMIT,
        *,
        scope: dict | None = None,
        include_untrusted: bool = False,
        memory_scope: str | None = None,
    ) -> dict:
        token_weights, query_phrases, expanded_terms = self._query_token_weights(query)
        if not token_weights:
            return {
                "items": [],
                "total": 0,
                "query_expanded_terms": [],
                "scope_breakdown": {"tenant": 0, "global": 0, "total": 0},
            }

        normalized_scope = self._normalize_scope(scope)
        retrieve_cap = self._retrieve_cap(limit)
        candidate_pool_limit = max(retrieve_cap * 2, retrieve_cap + 4)
        local_entries = self._filter_memory_items(
            self._load_long_term_bucket(user_id),
            scope=normalized_scope,
            memory_scope=memory_scope,
            include_inactive=False,
            include_untrusted=include_untrusted,
        )
        local_by_id = {
            str(entry.get("id") or "").strip(): entry
            for entry in local_entries
            if str(entry.get("id") or "").strip()
        }

        candidates: dict[str, dict] = {}
        for memory_id, entry in local_by_id.items():
            lexical_score, matched_terms, phrase_hit_count = self._lexical_features(
                entry=entry,
                token_weights=token_weights,
                query_phrases=query_phrases,
            )
            candidates[memory_id] = {
                "memory_id": memory_id,
                "source_mid_term_id": str(entry.get("source_mid_term_id") or ""),
                "memory_type": str(entry.get("memory_type") or "session_summary"),
                "memory_text": str(entry.get("memory_text") or ""),
                "summary": entry.get("summary"),
                "keywords": list(entry.get("keywords") or []),
                "created_at": str(entry.get("created_at") or ""),
                "tenant_id": str(entry.get("tenant_id") or normalized_scope["tenant_id"]),
                "project_id": str(entry.get("project_id") or normalized_scope["project_id"]),
                "environment": str(entry.get("environment") or normalized_scope["environment"]),
                "memory_scope": str(entry.get("memory_scope") or MEMORY_SCOPE_TENANT),
                "memory_layer_kind": str(
                    entry.get("memory_layer_kind") or MEMORY_LAYER_CONVERSATION
                ),
                "write_source": str(entry.get("write_source") or WRITE_SOURCE_DISTILLATION),
                "trust_level": str(entry.get("trust_level") or TRUST_LEVEL_TRUSTED),
                "retention_policy": str(entry.get("retention_policy") or RETENTION_POLICY_DISTILLABLE),
                "local_only_reasons": list(entry.get("local_only_reasons") or []),
                "local_only_filtered_count": int(entry.get("local_only_filtered_count") or 0),
                "memory_status": str(entry.get("memory_status") or MEMORY_STATUS_ACTIVE),
                "review_status": str(entry.get("review_status") or REVIEW_STATUS_APPROVED),
                "lexical_score": lexical_score,
                "vector_score": None,
                "phrase_hit_count": phrase_hit_count,
                "matched_terms": matched_terms,
            }

        chroma_items = None
        if self._long_term_store is not None:
            query_memories = getattr(self._long_term_store, "query_memories", None)
            if callable(query_memories):
                try:
                    chroma_items = query_memories(
                        user_id=user_id,
                        query=query,
                        limit=candidate_pool_limit,
                        filters={"memory_status": MEMORY_STATUS_ACTIVE},
                    )
                except TypeError:
                    chroma_items = query_memories(
                        user_id=user_id,
                        query=query,
                        limit=candidate_pool_limit,
                    )
        if chroma_items is not None:
            for vector_item in chroma_items:
                memory_id = str(vector_item.get("memory_id") or "").strip()
                if not memory_id:
                    continue

                candidate = candidates.get(memory_id)
                if candidate is None:
                    candidate = {
                        "memory_id": memory_id,
                        "source_mid_term_id": str(vector_item.get("source_mid_term_id") or ""),
                        "memory_type": str(vector_item.get("memory_type") or "session_summary"),
                        "memory_text": str(vector_item.get("memory_text") or ""),
                        "summary": vector_item.get("summary"),
                        "keywords": list(vector_item.get("keywords") or []),
                        "created_at": str(vector_item.get("created_at") or ""),
                        "tenant_id": str(vector_item.get("tenant_id") or normalized_scope["tenant_id"]),
                        "project_id": str(vector_item.get("project_id") or normalized_scope["project_id"]),
                        "environment": str(vector_item.get("environment") or normalized_scope["environment"]),
                        "memory_scope": str(vector_item.get("memory_scope") or MEMORY_SCOPE_TENANT),
                        "memory_layer_kind": str(
                            vector_item.get("memory_layer_kind") or MEMORY_LAYER_CONVERSATION
                        ),
                        "write_source": str(
                            vector_item.get("write_source") or WRITE_SOURCE_DISTILLATION
                        ),
                        "trust_level": str(vector_item.get("trust_level") or TRUST_LEVEL_TRUSTED),
                        "retention_policy": str(
                            vector_item.get("retention_policy") or RETENTION_POLICY_DISTILLABLE
                        ),
                        "local_only_reasons": list(vector_item.get("local_only_reasons") or []),
                        "local_only_filtered_count": int(vector_item.get("local_only_filtered_count") or 0),
                        "memory_status": str(
                            vector_item.get("memory_status") or MEMORY_STATUS_ACTIVE
                        ),
                        "review_status": str(
                            vector_item.get("review_status") or REVIEW_STATUS_APPROVED
                        ),
                        "lexical_score": 0.0,
                        "vector_score": None,
                        "phrase_hit_count": 0,
                        "matched_terms": [
                            str(term).strip()
                            for term in (vector_item.get("matched_terms") or [])
                            if str(term).strip()
                        ],
                    }
                    candidates[memory_id] = candidate

                vector_score = self._safe_float(vector_item.get("vector_score"))
                if vector_score is None:
                    vector_score = self._safe_float(vector_item.get("score"))
                if vector_score is not None:
                    current_vector = self._safe_float(candidate.get("vector_score"))
                    candidate["vector_score"] = (
                        vector_score
                        if current_vector is None
                        else max(current_vector, vector_score)
                    )

                if not candidate.get("memory_text"):
                    candidate["memory_text"] = str(vector_item.get("memory_text") or "")
                if candidate.get("summary") in {None, ""}:
                    candidate["summary"] = vector_item.get("summary")
                if not candidate.get("keywords"):
                    candidate["keywords"] = list(vector_item.get("keywords") or [])
                if not candidate.get("created_at"):
                    candidate["created_at"] = str(vector_item.get("created_at") or "")

                if not candidate.get("matched_terms"):
                    candidate["matched_terms"] = [
                        str(term).strip()
                        for term in (vector_item.get("matched_terms") or [])
                        if str(term).strip()
                    ]

                lexical_score, matched_terms, phrase_hit_count = self._lexical_features(
                    entry={
                        "memory_text": candidate.get("memory_text") or "",
                        "summary": candidate.get("summary"),
                        "keywords": candidate.get("keywords") or [],
                    },
                    token_weights=token_weights,
                    query_phrases=query_phrases,
                )
                candidate["lexical_score"] = max(
                    float(candidate.get("lexical_score") or 0.0),
                    lexical_score,
                )
                candidate["phrase_hit_count"] = max(
                    int(candidate.get("phrase_hit_count") or 0),
                    phrase_hit_count,
                )
                if matched_terms:
                    candidate["matched_terms"] = self._merge_matched_terms(
                        candidate.get("matched_terms") or [],
                        matched_terms,
                        limit=8,
                    )

        scored_candidates: list[dict] = []
        created_ats: list[datetime] = []
        for candidate in candidates.values():
            created_at = str(candidate.get("created_at") or "").strip()
            if not created_at:
                continue
            try:
                created_ats.append(self._from_iso(created_at))
            except ValueError:
                continue

        newest_at = max(created_ats) if created_ats else None
        oldest_at = min(created_ats) if created_ats else None
        recency_span_seconds = (
            max((newest_at - oldest_at).total_seconds(), 1.0)
            if newest_at is not None and oldest_at is not None and newest_at > oldest_at
            else None
        )

        for candidate in candidates.values():
            if not self._memory_visible_in_scope(candidate, normalized_scope):
                continue
            if memory_scope is not None and (
                str(candidate.get("memory_scope") or MEMORY_SCOPE_TENANT).strip().lower()
                != self._normalize_memory_scope(memory_scope)
            ):
                continue
            if not self._memory_active_for_retrieval(
                candidate,
                include_untrusted=include_untrusted,
            ):
                continue
            lexical_score = float(candidate.get("lexical_score") or 0.0)
            vector_score = self._safe_float(candidate.get("vector_score"))
            phrase_hit_count = int(candidate.get("phrase_hit_count") or 0)
            matched_terms = [
                str(term).strip().lower()
                for term in candidate.get("matched_terms") or []
                if str(term).strip()
            ]
            memory_type = str(candidate.get("memory_type") or "session_summary")

            phrase_boost = min(QUERY_PHRASE_BOOST_CAP, 0.03 * phrase_hit_count)
            term_boost = min(0.06, 0.008 * len(matched_terms))
            type_boost = self._memory_type_boost(memory_type, query)
            if vector_score is None:
                fused_score = (0.82 * lexical_score) + phrase_boost + term_boost + type_boost
            else:
                fused_score = (
                    (0.58 * vector_score)
                    + (0.34 * lexical_score)
                    + phrase_boost
                    + term_boost
                    + type_boost
                )

            created_at = str(candidate.get("created_at") or "").strip()
            if created_at and newest_at is not None and oldest_at is not None and recency_span_seconds is not None:
                try:
                    created_at_dt = self._from_iso(created_at)
                    recency_ratio = max(
                        0.0,
                        min(
                            1.0,
                            (created_at_dt - oldest_at).total_seconds() / recency_span_seconds,
                        ),
                    )
                    fused_score += 0.05 * recency_ratio
                except ValueError:
                    pass

            # Prevent hard injection of weak candidates when both lexical and vector signals are weak.
            if lexical_score <= 0 and (vector_score is None or vector_score < 0.34):
                continue
            if fused_score < MIN_RETRIEVE_SCORE:
                continue

            normalized_candidate = {
                "memory_id": candidate["memory_id"],
                "source_mid_term_id": candidate.get("source_mid_term_id", ""),
                "memory_type": candidate.get("memory_type", "session_summary"),
                "memory_text": candidate.get("memory_text", ""),
                "summary": candidate.get("summary"),
                "keywords": candidate.get("keywords", []),
                "created_at": candidate.get("created_at", ""),
                "tenant_id": candidate.get("tenant_id", "default"),
                "project_id": candidate.get("project_id", "default"),
                "environment": candidate.get("environment", "development"),
                "memory_scope": candidate.get("memory_scope", MEMORY_SCOPE_TENANT),
                "memory_layer_kind": candidate.get("memory_layer_kind", MEMORY_LAYER_CONVERSATION),
                "write_source": candidate.get("write_source", WRITE_SOURCE_DISTILLATION),
                "trust_level": candidate.get("trust_level", TRUST_LEVEL_TRUSTED),
                "retention_policy": candidate.get("retention_policy", RETENTION_POLICY_DISTILLABLE),
                "local_only_reasons": candidate.get("local_only_reasons", []),
                "local_only_filtered_count": int(candidate.get("local_only_filtered_count") or 0),
                "memory_status": candidate.get("memory_status", MEMORY_STATUS_ACTIVE),
                "review_status": candidate.get("review_status", REVIEW_STATUS_APPROVED),
                "score": round(min(fused_score, 1.0), 4),
                "lexical_score": round(lexical_score, 4),
                "vector_score": round(vector_score, 4) if vector_score is not None else None,
                "phrase_hit_count": phrase_hit_count,
                "matched_terms": matched_terms[:8],
            }
            scored_candidates.append(normalized_candidate)

        scored_candidates.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
        deduped_candidates = self._dedupe_scored_candidates(scored_candidates)
        top_candidates = deduped_candidates[:candidate_pool_limit]
        target_count = self._target_retrieve_count(
            cap=retrieve_cap,
            eligible_count=len(top_candidates),
            token_weight_count=len(token_weights),
        )
        reranked = self._diversity_rerank(top_candidates, target_count)

        return {
            "items": reranked,
            "total": len(reranked),
            "query_expanded_terms": expanded_terms,
            "scope_breakdown": self._scope_breakdown(reranked),
        }

    def get_layers(self, user_id: str, *, scope: dict | None = None, memory_scope: str | None = None) -> dict:
        short_term = self._filter_memory_items(
            self._get_short_term_bucket(user_id),
            scope=scope,
            memory_scope=memory_scope,
            include_inactive=False,
            include_untrusted=True,
        )
        mid_term = self._filter_memory_items(
            self._load_mid_term_bucket(user_id),
            scope=scope,
            memory_scope=memory_scope,
            include_inactive=False,
            include_untrusted=True,
        )
        long_term = self._filter_memory_items(
            self._load_long_term_bucket(user_id),
            scope=scope,
            memory_scope=memory_scope,
            include_inactive=False,
            include_untrusted=True,
        )
        all_items = [*short_term, *mid_term, *long_term]
        return {
            "user_id": user_id,
            "short_term": short_term,
            "mid_term": mid_term,
            "long_term": long_term,
            "short_term_count": len(short_term),
            "mid_term_count": len(mid_term),
            "long_term_count": len(long_term),
            "scope_breakdown": self._scope_breakdown(all_items),
        }

    def list_messages(
        self,
        user_id: str,
        *,
        session_id: str | None = None,
        limit: int = SHORT_TERM_MAX_TURNS,
        scope: dict | None = None,
        memory_scope: str | None = None,
    ) -> dict:
        list_messages = getattr(self._raw_message_store, "list_conversation_messages", None)
        if list_messages is not None:
            try:
                items = list_messages(
                    user_id=user_id,
                    session_id=session_id,
                    limit=limit,
                )
            except Exception as exc:  # pragma: no cover - defensive fallback for external stores
                logger.warning("Raw conversation log list failed: %s", exc)
                items = None
            if items is not None:
                filtered_items = self._filter_memory_items(
                    list(items),
                    scope=scope,
                    memory_scope=memory_scope,
                    include_inactive=False,
                    include_untrusted=True,
                )
                return {
                    "user_id": user_id,
                    "session_id": session_id,
                    "items": filtered_items,
                    "total": len(filtered_items),
                    "scope_breakdown": self._scope_breakdown(filtered_items),
                }

        bucket = self._filter_memory_items(
            self._get_short_term_bucket(user_id),
            scope=scope,
            memory_scope=memory_scope,
            include_inactive=False,
            include_untrusted=True,
        )
        if session_id is not None:
            bucket = [item for item in bucket if item.get("session_id") == session_id]
        items = bucket[-max(1, limit) :]
        return {
            "user_id": user_id,
            "session_id": session_id,
            "items": items,
            "total": len(items),
            "scope_breakdown": self._scope_breakdown(items),
        }

    def audit_memories(
        self,
        *,
        user_id: str,
        scope: dict | None = None,
        include_inactive: bool = True,
        memory_scope: str | None = None,
    ) -> dict:
        normalized_scope = self._normalize_scope(scope)
        items: list[dict] = []
        for layer_name, layer_items in (
            ("short_term", self._get_short_term_bucket(user_id)),
            ("mid_term", self._load_mid_term_bucket(user_id)),
            ("long_term", self._load_long_term_bucket(user_id)),
        ):
            filtered = self._filter_memory_items(
                layer_items,
                scope=normalized_scope,
                memory_scope=memory_scope,
                include_inactive=include_inactive,
                include_untrusted=True,
            )
            for item in filtered:
                items.append(
                    {
                        "layer": layer_name,
                        "id": str(item.get("id") or ""),
                        "user_id": str(item.get("user_id") or user_id),
                        "session_id": item.get("session_id"),
                        "source_mid_term_id": item.get("source_mid_term_id"),
                        "role": item.get("role"),
                        "memory_type": item.get("memory_type"),
                        "summary": item.get("summary"),
                        "content": item.get("content") or item.get("memory_text"),
                        "created_at": str(item.get("created_at") or ""),
                        "tenant_id": str(item.get("tenant_id") or "default"),
                        "project_id": str(item.get("project_id") or "default"),
                        "environment": str(item.get("environment") or "development"),
                        "memory_scope": str(item.get("memory_scope") or MEMORY_SCOPE_TENANT),
                        "memory_layer_kind": str(
                            item.get("memory_layer_kind") or MEMORY_LAYER_CONVERSATION
                        ),
                        "write_source": str(item.get("write_source") or WRITE_SOURCE_BRAIN_INTERNAL),
                        "trust_level": str(item.get("trust_level") or TRUST_LEVEL_TRUSTED),
                        "retention_policy": str(item.get("retention_policy") or RETENTION_POLICY_DISTILLABLE),
                        "local_only_reasons": list(item.get("local_only_reasons") or []),
                        "local_only_filtered_count": int(item.get("local_only_filtered_count") or 0),
                        "memory_status": str(item.get("memory_status") or MEMORY_STATUS_ACTIVE),
                        "review_status": str(item.get("review_status") or REVIEW_STATUS_APPROVED),
                        "reviewed_by": item.get("reviewed_by"),
                        "reviewed_at": item.get("reviewed_at"),
                        "review_note": item.get("review_note"),
                        "expires_at": item.get("expires_at"),
                        "archived_at": item.get("archived_at"),
                        "deleted_at": item.get("deleted_at"),
                        "corrected_at": item.get("corrected_at"),
                    }
                )
        items.sort(key=lambda item: (item.get("created_at", ""), item["id"]))
        return {
            "user_id": user_id,
            "items": items,
            "total": len(items),
            "scope_breakdown": self._scope_breakdown(items),
        }

    def review_memory(
        self,
        *,
        user_id: str,
        memory_id: str,
        action: str,
        reviewed_by: str,
        scope: dict | None = None,
        note: str | None = None,
        corrected_memory_text: str | None = None,
        corrected_summary: str | None = None,
    ) -> dict:
        normalized_scope = self._normalize_scope(scope)
        normalized_action = str(action or "").strip().lower()
        authoritative = self._load_long_term_bucket(user_id)
        long_bucket = self._long_term.setdefault(user_id, list(authoritative))
        target_index = -1
        target_item: dict | None = None
        for index, item in enumerate(long_bucket):
            if str(item.get("id") or "").strip() != str(memory_id or "").strip():
                continue
            if not self._memory_visible_in_scope(item, normalized_scope):
                continue
            target_index = index
            target_item = deepcopy(item)
            break
        if target_item is None or target_index < 0:
            raise HTTPException(status_code=404, detail="Memory not found")

        now = self._to_iso(self._now())
        target_item["reviewed_by"] = reviewed_by
        target_item["reviewed_at"] = now
        target_item["review_note"] = note
        if normalized_action == "approve":
            target_item["review_status"] = REVIEW_STATUS_APPROVED
            target_item["trust_level"] = TRUST_LEVEL_TRUSTED
            target_item["memory_status"] = MEMORY_STATUS_ACTIVE
        elif normalized_action == "reject":
            target_item["review_status"] = REVIEW_STATUS_REJECTED
            target_item["trust_level"] = TRUST_LEVEL_UNTRUSTED
            target_item["memory_status"] = MEMORY_STATUS_ARCHIVED
            target_item["archived_at"] = now
        elif normalized_action == "delete":
            target_item["review_status"] = REVIEW_STATUS_REJECTED
            target_item["memory_status"] = MEMORY_STATUS_DELETED
            target_item["deleted_at"] = now
        elif normalized_action == "correct":
            if not corrected_memory_text and corrected_summary is None:
                raise HTTPException(status_code=400, detail="Correct action requires corrected content")
            target_item["review_status"] = REVIEW_STATUS_APPROVED
            target_item["trust_level"] = TRUST_LEVEL_TRUSTED
            target_item["memory_status"] = MEMORY_STATUS_ACTIVE
            target_item["corrected_at"] = now
            if corrected_memory_text:
                target_item["memory_text"] = corrected_memory_text.strip()
            if corrected_summary is not None:
                target_item["summary"] = corrected_summary.strip()
        else:
            raise HTTPException(status_code=400, detail="Unsupported review action")

        long_bucket[target_index] = target_item
        if self._long_term_store is not None:
            self._long_term_store.save_memory(target_item)
        return {"ok": True, "message": f"Memory {normalized_action} completed", "item": target_item}

    def apply_lifecycle(self, *, user_id: str, scope: dict | None = None) -> dict:
        normalized_scope = self._normalize_scope(scope)
        authoritative = self._load_long_term_bucket(user_id)
        long_bucket = self._long_term.setdefault(user_id, list(authoritative))
        archived_count = 0
        now = self._now()
        for index, item in enumerate(list(long_bucket)):
            if not self._memory_visible_in_scope(item, normalized_scope):
                continue
            if str(item.get("memory_status") or MEMORY_STATUS_ACTIVE).strip().lower() != MEMORY_STATUS_ACTIVE:
                continue
            expires_at = str(item.get("expires_at") or "").strip()
            if not expires_at:
                continue
            try:
                expires_dt = self._from_iso(expires_at)
            except ValueError:
                continue
            if expires_dt > now:
                continue
            updated = deepcopy(item)
            updated["memory_status"] = MEMORY_STATUS_ARCHIVED
            updated["archived_at"] = self._to_iso(now)
            long_bucket[index] = updated
            archived_count += 1
            if self._long_term_store is not None:
                self._long_term_store.save_memory(updated)
        return {
            "ok": True,
            "archived_count": archived_count,
            "deleted_count": 0,
            "corrected_count": 0,
        }

    def delete_scope_data(
        self,
        *,
        tenant_id: str | None = None,
        user_ids: list[str] | tuple[str, ...] | set[str] | None = None,
    ) -> dict[str, int]:
        normalized_tenant_id = str(tenant_id or "").strip()
        normalized_user_ids = _normalize_identifier_list(user_ids)
        normalized_user_id_set = set(normalized_user_ids)

        deleted_short_term = 0
        deleted_mid_term_runtime = 0
        deleted_long_term_runtime = 0
        deleted_session_state_cache = 0
        deleted_redis_keys = 0

        for user_id in normalized_user_ids:
            short_bucket = self._short_term.pop(user_id, None)
            if short_bucket is not None:
                deleted_short_term += len(short_bucket)

            mid_bucket = self._mid_term.pop(user_id, None)
            if mid_bucket is not None:
                deleted_mid_term_runtime += len(mid_bucket)

            long_bucket = self._long_term.pop(user_id, None)
            if long_bucket is not None:
                deleted_long_term_runtime += len(long_bucket)

        for cache_key in list(self._session_state_cache):
            if cache_key[0] not in normalized_user_id_set:
                continue
            self._session_state_cache.pop(cache_key, None)
            deleted_session_state_cache += 1

        client = self._get_redis_client()
        if client is not None and normalized_user_ids:
            try:
                redis_keys = [self._short_term_key(user_id) for user_id in normalized_user_ids]
                deleted_redis_keys = int(client.delete(*redis_keys) or 0) if redis_keys else 0
            except Exception as exc:
                logger.warning("Redis scoped short-term memory delete failed: %s", exc)

        deleted_conversation_messages = 0
        delete_messages = getattr(self._raw_message_store, "delete_conversation_messages", None)
        if delete_messages is not None and normalized_user_ids:
            try:
                deleted_conversation_messages = int(
                    delete_messages(user_ids=normalized_user_ids) or 0
                )
            except Exception as exc:
                logger.warning("Raw conversation log delete failed: %s", exc)

        deleted_persisted_session_states = 0
        delete_session_states = getattr(self._raw_message_store, "delete_memory_session_states", None)
        if delete_session_states is not None and normalized_user_ids:
            try:
                deleted_persisted_session_states = int(
                    delete_session_states(user_ids=normalized_user_ids) or 0
                )
            except Exception as exc:
                logger.warning("Persisted memory session state delete failed: %s", exc)

        deleted_mid_term_store = 0
        delete_mid_term = getattr(self._mid_term_store, "delete_summaries", None)
        if delete_mid_term is not None and (normalized_tenant_id or normalized_user_ids):
            try:
                deleted_mid_term_store = int(
                    delete_mid_term(
                        tenant_id=normalized_tenant_id or None,
                        user_ids=normalized_user_ids,
                    )
                    or 0
                )
            except Exception as exc:
                logger.warning("Mid-term memory store delete failed: %s", exc)

        deleted_long_term_store = 0
        delete_long_term = getattr(self._long_term_store, "delete_memories", None)
        if delete_long_term is not None and (normalized_tenant_id or normalized_user_ids):
            try:
                deleted_long_term_store = int(
                    delete_long_term(
                        tenant_id=normalized_tenant_id or None,
                        user_ids=normalized_user_ids,
                    )
                    or 0
                )
            except Exception as exc:
                logger.warning("Long-term memory store delete failed: %s", exc)

        return {
            "short_term_deleted": deleted_short_term,
            "mid_term_runtime_deleted": deleted_mid_term_runtime,
            "mid_term_store_deleted": deleted_mid_term_store,
            "long_term_runtime_deleted": deleted_long_term_runtime,
            "long_term_store_deleted": deleted_long_term_store,
            "conversation_messages_deleted": deleted_conversation_messages,
            "session_state_cache_deleted": deleted_session_state_cache,
            "session_state_store_deleted": deleted_persisted_session_states,
            "redis_short_term_keys_deleted": deleted_redis_keys,
        }

    def clear(self) -> None:
        self._short_term.clear()
        self._mid_term.clear()
        self._long_term.clear()
        self._session_state_cache.clear()
        client = self._get_redis_client()
        if client is not None:
            try:
                keys = list(client.scan_iter(match="memory:short:*"))
                if keys:
                    client.delete(*keys)
            except Exception as exc:
                logger.warning("Redis short-term memory clear failed: %s", exc)
        if self._mid_term_store is not None:
            self._mid_term_store.clear()
        if self._long_term_store is not None:
            self._long_term_store.clear()

    def close(self) -> None:
        if self._long_term_store is not None and hasattr(self._long_term_store, "close"):
            self._long_term_store.close()


memory_service = MemoryService()


def reset_memory_store() -> None:
    memory_service.clear()
