from functools import lru_cache

from app.services.auth_service import AuthService
from app.services.workbot_service import WorkBotService


@lru_cache
def get_workbot_service() -> WorkBotService:
    return WorkBotService()


@lru_cache
def get_auth_service() -> AuthService:
    return AuthService()
