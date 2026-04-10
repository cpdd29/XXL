from fastapi import APIRouter

from app.schemas.auth import LoginRequest, LoginResponse, RefreshRequest
from app.services.auth_service import login, refresh

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
def login_route(payload: LoginRequest) -> LoginResponse:
    return LoginResponse(**login(payload.email, payload.password))


@router.post("/refresh", response_model=LoginResponse)
def refresh_route(payload: RefreshRequest) -> LoginResponse:
    return LoginResponse(**refresh(payload.refresh_token))
