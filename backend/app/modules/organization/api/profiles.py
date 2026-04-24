from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.platform.auth.authz import require_authenticated_user, require_permission
from app.modules.organization.schemas.profiles import (
    CreateProfileTenantRequest,
    ProfileActionResponse,
    ProfileActivityResponse,
    ProfileDetail,
    ProfileListResponse,
    ProfileTenantActionResponse,
    ProfileTenantOptionsResponse,
    UpdateProfileRequest,
)
from app.modules.organization.application.profile_service import (
    create_profile_tenant,
    delete_profile_tenant,
    export_profiles_csv,
    get_profile,
    get_profile_activity,
    list_profile_tenants,
    list_profiles,
    update_profile,
)


router = APIRouter(dependencies=[Depends(require_authenticated_user)])


@router.get(
    "/tenants",
    response_model=ProfileTenantOptionsResponse,
    dependencies=[Depends(require_permission("users:read"))],
)
def list_profile_tenants_route(
    management: bool = Query(default=False),
    current_user: dict = Depends(require_authenticated_user),
) -> ProfileTenantOptionsResponse:
    return ProfileTenantOptionsResponse(
        **list_profile_tenants(
            current_user,
            management_view=management,
        )
    )


@router.post(
    "/tenants",
    response_model=ProfileTenantActionResponse,
    dependencies=[Depends(require_permission("users:profile:write"))],
)
def create_profile_tenant_route(
    payload: CreateProfileTenantRequest,
    current_user: dict = Depends(require_authenticated_user),
) -> ProfileTenantActionResponse:
    return ProfileTenantActionResponse(
        **create_profile_tenant(
            current_user=current_user,
            name=payload.name,
            description=payload.description,
        )
    )


@router.delete(
    "/tenants/{tenant_id}",
    response_model=ProfileTenantActionResponse,
    dependencies=[Depends(require_permission("users:profile:write"))],
)
def delete_profile_tenant_route(
    tenant_id: str,
    current_user: dict = Depends(require_authenticated_user),
) -> ProfileTenantActionResponse:
    return ProfileTenantActionResponse(
        **delete_profile_tenant(
            tenant_id,
            current_user=current_user,
        )
    )


@router.get(
    "",
    response_model=ProfileListResponse,
    dependencies=[Depends(require_permission("users:read"))],
)
def list_profiles_route(
    tenant_id: str | None = Query(default=None, alias="tenantId"),
    search: str | None = Query(default=None),
    management: bool = Query(default=False),
    current_user: dict = Depends(require_authenticated_user),
) -> ProfileListResponse:
    return ProfileListResponse(
        **list_profiles(
            current_user=current_user,
            tenant_id=tenant_id,
            search=search,
            management_view=management,
        )
    )


@router.get(
    "/export",
    dependencies=[Depends(require_permission("users:read"))],
)
def export_profiles_route(
    tenant_id: str | None = Query(default=None, alias="tenantId"),
    search: str | None = Query(default=None),
    current_user: dict = Depends(require_authenticated_user),
) -> Response:
    csv_content, filename = export_profiles_csv(
        current_user=current_user,
        tenant_id=tenant_id,
        search=search,
    )
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
    "/{profile_id}",
    response_model=ProfileDetail,
    dependencies=[Depends(require_permission("users:read"))],
)
def get_profile_route(
    profile_id: str,
    current_user: dict = Depends(require_authenticated_user),
) -> ProfileDetail:
    return ProfileDetail(**get_profile(profile_id, current_user=current_user))


@router.get(
    "/{profile_id}/activity",
    response_model=ProfileActivityResponse,
    dependencies=[Depends(require_permission("users:read"))],
)
def get_profile_activity_route(
    profile_id: str,
    current_user: dict = Depends(require_authenticated_user),
) -> ProfileActivityResponse:
    return ProfileActivityResponse(**get_profile_activity(profile_id, current_user=current_user))


@router.put(
    "/{profile_id}",
    response_model=ProfileActionResponse,
    dependencies=[Depends(require_permission("users:profile:write"))],
)
def update_profile_route(
    profile_id: str,
    payload: UpdateProfileRequest,
    current_user: dict = Depends(require_authenticated_user),
) -> ProfileActionResponse:
    return ProfileActionResponse(
        **update_profile(
            profile_id,
            current_user=current_user,
            tags=payload.tags,
            notes=payload.notes,
            preferred_language=payload.preferred_language,
        )
    )
