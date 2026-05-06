from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from app.modules.reception.application.intake_console_service import (
    get_intake_console_overview,
    get_intake_trace_detail,
)
from app.modules.reception.schemas.intake_console import (
    IntakeConsoleOverviewResponse,
    IntakeTraceDetailResponse,
)
from app.platform.auth.authz import (
    authenticate_websocket,
    require_authenticated_user,
    require_permission,
)


router = APIRouter(dependencies=[Depends(require_authenticated_user)])


@router.get(
    "/overview",
    response_model=IntakeConsoleOverviewResponse,
    dependencies=[Depends(require_permission("dashboard:read"))],
)
def get_filtered_intake_console_overview_route(
    tenant_id: str | None = Query(default=None, alias="tenantId"),
    channel: str | None = Query(default=None),
) -> IntakeConsoleOverviewResponse:
    return get_intake_console_overview(tenant_id=tenant_id, channel=channel)


@router.get(
    "/traces/{trace_id}",
    response_model=IntakeTraceDetailResponse,
    dependencies=[Depends(require_permission("dashboard:read"))],
)
def get_intake_trace_detail_route(trace_id: str) -> IntakeTraceDetailResponse:
    return get_intake_trace_detail(trace_id)


@router.websocket("/realtime")
async def realtime_intake_console(websocket: WebSocket) -> None:
    authenticate_websocket(websocket, permission="dashboard:read")
    await websocket.accept()
    tenant_id = str(websocket.query_params.get("tenantId") or "").strip() or None
    channel = str(websocket.query_params.get("channel") or "").strip() or None
    try:
        while True:
            payload = get_intake_console_overview(tenant_id=tenant_id, channel=channel)
            await websocket.send_json(payload.model_dump(mode="json", by_alias=True))
            await asyncio.sleep(3)
    except WebSocketDisconnect:
        return
