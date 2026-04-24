import asyncio
from datetime import UTC, datetime
import hmac
from urllib.parse import quote
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import Response

from app.config import get_settings
from app.modules.organization.application.tenancy_service import resolve_scope
from app.platform.auth.authz import authenticate_websocket, require_authenticated_user, require_permission
from app.platform.observability.dashboard_service import (
    export_prometheus_metrics,
    export_audit_logs_csv,
    get_audit_logs,
    get_stats,
    next_realtime_payload,
)
from app.platform.observability.schemas.dashboard import AuditLogsResponse, DashboardStatsResponse

router = APIRouter()


def _extract_bearer_token(value: str | None) -> str | None:
    if not value:
        return None
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer":
        return None
    normalized = token.strip()
    return normalized or None


def require_dashboard_metrics_access(request: Request) -> dict[str, Any]:
    cached_user = getattr(request.state, "current_user", None)
    if cached_user is not None:
        return cached_user

    settings = get_settings()
    configured_metrics_token = str(settings.metrics_scrape_token or "").strip()
    presented_metrics_token = str(request.headers.get("X-WorkBot-Metrics-Token") or "").strip()
    if configured_metrics_token and presented_metrics_token:
        if not hmac.compare_digest(presented_metrics_token, configured_metrics_token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid metrics scrape token",
            )
        request.state.current_user = {
            "id": "metrics-scraper",
            "email": "metrics-scraper@workbot.local",
            "role": "operator",
            "status": "active",
            "auth_type": "metrics_scrape_token",
        }
        return request.state.current_user

    bearer_token = _extract_bearer_token(request.headers.get("authorization"))
    if configured_metrics_token and bearer_token and hmac.compare_digest(
        bearer_token,
        configured_metrics_token,
    ):
        request.state.current_user = {
            "id": "metrics-scraper",
            "email": "metrics-scraper@workbot.local",
            "role": "operator",
            "status": "active",
            "auth_type": "metrics_scrape_token",
        }
        return request.state.current_user

    current_user = require_authenticated_user(request)
    require_permission("dashboard:read")(request)
    return current_user


@router.get(
    "/stats",
    response_model=DashboardStatsResponse,
    dependencies=[Depends(require_permission("dashboard:read"))],
)
def get_dashboard_stats(
    tenant_id: str | None = Header(default=None, alias="X-WorkBot-Tenant-Id"),
    project_id: str | None = Header(default=None, alias="X-WorkBot-Project-Id"),
    environment: str | None = Header(default=None, alias="X-WorkBot-Environment"),
    current_user: dict = Depends(require_authenticated_user),
) -> DashboardStatsResponse:
    scope = resolve_scope(
        current_user=current_user,
        tenant_id=tenant_id,
        project_id=project_id,
        environment=environment,
    )
    return DashboardStatsResponse(**get_stats(scope=scope))


@router.get(
    "/metrics",
)
def get_dashboard_metrics(
    tenant_id: str | None = Header(default=None, alias="X-WorkBot-Tenant-Id"),
    project_id: str | None = Header(default=None, alias="X-WorkBot-Project-Id"),
    environment: str | None = Header(default=None, alias="X-WorkBot-Environment"),
    current_user: dict[str, Any] = Depends(require_dashboard_metrics_access),
) -> Response:
    scope = resolve_scope(
        current_user=current_user,
        tenant_id=tenant_id,
        project_id=project_id,
        environment=environment,
    )
    payload = export_prometheus_metrics(scope=scope)
    return Response(
        content=payload,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@router.get(
    "/logs",
    response_model=AuditLogsResponse,
    dependencies=[Depends(require_permission("logs:read"))],
)
def get_dashboard_logs(
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    layer: str | None = Query(default=None),
    user: str | None = Query(default=None),
    resource: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    tenant_id: str | None = Header(default=None, alias="X-WorkBot-Tenant-Id"),
    project_id: str | None = Header(default=None, alias="X-WorkBot-Project-Id"),
    environment: str | None = Header(default=None, alias="X-WorkBot-Environment"),
    current_user: dict = Depends(require_authenticated_user),
) -> AuditLogsResponse:
    scope = resolve_scope(
        current_user=current_user,
        tenant_id=tenant_id,
        project_id=project_id,
        environment=environment,
    )
    return AuditLogsResponse(
        **get_audit_logs(
            search=search,
            status_filter=status,
            layer=layer,
            user=user,
            resource=resource,
            limit=limit,
            offset=offset,
            scope=scope,
        )
    )


@router.get(
    "/logs/export",
    dependencies=[Depends(require_permission("logs:read"))],
)
def export_dashboard_logs(
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    layer: str | None = Query(default=None),
    user: str | None = Query(default=None),
    resource: str | None = Query(default=None),
    tenant_id: str | None = Header(default=None, alias="X-WorkBot-Tenant-Id"),
    project_id: str | None = Header(default=None, alias="X-WorkBot-Project-Id"),
    environment: str | None = Header(default=None, alias="X-WorkBot-Environment"),
    current_user: dict = Depends(require_authenticated_user),
) -> Response:
    scope = resolve_scope(
        current_user=current_user,
        tenant_id=tenant_id,
        project_id=project_id,
        environment=environment,
    )
    csv_content = export_audit_logs_csv(
        search=search,
        status_filter=status,
        layer=layer,
        user=user,
        resource=resource,
        scope=scope,
    )
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    filename = f"workbot-audit-logs-{timestamp}.csv"
    quoted_filename = quote(filename)
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f"attachment; filename={filename}; filename*=UTF-8''{quoted_filename}"
            )
        },
    )


@router.websocket("/realtime")
async def realtime_dashboard(websocket: WebSocket) -> None:
    authenticate_websocket(websocket, permission="dashboard:read")
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(next_realtime_payload())
            await asyncio.sleep(3)
    except WebSocketDisconnect:
        return
