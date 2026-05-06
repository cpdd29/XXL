from __future__ import annotations

from app.modules.organization.application import profile_service as organization_profile_service
from app.modules.reception.customer_access.schemas import (
    UpdateCustomerAccessSettingsRequest,
    UpdateCustomerAccessTenantPolicyRequest,
)
from app.modules.reception.customer_access.service import (
    PREVIOUS_DEFAULT_TEMPLATE_INTRO,
    customer_access_service,
    get_customer_access_settings,
)
from app.modules.reception.schemas.messages import ChannelType, UnifiedMessage
from app.platform.persistence.persistence_service import persistence_service
from app.platform.persistence.runtime_store import store


def test_profile_service_upsert_profile_syncs_runtime_user_when_requested() -> None:
    result = organization_profile_service.upsert_profile(
        current_user={
            "id": "customer-access-service",
            "email": "customer-access@workbot.local",
            "role": "super_admin",
            "platform_admin": True,
        },
        profile_id="profile-admission-sync",
        changes={
            "tenant_id": "tenant-alpha",
            "tenant_name": "Alpha Corp",
            "customer_id": "customer-alpha-sync",
            "name": "张准入",
            "contact_name": "张准入",
            "company_name": "甲方企业",
            "mobile": "13800000001",
            "service_code": "ALPHA-001",
            "email": "telegram-alpha-user@external.workbot.local",
            "role": "viewer",
            "status": "active",
            "created_at": "2026-04-27T09:00:00+00:00",
            "last_login": "2026-04-27T09:00:00+00:00",
            "total_interactions": 0,
            "platform_accounts": [{"platform": "telegram", "account_id": "alpha-user"}],
            "source_channels": ["telegram"],
            "tags": ["平台接待客户"],
            "notes": "由客户准入确认层创建。",
            "preferred_language": "zh",
            "identity_mapping_status": "verified",
            "identity_mapping_source": "customer_access",
            "identity_mapping_confidence": 1.0,
            "last_identity_sync_at": "2026-04-27T09:00:00+00:00",
        },
        sync_user_state=True,
    )

    profile = result["profile"]
    runtime_profile = store.user_profiles["profile-admission-sync"]
    runtime_user = next(user for user in store.users if user["id"] == "profile-admission-sync")

    assert profile["service_code"] == "ALPHA-001"
    assert runtime_profile["service_code"] == "ALPHA-001"
    assert runtime_profile["identity_mapping_source"] == "customer_access"
    assert runtime_user == {
        "id": "profile-admission-sync",
        "name": "张准入",
        "email": "telegram-alpha-user@external.workbot.local",
        "role": "viewer",
        "status": "active",
        "last_login": "2026-04-27T09:00:00+00:00",
        "total_interactions": 0,
        "created_at": "2026-04-27T09:00:00+00:00",
    }


def test_customer_access_old_default_template_is_upgraded() -> None:
    store.system_settings["customer_access"] = {
        "template_intro": PREVIOUS_DEFAULT_TEMPLATE_INTRO,
        "template_fields": [],
        "tenant_policies": [],
        "updated_at": None,
    }

    settings = get_customer_access_settings()

    assert "服务识别码：" in settings.template_intro
    assert "用户名称：" in settings.template_intro
    assert "用户电话号：" in settings.template_intro


