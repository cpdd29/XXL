from typing import Any

from fastapi import APIRouter, Depends, Query

from app.core.authz import require_authenticated_user, require_permission
from app.schemas.tool_sources import (
    ToolSourceDeleteResponse,
    ToolSourceDetailResponse,
    ToolSourceListResponse,
    ToolSourceMcpRegistrationRequest,
    ToolSourceRegistrationResponse,
    ToolSourceScanResponse,
    ToolSourceSkillRegistrationRequest,
)
from app.services.control_plane_audit_service import append_control_plane_audit_log
from app.services.tool_source_service import tool_source_service


router = APIRouter(dependencies=[Depends(require_authenticated_user)])


def _operator_identity(current_user: dict[str, Any]) -> str:
    return (
        str(current_user.get("email") or "").strip()
        or str(current_user.get("id") or "").strip()
        or "system"
    )


@router.get(
    "",
    response_model=ToolSourceListResponse,
    dependencies=[Depends(require_permission("tool_sources:read"))],
)
def list_tool_sources_route(refresh: bool = Query(default=False)) -> ToolSourceListResponse:
    return ToolSourceListResponse(**tool_source_service.list_sources(refresh=refresh))


@router.post(
    "/scan",
    response_model=ToolSourceScanResponse,
    dependencies=[Depends(require_permission("tool_sources:scan"))],
)
def scan_tool_sources_route(
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> ToolSourceScanResponse:
    response = ToolSourceScanResponse(**tool_source_service.scan_sources())
    append_control_plane_audit_log(
        action="tool_sources.scanned",
        user=_operator_identity(current_user),
        resource="tool_sources",
        details="扫描外接工具源与能力目录",
    )
    return response


@router.post(
    "/register-skill",
    response_model=ToolSourceRegistrationResponse,
    dependencies=[Depends(require_permission("tool_sources:scan"))],
)
def register_tool_source_skill_route(
    payload: ToolSourceSkillRegistrationRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> ToolSourceRegistrationResponse:
    response = ToolSourceRegistrationResponse(
        **tool_source_service.register_external_skill_tool(payload.model_dump(exclude_none=True))
    )
    append_control_plane_audit_log(
        action="tool_sources.skill_registered",
        user=_operator_identity(current_user),
        resource=f"tool_sources.{response.source_id}",
        details=f"新增外接 Skill {response.tool_id}",
        metadata={"source_id": response.source_id, "tool_id": response.tool_id},
    )
    return response


@router.post(
    "/register-mcp",
    response_model=ToolSourceRegistrationResponse,
    dependencies=[Depends(require_permission("tool_sources:scan"))],
)
def register_tool_source_mcp_route(
    payload: ToolSourceMcpRegistrationRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> ToolSourceRegistrationResponse:
    response = ToolSourceRegistrationResponse(
        **tool_source_service.register_external_mcp_tool(payload.model_dump(exclude_none=True))
    )
    append_control_plane_audit_log(
        action="tool_sources.mcp_registered",
        user=_operator_identity(current_user),
        resource=f"tool_sources.{response.source_id}",
        details=f"新增外接 MCP {response.tool_id}",
        metadata={"source_id": response.source_id, "tool_id": response.tool_id},
    )
    return response


@router.put(
    "/tools/{tool_id}/skill",
    response_model=ToolSourceRegistrationResponse,
    dependencies=[Depends(require_permission("tool_sources:scan"))],
)
def update_tool_source_skill_route(
    tool_id: str,
    payload: ToolSourceSkillRegistrationRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> ToolSourceRegistrationResponse:
    response = ToolSourceRegistrationResponse(
        **tool_source_service.update_external_skill_tool(tool_id, payload.model_dump(exclude_none=True))
    )
    append_control_plane_audit_log(
        action="tool_sources.skill_updated",
        user=_operator_identity(current_user),
        resource=f"tool_sources.{response.source_id}",
        details=f"更新外接 Skill {response.tool_id}",
        metadata={"source_id": response.source_id, "tool_id": response.tool_id},
    )
    return response


@router.put(
    "/tools/{tool_id}/mcp",
    response_model=ToolSourceRegistrationResponse,
    dependencies=[Depends(require_permission("tool_sources:scan"))],
)
def update_tool_source_mcp_route(
    tool_id: str,
    payload: ToolSourceMcpRegistrationRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> ToolSourceRegistrationResponse:
    response = ToolSourceRegistrationResponse(
        **tool_source_service.update_external_mcp_tool(tool_id, payload.model_dump(exclude_none=True))
    )
    append_control_plane_audit_log(
        action="tool_sources.mcp_updated",
        user=_operator_identity(current_user),
        resource=f"tool_sources.{response.source_id}",
        details=f"更新外接 MCP {response.tool_id}",
        metadata={"source_id": response.source_id, "tool_id": response.tool_id},
    )
    return response


@router.delete(
    "/tools/{tool_id}",
    response_model=ToolSourceDeleteResponse,
    dependencies=[Depends(require_permission("tool_sources:scan"))],
)
def delete_tool_source_tool_route(
    tool_id: str,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> ToolSourceDeleteResponse:
    response = ToolSourceDeleteResponse(**tool_source_service.delete_external_registry_tool(tool_id))
    append_control_plane_audit_log(
        action="tool_sources.tool_deleted",
        user=_operator_identity(current_user),
        resource=f"tool_sources.{response.source_id}",
        details=f"删除外接能力 {response.tool_id}",
        metadata={"source_id": response.source_id, "tool_id": response.tool_id},
    )
    return response


@router.get(
    "/{source_id}",
    response_model=ToolSourceDetailResponse,
    dependencies=[Depends(require_permission("tool_sources:read"))],
)
def get_tool_source_detail_route(source_id: str, refresh: bool = Query(default=False)) -> ToolSourceDetailResponse:
    return ToolSourceDetailResponse(**tool_source_service.get_source(source_id, refresh=refresh))
