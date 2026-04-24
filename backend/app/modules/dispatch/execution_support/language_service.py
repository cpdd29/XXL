from __future__ import annotations

import re


ZH_PATTERN = re.compile(r"[\u4e00-\u9fff]")
EN_PATTERN = re.compile(r"\b[a-zA-Z]{2,}\b")


def detect_language(text: str, preferred_language: str | None = None) -> str:
    normalized_preference = (preferred_language or "").lower()
    if normalized_preference in {"zh", "en"}:
        return normalized_preference

    zh_count = len(ZH_PATTERN.findall(text))
    en_count = len(EN_PATTERN.findall(text))

    if zh_count == 0 and en_count == 0:
        return "zh"
    if zh_count >= en_count:
        return "zh"
    return "en"
