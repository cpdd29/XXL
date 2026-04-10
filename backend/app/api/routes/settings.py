from fastapi import APIRouter, Depends

from app.core.authz import require_authenticated_user, require_permission
from app.schemas.settings import (
    AgentApiSettingsResponse,
    ChannelIntegrationSettingsResponse,
    GeneralSettingsResponse,
    SecurityPolicySettingsResponse,
    UpdateAgentApiSettingsRequest,
    UpdateChannelIntegrationSettingsRequest,
    UpdateGeneralSettingsRequest,
    UpdateSecurityPolicySettingsRequest,
)
from app.services.settings_service import (
    get_agent_api_settings,
    get_channel_integration_settings,
    get_general_settings,
    get_security_policy_settings,
    update_agent_api_settings,
    update_channel_integration_settings,
    update_general_settings,
    update_security_policy_settings,
)
from app.services.dingtalk_stream_service import dingtalk_stream_service


router = APIRouter(dependencies=[Depends(require_authenticated_user)])


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
    dependencies=[Depends(require_permission("settings:write"))],
)
def update_general_settings_route(
    payload: UpdateGeneralSettingsRequest,
) -> GeneralSettingsResponse:
    return GeneralSettingsResponse(**update_general_settings(payload.model_dump(exclude_none=True)))


@router.get(
    "/security-policy",
    response_model=SecurityPolicySettingsResponse,
    dependencies=[Depends(require_permission("settings:read"))],
)
def get_security_policy_settings_route() -> SecurityPolicySettingsResponse:
    return SecurityPolicySettingsResponse(**get_security_policy_settings())


@router.put(
    "/security-policy",
    response_model=SecurityPolicySettingsResponse,
    dependencies=[Depends(require_permission("settings:write"))],
)
def update_security_policy_settings_route(
    payload: UpdateSecurityPolicySettingsRequest,
) -> SecurityPolicySettingsResponse:
    return SecurityPolicySettingsResponse(
        **update_security_policy_settings(payload.model_dump(exclude_none=True))
    )


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
    dependencies=[Depends(require_permission("settings:write"))],
)
def update_agent_api_settings_route(
    payload: UpdateAgentApiSettingsRequest,
) -> AgentApiSettingsResponse:
    return AgentApiSettingsResponse(**update_agent_api_settings(payload.model_dump(exclude_none=True)))


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
    dependencies=[Depends(require_permission("settings:write"))],
)
@router.put(
    "/channel-integration",
    response_model=ChannelIntegrationSettingsResponse,
    dependencies=[Depends(require_permission("settings:write"))],
)
def update_channel_integration_settings_route(
    payload: UpdateChannelIntegrationSettingsRequest,
) -> ChannelIntegrationSettingsResponse:
    return _update_channel_integration_settings_response(payload)
