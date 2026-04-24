from fastapi import APIRouter

from app.modules.agent_config.api.router import router as agent_config_router
from app.modules.dispatch.api.router import router as dispatch_router
from app.modules.organization.api.router import router as organization_router
from app.modules.reception.api.router import router as reception_router
from app.platform.approval.api.router import router as approval_router
from app.platform.audit.api.router import router as audit_router
from app.platform.auth.api.router import router as auth_router
from app.platform.config.api.router import router as config_router
from app.platform.observability.api.router import router as observability_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="", tags=["auth"])
api_router.include_router(observability_router, prefix="", tags=["observability"])
api_router.include_router(approval_router, prefix="", tags=["approvals"])
api_router.include_router(audit_router, prefix="", tags=["events"])
api_router.include_router(dispatch_router, prefix="", tags=["tasks"])
api_router.include_router(agent_config_router, prefix="", tags=["agent-config"])
api_router.include_router(organization_router, prefix="", tags=["organization"])
api_router.include_router(config_router, prefix="", tags=["settings"])
api_router.include_router(reception_router, prefix="", tags=["reception"])
