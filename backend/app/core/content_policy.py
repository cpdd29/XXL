from __future__ import annotations

import re


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
    r"(?<![A-Za-z0-9])((?:验证码|校验码|动态码|otp|one[- ]time password|verification code))(\s*[:：]?\s*)(\d{4,8})(?!\d)",
    re.IGNORECASE,
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


def _apply_content_rule(text: str, rule: dict[str, object]) -> tuple[str, int]:
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
        return pattern.subn(lambda match: f"{match.group(1)}{match.group(2)}{replacement}", text)
    if str(rule.get("rule") or "") == "credential_secret_assignment":
        return pattern.subn(lambda match: f"{match.group(1)}{match.group(2)}{replacement}", text)
    if str(rule.get("rule") or "") == "otp_code":
        return pattern.subn(lambda match: f"{match.group(1)}{match.group(2)}{replacement}", text)
    return pattern.subn(str(replacement or "[REDACTED]"), text)


def _build_rewrite_diff(rule: dict[str, object], *, count: int) -> dict[str, object]:
    return {
        "rule": str(rule.get("rule") or ""),
        "label": str(rule.get("label") or ""),
        "category": str(rule.get("category") or "unknown"),
        "severity": str(rule.get("severity") or "medium"),
        "replacement": str(rule.get("replacement_label") or rule.get("replacement") or "[REDACTED]"),
        "count": count,
    }


def apply_content_policy(text: str) -> tuple[str, list[str], list[str], list[dict[str, object]]]:
    rewritten = text
    warnings: list[str] = []
    rewrite_notes: list[str] = []
    rewrite_diffs: list[dict[str, object]] = []
    for rule in CONTENT_POLICY_RULES:
        rewritten, count = _apply_content_rule(rewritten, rule)
        if count <= 0:
            continue
        label = str(rule.get("label") or "content rule")
        replacement_label = str(rule.get("replacement_label") or rule.get("replacement") or "[REDACTED]")
        warnings.append(str(rule.get("warning") or "Detected and redacted sensitive content"))
        rewrite_notes.append(f"{label} x{count} -> {replacement_label}")
        rewrite_diffs.append(_build_rewrite_diff(rule, count=count))
    if rewrite_notes:
        warnings.append("Content policy rewrote sensitive fields and allowed the message through")
    return rewritten, list(dict.fromkeys(warnings)), rewrite_notes, rewrite_diffs
