from pydantic import EmailStr

from app.schemas.base import APIModel


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


class LoginResponse(APIModel):
    access_token: str
    refresh_token: str
    expires_in: int
    user: AuthUser
