from fastapi import APIRouter

from app.modules.knowledge.api import knowledge


router = APIRouter()
router.include_router(knowledge.router, prefix="/knowledge", tags=["knowledge"])
