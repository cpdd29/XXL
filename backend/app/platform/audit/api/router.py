from fastapi import APIRouter

from app.platform.audit.api import events


router = APIRouter()
router.include_router(events.router, prefix="/events", tags=["events"])
