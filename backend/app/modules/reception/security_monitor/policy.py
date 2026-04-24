from __future__ import annotations

import re
from typing import Any

from app.platform.security.content_policy import CONTENT_POLICY_RULES, _apply_content_rule, apply_content_policy
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


def assess_prompt_injection(text: str, *, policy: dict[str, object]) -> dict[str, object]:
    lowered = str(text or "").lower()
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
    classifier_block_threshold = max(int(policy.get("prompt_classifier_block_threshold") or 3), 1)
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
