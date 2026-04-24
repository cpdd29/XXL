from typing import Literal

from pydantic import Field

from app.platform.contracts.api_model import APIModel


class User(APIModel):
    id: str
    name: str
    email: str
    role: str
    status: str
    last_login: str
    total_interactions: int
    created_at: str


class UserListResponse(APIModel):
    items: list[User]
    total: int


class UserPlatformAccount(APIModel):
    platform: str
    account_id: str


class UserProfile(APIModel):
    id: str
    name: str
    email: str
    role: str
    status: str
    last_login: str
    total_interactions: int
    created_at: str
    tags: list[str] = Field(default_factory=list)
    notes: str
    preferred_language: str
    source_channels: list[str] = Field(default_factory=list)
    platform_accounts: list[UserPlatformAccount] = Field(default_factory=list)
    identity_mapping_status: str = "unmapped"
    identity_mapping_source: str = "unknown"
    identity_mapping_confidence: float = 0.0
    last_identity_sync_at: str | None = None


class UserActivity(APIModel):
    id: str
    timestamp: str
    type: str
    title: str
    description: str
    source: str


class UserActivityResponse(APIModel):
    items: list[UserActivity]
    total: int


class UpdateUserRoleRequest(APIModel):
    role: Literal["admin", "operator", "viewer", "external", "power_user", "user", "blocked"]


class UpdateUserProfileRequest(APIModel):
    tags: list[str] = Field(default_factory=list)
    notes: str = ""
    preferred_language: str


class BindUserPlatformAccountRequest(APIModel):
    platform: str
    account_id: str
    confidence: float | None = None
    source: str | None = None


class UnbindUserPlatformAccountRequest(APIModel):
    platform: str
    account_id: str


class UserActionResponse(APIModel):
    ok: bool
    message: str
    user: User | UserProfile
