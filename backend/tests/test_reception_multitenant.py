from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
import httpx

import app.modules.reception.application.message_ingestion_service as message_ingestion_service
import app.modules.reception.agent_entry.hermes_reception_agent_service as hermes_reception_agent_module
from app.db.models import TaskRecord
from app.modules.agent_config.protocol_bindings.schemas import ProtocolBinding
from app.modules.dispatch.requirement_dispatch_agent.service import dispatch_requirement_task
from app.modules.organization.application import profile_service as organization_profile_service
from app.modules.organization.application.memory_service import memory_service
from app.modules.reception.application.message_ingestion_service import (
    _write_hermes_memory_writeback,
    ingest_unified_message,
)
from app.modules.reception.agent_entry.hermes_reception_agent_service import HermesReceptionAgentService
from app.modules.reception.customer_access.service import customer_access_service
from app.modules.reception.customer_access.schemas import (
    CustomerAdmissionResult,
    UpdateCustomerAccessSettingsRequest,
    UpdateCustomerAccessTenantPolicyRequest,
)
from app.modules.reception.schemas.messages import ChannelType, UnifiedMessage
from app.modules.reception.security_monitor.security_gateway_service import security_gateway_service
from app.platform.config.settings_service import DEFAULT_AGENT_API_SETTINGS, update_agent_api_settings
from app.platform.persistence.persistence_service import persistence_service
from app.platform.persistence.persistence_service import StatePersistenceService
from app.platform.persistence.runtime_store import store


def _seed_channel_tenant_binding() -> None:
    payload = {
        "dingtalk": {
            "enabled": True,
            "tenant_id": "tenant-alpha",
            "tenant_name": "Alpha Corp",
        }
    }
    store.system_settings["channel_integrations"] = payload
    persistence_service.persist_system_setting(
        key="channel_integrations",
        payload=payload,
        updated_at=store.now_string(),
    )


def _build_message(text: str) -> UnifiedMessage:
    return UnifiedMessage(
        message_id="msg-001",
        channel=ChannelType.DINGTALK,
        platform_user_id="ding-user-001",
        chat_id="chat-001",
        text=text,
        received_at="2026-04-27T10:00:00+08:00",
        raw_payload={},
        metadata={},
    )


def _reset_customer_access_settings() -> None:
    customer_access_service.update_settings(UpdateCustomerAccessSettingsRequest(tenant_policies=[]))


def _seed_bound_profile() -> None:
    store.user_profiles["profile-alpha-001"] = {
        "id": "profile-alpha-001",
        "tenant_id": "tenant-alpha",
        "tenant_name": "Alpha Corp",
        "customer_id": "customer-alpha-001",
        "company_name": "甲方企业",
        "contact_name": "张三",
        "mobile": "13800138000",
        "service_status": "active",
        "tags": ["平台接待客户"],
    }


def _enable_image_ocr_provider() -> None:
    settings_payload = deepcopy(DEFAULT_AGENT_API_SETTINGS)
    settings_payload["providers"]["openai"]["enabled"] = True
    settings_payload["providers"]["openai"]["base_url"] = "https://api.openai.com/v1"
    settings_payload["providers"]["openai"]["model"] = "gpt-5.4"
    settings_payload["providers"]["openai"]["endpoint_path"] = "/responses"
    settings_payload["providers"]["openai"]["api_key"] = "sk-test-ocr"
    update_agent_api_settings(settings_payload)


def _mock_bound_customer_access(message: UnifiedMessage) -> CustomerAdmissionResult:
    message.metadata["tenant_id"] = "tenant-alpha"
    message.metadata["tenant_name"] = "Alpha Corp"
    message.metadata["customer_id"] = "customer-alpha-001"
    message.metadata["user_profile_id"] = "profile-alpha-001"
    return CustomerAdmissionResult(
        status="bound",
        tenant_id="tenant-alpha",
        tenant_name="Alpha Corp",
        customer_id="customer-alpha-001",
        profile_id="profile-alpha-001",
        service_code="SC-ALPHA-001",
    )


def _mock_memory_ingest(**_: object) -> dict[str, object]:
    return {
        "auto_distilled_sessions": [],
        "auto_weekly_distilled": False,
        "distill_recommended": False,
    }


def _mock_memory_retrieve(**_: object) -> dict[str, object]:
    return {
        "items": [],
        "total": 0,
    }


def _mock_security_inspector(
    text: str,
    user_key: str,
    auth_scope: str,
    direction: str = "input",
    trace_id: str | None = None,
) -> dict[str, object]:
    blocked = direction == "output" and user_key.startswith("hermes:") and "泄露" in text
    return {
        "allowed": not blocked,
        "user_key": user_key,
        "sanitized_text": text,
        "detail": "mocked hermes result blocked" if blocked else "",
        "status_code": 403 if blocked else 200,
        "trace_id": trace_id or "trace-reception-001",
        "warnings": [],
        "prompt_injection_assessment": {},
        "rewrite_diffs": [],
        "security_verdict": {"layer": "mock_security"},
        "auth_scope": auth_scope,
    }


def test_customer_access_returns_pending_template_for_unbound_customer() -> None:
    _reset_customer_access_settings()
    _seed_channel_tenant_binding()
    message = _build_message("你好")

    result = customer_access_service.admit_message(message)

    assert result.status in {"pending_verification", "rejected"}
    assert any(keyword in str(result.reply_message or "") for keyword in ("服务识别码", "未通过校验"))
    assert result.tenant_id


def test_customer_access_binds_customer_after_template_submission() -> None:
    _reset_customer_access_settings()
    _seed_channel_tenant_binding()
    actor = {
        "id": "platform-admin",
        "email": "admin@workbot.local",
        "role": "super_admin",
        "platform_admin": True,
    }
    created = organization_profile_service.create_profile_tenant(
        current_user=actor,
        name="Alpha Corp",
        description="接待层多租户测试",
    )
    tenant_id = str(created["tenant"]["id"])
    registration_code = str(
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
                    tenant_name="Alpha Corp",
                    verification_mode="strict",
                    service_codes=[],
                    enabled=True,
                )
            ]
        )
    )
    message = _build_message(
        "\n".join(
            [
                "用户名称：张三",
                "用户电话号：13800138000",
                f"服务识别码：{registration_code}",
            ]
        )
    )

    result = customer_access_service.admit_message(message)

    if result.status == "bound":
        assert result.profile_id
        assert result.customer_id
        assert message.metadata["tenant_id"] == result.tenant_id
        assert message.metadata["customer_id"] == result.customer_id
        assert result.service_code
    else:
        assert result.status == "rejected"


