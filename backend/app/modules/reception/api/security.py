from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.modules.agent_config.schemas.agents import Agent
from app.modules.reception.schemas.security import (
    CreateSecurityAlertSubscriptionRequest,
    CreateSecurityIncidentReviewRequest,
    CreateSecurityPenaltyRequest,
    CreateSecurityRuleRequest,
    ReleaseSecurityPenaltyRequest,
    RollbackSecurityRuleRequest,
    SecurityAlertSubscriptionActionResponse,
    SecurityAlertSubscriptionsResponse,
    SecurityPenaltyActionResponse,
    SecurityPenaltyHistoryResponse,
    SecurityPenaltiesResponse,
    SecurityIncidentReviewActionResponse,
    SecurityIncidentReviewsResponse,
    SecurityReportExportResponse,
    SecurityReportResponse,
    SecurityRuleActionResponse,
    SecurityRuleHitDetailsResponse,
    SecurityRuleVersionHistoryResponse,
    SecurityRule,
    SecurityRulesResponse,
    SecurityRiskProfilesResponse,
    SecurityTrendResponse,
    UpdateSecurityAlertSubscriptionRequest,
    UpdateSecurityRuleRequest,
)
from app.platform.approval.schemas.approvals import ApprovalActionResponse, ApprovalItem
from app.platform.auth.authz import require_authenticated_user, require_permission
from app.platform.approval.approval_service import (
    create_bound_approval,
    require_approved_execution,
)
from app.modules.reception.security_monitor.security_service import (
    create_manual_security_penalty,
    create_security_alert_subscription,
    create_security_incident_review,
    create_security_rule,
    export_security_report,
    get_security_guardian,
    get_security_report,
    get_security_rule,
    get_security_rule_hit_details,
    get_security_risk_trends,
    list_active_security_penalties,
    list_security_incident_reviews,
    list_security_alert_subscriptions,
    list_security_penalty_history,
    list_security_rules,
    list_security_rule_versions,
    list_security_channel_risk_profiles,
    list_security_user_risk_profiles,
    release_active_security_penalty,
    rollback_security_rule,
    update_security_alert_subscription,
    update_security_rule,
)

router = APIRouter(dependencies=[Depends(require_authenticated_user)])


@router.get(
    "/guardian",
    response_model=Agent,
    dependencies=[Depends(require_permission("security:read"))],
)
def get_security_guardian_route() -> Agent:
    return Agent(**get_security_guardian())


@router.get(
    "/rules",
    response_model=SecurityRulesResponse,
    dependencies=[Depends(require_permission("security:read"))],
)
def list_security_rules_route() -> SecurityRulesResponse:
    return SecurityRulesResponse(**list_security_rules())


@router.get(
    "/report",
    response_model=SecurityReportResponse,
    dependencies=[Depends(require_permission("security:read"))],
)
def get_security_report_route(window_hours: int = 24) -> SecurityReportResponse:
    return SecurityReportResponse(**get_security_report(window_hours=window_hours))


@router.get(
    "/incidents/reviews",
    response_model=SecurityIncidentReviewsResponse,
    dependencies=[Depends(require_permission("security:read"))],
)
def list_security_incident_reviews_route(
    incident_id: str | None = None,
) -> SecurityIncidentReviewsResponse:
    return SecurityIncidentReviewsResponse(**list_security_incident_reviews(incident_id=incident_id))


