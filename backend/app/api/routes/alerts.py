from typing import Any

from fastapi import APIRouter, Depends, Header, Query

from app.core.authz import require_authenticated_user, require_permission
from app.schemas.alerts import (
    AlertCenterActionRequest,
    AlertCenterActionResponse,
    AlertCenterItem,
    AlertCenterListResponse,
    AlertDeliveryPreviewResponse,
    AlertEscalationPolicyRequest,
    AlertEscalationPolicyResponse,
    AlertManualSendRequest,
    AlertManualSendResponse,
    AlertSubscriptionActionResponse,
    AlertSubscriptionCreateRequest,
    AlertSubscriptionItem,
    AlertSubscriptionListResponse,
    AlertSubscriptionUpdateRequest,
)
from app.services.alert_center_service import (
    create_alert_subscription,
    get_alert,
    get_alert_escalation_policy,
    list_alert_subscriptions,
    list_alerts,
    preview_alert_delivery,
    send_alert_to_matching_subscriptions,
    update_alert_status,
    update_alert_subscription,
    upsert_alert_escalation_policy,
)
from app.services.tenancy_service import resolve_scope


router = APIRouter(dependencies=[Depends(require_authenticated_user)])


def _operator_identity(current_user: dict[str, Any]) -> str:
    return (
        str(current_user.get("email") or "").strip()
        or str(current_user.get("id") or "").strip()
        or "system"
    )


