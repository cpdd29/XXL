from fastapi import APIRouter

from app.modules.executor_config.api import executors


router = APIRouter()
router.include_router(executors.router, prefix="/executors", tags=["executors"])

