"""Security core layer for the brain trusted zone."""

from app.brain_core.security.audit import (
    build_audit_log_payload,
    build_trace_context,
    build_trace_event,
    serialize_audit_metadata,
)
from app.brain_core.security.auth import (
    ALLOWED_AUTH_SCOPES,
    format_auth_scope_details,
    is_allowed_auth_scope,
)
from app.brain_core.security.inspection import (
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
from app.brain_core.security.policy import (
    CONTENT_POLICY_RULES,
    assess_prompt_injection,
    apply_content_policy,
)
from app.brain_core.security.rate_limit import (
    build_penalty_payload,
    choose_rate_limit_penalty_detail,
    choose_rate_limit_penalty_duration,
    choose_rate_limit_penalty_level,
    is_limit_exceeded,
    is_penalty_active,
    resolve_window_count,
    trim_time_window,
)
from app.brain_core.security.state import (
    default_subject_state,
    deserialize_penalty,
    normalized_persisted_timestamps,
    parse_timestamp,
    serialize_penalty,
)

__all__ = [
    "ALLOWED_AUTH_SCOPES",
    "CONTENT_POLICY_RULES",
    "assess_prompt_injection",
    "apply_content_policy",
    "build_allow_audit_details",
    "build_allow_audit_metadata",
    "build_block_audit_details",
    "build_block_audit_metadata",
    "build_block_realtime_metadata",
    "build_audit_log_payload",
    "build_penalty_payload",
    "build_prompt_injection_audit_details",
    "build_security_allow_result",
    "build_trace_context",
    "build_trace_event",
    "choose_rate_limit_penalty_detail",
    "choose_rate_limit_penalty_duration",
    "choose_rate_limit_penalty_level",
    "default_prompt_injection_assessment",
    "format_auth_scope_details",
    "is_allowed_auth_scope",
    "is_limit_exceeded",
    "is_penalty_active",
    "normalized_security_policy_settings",
    "default_subject_state",
    "deserialize_penalty",
    "normalized_persisted_timestamps",
    "parse_timestamp",
    "resolve_active_penalty_block_layer",
    "resolve_allow_layer",
    "resolve_penalty_block_detail",
    "resolve_penalty_block_status_code",
    "resolve_window_count",
    "serialize_penalty",
    "serialize_audit_metadata",
    "trim_time_window",
]
