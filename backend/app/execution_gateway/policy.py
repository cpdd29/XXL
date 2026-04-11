from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256


@dataclass(slots=True, frozen=True)
class TrafficPolicy:
    mode: str = "builtin_primary"  # builtin_primary | runtime_primary
    shadow_mode: bool = False
    canary_percent: int = 0
    route_key: str = "global"
    force_builtin: bool = False


def _clamp_percent(value: int) -> int:
    return max(0, min(100, int(value)))


def resolve_effective_mode(policy: TrafficPolicy) -> str:
    if policy.force_builtin:
        return "builtin_primary"
    if policy.mode not in {"builtin_primary", "runtime_primary"}:
        return "builtin_primary"
    return policy.mode


def should_use_runtime(policy: TrafficPolicy, *, seed: str) -> bool:
    if resolve_effective_mode(policy) != "runtime_primary":
        return False
    percent = _clamp_percent(policy.canary_percent)
    if percent <= 0:
        return False
    if percent >= 100:
        return True
    digest = sha256(seed.encode("utf-8", errors="ignore")).hexdigest()
    bucket = int(digest[:8], 16) % 100
    return bucket < percent

