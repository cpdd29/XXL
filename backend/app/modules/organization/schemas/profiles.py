from pydantic import Field

from app.platform.contracts.api_model import APIModel


class ProfilePlatformAccount(APIModel):
    platform: str
    account_id: str


class ProfilePlatformAccountInput(APIModel):
    platform: str
    account_id: str


class ProfileSummary(APIModel):
    id: str = Field(description="人员画像主键，也是租户下人员的稳定标识。")
    customer_id: str | None = Field(
        default=None,
        description="业务客户编号，不等同于人员主键；通常用于服务归档、兼容映射或外部业务编号关联。",
    )
    tenant_id: str = Field(description="租户主键，用于确定人员画像所属租户。")
    tenant_name: str
    tenant_status: str = "active"
    name: str
    company_name: str | None = None
    contact_name: str | None = None
    mobile: str | None = None
    service_status: str = "active"
    source_channels: list[str] = Field(default_factory=list)
    channel_accounts: list[ProfilePlatformAccount] = Field(default_factory=list)
    platform_accounts: list[ProfilePlatformAccount] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    preferred_language: str
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    last_active_at: str = ""
    total_interactions: int = 0
    notes: str
    profile_summary: str | None = None
    preferences: list[str] = Field(default_factory=list)
    business_background: list[str] = Field(default_factory=list)
    decision_history: list[str] = Field(default_factory=list)
    last_reception_at: str | None = None
    last_updated_by: str | None = None
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
    customer_id: str | None = Field(
        default=None,
        description="业务客户编号，不等同于人员主键。",
    )
    tenant_id: str | None = None
    tenant_name: str | None = None
    name: str | None = None
    company_name: str | None = None
    contact_name: str | None = None
    mobile: str | None = None
    service_status: str | None = None
    source_channels: list[str] | None = None
    channel_accounts: list[ProfilePlatformAccountInput] | None = None
    platform_accounts: list[ProfilePlatformAccountInput] | None = None
    tags: list[str] | None = None
    notes: str | None = None
    preferred_language: str | None = None
    first_seen_at: str | None = None
    last_seen_at: str | None = None


class CreateCustomerProfileRequest(UpdateProfileRequest):
    profile_id: str | None = None


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


class ProfileTenantServiceRegistrationCodeActionResponse(APIModel):
    ok: bool
    message: str
    tenant_id: str
    registration_code: str
    status: str
    issued_at: str | None = None


class ProfileActionResponse(APIModel):
    ok: bool
    message: str
    profile: ProfileDetail


class ProfileDeleteActionResponse(APIModel):
    ok: bool
    message: str
    deleted_profile_id: str
