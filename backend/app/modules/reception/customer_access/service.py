from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha1
import json
import re
from typing import Any

from app.modules.organization.application import profile_service as organization_profile_service
from app.modules.reception.customer_access.schemas import (
    CustomerAccessSettings,
    CustomerAccessTemplateField,
    CustomerAccessTenantPolicy,
    CustomerAdmissionResult,
    UpdateCustomerAccessSettingsRequest,
)
from app.modules.reception.schemas.messages import UnifiedMessage
from app.platform.config.settings_service import get_channel_integration_runtime_settings
from app.platform.persistence.persistence_service import persistence_service
from app.platform.persistence.runtime_store import store


CUSTOMER_ACCESS_SETTING_KEY = "customer_access"
LEGACY_DEFAULT_TEMPLATE_INTRO = (
    "为确认您的服务归属，请按以下模板填写：\n"
    "1. 企业名称\n"
    "2. 联系人姓名\n"
    "3. 手机号\n"
    "4. 服务识别码（客户编号 / 邀请码 / 服务码）\n\n"
    "提交后系统会自动完成绑定，后续无需重复填写。"
)
PREVIOUS_DEFAULT_TEMPLATE_INTRO = (
    "为确认您的服务归属，请按以下模板填写：\n"
    "1. 服务识别码\n"
    "2. 用户名称\n"
    "3. 用户电话号\n\n"
    "首次接入请完整填写以上信息；若您已完成注册，后续仅需提供服务识别码。"
)
DEFAULT_TEMPLATE_INTRO = (
    "为确认您的服务归属，请按以下模板填写：\n"
    "1. 服务识别码：SR-XXXX-XXXX-XXXX-XXXX\n"
    "2. 用户名称：张三\n"
    "3. 用户电话号：13800138000\n\n"
    "首次接入请完整填写以上信息；若您已完成注册，后续仅需提供“服务识别码：SR-XXXX-XXXX-XXXX-XXXX”。"
)
DEFAULT_TEMPLATE_FIELDS = [
    CustomerAccessTemplateField(key="service_code", label="服务识别码", required=True),
    CustomerAccessTemplateField(key="contact_name", label="用户名称", required=True),
    CustomerAccessTemplateField(key="mobile", label="用户电话号", required=True),
]
COMPANY_NAME_ALIASES = ("企业名称", "公司名称", "企业", "公司", "company_name", "company")
CONTACT_NAME_ALIASES = ("用户名称", "联系人姓名", "联系人", "姓名", "contact_name", "contact", "user_name")
MOBILE_ALIASES = ("用户电话号", "用户手机号", "手机号", "手机", "联系电话", "mobile", "phone")
SERVICE_CODE_ALIASES = ("服务识别码", "客户编号", "邀请码", "服务码", "service_code", "code")
MOBILE_RE = re.compile(r"^[0-9+\-\s]{6,20}$")
NUMBERED_LINE_PREFIX_RE = re.compile(r"^\s*(?:\(?\d+\)?|（\d+）)\s*[.、:：)]?\s*")
SERVICE_CODE_CANDIDATE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{5,63}$")
CUSTOMER_ACCESS_SYSTEM_ACTOR = {
    "id": "customer-access-service",
    "email": "customer-access@workbot.local",
    "role": "super_admin",
    "platform_admin": True,
}