def test_hermes_protocol_payload_includes_platform_memory_and_customer_context() -> None:
    store.user_profiles["profile-alpha-001"] = {
        "id": "profile-alpha-001",
        "tenant_id": "tenant-alpha",
        "tenant_name": "Alpha Corp",
        "customer_id": "customer-alpha-001",
        "company_name": "甲方企业",
        "contact_name": "张三",
        "mobile": "13800138000",
        "service_status": "active",
        "tags": ["平台接待客户", "高价值"],
    }

    memory_service.write_long_term_memory(
        memory_type="tenant_soul",
        content="你是 Alpha Corp 的接待智能体，需要先确认需求，再给出下一步建议。",
        summary="你是 Alpha Corp 的接待智能体，需要先确认需求，再给出下一步建议。",
        scope={"tenant_id": "tenant-alpha"},
        subject_type="tenant",
        subject_id="tenant-alpha",
    )
    memory_service.write_long_term_memory(
        memory_type="customer_preference",
        content="该客户偏好中文回复，并希望方案先给结论再展开。",
        summary="客户偏好中文回复，并希望方案先给结论再展开。",
        scope={"tenant_id": "tenant-alpha"},
        subject_id="customer-alpha-001",
    )

    binding = ProtocolBinding(
        binding_id="binding-alpha",
        tenant_id="tenant-alpha",
        agent_id="hermes-reception-v1",
        protocol_id="tenant_reception_protocol",
        protocol_version="v1",
        metadata={"request_mode": "protocol"},
    )
    message = UnifiedMessage(
        message_id="msg-hermes-001",
        channel=ChannelType.DINGTALK,
        platform_user_id="ding-user-001",
        chat_id="chat-001",
        text="你好，我们想咨询产品方案",
        received_at="2026-04-27T10:00:00+08:00",
        raw_payload={},
        metadata={
            "tenant_id": "tenant-alpha",
            "customer_id": "customer-alpha-001",
            "user_profile_id": "profile-alpha-001",
        },
        session_id="session-001",
        detected_lang="zh",
    )

    payload = HermesReceptionAgentService()._build_protocol_payload(
        binding_metadata=binding.metadata,
        binding=binding,
        agent={"id": "hermes-reception-v1"},
        message=message,
    )

    assert payload["customerId"] == "profile-alpha-001"
    assert payload["profileId"] == "profile-alpha-001"
    assert payload["tenantSoul"] == "你是 Alpha Corp 的接待智能体，需要先确认需求，再给出下一步建议。"
    assert payload["customerContext"]["companyName"] == "甲方企业"
    assert payload["customerContext"]["contactName"] == "张三"
    assert payload["retrievedLongTermMemories"]
    assert payload["retrievedLongTermMemories"][0]["memoryType"] == "customer_preference"
    assert payload["runtimeMemoryMode"] == "platform_stateless"


def test_hermes_protocol_payload_uses_profile_memory_when_platform_memory_is_empty() -> None:
    store.user_profiles["profile-alpha-002"] = {
        "id": "profile-alpha-002",
        "tenant_id": "tenant-alpha",
        "tenant_name": "Alpha Corp",
        "customer_id": "customer-alpha-002",
        "company_name": "甲方企业二部",
        "contact_name": "李四",
        "mobile": "13800138001",
        "service_status": "active",
        "profile_summary": "甲方企业二部联系人李四，最近关注交付排期与官网改版。",
        "preferences": ["希望先看交付排期", "偏好中文沟通"],
        "business_background": ["计划做官网改版并补齐客户接待链路"],
        "decision_history": ["确定先做官网首页与接待入口"],
        "tags": ["平台接待客户"],
    }

    binding = ProtocolBinding(
        binding_id="binding-alpha-profile",
        tenant_id="tenant-alpha",
        agent_id="hermes-reception-v1",
        protocol_id="tenant_reception_protocol",
        protocol_version="v1",
        metadata={"request_mode": "protocol"},
    )
    message = UnifiedMessage(
        message_id="msg-hermes-profile-001",
        channel=ChannelType.DINGTALK,
        platform_user_id="ding-user-002",
        chat_id="chat-002",
        text="你好，我们这边要做官网改版，希望先看交付排期",
        received_at="2026-04-27T10:10:00+08:00",
        raw_payload={},
        metadata={
            "tenant_id": "tenant-alpha",
            "customer_id": "customer-alpha-002",
            "user_profile_id": "profile-alpha-002",
        },
        session_id="session-002",
        detected_lang="zh",
    )

    payload = HermesReceptionAgentService()._build_protocol_payload(
        binding_metadata=binding.metadata,
        binding=binding,
        agent={"id": "hermes-reception-v1"},
        message=message,
    )

    assert payload["customerContext"]["profileSummary"] == "甲方企业二部联系人李四，最近关注交付排期与官网改版。"
    assert payload["customerContext"]["preferences"] == ["希望先看交付排期", "偏好中文沟通"]
    assert any(item["memoryType"] == "profile_summary" for item in payload["retrievedLongTermMemories"])
    assert any(item["memoryType"] == "customer_preference" for item in payload["retrievedLongTermMemories"])


def test_hermes_reply_uses_profile_id_for_header_and_protocol_customer_id(monkeypatch) -> None:
    _seed_bound_profile()
    message = UnifiedMessage(
        message_id="msg-hermes-header-001",
        channel=ChannelType.DINGTALK,
        platform_user_id="ding-user-header-001",
        chat_id="chat-header-001",
        text="你好，帮我确认一下接待策略",
        received_at="2026-04-27T10:30:00+08:00",
        raw_payload={},
        metadata={
            "tenant_id": "tenant-alpha",
            "customer_id": "customer-alpha-001",
            "user_profile_id": "profile-alpha-001",
        },
        session_id="session-header-001",
        detected_lang="zh",
    )
    binding = ProtocolBinding(
        binding_id="binding-header-001",
        tenant_id="tenant-alpha",
        agent_id="hermes-reception-v1",
        protocol_id="tenant_reception_protocol",
        protocol_version="v1",
        metadata={"request_mode": "protocol"},
    )

    monkeypatch.setattr(
        memory_service,
        "retrieve",
        lambda **_: {"items": [], "total": 0},
    )
    monkeypatch.setattr(
        memory_service,
        "list_long_term_memories",
        lambda **_: {"items": []},
    )

    captured: dict[str, object] = {}

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "request_id": "reception:msg-hermes-header-001",
                "reply_text": "已确认接待策略。",
                "interaction_mode": "chat",
                "task_signal": "stay_in_reception",
                "memory_writeback": [],
                "metadata": {},
            }

    class _FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def post(self, url: str, headers: dict[str, str], json: dict[str, object]) -> _FakeResponse:
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _FakeResponse()

    service = HermesReceptionAgentService()
    monkeypatch.setattr(
        service,
        "_resolve_agent",
        lambda: {
            "id": "hermes-reception-v1",
            "name": "Hermes Reception",
            "config_summary": {
                "invocation": {
                    "base_url": "http://hermes.local",
                    "invoke_path": "/v1/chat/completions",
                }
            },
        },
    )
    monkeypatch.setattr(hermes_reception_agent_module, "get_protocol_binding", lambda **_: binding)
    monkeypatch.setattr(hermes_reception_agent_module.httpx, "Client", _FakeClient)

    result = service.reply(message=message)

    assert result["reply_text"] == "已确认接待策略。"
    assert captured["url"] == "http://hermes.local/v1/chat/completions"
    assert captured["headers"]["X-Hermes-Customer-Id"] == "profile-alpha-001"
    assert captured["json"]["customerId"] == "profile-alpha-001"
    assert captured["json"]["profileId"] == "profile-alpha-001"


