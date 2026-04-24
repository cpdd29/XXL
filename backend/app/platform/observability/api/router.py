from fastapi import APIRouter

from app.platform.observability.api import alerts, dashboard


router = APIRouter()
router.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
