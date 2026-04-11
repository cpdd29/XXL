from fastapi import APIRouter, Depends, Query

from app.core.authz import require_authenticated_user, require_permission
from app.schemas.tools import ToolCatalogResponse, ToolHealthResponse, ToolItem, ToolListResponse
from app.services.tool_catalog_service import tool_catalog_service


router = APIRouter(dependencies=[Depends(require_authenticated_user)])


@router.get(
    "",
    response_model=ToolListResponse,
    dependencies=[Depends(require_permission("agents:read"))],
)
def list_tools_route(refresh: bool = Query(default=False)) -> ToolListResponse:
    return ToolListResponse(**tool_catalog_service.list_tools(refresh=refresh))


@router.get(
    "/catalog",
    response_model=ToolCatalogResponse,
    dependencies=[Depends(require_permission("agents:read"))],
)
def list_tools_catalog_route(refresh: bool = Query(default=False)) -> ToolCatalogResponse:
    return ToolCatalogResponse(**tool_catalog_service.get_catalog(refresh=refresh))


@router.get(
    "/health",
    response_model=ToolHealthResponse,
    dependencies=[Depends(require_permission("agents:read"))],
)
def list_tools_health_route(refresh: bool = Query(default=False)) -> ToolHealthResponse:
    return ToolHealthResponse(**tool_catalog_service.get_health(refresh=refresh))


@router.get(
    "/{tool_id}",
    response_model=ToolItem,
    dependencies=[Depends(require_permission("agents:read"))],
)
def get_tool_route(tool_id: str, refresh: bool = Query(default=False)) -> ToolItem:
    return ToolItem(**tool_catalog_service.get_tool(tool_id, refresh=refresh))
