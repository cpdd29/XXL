from fastapi import APIRouter, Depends, Query

from app.core.authz import require_authenticated_user, require_permission
from app.schemas.collaboration import CollaborationOverviewResponse
from app.services.collaboration_service import get_collaboration_overview

router = APIRouter(dependencies=[Depends(require_authenticated_user)])


@router.get(
    "/overview",
    response_model=CollaborationOverviewResponse,
    dependencies=[Depends(require_permission("collaboration:read"))],
)
def get_collaboration_overview_route(
    task_id: str | None = Query(default=None, alias="taskId")
) -> CollaborationOverviewResponse:
    return CollaborationOverviewResponse(**get_collaboration_overview(task_id=task_id))
