from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskStep:
    id: str
    title: str
    status: str
    agent: str
    message: str
    started_at: str
    finished_at: str | None = None
    tokens: int = 0


@dataclass
class Task:
    id: str
    title: str
    description: str
    status: str
    priority: str
    created_at: str
    agent: str
    tokens: int
    completed_at: str | None = None
    duration: str | None = None
    steps: list[TaskStep] = field(default_factory=list)


@dataclass
class Agent:
    id: str
    name: str
    description: str
    type: str
    status: str
    enabled: bool
    tasks_completed: int
    tasks_total: int
    avg_response_time: str
    tokens_used: int
    tokens_limit: int
    success_rate: float
    last_active: str


@dataclass
class AuditLog:
    id: str
    timestamp: str
    action: str
    user: str
    resource: str
    status: str
    ip: str
    details: str


@dataclass
class SecurityRule:
    id: str
    name: str
    description: str
    type: str
    enabled: bool
    hit_count: int
    last_triggered: str


@dataclass
class User:
    id: str
    name: str
    email: str
    role: str
    status: str
    last_login: str
    total_interactions: int
    created_at: str


@dataclass
class UserProfile:
    user_id: str
    tags: list[str]
    preferred_language: str
    source_channel: str
    notes: str
    platform_accounts: list[dict[str, str]]
    permissions: list[str]


@dataclass
class Workflow:
    id: str
    name: str
    description: str
    version: str
    status: str
    updated_at: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    trigger: str
    agent_bindings: list[str]
