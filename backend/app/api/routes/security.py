from typing import Any

from fastapi import APIRouter, Depends

from app.core.authz import require_authenticated_user, require_permission
from app.schemas.security import (
    SecurityPenaltyActionResponse,
    SecurityPenaltiesResponse,
    SecurityReportResponse,
    SecurityRuleActionResponse,
    SecurityRulesResponse,
    UpdateSecurityRuleRequest,
)
from app.services.security_service import (
    get_security_report,
    list_active_security_penalties,
    list_security_rules,
    release_active_security_penalty,
    update_security_rule,
)

router = APIRouter(dependencies=[Depends(require_authenticated_user)])


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
    "/penalties",
    response_model=SecurityPenaltiesResponse,
    dependencies=[Depends(require_permission("security:penalties:read"))],
)
def list_security_penalties_route() -> SecurityPenaltiesResponse:
    return SecurityPenaltiesResponse(**list_active_security_penalties())


@router.put(
    "/rules/{rule_id}",
    response_model=SecurityRuleActionResponse,
    dependencies=[Depends(require_permission("security:rules:write"))],
)
def update_security_rule_route(
    rule_id: str, payload: UpdateSecurityRuleRequest
) -> SecurityRuleActionResponse:
    return SecurityRuleActionResponse(**update_security_rule(rule_id, payload.enabled))


@router.post(
    "/penalties/{user_key}/release",
    response_model=SecurityPenaltyActionResponse,
    dependencies=[Depends(require_permission("security:penalties:release"))],
)
def release_security_penalty_route(
    user_key: str,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> SecurityPenaltyActionResponse:
    operator_user = (
        str(current_user.get("email") or "").strip()
        or str(current_user.get("id") or "").strip()
        or "system"
    )
    return SecurityPenaltyActionResponse(
        **release_active_security_penalty(user_key, operator_user=operator_user)
    )