def test_hermes_memory_writeback_persists_long_term_memory() -> None:
    message = UnifiedMessage(
        message_id="msg-hermes-memory-001",
        channel=ChannelType.DINGTALK,
        platform_user_id="ding-user-001",
        chat_id="chat-001",
        text="我们更关注交付周期",
        received_at="2026-04-27T10:00:00+08:00",
        raw_payload={},
        metadata={
            "tenant_id": "tenant-alpha",
            "customer_id": "customer-alpha-001",
            "task_id": "task-alpha-001",
        },
        session_id="session-001",
        detected_lang="zh",
    )

    saved_count, warnings = _write_hermes_memory_writeback(
        message=message,
        hermes_result={
            "memory_writeback": [
                {
                    "scope": "customer",
                    "memory_type": "customer_preference",
                    "summary": "客户更关注交付周期，希望先给出时间计划。",
                    "title": "客户偏好",
                },
                {
                    "scope": "task_summary",
                    "memory_type": "task_result",
                    "summary": "本轮接待已澄清客户核心关注点为交付周期。",
                },
            ]
        },
    )

    assert saved_count == 2
    assert warnings == []

    customer_memories = memory_service.list_long_term_memories(
        scope={"tenant_id": "tenant-alpha"},
        subject_id="customer-alpha-001",
        subject_type="customer",
        limit=10,
        memory_scope="tenant",
    )
    task_memories = memory_service.list_long_term_memories(
        scope={"tenant_id": "tenant-alpha"},
        subject_id="task-alpha-001",
        subject_type="task_summary",
        limit=10,
        memory_scope="tenant",
    )

    assert any(item["memory_type"] == "customer_preference" for item in customer_memories["items"])
    assert any(item["memory_type"] == "task_result" for item in task_memories["items"])


def test_hermes_protocol_response_normalizes_json_text_payload() -> None:
    service = HermesReceptionAgentService()

    protocol_response = service._normalize_protocol_response(
        endpoint_path="/v1/chat/completions",
        request_id="req-structured-001",
        payload={
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "request_id": "req-structured-001",
                                "reply_text": "已记录您的关注点，我先补充交付排期建议。",
                                "interaction_mode": "task",
                                "task_signal": "dispatch_task",
                                "requirement_payload": {
                                    "summary": "需要补充交付排期建议",
                                    "details": "客户想优先了解交付时间与里程碑。",
                                },
                                "memory_writeback": [
                                    {
                                        "scope": "customer",
                                        "memory_type": "customer_preference",
                                        "summary": "客户希望优先了解交付排期。",
                                    }
                                ],
                            },
                            ensure_ascii=False,
                        ),
                    }
                }
            ]
        },
    )

    assert protocol_response.request_id == "req-structured-001"
    assert protocol_response.reply_text == "已记录您的关注点，我先补充交付排期建议。"
    assert protocol_response.interaction_mode == "task"
    assert protocol_response.task_signal == "dispatch_task"
    assert protocol_response.requirement_payload is not None
    assert protocol_response.requirement_payload.summary == "需要补充交付排期建议"
    assert len(protocol_response.memory_writeback) == 1
    assert protocol_response.memory_writeback[0].memory_type == "customer_preference"


def test_hermes_protocol_response_infers_task_mode_from_legacy_task_signal() -> None:
    service = HermesReceptionAgentService()

    protocol_response = service._normalize_protocol_response(
        endpoint_path="/v1/chat/completions",
        request_id="req-legacy-001",
        payload={
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "request_id": "req-legacy-001",
                                "reply_text": "我先登记这个需求。",
                                "task_signal": "dispatch_task",
                            },
                            ensure_ascii=False,
                        ),
                    }
                }
            ]
        },
    )

    assert protocol_response.request_id == "req-legacy-001"
    assert protocol_response.interaction_mode == "task"


def test_hermes_protocol_response_coerces_legacy_handoff_human_to_dispatch_task() -> None:
    service = HermesReceptionAgentService()

    protocol_response = service._normalize_protocol_response(
        endpoint_path="/v1/chat/completions",
        request_id="req-legacy-human-001",
        payload={
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "request_id": "req-legacy-human-001",
                                "reply_text": "我先把这个需求登记下来。",
                                "task_signal": "handoff_human",
                            },
                            ensure_ascii=False,
                        ),
                    }
                }
            ]
        },
    )

    assert protocol_response.request_id == "req-legacy-human-001"
    assert protocol_response.interaction_mode == "task"
    assert protocol_response.task_signal == "dispatch_task"


def test_hermes_protocol_response_coerces_structured_requirement_details() -> None:
    service = HermesReceptionAgentService()

    structured_details = {
        "provided_info": {
            "service_code": "SR-TENANT-001",
            "contact_name": "卢雨",
        },
        "missing_info": ["预算范围", "期望上线时间"],
    }
    protocol_response = service._normalize_protocol_response(
        endpoint_path="/v1/chat/completions",
        request_id="req-structured-details-001",
        payload={
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "request_id": "req-structured-details-001",
                                "reply_text": "我先帮您登记信息，再继续接待。",
                                "interaction_mode": "task",
                                "task_signal": "dispatch_task",
                                "requirement_payload": {
                                    "summary": "已识别客户提交注册信息",
                                    "details": structured_details,
                                },
                            },
                            ensure_ascii=False,
                        ),
                    }
                }
            ]
        },
    )

    assert protocol_response.requirement_payload is not None
    assert protocol_response.requirement_payload.details == json.dumps(structured_details, ensure_ascii=False)
    assert protocol_response.requirement_payload.metadata["raw_fields"]["details"] == structured_details
    assert protocol_response.task_signal == "dispatch_task"