def test_customer_access_admission_creates_profile_via_organization_profile_service(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.modules.reception.customer_access.service.get_channel_integration_runtime_settings",
        lambda: {
            "telegram": {
                "tenant_id": "tenant-alpha",
                "tenant_name": "Alpha Corp",
            }
        },
    )
    customer_access_service.update_settings(
        UpdateCustomerAccessSettingsRequest(
            tenant_policies=[
                UpdateCustomerAccessTenantPolicyRequest(
                    tenant_id="tenant-alpha",
                    tenant_name="Alpha Corp",
                    verification_mode="strict",
                    service_codes=["ALPHA-ACCESS-001"],
                    enabled=True,
                )
            ]
        )
    )

    message = UnifiedMessage(
        message_id="msg-customer-access-1",
        channel=ChannelType.TELEGRAM,
        platform_user_id="telegram-user-001",
        chat_id="chat-001",
        text="\n".join(
            [
                "服务识别码：ALPHA-ACCESS-001",
                "用户名称：张客户",
                "用户电话号：13800000001",
            ]
        ),
        received_at="2026-04-27T10:00:00+00:00",
        raw_payload={},
    )

    result = customer_access_service.admit_message(message)

    assert result.status == "bound"
    assert result.tenant_id == "tenant-alpha"
    assert result.tenant_name == "Alpha Corp"
    assert result.service_code == "ALPHA-ACCESS-001"
    assert result.profile_id is not None
    assert "已为您完成登记并绑定平台服务" in str(result.reply_message or "")
    assert "张客户" in str(result.reply_message or "")
    assert "Alpha Corp" in str(result.reply_message or "")

    runtime_profile = store.user_profiles[str(result.profile_id)]
    runtime_user = next(user for user in store.users if user["id"] == result.profile_id)

    assert runtime_profile["customer_id"] == result.customer_id
    assert runtime_profile["service_code"] == "ALPHA-ACCESS-001"
    assert runtime_profile["identity_mapping_status"] == "verified"
    assert runtime_profile["identity_mapping_source"] == "customer_access"
    assert runtime_profile["platform_accounts"] == [{"platform": "telegram", "account_id": "telegram-user-001"}]
    assert runtime_user["email"] == "telegram-telegram-user-001@external.workbot.local"
    assert runtime_user["role"] == "viewer"
    assert message.metadata == {
        "tenant_id": "tenant-alpha",
        "tenant_name": "Alpha Corp",
        "user_profile_id": str(result.profile_id),
        "customer_id": str(result.customer_id),
        "service_code": "ALPHA-ACCESS-001",
    }


def test_customer_access_supports_numbered_labeled_template_submission(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.modules.reception.customer_access.service.get_channel_integration_runtime_settings",
        lambda: {
            "telegram": {
                "tenant_id": "tenant-alpha",
                "tenant_name": "Alpha Corp",
            }
        },
    )
    customer_access_service.update_settings(
        UpdateCustomerAccessSettingsRequest(
            tenant_policies=[
                UpdateCustomerAccessTenantPolicyRequest(
                    tenant_id="tenant-alpha",
                    tenant_name="Alpha Corp",
                    verification_mode="strict",
                    service_codes=["SR-TENANT-6F125B-52234F-DBE1AA-6AA698"],
                    enabled=True,
                )
            ]
        )
    )

    message = UnifiedMessage(
        message_id="msg-customer-access-numbered-labeled-1",
        channel=ChannelType.TELEGRAM,
        platform_user_id="telegram-user-numbered-labeled-001",
        chat_id="chat-numbered-labeled-001",
        text="\n".join(
            [
                "1. 服务识别码：SR-TENANT-6F125B-52234F-DBE1AA-6AA698",
                "2. 用户名称：卢雨",
                "3. 用户电话号：15576043511",
            ]
        ),
        received_at="2026-04-29T10:00:00+00:00",
        raw_payload={},
    )

    result = customer_access_service.admit_message(message)

    assert result.status == "bound"
    assert result.service_code == "SR-TENANT-6F125B-52234F-DBE1AA-6AA698"
    assert result.profile_id is not None
    runtime_profile = store.user_profiles[str(result.profile_id)]
    assert runtime_profile["contact_name"] == "卢雨"
    assert runtime_profile["mobile"] == "15576043511"


