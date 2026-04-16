from __future__ import annotations


def normalized_security_policy_settings(policy: dict[str, object]) -> dict[str, int | bool]:
    return {
        "incident_window_seconds": max(int(policy.get("security_incident_window_seconds") or 1), 1),
        "ban_threshold": max(int(policy.get("message_rate_limit_ban_threshold") or 1), 1),
        "cooldown_seconds": max(int(policy.get("message_rate_limit_cooldown_seconds") or 1), 1),
        "ban_seconds": max(int(policy.get("message_rate_limit_ban_seconds") or 1), 1),
        "rate_limit_per_minute": max(int(policy.get("message_rate_limit_per_minute") or 1), 1),
        "prompt_injection_enabled": bool(policy.get("prompt_injection_enabled", True)),
        "content_redaction_enabled": bool(policy.get("content_redaction_enabled", True)),
    }


def default_prompt_injection_assessment() -> dict[str, object]:
    return {
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


def build_prompt_injection_audit_details(
    assessment: dict[str, object],
    *,
    incident_count: int,
) -> str:
    return (
        f"incident_count={incident_count}; "
        f"rule_score={assessment.get('rule_score')}; "
        f"classifier_score={assessment.get('classifier_score')}; "
        f"verdict={assessment.get('verdict')}; "
        f"reasons={', '.join(str(item) for item in (assessment.get('reasons') or []))}"
    )


def resolve_allow_layer(rewrite_notes: list[str]) -> str:
    return "content_policy_rewrite" if rewrite_notes else "security_pass"


def build_allow_audit_details(
    *,
    trace_id: str,
    rewrite_notes: list[str],
    prompt_assessment: dict[str, object],
) -> str:
    base_details = (
        f"消息已通过 5 层安全检查 (trace={trace_id})"
        if not rewrite_notes
        else f"消息已改写后放行: {', '.join(rewrite_notes)} (trace={trace_id})"
    )
    return (
        base_details
        + "; "
        + f"prompt_verdict={prompt_assessment.get('verdict')}, "
        + f"rule_score={prompt_assessment.get('rule_score')}, "
        + f"classifier_score={prompt_assessment.get('classifier_score')}"
    )


def build_allow_audit_metadata(
    *,
    trace_event: dict[str, object],
    prompt_assessment: dict[str, object],
    rewrite_notes: list[str],
    rewrite_diffs: list[dict[str, object]],
    clone,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "trace": trace_event,
        "prompt_injection_assessment": clone(prompt_assessment),
    }
    if rewrite_notes:
        metadata["rewrite_notes"] = list(rewrite_notes)
        metadata["rewrite_diffs"] = clone(rewrite_diffs)
    return metadata


def resolve_active_penalty_block_layer(penalty: dict[str, object]) -> str:
    return f"active_{penalty.get('level')}"


def resolve_penalty_block_status_code(
    penalty: dict[str, object],
    *,
    default_status_code: int,
) -> int:
    return int(penalty.get("status_code") or default_status_code)


def resolve_penalty_block_detail(
    penalty: dict[str, object],
    *,
    default_detail: str,
) -> str:
    return str(penalty.get("detail") or default_detail)


def build_block_audit_details(
    *,
    detail: str,
    trace_id: str,
    penalty: dict[str, object] | None,
    audit_details: str | None,
) -> str:
    penalty_suffix = ""
    if penalty is not None:
        penalty_suffix = f"; penalty={penalty.get('level')} until {penalty.get('until')}"
    detail_suffix = f"; {audit_details}" if audit_details else ""
    return f"{detail} (trace={trace_id}{penalty_suffix}{detail_suffix})"


def build_block_audit_metadata(
    *,
    trace_event: dict[str, object],
    penalty: dict[str, object] | None,
    assessment: dict[str, object] | None,
    clone,
) -> dict[str, object]:
    metadata: dict[str, object] = {"trace": trace_event}
    if assessment is not None:
        metadata["prompt_injection_assessment"] = clone(assessment)
    if penalty is not None:
        metadata["penalty"] = clone(penalty)
    return metadata


def build_block_realtime_metadata(
    *,
    layer: str,
    user_key: str,
    status_code: int,
) -> dict[str, object]:
    return {
        "event": "message_blocked",
        "layer": layer,
        "user_key": user_key,
        "status_code": status_code,
    }


def build_security_allow_result(
    *,
    trace_id: str,
    user_key: str,
    sanitized_text: str,
    warnings: list[str],
    prompt_assessment: dict[str, object],
    rewrite_diffs: list[dict[str, object]],
    trace_event: dict[str, object],
) -> dict[str, object]:
    return {
        "trace_id": trace_id,
        "user_key": user_key,
        "sanitized_text": sanitized_text,
        "warnings": warnings,
        "prompt_injection_assessment": prompt_assessment,
        "rewrite_diffs": rewrite_diffs,
        "trace": trace_event,
    }