def test_ingest_unified_message_creates_pending_task_from_hermes_result(monkeypatch) -> None:
    _seed_channel_tenant_binding()
    _seed_bound_profile()
    message = _build_message("我们要做一个新的门户网站")
    before_task_ids = {str(task.get("id") or "").strip() for task in store.tasks}

    monkeypatch.setattr(customer_access_service, "admit_message", _mock_bound_customer_access)
    monkeypatch.setattr(memory_service, "ingest_message", _mock_memory_ingest)
    monkeypatch.setattr(memory_service, "retrieve", _mock_memory_retrieve)
    monkeypatch.setattr(
        security_gateway_service,
        "inspect_text_entrypoint_snapshot",
        _mock_security_inspector,
    )
    monkeypatch.setattr(message_ingestion_service, "_attach_active_task_context", lambda message: None)
    monkeypatch.setattr(
        message_ingestion_service.hermes_reception_agent_service,
        "reply",
        lambda *, message: {
            "request_id": "req-task-001",
            "reply_text": "已收到，我先为您登记需求并进入待分发。",
            "interaction_mode": "task",
            "task_signal": "dispatch_task",
            "intent": "reception_task",
            "requirement_payload": {
                "summary": "开发新的门户网站",
                "details": "需要支持对外展示与客户接待。",
            },
            "memory_writeback": [],
        },
    )

    result = ingest_unified_message(message, auth_scope="messages:ingest")

    assert result["entrypoint"] == "master_bot.reception"
    assert result["interaction_mode"] == "task"
    assert result["reception_mode"] == "task_handoff"
    assert result["task_id"] is not None
    after_task_ids = {str(task.get("id") or "").strip() for task in store.tasks}
    created_task_ids = after_task_ids - before_task_ids
    assert created_task_ids == {str(result["task_id"])}
    created_task = next(task for task in store.tasks if str(task.get("id") or "").strip() == str(result["task_id"]))
    assert created_task["status"] == "pending"
    assert created_task["workflow_run_id"] is None
    assert created_task["title"] == "开发新的门户网站"
    assert created_task["requirement_payload"]["summary"] == "开发新的门户网站"
    assert created_task["description"] == "开发新的门户网站\n\n需要支持对外展示与客户接待。"
    assert created_task["manager_packet"]["manager_action"] == "development_group_provisioned"
    assert created_task["manager_packet"]["session_state"] == "development_group_ready"
    assert created_task["brain_dispatch_summary"]["execution_topology"] == "single_agent"
    assert created_task["route_decision"]["execution_plan"]["plan_type"] == "single_path"
    assert len(created_task["route_decision"]["execution_plan"]["steps"]) == 1
    group_id = str(created_task["state_machine"]["development_group_id"])
    provisioned_agents = [
        agent
        for agent in store.agents
        if str((agent.get("config_snapshot") or {}).get("runtime", {}).get("agent_metadata", {}).get("metadata", {}).get("group_id") or "") == group_id
    ]
    assert len(provisioned_agents) == 2
    assert all(agent.get("enabled") is False for agent in provisioned_agents)
    assert store.system_settings["dispatch.requirement_dispatch_agent.groups"]["items"][0]["id"] == group_id


def test_ingest_unified_message_task_mode_coerces_stay_in_reception_signal_and_persists_tenant_scope(
    monkeypatch,
) -> None:
    _seed_channel_tenant_binding()
    _seed_bound_profile()
    message = _build_message("帮我整理一个新的官网方案")

    monkeypatch.setattr(customer_access_service, "admit_message", _mock_bound_customer_access)
    monkeypatch.setattr(memory_service, "ingest_message", _mock_memory_ingest)
    monkeypatch.setattr(memory_service, "retrieve", _mock_memory_retrieve)
    monkeypatch.setattr(
        security_gateway_service,
        "inspect_text_entrypoint_snapshot",
        _mock_security_inspector,
    )
    monkeypatch.setattr(message_ingestion_service, "_attach_active_task_context", lambda message: None)
    monkeypatch.setattr(
        message_ingestion_service.hermes_reception_agent_service,
        "reply",
        lambda *, message: {
            "request_id": "req-task-002",
            "reply_text": "已收到，我先按需求任务登记。",
            "interaction_mode": "task",
            "task_signal": "stay_in_reception",
            "intent": "reception_task",
            "requirement_payload": {
                "summary": "官网方案需求",
                "details": "需要整理目标、结构与预算建议。",
            },
            "memory_writeback": [],
        },
    )

    result = ingest_unified_message(message, auth_scope="messages:ingest")

    assert result["interaction_mode"] == "task"
    assert result["reception_mode"] == "task_handoff"
    assert result["task_id"] is not None

    created_task = next(task for task in store.tasks if str(task.get("id") or "") == str(result["task_id"]))
    persisted_route_decision = StatePersistenceService._task_route_decision_record(created_task)
    persisted_row = TaskRecord(
        id=str(created_task["id"]),
        sort_index=0,
        title=str(created_task["title"]),
        description=str(
            StatePersistenceService._encrypt_text_payload(str(created_task["description"]))
        ),
        status=str(created_task["status"]),
        priority=str(created_task["priority"]),
        created_at=str(created_task["created_at"]),
        completed_at=created_task.get("completed_at"),
        agent=str(created_task["agent"]),
        tokens=int(created_task.get("tokens", 0)),
        duration=created_task.get("duration"),
        workflow_id=created_task.get("workflow_id"),
        workflow_run_id=created_task.get("workflow_run_id"),
        trace_id=created_task.get("trace_id"),
        channel=created_task.get("channel"),
        session_id=created_task.get("session_id"),
        user_key=created_task.get("user_key"),
        preferred_language=created_task.get("preferred_language"),
        detected_lang=created_task.get("detected_lang"),
        route_decision=persisted_route_decision,
        result=StatePersistenceService._encrypt_json_payload(created_task.get("result")),
    )
    restored_task = StatePersistenceService._task_record_to_payload(persisted_row)

    assert restored_task["tenant_id"] == "tenant-alpha"
    assert restored_task["tenant_name"] == "Alpha Corp"
    assert restored_task["manager_packet"]["manager_action"] == "development_group_provisioned"
    assert restored_task["manager_packet"]["session_state"] == "development_group_ready"
    assert restored_task["brain_dispatch_summary"]["execution_topology"] == "single_agent"
    assert restored_task["requirement_payload"]["summary"] == "官网方案需求"

    route_decision = result.get("route_decision") or {}
    assert route_decision.get("hermes_task_signal") == "dispatch_task"


def test_requirement_dispatch_is_idempotent_for_existing_task(monkeypatch) -> None:
    _seed_channel_tenant_binding()
    _seed_bound_profile()
    message = _build_message("帮我做一个官网 HTML 页面方案")

    monkeypatch.setattr(customer_access_service, "admit_message", _mock_bound_customer_access)
    monkeypatch.setattr(memory_service, "ingest_message", _mock_memory_ingest)
    monkeypatch.setattr(memory_service, "retrieve", _mock_memory_retrieve)
    monkeypatch.setattr(
        security_gateway_service,
        "inspect_text_entrypoint_snapshot",
        _mock_security_inspector,
    )
    monkeypatch.setattr(message_ingestion_service, "_attach_active_task_context", lambda message: None)
    monkeypatch.setattr(
        message_ingestion_service.hermes_reception_agent_service,
        "reply",
        lambda *, message: {
            "request_id": "req-task-003",
            "reply_text": "已收到，我先为您登记需求。",
            "interaction_mode": "task",
            "task_signal": "dispatch_task",
            "intent": "reception_task",
            "requirement_payload": {
                "summary": "官网 HTML 页面方案",
                "details": "需要先给出页面结构和交付思路。",
            },
            "memory_writeback": [],
        },
    )

    result = ingest_unified_message(message, auth_scope="messages:ingest")
    task_id = str(result["task_id"])
    task = next(task for task in store.tasks if str(task.get("id") or "") == task_id)
    group_id = str(task["state_machine"]["development_group_id"])
    first_agent_ids = sorted(
        str(agent.get("id") or "")
        for agent in store.agents
        if str((agent.get("config_snapshot") or {}).get("runtime", {}).get("agent_metadata", {}).get("metadata", {}).get("group_id") or "") == group_id
    )

    replay = dispatch_requirement_task(task_id, trigger="test_replay")

    assert replay["ok"] is True
    replay_task = replay["task"]
    assert replay_task["manager_packet"]["manager_action"] == "development_group_provisioned"
    second_agent_ids = sorted(
        str(agent.get("id") or "")
        for agent in store.agents
        if str((agent.get("config_snapshot") or {}).get("runtime", {}).get("agent_metadata", {}).get("metadata", {}).get("group_id") or "") == group_id
    )
    assert second_agent_ids == first_agent_ids


