from fastapi import APIRouter

from app.api.routes import (
    agents,
    auth,
    collaboration,
    dashboard,
    messages,
    memory,
    settings,
    security,
    tasks,
    tools,
    tool_sources,
    users,
    webhooks,
    workflows,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(collaboration.router, prefix="/collaboration", tags=["collaboration"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(workflows.router, prefix="/workflows", tags=["workflows"])
api_router.include_router(security.router, prefix="/security", tags=["security"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(messages.router, prefix="/messages", tags=["messages"])
api_router.include_router(memory.router, prefix="/memory", tags=["memory"])
api_router.include_router(tools.router, prefix="/tools", tags=["tools"])
api_router.include_router(tool_sources.router, prefix="/tool-sources", tags=["tool-sources"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
