from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.platform.contracts.api_model import APIModel


WecomBindSessionStatus = Literal["pending", "bound", "expired", "cancelled"]


class WecomChannelBinding(APIModel):
    tenant_id: str
    tenant_name: str | None = None
    channel: str = "wecom"
    display_name: str
    external_account: str | None = None
    status: Literal["bound"] = "bound"
    bound_at: str
    updated_at: str


class WecomBindSession(APIModel):
    session_id: str
    tenant_id: str
    tenant_name: str | None = None
    channel: str = "wecom"
    status: WecomBindSessionStatus
    bind_path: str
    qr_code_url: str | None = None
    scan_status: str | None = None
    expires_at: str
    created_at: str
    updated_at: str
    display_name: str | None = None
    external_account: str | None = None


class WecomBindingStateResponse(APIModel):
    tenant_id: str | None = None
    tenant_name: str | None = None
    binding: WecomChannelBinding | None = None
    active_session: WecomBindSession | None = None


class CreateWecomBindSessionRequest(APIModel):
    tenant_id: str
    tenant_name: str | None = None


class CreateWecomBindSessionResponse(APIModel):
    ok: bool
    message: str
    state: WecomBindingStateResponse


class DeleteWecomBindingResponse(APIModel):
    ok: bool
    message: str
    state: WecomBindingStateResponse


class PublicWecomBindSessionResponse(APIModel):
    tenant_id: str
    tenant_name: str | None = None
    session: WecomBindSession


class ConfirmWecomBindSessionRequest(APIModel):
    display_name: str
    external_account: str | None = None


class ConfirmWecomBindSessionResponse(APIModel):
    ok: bool
    message: str
    binding: WecomChannelBinding
    session: WecomBindSession


class WecomChannelCredential(APIModel):
    tenant_id: str
    tenant_name: str | None = None
    channel: str = "wecom"
    account_id: str
    access_token: str
    base_url: str
    user_id: str | None = None
    updated_at: str


class WecomStoredBindSession(WecomBindSession):
    qr_code_token: str | None = None
    qr_poll_base_url: str | None = None


class WecomBindingStateStore(APIModel):
    bindings: list[WecomChannelBinding] = Field(default_factory=list)
    sessions: list[WecomStoredBindSession] = Field(default_factory=list)
    credentials: list[WecomChannelCredential] = Field(default_factory=list)
    updated_at: str | None = None
