from fastapi import APIRouter

from app.platform.approval.api import approvals


router = APIRouter()
router.include_router(approvals.router, prefix="/approvals", tags=["approvals"])
