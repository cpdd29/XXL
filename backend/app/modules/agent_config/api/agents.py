from typing import Any
from copy import deepcopy

from fastapi import APIRouter, Depends, Query

from app.modules.agent_config.registries.brain_skill_service import brain_skill_service
from app.modules.agent_config.schemas.agents import (
    Agent,
    AgentActionResponse,
    AgentConfigRequest,
    AgentDeleteResponse,
    AgentEnabledRequest,
    AgentHeartbeatRequest,
    AgentListResponse,
    BrainSkillActionResponse,
    BrainSkillDeleteResponse,
    BrainSkillListResponse,
    BrainSkillScopeUpdateRequest,
    BrainSkillUploadRequest,
    ExternalAgentCreateRequest,
)
from app.modules.agent_config.registries.external_agent_registry_service import external_agent_registry_service
from app.modules.organization.application.tenancy_service import DEFAULT_TENANT_ID, ROOT_SCOPE_ROLES, current_user_scope, resolve_scope
from app.platform.auth.authz import require_authenticated_user, require_permission
from app.modules.agent_config.registries.agent_service import (
    create_agent,
    delete_agent,
    get_agent,
    list_agents,
    reload_agent,
    report_agent_heartbeat,
    set_agent_enabled,
    update_agent_config,
)
from app.platform.audit.control_plane_audit_service import append_control_plane_audit_log

router = APIRouter(dependencies=[Depends(require_authenticated_user)])


def _operator_identity(current_user: dict[str, Any]) -> str:
    return (
        str(current_user.get("email") or "").strip()
        or str(current_user.get("id") or "").strip()
        or "system"
    )


def _capability_tenant_context(
    current_user: dict[str, Any],
    *,
    tenant_id: str | None,
) -> tuple[str | None, bool]:
    role = str(current_user.get("role") or "").strip().lower()
    user_scope = current_user_scope(current_user)
    requested_tenant_id = str(tenant_id or "").strip() or None
    if role in ROOT_SCOPE_ROLES and requested_tenant_id is None and user_scope.get("tenant_id") == DEFAULT_TENANT_ID:
        return None, True
    resolved_scope = resolve_scope(current_user=current_user, tenant_id=requested_tenant_id)
    return str(resolved_scope.get("tenant_id") or "").strip() or None, False


@router.get(
    "",
    response_model=AgentListResponse,
    dependencies=[Depends(require_permission("agents:read"))],
)
def list_agents_route(
    include_task_child_agents: bool = Query(default=False),
) -> AgentListResponse:
    return AgentListResponse(
        **list_agents(include_task_child_agents=include_task_child_agents)
    )


@router.post(
    "",
    response_model=AgentActionResponse,
    dependencies=[Depends(require_permission("agents:reload"))],
)
def create_agent_route(
    payload: AgentConfigRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
    tenant_id: str | None = Query(default=None),
) -> AgentActionResponse:
    resolved_tenant_id, include_all_tenants = _capability_tenant_context(current_user, tenant_id=tenant_id)
    response = AgentActionResponse(
        **create_agent(
            payload.model_dump(exclude_unset=True),
            tenant_id=resolved_tenant_id,
            include_all_tenants=include_all_tenants,
        )
    )
    append_control_plane_audit_log(
        action="agent.created",
        user=_operator_identity(current_user),
        resource=f"agent.{response.agent.id}",
        details=f"新增 Agent 配置 {response.agent.name}",
    )
    return response