def test_customer_access_supports_numbered_positional_template_submission(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.modules.reception.customer_access.service.get_channel_integration_runtime_settings",
        lambda: {
            "telegram": {
                "tenant_id": "tenant-alpha",
                "tenant_name": "Alpha Corp",
            }
        },
    )
    customer_access_service.update_settings(
        UpdateCustomerAccessSettingsRequest(
            tenant_policies=[
                UpdateCustomerAccessTenantPolicyRequest(
                    tenant_id="tenant-alpha",
                    tenant_name="Alpha Corp",
                    verification_mode="strict",
                    service_codes=["SR-TENANT-6F125B-52234F-DBE1AA-6AA698"],
                    enabled=True,
                )
            ]
        )
    )

    message = UnifiedMessage(
        message_id="msg-customer-access-numbered-positional-1",
        channel=ChannelType.TELEGRAM,
        platform_user_id="telegram-user-numbered-positional-001",
        chat_id="chat-numbered-positional-001",
        text="\n".join(
            [
                "1、SR-TENANT-6F125B-52234F-DBE1AA-6AA698",
                "2、卢雨",
                "3、15576043511",
            ]
        ),
        received_at="2026-04-29T10:05:00+00:00",
        raw_payload={},
    )

    result = customer_access_service.admit_message(message)

    assert result.status == "bound"
    assert result.service_code == "SR-TENANT-6F125B-52234F-DBE1AA-6AA698"
    assert result.profile_id is not None
    runtime_profile = store.user_profiles[str(result.profile_id)]
    assert runtime_profile["contact_name"] == "卢雨"
    assert runtime_profile["mobile"] == "15576043511"


def test_customer_access_plain_greeting_returns_template_prompt(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.modules.reception.customer_access.service.get_channel_integration_runtime_settings",
        lambda: {
            "telegram": {
                "tenant_id": "tenant-alpha",
                "tenant_name": "Alpha Corp",
            }
        },
    )
    customer_access_service.update_settings(
        UpdateCustomerAccessSettingsRequest(
            tenant_policies=[
                UpdateCustomerAccessTenantPolicyRequest(
                    tenant_id="tenant-alpha",
                    tenant_name="Alpha Corp",
                    verification_mode="strict",
                    service_codes=["ALPHA-ACCESS-001"],
                    enabled=True,
                )
            ]
        )
    )

    message = UnifiedMessage(
        message_id="msg-customer-access-greeting-1",
        channel=ChannelType.TELEGRAM,
        platform_user_id="telegram-user-greeting-001",
        chat_id="chat-greeting-001",
        text="你好",
        received_at="2026-05-03T10:00:00+00:00",
        raw_payload={},
    )

    result = customer_access_service.admit_message(message)

    assert result.status == "pending_verification"
    assert result.service_code is None
    assert result.missing_fields == ["service_code"]
    assert "服务识别码" in str(result.reply_message or "")


def test_customer_access_supports_single_line_service_code_rebind(monkeypatch) -> None:
    actor = {
        "id": "platform-admin",
        "email": "admin@workbot.local",
        "role": "super_admin",
        "platform_admin": True,
    }
    created = organization_profile_service.create_profile_tenant(
        current_user=actor,
        name="Single Line Rebind",
        description="测试仅发送服务识别码的再次绑定",
    )
    tenant_id = str(created["tenant"]["id"])
    tenant_name = str(created["tenant"]["name"])
    generated_code = str(
        organization_profile_service.generate_profile_tenant_service_registration_code(
            tenant_id=tenant_id,
            current_user=actor,
        )["registration_code"]
    )

    customer_access_service.update_settings(
        UpdateCustomerAccessSettingsRequest(
            tenant_policies=[
                UpdateCustomerAccessTenantPolicyRequest(
                    tenant_id=tenant_id,
                    tenant_name=tenant_name,
                    verification_mode="strict",
                    service_codes=[],
                    enabled=True,
                )
            ]
        )
    )

    monkeypatch.setattr(
        "app.modules.reception.customer_access.service.get_channel_integration_runtime_settings",
        lambda: {
            "telegram": {
                "tenant_id": tenant_id,
                "tenant_name": tenant_name,
            },
            "dingtalk": {
                "tenant_id": tenant_id,
                "tenant_name": tenant_name,
            },
        },
    )

    first_message = UnifiedMessage(
        message_id="msg-customer-access-single-line-1",
        channel=ChannelType.TELEGRAM,
        platform_user_id="telegram-user-single-line-001",
        chat_id="chat-single-line-001",
        text="\n".join(
            [
                f"服务识别码：{generated_code}",
                "用户名称：单行客户",
                "用户电话号：13800000011",
            ]
        ),
        received_at="2026-05-03T10:05:00+00:00",
        raw_payload={},
    )
    first_result = customer_access_service.admit_message(first_message)

    second_message = UnifiedMessage(
        message_id="msg-customer-access-single-line-2",
        channel=ChannelType.DINGTALK,
        platform_user_id="dingtalk-user-single-line-002",
        chat_id="chat-single-line-002",
        text=generated_code,
        received_at="2026-05-03T10:10:00+00:00",
        raw_payload={},
    )
    second_result = customer_access_service.admit_message(second_message)

    assert first_result.status == "bound"
    assert second_result.status == "bound"
    assert "已为您完成登记并绑定平台服务" in str(first_result.reply_message or "")
    assert "已识别到您已有的服务档案" in str(second_result.reply_message or "")
    assert second_result.service_code == generated_code
    assert second_result.profile_id == first_result.profile_id


