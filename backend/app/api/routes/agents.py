from typing import Any

from fastapi import APIRouter, Depends

from app.core.authz import require_authenticated_user, require_permission
from app.schemas.agents import (
    Agent,
    AgentActionResponse,
    BrainSkillActionResponse,
    BrainSkillDeleteResponse,
    BrainSkillListResponse,
    BrainSkillUploadRequest,
    AgentConfigRequest,
    AgentHeartbeatRequest,
    AgentListResponse,
)
from app.services.brain_skill_service import brain_skill_service
from app.services.agent_service import (
    create_agent,
    get_agent,
    list_agents,
    reload_agent,
    report_agent_heartbeat,
    update_agent_config,
)
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


@router.post(
    "",
    response_model=AgentActionResponse,
    dependencies=[Depends(require_permission("agents:reload"))],
)
def create_agent_route(
    payload: AgentConfigRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> AgentActionResponse:
    response = AgentActionResponse(**create_agent(payload.model_dump(exclude_none=True)))
    append_control_plane_audit_log(
        action="agent.created",
        user=_operator_identity(current_user),
        resource=f"agent.{response.agent.id}",
        details=f"新增 Agent 配置 {response.agent.name}",
    )
    return response


@router.get(
    "/brain-skills",
    response_model=BrainSkillListResponse,
    dependencies=[Depends(require_permission("agents:read"))],
)
def list_brain_skills_route() -> BrainSkillListResponse:
    return BrainSkillListResponse(**brain_skill_service.list_skills())


@router.post(
    "/brain-skills",
    response_model=BrainSkillActionResponse,
    dependencies=[Depends(require_permission("agents:reload"))],
)
def create_brain_skill_route(
    payload: BrainSkillUploadRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> BrainSkillActionResponse:
    response = BrainSkillActionResponse(**brain_skill_service.upload_skill(payload.model_dump(exclude_none=True)))
    append_control_plane_audit_log(
        action="agent.brain_skill.created",
        user=_operator_identity(current_user),
        resource=f"brain_skill.{response.skill.id}",
        details=f"上传主脑 skill {response.skill.name}",
    )
    return response


@router.delete(
    "/brain-skills/{skill_id}",
    response_model=BrainSkillDeleteResponse,
    dependencies=[Depends(require_permission("agents:reload"))],
)
def delete_brain_skill_route(
    skill_id: str,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> BrainSkillDeleteResponse:
    response = BrainSkillDeleteResponse(**brain_skill_service.delete_skill(skill_id))
    append_control_plane_audit_log(
        action="agent.brain_skill.deleted",
        user=_operator_identity(current_user),
        resource=f"brain_skill.{response.skill_id}",
        details=f"删除主脑 skill {response.skill_id}",
    )
    return response


@router.get(
    "/{agent_id}/status",
    response_model=Agent,
    dependencies=[Depends(require_permission("agents:read"))],
)
def get_agent_status_route(agent_id: str) -> Agent:
    return Agent(**get_agent(agent_id))


@router.put(
    "/{agent_id}/config",
    response_model=AgentActionResponse,
    dependencies=[Depends(require_permission("agents:reload"))],
)
def update_agent_config_route(
    agent_id: str,
    payload: AgentConfigRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> AgentActionResponse:
    response = AgentActionResponse(**update_agent_config(agent_id, payload.model_dump(exclude_none=True)))
    append_control_plane_audit_log(
        action="agent.config.updated",
        user=_operator_identity(current_user),
        resource=f"agent.{agent_id}",
        details=f"更新 Agent 配置 {response.agent.name}",
    )
    return response


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
