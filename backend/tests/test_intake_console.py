from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.config import get_settings
from app.modules.reception.customer_access.schemas import UpdateCustomerAccessSettingsRequest
from app.modules.reception.customer_access.service import customer_access_service
from app.modules.reception.application.message_ingestion_service import ingest_unified_message
from app.modules.reception.schemas.messages import ChannelType, UnifiedMessage
from app.platform.observability.operational_log_service import append_realtime_event
from app.platform.persistence.persistence_service import persistence_service
from app.platform.persistence.runtime_store import store


client = TestClient(app)


def _seed_channel_binding() -> None:
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


def _reset_customer_access_settings() -> None:
    customer_access_service.update_settings(UpdateCustomerAccessSettingsRequest(tenant_policies=[]))


def _dashboard_auth_headers(auth_headers_factory) -> dict[str, str]:
    settings = get_settings()
    return auth_headers_factory(user_id="admin-1", email=settings.demo_admin_email, role="admin")


def test_ingest_unified_message_records_pending_intake_event() -> None:
    _reset_customer_access_settings()
    _seed_channel_binding()
    store.operational_logs.clear()
    message = UnifiedMessage(
        message_id="msg-intake-pending-001",
        channel=ChannelType.DINGTALK,
        platform_user_id="ding-user-001",
        chat_id="chat-001",
        text="你好",
        received_at="2026-04-28T12:00:00+08:00",
        raw_payload={},
        metadata={},
    )

    result = ingest_unified_message(message, auth_scope="messages:ingest")

    assert result["reception_mode"] == "customer_access"
    assert any(
        str((log.get("metadata") or {}).get("intake_status") or "") in {"pending_verification", "rejected"}
        for log in store.operational_logs
    )


