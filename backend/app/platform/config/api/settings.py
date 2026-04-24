from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.platform.approval.schemas.approvals import ApprovalActionResponse, ApprovalItem
from app.platform.auth.authz import require_authenticated_user, require_permission
from app.platform.config.schemas.settings import (
    AgentApiSettingsResponse,
    ChannelIntegrationSettingsResponse,
    GeneralSettingsResponse,
    SecurityPolicySettingsResponse,
    UpdateAgentApiSettingsRequest,
    UpdateChannelIntegrationSettingsRequest,
    UpdateGeneralSettingsRequest,
    UpdateSecurityPolicySettingsRequest,
)
from app.platform.approval.approval_service import (
    create_bound_approval,
    require_approved_execution,
)
from app.platform.config.settings_service import (
    get_agent_api_settings,
    get_channel_integration_settings,
    get_general_settings,
    get_security_policy_settings,
    update_agent_api_settings,
    update_channel_integration_settings,
    update_general_settings,
    update_security_policy_settings,
)
from app.modules.reception.channel_ingress.dingtalk_stream_service import dingtalk_stream_service
from app.platform.audit.control_plane_audit_service import append_control_plane_audit_log


router = APIRouter(dependencies=[Depends(require_authenticated_user)])


def _operator_identity(current_user: dict[str, Any]) -> str:
    return (
        str(current_user.get("email") or "").strip()
        or str(current_user.get("id") or "").strip()
        or "system"
    )


@router.get(
    "/general",
    response_model=GeneralSettingsResponse,
    dependencies=[Depends(require_permission("settings:read"))],
)
def get_general_settings_route() -> GeneralSettingsResponse:
    return GeneralSettingsResponse(**get_general_settings())


@router.put(
    "/general",
    response_model=GeneralSettingsResponse,
    dependencies=[Depends(require_permission("settings:general:write"))],
)
def update_general_settings_route(
    payload: UpdateGeneralSettingsRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> GeneralSettingsResponse:
    response = GeneralSettingsResponse(**update_general_settings(payload.model_dump(exclude_none=True)))
    append_control_plane_audit_log(
        action="settings.general.updated",
        user=_operator_identity(current_user),
        resource="settings.general",
        details="更新主脑通用设置",
    )
    return response


@router.get(
    "/security-policy",
    response_model=SecurityPolicySettingsResponse,
    dependencies=[Depends(require_permission("settings:read"))],
)
def get_security_policy_settings_route() -> SecurityPolicySettingsResponse:
    return SecurityPolicySettingsResponse(**get_security_policy_settings())


@router.put(
    "/security-policy",
    response_model=SecurityPolicySettingsResponse | ApprovalActionResponse,
    dependencies=[Depends(require_permission("settings:security-policy:write"))],
)
def update_security_policy_settings_route(
    payload: UpdateSecurityPolicySettingsRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> SecurityPolicySettingsResponse:
    operator = _operator_identity(current_user)
    request_payload = payload.model_dump(
        exclude_none=True,
        exclude={"approval_id", "approval_reason", "approval_note"},
    )
    if not payload.approval_id:
        approval = create_bound_approval(
            request_type="settings_change",
            title="更新主脑安全策略阈值",
            resource="settings.security_policy",
            requested_by=operator,
            request_payload=request_payload,
            target_action="settings.security_policy.update",
            reason=payload.approval_reason,
            note=payload.approval_note,
        )
        return JSONResponse(
            status_code=202,
            content=ApprovalActionResponse(
                ok=True,
                message="Approval required before updating security policy",
                approval=ApprovalItem(**approval),
                approval_required=True,
            ).model_dump(by_alias=True, exclude_none=True),
        )
    require_approved_execution(
        payload.approval_id,
        request_type="settings_change",
        resource="settings.security_policy",
        request_payload=request_payload,
        target_action="settings.security_policy.update",
        executed_by=operator,
        execution_ref="settings.security_policy",
    )
    response = SecurityPolicySettingsResponse(**update_security_policy_settings(request_payload))
    append_control_plane_audit_log(
        action="settings.security_policy.updated",
        user=operator,
        resource="settings.security_policy",
        details="更新主脑安全策略阈值",
    )
    return response


@router.get(
    "/agent-api",
    response_model=AgentApiSettingsResponse,
    dependencies=[Depends(require_permission("settings:read"))],
)
def get_agent_api_settings_route() -> AgentApiSettingsResponse:
    return AgentApiSettingsResponse(**get_agent_api_settings())


@router.put(
    "/agent-api",
    response_model=AgentApiSettingsResponse,
    dependencies=[Depends(require_permission("settings:agent-api:write"))],
)
def update_agent_api_settings_route(
    payload: UpdateAgentApiSettingsRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> AgentApiSettingsResponse:
    response = AgentApiSettingsResponse(**update_agent_api_settings(payload.model_dump(exclude_none=True)))
    append_control_plane_audit_log(
        action="settings.agent_api.updated",
        user=_operator_identity(current_user),
        resource="settings.agent_api",
        details="更新外部模型与 Agent API 配置",
    )
    return response


def _channel_integration_settings_response() -> ChannelIntegrationSettingsResponse:
    return ChannelIntegrationSettingsResponse(**get_channel_integration_settings())

def _update_channel_integration_settings_response(
    payload: UpdateChannelIntegrationSettingsRequest,
) -> ChannelIntegrationSettingsResponse:
    response = ChannelIntegrationSettingsResponse(
        **update_channel_integration_settings(payload.model_dump(exclude_none=True))
    )
    dingtalk_stream_service.reconcile_runtime()
    return response


@router.get(
    "/channel-integrations",
    response_model=ChannelIntegrationSettingsResponse,
    dependencies=[Depends(require_permission("settings:read"))],
)
@router.get(
    "/channel-integration",
    response_model=ChannelIntegrationSettingsResponse,
    dependencies=[Depends(require_permission("settings:read"))],
)
def get_channel_integration_settings_route() -> ChannelIntegrationSettingsResponse:
    return _channel_integration_settings_response()


@router.put(
    "/channel-integrations",
    response_model=ChannelIntegrationSettingsResponse,
    dependencies=[Depends(require_permission("settings:channel-integrations:write"))],
)
@router.put(
    "/channel-integration",
    response_model=ChannelIntegrationSettingsResponse,
    dependencies=[Depends(require_permission("settings:channel-integrations:write"))],
)
def update_channel_integration_settings_route(
    payload: UpdateChannelIntegrationSettingsRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> ChannelIntegrationSettingsResponse:
    response = _update_channel_integration_settings_response(payload)
    append_control_plane_audit_log(
        action="settings.channel_integrations.updated",
        user=_operator_identity(current_user),
        resource="settings.channel_integrations",
        details="更新渠道接入与 webhook 密钥配置",
    )
    return response