def test_profile_tenant_service_registration_code_generation_preserves_previous_pending_code() -> None:
    actor = {
        "id": "platform-admin",
        "email": "admin@workbot.local",
        "role": "super_admin",
        "platform_admin": True,
    }
    created = organization_profile_service.create_profile_tenant(
        current_user=actor,
        name="Alpha Registration",
        description="用于测试注册码生成",
    )
    tenant_id = str(created["tenant"]["id"])

    first = organization_profile_service.generate_profile_tenant_service_registration_code(
        tenant_id=tenant_id,
        current_user=actor,
    )
    first_code = str(first["registration_code"])
    assert first["status"] == "issued"
    assert first_code.startswith("SR-")

    second = organization_profile_service.generate_profile_tenant_service_registration_code(
        tenant_id=tenant_id,
        current_user=actor,
    )
    second_code = str(second["registration_code"])
    assert second["status"] == "issued"
    assert second_code != first_code

    assert (
        organization_profile_service.consume_profile_tenant_service_registration_code(
            tenant_id=tenant_id,
            registration_code="WRONG-CODE",
        )
        is False
    )
    assert (
        organization_profile_service.consume_profile_tenant_service_registration_code(
            tenant_id=tenant_id,
            registration_code=first_code,
        )
        is True
    )
    assert (
        organization_profile_service.consume_profile_tenant_service_registration_code(
            tenant_id=tenant_id,
            registration_code=second_code,
        )
        is True
    )

    third = organization_profile_service.generate_profile_tenant_service_registration_code(
        tenant_id=tenant_id,
        current_user=actor,
    )
    assert third["status"] == "issued"
    assert third["registration_code"] != second_code
    assert (
        organization_profile_service.match_profile_tenant_service_registration_code(
            tenant_id=tenant_id,
            registration_code=second_code,
        )
        is True
    )


