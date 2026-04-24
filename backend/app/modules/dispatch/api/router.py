from fastapi import APIRouter

from app.modules.dispatch.api import tasks


router = APIRouter()
router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