@dataclass(slots=True)
class ParsedAccessTemplate:
    company_name: str | None = None
    contact_name: str | None = None
    mobile: str | None = None
    service_code: str | None = None

    def missing_fields_for_new_registration(self) -> list[str]:
        missing: list[str] = []
        if not self.contact_name:
            missing.append("contact_name")
        if not self.mobile:
            missing.append("mobile")
        if not self.service_code:
            missing.append("service_code")
        return missing


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _normalize_string_list(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    items: list[str] = []
    seen: set[str] = set()
    for raw in values:
        normalized = _normalize_text(raw)
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        items.append(normalized)
    return items


def _default_settings() -> CustomerAccessSettings:
    return CustomerAccessSettings(
        template_intro=DEFAULT_TEMPLATE_INTRO,
        template_fields=deepcopy(DEFAULT_TEMPLATE_FIELDS),
        tenant_policies=[],
        updated_at=None,
    )


def _normalize_tenant_policy(payload: object) -> CustomerAccessTenantPolicy | None:
    if not isinstance(payload, dict):
        return None
    tenant_id = _normalize_text(payload.get("tenant_id") or payload.get("tenantId"))
    if not tenant_id:
        return None
    verification_mode = _normalize_text(
        payload.get("verification_mode") or payload.get("verificationMode") or "relaxed"
    ).lower()
    if verification_mode not in {"relaxed", "strict"}:
        verification_mode = "relaxed"
    return CustomerAccessTenantPolicy(
        tenant_id=tenant_id,
        tenant_name=_normalize_text(payload.get("tenant_name") or payload.get("tenantName")) or None,
        verification_mode=verification_mode,  # type: ignore[arg-type]
        service_codes=_normalize_string_list(payload.get("service_codes") or payload.get("serviceCodes")),
        enabled=bool(payload.get("enabled", True)),
    )


def _normalize_settings(payload: object) -> CustomerAccessSettings:
    if not isinstance(payload, dict):
        return _default_settings()

    template_intro = _normalize_text(payload.get("template_intro") or payload.get("templateIntro"))
    if template_intro in {LEGACY_DEFAULT_TEMPLATE_INTRO, PREVIOUS_DEFAULT_TEMPLATE_INTRO}:
        template_intro = DEFAULT_TEMPLATE_INTRO
    policies_payload = payload.get("tenant_policies") or payload.get("tenantPolicies") or []
    policies: list[CustomerAccessTenantPolicy] = []
    for item in policies_payload if isinstance(policies_payload, list) else []:
        policy = _normalize_tenant_policy(item)
        if policy is not None:
            policies.append(policy)

    return CustomerAccessSettings(
        template_intro=template_intro or DEFAULT_TEMPLATE_INTRO,
        template_fields=deepcopy(DEFAULT_TEMPLATE_FIELDS),
        tenant_policies=policies,
        updated_at=_normalize_text(payload.get("updated_at") or payload.get("updatedAt")) or None,
    )


def _current_settings() -> CustomerAccessSettings:
    read_setting = getattr(persistence_service, "read_system_setting", None)
    if callable(read_setting):
        persisted, authoritative = read_setting(CUSTOMER_ACCESS_SETTING_KEY)
        if authoritative and isinstance(persisted, dict):
            payload = persisted.get("payload")
            settings = _normalize_settings(payload)
            store.system_settings[CUSTOMER_ACCESS_SETTING_KEY] = settings.model_dump(mode="json")
            return settings

    cached = store.system_settings.get(CUSTOMER_ACCESS_SETTING_KEY)
    if isinstance(cached, dict):
        return _normalize_settings(cached)

    settings = _default_settings()
    store.system_settings[CUSTOMER_ACCESS_SETTING_KEY] = settings.model_dump(mode="json")
    return settings


def _persist_settings(settings: CustomerAccessSettings) -> None:
    dumped = settings.model_dump(mode="json")
    store.system_settings[CUSTOMER_ACCESS_SETTING_KEY] = deepcopy(dumped)
    persistence_service.persist_system_setting(
        key=CUSTOMER_ACCESS_SETTING_KEY,
        payload=dumped,
        updated_at=settings.updated_at or store.now_string(),
    )


def get_customer_access_settings() -> CustomerAccessSettings:
    return _current_settings()


def update_customer_access_settings(payload: UpdateCustomerAccessSettingsRequest) -> CustomerAccessSettings:
    current = _current_settings()
    if payload.template_intro is not None:
        current.template_intro = _normalize_text(payload.template_intro) or DEFAULT_TEMPLATE_INTRO
    if payload.tenant_policies is not None:
        current.tenant_policies = [
            CustomerAccessTenantPolicy(
                tenant_id=item.tenant_id,
                tenant_name=item.tenant_name,
                verification_mode=item.verification_mode,
                service_codes=_normalize_string_list(item.service_codes),
                enabled=item.enabled,
            )
            for item in payload.tenant_policies
            if _normalize_text(item.tenant_id)
        ]
    current.updated_at = store.now_string()
    _persist_settings(current)
    return current


def _resolve_channel_tenant_binding(channel: str) -> tuple[str | None, str | None]:
    settings = get_channel_integration_runtime_settings()
    provider = settings.get(channel) if isinstance(settings, dict) else None
    if not isinstance(provider, dict):
        return None, None
    tenant_id = _normalize_text(provider.get("tenant_id") or provider.get("tenantId")) or None
    tenant_name = _normalize_text(provider.get("tenant_name") or provider.get("tenantName")) or None
    return organization_profile_service.resolve_tenant_binding(tenant_id, tenant_name)


def _resolve_message_tenant_binding(message: UnifiedMessage) -> tuple[str | None, str | None]:
    metadata = message.metadata if isinstance(message.metadata, dict) else {}
    metadata_tenant_id = _normalize_text(metadata.get("tenant_id") or metadata.get("tenantId")) or None
    metadata_tenant_name = _normalize_text(metadata.get("tenant_name") or metadata.get("tenantName")) or None
    if metadata_tenant_id:
        return organization_profile_service.resolve_tenant_binding(metadata_tenant_id, metadata_tenant_name)
    return _resolve_channel_tenant_binding(_normalize_text(message.channel.value).lower())


def _find_policy(settings: CustomerAccessSettings, tenant_id: str | None) -> CustomerAccessTenantPolicy | None:
    if not tenant_id:
        return None
    for policy in settings.tenant_policies:
        if not policy.enabled:
            continue
        if _normalize_text(policy.tenant_id) == tenant_id:
            return policy
    return None


def _parse_json_like_text(text: str) -> dict[str, Any] | None:
    normalized = text.strip()
    if not normalized:
        return None
    if not (normalized.startswith("{") and normalized.endswith("}")):
        return None
    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _extract_template_value(payload: dict[str, Any], aliases: tuple[str, ...]) -> str | None:
    alias_set = {alias.lower() for alias in aliases}
    for key, value in payload.items():
        normalized_key = _normalize_text(key).lower()
        if normalized_key in alias_set:
            normalized_value = _normalize_text(value)
            if normalized_value:
                return normalized_value
    return None


def _parse_template_submission(text: str) -> ParsedAccessTemplate:
    parsed = ParsedAccessTemplate()
    json_payload = _parse_json_like_text(text)
    if json_payload is not None:
        parsed.company_name = _extract_template_value(json_payload, COMPANY_NAME_ALIASES)
        parsed.contact_name = _extract_template_value(json_payload, CONTACT_NAME_ALIASES)
        parsed.mobile = _extract_template_value(json_payload, MOBILE_ALIASES)
        parsed.service_code = _extract_template_value(json_payload, SERVICE_CODE_ALIASES)
        return parsed

    positional_values: list[str] = []
    for line in text.splitlines():
        normalized_line = _normalize_text(line)
        if not normalized_line:
            continue
        normalized_line = _normalize_text(NUMBERED_LINE_PREFIX_RE.sub("", normalized_line))
        if not normalized_line:
            continue
        if ":" in normalized_line:
            key, value = normalized_line.split(":", maxsplit=1)
        elif "：" in normalized_line:
            key, value = normalized_line.split("：", maxsplit=1)
        else:
            positional_values.append(normalized_line)
            continue
        normalized_key = _normalize_text(key).lower()
        normalized_value = _normalize_text(value)
        if not normalized_value:
            continue
        if normalized_key in {alias.lower() for alias in COMPANY_NAME_ALIASES}:
            parsed.company_name = normalized_value
        elif normalized_key in {alias.lower() for alias in CONTACT_NAME_ALIASES}:
            parsed.contact_name = normalized_value
        elif normalized_key in {alias.lower() for alias in MOBILE_ALIASES}:
            parsed.mobile = normalized_value
        elif normalized_key in {alias.lower() for alias in SERVICE_CODE_ALIASES}:
            parsed.service_code = normalized_value

    if positional_values:
        can_map_positionally = _looks_like_service_code_candidate(positional_values[0])
        if can_map_positionally and not parsed.service_code and len(positional_values) >= 1:
            parsed.service_code = positional_values[0]
        if can_map_positionally and not parsed.contact_name and len(positional_values) >= 2:
            parsed.contact_name = positional_values[1]
        if can_map_positionally and not parsed.mobile and len(positional_values) >= 3:
            parsed.mobile = positional_values[2]
    return parsed


def _looks_like_service_code_candidate(value: str) -> bool:
    normalized = _normalize_text(value)
    if not normalized:
        return False
    if not SERVICE_CODE_CANDIDATE_RE.fullmatch(normalized):
        return False
    return any(char.isdigit() for char in normalized) or "-" in normalized or "_" in normalized


def _template_prompt(settings: CustomerAccessSettings) -> str:
    return settings.template_intro


def _find_existing_profile(*, platform: str, account_id: str, tenant_id: str) -> dict[str, Any] | None:
    persisted = persistence_service.find_user_profile_by_platform_account(
        platform=platform,
        account_id=account_id,
    )
    if isinstance(persisted, dict) and _normalize_text(persisted.get("tenant_id")) == tenant_id:
        return deepcopy(persisted)

    for profile in store.user_profiles.values():
        if not isinstance(profile, dict):
            continue
        if _normalize_text(profile.get("tenant_id")) != tenant_id:
            continue
        accounts = profile.get("platform_accounts") or profile.get("platformAccounts") or []
        if not isinstance(accounts, list):
            continue
        for account in accounts:
            if not isinstance(account, dict):
                continue
            if (
                _normalize_text(account.get("platform")).lower() == platform
                and _normalize_text(account.get("account_id") or account.get("accountId")) == account_id
            ):
                return deepcopy(profile)
    return None


def _build_profile_id(*, tenant_id: str, platform: str, account_id: str) -> str:
    digest = sha1(f"{tenant_id}:{platform}:{account_id}".encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"profile-{digest}"


def _build_customer_id(*, tenant_id: str, service_code: str, mobile: str) -> str:
    digest = sha1(f"{tenant_id}:{service_code}:{mobile}".encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"customer-{digest}"


def _ensure_mobile(value: str | None) -> str | None:
    normalized = _normalize_text(value)
    if not normalized:
        return None
    if not MOBILE_RE.match(normalized):
        return None
    return normalized


def _normalize_identity_text(value: object) -> str:
    return re.sub(r"\s+", "", _normalize_text(value)).lower()


def _looks_like_access_submission(text: str) -> bool:
    parsed = _parse_template_submission(text)
    if parsed.service_code:
        return True

    normalized_text = _normalize_text(text).lower()
    alias_groups = (
        COMPANY_NAME_ALIASES,
        CONTACT_NAME_ALIASES,
        MOBILE_ALIASES,
        SERVICE_CODE_ALIASES,
    )
    hits = 0
    for aliases in alias_groups:
        if any(alias.lower() in normalized_text for alias in aliases):
            hits += 1
    return hits >= 2


def _profile_candidate_score(
    profile: dict[str, Any],
    *,
    platform: str | None = None,
    account_id: str | None = None,
    service_code: str | None = None,
    company_name: str | None = None,
    contact_name: str | None = None,
    mobile: str | None = None,
) -> tuple[int, int, str, str]:
    score = 0
    normalized_service_code = _normalize_text(service_code)
    normalized_mobile = _normalize_text(mobile)
    normalized_company = _normalize_identity_text(company_name)
    normalized_contact = _normalize_identity_text(contact_name)
    normalized_platform = _normalize_text(platform).lower()
    normalized_account_id = _normalize_text(account_id)

    if normalized_service_code and _normalize_text(profile.get("service_code") or profile.get("serviceCode")) == normalized_service_code:
        score += 8
    if normalized_mobile and _normalize_text(profile.get("mobile")) == normalized_mobile:
        score += 4
    if normalized_contact and _normalize_identity_text(profile.get("contact_name") or profile.get("contactName")) == normalized_contact:
        score += 2
    if normalized_company and _normalize_identity_text(profile.get("company_name") or profile.get("companyName")) == normalized_company:
        score += 1
    if normalized_platform and normalized_account_id:
        accounts = profile.get("platform_accounts") or profile.get("platformAccounts") or []
        for account in accounts if isinstance(accounts, list) else []:
            if not isinstance(account, dict):
                continue
            if (
                _normalize_text(account.get("platform")).lower() == normalized_platform
                and _normalize_text(account.get("account_id") or account.get("accountId")) == normalized_account_id
            ):
                score += 6
                break
    if _normalize_text(profile.get("service_status") or profile.get("serviceStatus")).lower() == "active":
        score += 1

    try:
        total_interactions = int(profile.get("total_interactions") or profile.get("totalInteractions") or 0)
    except (TypeError, ValueError):
        total_interactions = 0
    return (
        score,
        total_interactions,
        _normalize_text(profile.get("last_active_at") or profile.get("lastActiveAt") or profile.get("last_seen_at") or profile.get("updated_at")),
        _normalize_text(profile.get("id")),
    )


def _select_best_profile_candidate(
    candidates: list[dict[str, Any]],
    *,
    platform: str | None = None,
    account_id: str | None = None,
    service_code: str | None = None,
    company_name: str | None = None,
    contact_name: str | None = None,
    mobile: str | None = None,
) -> dict[str, Any] | None:
    if not candidates:
        return None
    ranked = sorted(
        candidates,
        key=lambda profile: _profile_candidate_score(
            profile,
            platform=platform,
            account_id=account_id,
            service_code=service_code,
            company_name=company_name,
            contact_name=contact_name,
            mobile=mobile,
        ),
        reverse=True,
    )
    return deepcopy(ranked[0]) if ranked else None


def _mask_mobile(value: object) -> str | None:
    normalized = re.sub(r"\s+", "", _normalize_text(value))
    if not normalized:
        return None
    digits = "".join(char for char in normalized if char.isdigit())
    if len(digits) >= 7:
        return f"{digits[:3]}****{digits[-4:]}"
    if len(digits) >= 4:
        return f"***{digits[-4:]}"
    return normalized


def _truncate_profile_summary(value: object, *, limit: int = 72) -> str | None:
    normalized = _normalize_text(value)
    if not normalized:
        return None
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _build_bound_reply_message(
    *,
    profile: dict[str, Any],
    tenant_name: str,
    action: str,
) -> str:
    contact_name = _normalize_text(profile.get("contact_name") or profile.get("contactName"))
    display_name = contact_name or _normalize_text(profile.get("name")) or "您好"
    profile_summary = _truncate_profile_summary(profile.get("profile_summary") or profile.get("profileSummary"))
    mobile = _mask_mobile(profile.get("mobile"))
    service_status = {
        "active": "服务中",
        "paused": "已暂停",
        "inactive": "未激活",
    }.get(_normalize_text(profile.get("service_status") or profile.get("serviceStatus")).lower(), "")

    opening = {
        "existing": f"{display_name}，已确认您当前账号的服务绑定。",
        "rebound": f"{display_name}，已识别到您已有的服务档案，并完成本次绑定。",
        "created": f"{display_name}，已为您完成登记并绑定平台服务。",
    }.get(action, f"{display_name}，已完成服务绑定。")

    lines = [opening, f"当前归属：{tenant_name}。"]
    if profile_summary:
        lines.append(f"画像信息：{profile_summary}")
    else:
        facts: list[str] = []
        if contact_name:
            facts.append(f"联系人 {contact_name}")
        if mobile:
            facts.append(f"手机号 {mobile}")
        if service_status:
            facts.append(f"当前状态 {service_status}")
        if facts:
            lines.append("已识别信息：" + "，".join(facts) + "。")
    lines.append("您可以直接告诉我现在想咨询或办理什么，我会结合当前画像继续为您跟进。")
    return "\n".join(line for line in lines if line)


def _find_registered_profile_by_identity(
    *,
    tenant_id: str,
    company_name: str | None,
    contact_name: str | None,
    mobile: str | None,
    platform: str | None = None,
    account_id: str | None = None,
    service_code: str | None = None,
) -> dict[str, Any] | None:
    normalized_mobile = _normalize_text(mobile)
    if not normalized_mobile:
        return None
    normalized_company = _normalize_identity_text(company_name)
    normalized_contact = _normalize_identity_text(contact_name)
    if not normalized_company and not normalized_contact:
        return None

    listed = organization_profile_service.list_profiles(
        current_user=CUSTOMER_ACCESS_SYSTEM_ACTOR,
        tenant_id=tenant_id,
        management_view=True,
    )
    items = listed.get("items") if isinstance(listed, dict) else []
    if not isinstance(items, list):
        return None

    matched: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if _normalize_text(item.get("tenant_id") or item.get("tenantId")) != tenant_id:
            continue
        if _normalize_text(item.get("mobile")) != normalized_mobile:
            continue
        if normalized_company and _normalize_identity_text(item.get("company_name") or item.get("companyName")) != normalized_company:
            continue
        if normalized_contact and _normalize_identity_text(item.get("contact_name") or item.get("contactName")) != normalized_contact:
            continue
        profile_id = _normalize_text(item.get("id"))
        if not profile_id:
            continue
        matched.append(item)
    return _select_best_profile_candidate(
        matched,
        platform=platform,
        account_id=account_id,
        service_code=service_code,
        company_name=company_name,
        contact_name=contact_name,
        mobile=mobile,
    )


def _find_registered_profile_by_service_code(
    *,
    tenant_id: str,
    service_code: str | None,
    platform: str | None = None,
    account_id: str | None = None,
    company_name: str | None = None,
    contact_name: str | None = None,
    mobile: str | None = None,
) -> dict[str, Any] | None:
    normalized_service_code = _normalize_text(service_code)
    if not normalized_service_code:
        return None

    profiles_payload = persistence_service.list_user_profiles()
    profiles = profiles_payload if isinstance(profiles_payload, list) else list(store.user_profiles.values())
    matched: list[dict[str, Any]] = []
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        if _normalize_text(profile.get("tenant_id") or profile.get("tenantId")) != tenant_id:
            continue
        if _normalize_text(profile.get("service_code") or profile.get("serviceCode")) != normalized_service_code:
            continue
        matched.append(profile)
    return _select_best_profile_candidate(
        matched,
        platform=platform,
        account_id=account_id,
        service_code=service_code,
        company_name=company_name,
        contact_name=contact_name,
        mobile=mobile,
    )


def _bind_existing_profile_to_channel(
    *,
    profile_id: str,
    channel: str,
    platform_user_id: str,
    template: ParsedAccessTemplate,
) -> dict[str, Any]:
    existing = organization_profile_service.get_profile(
        profile_id,
        current_user=CUSTOMER_ACCESS_SYSTEM_ACTOR,
    )
    existing_accounts = existing.get("platform_accounts") or existing.get("platformAccounts") or []
    normalized_accounts: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for account in existing_accounts if isinstance(existing_accounts, list) else []:
        if not isinstance(account, dict):
            continue
        platform = _normalize_text(account.get("platform")).lower()
        account_id = _normalize_text(account.get("account_id") or account.get("accountId"))
        if not platform or not account_id:
            continue
        key = (platform, account_id)
        if key in seen:
            continue
        seen.add(key)
        normalized_accounts.append({"platform": platform, "account_id": account_id})
    next_key = (_normalize_text(channel).lower(), _normalize_text(platform_user_id))
    if next_key[0] and next_key[1] and next_key not in seen:
        normalized_accounts.append({"platform": next_key[0], "account_id": next_key[1]})

    source_channels = existing.get("source_channels") or existing.get("sourceChannels") or []
    normalized_channels = {
        _normalize_text(value).lower()
        for value in (source_channels if isinstance(source_channels, list) else [])
        if _normalize_text(value)
    }
    normalized_channels.add(_normalize_text(channel).lower())
    now = store.now_string()
    updates: dict[str, Any] = {
        "platform_accounts": normalized_accounts,
        "channel_accounts": normalized_accounts,
        "source_channels": sorted(normalized_channels),
        "last_login": now,
        "last_seen_at": now,
        "last_active_at": now,
        "identity_mapping_status": "verified",
        "identity_mapping_source": "customer_access",
        "identity_mapping_confidence": 1.0,
        "last_identity_sync_at": now,
        "service_status": "active",
    }
    if not _normalize_text(existing.get("company_name") or existing.get("companyName")) and _normalize_text(template.company_name):
        updates["company_name"] = _normalize_text(template.company_name)
    if not _normalize_text(existing.get("contact_name") or existing.get("contactName")) and _normalize_text(template.contact_name):
        updates["contact_name"] = _normalize_text(template.contact_name)
    if not _normalize_text(existing.get("mobile")) and _normalize_text(template.mobile):
        updates["mobile"] = _normalize_text(template.mobile)
    if not _normalize_text(existing.get("service_code") or existing.get("serviceCode")) and _normalize_text(template.service_code):
        updates["service_code"] = _normalize_text(template.service_code)

    result = organization_profile_service.update_profile(
        profile_id,
        current_user=CUSTOMER_ACCESS_SYSTEM_ACTOR,
        changes=updates,
    )
    return deepcopy(result["profile"])


def _persist_profile(
    *,
    profile_id: str,
    customer_id: str,
    tenant_id: str,
    tenant_name: str,
    channel: str,
    platform_user_id: str,
    template: ParsedAccessTemplate,
) -> dict[str, Any]:
    now = store.now_string()
    result = organization_profile_service.upsert_profile(
        current_user=CUSTOMER_ACCESS_SYSTEM_ACTOR,
        profile_id=profile_id,
        changes={
            "customer_id": customer_id,
            "tenant_id": tenant_id,
            "tenant_name": tenant_name,
            "name": template.contact_name or platform_user_id,
            "email": f"{channel}-{platform_user_id}@external.workbot.local",
            "role": "viewer",
            "status": "active",
            "last_login": now,
            "total_interactions": 0,
            "created_at": now.split("T", maxsplit=1)[0],
            "tags": ["平台接待客户", f"{channel}接入"],
            "notes": "由客户准入确认层创建。",
            "preferred_language": "zh",
            "source_channels": [channel],
            "platform_accounts": [{"platform": channel, "account_id": platform_user_id}],
            "last_active_at": now,
            "last_seen_at": now,
            "company_name": template.company_name,
            "contact_name": template.contact_name,
            "mobile": template.mobile,
            "service_code": template.service_code,
            "service_status": "active",
            "identity_mapping_status": "verified",
            "identity_mapping_source": "customer_access",
            "identity_mapping_confidence": 1.0,
            "last_identity_sync_at": now,
        },
        sync_user_state=True,
    )
    return deepcopy(result["profile"])


def _apply_profile_metadata(message: UnifiedMessage, profile: dict[str, Any]) -> None:
    metadata = message.metadata if isinstance(message.metadata, dict) else {}
    metadata["tenant_id"] = _normalize_text(profile.get("tenant_id"))
    metadata["tenant_name"] = _normalize_text(profile.get("tenant_name"))
    metadata["user_profile_id"] = _normalize_text(profile.get("id"))
    metadata["customer_id"] = _normalize_text(profile.get("customer_id"))
    metadata["service_code"] = _normalize_text(profile.get("service_code"))
    message.metadata = metadata


class CustomerAccessService:
    def get_settings(self) -> CustomerAccessSettings:
        return get_customer_access_settings()

    def update_settings(self, payload: UpdateCustomerAccessSettingsRequest) -> CustomerAccessSettings:
        return update_customer_access_settings(payload)

    def admit_message(self, message: UnifiedMessage) -> CustomerAdmissionResult:
        channel = _normalize_text(message.channel.value).lower()
        platform_user_id = _normalize_text(message.platform_user_id)
        tenant_id, tenant_name = _resolve_message_tenant_binding(message)
        settings = _current_settings()

        if not channel or not platform_user_id:
            return CustomerAdmissionResult(
                status="rejected",
                reply_message="客户准入失败：消息缺少渠道用户标识。",
            )

        if not tenant_id:
            return CustomerAdmissionResult(
                status="rejected",
                reply_message="当前渠道尚未绑定租户，暂时无法接入平台接待。",
            )
        resolved_tenant_name = tenant_name or f"{tenant_id} 租户"

        existing_profile = _find_existing_profile(
            platform=channel,
            account_id=platform_user_id,
            tenant_id=tenant_id,
        )
        if existing_profile is not None:
            _apply_profile_metadata(message, existing_profile)
            reply_message = None
            if _looks_like_access_submission(message.text):
                reply_message = _build_bound_reply_message(
                    profile=existing_profile,
                    tenant_name=resolved_tenant_name,
                    action="existing",
                )
            return CustomerAdmissionResult(
                status="bound",
                reply_message=reply_message,
                tenant_id=tenant_id,
                tenant_name=resolved_tenant_name,
                customer_id=_normalize_text(existing_profile.get("customer_id")) or None,
                profile_id=_normalize_text(existing_profile.get("id")) or None,
                service_code=_normalize_text(existing_profile.get("service_code")) or None,
                matched_policy=_find_policy(settings, tenant_id),
            )

        parsed = _parse_template_submission(message.text)
        parsed.mobile = _ensure_mobile(parsed.mobile)
        service_code = _normalize_text(parsed.service_code)
        if not service_code:
            return CustomerAdmissionResult(
                status="pending_verification",
                reply_message=_template_prompt(settings),
                tenant_id=tenant_id,
                tenant_name=resolved_tenant_name,
                missing_fields=["service_code"],
                matched_policy=_find_policy(settings, tenant_id),
            )

        policy = _find_policy(settings, tenant_id)
        matched_profile = _find_registered_profile_by_service_code(
            tenant_id=tenant_id,
            service_code=service_code,
            platform=channel,
            account_id=platform_user_id,
            company_name=parsed.company_name,
            contact_name=parsed.contact_name,
            mobile=parsed.mobile,
        )
        if matched_profile is not None:
            profile = _bind_existing_profile_to_channel(
                profile_id=_normalize_text(matched_profile.get("id")),
                channel=channel,
                platform_user_id=platform_user_id,
                template=parsed,
            )
            _apply_profile_metadata(message, profile)
            return CustomerAdmissionResult(
                status="bound",
                reply_message=_build_bound_reply_message(
                    profile=profile,
                    tenant_name=resolved_tenant_name,
                    action="rebound",
                ),
                tenant_id=tenant_id,
                tenant_name=resolved_tenant_name,
                customer_id=_normalize_text(profile.get("customer_id")) or None,
                profile_id=_normalize_text(profile.get("id")) or None,
                service_code=_normalize_text(profile.get("service_code")) or None,
                matched_policy=policy,
            )

        registration_code_matched = organization_profile_service.match_profile_tenant_service_registration_code(
            tenant_id=tenant_id,
            registration_code=service_code,
        )
        allowed_codes = {code.lower() for code in policy.service_codes} if policy is not None else set()
        manual_code_allowed = service_code.lower() in allowed_codes
        if not registration_code_matched and not manual_code_allowed:
            return CustomerAdmissionResult(
                status="rejected",
                reply_message="服务识别码未通过校验，当前无法确认您属于平台服务对象。",
                tenant_id=tenant_id,
                tenant_name=resolved_tenant_name,
                service_code=service_code,
                matched_policy=policy,
            )

        missing_fields = parsed.missing_fields_for_new_registration()
        if missing_fields:
            return CustomerAdmissionResult(
                status="pending_verification",
                reply_message=_template_prompt(settings),
                tenant_id=tenant_id,
                tenant_name=resolved_tenant_name,
                missing_fields=missing_fields,
                service_code=service_code,
                matched_policy=policy,
            )

        identity_profile = _find_registered_profile_by_identity(
            tenant_id=tenant_id,
            company_name=parsed.company_name,
            contact_name=parsed.contact_name,
            mobile=parsed.mobile,
            platform=channel,
            account_id=platform_user_id,
            service_code=service_code,
        )
        if identity_profile is not None:
            profile = _bind_existing_profile_to_channel(
                profile_id=_normalize_text(identity_profile.get("id")),
                channel=channel,
                platform_user_id=platform_user_id,
                template=parsed,
            )
            _apply_profile_metadata(message, profile)
            return CustomerAdmissionResult(
                status="bound",
                reply_message=_build_bound_reply_message(
                    profile=profile,
                    tenant_name=resolved_tenant_name,
                    action="rebound",
                ),
                tenant_id=tenant_id,
                tenant_name=resolved_tenant_name,
                customer_id=_normalize_text(profile.get("customer_id")) or None,
                profile_id=_normalize_text(profile.get("id")) or None,
                service_code=_normalize_text(profile.get("service_code")) or service_code or None,
                matched_policy=policy,
            )

        profile_id = _build_profile_id(
            tenant_id=tenant_id,
            platform=channel,
            account_id=platform_user_id,
        )
        customer_id = _build_customer_id(
            tenant_id=tenant_id,
            service_code=service_code,
            mobile=str(parsed.mobile or ""),
        )
        profile = _persist_profile(
            profile_id=profile_id,
            customer_id=customer_id,
            tenant_id=tenant_id,
            tenant_name=resolved_tenant_name,
            channel=channel,
            platform_user_id=platform_user_id,
            template=parsed,
        )
        if registration_code_matched:
            organization_profile_service.consume_profile_tenant_service_registration_code(
                tenant_id=tenant_id,
                registration_code=service_code,
            )
        _apply_profile_metadata(message, profile)
        return CustomerAdmissionResult(
            status="bound",
            reply_message=_build_bound_reply_message(
                profile=profile,
                tenant_name=resolved_tenant_name,
                action="created",
            ),
            tenant_id=tenant_id,
            tenant_name=resolved_tenant_name,
            customer_id=customer_id,
            profile_id=profile_id,
            service_code=service_code,
            matched_policy=policy,
        )


customer_access_service = CustomerAccessService()