def test_customer_access_strict_policy_supports_generated_code_and_registered_service_code_rebind(monkeypatch) -> None:
    actor = {
        "id": "platform-admin",
        "email": "admin@workbot.local",
        "role": "super_admin",
        "platform_admin": True,
    }
    created = organization_profile_service.create_profile_tenant(
        current_user=actor,
        name="Beta Strict",
        description="严格校验租户",
    )
    tenant_id = str(created["tenant"]["id"])
    tenant_name = str(created["tenant"]["name"])
    code_payload = organization_profile_service.generate_profile_tenant_service_registration_code(
        tenant_id=tenant_id,
        current_user=actor,
    )
    generated_code = str(code_payload["registration_code"])

    monkeypatch.setattr(
        "app.modules.reception.customer_access.service.get_channel_integration_runtime_settings",
        lambda: {
            "telegram": {
                "tenant_id": tenant_id,
                "tenant_name": tenant_name,
            },
            "dingtalk": {
                "tenant_id": tenant_id,
                "tenant_name": tenant_name,
            }
        },
    )
    customer_access_service.update_settings(
        UpdateCustomerAccessSettingsRequest(
            tenant_policies=[
                UpdateCustomerAccessTenantPolicyRequest(
                    tenant_id=tenant_id,
                    tenant_name=tenant_name,
                    verification_mode="strict",
                    service_codes=[],
                    enabled=True,
                )
            ]
        )
    )

    first_message = UnifiedMessage(
        message_id="msg-customer-access-strict-1",
        channel=ChannelType.TELEGRAM,
        platform_user_id="telegram-user-strict-1",
        chat_id="chat-strict-1",
        text="\n".join(
            [
                f"服务识别码：{generated_code}",
                "用户名称：李客户",
                "用户电话号：13800000002",
            ]
        ),
        received_at="2026-04-28T10:00:00+00:00",
        raw_payload={},
    )
    first_result = customer_access_service.admit_message(first_message)
    assert first_result.status == "bound"
    assert first_result.service_code == generated_code
    assert first_result.profile_id is not None
    assert first_result.customer_id is not None

    regenerated = organization_profile_service.generate_profile_tenant_service_registration_code(
        tenant_id=tenant_id,
        current_user=actor,
    )
    assert regenerated["status"] == "issued"
    assert regenerated["registration_code"] != generated_code

    follow_up_message = UnifiedMessage(
        message_id="msg-customer-access-strict-2",
        channel=ChannelType.DINGTALK,
        platform_user_id="dingtalk-user-strict-2",
        chat_id="chat-strict-2",
        text=f"服务识别码：{generated_code}",
        received_at="2026-04-28T10:05:00+00:00",
        raw_payload={},
    )
    follow_up_result = customer_access_service.admit_message(follow_up_message)
    assert follow_up_result.status == "bound"
    assert "已识别到您已有的服务档案" in str(follow_up_result.reply_message or "")
    assert follow_up_result.profile_id == first_result.profile_id
    assert follow_up_result.customer_id == first_result.customer_id
    runtime_profile = store.user_profiles[str(first_result.profile_id)]
    assert runtime_profile["platform_accounts"] == [
        {"platform": "telegram", "account_id": "telegram-user-strict-1"},
        {"platform": "dingtalk", "account_id": "dingtalk-user-strict-2"},
    ]


def test_customer_access_reuses_existing_identity_profile_instead_of_creating_duplicate(monkeypatch) -> None:
    actor = {
        "id": "platform-admin",
        "email": "admin@workbot.local",
        "role": "super_admin",
        "platform_admin": True,
    }
    created = organization_profile_service.create_profile_tenant(
        current_user=actor,
        name="Identity Reuse",
        description="测试同一客户重复提交时复用既有画像",
    )
    tenant_id = str(created["tenant"]["id"])
    tenant_name = str(created["tenant"]["name"])
    generated_code = str(
        organization_profile_service.generate_profile_tenant_service_registration_code(
            tenant_id=tenant_id,
            current_user=actor,
        )["registration_code"]
    )

    organization_profile_service.upsert_profile(
        current_user=actor,
        profile_id="profile-existing-identity-001",
        changes={
            "tenant_id": tenant_id,
            "tenant_name": tenant_name,
            "customer_id": "customer-existing-identity-001",
            "name": "张三",
            "contact_name": "张三",
            "company_name": "甲方企业",
            "mobile": "13800138000",
            "email": "legacy-identity@external.workbot.local",
            "role": "viewer",
            "status": "active",
            "created_at": "2026-05-05T12:00:00+08:00",
            "last_login": "2026-05-05T12:00:00+08:00",
            "total_interactions": 3,
            "platform_accounts": [{"platform": "dingtalk", "account_id": "legacy-identity-user"}],
            "source_channels": ["dingtalk"],
            "tags": ["平台接待客户"],
            "notes": "预先存在的客户画像。",
            "preferred_language": "zh",
            "identity_mapping_status": "verified",
            "identity_mapping_source": "manual_seed",
            "identity_mapping_confidence": 0.8,
            "last_identity_sync_at": "2026-05-05T12:00:00+08:00",
            "service_status": "active",
        },
        sync_user_state=True,
    )

    monkeypatch.setattr(
        "app.modules.reception.customer_access.service.get_channel_integration_runtime_settings",
        lambda: {
            "wecom": {
                "tenant_id": tenant_id,
                "tenant_name": tenant_name,
            }
        },
    )
    customer_access_service.update_settings(
        UpdateCustomerAccessSettingsRequest(
            tenant_policies=[
                UpdateCustomerAccessTenantPolicyRequest(
                    tenant_id=tenant_id,
                    tenant_name=tenant_name,
                    verification_mode="strict",
                    service_codes=[],
                    enabled=True,
                )
            ]
        )
    )

    message = UnifiedMessage(
        message_id="msg-customer-access-identity-reuse-1",
        channel=ChannelType.WECOM,
        platform_user_id="wecom-identity-user-001",
        chat_id="wecom-chat-identity-001",
        text="\n".join(
            [
                f"服务识别码：{generated_code}",
                "企业名称：甲方企业",
                "用户名称：张三",
                "用户电话号：13800138000",
            ]
        ),
        received_at="2026-05-05T12:30:00+08:00",
        raw_payload={},
    )

    result = customer_access_service.admit_message(message)

    assert result.status == "bound"
    assert result.profile_id == "profile-existing-identity-001"
    assert result.customer_id == "customer-existing-identity-001"
    assert result.service_code == generated_code
    assert "已识别到您已有的服务档案" in str(result.reply_message or "")
    runtime_profile = store.user_profiles["profile-existing-identity-001"]
    assert runtime_profile["service_code"] == generated_code
    assert {"platform": "wecom", "account_id": "wecom-identity-user-001"} in runtime_profile["platform_accounts"]

    tenant_profiles = organization_profile_service.list_profiles(
        current_user=actor,
        tenant_id=tenant_id,
        management_view=True,
    )["items"]
    matched_profiles = [
        item
        for item in tenant_profiles
        if item.get("mobile") == "13800138000" and item.get("contact_name") == "张三"
    ]
    assert len(matched_profiles) == 1


