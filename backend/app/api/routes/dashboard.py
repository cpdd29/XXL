import asyncio
from datetime import UTC, datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

from app.core.authz import authenticate_websocket, require_authenticated_user, require_permission
from app.schemas.dashboard import AuditLogsResponse, DashboardStatsResponse
from app.services.dashboard_service import (
    export_audit_logs_csv,
    get_audit_logs,
    get_stats,
    next_realtime_payload,
)

router = APIRouter(dependencies=[Depends(require_authenticated_user)])


@router.get(
    "/stats",
    response_model=DashboardStatsResponse,
    dependencies=[Depends(require_permission("dashboard:read"))],
)
def get_dashboard_stats() -> DashboardStatsResponse:
    return DashboardStatsResponse(**get_stats())


@router.get(
    "/logs",
    response_model=AuditLogsResponse,
    dependencies=[Depends(require_permission("logs:read"))],
)
def get_dashboard_logs(
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    user: str | None = Query(default=None),
    resource: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AuditLogsResponse:
    return AuditLogsResponse(
        **get_audit_logs(
            search=search,
            status_filter=status,
            user=user,
            resource=resource,
            limit=limit,
            offset=offset,
        )
    )


@router.get(
    "/logs/export",
    dependencies=[Depends(require_permission("logs:read"))],
)
def export_dashboard_logs(
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    user: str | None = Query(default=None),
    resource: str | None = Query(default=None),
) -> Response:
    csv_content = export_audit_logs_csv(
        search=search,
        status_filter=status,
        user=user,
        resource=resource,
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