def test_ingest_unified_message_coerces_legacy_handoff_human_into_dispatch_task(monkeypatch) -> None:
    _seed_channel_tenant_binding()
    _seed_bound_profile()
    message = _build_message("我们有一个新需求要登记")
    before_task_ids = {str(task.get("id") or "").strip() for task in store.tasks}

    monkeypatch.setattr(customer_access_service, "admit_message", _mock_bound_customer_access)
    monkeypatch.setattr(memory_service, "ingest_message", _mock_memory_ingest)
    monkeypatch.setattr(memory_service, "retrieve", _mock_memory_retrieve)
    monkeypatch.setattr(
        security_gateway_service,
        "inspect_text_entrypoint_snapshot",
        _mock_security_inspector,
    )
    monkeypatch.setattr(message_ingestion_service, "_attach_active_task_context", lambda message: None)
    monkeypatch.setattr(
        message_ingestion_service.hermes_reception_agent_service,
        "reply",
        lambda *, message: {
            "request_id": "req-task-legacy-human-001",
            "reply_text": "已收到，我先登记为待分发需求。",
            "interaction_mode": "task",
            "task_signal": "handoff_human",
            "intent": "reception_task",
            "requirement_payload": {
                "summary": "登记新的门户网站需求",
                "details": "需要先进入平台任务中心等待后续分发。",
            },
            "memory_writeback": [],
        },
    )

    result = ingest_unified_message(message, auth_scope="messages:ingest")

    assert result["entrypoint"] == "master_bot.reception"
    assert result["interaction_mode"] == "task"
    assert result["reception_mode"] == "task_handoff"
    created_task_ids = {str(task.get("id") or "").strip() for task in store.tasks} - before_task_ids
    assert created_task_ids == {str(result["task_id"])}
    created_task = next(task for task in store.tasks if str(task.get("id") or "").strip() == str(result["task_id"]))
    assert created_task["status"] == "pending"
    assert created_task["manager_packet"]["manager_action"] == "development_group_provisioned"
    assert created_task["manager_packet"]["session_state"] == "development_group_ready"
    assert created_task["brain_dispatch_summary"]["execution_topology"] == "single_agent"
    assert created_task["state_machine"]["development_group_id"]
    assert created_task["agent"]


def test_ingest_unified_message_keeps_original_identity_fields_for_customer_access(monkeypatch) -> None:
    _reset_customer_access_settings()
    actor = {
        "id": "platform-admin",
        "email": "admin@workbot.local",
        "role": "super_admin",
        "platform_admin": True,
    }
    created = organization_profile_service.create_profile_tenant(
        current_user=actor,
        name="Identity Corp",
        description="客户准入身份字段测试",
    )
    tenant_id = str(created["tenant"]["id"])
    tenant_name = str(created["tenant"]["name"])
    registration_code = str(
        organization_profile_service.generate_profile_tenant_service_registration_code(
            tenant_id=tenant_id,
            current_user=actor,
        )["registration_code"]
    )
    channel_payload = {
        "dingtalk": {
            "enabled": True,
            "tenant_id": tenant_id,
            "tenant_name": tenant_name,
        }
    }
    store.system_settings["channel_integrations"] = channel_payload
    persistence_service.persist_system_setting(
        key="channel_integrations",
        payload=channel_payload,
        updated_at=store.now_string(),
    )

    message = _build_message(
        "\n".join(
            [
                f"1. 服务识别码：{registration_code}",
                "2. 用户名称：卢雨",
                "3. 用户电话号：15576043511",
            ]
        )
    )

    def _security_redacts_phone(
        text: str,
        user_key: str,
        auth_scope: str,
        direction: str = "input",
    ) -> dict[str, object]:
        return {
            "allowed": True,
            "user_key": user_key,
            "sanitized_text": text.replace("15576043511", "[REDACTED_PHONE]"),
            "detail": "",
            "status_code": 200,
            "trace_id": "trace-customer-access-identity",
            "warnings": ["Detected and redacted phone number"],
            "prompt_injection_assessment": {},
            "rewrite_diffs": [
                {
                    "type": "redaction",
                    "match": "15576043511",
                    "replacement": "[REDACTED_PHONE]",
                }
            ],
            "security_verdict": {"layer": "mock_security"},
            "auth_scope": auth_scope,
        }

    monkeypatch.setattr(
        security_gateway_service,
        "inspect_text_entrypoint_snapshot",
        _security_redacts_phone,
    )
    monkeypatch.setattr(memory_service, "ingest_message", _mock_memory_ingest)
    monkeypatch.setattr(memory_service, "retrieve", _mock_memory_retrieve)
    monkeypatch.setattr(message_ingestion_service, "_attach_active_task_context", lambda message: None)
    monkeypatch.setattr(
        message_ingestion_service.hermes_reception_agent_service,
        "reply",
        lambda *, message: {
            "request_id": "req-customer-access-identity-001",
            "reply_text": "已完成身份确认，请继续描述您的需求。",
            "interaction_mode": "chat",
            "task_signal": "stay_in_reception",
            "intent": "reception_chat",
            "memory_writeback": [],
        },
    )

    result = ingest_unified_message(message, auth_scope="messages:ingest")

    assert result["entrypoint"] == "master_bot.customer_access"
    assert result["interaction_mode"] == "chat"
    assert result["reception_mode"] == "customer_access"
    assert "已为您完成登记并绑定平台服务" in result["message"]
    profile_id = str(message.metadata.get("user_profile_id") or "")
    assert profile_id
    profile = organization_profile_service.get_profile(profile_id, current_user=actor)
    assert profile["contact_name"] == "卢雨"
    assert profile["mobile"] == "15576043511"
    assert profile["service_code"] == registration_code
    assert "[REDACTED_PHONE]" in result["unified_message"]["text"]


