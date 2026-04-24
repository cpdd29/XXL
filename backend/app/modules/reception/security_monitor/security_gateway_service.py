from __future__ import annotations

import logging
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException, status

from app.config import get_settings as _get_app_settings
from app.modules.reception.security_monitor.audit import (
    build_audit_log_payload,
    build_trace_context,
    build_trace_event,
)
from app.modules.reception.security_monitor.auth import (
    format_auth_scope_details,
    is_allowed_auth_scope,
)
from app.modules.reception.security_monitor.inspection import (
    build_allow_audit_details,
    build_allow_audit_metadata,
    build_block_audit_details,
    build_block_audit_metadata,
    build_block_realtime_metadata,
    build_prompt_injection_audit_details,
    build_security_allow_result,
    default_prompt_injection_assessment,
    normalized_security_policy_settings,
    resolve_active_penalty_block_layer,
    resolve_allow_layer,
    resolve_penalty_block_detail,
    resolve_penalty_block_status_code,
)
from app.modules.reception.security_monitor.policy import (
    CONTENT_POLICY_RULES,
    _apply_content_rule as _apply_single_content_rule,
    apply_content_policy,
    assess_prompt_injection,
)
from app.modules.reception.security_monitor.rate_limit import (
    build_penalty_payload,
    choose_rate_limit_penalty_detail,
    choose_rate_limit_penalty_duration,
    choose_rate_limit_penalty_level,
    is_limit_exceeded,
    is_penalty_active,
    resolve_window_count,
    trim_time_window,
)
from app.modules.reception.security_monitor.state import (
    default_subject_state,
    deserialize_penalty,
    normalized_persisted_timestamps,
    parse_timestamp,
    serialize_penalty,
)
from app.platform.messaging.redis_client import redis_provider
from app.modules.reception.schemas.messages import UnifiedMessage
from app.platform.observability.operational_log_service import append_realtime_event
from app.platform.persistence.persistence_service import persistence_service
from app.platform.config.settings_service import get_security_policy_settings
from app.platform.persistence.runtime_store import store
from app.platform.observability.trace_exporter_service import trace_exporter_service


