from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.modules.agent_config.protocol_bindings.schemas import (
    ProtocolBindingActionResponse,
    ProtocolBindingListResponse,
    ProtocolBindingUpsertRequest,
)
from app.modules.agent_config.protocol_bindings.service import (
    delete_protocol_binding,
    list_protocol_bindings,
    upsert_protocol_binding,
)
from app.platform.auth.authz import require_authenticated_user, require_permission


router = APIRouter(dependencies=[Depends(require_authenticated_user)])


@router.get(
    "",
    response_model=ProtocolBindingListResponse,
    dependencies=[Depends(require_permission("agents:read"))],
)
def list_protocol_bindings_route(
    tenant_id: str | None = Query(default=None, alias="tenantId"),
    agent_id: str | None = Query(default=None, alias="agentId"),
) -> ProtocolBindingListResponse:
    items = list_protocol_bindings(tenant_id=tenant_id, agent_id=agent_id)
    return ProtocolBindingListResponse(items=items, total=len(items))


@router.put(
    "",
    response_model=ProtocolBindingActionResponse,
    dependencies=[Depends(require_permission("settings:channel-integrations:write"))],
)
def upsert_protocol_binding_route(
    payload: ProtocolBindingUpsertRequest,
) -> ProtocolBindingActionResponse:
    binding = upsert_protocol_binding(payload)
    return ProtocolBindingActionResponse(
        ok=True,
        message="租户协议绑定已更新",
        binding=binding,
    )


@router.delete(
    "",
    response_model=ProtocolBindingActionResponse,
    dependencies=[Depends(require_permission("settings:channel-integrations:write"))],
)
def delete_protocol_binding_route(
    binding_id: str | None = Query(default=None, alias="bindingId"),
    tenant_id: str | None = Query(default=None, alias="tenantId"),
    agent_id: str | None = Query(default=None, alias="agentId"),
) -> ProtocolBindingActionResponse:
    try:
        deleted = delete_protocol_binding(
            binding_id=binding_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return ProtocolBindingActionResponse(
        ok=True,
        message="租户协议绑定已删除",
        binding=deleted,
    )
