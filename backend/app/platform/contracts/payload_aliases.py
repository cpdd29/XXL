from __future__ import annotations

from typing import Any


def alias_value(payload: dict[str, Any] | None, *keys: str) -> Any:
    if not isinstance(payload, dict):
        return None
    for key in keys:
        if key not in payload:
            continue
        value = payload.get(key)
        if value is not None:
            return value
    return None


def alias_text(payload: dict[str, Any] | None, *keys: str) -> str | None:
    value = alias_value(payload, *keys)
    normalized = str(value or "").strip()
    return normalized or None


def alias_bool(payload: dict[str, Any] | None, *keys: str) -> bool | None:
    value = alias_value(payload, *keys)
    return value if isinstance(value, bool) else None


def alias_dict(payload: dict[str, Any] | None, *keys: str) -> dict[str, Any] | None:
    value = alias_value(payload, *keys)
    return dict(value) if isinstance(value, dict) else None


def alias_list(payload: dict[str, Any] | None, *keys: str) -> list[Any] | None:
    value = alias_value(payload, *keys)
    return list(value) if isinstance(value, list) else None


def dispatch_context_from_run(run: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(run, dict):
        return None
    return alias_dict(run, "dispatch_context", "dispatchContext")


def route_decision_from_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    return alias_dict(payload, "route_decision", "routeDecision")


def route_decision_from_task(task: dict[str, Any] | None) -> dict[str, Any] | None:
    return route_decision_from_payload(task)


def route_decision_from_run(run: dict[str, Any] | None) -> dict[str, Any] | None:
    return route_decision_from_payload(dispatch_context_from_run(run))


def execution_plan_from_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    return alias_dict(payload, "execution_plan", "executionPlan")


def execution_plan_from_route_decision(route_decision: dict[str, Any] | None) -> dict[str, Any] | None:
    return execution_plan_from_payload(route_decision)