def test_customer_access_historical_service_code_remains_valid_after_rotation(monkeypatch) -> None:
    actor = {
        "id": "platform-admin",
        "email": "admin@workbot.local",
        "role": "super_admin",
        "platform_admin": True,
    }
    created = organization_profile_service.create_profile_tenant(
        current_user=actor,
        name="History Rotation",
        description="测试历史服务识别码继续有效",
    )
    tenant_id = str(created["tenant"]["id"])
    tenant_name = str(created["tenant"]["name"])
    first_code = str(
        organization_profile_service.generate_profile_tenant_service_registration_code(
            tenant_id=tenant_id,
            current_user=actor,
        )["registration_code"]
    )

    monkeypatch.setattr(
        "app.modules.reception.customer_access.service.get_channel_integration_runtime_settings",
        lambda: {
            "telegram": {
                "tenant_id": tenant_id,
                "tenant_name": tenant_name,
            }
        },
    )

    first_message = UnifiedMessage(
        message_id="msg-customer-access-history-1",
        channel=ChannelType.TELEGRAM,
        platform_user_id="telegram-history-user-1",
        chat_id="chat-history-1",
        text="\n".join(
            [
                f"服务识别码：{first_code}",
                "用户名称：历史客户",
                "用户电话号：13800000009",
            ]
        ),
        received_at="2026-04-29T11:00:00+00:00",
        raw_payload={},
    )
    first_result = customer_access_service.admit_message(first_message)
    assert first_result.status == "bound"
    assert first_result.profile_id is not None

    organization_profile_service.delete_profile(
        str(first_result.profile_id),
        current_user=actor,
    )

    rotated_code = str(
        organization_profile_service.generate_profile_tenant_service_registration_code(
            tenant_id=tenant_id,
            current_user=actor,
        )["registration_code"]
    )
    assert rotated_code != first_code

    second_message = UnifiedMessage(
        message_id="msg-customer-access-history-2",
        channel=ChannelType.TELEGRAM,
        platform_user_id="telegram-history-user-2",
        chat_id="chat-history-2",
        text="\n".join(
            [
                f"服务识别码：{first_code}",
                "用户名称：历史客户",
                "用户电话号：13800000009",
            ]
        ),
        received_at="2026-04-29T11:05:00+00:00",
        raw_payload={},
    )
    second_result = customer_access_service.admit_message(second_message)

    assert second_result.status == "bound"
    assert second_result.service_code == first_code
    assert second_result.profile_id is not None
    assert second_result.profile_id != first_result.profile_id


