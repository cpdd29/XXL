from fastapi import APIRouter

from app.platform.auth.api import auth


router = APIRouter()
router.include_router(auth.router, prefix="/auth", tags=["auth"])
