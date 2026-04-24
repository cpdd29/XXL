from fastapi import APIRouter

from app.modules.reception.api import messages, security, webhooks


router = APIRouter()
router.include_router(messages.router, prefix="/messages", tags=["messages"])
router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
router.include_router(security.router, prefix="/security", tags=["security"])