@router.post(
    "/incidents/{incident_id}/review",
    response_model=SecurityIncidentReviewActionResponse,
    dependencies=[Depends(require_permission("security:incidents:review"))],
)
def create_security_incident_review_route(
    incident_id: str,
    payload: CreateSecurityIncidentReviewRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> SecurityIncidentReviewActionResponse:
    reviewer = (
        str(current_user.get("email") or "").strip()
        or str(current_user.get("id") or "").strip()
        or "system"
    )
    return SecurityIncidentReviewActionResponse(
        **create_security_incident_review(
            incident_id=incident_id,
            action=payload.action,
            note=payload.note,
            reviewer=reviewer,
        )
    )


@router.get(
    "/penalties",
    response_model=SecurityPenaltiesResponse,
    dependencies=[Depends(require_permission("security:penalties:read"))],
)
def list_security_penalties_route() -> SecurityPenaltiesResponse:
    return SecurityPenaltiesResponse(**list_active_security_penalties())


@router.get(
    "/penalties/history",
    response_model=SecurityPenaltyHistoryResponse,
    dependencies=[Depends(require_permission("security:read"))],
)
def list_security_penalty_history_route(
    user_key: str | None = None,
) -> SecurityPenaltyHistoryResponse:
    return SecurityPenaltyHistoryResponse(**list_security_penalty_history(user_key=user_key))


@router.post(
    "/penalties/manual",
    response_model=SecurityPenaltyActionResponse | ApprovalActionResponse,
    dependencies=[Depends(require_permission("security:penalties:manual:create"))],
)
def create_manual_security_penalty_route(
    payload: CreateSecurityPenaltyRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> SecurityPenaltyActionResponse:
    operator_user = (
        str(current_user.get("email") or "").strip()
        or str(current_user.get("id") or "").strip()
        or "system"
    )
    request_payload = payload.model_dump(
        exclude_none=True,
        exclude={"approval_id", "approval_reason", "approval_note"},
    )
    if not payload.approval_id:
        approval = create_bound_approval(
            request_type="security_release",
            title=f"人工创建安全处罚 {payload.user_key}",
            resource=f"security.penalty.manual.{payload.user_key}",
            requested_by=operator_user,
            request_payload=request_payload,
            target_action="security.penalty.manual.create",
            reason=payload.approval_reason,
            note=payload.approval_note or payload.note,
        )
        return JSONResponse(
            status_code=202,
            content=ApprovalActionResponse(
                ok=True,
                message="Approval required before creating manual security penalty",
                approval=ApprovalItem(**approval),
                approval_required=True,
            ).model_dump(by_alias=True, exclude_none=True),
        )
    require_approved_execution(
        payload.approval_id,
        request_type="security_release",
        resource=f"security.penalty.manual.{payload.user_key}",
        request_payload=request_payload,
        target_action="security.penalty.manual.create",
        executed_by=operator_user,
        execution_ref=f"security.penalty.manual.{payload.user_key}",
    )
    return SecurityPenaltyActionResponse(
        **create_manual_security_penalty(
            user_key=payload.user_key,
            level=payload.level,
            detail=payload.detail,
            duration_seconds=payload.duration_seconds,
            status_code=payload.status_code,
            note=payload.note,
            operator_user=operator_user,
        )
    )


@router.post(
    "/rules",
    response_model=SecurityRuleActionResponse,
    dependencies=[Depends(require_permission("security:rules:write"))],
)
def create_security_rule_route(
    payload: CreateSecurityRuleRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> SecurityRuleActionResponse:
    operator_user = (
        str(current_user.get("email") or "").strip()
        or str(current_user.get("id") or "").strip()
        or "system"
    )
    return SecurityRuleActionResponse(
        **create_security_rule(
            name=payload.name,
            description=payload.description,
            rule_type=payload.type,
            enabled=payload.enabled,
            operator_user=operator_user,
        )
    )


@router.get(
    "/rules/{rule_id}",
    response_model=SecurityRule,
    dependencies=[Depends(require_permission("security:read"))],
)
def get_security_rule_route(rule_id: str) -> SecurityRule:
    return SecurityRule(**get_security_rule(rule_id))


@router.put(
    "/rules/{rule_id}",
    response_model=SecurityRuleActionResponse,
    dependencies=[Depends(require_permission("security:rules:write"))],
)
def update_security_rule_route(
    rule_id: str,
    payload: UpdateSecurityRuleRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> SecurityRuleActionResponse:
    operator_user = (
        str(current_user.get("email") or "").strip()
        or str(current_user.get("id") or "").strip()
        or "system"
    )
    return SecurityRuleActionResponse(
        **update_security_rule(
            rule_id,
            payload.enabled,
            name=payload.name,
            description=payload.description,
            rule_type=payload.type,
            operator_user=operator_user,
        )
    )


@router.get(
    "/rules/{rule_id}/hits",
    response_model=SecurityRuleHitDetailsResponse,
    dependencies=[Depends(require_permission("security:read"))],
)
def get_security_rule_hits_route(rule_id: str) -> SecurityRuleHitDetailsResponse:
    return SecurityRuleHitDetailsResponse(**get_security_rule_hit_details(rule_id))


@router.get(
    "/rules/{rule_id}/versions",
    response_model=SecurityRuleVersionHistoryResponse,
    dependencies=[Depends(require_permission("security:read"))],
)
def list_security_rule_versions_route(rule_id: str) -> SecurityRuleVersionHistoryResponse:
    return SecurityRuleVersionHistoryResponse(**list_security_rule_versions(rule_id))


@router.post(
    "/rules/{rule_id}/rollback",
    response_model=SecurityRuleActionResponse,
    dependencies=[Depends(require_permission("security:rules:write"))],
)
def rollback_security_rule_route(
    rule_id: str,
    payload: RollbackSecurityRuleRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> SecurityRuleActionResponse:
    operator_user = (
        str(current_user.get("email") or "").strip()
        or str(current_user.get("id") or "").strip()
        or "system"
    )
    return SecurityRuleActionResponse(
        **rollback_security_rule(
            rule_id=rule_id,
            version_id=payload.version_id,
            operator_user=operator_user,
        )
    )


@router.post(
    "/penalties/{user_key}/release",
    response_model=SecurityPenaltyActionResponse | ApprovalActionResponse,
    dependencies=[Depends(require_permission("security:penalties:release"))],
)
def release_security_penalty_route(
    user_key: str,
    payload: ReleaseSecurityPenaltyRequest | None = None,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> SecurityPenaltyActionResponse:
    operator_user = (
        str(current_user.get("email") or "").strip()
        or str(current_user.get("id") or "").strip()
        or "system"
    )
    request_payload = {"user_key": user_key}
    request = payload or ReleaseSecurityPenaltyRequest()
    if not request.approval_id:
        approval = create_bound_approval(
            request_type="security_release",
            title=f"解除安全处罚 {user_key}",
            resource=f"security.penalty.release.{user_key}",
            requested_by=operator_user,
            request_payload=request_payload,
            target_action="security.penalty.release",
            reason=request.approval_reason,
            note=request.approval_note,
        )
        return JSONResponse(
            status_code=202,
            content=ApprovalActionResponse(
                ok=True,
                message="Approval required before releasing security penalty",
                approval=ApprovalItem(**approval),
                approval_required=True,
            ).model_dump(by_alias=True, exclude_none=True),
        )
    require_approved_execution(
        request.approval_id,
        request_type="security_release",
        resource=f"security.penalty.release.{user_key}",
        request_payload=request_payload,
        target_action="security.penalty.release",
        executed_by=operator_user,
        execution_ref=f"security.penalty.release.{user_key}",
    )
    return SecurityPenaltyActionResponse(
        **release_active_security_penalty(user_key, operator_user=operator_user)
    )


@router.get(
    "/profiles/users",
    response_model=SecurityRiskProfilesResponse,
    dependencies=[Depends(require_permission("security:read"))],
)
def list_security_user_profiles_route() -> SecurityRiskProfilesResponse:
    return SecurityRiskProfilesResponse(**list_security_user_risk_profiles())


@router.get(
    "/profiles/channels",
    response_model=SecurityRiskProfilesResponse,
    dependencies=[Depends(require_permission("security:read"))],
)
def list_security_channel_profiles_route() -> SecurityRiskProfilesResponse:
    return SecurityRiskProfilesResponse(**list_security_channel_risk_profiles())


@router.get(
    "/trends",
    response_model=SecurityTrendResponse,
    dependencies=[Depends(require_permission("security:read"))],
)
def get_security_trends_route(days: int = 7) -> SecurityTrendResponse:
    return SecurityTrendResponse(**get_security_risk_trends(days=days))


@router.get(
    "/subscriptions",
    response_model=SecurityAlertSubscriptionsResponse,
    dependencies=[Depends(require_permission("security:read"))],
)
def list_security_alert_subscriptions_route() -> SecurityAlertSubscriptionsResponse:
    return SecurityAlertSubscriptionsResponse(**list_security_alert_subscriptions())


@router.post(
    "/subscriptions",
    response_model=SecurityAlertSubscriptionActionResponse,
    dependencies=[Depends(require_permission("security:subscriptions:write"))],
)
def create_security_alert_subscription_route(
    payload: CreateSecurityAlertSubscriptionRequest,
) -> SecurityAlertSubscriptionActionResponse:
    return SecurityAlertSubscriptionActionResponse(
        **create_security_alert_subscription(
            channel=payload.channel,
            target=payload.target,
            enabled=payload.enabled,
            severity_scope=payload.severity_scope,
        )
    )


@router.put(
    "/subscriptions/{subscription_id}",
    response_model=SecurityAlertSubscriptionActionResponse,
    dependencies=[Depends(require_permission("security:subscriptions:write"))],
)
def update_security_alert_subscription_route(
    subscription_id: str,
    payload: UpdateSecurityAlertSubscriptionRequest,
) -> SecurityAlertSubscriptionActionResponse:
    return SecurityAlertSubscriptionActionResponse(
        **update_security_alert_subscription(
            subscription_id=subscription_id,
            target=payload.target,
            enabled=payload.enabled,
            severity_scope=payload.severity_scope,
        )
    )


@router.get(
    "/exports/report",
    response_model=SecurityReportExportResponse,
    dependencies=[Depends(require_permission("security:read"))],
)
def export_security_report_route(period: str = "daily") -> SecurityReportExportResponse:
    return SecurityReportExportResponse(**export_security_report(period=period))
