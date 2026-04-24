from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from app.modules.agent_config.schemas.agents import Agent
from app.modules.agent_config.schemas.external_connections import (
    ExternalAgentListResponse,
    ExternalAgentRegistrationRequest,
    ExternalCapabilityActionResponse,
    ExternalCapabilityHealthItem,
    ExternalCapabilityHealthResponse,
    ExternalCapabilityGovernanceFamilySummary,
    ExternalCapabilityGovernanceOverviewResponse,
    ExternalCapabilityGovernanceSummary,
    ExternalCapabilityVersionItem,
    ExternalCapabilityVersionListResponse,
    ExternalCapabilityVersionUpdateRequest,
    ExternalFailureReportRequest,
    ExternalHeartbeatRequest,
    ExternalSkillRegistrationRequest,
)
from app.modules.organization.application.tenancy_service import resolve_scope
from app.modules.agent_config.registries.external_agent_registry_service import external_agent_registry_service
from app.modules.agent_config.registries.external_skill_registry_service import external_skill_registry_service
from app.platform.audit.control_plane_audit_service import append_control_plane_audit_log
from app.platform.auth.authz import require_authenticated_user, require_permission
from app.platform.auth.external_connection_auth_service import verify_external_request
from app.platform.observability.dashboard_service import get_audit_logs


router = APIRouter()


def _operator_identity(current_user: dict[str, Any]) -> str:
    return (
        str(current_user.get("email") or "").strip()
        or str(current_user.get("id") or "").strip()
        or "system"
    )


def _rollout_policy(item: dict[str, Any]) -> dict[str, Any]:
    raw = item.get("rollout_policy") if isinstance(item.get("rollout_policy"), dict) else {}
    canary_percent = raw.get("canary_percent", item.get("canary_percent"))
    route_key = raw.get("route_key", item.get("route_key"))
    return {
        "canary_percent": int(canary_percent or 0),
        "route_key": str(route_key or "global"),
    }


def _rollback_policy(item: dict[str, Any]) -> dict[str, Any]:
    raw = item.get("rollback_policy") if isinstance(item.get("rollback_policy"), dict) else {}
    active = raw.get("active")
    if active is None:
        active = raw.get("rollback_active")
    target_version_id = raw.get("target_version_id")
    if target_version_id is None:
        target_version_id = raw.get("rollback_target_version_id")
    return {
        "active": bool(active),
        "target_version_id": str(target_version_id or "").strip() or None,
    }


def _require_external_auth(
    payload: dict[str, Any],
    *,
    token: str | None,
    timestamp: str | None,
    signature: str | None,
    nonce: str | None,
) -> None:
    verify_external_request(payload=payload, token=token, timestamp=timestamp, signature=signature, nonce=nonce)