def test_ingest_unified_message_short_circuits_bound_customer_access_reply(monkeypatch) -> None:
    _seed_channel_tenant_binding()
    message = _build_message(
        "\n".join(
            [
                "服务识别码：SR-TENANT-6C876B-4D65B5-2412B2-933488",
                "用户名称：张三",
                "用户电话号：13800138000",
            ]
        )
    )
    before_task_ids = {str(task.get("id") or "").strip() for task in store.tasks}

    def _mock_bound_with_reply(message: UnifiedMessage) -> CustomerAdmissionResult:
        message.metadata["tenant_id"] = "tenant-alpha"
        message.metadata["tenant_name"] = "Alpha Corp"
        message.metadata["customer_id"] = "customer-alpha-001"
        message.metadata["user_profile_id"] = "profile-alpha-001"
        message.metadata["service_code"] = "SR-TENANT-6C876B-4D65B5-2412B2-933488"
        return CustomerAdmissionResult(
            status="bound",
            tenant_id="tenant-alpha",
            tenant_name="Alpha Corp",
            customer_id="customer-alpha-001",
            profile_id="profile-alpha-001",
            service_code="SR-TENANT-6C876B-4D65B5-2412B2-933488",
            reply_message="张三，已为您完成登记并绑定平台服务。\n当前归属：Alpha Corp。",
        )

    monkeypatch.setattr(customer_access_service, "admit_message", _mock_bound_with_reply)
    monkeypatch.setattr(
        security_gateway_service,
        "inspect_text_entrypoint_snapshot",
        _mock_security_inspector,
    )
    monkeypatch.setattr(
        message_ingestion_service.hermes_reception_agent_service,
        "reply",
        lambda **_: (_ for _ in ()).throw(AssertionError("Hermes should not be called for bind reply")),
    )

    result = ingest_unified_message(message, auth_scope="messages:ingest")

    assert result["entrypoint"] == "master_bot.customer_access"
    assert result["interaction_mode"] == "chat"
    assert result["reception_mode"] == "customer_access"
    assert "已为您完成登记并绑定平台服务" in result["message"]
    assert result["unified_message"]["metadata"]["user_profile_id"] == "profile-alpha-001"
    after_task_ids = {str(task.get("id") or "").strip() for task in store.tasks}
    assert after_task_ids == before_task_ids


def test_ingest_unified_message_writes_back_profile_memory(monkeypatch) -> None:
    _seed_channel_tenant_binding()
    _seed_bound_profile()
    message = _build_message("我们要做官网改版，希望先给交付排期，我们更关注交付周期。")

    monkeypatch.setattr(customer_access_service, "admit_message", _mock_bound_customer_access)
    monkeypatch.setattr(memory_service, "ingest_message", _mock_memory_ingest)
    monkeypatch.setattr(memory_service, "retrieve", _mock_memory_retrieve)
    monkeypatch.setattr(
        security_gateway_service,
        "inspect_text_entrypoint_snapshot",
        _mock_security_inspector,
    )
    monkeypatch.setattr(message_ingestion_service, "_attach_active_task_context", lambda message: None)
    monkeypatch.setattr(
        message_ingestion_service.hermes_reception_agent_service,
        "reply",
        lambda *, message: {
            "request_id": "req-profile-writeback-001",
            "reply_text": "已收到，我先为您整理官网改版需求。",
            "interaction_mode": "task",
            "task_signal": "dispatch_task",
            "requirement_payload": {
                "summary": "官网改版需求",
                "details": "客户希望优先看到交付排期，并确定先做官网首页和接待入口。",
            },
            "memory_writeback": [],
        },
    )

    result = ingest_unified_message(message, auth_scope="messages:ingest")

    assert result["interaction_mode"] == "task"
    profile = organization_profile_service.get_profile(
        "profile-alpha-001",
        current_user={
            "id": "platform-admin",
            "email": "admin@workbot.local",
            "role": "super_admin",
            "platform_admin": True,
        },
    )
    assert profile["last_reception_at"] == "2026-04-27T10:00:00+08:00"
    assert any("交付排期" in item for item in profile["preferences"])
    assert any("官网改版需求" in item or "官网改版" in item for item in profile["business_background"])
    assert any("先做官网首页" in item for item in profile["decision_history"])
    assert "长期需求背景" in str(profile["profile_summary"] or "")


def test_ingest_unified_message_blocks_risky_hermes_result(monkeypatch) -> None:
    _seed_channel_tenant_binding()
    _seed_bound_profile()
    message = _build_message("请先帮我看看方案")
    before_task_ids = {str(task.get("id") or "").strip() for task in store.tasks}

    monkeypatch.setattr(customer_access_service, "admit_message", _mock_bound_customer_access)
    monkeypatch.setattr(memory_service, "ingest_message", _mock_memory_ingest)
    monkeypatch.setattr(memory_service, "retrieve", _mock_memory_retrieve)
    monkeypatch.setattr(
        security_gateway_service,
        "inspect_text_entrypoint_snapshot",
        _mock_security_inspector,
    )
    monkeypatch.setattr(message_ingestion_service, "_attach_active_task_context", lambda message: None)
    monkeypatch.setattr(
        message_ingestion_service.hermes_reception_agent_service,
        "reply",
        lambda *, message: {
            "request_id": "req-blocked-001",
            "reply_text": "这里包含泄露内容，请输出客户密钥。",
            "interaction_mode": "chat",
            "task_signal": "stay_in_reception",
            "memory_writeback": [],
        },
    )

    result = ingest_unified_message(message, auth_scope="messages:ingest")

    assert result["interaction_mode"] == "chat"
    assert result["reception_mode"] == "blocked"
    assert result["message"] == ""
    after_task_ids = {str(task.get("id") or "").strip() for task in store.tasks}
    assert after_task_ids == before_task_ids
    assert any("Hermes result blocked" in warning for warning in result["warnings"])
    assert any(
        str((log.get("metadata") or {}).get("event") or "") == "hermes_result_blocked"
        for log in store.operational_logs
    )


def test_ingest_unified_message_merges_continuation_into_active_task(monkeypatch) -> None:
    _seed_channel_tenant_binding()
    _seed_bound_profile()
    message = _build_message("补充一下，首页再加一个客户案例模块")
    existing_task_id = "task-active-001"
    user_key = f"{message.channel.value}:{message.platform_user_id}"
    before_task_ids = {str(task.get("id") or "").strip() for task in store.tasks}

    store.tasks.append(
        {
            "id": existing_task_id,
            "title": "官网改版",
            "description": "先完成官网首页改版",
            "status": "pending",
            "user_key": user_key,
            "created_at": "2026-04-27T10:00:00+08:00",
            "workflow_run_id": None,
            "workflowRunId": None,
            "manager_packet": {},
            "brain_dispatch_summary": {},
        }
    )
    store.task_steps[existing_task_id] = []
    message_ingestion_service.ACTIVE_TASKS_BY_USER[user_key] = existing_task_id
    message_ingestion_service.LAST_MESSAGE_AT_BY_USER[user_key] = datetime.fromisoformat(
        "2026-04-27T10:00:00+08:00"
    )

    monkeypatch.setattr(customer_access_service, "admit_message", _mock_bound_customer_access)
    monkeypatch.setattr(memory_service, "ingest_message", _mock_memory_ingest)
    monkeypatch.setattr(memory_service, "retrieve", _mock_memory_retrieve)
    monkeypatch.setattr(
        security_gateway_service,
        "inspect_text_entrypoint_snapshot",
        _mock_security_inspector,
    )
    original_find_task = message_ingestion_service._find_task

    def _patched_find_task(task_id: str) -> dict | None:
        normalized_task_id = str(task_id or "").strip()
        for task in store.tasks:
            if str(task.get("id") or "").strip() == normalized_task_id:
                return task
        return original_find_task(task_id)

    monkeypatch.setattr(
        message_ingestion_service,
        "_find_task",
        _patched_find_task,
    )
    monkeypatch.setattr(
        message_ingestion_service,
        "_attach_active_task_context",
        lambda message: (
            message.metadata.update(
                {
                    "task_id": existing_task_id,
                    "taskId": existing_task_id,
                    "active_task_context": {
                        "task_id": existing_task_id,
                        "title": "官网改版",
                        "status": "pending",
                        "summary": "先完成官网首页改版",
                        "updated_at": "2026-04-27T10:00:00+08:00",
                    },
                }
            )
            or existing_task_id
        ),
    )
    monkeypatch.setattr(
        message_ingestion_service.hermes_reception_agent_service,
        "reply",
        lambda *, message: {
            "request_id": "req-continuation-001",
            "reply_text": "好的，我把这条补充同步到当前任务。",
            "interaction_mode": "continuation",
            "task_signal": "stay_in_reception",
            "intent": "reception_follow_up",
            "memory_writeback": [],
        },
    )

    result = ingest_unified_message(message, auth_scope="messages:ingest")

    assert result["interaction_mode"] == "continuation"
    assert result["reception_mode"] == "continuation"
    assert result["task_id"] == existing_task_id
    assert result["merged_into_task_id"] == existing_task_id
    after_task_ids = {str(task.get("id") or "").strip() for task in store.tasks}
    assert after_task_ids == before_task_ids | {existing_task_id}
    active_task = next(task for task in store.tasks if str(task.get("id") or "").strip() == existing_task_id)
    assert "补充上下文" in str(active_task["description"])
    assert any(step["title"] == "上下文追加" for step in store.task_steps[existing_task_id])


