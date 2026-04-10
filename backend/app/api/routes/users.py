from datetime import UTC, datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.core.authz import require_authenticated_user, require_permission
from app.schemas.users import (
    BindUserPlatformAccountRequest,
    UnbindUserPlatformAccountRequest,
    UpdateUserProfileRequest,
    UpdateUserRoleRequest,
    UserActionResponse,
    UserActivityResponse,
    UserListResponse,
    UserProfile,
)
from app.services.user_service import (
    bind_user_platform_account,
    block_user,
    export_users_csv,
    get_user_activity,
    get_user_profile,
    list_users,
    unbind_user_platform_account,
    update_user_profile,
    update_user_role,
)

router = APIRouter(dependencies=[Depends(require_authenticated_user)])


@router.get(
    "",
    response_model=UserListResponse,
    dependencies=[Depends(require_permission("users:read"))],
)
def list_users_route(
    search: str | None = Query(default=None),
    role: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> UserListResponse:
    return UserListResponse(**list_users(search=search, role_filter=role, status_filter=status))


@router.get(
    "/export",
    dependencies=[Depends(require_permission("users:read"))],
)
def export_users_route(
    search: str | None = Query(default=None),
    role: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> Response:
    csv_content = export_users_csv(search=search, role_filter=role, status_filter=status)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    filename = f"workbot-users-{timestamp}.csv"
    quoted_filename = quote(filename)
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f"attachment; filename={filename}; filename*=UTF-8''{quoted_filename}"
            )
        },
    )


@router.get(
    "/{user_id}/profile",
    response_model=UserProfile,
    dependencies=[Depends(require_permission("users:read"))],
)
def get_user_profile_route(user_id: str) -> UserProfile:
    return UserProfile(**get_user_profile(user_id))


@router.get(
    "/{user_id}/activity",
    response_model=UserActivityResponse,
    dependencies=[Depends(require_permission("users:read"))],
)
def get_user_activity_route(user_id: str) -> UserActivityResponse:
    return UserActivityResponse(**get_user_activity(user_id))


@router.put(
    "/{user_id}/profile",
    response_model=UserActionResponse,
    dependencies=[Depends(require_permission("users:write"))],
)
def update_user_profile_route(
    user_id: str,
    payload: UpdateUserProfileRequest,
) -> UserActionResponse:
    return UserActionResponse(
        **update_user_profile(
            user_id,
            tags=payload.tags,
            notes=payload.notes,
            preferred_language=payload.preferred_language,
        )
    )


@router.post(
    "/{user_id}/platform-accounts/bind",
    response_model=UserActionResponse,
    dependencies=[Depends(require_permission("users:write"))],
)
def bind_user_platform_account_route(
    user_id: str,
    payload: BindUserPlatformAccountRequest,
) -> UserActionResponse:
    return UserActionResponse(
        **bind_user_platform_account(
            user_id,
            platform=payload.platform,
            account_id=payload.account_id,
            confidence=payload.confidence,
            source=payload.source,
        )
    )


@router.post(
    "/{user_id}/platform-accounts/unbind",
    response_model=UserActionResponse,
    dependencies=[Depends(require_permission("users:write"))],
)
def unbind_user_platform_account_route(
    user_id: str,
    payload: UnbindUserPlatformAccountRequest,
) -> UserActionResponse:
    return UserActionResponse(
        **unbind_user_platform_account(
            user_id,
            platform=payload.platform,
            account_id=payload.account_id,
        )
    )


@router.put(
    "/{user_id}/role",
    response_model=UserActionResponse,
    dependencies=[Depends(require_permission("users:write"))],
)
def update_user_role_route(user_id: str, payload: UpdateUserRoleRequest) -> UserActionResponse:
    return UserActionResponse(**update_user_role(user_id, payload.role))


@router.post(
    "/{user_id}/block",
    response_model=UserActionResponse,
    dependencies=[Depends(require_permission("users:block"))],
)
def block_user_route(user_id: str) -> UserActionResponse:
    return UserActionResponse(**block_user(user_id))
