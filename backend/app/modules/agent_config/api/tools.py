from fastapi import APIRouter, Depends, Query

from app.modules.agent_config.registries.tool_catalog_service import tool_catalog_service
from app.modules.agent_config.schemas.tools import ToolCatalogResponse, ToolHealthResponse, ToolItem, ToolListResponse
from app.modules.organization.application.tenancy_service import DEFAULT_TENANT_ID, ROOT_SCOPE_ROLES, current_user_scope, resolve_scope
from app.platform.auth.authz import require_authenticated_user, require_permission


router = APIRouter(dependencies=[Depends(require_authenticated_user)])


def _capability_tenant_context(
    current_user: dict[str, object],
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
    response_model=ToolListResponse,
    dependencies=[Depends(require_permission("agents:read"))],
)
def list_tools_route(
    refresh: bool = Query(default=False),
    tenant_id: str | None = Query(default=None),
    scope: str | None = Query(default=None),
    current_user: dict[str, object] = Depends(require_authenticated_user),
) -> ToolListResponse:
    resolved_tenant_id, include_all_tenants = _capability_tenant_context(current_user, tenant_id=tenant_id)
    return ToolListResponse(
        **tool_catalog_service.list_tools(
            refresh=refresh,
            tenant_id=resolved_tenant_id,
            include_all_tenants=include_all_tenants,
            scope=scope,
        )
    )


@router.get(
    "/catalog",
    response_model=ToolCatalogResponse,
    dependencies=[Depends(require_permission("agents:read"))],
)
def list_tools_catalog_route(
    refresh: bool = Query(default=False),
    tenant_id: str | None = Query(default=None),
    scope: str | None = Query(default=None),
    current_user: dict[str, object] = Depends(require_authenticated_user),
) -> ToolCatalogResponse:
    resolved_tenant_id, include_all_tenants = _capability_tenant_context(current_user, tenant_id=tenant_id)
    return ToolCatalogResponse(
        **tool_catalog_service.get_catalog(
            refresh=refresh,
            tenant_id=resolved_tenant_id,
            include_all_tenants=include_all_tenants,
            scope=scope,
        )
    )


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
def get_tool_route(
    tool_id: str,
    refresh: bool = Query(default=False),
    tenant_id: str | None = Query(default=None),
    scope: str | None = Query(default=None),
    current_user: dict[str, object] = Depends(require_authenticated_user),
) -> ToolItem:
    resolved_tenant_id, include_all_tenants = _capability_tenant_context(current_user, tenant_id=tenant_id)
    return ToolItem(
        **tool_catalog_service.get_tool(
            tool_id,
            refresh=refresh,
            tenant_id=resolved_tenant_id,
            include_all_tenants=include_all_tenants,
            scope=scope,
        )
    )
