from fastapi import APIRouter, Depends

from app.core.authz import require_authenticated_user, require_permission
from app.schemas.agents import Agent, AgentActionResponse, AgentHeartbeatRequest, AgentListResponse
from app.services.agent_service import get_agent, list_agents, reload_agent, report_agent_heartbeat

router = APIRouter(dependencies=[Depends(require_authenticated_user)])


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
def reload_agent_route(agent_id: str) -> AgentActionResponse:
    return AgentActionResponse(**reload_agent(agent_id))


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
