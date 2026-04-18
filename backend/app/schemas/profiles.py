from pydantic import Field

from app.schemas.base import APIModel


class ProfilePlatformAccount(APIModel):
    platform: str
    account_id: str


class ProfileSummary(APIModel):
    id: str
    tenant_id: str
    tenant_name: str
    tenant_status: str = "active"
    name: str
    source_channels: list[str] = Field(default_factory=list)
    platform_accounts: list[ProfilePlatformAccount] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    preferred_language: str
    last_active_at: str = ""
    total_interactions: int = 0
    notes: str
    interaction_summary: str = ""


class ProfileDetail(ProfileSummary):
    identity_mapping_status: str = "unmapped"
    identity_mapping_source: str = "unknown"
    identity_mapping_confidence: float = 0.0
    last_identity_sync_at: str | None = None


class ProfileListResponse(APIModel):
    items: list[ProfileSummary]
    total: int
    applied_tenant_id: str | None = None
    can_view_all_tenants: bool = False


class ProfileActivity(APIModel):
    id: str
    timestamp: str
    type: str
    title: str
    description: str
    source: str


class ProfileActivityResponse(APIModel):
    items: list[ProfileActivity]
    total: int


class UpdateProfileRequest(APIModel):
    tags: list[str] = Field(default_factory=list)
    notes: str = ""
    preferred_language: str


class ProfileTenantOption(APIModel):
    id: str
    name: str
    status: str
    profile_count: int
    description: str


class ProfileTenantOptionsResponse(APIModel):
    items: list[ProfileTenantOption]
    total: int
    can_view_all_tenants: bool = False
    default_tenant_id: str | None = None


class CreateProfileTenantRequest(APIModel):
    name: str
    description: str = ""


class ProfileTenantActionResponse(APIModel):
    ok: bool
    message: str
    tenant: ProfileTenantOption | None = None
    deleted_tenant_id: str | None = None


class ProfileActionResponse(APIModel):
    ok: bool
    message: str
    profile: ProfileDetail
