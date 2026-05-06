from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.modules.reception.channel_binding.schemas import (
    ConfirmWecomBindSessionRequest,
    ConfirmWecomBindSessionResponse,
    PublicWecomBindSessionResponse,
)
from app.modules.reception.channel_binding.service import wecom_channel_binding_service


router = APIRouter()


@router.get(
    "/wecom/{token}",
    response_model=PublicWecomBindSessionResponse,
)
def get_public_wecom_bind_session_route(token: str) -> PublicWecomBindSessionResponse:
    try:
        session = wecom_channel_binding_service.get_public_session(token)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return PublicWecomBindSessionResponse(
        tenant_id=session.tenant_id,
        tenant_name=session.tenant_name,
        session=session,
    )


@router.post(
    "/wecom/{token}/confirm",
    response_model=ConfirmWecomBindSessionResponse,
)
def confirm_public_wecom_bind_session_route(
    token: str,
    payload: ConfirmWecomBindSessionRequest,
) -> ConfirmWecomBindSessionResponse:
    try:
        binding, session = wecom_channel_binding_service.confirm_bind_session(token, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return ConfirmWecomBindSessionResponse(
        ok=True,
        message="扫码绑定已完成",
        binding=binding,
        session=session,
    )