@router.get(
    "",
    response_model=AlertCenterListResponse,
    dependencies=[Depends(require_permission("alerts:read"))],
)
def list_alerts_route(
    search: str | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    severity: str | None = Query(default=None),
    source: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    tenant_id: str | None = Header(default=None, alias="X-WorkBot-Tenant-Id"),
    project_id: str | None = Header(default=None, alias="X-WorkBot-Project-Id"),
    environment: str | None = Header(default=None, alias="X-WorkBot-Environment"),
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> AlertCenterListResponse:
    scope = resolve_scope(
        current_user=current_user,
        tenant_id=tenant_id,
        project_id=project_id,
        environment=environment,
    )
    return AlertCenterListResponse(
        **list_alerts(
            search=search,
            status_filter=status_value,
            severity=severity,
            source=source,
            limit=limit,
            offset=offset,
            scope=scope,
        )
    )


@router.get(
    "/subscriptions",
    response_model=AlertSubscriptionListResponse,
    dependencies=[Depends(require_permission("alerts:read"))],
)
def list_alert_subscriptions_route(
    tenant_id: str | None = Header(default=None, alias="X-WorkBot-Tenant-Id"),
    project_id: str | None = Header(default=None, alias="X-WorkBot-Project-Id"),
    environment: str | None = Header(default=None, alias="X-WorkBot-Environment"),
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> AlertSubscriptionListResponse:
    scope = resolve_scope(
        current_user=current_user,
        tenant_id=tenant_id,
        project_id=project_id,
        environment=environment,
    )
    return AlertSubscriptionListResponse(**list_alert_subscriptions(scope=scope))


@router.post(
    "/subscriptions",
    response_model=AlertSubscriptionActionResponse,
    dependencies=[Depends(require_permission("alerts:write"))],
)
def create_alert_subscription_route(
    payload: AlertSubscriptionCreateRequest,
    tenant_id: str | None = Header(default=None, alias="X-WorkBot-Tenant-Id"),
    project_id: str | None = Header(default=None, alias="X-WorkBot-Project-Id"),
    environment: str | None = Header(default=None, alias="X-WorkBot-Environment"),
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> AlertSubscriptionActionResponse:
    scope = resolve_scope(
        current_user=current_user,
        tenant_id=tenant_id,
        project_id=project_id,
        environment=environment,
    )
    return AlertSubscriptionActionResponse(
        ok=True,
        message="Alert subscription created",
        subscription=AlertSubscriptionItem(
            **create_alert_subscription(
                channel=payload.channel,
                target=payload.target,
                enabled=payload.enabled,
                severity_scope=payload.severity_scope,
                scope=scope,
            )["subscription"]
        ),
    )


@router.patch(
    "/subscriptions/{subscription_id}",
    response_model=AlertSubscriptionActionResponse,
    dependencies=[Depends(require_permission("alerts:write"))],
)
def update_alert_subscription_route(
    subscription_id: str,
    payload: AlertSubscriptionUpdateRequest,
    tenant_id: str | None = Header(default=None, alias="X-WorkBot-Tenant-Id"),
    project_id: str | None = Header(default=None, alias="X-WorkBot-Project-Id"),
    environment: str | None = Header(default=None, alias="X-WorkBot-Environment"),
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> AlertSubscriptionActionResponse:
    scope = resolve_scope(
        current_user=current_user,
        tenant_id=tenant_id,
        project_id=project_id,
        environment=environment,
    )
    return AlertSubscriptionActionResponse(
        ok=True,
        message="Alert subscription updated",
        subscription=AlertSubscriptionItem(
            **update_alert_subscription(
                subscription_id=subscription_id,
                target=payload.target,
                enabled=payload.enabled,
                severity_scope=payload.severity_scope,
                scope=scope,
            )["subscription"]
        ),
    )


@router.get(
    "/escalation-policy",
    response_model=AlertEscalationPolicyResponse,
    dependencies=[Depends(require_permission("alerts:read"))],
)
def get_alert_escalation_policy_route(
    tenant_id: str | None = Header(default=None, alias="X-WorkBot-Tenant-Id"),
    project_id: str | None = Header(default=None, alias="X-WorkBot-Project-Id"),
    environment: str | None = Header(default=None, alias="X-WorkBot-Environment"),
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> AlertEscalationPolicyResponse:
    scope = resolve_scope(
        current_user=current_user,
        tenant_id=tenant_id,
        project_id=project_id,
        environment=environment,
    )
    return AlertEscalationPolicyResponse(
        ok=True,
        message="Alert escalation policy loaded",
        policy=get_alert_escalation_policy(scope=scope),
    )


@router.put(
    "/escalation-policy",
    response_model=AlertEscalationPolicyResponse,
    dependencies=[Depends(require_permission("alerts:write"))],
)
def upsert_alert_escalation_policy_route(
    payload: AlertEscalationPolicyRequest,
    tenant_id: str | None = Header(default=None, alias="X-WorkBot-Tenant-Id"),
    project_id: str | None = Header(default=None, alias="X-WorkBot-Project-Id"),
    environment: str | None = Header(default=None, alias="X-WorkBot-Environment"),
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> AlertEscalationPolicyResponse:
    scope = resolve_scope(
        current_user=current_user,
        tenant_id=tenant_id,
        project_id=project_id,
        environment=environment,
    )
    return AlertEscalationPolicyResponse(
        **upsert_alert_escalation_policy(
            policies=payload.policies,
            scope=scope,
        )
    )


@router.get(
    "/{alert_id}/delivery-preview",
    response_model=AlertDeliveryPreviewResponse,
    dependencies=[Depends(require_permission("alerts:read"))],
)
@router.post(
    "/{alert_id}/delivery-preview",
    response_model=AlertDeliveryPreviewResponse,
    dependencies=[Depends(require_permission("alerts:read"))],
)
def preview_alert_delivery_route(
    alert_id: str,
    payload: AlertManualSendRequest | None = None,
    tenant_id: str | None = Header(default=None, alias="X-WorkBot-Tenant-Id"),
    project_id: str | None = Header(default=None, alias="X-WorkBot-Project-Id"),
    environment: str | None = Header(default=None, alias="X-WorkBot-Environment"),
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> AlertDeliveryPreviewResponse:
    request_payload = payload or AlertManualSendRequest()
    scope = resolve_scope(
        current_user=current_user,
        tenant_id=tenant_id,
        project_id=project_id,
        environment=environment,
    )
    return AlertDeliveryPreviewResponse(
        **preview_alert_delivery(
            alert_id=alert_id,
            note=request_payload.note,
            scope=scope,
        )
    )


@router.post(
    "/{alert_id}/send",
    response_model=AlertManualSendResponse,
    dependencies=[Depends(require_permission("alerts:write"))],
)
def send_alert_route(
    alert_id: str,
    payload: AlertManualSendRequest | None = None,
    tenant_id: str | None = Header(default=None, alias="X-WorkBot-Tenant-Id"),
    project_id: str | None = Header(default=None, alias="X-WorkBot-Project-Id"),
    environment: str | None = Header(default=None, alias="X-WorkBot-Environment"),
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> AlertManualSendResponse:
    request_payload = payload or AlertManualSendRequest()
    scope = resolve_scope(
        current_user=current_user,
        tenant_id=tenant_id,
        project_id=project_id,
        environment=environment,
    )
    return AlertManualSendResponse(
        **send_alert_to_matching_subscriptions(
            alert_id=alert_id,
            operator=_operator_identity(current_user),
            note=request_payload.note,
            scope=scope,
        )
    )


@router.get(
    "/{alert_id}",
    response_model=AlertCenterItem,
    dependencies=[Depends(require_permission("alerts:read"))],
)
def get_alert_route(
    alert_id: str,
    tenant_id: str | None = Header(default=None, alias="X-WorkBot-Tenant-Id"),
    project_id: str | None = Header(default=None, alias="X-WorkBot-Project-Id"),
    environment: str | None = Header(default=None, alias="X-WorkBot-Environment"),
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> AlertCenterItem:
    scope = resolve_scope(
        current_user=current_user,
        tenant_id=tenant_id,
        project_id=project_id,
        environment=environment,
    )
    return AlertCenterItem(**get_alert(alert_id, scope=scope))


@router.post(
    "/{alert_id}/ack",
    response_model=AlertCenterActionResponse,
    dependencies=[Depends(require_permission("alerts:write"))],
)
def acknowledge_alert_route(
    alert_id: str,
    payload: AlertCenterActionRequest | None = None,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> AlertCenterActionResponse:
    request_payload = payload or AlertCenterActionRequest()
    return AlertCenterActionResponse(
        ok=True,
        message="Alert acknowledged",
        alert=AlertCenterItem(
            **update_alert_status(
                alert_id,
                next_status="acknowledged",
                operator=_operator_identity(current_user),
                note=request_payload.note,
            )
        ),
    )


@router.post(
    "/{alert_id}/resolve",
    response_model=AlertCenterActionResponse,
    dependencies=[Depends(require_permission("alerts:write"))],
)
def resolve_alert_route(
    alert_id: str,
    payload: AlertCenterActionRequest | None = None,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> AlertCenterActionResponse:
    request_payload = payload or AlertCenterActionRequest()
    return AlertCenterActionResponse(
        ok=True,
        message="Alert resolved",
        alert=AlertCenterItem(
            **update_alert_status(
                alert_id,
                next_status="resolved",
                operator=_operator_identity(current_user),
                note=request_payload.note,
            )
        ),
    )


@router.post(
    "/{alert_id}/suppress",
    response_model=AlertCenterActionResponse,
    dependencies=[Depends(require_permission("alerts:write"))],
)
def suppress_alert_route(
    alert_id: str,
    payload: AlertCenterActionRequest | None = None,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> AlertCenterActionResponse:
    request_payload = payload or AlertCenterActionRequest(duration_minutes=60)
    return AlertCenterActionResponse(
        ok=True,
        message="Alert suppressed",
        alert=AlertCenterItem(
            **update_alert_status(
                alert_id,
                next_status="suppressed",
                operator=_operator_identity(current_user),
                note=request_payload.note,
                duration_minutes=request_payload.duration_minutes or 60,
            )
        ),
    )