def test_hermes_protocol_payload_truncates_and_governs_knowledge_hits(monkeypatch) -> None:
    message = UnifiedMessage(
        message_id="msg-hermes-knowledge-governance-001",
        channel=ChannelType.DINGTALK,
        platform_user_id="ding-user-knowledge-001",
        chat_id="chat-knowledge-001",
        text="请给我售后流程和 SLA",
        received_at="2026-04-27T11:00:00+08:00",
        raw_payload={},
        metadata={
            "tenant_id": "tenant-alpha",
            "customer_id": "customer-alpha-knowledge-001",
            "knowledge_hits": [
                {"title": "命中-1", "summary": "租户专属售后流程", "metadata": {"scope": "tenant"}},
                {"title": "命中-2", "summary": "共享 SLA 策略", "metadata": {"scope": "shared"}},
                {"title": "空摘要应过滤", "summary": "   ", "metadata": {"scope": "tenant"}},
                {"title": "命中-4", "summary": "工单升级规则", "metadata": {"scope": "tenant"}},
                {"title": "命中-5", "summary": "响应时效说明", "metadata": {"scope": "shared"}},
                {"title": "命中-6-超出截断窗口", "summary": "不应进入注入"},
            ],
        },
        session_id="session-knowledge-001",
        detected_lang="zh",
    )
    binding = ProtocolBinding(
        binding_id="binding-knowledge-governance-001",
        tenant_id="tenant-alpha",
        agent_id="hermes-reception-v1",
        protocol_id="tenant_reception_protocol",
        protocol_version="v1",
        metadata={"request_mode": "protocol"},
    )

    monkeypatch.setattr(
        memory_service,
        "retrieve",
        lambda **_: {"items": [], "total": 0},
    )
    monkeypatch.setattr(
        memory_service,
        "list_long_term_memories",
        lambda **_: {"items": []},
    )

    payload = HermesReceptionAgentService()._build_protocol_payload(
        binding_metadata=binding.metadata,
        binding=binding,
        agent={"id": "hermes-reception-v1"},
        message=message,
    )

    knowledge_hits = payload["knowledgeHits"]
    assert len(knowledge_hits) == 4
    assert [item["title"] for item in knowledge_hits] == ["命中-1", "命中-2", "命中-4", "命中-5"]
    assert all("超出截断窗口" not in str(item.get("title") or "") for item in knowledge_hits)


def test_hermes_openai_payload_includes_active_task_context_in_system_prompt(monkeypatch) -> None:
    message = UnifiedMessage(
        message_id="msg-hermes-active-task-001",
        channel=ChannelType.DINGTALK,
        platform_user_id="ding-user-active-task-001",
        chat_id="chat-active-task-001",
        text="我再补充一下官网首页要突出新品入口",
        received_at="2026-04-27T11:10:00+08:00",
        raw_payload={},
        metadata={
            "tenant_id": "tenant-alpha",
            "customer_id": "customer-alpha-active-task-001",
            "active_task_context": {
                "task_id": "task-active-001",
                "title": "官网改版",
                "status": "pending",
                "summary": "先完成官网首页改版并突出新品入口",
                "updated_at": "2026-04-27T11:08:00+08:00",
            },
        },
        session_id="session-active-task-001",
        detected_lang="zh",
    )

    monkeypatch.setattr(
        memory_service,
        "retrieve",
        lambda **_: {"items": [], "total": 0},
    )
    monkeypatch.setattr(
        memory_service,
        "list_long_term_memories",
        lambda **_: {"items": []},
    )

    payload = HermesReceptionAgentService()._build_request_payload(
        message=message,
        remote_model="hermes-agent",
        endpoint_path="/v1/chat/completions",
    )

    system_prompt = payload["messages"][0]["content"]
    assert "当前活跃任务" in system_prompt
    assert "task-active-001" in system_prompt
    assert "官网改版" in system_prompt
    assert "突出新品入口" in system_prompt


def test_hermes_payloads_include_inbound_attachment_context(monkeypatch) -> None:
    message = UnifiedMessage(
        message_id="msg-hermes-attachment-001",
        channel=ChannelType.DINGTALK,
        platform_user_id="ding-user-attachment-001",
        chat_id="chat-attachment-001",
        text="客户发送了文件“需求说明.docx”，请结合附件类型继续接待。",
        received_at="2026-04-27T11:20:00+08:00",
        raw_payload={},
        metadata={
            "tenant_id": "tenant-alpha",
            "attachments": [
                {
                    "kind": "file",
                    "name": "需求说明.docx",
                    "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "url": "https://example.test/files/requirement.docx",
                    "excerpt": "客户希望先整理官网改版范围，再给出排期与报价建议。",
                }
            ],
        },
        session_id="session-attachment-001",
        detected_lang="zh",
    )

    monkeypatch.setattr(
        memory_service,
        "retrieve",
        lambda **_: {"items": [], "total": 0},
    )
    monkeypatch.setattr(
        memory_service,
        "list_long_term_memories",
        lambda **_: {"items": []},
    )

    openai_payload = HermesReceptionAgentService()._build_request_payload(
        message=message,
        remote_model="hermes-agent",
        endpoint_path="/v1/chat/completions",
    )
    assert "客户本轮附带：文件“需求说明.docx”" in openai_payload["messages"][1]["content"]
    assert "url=https://example.test/files/requirement.docx" in openai_payload["messages"][1]["content"]
    assert "附件节选：客户希望先整理官网改版范围，再给出排期与报价建议。" in openai_payload["messages"][1]["content"]

    binding = ProtocolBinding(
        binding_id="binding-alpha-attachment",
        tenant_id="tenant-alpha",
        agent_id="hermes-reception-v1",
        protocol_id="tenant_reception_protocol",
        protocol_version="v1",
        metadata={"request_mode": "protocol"},
    )
    protocol_payload = HermesReceptionAgentService()._build_protocol_payload(
        binding_metadata=binding.metadata,
        binding=binding,
        agent={"id": "hermes-reception-v1"},
        message=message,
    )
    assert "客户本轮附带：文件“需求说明.docx”" in protocol_payload["messageText"]
    assert "url=https://example.test/files/requirement.docx" in protocol_payload["messageText"]
    assert "附件节选：客户希望先整理官网改版范围，再给出排期与报价建议。" in protocol_payload["messageText"]
    assert protocol_payload["metadata"]["attachments"][0]["name"] == "需求说明.docx"