logger = logging.getLogger(__name__)
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
        return parse_timestamp(value)

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
        return trim_time_window(window, now=now, window_seconds=60)

    def _trim_incidents(self, user_key: str, now: datetime, window_seconds: int) -> deque[datetime]:
        incidents = self._recent_incidents[user_key]
        return trim_time_window(incidents, now=now, window_seconds=window_seconds)

    def _default_subject_state(self, user_key: str) -> dict[str, object]:
        return default_subject_state(user_key, now=self._now())

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
        return normalized_persisted_timestamps(values, threshold=threshold)

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
                return is_limit_exceeded(
                    current_count=resolve_window_count(
                        persisted_count=persisted_count,
                        database_authoritative=database_authoritative,
                        runtime_count=current_count,
                    ),
                    limit=limit,
                )
            except Exception as exc:
                logger.warning("Redis rate limiting failed, using in-memory fallback: %s", exc)

        if persisted_count is not None:
            return is_limit_exceeded(current_count=persisted_count, limit=limit)

        request_window = self._trim_window(user_key, now)
        limited = is_limit_exceeded(current_count=len(request_window), limit=limit)
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
                return resolve_window_count(
                    persisted_count=persisted_count,
                    database_authoritative=database_authoritative,
                    runtime_count=redis_count,
                )
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

    def _build_trace_context(
        self,
        *,
        trace_id: str,
        user_key: str,
        auth_scope: str,
        now: datetime,
    ) -> dict[str, object]:
        return build_trace_context(
            trace_id=trace_id,
            user_key=user_key,
            auth_scope=auth_scope,
            now=now,
        )

    def _build_trace_event(
        self,
        trace_context: dict[str, object],
        *,
        layer: str,
        outcome: str,
        status_code: int,
    ) -> dict[str, object]:
        return build_trace_event(
            trace_context,
            layer=layer,
            outcome=outcome,
            status_code=status_code,
            ended_at=self._now(),
        )

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
        log_payload = build_audit_log_payload(
            action=action,
            user=user,
            resource=resource,
            status_value=status_value,
            details=details,
            timestamp=store.now_string(),
            metadata=store.clone(metadata) if isinstance(metadata, dict) else None,
            ip=ip,
        )
        store.audit_logs.insert(0, log_payload)
        del store.audit_logs[200:]
        persistence_service.append_audit_log(log=log_payload)
        trace_exporter_service.export_audit_event(log_payload)

    @staticmethod
    def _serialize_penalty(payload: dict[str, object]) -> str:
        return serialize_penalty(payload)

    @staticmethod
    def _deserialize_penalty(value: object) -> dict[str, object] | None:
        return deserialize_penalty(value)

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
                if not is_penalty_active(payload, now=now):
                    if payload is not None:
                        client.delete(self._penalty_key(user_key))
                    return None
                return payload
            except Exception as exc:
                logger.warning("Redis penalty lookup failed, using in-memory fallback: %s", exc)

        payload = self._active_penalties.get(user_key)
        if not is_penalty_active(payload, now=now):
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
                    if not is_penalty_active(payload, now=current_time):
                        if payload is not None:
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
            if not is_penalty_active(normalized_payload, now=current_time):
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
        now: datetime,
        level: str,
        detail: str,
        duration_seconds: int,
        status_code: int,
    ) -> dict[str, object]:
        payload = build_penalty_payload(
            now=now,
            level=level,
            detail=detail,
            duration_seconds=duration_seconds,
            status_code=status_code,
        )
        client = self._get_redis_client()
        if client is not None:
            try:
                until = datetime.fromisoformat(str(payload["until"]))
                ttl = max(int((until - self._now()).total_seconds()), 1)
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
            now=now,
            level=level,
            detail=detail,
            duration_seconds=duration_seconds,
            status_code=status_code,
        )

    def _apply_rate_limit_penalty(
        self,
        *,
        user_key: str,
        now: datetime,
        incident_count: int,
        ban_threshold: int,
        cooldown_seconds: int,
        ban_seconds: int,
        status_code: int,
    ) -> dict[str, object]:
        return self._apply_penalty(
            user_key,
            now,
            level=choose_rate_limit_penalty_level(
                incident_count=incident_count,
                ban_threshold=ban_threshold,
            ),
            detail=choose_rate_limit_penalty_detail(
                incident_count=incident_count,
                ban_threshold=ban_threshold,
            ),
            duration_seconds=choose_rate_limit_penalty_duration(
                incident_count=incident_count,
                ban_threshold=ban_threshold,
                cooldown_seconds=cooldown_seconds,
                ban_seconds=ban_seconds,
            ),
            status_code=status_code,
        )

    def _maybe_escalate_active_cooldown_penalty(
        self,
        *,
        user_key: str,
        now: datetime,
        active_penalty: dict[str, object],
        incident_window_seconds: int,
        ban_threshold: int,
        cooldown_seconds: int,
        ban_seconds: int,
    ) -> dict[str, object]:
        if str(active_penalty.get("level") or "") != "cooldown" or ban_threshold <= 1:
            return active_penalty

        incident_count = self._record_incident(user_key, now, incident_window_seconds)
        if incident_count < ban_threshold:
            return active_penalty

        return self._apply_rate_limit_penalty(
            user_key=user_key,
            now=now,
            incident_count=incident_count,
            ban_threshold=ban_threshold,
            cooldown_seconds=cooldown_seconds,
            ban_seconds=ban_seconds,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    def _prompt_injection_assessment(self, text: str) -> dict[str, object]:
        return assess_prompt_injection(text, policy=self._policy())

    def _apply_content_policy(self, text: str) -> tuple[str, list[str], list[str], list[dict[str, object]]]:
        return apply_content_policy(text)

    @staticmethod
    def _apply_content_rule(text: str, rule: dict[str, object]) -> tuple[str, int]:
        # Compatibility shim for webhook payload sanitization path.
        return _apply_single_content_rule(text, rule)

    def _enforce_rate_limit_guard(
        self,
        *,
        user_key: str,
        now: datetime,
        trace_id: str,
        trace_context: dict[str, object],
        normalized_policy: dict[str, int | bool],
    ) -> None:
        if not self._is_rule_enabled("频率限制"):
            return

        incident_window_seconds = int(normalized_policy["incident_window_seconds"])
        ban_threshold = int(normalized_policy["ban_threshold"])
        cooldown_seconds = int(normalized_policy["cooldown_seconds"])
        ban_seconds = int(normalized_policy["ban_seconds"])
        rate_limit_per_minute = int(normalized_policy["rate_limit_per_minute"])
        active_penalty = self._load_penalty(user_key, now)
        if active_penalty is not None:
            penalty = self._maybe_escalate_active_cooldown_penalty(
                user_key=user_key,
                now=now,
                active_penalty=active_penalty,
                incident_window_seconds=incident_window_seconds,
                ban_threshold=ban_threshold,
                cooldown_seconds=cooldown_seconds,
                ban_seconds=ban_seconds,
            )

            self._block(
                user_key=user_key,
                layer=resolve_active_penalty_block_layer(penalty),
                status_code=resolve_penalty_block_status_code(
                    penalty,
                    default_status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                ),
                detail=resolve_penalty_block_detail(
                    penalty,
                    default_detail="Security policy blocked this user",
                ),
                rule_name="频率限制",
                trace_id=trace_id,
                trace_context=trace_context,
                penalty=penalty,
            )

        if not self._is_rate_limited(user_key, now, rate_limit_per_minute):
            return

        incident_count = self._record_incident(
            user_key,
            now,
            incident_window_seconds,
        )
        penalty = self._apply_rate_limit_penalty(
            user_key=user_key,
            now=now,
            incident_count=incident_count,
            ban_threshold=ban_threshold,
            cooldown_seconds=cooldown_seconds,
            ban_seconds=ban_seconds,
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

    def _enforce_auth_scope_guard(
        self,
        *,
        user_key: str,
        auth_scope: str,
        trace_id: str,
        trace_context: dict[str, object],
    ) -> None:
        if is_allowed_auth_scope(auth_scope):
            return

        self._block(
            user_key=user_key,
            layer="auth_rbac",
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Message ingest scope is not allowed",
            rule_name=None,
            trace_id=trace_id,
            trace_context=trace_context,
            audit_details=format_auth_scope_details(auth_scope),
        )

    def _assess_prompt_injection_guard(
        self,
        *,
        user_key: str,
        now: datetime,
        text: str,
        trace_id: str,
        trace_context: dict[str, object],
        normalized_policy: dict[str, int | bool],
    ) -> dict[str, object]:
        prompt_assessment = default_prompt_injection_assessment()
        if not self._is_rule_enabled("恶意内容检测"):
            return prompt_assessment
        if not bool(normalized_policy["prompt_injection_enabled"]):
            return prompt_assessment

        prompt_assessment = self._prompt_injection_assessment(text)
        if str(prompt_assessment.get("verdict")) != "block":
            return prompt_assessment

        incident_count = self._record_incident(
            user_key,
            now,
            int(normalized_policy["incident_window_seconds"]),
        )
        penalty = self._apply_penalty(
            user_key,
            now,
            level="ban",
            detail="User temporarily blocked by security policy",
            duration_seconds=int(normalized_policy["ban_seconds"]),
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
            audit_details=build_prompt_injection_audit_details(
                prompt_assessment,
                incident_count=incident_count,
            ),
        )
        return prompt_assessment

    def _apply_content_redaction_guard(
        self,
        *,
        text: str,
        normalized_policy: dict[str, int | bool],
    ) -> tuple[str, list[str], list[str], list[dict[str, object]]]:
        if not self._is_rule_enabled("数据脱敏"):
            return text, [], [], []
        if not bool(normalized_policy["content_redaction_enabled"]):
            return text, [], [], []
        return self._apply_content_policy(text)

    def _finalize_allow_audit(
        self,
        *,
        user_key: str,
        trace_id: str,
        trace_context: dict[str, object],
        prompt_assessment: dict[str, object],
        rewrite_notes: list[str],
        rewrite_diffs: list[dict[str, object]],
    ) -> dict[str, object]:
        if rewrite_notes:
            self._touch_rule("数据脱敏", "刚刚")

        allow_layer = resolve_allow_layer(rewrite_notes)
        trace_event = self._build_trace_event(
            trace_context,
            layer=allow_layer,
            outcome="allowed",
            status_code=status.HTTP_200_OK,
        )
        audit_metadata = build_allow_audit_metadata(
            trace_event=trace_event,
            prompt_assessment=prompt_assessment,
            rewrite_notes=rewrite_notes,
            rewrite_diffs=rewrite_diffs,
            clone=store.clone,
        )
        self._append_audit(
            action="安全网关改写放行" if rewrite_notes else "安全网关放行",
            user=user_key,
            resource="Security Gateway",
            status_value="warning" if rewrite_notes else "success",
            details=build_allow_audit_details(
                trace_id=trace_id,
                rewrite_notes=rewrite_notes,
                prompt_assessment=prompt_assessment,
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
        return trace_event

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
        trace_event = self._build_trace_event(
            trace_context,
            layer=layer,
            outcome="blocked",
            status_code=status_code,
        )
        telemetry_metadata = build_block_audit_metadata(
            trace_event=trace_event,
            penalty=penalty,
            assessment=assessment,
            clone=store.clone,
        )
        self._append_audit(
            action=f"安全网关拦截:{layer}",
            user=user_key,
            resource="Security Gateway",
            status_value="error" if status_code >= 500 else "warning",
            details=build_block_audit_details(
                detail=detail,
                trace_id=trace_id,
                penalty=penalty,
                audit_details=audit_details,
            ),
            metadata=telemetry_metadata,
        )
        self._push_realtime(
            "安全网关",
            f"{layer} 已拦截消息",
            "error",
            trace_id=trace_id,
            metadata=build_block_realtime_metadata(
                layer=layer,
                user_key=user_key,
                status_code=status_code,
            ),
        )
        raise HTTPException(status_code=status_code, detail=detail)

    def inspect(self, message: UnifiedMessage, auth_scope: str) -> dict[str, object]:
        user_key = f"{message.channel.value}:{message.platform_user_id}"
        return self.inspect_text_entrypoint(
            text=message.text,
            user_key=user_key,
            auth_scope=auth_scope,
        )

    def _build_block_result(
        self,
        *,
        trace_id: str,
        user_key: str,
        auth_scope: str,
        text: str,
        prompt_assessment: dict[str, object],
        warnings: list[str],
        rewrite_diffs: list[dict[str, object]],
        trace_context: dict[str, object],
        blocked_layer: str,
        status_code: int,
        detail: str,
    ) -> dict[str, object]:
        trace_event = self._build_trace_event(
            trace_context,
            layer=blocked_layer,
            outcome="blocked",
            status_code=status_code,
        )
        return {
            "allowed": False,
            "trace_id": trace_id,
            "audit_trace_id": trace_id,
            "user_key": user_key,
            "auth_scope": auth_scope,
            "sanitized_text": text,
            "allowed_message": None,
            "warnings": list(warnings),
            "warning_count": len(warnings),
            "prompt_injection_assessment": store.clone(prompt_assessment),
            "rewrite_diffs": store.clone(rewrite_diffs),
            "rewrite_diffs_count": len(rewrite_diffs),
            "trace": trace_event,
            "status_code": status_code,
            "detail": detail,
            "security_verdict": {
                "allowed": False,
                "layer": blocked_layer,
                "status_code": status_code,
                "detail": detail,
            },
        }

    def _build_allow_result(
        self,
        *,
        trace_id: str,
        user_key: str,
        auth_scope: str,
        sanitized_text: str,
        warnings: list[str],
        prompt_assessment: dict[str, object],
        rewrite_diffs: list[dict[str, object]],
        trace_event: dict[str, object],
    ) -> dict[str, object]:
        result = build_security_allow_result(
            trace_id=trace_id,
            user_key=user_key,
            sanitized_text=sanitized_text,
            warnings=warnings,
            prompt_assessment=prompt_assessment,
            rewrite_diffs=rewrite_diffs,
            trace_event=trace_event,
        )
        result.update(
            {
                "allowed": True,
                "audit_trace_id": trace_id,
                "auth_scope": auth_scope,
                "allowed_message": sanitized_text,
                "warning_count": len(warnings),
                "rewrite_diffs_count": len(rewrite_diffs),
                "security_verdict": {
                    "allowed": True,
                    "layer": str(trace_event.get("layer") or "security_pass"),
                    "status_code": int(trace_event.get("status_code") or status.HTTP_200_OK),
                    "detail": "Security flow allowed the request",
                },
            }
        )
        return result

    def inspect_text_entrypoint_snapshot(
        self,
        *,
        text: str,
        user_key: str,
        auth_scope: str,
    ) -> dict[str, object]:
        policy = self._policy()
        normalized_policy = normalized_security_policy_settings(policy)
        now = self._now()
        trace_id = f"trace-{uuid4().hex[:12]}"
        trace_context = self._build_trace_context(
            trace_id=trace_id,
            user_key=user_key,
            auth_scope=auth_scope,
            now=now,
        )
        normalized_text = str(text or "").strip()
        prompt_assessment = default_prompt_injection_assessment()
        warnings: list[str] = []
        rewrite_notes: list[str] = []
        rewrite_diffs: list[dict[str, object]] = []

        try:
            self._enforce_rate_limit_guard(
                user_key=user_key,
                now=now,
                trace_id=trace_id,
                trace_context=trace_context,
                normalized_policy=normalized_policy,
            )
        except HTTPException as exc:
            return self._build_block_result(
                trace_id=trace_id,
                user_key=user_key,
                auth_scope=auth_scope,
                text=normalized_text,
                prompt_assessment=prompt_assessment,
                warnings=warnings,
                rewrite_diffs=rewrite_diffs,
                trace_context=trace_context,
                blocked_layer="rate_limit",
                status_code=exc.status_code,
                detail=str(exc.detail),
            )

        try:
            self._enforce_auth_scope_guard(
                user_key=user_key,
                auth_scope=auth_scope,
                trace_id=trace_id,
                trace_context=trace_context,
            )
        except HTTPException as exc:
            return self._build_block_result(
                trace_id=trace_id,
                user_key=user_key,
                auth_scope=auth_scope,
                text=normalized_text,
                prompt_assessment=prompt_assessment,
                warnings=warnings,
                rewrite_diffs=rewrite_diffs,
                trace_context=trace_context,
                blocked_layer="auth_rbac",
                status_code=exc.status_code,
                detail=str(exc.detail),
            )

        try:
            prompt_assessment = self._assess_prompt_injection_guard(
                user_key=user_key,
                now=now,
                text=normalized_text,
                trace_id=trace_id,
                trace_context=trace_context,
                normalized_policy=normalized_policy,
            )
        except HTTPException as exc:
            if str(prompt_assessment.get("verdict") or "").strip() != "block":
                prompt_assessment = self._prompt_injection_assessment(normalized_text)
            return self._build_block_result(
                trace_id=trace_id,
                user_key=user_key,
                auth_scope=auth_scope,
                text=normalized_text,
                prompt_assessment=prompt_assessment,
                warnings=warnings,
                rewrite_diffs=rewrite_diffs,
                trace_context=trace_context,
                blocked_layer="prompt_injection",
                status_code=exc.status_code,
                detail=str(exc.detail),
            )

        sanitized_text, warnings, rewrite_notes, rewrite_diffs = self._apply_content_redaction_guard(
            text=normalized_text,
            normalized_policy=normalized_policy,
        )
        trace_event = self._finalize_allow_audit(
            user_key=user_key,
            trace_id=trace_id,
            trace_context=trace_context,
            prompt_assessment=prompt_assessment,
            rewrite_notes=rewrite_notes,
            rewrite_diffs=rewrite_diffs,
        )
        return self._build_allow_result(
            trace_id=trace_id,
            user_key=user_key,
            auth_scope=auth_scope,
            sanitized_text=sanitized_text,
            warnings=warnings,
            prompt_assessment=prompt_assessment,
            rewrite_diffs=rewrite_diffs,
            trace_event=trace_event,
        )

    def inspect_text_entrypoint(
        self,
        *,
        text: str,
        user_key: str,
        auth_scope: str,
    ) -> dict[str, object]:
        result = self.inspect_text_entrypoint_snapshot(
            text=text,
            user_key=user_key,
            auth_scope=auth_scope,
        )
        if bool(result.get("allowed")):
            return result
        raise HTTPException(
            status_code=int(result.get("status_code") or status.HTTP_403_FORBIDDEN),
            detail=str(result.get("detail") or "Security policy blocked this request"),
        )

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


def get_settings():
    return _get_app_settings()


def reset_security_gateway_state() -> None:
    security_gateway_service.reset()
