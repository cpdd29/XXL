from fastapi import APIRouter

from app.modules.agent_config.api import agents, external_connections, tool_sources, tools


router = APIRouter()
router.include_router(agents.router, prefix="/agents", tags=["agents"])
router.include_router(tools.router, prefix="/tools", tags=["tools"])
router.include_router(tool_sources.router, prefix="/tool-sources", tags=["tool-sources"])
router.include_router(
    external_connections.router,
    prefix="/external-connections",
    tags=["external-connections"],
)