@router.post(
    "/external",
    response_model=AgentActionResponse,
    dependencies=[Depends(require_permission("agents:reload"))],
)
def create_external_agent_route(
    payload: ExternalAgentCreateRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> AgentActionResponse:
    existing = external_agent_registry_service.get_agent(str(payload.id).strip())
    existing_metadata = (
        deepcopy(((existing or {}).get("config_snapshot") or {}).get("metadata") or {})
        if isinstance(((existing or {}).get("config_snapshot") or {}).get("metadata"), dict)
        else {}
    )
    normalized_payload = payload.model_dump(exclude_none=True)
    normalized_payload["type"] = str(normalized_payload.get("type") or "write").strip() or "write"
    normalized_payload["agent_family"] = (
        str(normalized_payload.get("agent_family") or normalized_payload.get("id") or "").strip()
        or str(normalized_payload.get("id") or "").strip()
    )

    tags = list(normalized_payload.pop("tags", []) or [])
    api_key = str(normalized_payload.pop("api_key", "") or "").strip()
    remote_model = str(normalized_payload.pop("remote_model", "") or "").strip()
    metadata = existing_metadata
    metadata["tags"] = tags
    metadata["source"] = "control_plane"
    if remote_model:
        metadata["model"] = remote_model
        metadata["remote_model"] = remote_model
    elif str(metadata.get("model") or "").strip():
        metadata["remote_model"] = str(metadata.get("model") or "").strip()
    if api_key:
        metadata["auth"] = {
            "type": "bearer",
            "bearer_token": api_key,
        }
    normalized_payload["metadata"] = metadata
    item = external_agent_registry_service.register_agent(normalized_payload)
    agent_payload = get_agent(str(item.get("id") or ""))
    response = AgentActionResponse(
        ok=True,
        message=f"External agent {agent_payload['name']} registered",
        agent=Agent(**agent_payload),
    )
    append_control_plane_audit_log(
        action="agent.external.created",
        user=_operator_identity(current_user),
        resource=f"agent.{response.agent.id}",
        details=f"新增外接 Agent {response.agent.name}",
    )
    return response


@router.get(
    "/brain-skills",
    response_model=BrainSkillListResponse,
    dependencies=[Depends(require_permission("agents:read"))],
)
def list_brain_skills_route(
    tenant_id: str | None = Query(default=None),
    scope: str | None = Query(default=None),
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> BrainSkillListResponse:
    resolved_tenant_id, include_all_tenants = _capability_tenant_context(current_user, tenant_id=tenant_id)
    return BrainSkillListResponse(
        **brain_skill_service.list_skills(
            tenant_id=resolved_tenant_id,
            include_all_tenants=include_all_tenants,
            scope=scope,
        )
    )


@router.post(
    "/brain-skills",
    response_model=BrainSkillActionResponse,
    dependencies=[Depends(require_permission("agents:reload"))],
)
def create_brain_skill_route(
    payload: BrainSkillUploadRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
    tenant_id: str | None = Query(default=None),
) -> BrainSkillActionResponse:
    requested_tenant_id = payload.owner_tenant_id or tenant_id
    resolved_tenant_id, _ = _capability_tenant_context(current_user, tenant_id=requested_tenant_id)
    response = BrainSkillActionResponse(
        **brain_skill_service.upload_skill(
            payload.model_dump(exclude_none=True),
            tenant_id=resolved_tenant_id,
        )
    )
    append_control_plane_audit_log(
        action="agent.brain_skill.created",
        user=_operator_identity(current_user),
        resource=f"brain_skill.{response.skill.id}",
        details=f"上传主脑 skill {response.skill.name}",
    )
    return response


@router.put(
    "/brain-skills/{skill_id}/scope",
    response_model=BrainSkillActionResponse,
    dependencies=[Depends(require_permission("agents:reload"))],
)
def update_brain_skill_scope_route(
    skill_id: str,
    payload: BrainSkillScopeUpdateRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
    tenant_id: str | None = Query(default=None),
) -> BrainSkillActionResponse:
    requested_tenant_id = payload.owner_tenant_id or tenant_id
    resolved_tenant_id, _ = _capability_tenant_context(current_user, tenant_id=requested_tenant_id)
    response = BrainSkillActionResponse(
        **brain_skill_service.update_skill_scope(
            skill_id,
            scope=payload.scope,
            owner_tenant_id=resolved_tenant_id if payload.scope == "tenant" else None,
        )
    )
    append_control_plane_audit_log(
        action="agent.brain_skill.scope_updated",
        user=_operator_identity(current_user),
        resource=f"brain_skill.{response.skill.id}",
        details=f"更新主脑 skill {response.skill.name} 的作用域",
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


@router.delete(
    "/{agent_id}",
    response_model=AgentDeleteResponse,
)
def delete_agent_route(
    agent_id: str,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> AgentDeleteResponse:
    response = AgentDeleteResponse(**delete_agent(agent_id))
    append_control_plane_audit_log(
        action="agent.deleted",
        user=_operator_identity(current_user),
        resource=f"agent.{response.agent_id}",
        details=f"删除 Agent {response.agent_id}",
    )
    return response


@router.put(
    "/{agent_id}/enabled",
    response_model=AgentActionResponse,
    dependencies=[Depends(require_permission("agents:reload"))],
)
def set_agent_enabled_route(
    agent_id: str,
    payload: AgentEnabledRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> AgentActionResponse:
    response = AgentActionResponse(**set_agent_enabled(agent_id, enabled=payload.enabled))
    append_control_plane_audit_log(
        action="agent.enabled.updated",
        user=_operator_identity(current_user),
        resource=f"agent.{agent_id}",
        details=f"设置 Agent 启用状态为 {payload.enabled}",
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
    tenant_id: str | None = Query(default=None),
) -> AgentActionResponse:
    resolved_tenant_id, include_all_tenants = _capability_tenant_context(current_user, tenant_id=tenant_id)
    response = AgentActionResponse(
        **update_agent_config(
            agent_id,
            payload.model_dump(exclude_unset=True),
            tenant_id=resolved_tenant_id,
            include_all_tenants=include_all_tenants,
        )
    )
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
