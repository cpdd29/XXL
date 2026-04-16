from __future__ import annotations

from typing import Any

from app.services import workflow_execution_service


AGENT_DISPATCH_WORKFLOW_ID = workflow_execution_service.AGENT_DISPATCH_WORKFLOW_ID
AGENT_DISPATCH_WORKFLOW_NAME = workflow_execution_service.AGENT_DISPATCH_WORKFLOW_NAME
INTENT_AGENT_TYPE_MAP = workflow_execution_service.INTENT_AGENT_TYPE_MAP


def select_workflow_candidates_for_message(
    intent: str,
    message_text: str,
    *,
    channel: str | None = None,
    detected_lang: str | None = None,
) -> list[tuple[dict[str, Any], str]]:
    return workflow_execution_service.select_workflow_candidates_for_message(
        intent,
        message_text,
        channel=channel,
        detected_lang=detected_lang,
    )


def resolve_agent_dispatch_execution_agent(intent: str | None, *, route_seed: str | None = None) -> dict | None:
    return workflow_execution_service.resolve_agent_dispatch_execution_agent(intent, route_seed=route_seed)


def resolve_workflow_execution_agent(
    workflow: dict[str, Any],
    intent: str | None,
    *,
    route_seed: str | None = None,
) -> dict | None:
    return workflow_execution_service.resolve_workflow_execution_agent(
        workflow,
        intent,
        route_seed=route_seed,
    )

__all__ = [
    "AGENT_DISPATCH_WORKFLOW_ID",
    "AGENT_DISPATCH_WORKFLOW_NAME",
    "INTENT_AGENT_TYPE_MAP",
    "resolve_agent_dispatch_execution_agent",
    "resolve_workflow_execution_agent",
    "select_workflow_candidates_for_message",
]
