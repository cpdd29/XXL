from fastapi import APIRouter

from app.platform.config.api import settings


router = APIRouter()
router.include_router(settings.router, prefix="/settings", tags=["settings"])
