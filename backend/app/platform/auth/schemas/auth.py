from pydantic import EmailStr

from app.platform.contracts.api_model import APIModel


class LoginRequest(APIModel):
    email: EmailStr
    password: str


class RefreshRequest(APIModel):
    refresh_token: str


class AuthUser(APIModel):
    id: str
    name: str
    email: EmailStr
    role: str


class AuthRoleSummary(APIModel):
    key: str
    label: str
    tier: str
    description: str


class AuthPermissionGroup(APIModel):
    key: str
    label: str
    permissions: list[str]


class LoginResponse(APIModel):
    access_token: str
    refresh_token: str
    expires_in: int
    user: AuthUser


class AuthSessionResponse(APIModel):
    user: AuthUser
    role_summary: AuthRoleSummary
    permissions: list[str]
    permission_groups: list[AuthPermissionGroup]
