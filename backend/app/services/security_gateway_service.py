from __future__ import annotations

import json
import logging
import re
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException, status

from app.config import get_settings
from app.core.redis_client import redis_provider
from app.schemas.messages import UnifiedMessage, allowed_ingest_auth_scopes
from app.services.operational_log_service import append_realtime_event
from app.services.persistence_service import persistence_service
from app.services.settings_service import get_security_policy_settings
from app.services.store import store
from app.services.trace_exporter_service import trace_exporter_service


EMAIL_PATTERN = re.compile(r"([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
PHONE_PATTERN = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
CN_ID_CARD_PATTERN = re.compile(r"(?<!\d)(\d{17}[\dXx])(?!\d)")
BANK_CARD_CANDIDATE_PATTERN = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
OPENAI_KEY_PATTERN = re.compile(r"\bsk(?:-proj)?-[A-Za-z0-9_-]{16,}\b")
TELEGRAM_BOT_TOKEN_PATTERN = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{20,}\b")
BEARER_TOKEN_PATTERN = re.compile(r"\b(Bearer)(\s+)([A-Za-z0-9._-]{16,})\b", re.IGNORECASE)
SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"\b((?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|session[_-]?token|secret|token))(\s*[:=]\s*)([A-Za-z0-9._-]{12,})\b",
    re.IGNORECASE,
)
OTP_PATTERN = re.compile(
    r"\b((?:验证码|校验码|动态码|otp|one[- ]time password|verification code))(\s*[:：]?\s*)(\d{4,8})\b",
    re.IGNORECASE,
)
INJECTION_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"reveal\s+(the\s+)?system\s+prompt",
        r"developer\s+message",
        r"system\s+prompt",
        r"jailbreak",
        r"忽略(之前|上述|所有).*指令",
        r"系统提示词",
        r"开发者消息",
        r"越狱",
    )
]
SUSPICIOUS_KEYWORDS = (
    "ignore previous",
    "system prompt",
    "developer message",
    "developer notes",
    "jailbreak",
    "hidden instructions",
    "internal instructions",
    "verbatim prompt",
    "泄露提示词",
    "忽略指令",
    "绕过限制",
)
PROMPT_OVERRIDE_HINTS = (
    "ignore previous",
    "disregard previous",
    "override safety",
    "bypass policy",
    "忽略之前",
    "忽略上述",
    "绕过限制",
)
PROMPT_EXTRACTION_HINTS = (
    "system prompt",
    "developer message",
    "developer notes",
    "hidden instructions",
    "internal instructions",
    "full prompt",
    "verbatim",
    "逐字",
    "提示词",
    "开发者消息",
    "系统提示词",
)
PROMPT_BYPASS_HINTS = (
    "for research only",
    "red team",
    "simulate jailbreak",
    "pretend to ignore",
    "仅用于研究",
    "红队",
    "越狱",
)
CONTENT_POLICY_RULES = (
    {
        "rule": "pii_email",
        "label": "email address",
        "category": "pii",
        "severity": "medium",
        "pattern": EMAIL_PATTERN,
        "replacement": "[REDACTED_EMAIL]",
        "replacement_label": "[REDACTED_EMAIL]",
        "warning": "Detected and redacted email address",
    },
    {
        "rule": "pii_phone",
        "label": "phone number",
        "category": "pii",
        "severity": "medium",
        "pattern": PHONE_PATTERN,
        "replacement": "[REDACTED_PHONE]",
        "replacement_label": "[REDACTED_PHONE]",
        "warning": "Detected and redacted phone number",
    },
    {
        "rule": "pii_cn_id_card",
        "label": "CN ID card",
        "category": "pii",
        "severity": "high",
        "pattern": CN_ID_CARD_PATTERN,
        "replacement": "[REDACTED_CN_ID]",
        "replacement_label": "[REDACTED_CN_ID]",
        "warning": "Detected and redacted CN ID card number",
    },
    {
        "rule": "financial_bank_card",
        "label": "bank card",
        "category": "financial",
        "severity": "high",
        "pattern": BANK_CARD_CANDIDATE_PATTERN,
        "replacement": "[REDACTED_BANK_CARD]",
        "replacement_label": "[REDACTED_BANK_CARD]",
        "warning": "Detected and redacted bank card number",
    },
    {
        "rule": "credential_openai_key",
        "label": "OpenAI API key",
        "category": "credential",
        "severity": "critical",
        "pattern": OPENAI_KEY_PATTERN,
        "replacement": "[REDACTED_API_KEY]",
        "replacement_label": "[REDACTED_API_KEY]",
        "warning": "Detected and redacted API credential",
    },
    {
        "rule": "credential_telegram_bot_token",
        "label": "Telegram bot token",
        "category": "credential",
        "severity": "critical",
        "pattern": TELEGRAM_BOT_TOKEN_PATTERN,
        "replacement": "[REDACTED_BOT_TOKEN]",
        "replacement_label": "[REDACTED_BOT_TOKEN]",
        "warning": "Detected and redacted bot credential",
    },
    {
        "rule": "credential_bearer_token",
        "label": "bearer token",
        "category": "credential",
        "severity": "critical",
        "pattern": BEARER_TOKEN_PATTERN,
        "replacement": "[REDACTED_BEARER_TOKEN]",
        "replacement_label": "[REDACTED_BEARER_TOKEN]",
        "warning": "Detected and redacted bearer token",
    },
    {
        "rule": "credential_secret_assignment",
        "label": "credential assignment",
        "category": "credential",
        "severity": "critical",
        "pattern": SECRET_ASSIGNMENT_PATTERN,
        "replacement": "[REDACTED_SECRET]",
        "replacement_label": "[REDACTED_SECRET]",
        "warning": "Detected and redacted credential assignment",
    },
    {
        "rule": "otp_code",
        "label": "verification code",
        "category": "business",
        "severity": "high",
        "pattern": OTP_PATTERN,
        "replacement": "[REDACTED_OTP]",
        "replacement_label": "[REDACTED_OTP]",
        "warning": "Detected and redacted verification code",
    },
)
ALLOWED_AUTH_SCOPES = allowed_ingest_auth_scopes()


