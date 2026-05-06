from __future__ import annotations

from fastapi import APIRouter, Depends

from app.modules.reception.customer_access import customer_access_service
from app.modules.reception.customer_access.schemas import (
    CustomerAccessSettingsActionResponse,
    CustomerAccessSettingsResponse,
    UpdateCustomerAccessSettingsRequest,
)
from app.platform.auth.authz import require_authenticated_user, require_permission


router = APIRouter(dependencies=[Depends(require_authenticated_user)])


@router.get(
    "/settings",
    response_model=CustomerAccessSettingsResponse,
    dependencies=[Depends(require_permission("settings:read"))],
)
def get_customer_access_settings_route() -> CustomerAccessSettingsResponse:
    return CustomerAccessSettingsResponse(settings=customer_access_service.get_settings())


@router.put(
    "/settings",
    response_model=CustomerAccessSettingsActionResponse,
    dependencies=[Depends(require_permission("settings:channel-integrations:write"))],
)
def update_customer_access_settings_route(
    payload: UpdateCustomerAccessSettingsRequest,
) -> CustomerAccessSettingsActionResponse:
    settings = customer_access_service.update_settings(payload)
    return CustomerAccessSettingsActionResponse(
        ok=True,
        message="客户准入配置已更新",
        settings=settings,
    )