def test_intake_overview_route_returns_admission_events_and_reception_sessions(auth_headers_factory) -> None:
    auth_headers = _dashboard_auth_headers(auth_headers_factory)
    store.operational_logs.clear()
    store.user_profiles["profile-alpha-001"] = {
        "id": "profile-alpha-001",
        "tenant_id": "tenant-alpha",
        "tenant_name": "Alpha Corp",
        "name": "张三",
        "contact_name": "张三",
        "service_code": "ALPHA-001",
    }

    append_realtime_event(
        agent="客户准入层",
        message="客户准入通过，已进入 Hermes 接待",
        type_="success",
        source="message_ingestion",
        timestamp=datetime(2026, 4, 28, 4, 0, 1, tzinfo=UTC),
        trace_id="trace-pass-001",
        metadata={
            "domain": "intake",
            "intake_event_kind": "admission",
            "intake_status": "passed",
            "tenant_id": "tenant-alpha",
            "tenant_name": "Alpha Corp",
            "profile_id": "profile-alpha-001",
            "channel": "dingtalk",
            "platform_user_id": "ding-user-001",
            "service_code": "ALPHA-001",
            "session_id": "session-alpha-001",
        },
    )
    append_realtime_event(
        agent="客户准入层",
        message="客户准入待补充",
        type_="warning",
        source="message_ingestion",
        timestamp=datetime(2026, 4, 28, 4, 0, 2, tzinfo=UTC),
        trace_id="trace-pending-001",
        metadata={
            "domain": "intake",
            "intake_event_kind": "admission",
            "intake_status": "pending_verification",
            "tenant_id": "tenant-alpha",
            "tenant_name": "Alpha Corp",
            "channel": "dingtalk",
            "platform_user_id": "ding-user-002",
            "session_id": "session-alpha-002",
            "missing_fields": ["service_code"],
        },
    )
    append_realtime_event(
        agent="安全网关",
        message="prompt_injection 已拦截消息",
        type_="error",
        source="security_gateway",
        timestamp=datetime(2026, 4, 28, 4, 0, 2, 500000, tzinfo=UTC),
        trace_id="trace-security-001",
        metadata={
            "event": "message_blocked",
            "layer": "prompt_injection",
            "user_key": "dingtalk:ding-user-003",
            "status_code": 403,
        },
    )
    append_realtime_event(
        agent="安全监听层",
        message="渠道消息被安全监听阻断",
        type_="error",
        source="message_ingestion",
        timestamp=datetime(2026, 4, 28, 4, 0, 3, tzinfo=UTC),
        trace_id="trace-security-001",
        metadata={
            "domain": "intake",
            "intake_event_kind": "admission",
            "intake_status": "security_blocked",
            "tenant_id": "tenant-alpha",
            "tenant_name": "Alpha Corp",
            "channel": "dingtalk",
            "platform_user_id": "ding-user-003",
            "session_id": "session-alpha-003",
            "reason": "Prompt injection risk detected",
        },
    )
    append_realtime_event(
        agent="Hermes Reception Agent",
        message="Hermes 正在接待当前客户",
        type_="info",
        source="message_ingestion",
        timestamp=datetime(2026, 4, 28, 4, 0, 3, 500000, tzinfo=UTC),
        trace_id="trace-pass-001",
        metadata={
            "domain": "intake",
            "intake_event_kind": "session",
            "agent_role": "hermes_reception",
            "reception_session_state": "serving",
            "tenant_id": "tenant-alpha",
            "tenant_name": "Alpha Corp",
            "profile_id": "profile-alpha-001",
            "channel": "dingtalk",
            "platform_user_id": "ding-user-001",
            "service_code": "ALPHA-001",
            "session_id": "session-alpha-001",
            "active_task_id": "task-alpha-001",
            "active_task_context": {
                "task_id": "task-alpha-001",
                "title": "官网改版",
                "status": "pending",
                "summary": "先完成官网首页改版",
                "updated_at": "2026-04-28T04:00:03+00:00",
            },
        },
    )
    append_realtime_event(
        agent="Hermes Reception Agent",
        message="Hermes 已生成回复：我先帮您确认需求范围",
        type_="success",
        source="message_ingestion",
        timestamp=datetime(2026, 4, 28, 4, 0, 4, tzinfo=UTC),
        trace_id="trace-pass-001",
        metadata={
            "domain": "intake",
            "intake_event_kind": "session",
            "agent_role": "hermes_reception",
            "reception_session_state": "replied",
            "tenant_id": "tenant-alpha",
            "tenant_name": "Alpha Corp",
            "profile_id": "profile-alpha-001",
            "channel": "dingtalk",
            "platform_user_id": "ding-user-001",
            "service_code": "ALPHA-001",
            "session_id": "session-alpha-001",
            "interaction_mode": "task",
            "task_signal": "dispatch_task",
            "protocol_mode": "platform_stateless",
            "reply_preview": "我先帮您确认需求范围",
        },
    )

    response = client.get("/api/intake/overview", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["passed"] == 1
    assert body["summary"]["pendingVerification"] == 1
    assert body["summary"]["securityBlocked"] == 1
    assert len(body["admissionEvents"]) >= 3
    assert len(body["securityEvents"]) >= 1
    assert len(body["hermesEvents"]) >= 2
    assert body["receptionSessions"][0]["tenantName"] == "Alpha Corp"
    assert body["receptionSessions"][0]["personName"] == "张三"
    assert body["receptionSessions"][0]["state"] == "replied"
    assert body["receptionSessions"][0]["currentStage"] == "已转任务"
    assert body["receptionSessions"][0]["activeTaskId"] == "task-alpha-001"
    assert body["receptionSessions"][0]["activeTask"]["taskId"] == "task-alpha-001"
    assert body["receptionSessions"][0]["activeTask"]["title"] == "官网改版"
    assert body["receptionSessions"][0]["activeTask"]["status"] == "pending"
    assert body["receptionSessions"][0]["lastInteractionMode"] == "task"
    assert body["receptionSessions"][0]["lastTaskSignal"] == "dispatch_task"
    assert body["receptionSessions"][0]["lastInputSecurityStatus"] == "passed"
    assert body["receptionSessions"][0]["lastOutputSecurityStatus"] == "passed"
    assert body["receptionSessions"][0]["protocolMode"] == "platform_stateless"
    assert body["receptionSessions"][0]["replyPreview"] == "我先帮您确认需求范围"
    assert body["securityEvents"][0]["blockStage"] == "渠道输入"
    assert body["securityEvents"][0]["securityLayer"] == "prompt_injection"
    assert body["hermesEvents"][0]["currentStage"] == "已转任务"
    assert body["hermesEvents"][0]["interactionMode"] == "task"
    assert body["hermesEvents"][0]["taskSignal"] == "dispatch_task"
    assert body["hermesEvents"][0]["outputSecurityStatus"] == "passed"
    assert body["hermesEvents"][0]["activeTask"]["taskId"] == "task-alpha-001"
    assert body["hermesEvents"][0]["activeTask"]["summary"] == "先完成官网首页改版"


def test_intake_overview_route_maps_output_security_block_state(auth_headers_factory) -> None:
    auth_headers = _dashboard_auth_headers(auth_headers_factory)
    store.operational_logs.clear()
    store.user_profiles["profile-alpha-009"] = {
        "id": "profile-alpha-009",
        "tenant_id": "tenant-alpha",
        "tenant_name": "Alpha Corp",
        "name": "王五",
        "contact_name": "王五",
        "service_code": "ALPHA-009",
    }

    append_realtime_event(
        agent="客户准入层",
        message="客户准入通过，已进入 Hermes 接待",
        type_="success",
        source="message_ingestion",
        timestamp=datetime(2026, 4, 28, 4, 3, 0, tzinfo=UTC),
        trace_id="trace-block-001",
        metadata={
            "domain": "intake",
            "intake_event_kind": "admission",
            "intake_status": "passed",
            "tenant_id": "tenant-alpha",
            "tenant_name": "Alpha Corp",
            "profile_id": "profile-alpha-009",
            "channel": "dingtalk",
            "platform_user_id": "ding-user-009",
            "service_code": "ALPHA-009",
            "session_id": "session-alpha-009",
        },
    )
    append_realtime_event(
        agent="Hermes Reception Agent",
        message="Hermes 正在接待当前客户",
        type_="info",
        source="message_ingestion",
        timestamp=datetime(2026, 4, 28, 4, 3, 1, tzinfo=UTC),
        trace_id="trace-block-001",
        metadata={
            "domain": "intake",
            "intake_event_kind": "session",
            "agent_role": "hermes_reception",
            "reception_session_state": "serving",
            "tenant_id": "tenant-alpha",
            "tenant_name": "Alpha Corp",
            "profile_id": "profile-alpha-009",
            "channel": "dingtalk",
            "platform_user_id": "ding-user-009",
            "service_code": "ALPHA-009",
            "session_id": "session-alpha-009",
            "active_task_id": "task-alpha-009",
            "active_task_context": {
                "task_id": "task-alpha-009",
                "title": "售后升级处理",
                "status": "running",
                "summary": "等待输出前安全复核",
            },
        },
    )
    append_realtime_event(
        agent="安全网关",
        message="xss 已拦截消息",
        type_="error",
        source="security_gateway",
        timestamp=datetime(2026, 4, 28, 4, 3, 1, 500000, tzinfo=UTC),
        trace_id="trace-block-001",
        metadata={
            "event": "message_blocked",
            "layer": "xss",
            "rule_name": "XSS 防护",
            "user_key": "hermes:dingtalk:ding-user-009:reply_text",
            "status_code": 403,
            "detail": "XSS risk detected",
        },
    )
    append_realtime_event(
        agent="Hermes 回传安全监听",
        message="Hermes 回传结果被安全监听阻断",
        type_="error",
        source="message_ingestion",
        timestamp=datetime(2026, 4, 28, 4, 3, 2, tzinfo=UTC),
        trace_id="trace-block-001",
        metadata={
            "domain": "intake",
            "intake_event_kind": "admission",
            "intake_status": "security_blocked",
            "tenant_id": "tenant-alpha",
            "tenant_name": "Alpha Corp",
            "profile_id": "profile-alpha-009",
            "channel": "dingtalk",
            "platform_user_id": "ding-user-009",
            "service_code": "ALPHA-009",
            "session_id": "session-alpha-009",
            "reason": "输出命中敏感信息规则",
        },
    )
    append_realtime_event(
        agent="Hermes Reception Agent",
        message="Hermes 回传结果被安全监听阻断",
        type_="warning",
        source="message_ingestion",
        timestamp=datetime(2026, 4, 28, 4, 3, 3, tzinfo=UTC),
        trace_id="trace-block-001",
        metadata={
            "domain": "intake",
            "intake_event_kind": "session",
            "agent_role": "hermes_reception",
            "reception_session_state": "failed",
            "tenant_id": "tenant-alpha",
            "tenant_name": "Alpha Corp",
            "profile_id": "profile-alpha-009",
            "channel": "dingtalk",
            "platform_user_id": "ding-user-009",
            "service_code": "ALPHA-009",
            "session_id": "session-alpha-009",
            "event": "hermes_result_blocked",
            "reason": "输出命中敏感信息规则",
        },
    )

    response = client.get("/api/intake/overview", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    target = next(item for item in body["receptionSessions"] if item["sessionId"] == "session-alpha-009")
    security_target = next(item for item in body["securityEvents"] if item["sessionId"] == "session-alpha-009")
    hermes_target = next(item for item in body["hermesEvents"] if item["sessionId"] == "session-alpha-009")
    assert target["currentStage"] == "输出安全阻断"
    assert target["lastInputSecurityStatus"] == "passed"
    assert target["lastOutputSecurityStatus"] == "blocked"
    assert target["outputBlockReason"] == "输出命中敏感信息规则"
    assert target["outputBlockLayer"] == "xss"
    assert target["outputBlockRuleName"] == "XSS 防护"
    assert target["outputBlockStatusCode"] == 403
    assert target["activeTaskId"] == "task-alpha-009"
    assert target["activeTask"]["taskId"] == "task-alpha-009"
    assert target["activeTask"]["title"] == "售后升级处理"
    assert security_target["blockStage"] == "Hermes 输出"
    assert security_target["securityLayer"] == "xss"
    assert security_target["securityRuleName"] == "XSS 防护"
    assert security_target["statusCode"] == 403
    assert security_target["reason"] == "输出命中敏感信息规则"
    assert hermes_target["currentStage"] == "输出安全阻断"
    assert hermes_target["outputSecurityStatus"] == "blocked"
    assert hermes_target["outputBlockLayer"] == "xss"
    assert hermes_target["outputBlockRuleName"] == "XSS 防护"
    assert hermes_target["outputBlockStatusCode"] == 403
    assert hermes_target["activeTask"]["taskId"] == "task-alpha-009"


def test_intake_overview_route_supports_filters(auth_headers_factory) -> None:
    auth_headers = _dashboard_auth_headers(auth_headers_factory)
    store.operational_logs.clear()
    append_realtime_event(
        agent="客户准入层",
        message="客户准入通过，已进入 Hermes 接待",
        type_="success",
        source="message_ingestion",
        timestamp=datetime(2026, 4, 28, 4, 1, 0, tzinfo=UTC),
        trace_id="trace-filter-tenant-a",
        metadata={
            "domain": "intake",
            "intake_event_kind": "admission",
            "intake_status": "passed",
            "tenant_id": "tenant-alpha",
            "tenant_name": "Alpha Corp",
            "channel": "dingtalk",
        },
    )
    append_realtime_event(
        agent="客户准入层",
        message="客户准入通过，已进入 Hermes 接待",
        type_="success",
        source="message_ingestion",
        timestamp=datetime(2026, 4, 28, 4, 1, 1, tzinfo=UTC),
        trace_id="trace-filter-tenant-b",
        metadata={
            "domain": "intake",
            "intake_event_kind": "admission",
            "intake_status": "passed",
            "tenant_id": "tenant-beta",
            "tenant_name": "Beta Corp",
            "channel": "feishu",
        },
    )

    response = client.get("/api/intake/overview?tenantId=tenant-alpha&channel=dingtalk", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["passed"] == 1
    assert len(body["admissionEvents"]) == 1
    assert body["admissionEvents"][0]["tenantId"] == "tenant-alpha"
    assert body["admissionEvents"][0]["channel"] == "dingtalk"


def test_intake_trace_detail_route_returns_trace_logs(auth_headers_factory) -> None:
    auth_headers = _dashboard_auth_headers(auth_headers_factory)
    store.operational_logs.clear()
    append_realtime_event(
        agent="安全监听层",
        message="渠道消息被安全监听阻断",
        type_="error",
        source="message_ingestion",
        timestamp=datetime(2026, 4, 28, 4, 2, 0, tzinfo=UTC),
        trace_id="trace-detail-001",
        metadata={
            "domain": "intake",
            "intake_event_kind": "admission",
            "intake_status": "security_blocked",
            "tenant_id": "tenant-alpha",
            "tenant_name": "Alpha Corp",
            "channel": "dingtalk",
            "person_name": "李四",
            "service_code": "ALPHA-002",
            "session_id": "session-alpha-002",
        },
    )
    append_realtime_event(
        agent="安全网关",
        message="prompt_injection 已拦截消息",
        type_="error",
        source="security_gateway",
        timestamp=datetime(2026, 4, 28, 4, 2, 1, tzinfo=UTC),
        trace_id="trace-detail-001",
        metadata={
            "layer": "prompt_injection",
        },
    )

    response = client.get("/api/intake/traces/trace-detail-001", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["traceId"] == "trace-detail-001"
    assert body["tenantName"] == "Alpha Corp"
    assert body["personName"] == "李四"
    assert len(body["items"]) == 2
    assert body["items"][0]["traceId"] == "trace-detail-001"


def test_intake_overview_route_exposes_knowledge_hits_summary_on_session_events(auth_headers_factory) -> None:
    auth_headers = _dashboard_auth_headers(auth_headers_factory)
    store.operational_logs.clear()
    store.user_profiles["profile-alpha-knowledge-001"] = {
        "id": "profile-alpha-knowledge-001",
        "tenant_id": "tenant-alpha",
        "tenant_name": "Alpha Corp",
        "name": "赵六",
        "contact_name": "赵六",
        "service_code": "ALPHA-KHIT-001",
    }

    append_realtime_event(
        agent="客户准入层",
        message="客户准入通过，已进入 Hermes 接待",
        type_="success",
        source="message_ingestion",
        timestamp=datetime(2026, 4, 28, 5, 0, 0, tzinfo=UTC),
        trace_id="trace-knowledge-001",
        metadata={
            "domain": "intake",
            "intake_event_kind": "admission",
            "intake_status": "passed",
            "tenant_id": "tenant-alpha",
            "tenant_name": "Alpha Corp",
            "profile_id": "profile-alpha-knowledge-001",
            "channel": "dingtalk",
            "platform_user_id": "ding-user-knowledge-001",
            "service_code": "ALPHA-KHIT-001",
            "session_id": "session-alpha-knowledge-001",
        },
    )
    append_realtime_event(
        agent="Hermes Reception Agent",
        message="Hermes 已生成回复：我先为您总结售后关键项",
        type_="success",
        source="message_ingestion",
        timestamp=datetime(2026, 4, 28, 5, 0, 1, tzinfo=UTC),
        trace_id="trace-knowledge-001",
        metadata={
            "domain": "intake",
            "intake_event_kind": "session",
            "agent_role": "hermes_reception",
            "reception_session_state": "replied",
            "tenant_id": "tenant-alpha",
            "tenant_name": "Alpha Corp",
            "profile_id": "profile-alpha-knowledge-001",
            "channel": "dingtalk",
            "platform_user_id": "ding-user-knowledge-001",
            "service_code": "ALPHA-KHIT-001",
            "session_id": "session-alpha-knowledge-001",
            "interaction_mode": "chat",
            "task_signal": "stay_in_reception",
            "protocol_mode": "platform_stateless",
            "reply_preview": "我先为您总结售后关键项",
            "knowledge_hit_count": 3,
            "knowledge_tenant_hits": 2,
            "knowledge_shared_hits": 1,
            "knowledge_hits_preview": [
                {"title": "租户售后流程", "scope": "tenant", "score": 9.2, "summary": "先登记工单"},
                {"title": "共享 SLA 规范", "scope": "shared", "score": 8.8, "summary": "响应时效分级"},
                {"title": "", "scope": "tenant", "score": 7.1, "summary": "无标题应过滤"},
            ],
        },
    )

    response = client.get("/api/intake/overview", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    session = next(item for item in body["receptionSessions"] if item["sessionId"] == "session-alpha-knowledge-001")
    hermes = next(item for item in body["hermesEvents"] if item["sessionId"] == "session-alpha-knowledge-001")
    assert session["knowledgeHitCount"] == 3
    assert session["knowledgeTenantHits"] == 2
    assert session["knowledgeSharedHits"] == 1
    assert len(session["knowledgeHitsPreview"]) == 2
    assert session["knowledgeHitsPreview"][0]["title"] == "租户售后流程"
    assert hermes["knowledgeHitCount"] == 3
    assert hermes["knowledgeTenantHits"] == 2
    assert hermes["knowledgeSharedHits"] == 1
    assert len(hermes["knowledgeHitsPreview"]) == 2

    trace_response = client.get("/api/intake/traces/trace-knowledge-001", headers=auth_headers)

    assert trace_response.status_code == 200
    trace_body = trace_response.json()
    assert trace_body["traceId"] == "trace-knowledge-001"
    assert trace_body["items"][0]["metadata"]["knowledge_hit_count"] == 3
    assert len(trace_body["items"][0]["metadata"]["knowledge_hits_preview"]) == 3
    assert trace_body["items"][0]["metadata"]["knowledge_hits_preview"][0]["title"] == "租户售后流程"
