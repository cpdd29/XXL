from typing import Any

from fastapi import APIRouter, Depends

from app.core.authz import require_authenticated_user, require_permission
from app.schemas.agents import Agent, AgentActionResponse, AgentHeartbeatRequest, AgentListResponse
from app.services.agent_service import get_agent, list_agents, reload_agent, report_agent_heartbeat
from app.services.control_plane_audit_service import append_control_plane_audit_log

router = APIRouter(dependencies=[Depends(require_authenticated_user)])


def _operator_identity(current_user: dict[str, Any]) -> str:
    return (
        str(current_user.get("email") or "").strip()
        or str(current_user.get("id") or "").strip()
        or "system"
    )


@router.get(
    "",
    response_model=AgentListResponse,
    dependencies=[Depends(require_permission("agents:read"))],
)
def list_agents_route() -> AgentListResponse:
    return AgentListResponse(**list_agents())


@router.get(
    "/{agent_id}/status",
    response_model=Agent,
    dependencies=[Depends(require_permission("agents:read"))],
)
def get_agent_status_route(agent_id: str) -> Agent:
    return Agent(**get_agent(agent_id))


@router.post(
    "/{agent_id}/reload",
    response_model=AgentActionResponse,
    dependencies=[Depends(require_permission("agents:reload"))],
)
def reload_agent_route(
    agent_id: str,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> AgentActionResponse:
    response = AgentActionResponse(**reload_agent(agent_id))
    append_control_plane_audit_log(
        action="agent.reloaded",
        user=_operator_identity(current_user),
        resource=f"agent.{agent_id}",
        details=f"重新加载 Agent {agent_id}",
    )
    return response


@router.post(
    "/{agent_id}/heartbeat",
    response_model=AgentActionResponse,
    dependencies=[Depends(require_permission("agents:heartbeat"))],
)
def report_agent_heartbeat_route(
    agent_id: str,
    payload: AgentHeartbeatRequest,
) -> AgentActionResponse:
    return AgentActionResponse(
        **report_agent_heartbeat(
            agent_id,
            status_text=payload.status,
            interval_seconds=payload.interval_seconds,
            timeout_seconds=payload.timeout_seconds,
            source=payload.source,
            load=payload.load,
            queue_depth=payload.queue_depth,
            metadata=payload.metadata,
        )
    )
