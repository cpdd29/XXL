from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.platform.contracts.api_model import APIModel


CustomerAccessStatus = Literal["bound", "pending_verification", "rejected"]
CustomerAccessVerificationMode = Literal["relaxed", "strict"]


class CustomerAccessTemplateField(APIModel):
    key: str
    label: str
    required: bool = True


class CustomerAccessTenantPolicy(APIModel):
    tenant_id: str
    tenant_name: str | None = None
    verification_mode: CustomerAccessVerificationMode = "relaxed"
    service_codes: list[str] = Field(default_factory=list)
    enabled: bool = True


class CustomerAccessSettings(APIModel):
    template_intro: str
    template_fields: list[CustomerAccessTemplateField] = Field(default_factory=list)
    tenant_policies: list[CustomerAccessTenantPolicy] = Field(default_factory=list)
    updated_at: str | None = None


class UpdateCustomerAccessTenantPolicyRequest(APIModel):
    tenant_id: str
    tenant_name: str | None = None
    verification_mode: CustomerAccessVerificationMode = "relaxed"
    service_codes: list[str] = Field(default_factory=list)
    enabled: bool = True


class UpdateCustomerAccessSettingsRequest(APIModel):
    template_intro: str | None = None
    tenant_policies: list[UpdateCustomerAccessTenantPolicyRequest] | None = None


class CustomerAccessSettingsResponse(APIModel):
    settings: CustomerAccessSettings


class CustomerAccessSettingsActionResponse(APIModel):
    ok: bool
    message: str
    settings: CustomerAccessSettings


class CustomerAdmissionResult(APIModel):
    status: CustomerAccessStatus
    reply_message: str | None = None
    tenant_id: str | None = None
    tenant_name: str | None = None
    customer_id: str | None = None
    profile_id: str | None = None
    service_code: str | None = None
    matched_policy: CustomerAccessTenantPolicy | None = None
    missing_fields: list[str] = Field(default_factory=list)