async def _request_payload(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def _health_items() -> list[dict[str, Any]]:
    external_agent_registry_service.prune_expired()
    external_skill_registry_service.prune_expired()
    items: list[dict[str, Any]] = []
    for item in external_agent_registry_service.list_agents(include_offline=True):
        items.append(
            {
                "capability_type": "agent",
                "id": item["id"],
                "name": item["name"],
                "family": item.get("agent_family"),
                "version": item.get("version"),
                "compatibility": list(item.get("compatibility") or []),
                "release_channel": item.get("release_channel"),
                "status": str(item.get("runtime_status") or item.get("status") or "unknown"),
                "routable": bool(item.get("routable")),
                "circuit_state": item.get("circuit_state"),
                "consecutive_failures": int(item.get("consecutive_failures") or 0),
                "next_retry_at": item.get("next_retry_at"),
                "last_heartbeat_at": item.get("last_heartbeat_at"),
                "health": {
                    "reason": item.get("runtime_status_reason"),
                    "last_error": item.get("last_error"),
                },
                "invocation": ((item.get("config_summary") or {}).get("invocation") or {}),
            }
        )
    for item in external_skill_registry_service.list_skills(include_offline=True):
        items.append(
            {
                "capability_type": "skill",
                "id": item["id"],
                "name": item["name"],
                "family": item.get("skill_family"),
                "version": item.get("version"),
                "compatibility": list(item.get("compatibility") or []),
                "release_channel": item.get("release_channel"),
                "status": str(item.get("health_status") or "unknown"),
                "routable": bool(item.get("routable")),
                "circuit_state": item.get("circuit_state"),
                "consecutive_failures": int(item.get("consecutive_failures") or 0),
                "next_retry_at": item.get("next_retry_at"),
                "last_heartbeat_at": item.get("last_heartbeat_at"),
                "health": dict(item.get("health_summary") or {}),
                "invocation": dict(item.get("invocation") or {}),
            }
        )
    items.sort(key=lambda item: (not item["routable"], item["capability_type"], item["name"].lower()))
    return items


def _pick_family_primary_item(items: list[dict[str, Any]]) -> dict[str, Any]:
    if not items:
        raise ValueError("items must not be empty")
    for item in items:
        if bool(item.get("default_version")):
            return item
    return items[0]


def _agent_governance_summary(family: str) -> dict[str, Any] | None:
    versions = external_agent_registry_service.list_versions(family)
    if not versions:
        return None
    primary = _pick_family_primary_item(versions)
    config_summary = primary.get("config_summary") if isinstance(primary.get("config_summary"), dict) else {}
    invocation = config_summary.get("invocation") if isinstance(config_summary.get("invocation"), dict) else {}
    default_item = next((item for item in versions if bool(item.get("default_version"))), None)
    return {
        "capability_type": "agent",
        "family": str(primary.get("agent_family") or family),
        "name": str(primary.get("name") or primary.get("id") or family),
        "current_id": str(primary.get("id") or ""),
        "current_version": primary.get("version"),
        "release_channel": primary.get("release_channel"),
        "compatibility": list(primary.get("compatibility") or []),
        "default_version_id": default_item.get("id") if isinstance(default_item, dict) else None,
        "fallback_version_id": primary.get("fallback_version_id"),
        "deprecated": bool(primary.get("deprecated")),
        "enabled": bool(primary.get("enabled", True)),
        "routable": bool(primary.get("routable")),
        "status": str(primary.get("runtime_status") or primary.get("status") or "unknown"),
        "circuit_state": primary.get("circuit_state"),
        "consecutive_failures": int(primary.get("consecutive_failures") or 0),
        "next_retry_at": primary.get("next_retry_at"),
        "last_heartbeat_at": primary.get("last_heartbeat_at"),
        "health": {
            "reason": primary.get("runtime_status_reason"),
            "last_error": primary.get("last_error"),
        },
        "invocation": invocation,
        "rollout_policy": _rollout_policy(primary),
        "rollback_policy": _rollback_policy(primary),
        "version_count": len(versions),
    }


def _skill_governance_summary(family: str) -> dict[str, Any] | None:
    versions = external_skill_registry_service.list_versions(family)
    if not versions:
        return None
    primary = _pick_family_primary_item(versions)
    default_item = next((item for item in versions if bool(item.get("default_version"))), None)
    return {
        "capability_type": "skill",
        "family": str(primary.get("skill_family") or family),
        "name": str(primary.get("name") or primary.get("id") or family),
        "current_id": str(primary.get("id") or ""),
        "current_version": primary.get("version"),
        "release_channel": primary.get("release_channel"),
        "compatibility": list(primary.get("compatibility") or []),
        "default_version_id": default_item.get("id") if isinstance(default_item, dict) else None,
        "fallback_version_id": primary.get("fallback_version_id"),
        "deprecated": bool(primary.get("deprecated")),
        "enabled": bool(primary.get("enabled", True)),
        "routable": bool(primary.get("routable")),
        "status": str(primary.get("health_status") or "unknown"),
        "circuit_state": primary.get("circuit_state"),
        "consecutive_failures": int(primary.get("consecutive_failures") or 0),
        "next_retry_at": primary.get("next_retry_at"),
        "last_heartbeat_at": primary.get("last_heartbeat_at"),
        "health": dict(primary.get("health_summary") or {}),
        "invocation": dict(primary.get("invocation") or {}),
        "rollout_policy": _rollout_policy(primary),
        "rollback_policy": _rollback_policy(primary),
        "version_count": len(versions),
    }


def _governance_items() -> list[dict[str, Any]]:
    external_agent_registry_service.prune_expired()
    external_skill_registry_service.prune_expired()
    items: list[dict[str, Any]] = []

    agent_families = {
        str(item.get("agent_family") or item.get("id") or "").strip()
        for item in external_agent_registry_service.list_agents(include_offline=True)
        if str(item.get("agent_family") or item.get("id") or "").strip()
    }
    for family in sorted(agent_families):
        summary = _agent_governance_summary(family)
        if summary is not None:
            items.append(summary)

    skill_families = {
        str(item.get("skill_family") or item.get("id") or "").strip()
        for item in external_skill_registry_service.list_skills(include_offline=True)
        if str(item.get("skill_family") or item.get("id") or "").strip()
    }
    for family in sorted(skill_families):
        summary = _skill_governance_summary(family)
        if summary is not None:
            items.append(summary)

    items.sort(key=lambda item: (item["capability_type"], not item["routable"], item["name"].lower()))
    return items


def _agent_version_items(family: str) -> list[ExternalCapabilityVersionItem]:
    return [
        ExternalCapabilityVersionItem(
            capability_type="agent",
            id=item["id"],
            family=str(item.get("agent_family") or ""),
            name=item["name"],
            version=str(item.get("version") or ""),
            release_channel=item.get("release_channel"),
            compatibility=list(item.get("compatibility") or []),
            default_version=bool(item.get("default_version")),
            fallback_version_id=item.get("fallback_version_id"),
            deprecated=bool(item.get("deprecated")),
            enabled=bool(item.get("enabled", True)),
            routable=bool(item.get("routable")),
            status=str(item.get("runtime_status") or item.get("status") or ""),
            rollout_policy=_rollout_policy(item),
            rollback_policy=_rollback_policy(item),
        )
        for item in external_agent_registry_service.list_versions(family)
    ]


def _skill_version_items(family: str) -> list[ExternalCapabilityVersionItem]:
    return [
        ExternalCapabilityVersionItem(
            capability_type="skill",
            id=item["id"],
            family=str(item.get("skill_family") or ""),
            name=item["name"],
            version=str(item.get("version") or ""),
            release_channel=item.get("release_channel"),
            compatibility=list(item.get("compatibility") or []),
            default_version=bool(item.get("default_version")),
            fallback_version_id=item.get("fallback_version_id"),
            deprecated=bool(item.get("deprecated")),
            enabled=bool(item.get("enabled", True)),
            routable=bool(item.get("routable")),
            status=str(item.get("health_status") or ""),
            rollout_policy=_rollout_policy(item),
            rollback_policy=_rollback_policy(item),
        )
        for item in external_skill_registry_service.list_versions(family)
    ]


@router.get(
    "/agents",
    response_model=ExternalAgentListResponse,
    dependencies=[Depends(require_authenticated_user), Depends(require_permission("external:read"))],
)
def list_external_agents_route() -> ExternalAgentListResponse:
    items = [Agent(**item) for item in external_agent_registry_service.list_agents(include_offline=True)]
    return ExternalAgentListResponse(items=items, total=len(items))


@router.get(
    "/agents/families/{family}/versions",
    response_model=ExternalCapabilityVersionListResponse,
    dependencies=[Depends(require_authenticated_user), Depends(require_permission("external:read"))],
)
def list_external_agent_versions_route(family: str) -> ExternalCapabilityVersionListResponse:
    items = _agent_version_items(family)
    return ExternalCapabilityVersionListResponse(items=items, total=len(items))


@router.get(
    "/skills/families/{family}/versions",
    response_model=ExternalCapabilityVersionListResponse,
    dependencies=[Depends(require_authenticated_user), Depends(require_permission("external:read"))],
)
def list_external_skill_versions_route(family: str) -> ExternalCapabilityVersionListResponse:
    items = _skill_version_items(family)
    return ExternalCapabilityVersionListResponse(items=items, total=len(items))


@router.get(
    "/health",
    response_model=ExternalCapabilityHealthResponse,
    dependencies=[Depends(require_authenticated_user), Depends(require_permission("external:read"))],
)
def get_external_capability_health_route() -> ExternalCapabilityHealthResponse:
    items = _health_items()
    summary = {
        "agents": len([item for item in items if item["capability_type"] == "agent"]),
        "skills": len([item for item in items if item["capability_type"] == "skill"]),
        "routable": len([item for item in items if item["routable"]]),
        "open_circuits": len([item for item in items if str(item.get("circuit_state") or "") == "open"]),
        "offline": len([item for item in items if str(item.get("status") or "") == "offline"]),
    }
    return ExternalCapabilityHealthResponse(
        items=[ExternalCapabilityHealthItem(**item) for item in items],
        total=len(items),
        summary=summary,
    )


@router.get(
    "/governance",
    response_model=ExternalCapabilityGovernanceOverviewResponse,
    dependencies=[Depends(require_authenticated_user), Depends(require_permission("external:read"))],
)
def get_external_capability_governance_route(
    audit_limit: int = Query(default=20, ge=1, le=100),
    tenant_id: str | None = Header(default=None, alias="X-WorkBot-Tenant-Id"),
    project_id: str | None = Header(default=None, alias="X-WorkBot-Project-Id"),
    environment: str | None = Header(default=None, alias="X-WorkBot-Environment"),
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> ExternalCapabilityGovernanceOverviewResponse:
    items = _governance_items()
    scope = resolve_scope(
        current_user=current_user,
        tenant_id=tenant_id,
        project_id=project_id,
        environment=environment,
    )
    audits = get_audit_logs(resource="external", limit=audit_limit, scope=scope)
    summary = {
        "agent_families": len([item for item in items if item["capability_type"] == "agent"]),
        "skill_families": len([item for item in items if item["capability_type"] == "skill"]),
        "total_families": len(items),
        "total_versions": sum(int(item.get("version_count") or 0) for item in items),
        "routable": len([item for item in items if item["routable"]]),
        "open_circuits": len([item for item in items if str(item.get("circuit_state") or "") == "open"]),
        "offline": len([item for item in items if str(item.get("status") or "") in {"offline", "unknown"}]),
    }
    return ExternalCapabilityGovernanceOverviewResponse(
        items=[ExternalCapabilityGovernanceFamilySummary(**item) for item in items],
        total=len(items),
        summary=ExternalCapabilityGovernanceSummary(**summary),
        recent_audits=audits["items"],
    )


@router.post("/agents/register", response_model=ExternalCapabilityActionResponse)
async def register_external_agent_route(
    request: Request,
    payload: ExternalAgentRegistrationRequest,
    x_workbot_external_token: str | None = Header(default=None),
    x_workbot_external_timestamp: str | None = Header(default=None),
    x_workbot_external_signature: str | None = Header(default=None),
    x_workbot_external_nonce: str | None = Header(default=None),
) -> ExternalCapabilityActionResponse:
    dumped = payload.model_dump(exclude_none=True)
    auth_payload = await _request_payload(request)
    _require_external_auth(
        auth_payload or dumped,
        token=x_workbot_external_token,
        timestamp=x_workbot_external_timestamp,
        signature=x_workbot_external_signature,
        nonce=x_workbot_external_nonce,
    )
    item = external_agent_registry_service.register_agent(dumped)
    return ExternalCapabilityActionResponse(ok=True, message="External agent registered", capability_type="agent", item=item)


@router.post("/skills/register", response_model=ExternalCapabilityActionResponse)
async def register_external_skill_route(
    request: Request,
    payload: ExternalSkillRegistrationRequest,
    x_workbot_external_token: str | None = Header(default=None),
    x_workbot_external_timestamp: str | None = Header(default=None),
    x_workbot_external_signature: str | None = Header(default=None),
    x_workbot_external_nonce: str | None = Header(default=None),
) -> ExternalCapabilityActionResponse:
    dumped = payload.model_dump(exclude_none=True)
    auth_payload = await _request_payload(request)
    _require_external_auth(
        auth_payload or dumped,
        token=x_workbot_external_token,
        timestamp=x_workbot_external_timestamp,
        signature=x_workbot_external_signature,
        nonce=x_workbot_external_nonce,
    )
    item = external_skill_registry_service.register_skill(dumped)
    return ExternalCapabilityActionResponse(ok=True, message="External skill registered", capability_type="skill", item=item)


@router.post("/agents/{agent_id}/heartbeat", response_model=ExternalCapabilityActionResponse)
async def external_agent_heartbeat_route(
    request: Request,
    agent_id: str,
    payload: ExternalHeartbeatRequest,
    x_workbot_external_token: str | None = Header(default=None),
    x_workbot_external_timestamp: str | None = Header(default=None),
    x_workbot_external_signature: str | None = Header(default=None),
    x_workbot_external_nonce: str | None = Header(default=None),
) -> ExternalCapabilityActionResponse:
    dumped = payload.model_dump(exclude_none=True)
    auth_payload = {**(await _request_payload(request)), "agent_id": agent_id}
    _require_external_auth(
        auth_payload or {"agent_id": agent_id, **dumped},
        token=x_workbot_external_token,
        timestamp=x_workbot_external_timestamp,
        signature=x_workbot_external_signature,
        nonce=x_workbot_external_nonce,
    )
    item = external_agent_registry_service.report_heartbeat(
        agent_id,
        status=payload.status,
        load=payload.load,
        queue_depth=payload.queue_depth,
        metadata=payload.metadata,
    )
    return ExternalCapabilityActionResponse(ok=True, message="External agent heartbeat accepted", capability_type="agent", item=item)


@router.post("/skills/{skill_id}/heartbeat", response_model=ExternalCapabilityActionResponse)
async def external_skill_heartbeat_route(
    request: Request,
    skill_id: str,
    payload: ExternalHeartbeatRequest,
    x_workbot_external_token: str | None = Header(default=None),
    x_workbot_external_timestamp: str | None = Header(default=None),
    x_workbot_external_signature: str | None = Header(default=None),
    x_workbot_external_nonce: str | None = Header(default=None),
) -> ExternalCapabilityActionResponse:
    dumped = payload.model_dump(exclude_none=True)
    auth_payload = {**(await _request_payload(request)), "skill_id": skill_id}
    _require_external_auth(
        auth_payload or {"skill_id": skill_id, **dumped},
        token=x_workbot_external_token,
        timestamp=x_workbot_external_timestamp,
        signature=x_workbot_external_signature,
        nonce=x_workbot_external_nonce,
    )
    item = external_skill_registry_service.report_heartbeat(
        skill_id,
        status=payload.status,
        metadata=payload.metadata,
    )
    return ExternalCapabilityActionResponse(ok=True, message="External skill heartbeat accepted", capability_type="skill", item=item)


@router.post("/agents/{agent_id}/failures", response_model=ExternalCapabilityActionResponse)
def report_external_agent_failure_route(
    agent_id: str,
    payload: ExternalFailureReportRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
    _: None = Depends(require_permission("external:write")),
) -> ExternalCapabilityActionResponse:
    try:
        item = external_agent_registry_service.report_failure(agent_id, error=payload.error)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    append_control_plane_audit_log(
        action="external.agent.failure_reported",
        user=_operator_identity(current_user),
        resource=f"external.agent.{agent_id}",
        details=f"外接 Agent 失败上报 {agent_id}",
        metadata={"error": payload.error, "circuit_state": item.get("circuit_state")},
    )
    return ExternalCapabilityActionResponse(ok=True, message="External agent failure recorded", capability_type="agent", item=item)


@router.post("/skills/{skill_id}/failures", response_model=ExternalCapabilityActionResponse)
def report_external_skill_failure_route(
    skill_id: str,
    payload: ExternalFailureReportRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
    _: None = Depends(require_permission("external:write")),
) -> ExternalCapabilityActionResponse:
    try:
        item = external_skill_registry_service.report_failure(skill_id, error=payload.error)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    append_control_plane_audit_log(
        action="external.skill.failure_reported",
        user=_operator_identity(current_user),
        resource=f"external.skill.{skill_id}",
        details=f"外接 Skill 失败上报 {skill_id}",
        metadata={"error": payload.error, "circuit_state": item.get("circuit_state")},
    )
    return ExternalCapabilityActionResponse(ok=True, message="External skill failure recorded", capability_type="skill", item=item)


@router.post("/agents/{agent_id}/recover", response_model=ExternalCapabilityActionResponse)
def recover_external_agent_route(
    agent_id: str,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
    _: None = Depends(require_permission("external:write")),
) -> ExternalCapabilityActionResponse:
    try:
        item = external_agent_registry_service.recover_agent(agent_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    append_control_plane_audit_log(
        action="external.agent.recovered",
        user=_operator_identity(current_user),
        resource=f"external.agent.{agent_id}",
        details=f"外接 Agent 恢复 {agent_id}",
        metadata={
            "runtime_status": item.get("runtime_status"),
            "circuit_state": item.get("circuit_state"),
            "routable": bool(item.get("routable")),
        },
    )
    return ExternalCapabilityActionResponse(ok=True, message="External agent recovered", capability_type="agent", item=item)


@router.post("/skills/{skill_id}/recover", response_model=ExternalCapabilityActionResponse)
def recover_external_skill_route(
    skill_id: str,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
    _: None = Depends(require_permission("external:write")),
) -> ExternalCapabilityActionResponse:
    try:
        item = external_skill_registry_service.recover_skill(skill_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    append_control_plane_audit_log(
        action="external.skill.recovered",
        user=_operator_identity(current_user),
        resource=f"external.skill.{skill_id}",
        details=f"外接 Skill 恢复 {skill_id}",
        metadata={
            "health_status": item.get("health_status"),
            "circuit_state": item.get("circuit_state"),
            "routable": bool(item.get("routable")),
        },
    )
    return ExternalCapabilityActionResponse(ok=True, message="External skill recovered", capability_type="skill", item=item)


@router.post("/agents/{agent_id}/promote", response_model=ExternalCapabilityActionResponse)
def promote_external_agent_version_route(
    agent_id: str,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
    _: None = Depends(require_permission("external:write")),
) -> ExternalCapabilityActionResponse:
    try:
        item = external_agent_registry_service.promote_version(agent_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    append_control_plane_audit_log(
        action="external.agent.version_promoted",
        user=_operator_identity(current_user),
        resource=f"external.agent.{agent_id}",
        details=f"外接 Agent 版本切主 {agent_id}",
        metadata={"family": item.get("agent_family"), "version": item.get("version")},
    )
    return ExternalCapabilityActionResponse(ok=True, message="External agent version promoted", capability_type="agent", item=item)


@router.post("/skills/{skill_id}/promote", response_model=ExternalCapabilityActionResponse)
def promote_external_skill_version_route(
    skill_id: str,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
    _: None = Depends(require_permission("external:write")),
) -> ExternalCapabilityActionResponse:
    try:
        item = external_skill_registry_service.promote_version(skill_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    append_control_plane_audit_log(
        action="external.skill.version_promoted",
        user=_operator_identity(current_user),
        resource=f"external.skill.{skill_id}",
        details=f"外接 Skill 版本切主 {skill_id}",
        metadata={"family": item.get("skill_family"), "version": item.get("version")},
    )
    return ExternalCapabilityActionResponse(ok=True, message="External skill version promoted", capability_type="skill", item=item)


@router.post("/agents/{agent_id}/set-fallback", response_model=ExternalCapabilityActionResponse)
def set_external_agent_fallback_route(
    agent_id: str,
    payload: ExternalCapabilityVersionUpdateRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
    _: None = Depends(require_permission("external:write")),
) -> ExternalCapabilityActionResponse:
    try:
        item = external_agent_registry_service.set_fallback_version(agent_id, payload.fallback_version_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    append_control_plane_audit_log(
        action="external.agent.fallback_updated",
        user=_operator_identity(current_user),
        resource=f"external.agent.{agent_id}",
        details=f"外接 Agent fallback 更新 {agent_id}",
        metadata={"fallback_version_id": item.get("fallback_version_id")},
    )
    return ExternalCapabilityActionResponse(ok=True, message="External agent fallback updated", capability_type="agent", item=item)


@router.post("/skills/{skill_id}/set-fallback", response_model=ExternalCapabilityActionResponse)
def set_external_skill_fallback_route(
    skill_id: str,
    payload: ExternalCapabilityVersionUpdateRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
    _: None = Depends(require_permission("external:write")),
) -> ExternalCapabilityActionResponse:
    try:
        item = external_skill_registry_service.set_fallback_version(skill_id, payload.fallback_version_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    append_control_plane_audit_log(
        action="external.skill.fallback_updated",
        user=_operator_identity(current_user),
        resource=f"external.skill.{skill_id}",
        details=f"外接 Skill fallback 更新 {skill_id}",
        metadata={"fallback_version_id": item.get("fallback_version_id")},
    )
    return ExternalCapabilityActionResponse(ok=True, message="External skill fallback updated", capability_type="skill", item=item)


@router.post("/agents/{agent_id}/rollout-policy", response_model=ExternalCapabilityActionResponse)
def set_external_agent_rollout_policy_route(
    agent_id: str,
    payload: ExternalCapabilityVersionUpdateRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
    _: None = Depends(require_permission("external:write")),
) -> ExternalCapabilityActionResponse:
    try:
        item = external_agent_registry_service.set_rollout_policy(agent_id, payload.rollout_policy)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    append_control_plane_audit_log(
        action="external.agent.rollout_policy_updated",
        user=_operator_identity(current_user),
        resource=f"external.agent.{agent_id}",
        details=f"外接 Agent 灰度策略更新 {agent_id}",
        metadata={"rollout_policy": _rollout_policy(item)},
    )
    return ExternalCapabilityActionResponse(ok=True, message="External agent rollout policy updated", capability_type="agent", item=item)


@router.post("/skills/{skill_id}/rollout-policy", response_model=ExternalCapabilityActionResponse)
def set_external_skill_rollout_policy_route(
    skill_id: str,
    payload: ExternalCapabilityVersionUpdateRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
    _: None = Depends(require_permission("external:write")),
) -> ExternalCapabilityActionResponse:
    try:
        item = external_skill_registry_service.set_rollout_policy(skill_id, payload.rollout_policy)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    append_control_plane_audit_log(
        action="external.skill.rollout_policy_updated",
        user=_operator_identity(current_user),
        resource=f"external.skill.{skill_id}",
        details=f"外接 Skill 灰度策略更新 {skill_id}",
        metadata={"rollout_policy": _rollout_policy(item)},
    )
    return ExternalCapabilityActionResponse(ok=True, message="External skill rollout policy updated", capability_type="skill", item=item)


@router.post("/agents/{agent_id}/rollback", response_model=ExternalCapabilityActionResponse)
def set_external_agent_rollback_policy_route(
    agent_id: str,
    payload: ExternalCapabilityVersionUpdateRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
    _: None = Depends(require_permission("external:write")),
) -> ExternalCapabilityActionResponse:
    try:
        item = external_agent_registry_service.set_rollback_policy(agent_id, payload.rollback_policy)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    append_control_plane_audit_log(
        action="external.agent.rollback_policy_updated",
        user=_operator_identity(current_user),
        resource=f"external.agent.{agent_id}",
        details=f"外接 Agent 回滚策略更新 {agent_id}",
        metadata={"rollback_policy": _rollback_policy(item)},
    )
    return ExternalCapabilityActionResponse(ok=True, message="External agent rollback policy updated", capability_type="agent", item=item)


@router.post("/skills/{skill_id}/rollback", response_model=ExternalCapabilityActionResponse)
def set_external_skill_rollback_policy_route(
    skill_id: str,
    payload: ExternalCapabilityVersionUpdateRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
    _: None = Depends(require_permission("external:write")),
) -> ExternalCapabilityActionResponse:
    try:
        item = external_skill_registry_service.set_rollback_policy(skill_id, payload.rollback_policy)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    append_control_plane_audit_log(
        action="external.skill.rollback_policy_updated",
        user=_operator_identity(current_user),
        resource=f"external.skill.{skill_id}",
        details=f"外接 Skill 回滚策略更新 {skill_id}",
        metadata={"rollback_policy": _rollback_policy(item)},
    )
    return ExternalCapabilityActionResponse(ok=True, message="External skill rollback policy updated", capability_type="skill", item=item)


@router.post("/agents/{agent_id}/deprecate", response_model=ExternalCapabilityActionResponse)
def set_external_agent_deprecated_route(
    agent_id: str,
    payload: ExternalCapabilityVersionUpdateRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
    _: None = Depends(require_permission("external:write")),
) -> ExternalCapabilityActionResponse:
    try:
        item = external_agent_registry_service.set_deprecated(agent_id, deprecated=bool(payload.deprecated))
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    append_control_plane_audit_log(
        action="external.agent.deprecation_updated",
        user=_operator_identity(current_user),
        resource=f"external.agent.{agent_id}",
        details=f"外接 Agent deprecated 状态更新 {agent_id}",
        metadata={"deprecated": bool(item.get("deprecated"))},
    )
    return ExternalCapabilityActionResponse(ok=True, message="External agent deprecation updated", capability_type="agent", item=item)


@router.post("/skills/{skill_id}/deprecate", response_model=ExternalCapabilityActionResponse)
def set_external_skill_deprecated_route(
    skill_id: str,
    payload: ExternalCapabilityVersionUpdateRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
    _: None = Depends(require_permission("external:write")),
) -> ExternalCapabilityActionResponse:
    try:
        item = external_skill_registry_service.set_deprecated(skill_id, deprecated=bool(payload.deprecated))
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    append_control_plane_audit_log(
        action="external.skill.deprecation_updated",
        user=_operator_identity(current_user),
        resource=f"external.skill.{skill_id}",
        details=f"外接 Skill deprecated 状态更新 {skill_id}",
        metadata={"deprecated": bool(item.get("deprecated"))},
    )
    return ExternalCapabilityActionResponse(ok=True, message="External skill deprecation updated", capability_type="skill", item=item)