def test_customer_access_replaced_pending_service_code_remains_valid_after_regeneration(monkeypatch) -> None:
    actor = {
        "id": "platform-admin",
        "email": "admin@workbot.local",
        "role": "super_admin",
        "platform_admin": True,
    }
    created = organization_profile_service.create_profile_tenant(
        current_user=actor,
        name="Pending Rotation",
        description="测试替换前的未使用服务识别码仍可继续注册",
    )
    tenant_id = str(created["tenant"]["id"])
    tenant_name = str(created["tenant"]["name"])
    first_code = str(
        organization_profile_service.generate_profile_tenant_service_registration_code(
            tenant_id=tenant_id,
            current_user=actor,
        )["registration_code"]
    )
    second_code = str(
        organization_profile_service.generate_profile_tenant_service_registration_code(
            tenant_id=tenant_id,
            current_user=actor,
        )["registration_code"]
    )
    assert second_code != first_code

    monkeypatch.setattr(
        "app.modules.reception.customer_access.service.get_channel_integration_runtime_settings",
        lambda: {
            "wecom": {
                "tenant_id": tenant_id,
                "tenant_name": tenant_name,
            }
        },
    )

    message = UnifiedMessage(
        message_id="msg-customer-access-pending-history-1",
        channel=ChannelType.WECOM,
        platform_user_id="wecom-pending-history-user-1",
        chat_id="wecom-pending-history-chat-1",
        text="\n".join(
            [
                f"服务识别码：{first_code}",
                "用户名称：张三",
                "用户电话号：13800138000",
            ]
        ),
        received_at="2026-05-05T12:00:00+08:00",
        raw_payload={},
    )

    result = customer_access_service.admit_message(message)

    assert result.status == "bound"
    assert result.service_code == first_code
    assert result.profile_id is not None


def test_customer_access_new_registration_requires_name_and_mobile(monkeypatch) -> None:
    actor = {
        "id": "platform-admin",
        "email": "admin@workbot.local",
        "role": "super_admin",
        "platform_admin": True,
    }
    created = organization_profile_service.create_profile_tenant(
        current_user=actor,
        name="Gamma Access",
        description="测试首次注册字段要求",
    )
    tenant_id = str(created["tenant"]["id"])
    tenant_name = str(created["tenant"]["name"])
    generated_code = str(
        organization_profile_service.generate_profile_tenant_service_registration_code(
            tenant_id=tenant_id,
            current_user=actor,
        )["registration_code"]
    )

    monkeypatch.setattr(
        "app.modules.reception.customer_access.service.get_channel_integration_runtime_settings",
        lambda: {
            "telegram": {
                "tenant_id": tenant_id,
                "tenant_name": tenant_name,
            }
        },
    )

    message = UnifiedMessage(
        message_id="msg-customer-access-gamma-1",
        channel=ChannelType.TELEGRAM,
        platform_user_id="telegram-user-gamma-1",
        chat_id="chat-gamma-1",
        text=f"服务识别码：{generated_code}",
        received_at="2026-04-28T10:20:00+00:00",
        raw_payload={},
    )
    result = customer_access_service.admit_message(message)
    assert result.status == "pending_verification"
    assert result.service_code == generated_code
    assert result.missing_fields == ["contact_name", "mobile"]


