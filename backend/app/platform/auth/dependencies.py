from functools import lru_cache

from app.platform.auth.auth_service import AuthService


@lru_cache
def get_auth_service() -> AuthService:
    return AuthService()
