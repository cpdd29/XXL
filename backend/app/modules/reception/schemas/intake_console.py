from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.platform.contracts.api_model import APIModel


IntakeAdmissionStatus = Literal["passed", "pending_verification", "rejected", "security_blocked"]
IntakeReceptionSessionState = Literal["serving", "replied", "failed"]


class IntakeStatusSummary(APIModel):
    passed: int = 0
    pending_verification: int = 0
    rejected: int = 0
    security_blocked: int = 0


class IntakeAdmissionEvent(APIModel):
    id: str
    timestamp: str
    status: IntakeAdmissionStatus
    agent: str
    message: str
    tenant_id: str | None = None
    tenant_name: str | None = None
    profile_id: str | None = None
    customer_id: str | None = None
    person_name: str | None = None
    channel: str | None = None
    platform_user_id: str | None = None
    service_code: str | None = None
    session_id: str | None = None
    trace_id: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    reason: str | None = None


class IntakeKnowledgeHitPreview(APIModel):
    title: str
    source: str | None = None
    summary: str | None = None
    scope: str | None = None
    score: float | None = None


class IntakeActiveTaskPreview(APIModel):
    task_id: str
    title: str | None = None
    status: str | None = None
    summary: str | None = None
    updated_at: str | None = None


class IntakeReceptionSession(APIModel):
    session_key: str
    updated_at: str
    state: IntakeReceptionSessionState
    agent: str
    latest_message: str
    tenant_id: str | None = None
    tenant_name: str | None = None
    profile_id: str | None = None
    customer_id: str | None = None
    person_name: str | None = None
    channel: str | None = None
    platform_user_id: str | None = None
    service_code: str | None = None
    session_id: str | None = None
    trace_id: str | None = None
    current_stage: str | None = None
    active_task_id: str | None = None
    active_task: IntakeActiveTaskPreview | None = None
    last_interaction_mode: str | None = None
    last_task_signal: str | None = None
    last_input_security_status: str | None = None
    last_output_security_status: str | None = None
    output_block_reason: str | None = None
    output_block_layer: str | None = None
    output_block_rule_name: str | None = None
    output_block_status_code: int | None = None
    reply_preview: str | None = None
    protocol_mode: str | None = None
    knowledge_hit_count: int = 0
    knowledge_tenant_hits: int = 0
    knowledge_shared_hits: int = 0
    knowledge_hits_preview: list[IntakeKnowledgeHitPreview] = Field(default_factory=list)


class IntakeSecurityEvent(APIModel):
    id: str
    timestamp: str
    status: IntakeAdmissionStatus
    agent: str
    message: str
    block_stage: str | None = None
    security_layer: str | None = None
    security_rule_name: str | None = None
    status_code: int | None = None
    tenant_id: str | None = None
    tenant_name: str | None = None
    profile_id: str | None = None
    customer_id: str | None = None
    person_name: str | None = None
    channel: str | None = None
    platform_user_id: str | None = None
    service_code: str | None = None
    session_id: str | None = None
    trace_id: str | None = None
    reason: str | None = None


class IntakeHermesEvent(APIModel):
    id: str
    timestamp: str
    state: IntakeReceptionSessionState
    agent: str
    message: str
    current_stage: str | None = None
    interaction_mode: str | None = None
    task_signal: str | None = None
    protocol_mode: str | None = None
    reply_preview: str | None = None
    output_security_status: str | None = None
    output_block_layer: str | None = None
    output_block_rule_name: str | None = None
    output_block_status_code: int | None = None
    active_task_id: str | None = None
    active_task: IntakeActiveTaskPreview | None = None
    tenant_id: str | None = None
    tenant_name: str | None = None
    profile_id: str | None = None
    customer_id: str | None = None
    person_name: str | None = None
    channel: str | None = None
    platform_user_id: str | None = None
    service_code: str | None = None
    session_id: str | None = None
    trace_id: str | None = None
    reason: str | None = None
    knowledge_hit_count: int = 0
    knowledge_tenant_hits: int = 0
    knowledge_shared_hits: int = 0
    knowledge_hits_preview: list[IntakeKnowledgeHitPreview] = Field(default_factory=list)


class IntakeConsoleOverviewResponse(APIModel):
    summary: IntakeStatusSummary
    admission_events: list[IntakeAdmissionEvent] = Field(default_factory=list)
    security_events: list[IntakeSecurityEvent] = Field(default_factory=list)
    hermes_events: list[IntakeHermesEvent] = Field(default_factory=list)
    reception_sessions: list[IntakeReceptionSession] = Field(default_factory=list)
    active_session_count: int = 0
    updated_at: str | None = None


class IntakeTraceLogEntry(APIModel):
    id: str
    timestamp: str
    type: str
    agent: str
    message: str
    source: str
    trace_id: str | None = None
    task_id: str | None = None
    workflow_run_id: str | None = None
    metadata: dict | None = None


class IntakeTraceDetailResponse(APIModel):
    trace_id: str
    tenant_id: str | None = None
    tenant_name: str | None = None
    profile_id: str | None = None
    customer_id: str | None = None
    person_name: str | None = None
    channel: str | None = None
    platform_user_id: str | None = None
    service_code: str | None = None
    session_id: str | None = None
    items: list[IntakeTraceLogEntry] = Field(default_factory=list)
