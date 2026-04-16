from fastapi import APIRouter, Depends

from app.core.authz import (
    build_permission_groups,
    list_permissions_for_role,
    get_role_summary,
    require_authenticated_user,
)
from app.schemas.auth import AuthSessionResponse, LoginRequest, LoginResponse, RefreshRequest
from app.services.auth_service import login, refresh

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
def login_route(payload: LoginRequest) -> LoginResponse:
    return LoginResponse(**login(payload.email, payload.password))


@router.post("/refresh", response_model=LoginResponse)
def refresh_route(payload: RefreshRequest) -> LoginResponse:
    return LoginResponse(**refresh(payload.refresh_token))


@router.get("/session", response_model=AuthSessionResponse)
def auth_session_route(
    current_user: dict = Depends(require_authenticated_user),
) -> AuthSessionResponse:
    role = str(current_user.get("role") or "")
    return AuthSessionResponse(
        user=current_user,
        role_summary=get_role_summary(role),
        permissions=list_permissions_for_role(role),
        permission_groups=build_permission_groups(role),
    )