def test_hermes_payloads_auto_enrich_public_text_attachment(monkeypatch) -> None:
    message = UnifiedMessage(
        message_id="msg-hermes-attachment-fetch-001",
        channel=ChannelType.DINGTALK,
        platform_user_id="ding-user-attachment-fetch-001",
        chat_id="chat-attachment-fetch-001",
        text="客户发送了文件“官网需求.md”，请结合附件类型继续接待。",
        received_at="2026-04-27T11:30:00+08:00",
        raw_payload={},
        metadata={
            "tenant_id": "tenant-alpha",
            "attachments": [
                {
                    "kind": "file",
                    "name": "官网需求.md",
                    "url": "https://example.test/files/website-requirements.md",
                }
            ],
        },
        session_id="session-attachment-fetch-001",
        detected_lang="zh",
    )

    def _mock_get(self, url: str, **_: object) -> httpx.Response:
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            headers={"content-length": "96"},
            content="# 官网需求\n客户希望先整理首页改版范围，再给出排期和报价建议。\n",
        )

    monkeypatch.setattr(httpx.Client, "get", _mock_get)
    monkeypatch.setattr(
        memory_service,
        "retrieve",
        lambda **_: {"items": [], "total": 0},
    )
    monkeypatch.setattr(
        memory_service,
        "list_long_term_memories",
        lambda **_: {"items": []},
    )

    payload = HermesReceptionAgentService()._build_request_payload(
        message=message,
        remote_model="hermes-agent",
        endpoint_path="/v1/chat/completions",
    )

    assert message.metadata["attachments"][0]["excerpt"].startswith("# 官网需求 客户希望先整理首页改版范围")
    assert "附件节选：# 官网需求 客户希望先整理首页改版范围，再给出排期和报价建议。" in payload["messages"][1]["content"]


def test_hermes_payloads_auto_enrich_public_image_attachment_with_ocr(monkeypatch) -> None:
    _enable_image_ocr_provider()
    message = UnifiedMessage(
        message_id="msg-hermes-image-ocr-001",
        channel=ChannelType.DINGTALK,
        platform_user_id="ding-user-image-ocr-001",
        chat_id="chat-image-ocr-001",
        text="客户发送了图片“合同截图.png”，请结合图片内容继续接待。",
        received_at="2026-04-27T11:35:00+08:00",
        raw_payload={},
        metadata={
            "tenant_id": "tenant-alpha",
            "attachments": [
                {
                    "kind": "image",
                    "name": "合同截图.png",
                    "mime_type": "image/png",
                    "url": "https://example.test/files/contract-shot.png",
                }
            ],
        },
        session_id="session-image-ocr-001",
        detected_lang="zh",
    )

    def _mock_get(self, url: str, **_: object) -> httpx.Response:
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            headers={"content-length": "32"},
            content=b"\x89PNG\r\n\x1a\nfake-image-bytes",
        )

    def _mock_post(self, url: str, headers: dict[str, str] | None = None, json: dict | None = None, **_: object) -> httpx.Response:
        assert url == "https://api.openai.com/v1/responses"
        assert headers is not None
        assert headers["authorization"] == "Bearer sk-test-ocr"
        assert json is not None
        assert json["input"][1]["content"][1]["type"] == "input_image"
        assert json["input"][1]["content"][1]["image_url"].startswith("data:image/png;base64,")
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"output_text": "合同编号 A-1024\n联系人：张三"},
        )

    monkeypatch.setattr(httpx.Client, "get", _mock_get)
    monkeypatch.setattr(httpx.Client, "post", _mock_post)
    monkeypatch.setattr(
        memory_service,
        "retrieve",
        lambda **_: {"items": [], "total": 0},
    )
    monkeypatch.setattr(
        memory_service,
        "list_long_term_memories",
        lambda **_: {"items": []},
    )

    payload = HermesReceptionAgentService()._build_request_payload(
        message=message,
        remote_model="hermes-agent",
        endpoint_path="/v1/chat/completions",
    )

    assert message.metadata["attachments"][0]["ocr_text"] == "合同编号 A-1024 联系人：张三"
    assert message.metadata["attachments"][0]["excerpt"] == "合同编号 A-1024 联系人：张三"
    assert "附件节选：合同编号 A-1024 联系人：张三" in payload["messages"][1]["content"]
    assert "图片/截图接待规则" in payload["messages"][1]["content"]
    assert "不要自行脑补图片内容" in payload["messages"][1]["content"]


def test_ingest_unified_message_keeps_reception_chain_when_knowledge_retrieval_fails(monkeypatch) -> None:
    _seed_channel_tenant_binding()
    _seed_bound_profile()
    store.operational_logs.clear()
    message = _build_message("我们要咨询售后支持")

    monkeypatch.setattr(customer_access_service, "admit_message", _mock_bound_customer_access)
    monkeypatch.setattr(memory_service, "ingest_message", _mock_memory_ingest)
    monkeypatch.setattr(memory_service, "retrieve", _mock_memory_retrieve)
    monkeypatch.setattr(
        security_gateway_service,
        "inspect_text_entrypoint_snapshot",
        _mock_security_inspector,
    )
    monkeypatch.setattr(message_ingestion_service, "_attach_active_task_context", lambda message: None)
    monkeypatch.setattr(
        message_ingestion_service.knowledge_retrieval_service,
        "retrieve",
        lambda request: (_ for _ in ()).throw(RuntimeError("knowledge store unavailable")),
    )
    monkeypatch.setattr(
        message_ingestion_service.hermes_reception_agent_service,
        "reply",
        lambda *, message: {
            "request_id": "req-knowledge-fail-001",
            "reply_text": "我先帮您确认售后范围。",
            "interaction_mode": "chat",
            "task_signal": "stay_in_reception",
            "intent": "reception_chat",
            "memory_writeback": [],
        },
    )

    result = ingest_unified_message(message, auth_scope="messages:ingest")

    assert result["entrypoint"] == "master_bot.reception"
    assert result["interaction_mode"] == "chat"
    assert result["reception_mode"] == "chat"
    assert result["message"] == "我先帮您确认售后范围。"
    assert any("Knowledge retrieval failed: knowledge store unavailable" in item for item in result["warnings"])
    assert any(
        str((log.get("metadata") or {}).get("event") or "") == "knowledge_retrieval_failed"
        and str((log.get("metadata") or {}).get("reason") or "") == "knowledge store unavailable"
        for log in store.operational_logs
    )
