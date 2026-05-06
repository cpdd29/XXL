from fastapi import APIRouter

from app.modules.reception.api import channel_binding, customer_access, intake, messages, security, shared_files, webhooks


router = APIRouter()
router.include_router(customer_access.router, prefix="/customer-access", tags=["customer-access"])
router.include_router(channel_binding.router, prefix="/channel-bind", tags=["channel-bind"])
router.include_router(intake.router, prefix="/intake", tags=["intake"])
router.include_router(messages.router, prefix="/messages", tags=["messages"])
router.include_router(shared_files.router, prefix="/shared-files", tags=["shared-files"])
router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
router.include_router(security.router, prefix="/security", tags=["security"])
