from typing import Any

from fastapi import APIRouter, Depends, Query

from app.core.authz import require_authenticated_user, require_permission
from app.schemas.tool_sources import ToolSourceDetailResponse, ToolSourceListResponse, ToolSourceScanResponse
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


@router.get(
    "/{source_id}",
    response_model=ToolSourceDetailResponse,
    dependencies=[Depends(require_permission("tool_sources:read"))],
)
def get_tool_source_detail_route(source_id: str, refresh: bool = Query(default=False)) -> ToolSourceDetailResponse:
    return ToolSourceDetailResponse(**tool_source_service.get_source(source_id, refresh=refresh))
