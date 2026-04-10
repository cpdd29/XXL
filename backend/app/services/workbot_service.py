from copy import deepcopy
from uuid import uuid4

from fastapi import HTTPException, status

from app.models.entities import Agent, SecurityRule, Task, User, Workflow
from app.schemas.dashboard import SummaryMetric, TrendPoint
from app.services.sample_data import (
    build_agents,
    build_audit_logs,
    build_security_rules,
    build_tasks,
    build_user_profiles,
    build_users,
    build_workflows,
)


class WorkBotService:
    def __init__(self) -> None:
        self._agents = build_agents()
        self._audit_logs = build_audit_logs()
        self._security_rules = build_security_rules()
        self._tasks = build_tasks()
        self._users = build_users()
        self._user_profiles = build_user_profiles()
        self._workflows = build_workflows()

    def get_dashboard_stats(self) -> dict[str, object]:
        metrics = [
            SummaryMetric(
                title="活跃 Agent",
                value=len([agent for agent in self._agents if agent.enabled]),
                description=f"{len([agent for agent in self._agents if agent.status == 'running'])} 个运行中",
                trend_value=8,
                trend_positive=True,
            ),
            SummaryMetric(
                title="工作流",
                value=len(self._workflows),
                description="当前已配置工作流",
                trend_value=12,
                trend_positive=True,
            ),
            SummaryMetric(
                title="待处理任务",
                value=len([task for task in self._tasks if task.status in {'pending', 'running'}]),
                description="较昨日减少 23 个",
                trend_value=15,
                trend_positive=False,
            ),
            SummaryMetric(
                title="今日执行",
                value="2.4k",
                description="平均响应 120ms",
                trend_value=5,
                trend_positive=True,
            ),
        ]
        trend = [
            TrendPoint(time="00:00", requests=120, tokens=4500),
            TrendPoint(time="04:00", requests=80, tokens=3200),
            TrendPoint(time="08:00", requests=450, tokens=18000),
            TrendPoint(time="12:00", requests=680, tokens=27200),
            TrendPoint(time="16:00", requests=590, tokens=23600),
            TrendPoint(time="20:00", requests=320, tokens=12800),
            TrendPoint(time="24:00", requests=180, tokens=7200),
        ]
        return {
            "summary_metrics": metrics,
            "trend": trend,
            "agents": self._agents,
            "recent_logs": self._audit_logs[:6],
        }

    def list_dashboard_logs(self) -> list:
        return deepcopy(self._audit_logs)

    def list_tasks(self) -> list[Task]:
        return deepcopy(self._tasks)

    def get_task(self, task_id: str) -> Task:
        task = next((task for task in self._tasks if task.id == task_id), None)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        return deepcopy(task)

    def cancel_task(self, task_id: str) -> Task:
        task = next((task for task in self._tasks if task.id == task_id), None)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        task.status = "cancelled"
        task.duration = task.duration or "--"
        return deepcopy(task)

    def list_agents(self) -> list[Agent]:
        return deepcopy(self._agents)

    def get_agent(self, agent_id: str) -> Agent:
        agent = next((agent for agent in self._agents if agent.id == agent_id), None)
        if agent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
        return deepcopy(agent)

    def reload_agent(self, agent_id: str) -> Agent:
        agent = next((agent for agent in self._agents if agent.id == agent_id), None)
        if agent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
        agent.status = "idle"
        agent.last_active = "刚刚"
        return deepcopy(agent)

    def list_users(self) -> list[User]:
        return deepcopy(self._users)

    def get_user(self, user_id: str) -> User:
        user = next((user for user in self._users if user.id == user_id), None)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return user

    def get_user_profile(self, user_id: str) -> dict:
        self.get_user(user_id)
        profile = self._user_profiles.get(user_id)
        if profile is None:
            return {
                "user_id": user_id,
                "tags": ["待补充画像"],
                "preferred_language": "zh",
                "source_channel": "unknown",
                "notes": "当前用户尚未沉淀完整画像。",
                "platform_accounts": [],
                "permissions": [],
            }
        return deepcopy(profile.__dict__)

    def update_user_role(self, user_id: str, role: str) -> User:
        user = next((user for user in self._users if user.id == user_id), None)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        user.role = role
        return deepcopy(user)

    def block_user(self, user_id: str) -> User:
        user = next((user for user in self._users if user.id == user_id), None)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        user.status = "suspended"
        return deepcopy(user)

    def list_workflows(self) -> list[Workflow]:
        return deepcopy(self._workflows)

    def get_workflow(self, workflow_id: str) -> Workflow:
        workflow = next((workflow for workflow in self._workflows if workflow.id == workflow_id), None)
        if workflow is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
        return workflow

    def create_workflow(self, payload: dict) -> Workflow:
        workflow = Workflow(
            id=f"wf-{uuid4().hex[:8]}",
            name=payload["name"],
            description=payload.get("description", ""),
            version="1.0",
            status="draft",
            updated_at="2026-04-01 12:00:00",
            nodes=payload.get("nodes", []),
            edges=payload.get("edges", []),
            trigger=payload.get("trigger", "message.keyword"),
            agent_bindings=payload.get("agent_bindings", []),
        )
        self._workflows.insert(0, workflow)
        return deepcopy(workflow)

    def update_workflow(self, workflow_id: str, payload: dict) -> Workflow:
        workflow = self.get_workflow(workflow_id)
        for field, value in payload.items():
            if value is not None:
                setattr(workflow, field, value)
        workflow.updated_at = "2026-04-01 12:10:00"
        index = next(i for i, item in enumerate(self._workflows) if item.id == workflow_id)
        self._workflows[index] = workflow
        return deepcopy(workflow)

    def run_workflow(self, workflow_id: str) -> dict[str, str]:
        self.get_workflow(workflow_id)
        return {
            "workflow_id": workflow_id,
            "message": "Workflow execution started",
            "status": "running",
            "run_id": f"run-{uuid4().hex[:10]}",
        }

    def list_security_rules(self) -> list[SecurityRule]:
        return deepcopy(self._security_rules)

    def update_security_rule(self, rule_id: str, enabled: bool) -> SecurityRule:
        rule = next((rule for rule in self._security_rules if rule.id == rule_id), None)
        if rule is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
        rule.enabled = enabled
        return deepcopy(rule)
