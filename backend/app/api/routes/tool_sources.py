from fastapi import APIRouter, Depends, Query

from app.core.authz import require_authenticated_user, require_permission
from app.schemas.tool_sources import ToolSourceDetailResponse, ToolSourceListResponse, ToolSourceScanResponse
from app.services.tool_source_service import tool_source_service


router = APIRouter(dependencies=[Depends(require_authenticated_user)])


@router.get(
    "",
    response_model=ToolSourceListResponse,
    dependencies=[Depends(require_permission("agents:read"))],
)
def list_tool_sources_route(refresh: bool = Query(default=False)) -> ToolSourceListResponse:
    return ToolSourceListResponse(**tool_source_service.list_sources(refresh=refresh))


@router.post(
    "/scan",
    response_model=ToolSourceScanResponse,
    dependencies=[Depends(require_permission("agents:reload"))],
)
def scan_tool_sources_route() -> ToolSourceScanResponse:
    return ToolSourceScanResponse(**tool_source_service.scan_sources())


@router.get(
    "/{source_id}",
    response_model=ToolSourceDetailResponse,
    dependencies=[Depends(require_permission("agents:read"))],
)
def get_tool_source_detail_route(source_id: str, refresh: bool = Query(default=False)) -> ToolSourceDetailResponse:
    return ToolSourceDetailResponse(**tool_source_service.get_source(source_id, refresh=refresh))