logger = logging.getLogger(__name__)


def _passes_luhn(number: str) -> bool:
    digits = [int(char) for char in number if char.isdigit()]
    if len(digits) != len(number) or not 13 <= len(digits) <= 19:
        return False

    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        value = digit
        if index % 2 == parity:
            value *= 2
            if value > 9:
                value -= 9
        checksum += value
    return checksum % 10 == 0


class SecurityGatewayService:
    def __init__(self, *, redis_provider_override=None) -> None:
        self._recent_requests: dict[str, deque[datetime]] = defaultdict(deque)
        self._recent_incidents: dict[str, deque[datetime]] = defaultdict(deque)
        self._active_penalties: dict[str, dict[str, object]] = {}
        self._redis_provider = redis_provider_override or redis_provider

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    def _get_redis_client(self):
        return self._redis_provider.get_client() if self._redis_provider is not None else None

    @staticmethod
    def _policy() -> dict[str, object]:
        payload = get_security_policy_settings()
        settings_payload = payload.get("settings")
        return settings_payload if isinstance(settings_payload, dict) else {}

    @staticmethod
    def _parse_timestamp(value: object) -> datetime | None:
        normalized = str(value or "").strip()
        if not normalized:
            return None
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed

    @staticmethod
    def _rate_limit_key(user_key: str) -> str:
        return f"security:rate:{user_key}"

    @staticmethod
    def _incident_key(user_key: str) -> str:
        return f"security:incident:{user_key}"

    @staticmethod
    def _penalty_key(user_key: str) -> str:
        return f"security:penalty:{user_key}"

    def _trim_window(self, user_key: str, now: datetime) -> deque[datetime]:
        window = self._recent_requests[user_key]
        threshold = now - timedelta(minutes=1)
        while window and window[0] < threshold:
            window.popleft()
        return window

    def _trim_incidents(self, user_key: str, now: datetime, window_seconds: int) -> deque[datetime]:
        incidents = self._recent_incidents[user_key]
        threshold = now - timedelta(seconds=max(window_seconds, 1))
        while incidents and incidents[0] < threshold:
            incidents.popleft()
        return incidents

    def _default_subject_state(self, user_key: str) -> dict[str, object]:
        return {
            "user_key": user_key,
            "rate_request_timestamps": [],
            "incident_timestamps": [],
            "active_penalty": None,
            "updated_at": self._now().isoformat(),
        }

    def _read_persisted_subject_state(
        self,
        user_key: str,
    ) -> tuple[dict[str, object] | None, bool]:
        read_state = getattr(persistence_service, "read_security_subject_state", None)
        if callable(read_state):
            return read_state(user_key)

        get_state = getattr(persistence_service, "get_security_subject_state", None)
        if not callable(get_state):
            return None, False

        state = get_state(user_key)
        if state is None:
            return None, False
        return state, True

    def _load_persisted_subject_state(self, user_key: str) -> dict[str, object] | None:
        state, authoritative = self._read_persisted_subject_state(user_key)
        if not authoritative:
            return None
        return state or self._default_subject_state(user_key)

    def _persist_subject_state(
        self,
        user_key: str,
        *,
        rate_request_timestamps: list[datetime],
        incident_timestamps: list[datetime],
        active_penalty: dict[str, object] | None,
        updated_at: datetime | None = None,
    ) -> bool:
        upsert_state = getattr(persistence_service, "upsert_security_subject_state", None)
        if not callable(upsert_state):
            return False

        timestamp = updated_at or self._now()
        return upsert_state(
            {
                "user_key": user_key,
                "rate_request_timestamps": [item.isoformat() for item in rate_request_timestamps],
                "incident_timestamps": [item.isoformat() for item in incident_timestamps],
                "active_penalty": store.clone(active_penalty) if active_penalty is not None else None,
                "updated_at": timestamp.isoformat(),
            }
        )

    def _normalized_persisted_timestamps(
        self,
        values: object,
        *,
        threshold: datetime | None = None,
    ) -> list[datetime]:
        if not isinstance(values, list):
            return []

        timestamps: list[datetime] = []
        for item in values:
            parsed = self._parse_timestamp(item)
            if parsed is None:
                continue
            if threshold is not None and parsed < threshold:
                continue
            timestamps.append(parsed)
        timestamps.sort()
        return timestamps

    def _persisted_rate_count_before_append(
        self,
        user_key: str,
        now: datetime,
    ) -> tuple[int | None, bool]:
        state = self._load_persisted_subject_state(user_key)
        if state is None:
            return None, False

        rate_window = self._normalized_persisted_timestamps(
            state.get("rate_request_timestamps"),
            threshold=now - timedelta(minutes=1),
        )
        incident_window = self._normalized_persisted_timestamps(
            state.get("incident_timestamps"),
            threshold=now - timedelta(
                seconds=max(int(self._policy().get("security_incident_window_seconds") or 1), 1)
            ),
        )
        penalty = self._deserialize_penalty(state.get("active_penalty"))
        rate_count = len(rate_window)
        rate_window.append(now)
        self._persist_subject_state(
            user_key,
            rate_request_timestamps=rate_window,
            incident_timestamps=incident_window,
            active_penalty=penalty,
            updated_at=now,
        )
        return rate_count, True

    def _persisted_incident_count(
        self,
        user_key: str,
        now: datetime,
        window_seconds: int,
    ) -> tuple[int | None, bool]:
        state = self._load_persisted_subject_state(user_key)
        if state is None:
            return None, False

        rate_window = self._normalized_persisted_timestamps(
            state.get("rate_request_timestamps"),
            threshold=now - timedelta(minutes=1),
        )
        incident_window = self._normalized_persisted_timestamps(
            state.get("incident_timestamps"),
            threshold=now - timedelta(seconds=max(window_seconds, 1)),
        )
        penalty = self._deserialize_penalty(state.get("active_penalty"))
        incident_window.append(now)
        self._persist_subject_state(
            user_key,
            rate_request_timestamps=rate_window,
            incident_timestamps=incident_window,
            active_penalty=penalty,
            updated_at=now,
        )
        return len(incident_window), True

    def _load_persisted_penalty(
        self,
        user_key: str,
        now: datetime,
    ) -> tuple[dict[str, object] | None, bool]:
        state, authoritative = self._read_persisted_subject_state(user_key)
        if not authoritative:
            return None, False
        normalized_state = state or self._default_subject_state(user_key)

        penalty = self._deserialize_penalty(normalized_state.get("active_penalty"))
        if penalty is None:
            return None, True

        until = datetime.fromisoformat(str(penalty["until"]))
        if until > now:
            return penalty, True

        self._persist_subject_state(
            user_key,
            rate_request_timestamps=self._normalized_persisted_timestamps(
                normalized_state.get("rate_request_timestamps"),
                threshold=now - timedelta(minutes=1),
            ),
            incident_timestamps=self._normalized_persisted_timestamps(
                normalized_state.get("incident_timestamps"),
                threshold=now - timedelta(
                    seconds=max(int(self._policy().get("security_incident_window_seconds") or 1), 1)
                ),
            ),
            active_penalty=None,
            updated_at=now,
        )
        return None, True

    def _clear_cached_penalty(self, user_key: str) -> None:
        self._active_penalties.pop(user_key, None)

        client = self._get_redis_client()
        if client is None:
            return

        try:
            client.delete(self._penalty_key(user_key))
        except Exception as exc:
            logger.warning("Redis penalty cleanup failed, keeping database-authoritative state: %s", exc)

    def _is_rate_limited(self, user_key: str, now: datetime, limit: int) -> bool:
        persisted_count, database_authoritative = self._persisted_rate_count_before_append(
            user_key,
            now,
        )
        client = self._get_redis_client()
        if client is not None:
            try:
                key = self._rate_limit_key(user_key)
                current_score = now.timestamp()
                window_start = current_score - 60
                client.zremrangebyscore(key, 0, window_start)
                current_count = int(client.zcard(key))
                client.zadd(key, {f"{current_score}:{uuid4().hex[:8]}": current_score})
                client.expire(key, 120)
                if database_authoritative:
                    return int(persisted_count or 0) >= limit
                if persisted_count is None:
                    return current_count >= limit
                return max(current_count, persisted_count) >= limit
            except Exception as exc:
                logger.warning("Redis rate limiting failed, using in-memory fallback: %s", exc)

        if persisted_count is not None:
            return persisted_count >= limit

        request_window = self._trim_window(user_key, now)
        limited = len(request_window) >= limit
        request_window.append(now)
        return limited

    def _record_incident(self, user_key: str, now: datetime, window_seconds: int) -> int:
        persisted_count, database_authoritative = self._persisted_incident_count(
            user_key,
            now,
            window_seconds,
        )
        client = self._get_redis_client()
        if client is not None:
            try:
                key = self._incident_key(user_key)
                current_score = now.timestamp()
                window_start = current_score - max(window_seconds, 1)
                client.zremrangebyscore(key, 0, window_start)
                client.zadd(key, {f"{current_score}:{uuid4().hex[:8]}": current_score})
                client.expire(key, max(window_seconds * 2, 60))
                redis_count = int(client.zcard(key))
                if database_authoritative:
                    return int(persisted_count or 0)
                if persisted_count is None:
                    return redis_count
                return max(redis_count, persisted_count)
            except Exception as exc:
                logger.warning("Redis incident tracking failed, using in-memory fallback: %s", exc)

        if persisted_count is not None:
            return persisted_count

        incidents = self._trim_incidents(user_key, now, window_seconds)
        incidents.append(now)
        return len(incidents)

    def _find_cached_rule(
        self,
        *,
        rule_id: str | None = None,
        rule_name: str | None = None,
    ) -> dict | None:
        normalized_rule_id = str(rule_id or "").strip()
        normalized_rule_name = str(rule_name or "").strip()
        for rule in store.security_rules:
            if normalized_rule_id and str(rule.get("id") or "").strip() == normalized_rule_id:
                return rule
            if normalized_rule_name and str(rule.get("name") or "").strip() == normalized_rule_name:
                return rule
        return None

    def _sync_cached_rule(self, rule_payload: dict) -> dict:
        cached_rule = self._find_cached_rule(
            rule_id=str(rule_payload.get("id") or "").strip(),
            rule_name=str(rule_payload.get("name") or "").strip(),
        )
        payload = store.clone(rule_payload)
        if cached_rule is None:
            store.security_rules.append(payload)
            return payload

        cached_rule.clear()
        cached_rule.update(payload)
        return cached_rule

    def _load_database_rule(self, rule_name: str) -> tuple[dict | None, bool]:
        if not getattr(persistence_service, "enabled", False):
            return None, False

        database_rules = persistence_service.list_security_rules()
        if database_rules is None:
            return None, True

        for rule in database_rules:
            if str(rule.get("name") or "") == rule_name:
                return rule, True
        return None, True

    def _load_rule(self, rule_name: str) -> dict | None:
        database_rule, database_authoritative = self._load_database_rule(rule_name)
        if database_authoritative:
            if database_rule is None:
                return None
            return self._sync_cached_rule(database_rule)

        return self._find_cached_rule(rule_name=rule_name)

    def _is_rule_enabled(self, rule_name: str, *, default: bool = True) -> bool:
        rule = self._load_rule(rule_name)
        if rule is None:
            return default
        return bool(rule.get("enabled", default))

    def _touch_rule(self, rule_name: str, now_label: str) -> None:
        rule = self._load_rule(rule_name)
        if rule is None:
            return

        rule["hit_count"] = int(rule.get("hit_count", 0)) + 1
        rule["last_triggered"] = now_label
        persistence_service.persist_security_rule_state(rule=rule)

    def _push_realtime(
        self,
        agent: str,
        message: str,
        type_: str = "info",
        *,
        trace_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        append_realtime_event(
            agent=agent,
            message=message,
            type_=type_,
            source="security_gateway",
            timestamp=self._now(),
            trace_id=trace_id,
            metadata=store.clone(metadata) if isinstance(metadata, dict) else None,
        )

    @staticmethod
    def _serialize_audit_metadata(metadata: dict[str, object]) -> str:
        return json.dumps(
            metadata,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def _build_trace_context(
        self,
        *,
        trace_id: str,
        user_key: str,
        auth_scope: str,
        now: datetime,
    ) -> dict[str, object]:
        return {
            "trace_id": trace_id,
            "span_id": uuid4().hex[:16],
            "parent_span_id": None,
            "trace_flags": "01",
            "trace_state": "workbot.security_gateway=sampled",
            "service": "workbot.security_gateway",
            "operation": "inspect",
            "user_key": user_key,
            "auth_scope": auth_scope,
            "started_at": now.isoformat(),
        }

    def _build_trace_event(
        self,
        trace_context: dict[str, object],
        *,
        layer: str,
        outcome: str,
        status_code: int,
    ) -> dict[str, object]:
        trace_event = dict(trace_context)
        trace_event["layer"] = layer
        trace_event["outcome"] = outcome
        trace_event["status_code"] = status_code
        trace_event["ended_at"] = self._now().isoformat()
        trace_event["event_span_id"] = uuid4().hex[:16]
        return trace_event

    def _append_audit(
        self,
        *,
        action: str,
        user: str,
        resource: str,
        status_value: str,
        details: str,
        metadata: dict[str, object] | None = None,
        ip: str = "-",
    ) -> None:
        details_value = details
        if isinstance(metadata, dict) and metadata:
            details_value = (
                f"{details}; telemetry={self._serialize_audit_metadata(metadata)}"
            )
        log_payload = {
            "id": f"audit-{uuid4().hex[:10]}",
            "timestamp": store.now_string(),
            "action": action,
            "user": user,
            "resource": resource,
            "status": status_value,
            "ip": ip,
            "details": details_value,
        }
        if isinstance(metadata, dict) and metadata:
            log_payload["metadata"] = store.clone(metadata)
        store.audit_logs.insert(0, log_payload)
        del store.audit_logs[200:]
        persistence_service.append_audit_log(log=log_payload)
        trace_exporter_service.export_audit_event(log_payload)

    @staticmethod
    def _serialize_penalty(payload: dict[str, object]) -> str:
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _deserialize_penalty(value: object) -> dict[str, object] | None:
        if value is None:
            return None
        if isinstance(value, dict):
            payload = dict(value)
        else:
            try:
                if isinstance(value, bytes):
                    value = value.decode("utf-8")
                payload = json.loads(str(value))
            except (TypeError, ValueError, json.JSONDecodeError):
                return None
        try:
            until = str(payload.get("until") or "").strip()
            if not until:
                return None
            datetime.fromisoformat(until)
        except (AttributeError, TypeError, ValueError):
            return None
        return payload

    def _load_penalty(self, user_key: str, now: datetime) -> dict[str, object] | None:
        persisted_payload, database_authoritative = self._load_persisted_penalty(user_key, now)
        if persisted_payload is not None:
            return persisted_payload
        if database_authoritative:
            self._clear_cached_penalty(user_key)
            return None

        client = self._get_redis_client()
        if client is not None:
            try:
                payload = self._deserialize_penalty(client.get(self._penalty_key(user_key)))
                if payload is None:
                    return None
                until = datetime.fromisoformat(str(payload["until"]))
                if until <= now:
                    client.delete(self._penalty_key(user_key))
                    return None
                return payload
            except Exception as exc:
                logger.warning("Redis penalty lookup failed, using in-memory fallback: %s", exc)

        payload = self._active_penalties.get(user_key)
        if payload is None:
            return None
        until_value = str(payload.get("until") or "").strip()
        try:
            until = datetime.fromisoformat(until_value)
        except ValueError:
            self._active_penalties.pop(user_key, None)
            return None
        if until <= now:
            self._active_penalties.pop(user_key, None)
            return None
        return store.clone(payload)

    def list_runtime_active_penalties(
        self,
        *,
        now: datetime | None = None,
    ) -> list[dict[str, object]]:
        current_time = now or self._now()
        items: list[dict[str, object]] = []
        seen_user_keys: set[str] = set()
        prefix = "security:penalty:"

        client = self._get_redis_client()
        if client is not None:
            try:
                for raw_key in client.scan_iter(match=f"{prefix}*"):
                    key = raw_key.decode("utf-8") if isinstance(raw_key, bytes) else str(raw_key)
                    if not key.startswith(prefix):
                        continue
                    user_key = key[len(prefix) :].strip()
                    if not user_key:
                        continue

                    payload = self._deserialize_penalty(client.get(raw_key))
                    if payload is None:
                        continue

                    until = datetime.fromisoformat(str(payload["until"]))
                    if until <= current_time:
                        client.delete(raw_key)
                        continue

                    items.append({"user_key": user_key, **store.clone(payload)})
                    seen_user_keys.add(user_key)
            except Exception as exc:
                logger.warning("Redis active penalty scan failed, using in-memory fallback: %s", exc)

        for user_key, payload in list(self._active_penalties.items()):
            if user_key in seen_user_keys:
                continue
            normalized_payload = self._deserialize_penalty(payload)
            if normalized_payload is None:
                self._active_penalties.pop(user_key, None)
                continue

            until = datetime.fromisoformat(str(normalized_payload["until"]))
            if until <= current_time:
                self._active_penalties.pop(user_key, None)
                continue

            items.append({"user_key": user_key, **store.clone(normalized_payload)})

        return items

    def clear_penalty_cache(self, user_key: str) -> None:
        self._clear_cached_penalty(user_key)

    def clear_subject_state(self, user_key: str) -> None:
        self._active_penalties.pop(user_key, None)
        self._recent_requests.pop(user_key, None)
        self._recent_incidents.pop(user_key, None)

        client = self._get_redis_client()
        if client is None:
            return

        try:
            client.delete(
                self._penalty_key(user_key),
                self._rate_limit_key(user_key),
                self._incident_key(user_key),
            )
        except Exception as exc:
            logger.warning("Redis security subject cleanup failed: %s", exc)

    def _store_penalty(
        self,
        user_key: str,
        *,
        until: datetime,
        level: str,
        detail: str,
        status_code: int,
    ) -> dict[str, object]:
        payload = {
            "level": level,
            "detail": detail,
            "status_code": status_code,
            "until": until.isoformat(),
        }
        now = self._now()
        client = self._get_redis_client()
        if client is not None:
            try:
                ttl = max(int((until - now).total_seconds()), 1)
                client.setex(self._penalty_key(user_key), ttl, self._serialize_penalty(payload))
            except Exception as exc:
                logger.warning("Redis penalty write failed, using in-memory fallback: %s", exc)
        state = self._load_persisted_subject_state(user_key)
        if state is not None:
            self._persist_subject_state(
                user_key,
                rate_request_timestamps=self._normalized_persisted_timestamps(
                    state.get("rate_request_timestamps"),
                    threshold=now - timedelta(minutes=1),
                ),
                incident_timestamps=self._normalized_persisted_timestamps(
                    state.get("incident_timestamps"),
                    threshold=now - timedelta(
                        seconds=max(int(self._policy().get("security_incident_window_seconds") or 1), 1)
                    ),
                ),
                active_penalty=payload,
                updated_at=now,
            )
        self._active_penalties[user_key] = store.clone(payload)
        return payload

    def _apply_penalty(
        self,
        user_key: str,
        now: datetime,
        *,
        level: str,
        detail: str,
        duration_seconds: int,
        status_code: int,
    ) -> dict[str, object]:
        return self._store_penalty(
            user_key,
            until=now + timedelta(seconds=max(duration_seconds, 1)),
            level=level,
            detail=detail,
            status_code=status_code,
        )

    def _prompt_injection_assessment(self, text: str) -> dict[str, object]:
        policy = self._policy()
        lowered = text.lower()
        rule_reasons: list[str] = []
        rule_score = 0
        matched_signals: list[str] = []

        if any(pattern.search(text) for pattern in INJECTION_PATTERNS):
            rule_reasons.append("matched explicit injection pattern")
            rule_score += 4
            matched_signals.append("explicit_injection_pattern")

        suspicious_hits = [keyword for keyword in SUSPICIOUS_KEYWORDS if keyword in lowered]
        if suspicious_hits:
            rule_reasons.append("contained prompt-extraction keyword")
            rule_score += 2
            matched_signals.append("suspicious_prompt_keywords")

        override_hits = [keyword for keyword in PROMPT_OVERRIDE_HINTS if keyword in lowered]
        if override_hits:
            rule_reasons.append("contained instruction-override hint")
            rule_score += 2
            matched_signals.append("instruction_override_hint")

        extraction_hits = [keyword for keyword in PROMPT_EXTRACTION_HINTS if keyword in lowered]
        if extraction_hits:
            rule_reasons.append("attempted hidden prompt extraction")
            rule_score += 2
            matched_signals.append("prompt_extraction_hint")

        bypass_hits = [keyword for keyword in PROMPT_BYPASS_HINTS if keyword in lowered]
        if bypass_hits:
            rule_reasons.append("contained safety-bypass framing")
            rule_score += 1
            matched_signals.append("safety_bypass_framing")

        classifier_reasons: list[str] = []
        classifier_score = 0
        if rule_score >= 4:
            classifier_reasons.append("rule detector reported high risk")
            classifier_score += 2
        if override_hits and extraction_hits:
            classifier_reasons.append("override + extraction intent appeared together")
            classifier_score += 2
        if len(set(suspicious_hits)) >= 2:
            classifier_reasons.append("multiple suspicious prompt keywords appeared")
            classifier_score += 1
        if bypass_hits and (override_hits or extraction_hits):
            classifier_reasons.append("bypass framing was paired with override/extraction intent")
            classifier_score += 1
        if ("reveal" in lowered and "prompt" in lowered) or ("泄露" in lowered and "提示词" in lowered):
            classifier_reasons.append("direct prompt disclosure intent detected")
            classifier_score += 1
        classifier_score = min(classifier_score, 6)

        rule_block_threshold = max(int(policy.get("prompt_rule_block_threshold") or 4), 1)
        classifier_block_threshold = max(
            int(policy.get("prompt_classifier_block_threshold") or 3),
            1,
        )
        rule_verdict = "block" if rule_score >= rule_block_threshold else "allow"
        classifier_verdict = "block" if classifier_score >= classifier_block_threshold else "allow"
        verdict = "block" if (rule_verdict == "block" or classifier_verdict == "block") else "allow"
        if rule_score >= 6 or classifier_score >= 4:
            risk_level = "critical"
        elif rule_score >= 4 or classifier_score >= 3:
            risk_level = "high"
        elif rule_score >= 2 or classifier_score >= 1:
            risk_level = "medium"
        else:
            risk_level = "low"

        reasons = list(dict.fromkeys([*rule_reasons, *classifier_reasons]))
        return {
            "rule_score": rule_score,
            "classifier_score": classifier_score,
            "rule_block_threshold": rule_block_threshold,
            "classifier_block_threshold": classifier_block_threshold,
            "reasons": reasons,
            "verdict": verdict,
            "rule_verdict": rule_verdict,
            "classifier_verdict": classifier_verdict,
            "rule_reasons": list(dict.fromkeys(rule_reasons)),
            "classifier_reasons": list(dict.fromkeys(classifier_reasons)),
            "risk_level": risk_level,
            "matched_signals": list(dict.fromkeys(matched_signals)),
        }

    @staticmethod
    def _apply_content_rule(
        text: str,
        rule: dict[str, object],
    ) -> tuple[str, int]:
        pattern = rule.get("pattern")
        replacement = rule.get("replacement")
        if not isinstance(pattern, re.Pattern):
            return text, 0

        if str(rule.get("rule") or "") == "financial_bank_card":
            count = 0

            def _replace_bank_card(match: re.Match[str]) -> str:
                nonlocal count
                candidate = re.sub(r"[ -]", "", match.group(0))
                if not _passes_luhn(candidate):
                    return match.group(0)
                count += 1
                return str(replacement or "[REDACTED]")

            return pattern.sub(_replace_bank_card, text), count

        if str(rule.get("rule") or "") == "credential_bearer_token":
            def _replace_bearer_token(match: re.Match[str]) -> str:
                return f"{match.group(1)}{match.group(2)}{replacement}"

            return pattern.subn(_replace_bearer_token, text)

        if str(rule.get("rule") or "") == "credential_secret_assignment":
            def _replace_secret_assignment(match: re.Match[str]) -> str:
                return f"{match.group(1)}{match.group(2)}{replacement}"

            return pattern.subn(_replace_secret_assignment, text)

        if str(rule.get("rule") or "") == "otp_code":
            def _replace_otp(match: re.Match[str]) -> str:
                return f"{match.group(1)}{match.group(2)}{replacement}"

            return pattern.subn(_replace_otp, text)

        return pattern.subn(str(replacement or "[REDACTED]"), text)

    @staticmethod
    def _build_rewrite_diff(
        rule: dict[str, object],
        *,
        count: int,
    ) -> dict[str, object]:
        return {
            "rule": str(rule.get("rule") or ""),
            "label": str(rule.get("label") or ""),
            "category": str(rule.get("category") or "unknown"),
            "severity": str(rule.get("severity") or "medium"),
            "replacement": str(rule.get("replacement_label") or rule.get("replacement") or "[REDACTED]"),
            "count": count,
        }

    def _apply_content_policy(
        self,
        text: str,
    ) -> tuple[str, list[str], list[str], list[dict[str, object]]]:
        rewritten = text
        warnings: list[str] = []
        rewrite_notes: list[str] = []
        rewrite_diffs: list[dict[str, object]] = []

        for rule in CONTENT_POLICY_RULES:
            rewritten, count = self._apply_content_rule(rewritten, rule)
            if count <= 0:
                continue
            label = str(rule.get("label") or "content rule")
            replacement_label = str(rule.get("replacement_label") or rule.get("replacement") or "[REDACTED]")
            warnings.append(str(rule.get("warning") or "Detected and redacted sensitive content"))
            rewrite_notes.append(f"{label} x{count} -> {replacement_label}")
            rewrite_diffs.append(self._build_rewrite_diff(rule, count=count))

        if rewrite_notes:
            warnings.append(
                "Content policy rewrote sensitive fields and allowed the message through"
            )
        return rewritten, list(dict.fromkeys(warnings)), rewrite_notes, rewrite_diffs

    def _block(
        self,
        *,
        user_key: str,
        layer: str,
        status_code: int,
        detail: str,
        rule_name: str | None,
        trace_id: str,
        trace_context: dict[str, object],
        penalty: dict[str, object] | None = None,
        assessment: dict[str, object] | None = None,
        audit_details: str | None = None,
    ) -> None:
        now_label = "刚刚"
        if rule_name:
            self._touch_rule(rule_name, now_label)
        penalty_suffix = ""
        if penalty is not None:
            penalty_suffix = (
                f"; penalty={penalty.get('level')} until {penalty.get('until')}"
            )
        detail_suffix = f"; {audit_details}" if audit_details else ""
        telemetry_metadata: dict[str, object] = {
            "trace": self._build_trace_event(
                trace_context,
                layer=layer,
                outcome="blocked",
                status_code=status_code,
            )
        }
        if assessment is not None:
            telemetry_metadata["prompt_injection_assessment"] = store.clone(assessment)
        if penalty is not None:
            telemetry_metadata["penalty"] = store.clone(penalty)
        self._append_audit(
            action=f"安全网关拦截:{layer}",
            user=user_key,
            resource="Security Gateway",
            status_value="error" if status_code >= 500 else "warning",
            details=f"{detail} (trace={trace_id}{penalty_suffix}{detail_suffix})",
            metadata=telemetry_metadata,
        )
        self._push_realtime(
            "安全网关",
            f"{layer} 已拦截消息",
            "error",
            trace_id=trace_id,
            metadata={
                "event": "message_blocked",
                "layer": layer,
                "user_key": user_key,
                "status_code": status_code,
            },
        )
        raise HTTPException(status_code=status_code, detail=detail)

    def inspect(self, message: UnifiedMessage, auth_scope: str) -> dict[str, object]:
        policy = self._policy()
        now = self._now()
        trace_id = f"trace-{uuid4().hex[:12]}"
        user_key = f"{message.channel.value}:{message.platform_user_id}"
        trace_context = self._build_trace_context(
            trace_id=trace_id,
            user_key=user_key,
            auth_scope=auth_scope,
            now=now,
        )

        if self._is_rule_enabled("频率限制"):
            active_penalty = self._load_penalty(user_key, now)
            if active_penalty is not None:
                penalty = active_penalty
                if (
                    str(active_penalty.get("level") or "") == "cooldown"
                    and int(policy.get("message_rate_limit_ban_threshold") or 1) > 1
                ):
                    incident_count = self._record_incident(
                        user_key,
                        now,
                        int(policy.get("security_incident_window_seconds") or 1),
                    )
                    if incident_count >= int(policy.get("message_rate_limit_ban_threshold") or 1):
                        penalty = self._apply_penalty(
                            user_key,
                            now,
                            level="ban",
                            detail="User temporarily blocked by security policy",
                            duration_seconds=int(policy.get("message_rate_limit_ban_seconds") or 1),
                            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        )

                self._block(
                    user_key=user_key,
                    layer=f"active_{penalty.get('level')}",
                    status_code=int(penalty.get("status_code") or status.HTTP_429_TOO_MANY_REQUESTS),
                    detail=str(penalty.get("detail") or "Security policy blocked this user"),
                    rule_name="频率限制",
                    trace_id=trace_id,
                    trace_context=trace_context,
                    penalty=penalty,
                )

            if self._is_rate_limited(
                user_key,
                now,
                int(policy.get("message_rate_limit_per_minute") or 1),
            ):
                incident_count = self._record_incident(
                    user_key,
                    now,
                    int(policy.get("security_incident_window_seconds") or 1),
                )
                penalty = self._apply_penalty(
                    user_key,
                    now,
                    level=(
                        "ban"
                        if incident_count >= int(policy.get("message_rate_limit_ban_threshold") or 1)
                        else "cooldown"
                    ),
                    detail=(
                        "User temporarily blocked by security policy"
                        if incident_count >= int(policy.get("message_rate_limit_ban_threshold") or 1)
                        else "User is cooling down after rate limit violations"
                    ),
                    duration_seconds=(
                        int(policy.get("message_rate_limit_ban_seconds") or 1)
                        if incident_count >= int(policy.get("message_rate_limit_ban_threshold") or 1)
                        else int(policy.get("message_rate_limit_cooldown_seconds") or 1)
                    ),
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                )
                self._block(
                    user_key=user_key,
                    layer="rate_limit",
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded for this user",
                    rule_name="频率限制",
                    trace_id=trace_id,
                    trace_context=trace_context,
                    penalty=penalty,
                    audit_details=f"incident_count={incident_count}",
                )

        if auth_scope not in ALLOWED_AUTH_SCOPES:
            self._block(
                user_key=user_key,
                layer="auth_rbac",
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Message ingest scope is not allowed",
                rule_name=None,
                trace_id=trace_id,
                trace_context=trace_context,
                audit_details=(
                    f"auth_scope={auth_scope}; "
                    f"allowed_scopes={', '.join(sorted(ALLOWED_AUTH_SCOPES))}"
                ),
            )

        normalized_text = message.text.strip()
        prompt_assessment: dict[str, object] = {
            "rule_score": 0,
            "classifier_score": 0,
            "reasons": [],
            "verdict": "skipped",
            "rule_verdict": "skipped",
            "classifier_verdict": "skipped",
            "rule_reasons": [],
            "classifier_reasons": [],
            "risk_level": "low",
            "matched_signals": [],
        }
        if self._is_rule_enabled("恶意内容检测") and bool(policy.get("prompt_injection_enabled", True)):
            prompt_assessment = self._prompt_injection_assessment(normalized_text)
            if str(prompt_assessment.get("verdict")) == "block":
                incident_count = self._record_incident(
                    user_key,
                    now,
                    int(policy.get("security_incident_window_seconds") or 1),
                )
                penalty = self._apply_penalty(
                    user_key,
                    now,
                    level="ban",
                    detail="User temporarily blocked by security policy",
                    duration_seconds=int(policy.get("message_rate_limit_ban_seconds") or 1),
                    status_code=status.HTTP_403_FORBIDDEN,
                )
                self._block(
                    user_key=user_key,
                    layer="prompt_injection",
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Prompt injection risk detected",
                    rule_name="恶意内容检测",
                    trace_id=trace_id,
                    trace_context=trace_context,
                    penalty=penalty,
                    assessment=prompt_assessment,
                    audit_details=(
                        f"incident_count={incident_count}; "
                        f"rule_score={prompt_assessment.get('rule_score')}; "
                        f"classifier_score={prompt_assessment.get('classifier_score')}; "
                        f"verdict={prompt_assessment.get('verdict')}; "
                        f"reasons={', '.join(str(item) for item in (prompt_assessment.get('reasons') or []))}"
                    ),
                )

        if self._is_rule_enabled("数据脱敏") and bool(policy.get("content_redaction_enabled", True)):
            sanitized_text, warnings, rewrite_notes, rewrite_diffs = self._apply_content_policy(normalized_text)
        else:
            sanitized_text, warnings, rewrite_notes, rewrite_diffs = normalized_text, [], [], []

        if warnings:
            self._touch_rule("数据脱敏", "刚刚")

        allow_layer = "content_policy_rewrite" if rewrite_notes else "security_pass"
        audit_metadata: dict[str, object] = {
            "trace": self._build_trace_event(
                trace_context,
                layer=allow_layer,
                outcome="allowed",
                status_code=status.HTTP_200_OK,
            ),
            "prompt_injection_assessment": store.clone(prompt_assessment),
        }
        if rewrite_notes:
            audit_metadata["rewrite_notes"] = list(rewrite_notes)
            audit_metadata["rewrite_diffs"] = store.clone(rewrite_diffs)
        self._append_audit(
            action="安全网关改写放行" if rewrite_notes else "安全网关放行",
            user=user_key,
            resource="Security Gateway",
            status_value="warning" if rewrite_notes else "success",
            details=(
                f"消息已通过 5 层安全检查 (trace={trace_id})"
                if not rewrite_notes
                else (
                    f"消息已改写后放行: {', '.join(rewrite_notes)} "
                    f"(trace={trace_id})"
                )
            )
            + (
                "; "
                f"prompt_verdict={prompt_assessment.get('verdict')}, "
                f"rule_score={prompt_assessment.get('rule_score')}, "
                f"classifier_score={prompt_assessment.get('classifier_score')}"
            ),
            metadata=audit_metadata,
        )
        self._push_realtime(
            "安全网关",
            "消息已通过安全网关",
            "success",
            trace_id=trace_id,
            metadata={
                "event": "message_allowed",
                "user_key": user_key,
                "rewrite_count": len(rewrite_diffs),
                "prompt_verdict": prompt_assessment.get("verdict"),
            },
        )

        return {
            "trace_id": trace_id,
            "user_key": user_key,
            "sanitized_text": sanitized_text,
            "warnings": warnings,
            "prompt_injection_assessment": prompt_assessment,
            "rewrite_diffs": rewrite_diffs,
            "trace": audit_metadata["trace"],
        }

    def reset(self) -> None:
        self._recent_requests.clear()
        self._recent_incidents.clear()
        self._active_penalties.clear()
        client = self._get_redis_client()
        if client is None:
            return
        try:
            keys = list(client.scan_iter(match="security:*"))
            if keys:
                client.delete(*keys)
        except Exception as exc:
            logger.warning("Redis rate limit clear failed: %s", exc)


security_gateway_service = SecurityGatewayService()


def reset_security_gateway_state() -> None:
    security_gateway_service.reset()
