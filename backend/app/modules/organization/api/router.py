from fastapi import APIRouter

from app.modules.organization.api import memory, profiles, users


router = APIRouter()
router.include_router(memory.router, prefix="/memory", tags=["memory"])
router.include_router(profiles.router, prefix="/profiles", tags=["profiles"])
router.include_router(users.router, prefix="/users", tags=["users"])
