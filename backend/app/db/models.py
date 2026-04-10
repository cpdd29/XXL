from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AgentRecord(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sort_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tasks_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tasks_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_response_time: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_rate: Mapped[float] = mapped_column(nullable=False, default=0.0)
    last_active: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    config_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class SystemSettingRecord(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[str] = mapped_column(String(128), nullable=False)


class TaskRecord(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sort_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    priority: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[str] = mapped_column(String(128), nullable=False)
    completed_at: Mapped[str | None] = mapped_column(String(128), nullable=True)
    agent: Mapped[str] = mapped_column(String(255), nullable=False)
    tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration: Mapped[str | None] = mapped_column(String(128), nullable=True)
    workflow_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    workflow_run_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    channel: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    user_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    preferred_language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    detected_lang: Mapped[str | None] = mapped_column(String(32), nullable=True)
    route_decision: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class TaskStepRecord(Base):
    __tablename__ = "task_steps"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sort_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    agent: Mapped[str] = mapped_column(String(255), nullable=False)
    started_at: Mapped[str] = mapped_column(String(128), nullable=False)
    finished_at: Mapped[str | None] = mapped_column(String(128), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class WorkflowRecord(Base):
    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    sort_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(128), nullable=False)
    node_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    edge_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    trigger: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    agent_bindings: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    nodes: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    edges: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)


class WorkflowRunRecord(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    sort_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    workflow_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workflow_name: Mapped[str] = mapped_column(String(255), nullable=False)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    trigger: Mapped[str] = mapped_column(String(255), nullable=False)
    intent: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(128), nullable=False)
    started_at: Mapped[str] = mapped_column(String(128), nullable=False)
    completed_at: Mapped[str | None] = mapped_column(String(128), nullable=True)
    next_dispatch_at: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dispatch_failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_dispatch_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    dispatcher_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dispatch_claimed_at: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dispatch_lease_expires_at: Mapped[str | None] = mapped_column(String(128), nullable=True)
    current_stage: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    active_edges: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    nodes: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    logs: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    message_dispatch_context: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    memory_hits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warnings: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)


class WorkflowDispatchJobRecord(Base):
    __tablename__ = "workflow_dispatch_jobs"

    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    available_at: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    step_delay_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    dispatcher_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    claimed_at: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(128), nullable=False)


class WorkflowExecutionJobRecord(Base):
    __tablename__ = "workflow_execution_jobs"

    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    available_at: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    step_delay_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    claimed_at: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(128), nullable=False)


class AgentExecutionJobRecord(Base):
    __tablename__ = "agent_execution_jobs"

    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    workflow_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    execution_agent_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    available_at: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    step_delay_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    claimed_at: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(128), nullable=False)


class InternalEventDeliveryRecord(Base):
    __tablename__ = "internal_event_deliveries"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    event_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(255), nullable=False, default="Internal Event Bus")
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    triggered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    triggered_workflow_ids: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    triggered_run_ids: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    triggered_task_ids: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    primary_workflow: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(128), nullable=False)
    delivered_at: Mapped[str | None] = mapped_column(String(128), nullable=True)


class ConversationMessageRecord(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    detected_lang: Mapped[str] = mapped_column(String(32), nullable=False, default="zh")
    created_at: Mapped[str] = mapped_column(String(128), nullable=False, index=True)


class MemorySessionStateRecord(Base):
    __tablename__ = "memory_session_states"

    user_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    last_distilled_message_created_at: Mapped[str] = mapped_column(String(128), nullable=False)
    last_distilled_message_ids_at_created_at: Mapped[list[Any]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    updated_at: Mapped[str] = mapped_column(String(128), nullable=False)


class UserRecord(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sort_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    last_login: Mapped[str] = mapped_column(String(128), nullable=False)
    total_interactions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String(128), nullable=False)


class UserProfileRecord(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class AuditLogRecord(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    sort_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    timestamp: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    user: Mapped[str] = mapped_column(String(255), nullable=False)
    resource: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    ip: Mapped[str] = mapped_column(String(128), nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_payload: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSON,
        nullable=True,
    )


class OperationalLogRecord(Base):
    __tablename__ = "operational_logs"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    sort_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    timestamp: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    agent: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False, default="runtime")
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    workflow_run_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    metadata_payload: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSON,
        nullable=True,
    )


class SecurityRuleRecord(Base):
    __tablename__ = "security_rules"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sort_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_triggered: Mapped[str] = mapped_column(String(128), nullable=False, default="")


class SecuritySubjectStateRecord(Base):
    __tablename__ = "security_subject_states"

    user_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    rate_request_timestamps: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    incident_timestamps: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    active_penalty: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[str] = mapped_column(String(128), nullable=False)