def test_customer_access_generated_service_code_is_tenant_isolated(monkeypatch) -> None:
    actor = {
        "id": "platform-admin",
        "email": "admin@workbot.local",
        "role": "super_admin",
        "platform_admin": True,
    }
    tenant_a = organization_profile_service.create_profile_tenant(
        current_user=actor,
        name="Tenant A",
        description="用于租户隔离测试 A",
    )
    tenant_b = organization_profile_service.create_profile_tenant(
        current_user=actor,
        name="Tenant B",
        description="用于租户隔离测试 B",
    )
    tenant_a_id = str(tenant_a["tenant"]["id"])
    tenant_b_id = str(tenant_b["tenant"]["id"])
    tenant_b_name = str(tenant_b["tenant"]["name"])
    tenant_a_code = str(
        organization_profile_service.generate_profile_tenant_service_registration_code(
            tenant_id=tenant_a_id,
            current_user=actor,
        )["registration_code"]
    )

    monkeypatch.setattr(
        "app.modules.reception.customer_access.service.get_channel_integration_runtime_settings",
        lambda: {
            "telegram": {
                "tenant_id": tenant_b_id,
                "tenant_name": tenant_b_name,
            }
        },
    )
    customer_access_service.update_settings(
        UpdateCustomerAccessSettingsRequest(
            tenant_policies=[
                UpdateCustomerAccessTenantPolicyRequest(
                    tenant_id=tenant_b_id,
                    tenant_name=tenant_b_name,
                    verification_mode="strict",
                    service_codes=[],
                    enabled=True,
                )
            ]
        )
    )

    message = UnifiedMessage(
        message_id="msg-customer-access-tenant-isolated-1",
        channel=ChannelType.TELEGRAM,
        platform_user_id="telegram-user-tenant-isolated-1",
        chat_id="chat-tenant-isolated-1",
        text="\n".join(
            [
                "企业名称：隔离企业",
                "联系人姓名：隔离联系人",
                "手机号：13800000003",
                f"服务识别码：{tenant_a_code}",
            ]
        ),
        received_at="2026-04-28T11:00:00+00:00",
        raw_payload={},
    )
    result = customer_access_service.admit_message(message)
    assert result.status == "rejected"
    assert "服务识别码未通过校验" in str(result.reply_message or "")


def test_customer_access_maps_stale_channel_tenant_binding_to_current_catalog(monkeypatch) -> None:
    persistence_service.persist_system_setting(
        key="profile_tenants",
        payload={
            "items": [
                {
                    "id": "tenant-alpha-new",
                    "name": "Alpha Corp",
                    "status": "active",
                    "description": "当前有效租户",
                }
            ],
            "updated_at": "2026-05-05T12:00:00+08:00",
        },
        updated_at="2026-05-05T12:00:00+08:00",
    )

    monkeypatch.setattr(
        "app.modules.reception.customer_access.service.get_channel_integration_runtime_settings",
        lambda: {
            "wecom": {
                "tenant_id": "tenant-alpha-old",
                "tenant_name": "Alpha Corp",
            }
        },
    )
    customer_access_service.update_settings(
        UpdateCustomerAccessSettingsRequest(
            tenant_policies=[
                UpdateCustomerAccessTenantPolicyRequest(
                    tenant_id="tenant-alpha-new",
                    tenant_name="Alpha Corp",
                    verification_mode="strict",
                    service_codes=["SR-TENANT-6C876B-4D65B5-2412B2-933488"],
                    enabled=True,
                )
            ]
        )
    )

    message = UnifiedMessage(
        message_id="msg-customer-access-stale-tenant-binding-1",
        channel=ChannelType.WECOM,
        platform_user_id="wecom-user-tenant-binding-001",
        chat_id="wecom-chat-tenant-binding-001",
        text="\n".join(
            [
                "服务识别码：SR-TENANT-6C876B-4D65B5-2412B2-933488",
                "用户名称：张三",
                "用户电话号：13800138000",
            ]
        ),
        received_at="2026-05-05T12:00:00+08:00",
        raw_payload={},
    )

    result = customer_access_service.admit_message(message)

    assert result.status == "bound"
    assert result.tenant_id == "tenant-alpha-new"
    assert result.tenant_name == "Alpha Corp"
    assert message.metadata == {
        "tenant_id": "tenant-alpha-new",
        "tenant_name": "Alpha Corp",
        "user_profile_id": str(result.profile_id),
        "customer_id": str(result.customer_id),
        "service_code": "SR-TENANT-6C876B-4D65B5-2412B2-933488",
    }
