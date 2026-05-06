from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import logging
from typing import Any

from app.modules.agent_config.registries import agent_service as agent_registry_service
from app.modules.agent_config.registries.brain_skill_service import brain_skill_service
from app.modules.agent_config.registries.tool_source_service import tool_source_service
from app.modules.dispatch.workflow_runtime.mandatory_workflow_registry_service import (
    FREE_AGENT_WORKFLOW_ID,
    PROFESSIONAL_AGENT_WORKFLOW_ID,
)
from app.platform.messaging.nats_event_bus import nats_event_bus
from app.platform.observability.operational_log_service import append_realtime_event
from app.platform.persistence.persistence_service import persistence_service
from app.platform.persistence.runtime_store import store

logger = logging.getLogger(__name__)

GROUPS_SETTING_KEY = "dispatch.requirement_dispatch_agent.groups"
DISPATCHER_AGENT_ID = "requirement_dispatcher"
DISPATCHER_AGENT_NAME = "需求分发 Agent"
DEVELOPMENT_SESSION_STATE = "development_group_ready"
DEVELOPMENT_STATE_LABEL = "已完成需求下发"
DRAFT_WARNING = "当前未配置已启用模型，开发组已按草稿模式保留。"
FRONTEND_HINTS = {"html", "h5", "web", "页面", "前端", "官网", "ui", "vue", "react"}
BACKEND_HINTS = {"api", "后端", "接口", "服务端", "service", "数据库", "db", "mysql", "postgres", "nats"}
INTEGRATION_HINTS = {"联调", "集成", "对接", "接入", "部署", "上线", "发布", "验收"}
OCR_HINTS = {"ocr", "图片", "图像", "识别", "截图"}
MULTI_AGENT_HINTS = {"并且", "同时", "以及", "多页面", "多模块", "全流程", "端到端", "小组"}


ROLE_LIBRARY: dict[str, dict[str, Any]] = {
    "fullstack": {
        "role_key": "fullstack",
        "name": "全栈开发 Agent",
        "agent_type": "default",
        "focus": "负责需求的端到端实现、联调与交付整理。",
        "workflow_id": FREE_AGENT_WORKFLOW_ID,
    },
    "frontend": {
        "role_key": "frontend",
        "name": "前端开发 Agent",
        "agent_type": "default",
        "focus": "负责页面结构、交互体验与前端实现。",
        "workflow_id": FREE_AGENT_WORKFLOW_ID,
    },
    "backend": {
        "role_key": "backend",
        "name": "后端开发 Agent",
        "agent_type": "default",
        "focus": "负责接口、服务编排、数据处理与稳定性保障。",
        "workflow_id": FREE_AGENT_WORKFLOW_ID,
    },
    "integration": {
        "role_key": "integration",
        "name": "集成联调 Agent",
        "agent_type": "default",
        "focus": "负责多模块集成、NATS 协同、外部能力接入与联调验证。",
        "workflow_id": FREE_AGENT_WORKFLOW_ID,
    },
    "acceptance": {
        "role_key": "acceptance",
        "name": "验收 Agent",
        "agent_type": "default",
        "focus": "负责对照需求做验收、回归检查和交付判定。",
        "workflow_id": PROFESSIONAL_AGENT_WORKFLOW_ID,
    },
}


class RequirementDispatchService:
    def group_for_task(self, task: dict[str, Any]) -> dict[str, Any] | None:
        return store.clone(self._group_entry_for_task(task))

    def bootstrap(self, *, limit: int = 50) -> dict[str, Any]:
        dispatched = 0
        skipped = 0
        failed = 0

        for task in list(store.tasks)[: max(int(limit), 1)]:
            if not self._needs_dispatch(task):
                skipped += 1
                continue
            try:
                self.dispatch_task(str(task.get("id") or ""), trigger="bootstrap")
                dispatched += 1
            except Exception as exc:  # pragma: no cover - defensive runtime path
                failed += 1
                logger.warning("Requirement dispatch bootstrap failed for task %s: %s", task.get("id"), exc)

        return {
            "ok": failed == 0,
            "dispatched": dispatched,
            "skipped": skipped,
            "failed": failed,
        }

    def dispatch_task(self, task_id: str, *, trigger: str = "task_created") -> dict[str, Any]:
        task = self._find_task_mutable(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        if self._dispatch_completed(task):
            return {
                "ok": True,
                "task": store.clone(task),
                "group": self._group_entry_for_task(task),
                "published": False,
                "message": "Requirement dispatch already completed",
            }

        if not self._needs_dispatch(task):
            return {
                "ok": True,
                "task": store.clone(task),
                "group": self._group_entry_for_task(task),
                "published": False,
                "message": "Task does not require requirement dispatch",
            }

        requirement_summary = self._requirement_summary(task)
        requirement_description = self._requirement_description(task)
        topology, rationale = self._decide_topology(task)
        requested_capabilities = self._requested_capability_bindings(task)
        applied_capabilities = self._apply_available_capability_bindings(
            requested_capabilities,
            tenant_id=self._text(task.get("tenant_id")) or None,
        )
        model_binding = self._default_model_binding()
        provision_warnings = list(applied_capabilities["warnings"])
        if model_binding is None:
            provision_warnings.append(DRAFT_WARNING)

        group_id = self._group_id_for_task(task)
        group_name = self._group_name(task=task, topology=topology)
        roles = self._development_roles(task, topology=topology)
        nats_subjects = self._nats_subjects(group_id=group_id, roles=roles)

        development_agents: list[dict[str, Any]] = []
        for role in roles:
            development_agents.append(
                self._provision_group_agent(
                    task=task,
                    group_id=group_id,
                    group_name=group_name,
                    role=role,
                    requested_capabilities=requested_capabilities,
                    applied_capabilities=applied_capabilities,
                    model_binding=model_binding,
                    nats_subjects=nats_subjects,
                    topology=topology,
                    warnings=provision_warnings,
                )
            )
        acceptance_agent = self._provision_group_agent(
            task=task,
            group_id=group_id,
            group_name=group_name,
            role=ROLE_LIBRARY["acceptance"],
            requested_capabilities=requested_capabilities,
            applied_capabilities=applied_capabilities,
            model_binding=model_binding,
            nats_subjects=nats_subjects,
            topology=topology,
            warnings=provision_warnings,
        )

        lead_agent = development_agents[0]
        group_entry = self._build_group_entry(
            task=task,
            group_id=group_id,
            group_name=group_name,
            topology=topology,
            rationale=rationale,
            development_agents=development_agents,
            acceptance_agent=acceptance_agent,
            requested_capabilities=requested_capabilities,
            applied_capabilities=applied_capabilities,
            nats_subjects=nats_subjects,
            model_binding=model_binding,
            warnings=provision_warnings,
        )
        self._upsert_group_entry(group_entry)

        execution_plan = self._build_execution_plan(
            topology=topology,
            development_agents=development_agents,
            acceptance_agent=acceptance_agent,
            group_entry=group_entry,
            rationale=rationale,
        )
        summary_line = self._summary_line(
            topology=topology,
            group_name=group_name,
            development_agents=development_agents,
            acceptance_agent=acceptance_agent,
            warnings=provision_warnings,
        )

        route_decision = self._dict(task.get("route_decision"))
        route_decision.update(
            {
                "execution_scope": topology,
                "executionScope": topology,
                "execution_agent_id": str(lead_agent.get("id") or "").strip() or None,
                "executionAgentId": str(lead_agent.get("id") or "").strip() or None,
                "execution_agent": str(lead_agent.get("name") or "").strip() or None,
                "executionAgent": str(lead_agent.get("name") or "").strip() or None,
                "routing_strategy": "requirement_dispatch_agent",
                "routingStrategy": "requirement_dispatch_agent",
                "execution_plan": execution_plan,
                "executionPlan": execution_plan,
                "route_rationale": {
                    "route_reason_summary": summary_line,
                    "dispatch_topology": topology,
                    "decision_source": rationale.get("source"),
                    "decision_score": rationale.get("score"),
                    "reasons": list(rationale.get("reasons") or []),
                },
                "routeRationale": {
                    "route_reason_summary": summary_line,
                    "dispatch_topology": topology,
                    "decision_source": rationale.get("source"),
                    "decision_score": rationale.get("score"),
                    "reasons": list(rationale.get("reasons") or []),
                },
                "dispatch_status": "completed",
                "dispatchStatus": "completed",
                "group_id": group_id,
                "groupId": group_id,
            }
        )
        task["route_decision"] = route_decision

        manager_packet = self._dict(task.get("manager_packet"))
        manager_packet.update(
            {
                "manager_role": "requirement_dispatcher",
                "manager_action": "development_group_provisioned",
                "next_owner": group_name if topology == "multi_agent" else str(lead_agent.get("name") or "").strip(),
                "delivery_mode": "development_group",
                "response_contract": "development_group_plan",
                "task_shape": "multi_step" if topology == "multi_agent" else "single_step",
                "decomposition_hint": "parallel_specialist_implementation"
                if topology == "multi_agent"
                else "direct_execute",
                "session_state": DEVELOPMENT_SESSION_STATE,
                "state_label": DEVELOPMENT_STATE_LABEL,
                "handoff_summary": summary_line,
            }
        )
        task["manager_packet"] = manager_packet

        brain_dispatch_summary = self._dict(task.get("brain_dispatch_summary"))
        brain_dispatch_summary.update(
            {
                "dispatch_type": "requirement_group_provisioned",
                "execution_agent": group_name if topology == "multi_agent" else str(lead_agent.get("name") or "").strip(),
                "manager_action": manager_packet["manager_action"],
                "next_owner": manager_packet["next_owner"],
                "delivery_mode": manager_packet["delivery_mode"],
                "response_contract": manager_packet["response_contract"],
                "execution_scope": topology,
                "execution_topology": topology,
                "summary_line": summary_line,
                "routing_strategy": route_decision["routing_strategy"],
                "session_state": DEVELOPMENT_SESSION_STATE,
                "state_label": DEVELOPMENT_STATE_LABEL,
            }
        )
        task["brain_dispatch_summary"] = brain_dispatch_summary

        state_machine = self._dict(task.get("state_machine"))
        state_machine.update(
            {
                "dispatch_state": "dispatched",
                "task_status": str(task.get("status") or "pending").strip() or "pending",
                "session_state": DEVELOPMENT_SESSION_STATE,
                "execution_topology": topology,
                "development_group_id": group_id,
                "development_agent_count": len(development_agents),
                "acceptance_agent_id": str(acceptance_agent.get("id") or "").strip() or None,
            }
        )
        task["state_machine"] = state_machine
        task["agent"] = manager_packet["next_owner"]

        self._upsert_requirement_dispatch_steps(
            task=task,
            group_entry=group_entry,
            lead_agent=lead_agent,
            summary_line=summary_line,
        )
        self._persist_task(task)

        published = nats_event_bus.publish_json(
            nats_subjects["broadcast"],
            {
                "event_name": "requirement.dispatch.group.provisioned",
                "aggregate": {
                    "type": "requirement_group",
                    "id": group_id,
                },
                "source": {
                    "service": "requirement_dispatch_agent",
                    "agent_id": DISPATCHER_AGENT_ID,
                    "trigger": trigger,
                },
                "payload": {
                    "task_id": str(task.get("id") or "").strip(),
                    "task_title": str(task.get("title") or "").strip(),
                    "group_id": group_id,
                    "group_name": group_name,
                    "topology": topology,
                    "lead_agent_id": str(lead_agent.get("id") or "").strip() or None,
                    "acceptance_agent_id": str(acceptance_agent.get("id") or "").strip() or None,
                    "member_agent_ids": [str(item.get("id") or "").strip() for item in development_agents],
                },
            },
        )

        append_realtime_event(
            agent=DISPATCHER_AGENT_NAME,
            message=f"任务 {task.get('id')} 已完成需求下发，生成 {group_name}",
            type_="success",
            source="requirement_dispatch",
            trace_id=self._text(task.get("trace_id")) or None,
            task_id=str(task.get("id") or "").strip() or None,
            metadata={
                "event": "requirement_dispatch_completed",
                "group_id": group_id,
                "topology": topology,
                "published": published,
                "draft_mode": model_binding is None,
            },
        )

        return {
            "ok": True,
            "task": store.clone(task),
            "group": store.clone(group_entry),
            "published": published,
            "message": "Requirement dispatch completed",
        }

    def _needs_dispatch(self, task: dict[str, Any]) -> bool:
        route_decision = self._dict(task.get("route_decision"))
        manager_packet = self._dict(task.get("manager_packet"))
        execution_scope = self._text(
            route_decision.get("execution_scope") or route_decision.get("executionScope")
        )
        if execution_scope != "pending_dispatch":
            return False
        return self._text(manager_packet.get("manager_action")) == "handoff_to_dispatch_queue"

    def _dispatch_completed(self, task: dict[str, Any]) -> bool:
        manager_packet = self._dict(task.get("manager_packet"))
        state_machine = self._dict(task.get("state_machine"))
        return (
            self._text(manager_packet.get("manager_action")) == "development_group_provisioned"
            or self._text(manager_packet.get("session_state")) == DEVELOPMENT_SESSION_STATE
            or self._text(state_machine.get("session_state")) == DEVELOPMENT_SESSION_STATE
        )

    def _find_task_mutable(self, task_id: str) -> dict[str, Any] | None:
        normalized_task_id = self._text(task_id)
        if not normalized_task_id:
            return None
        for task in store.tasks:
            if self._text(task.get("id")) == normalized_task_id:
                return task
        return None

    def _group_id_for_task(self, task: dict[str, Any]) -> str:
        return self._stable_identifier(f"reqgrp-{self._text(task.get('id')) or 'task'}", max_length=48)

    def _group_name(self, *, task: dict[str, Any], topology: str) -> str:
        suffix = "多智能体开发组" if topology == "multi_agent" else "单智能体开发组"
        task_label = self._text(task.get("id")) or "任务"
        return f"任务 {task_label} · {suffix}"

    def _requirement_payload(self, task: dict[str, Any]) -> dict[str, Any]:
        return self._dict(task.get("requirement_payload"))

    def _requirement_summary(self, task: dict[str, Any]) -> str:
        payload = self._requirement_payload(task)
        return (
            self._text(payload.get("summary"))
            or self._text(task.get("title"))
            or "未命名需求"
        )

    def _requirement_description(self, task: dict[str, Any]) -> str:
        payload = self._requirement_payload(task)
        details = self._text(payload.get("details"))
        if details:
            return details
        return self._text(task.get("description")) or self._requirement_summary(task)

    def _decide_topology(self, task: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        payload = self._requirement_payload(task)
        explicit = self._text(
            payload.get("execution_topology")
            or payload.get("executionTopology")
            or payload.get("topology")
        ).lower()
        if explicit in {"single", "single_agent", "single-agent"}:
            return "single_agent", {
                "source": "explicit",
                "score": 0,
                "reasons": ["requirement_payload 明确指定 single_agent"],
            }
        if explicit in {"multi", "multi_agent", "multi-agent"}:
            return "multi_agent", {
                "source": "explicit",
                "score": 100,
                "reasons": ["requirement_payload 明确指定 multi_agent"],
            }

        text = f"{self._requirement_summary(task)}\n{self._requirement_description(task)}".lower()
        score = 0
        reasons: list[str] = []
        if len(text) >= 120:
            score += 1
            reasons.append("需求描述较长，信息量偏大")
        if self._contains_any(text, MULTI_AGENT_HINTS):
            score += 1
            reasons.append("需求描述出现并行或多模块提示")
        if self._contains_any(text, FRONTEND_HINTS) and self._contains_any(text, BACKEND_HINTS):
            score += 2
            reasons.append("同时包含前端与后端实现特征")
        if self._contains_any(text, INTEGRATION_HINTS):
            score += 1
            reasons.append("包含联调/集成/交付类工作")
        if self._contains_any(text, OCR_HINTS) and self._contains_any(text, BACKEND_HINTS | FRONTEND_HINTS):
            score += 1
            reasons.append("包含图片 OCR 等能力接入要求")
        topology = "multi_agent" if score >= 3 else "single_agent"
        if not reasons:
            reasons.append("需求边界清晰，优先按单智能体落地")
        return topology, {
            "source": "heuristic",
            "score": score,
            "reasons": reasons,
        }

    def _development_roles(self, task: dict[str, Any], *, topology: str) -> list[dict[str, Any]]:
        if topology == "single_agent":
            return [deepcopy(ROLE_LIBRARY["fullstack"])]

        text = f"{self._requirement_summary(task)}\n{self._requirement_description(task)}".lower()
        roles: list[dict[str, Any]] = []
        if self._contains_any(text, FRONTEND_HINTS):
            roles.append(deepcopy(ROLE_LIBRARY["frontend"]))
        if self._contains_any(text, BACKEND_HINTS) or self._contains_any(text, OCR_HINTS):
            roles.append(deepcopy(ROLE_LIBRARY["backend"]))
        if self._contains_any(text, INTEGRATION_HINTS) or self._contains_any(text, OCR_HINTS):
            roles.append(deepcopy(ROLE_LIBRARY["integration"]))
        if not roles:
            roles = [
                deepcopy(ROLE_LIBRARY["frontend"]),
                deepcopy(ROLE_LIBRARY["integration"]),
            ]

        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in roles:
            role_key = self._text(item.get("role_key"))
            if not role_key or role_key in seen:
                continue
            seen.add(role_key)
            deduped.append(item)
        return deduped

    def _requested_capability_bindings(self, task: dict[str, Any]) -> dict[str, list[str]]:
        payload = self._requirement_payload(task)
        requested_skill_ids = self._dedupe_identifiers(
            payload.get("skill_ids")
            or payload.get("skillIds")
            or payload.get("skills")
            or []
        )
        requested_tool_ids = self._dedupe_identifiers(
            payload.get("tool_ids")
            or payload.get("toolIds")
            or payload.get("mcp_tool_ids")
            or payload.get("mcpToolIds")
            or payload.get("mcp")
            or []
        )
        return {
            "skill_ids": requested_skill_ids,
            "tool_ids": requested_tool_ids,
        }

    def _apply_available_capability_bindings(
        self,
        requested: dict[str, list[str]],
        *,
        tenant_id: str | None,
    ) -> dict[str, Any]:
        requested_skill_ids = self._dedupe_identifiers(requested.get("skill_ids") or [])
        requested_tool_ids = self._dedupe_identifiers(requested.get("tool_ids") or [])

        available_skill_ids = {
            str(item.get("id") or "").strip()
            for item in brain_skill_service.list_skills(
                tenant_id=tenant_id,
                include_all_tenants=True,
            ).get("items", [])
            if str(item.get("id") or "").strip()
        }
        available_tool_ids = {
            str(item.get("id") or "").strip()
            for item in tool_source_service.list_tools(
                tenant_id=tenant_id,
                include_all_tenants=True,
            )
            if str(item.get("id") or "").strip()
        }

        applied_skill_ids = [item for item in requested_skill_ids if item in available_skill_ids]
        applied_tool_ids = [item for item in requested_tool_ids if item in available_tool_ids]
        warnings: list[str] = []
        missing_skill_ids = [item for item in requested_skill_ids if item not in available_skill_ids]
        missing_tool_ids = [item for item in requested_tool_ids if item not in available_tool_ids]
        if missing_skill_ids:
            warnings.append(f"以下 Skill 当前不可绑定，已仅保留配置意图：{', '.join(missing_skill_ids)}")
        if missing_tool_ids:
            warnings.append(f"以下 MCP/Tool 当前不可绑定，已仅保留配置意图：{', '.join(missing_tool_ids)}")
        return {
            "requested_skill_ids": requested_skill_ids,
            "requested_tool_ids": requested_tool_ids,
            "applied_skill_ids": applied_skill_ids,
            "applied_tool_ids": applied_tool_ids,
            "warnings": warnings,
        }

    def _default_model_binding(self) -> dict[str, str] | None:
        enabled_models = getattr(agent_registry_service, "_enabled_provider_models")()
        if not enabled_models:
            return None
        for provider_key in ("codex", "claude", "openai", "deepseek", "kimi", "gemini", "minimax", "openapi"):
            if provider_key in enabled_models:
                return deepcopy(enabled_models[provider_key])
        first = next(iter(enabled_models.values()), None)
        return deepcopy(first) if isinstance(first, dict) else None

    def _nats_subjects(self, *, group_id: str, roles: list[dict[str, Any]]) -> dict[str, Any]:
        base = f"brain.requirement.groups.{group_id}"
        members = {
            self._text(role.get("role_key")): f"{base}.members.{self._text(role.get('role_key'))}"
            for role in roles
            if self._text(role.get("role_key"))
        }
        members["acceptance"] = f"{base}.members.acceptance"
        return {
            "broadcast": f"{base}.broadcast",
            "coordination": f"{base}.coordination",
            "leader": f"{base}.leader",
            "acceptance": members["acceptance"],
            "members": members,
        }

    def _provision_group_agent(
        self,
        *,
        task: dict[str, Any],
        group_id: str,
        group_name: str,
        role: dict[str, Any],
        requested_capabilities: dict[str, list[str]],
        applied_capabilities: dict[str, Any],
        model_binding: dict[str, str] | None,
        nats_subjects: dict[str, Any],
        topology: str,
        warnings: list[str],
    ) -> dict[str, Any]:
        role_key = self._text(role.get("role_key")) or "agent"
        agent_id = self._stable_identifier(
            f"reqgrp-{self._text(task.get('id')) or 'task'}-{role_key}",
            max_length=63,
        )
        existing = next(
            (
                item
                for item in store.agents
                if self._text(item.get("id")) == agent_id
            ),
            None,
        )
        name = f"任务 {self._text(task.get('id')) or ''} · {self._text(role.get('name')) or '开发 Agent'}".strip()
        description = (
            f"由需求分发自动生成，隶属于 {group_name}，"
            f"负责 {self._text(role.get('focus')) or '当前需求执行'}"
        )
        enabled = model_binding is not None
        agent = deepcopy(existing) if isinstance(existing, dict) else {
            "id": agent_id,
            "tasks_completed": 0,
            "tasks_total": 0,
            "avg_response_time": "--",
            "tokens_used": 0,
            "tokens_limit": 0,
            "success_rate": 0.0,
            "last_active": "未运行",
        }
        agent.update(
            {
                "name": name,
                "description": description,
                "type": self._text(role.get("agent_type")) or "default",
                "status": "idle" if enabled else "maintenance",
                "enabled": enabled,
            }
        )

        snapshot = getattr(agent_registry_service, "_build_manual_config_snapshot")(agent)
        snapshot["status"] = "generated"
        snapshot["directory"] = f"generated://requirement_dispatch/{group_id}/{role_key}"
        snapshot["version"] = "generated.requirement_dispatch.v1"
        snapshot["files_loaded"] = ["soul.md"]
        snapshot["warnings"] = list(dict.fromkeys(warnings))
        snapshot["soul"] = self._build_agent_soul(
            task=task,
            group_name=group_name,
            role=role,
            topology=topology,
            nats_subjects=nats_subjects,
        )
        snapshot["tools"] = {
            "requested_tool_ids": list(applied_capabilities.get("requested_tool_ids") or []),
            "bound_tool_ids": list(applied_capabilities.get("applied_tool_ids") or []),
            "nats_subjects": deepcopy(nats_subjects),
        }
        if model_binding is not None:
            snapshot = getattr(agent_registry_service, "_apply_model_binding_to_snapshot")(
                snapshot,
                agent=agent,
                provider_key=self._text(model_binding.get("provider_key")) or None,
                model=self._text(model_binding.get("model")) or None,
                source="requirement_dispatch_agent",
            )
        snapshot = getattr(agent_registry_service, "_apply_skill_binding_to_snapshot")(
            snapshot,
            agent=agent,
            skill_ids=list(applied_capabilities.get("applied_skill_ids") or []),
            source="requirement_dispatch_agent",
        )
        snapshot = getattr(agent_registry_service, "_apply_tool_binding_to_snapshot")(
            snapshot,
            agent=agent,
            tool_ids=list(applied_capabilities.get("applied_tool_ids") or []),
            source="requirement_dispatch_agent",
        )
        snapshot = getattr(agent_registry_service, "_apply_workflow_binding_to_snapshot")(
            snapshot,
            agent=agent,
            agent_workflow_id=self._text(role.get("workflow_id")) or None,
            input_contract={},
            output_contract={},
            contract_version="agent-workflow-contract-v1",
            source="requirement_dispatch_agent",
        )
        metadata = {
            "source": "requirement_dispatch_agent",
            "provisioned_by": DISPATCHER_AGENT_ID,
            "provisioned_at": self._now_iso(),
            "provision_state": "ready" if enabled else "draft",
            "group_id": group_id,
            "group_name": group_name,
            "group_role": role_key,
            "task_id": self._text(task.get("id")) or None,
            "task_title": self._text(task.get("title")) or None,
            "tenant_id": self._text(task.get("tenant_id")) or None,
            "tenant_name": self._text(task.get("tenant_name")) or None,
            "topology": topology,
            "requested_skill_ids": list(requested_capabilities.get("skill_ids") or []),
            "requested_tool_ids": list(requested_capabilities.get("tool_ids") or []),
            "applied_skill_ids": list(applied_capabilities.get("applied_skill_ids") or []),
            "applied_tool_ids": list(applied_capabilities.get("applied_tool_ids") or []),
            "nats_subject": self._text((nats_subjects.get("members") or {}).get(role_key)) or None,
        }
        snapshot = getattr(agent_registry_service, "_apply_agent_metadata_to_snapshot")(
            snapshot,
            agent=agent,
            metadata=metadata,
            source="requirement_dispatch_agent",
        )
        agent["config_snapshot"] = snapshot
        agent["config_summary"] = getattr(agent_registry_service, "_build_agent_config_summary_with_bindings")(
            snapshot,
            bound_tool_ids=list(applied_capabilities.get("applied_tool_ids") or []),
        )
        cached = getattr(agent_registry_service, "_sync_cached_agent")(agent)
        getattr(agent_registry_service, "_persist_agent")(cached)
        return getattr(agent_registry_service, "_decorate_agent")(cached)

    def _build_agent_soul(
        self,
        *,
        task: dict[str, Any],
        group_name: str,
        role: dict[str, Any],
        topology: str,
        nats_subjects: dict[str, Any],
    ) -> str:
        role_key = self._text(role.get("role_key")) or "agent"
        subject = self._text((nats_subjects.get("members") or {}).get(role_key)) or nats_subjects.get("broadcast")
        summary = self._requirement_summary(task)
        description = self._requirement_description(task)
        return "\n".join(
            [
                f"# {self._text(role.get('name')) or '开发 Agent'} Soul",
                "",
                f"你属于开发组 `{group_name}`，当前任务是 `{summary}`。",
                f"你的职责：{self._text(role.get('focus')) or '完成当前需求交付。'}",
                "",
                "## 协作约束",
                "- 所有输出都必须围绕当前需求，不擅自扩展范围。",
                "- 进度、阻塞与交付说明通过 NATS 主题同步。",
                f"- 当前专属主题：`{subject}`。",
                f"- 当前编排模式：`{topology}`。",
                "",
                "## 需求上下文",
                f"- task_id: {self._text(task.get('id')) or '-'}",
                f"- tenant_id: {self._text(task.get('tenant_id')) or '-'}",
                f"- requirement_summary: {summary}",
                f"- requirement_details: {description}",
            ]
        ).strip()

    def _build_group_entry(
        self,
        *,
        task: dict[str, Any],
        group_id: str,
        group_name: str,
        topology: str,
        rationale: dict[str, Any],
        development_agents: list[dict[str, Any]],
        acceptance_agent: dict[str, Any],
        requested_capabilities: dict[str, list[str]],
        applied_capabilities: dict[str, Any],
        nats_subjects: dict[str, Any],
        model_binding: dict[str, str] | None,
        warnings: list[str],
    ) -> dict[str, Any]:
        created_at = self._now_iso()
        return {
            "id": group_id,
            "name": group_name,
            "status": "provisioned" if model_binding is not None else "draft",
            "task_id": self._text(task.get("id")) or None,
            "task_title": self._text(task.get("title")) or None,
            "tenant_id": self._text(task.get("tenant_id")) or None,
            "tenant_name": self._text(task.get("tenant_name")) or None,
            "topology": topology,
            "dispatcher_agent_id": DISPATCHER_AGENT_ID,
            "development_agent_ids": [self._text(item.get("id")) for item in development_agents if self._text(item.get("id"))],
            "acceptance_agent_id": self._text(acceptance_agent.get("id")) or None,
            "development_agents": [
                {
                    "id": self._text(item.get("id")) or None,
                    "name": self._text(item.get("name")) or None,
                    "role": self._text((item.get("metadata") or {}).get("group_role")) or None,
                }
                for item in development_agents
            ],
            "acceptance_agent": {
                "id": self._text(acceptance_agent.get("id")) or None,
                "name": self._text(acceptance_agent.get("name")) or None,
            },
            "requested_skill_ids": list(requested_capabilities.get("skill_ids") or []),
            "requested_tool_ids": list(requested_capabilities.get("tool_ids") or []),
            "applied_skill_ids": list(applied_capabilities.get("applied_skill_ids") or []),
            "applied_tool_ids": list(applied_capabilities.get("applied_tool_ids") or []),
            "nats_subjects": deepcopy(nats_subjects),
            "rationale": deepcopy(rationale),
            "timeline": self._build_group_timeline(
                task=task,
                group_id=group_id,
                group_name=group_name,
                topology=topology,
                rationale=rationale,
                development_agents=development_agents,
                acceptance_agent=acceptance_agent,
                requested_capabilities=requested_capabilities,
                applied_capabilities=applied_capabilities,
                nats_subjects=nats_subjects,
                model_binding=model_binding,
                warnings=warnings,
                created_at=created_at,
            ),
            "warnings": list(dict.fromkeys(warnings)),
            "model_binding": deepcopy(model_binding) if isinstance(model_binding, dict) else None,
            "created_at": created_at,
            "updated_at": created_at,
        }

    def _build_group_timeline(
        self,
        *,
        task: dict[str, Any],
        group_id: str,
        group_name: str,
        topology: str,
        rationale: dict[str, Any],
        development_agents: list[dict[str, Any]],
        acceptance_agent: dict[str, Any],
        requested_capabilities: dict[str, list[str]],
        applied_capabilities: dict[str, Any],
        nats_subjects: dict[str, Any],
        model_binding: dict[str, str] | None,
        warnings: list[str],
        created_at: str,
    ) -> list[dict[str, Any]]:
        requested_skill_ids = list(requested_capabilities.get("skill_ids") or [])
        requested_tool_ids = list(requested_capabilities.get("tool_ids") or [])
        applied_skill_ids = list(applied_capabilities.get("applied_skill_ids") or [])
        applied_tool_ids = list(applied_capabilities.get("applied_tool_ids") or [])
        decision_reasons = [str(item or "").strip() for item in list(rationale.get("reasons") or []) if str(item or "").strip()]

        timeline: list[dict[str, Any]] = [
            {
                "id": f"{group_id}:group-created",
                "kind": "group_created",
                "title": "创建开发组",
                "detail": (
                    f"需求分发 Agent 已为任务 {self._text(task.get('id')) or '-'} 创建开发组 {group_name}，"
                    f"执行拓扑为 {topology}。"
                ),
                "timestamp": created_at,
                "actor_agent_id": DISPATCHER_AGENT_ID,
                "actor_agent_name": DISPATCHER_AGENT_NAME,
                "metadata": {
                    "group_id": group_id,
                    "task_id": self._text(task.get("id")) or None,
                    "topology": topology,
                    "decision_source": self._text(rationale.get("source")) or None,
                    "decision_reasons": decision_reasons,
                },
            },
            {
                "id": f"{group_id}:capability-planned",
                "kind": "capability_planned",
                "title": "写入能力编排",
                "detail": (
                    f"请求 Skill {len(requested_skill_ids)} 项、请求 Tool/MCP {len(requested_tool_ids)} 项；"
                    f"实际绑定 Skill {len(applied_skill_ids)} 项、Tool/MCP {len(applied_tool_ids)} 项。"
                ),
                "timestamp": created_at,
                "actor_agent_id": DISPATCHER_AGENT_ID,
                "actor_agent_name": DISPATCHER_AGENT_NAME,
                "metadata": {
                    "requested_skill_ids": requested_skill_ids,
                    "requested_tool_ids": requested_tool_ids,
                    "applied_skill_ids": applied_skill_ids,
                    "applied_tool_ids": applied_tool_ids,
                    "warnings": list(dict.fromkeys(warnings)),
                    "model_binding": deepcopy(model_binding) if isinstance(model_binding, dict) else None,
                },
            },
        ]

        for item in development_agents:
            metadata = self._dict(item.get("metadata"))
            agent_id = self._text(item.get("id")) or None
            role = self._text(metadata.get("group_role")) or "development"
            provisioned_at = self._text(metadata.get("provisioned_at")) or created_at
            timeline.append(
                {
                    "id": f"{group_id}:member:{agent_id or role}",
                    "kind": "development_agent_provisioned",
                    "title": "生成开发成员",
                    "detail": (
                        f"{self._text(item.get('name')) or '开发 Agent'} 已加入开发组，"
                        f"承担 {role} 角色。"
                    ),
                    "timestamp": provisioned_at,
                    "actor_agent_id": agent_id,
                    "actor_agent_name": self._text(item.get("name")) or None,
                    "metadata": {
                        "role": role,
                        "agent_id": agent_id,
                        "provision_state": self._text(metadata.get("provision_state")) or None,
                        "nats_subject": self._text(metadata.get("nats_subject")) or None,
                        "requested_skill_ids": list(metadata.get("requested_skill_ids") or []),
                        "requested_tool_ids": list(metadata.get("requested_tool_ids") or []),
                        "applied_skill_ids": list(metadata.get("applied_skill_ids") or []),
                        "applied_tool_ids": list(metadata.get("applied_tool_ids") or []),
                    },
                }
            )

        acceptance_metadata = self._dict(acceptance_agent.get("metadata"))
        acceptance_provisioned_at = self._text(acceptance_metadata.get("provisioned_at")) or created_at
        timeline.append(
            {
                "id": f"{group_id}:acceptance",
                "kind": "acceptance_agent_provisioned",
                "title": "生成验收成员",
                "detail": (
                    f"{self._text(acceptance_agent.get('name')) or ROLE_LIBRARY['acceptance']['name']} "
                    "已加入开发组，承担最终验收。"
                ),
                "timestamp": acceptance_provisioned_at,
                "actor_agent_id": self._text(acceptance_agent.get("id")) or None,
                "actor_agent_name": self._text(acceptance_agent.get("name")) or None,
                "metadata": {
                    "role": self._text(acceptance_metadata.get("group_role")) or "acceptance",
                    "agent_id": self._text(acceptance_agent.get("id")) or None,
                    "provision_state": self._text(acceptance_metadata.get("provision_state")) or None,
                    "nats_subject": self._text(acceptance_metadata.get("nats_subject")) or None,
                },
            }
        )

        timeline.append(
            {
                "id": f"{group_id}:nats-subjects",
                "kind": "coordination_allocated",
                "title": "分配协作主题",
                "detail": "已为开发组分配广播、协调、负责人及成员级 NATS 通信主题。",
                "timestamp": created_at,
                "actor_agent_id": DISPATCHER_AGENT_ID,
                "actor_agent_name": DISPATCHER_AGENT_NAME,
                "metadata": deepcopy(nats_subjects),
            }
        )
        return timeline

    def _build_execution_plan(
        self,
        *,
        topology: str,
        development_agents: list[dict[str, Any]],
        acceptance_agent: dict[str, Any],
        group_entry: dict[str, Any],
        rationale: dict[str, Any],
    ) -> dict[str, Any]:
        steps = [
            {
                "id": f"develop-{index + 1}",
                "branch_id": f"branch-{self._text((item.get('metadata') or {}).get('group_role')) or index + 1}",
                "intent": "implementation",
                "role": self._text((item.get("metadata") or {}).get("group_role")) or "development",
                "completion_policy": "required",
                "depends_on": [],
                "execution_agent_id": self._text(item.get("id")) or None,
                "execution_agent": self._text(item.get("name")) or None,
                "agent_type": self._text(item.get("type")) or None,
            }
            for index, item in enumerate(development_agents)
        ]
        return {
            "plan_type": "multi_agent" if topology == "multi_agent" else "single_path",
            "coordination_mode": "parallel" if topology == "multi_agent" else "serial",
            "planner": "requirement_dispatch_agent",
            "aggregator": self._text(acceptance_agent.get("id")) or DISPATCHER_AGENT_ID,
            "step_count": len(steps),
            "planned_agent_count": len(steps),
            "summary": " + ".join(
                self._text(item.get("name")) or "开发 Agent"
                for item in development_agents
            ),
            "steps": steps,
            "fan_out": {
                "mode": "parallel" if topology == "multi_agent" else "serial",
                "branch_count": len(steps),
                "branches": [
                    {
                        "id": step["branch_id"],
                        "step_id": step["id"],
                        "role": step["role"],
                        "execution_agent": step["execution_agent"],
                        "execution_agent_id": step["execution_agent_id"],
                    }
                    for step in steps
                ],
            },
            "fan_in": {
                "strategy": "acceptance_review",
                "aggregator": self._text(acceptance_agent.get("name")) or ROLE_LIBRARY["acceptance"]["name"],
                "aggregator_id": self._text(acceptance_agent.get("id")) or None,
                "output_contract": "requirement_delivery_review",
            },
            "merge_strategy": "acceptance_gate",
            "winner_strategy": "all_required",
            "quorum": {
                "required_completed_agents": len(steps),
            },
            "metadata": {
                "group_id": self._text(group_entry.get("id")) or None,
                "group_name": self._text(group_entry.get("name")) or None,
                "acceptance_agent_id": self._text(acceptance_agent.get("id")) or None,
                "acceptance_agent_name": self._text(acceptance_agent.get("name")) or None,
                "nats_subjects": deepcopy(group_entry.get("nats_subjects") or {}),
                "warnings": list(group_entry.get("warnings") or []),
                "decision_source": self._text(rationale.get("source")) or None,
                "decision_reasons": list(rationale.get("reasons") or []),
            },
        }

    def _summary_line(
        self,
        *,
        topology: str,
        group_name: str,
        development_agents: list[dict[str, Any]],
        acceptance_agent: dict[str, Any],
        warnings: list[str],
    ) -> str:
        member_count = len(development_agents)
        acceptance_name = self._text(acceptance_agent.get("name")) or ROLE_LIBRARY["acceptance"]["name"]
        warning_suffix = f"；注意：{'；'.join(warnings)}" if warnings else ""
        return (
            f"已完成需求下发，建立 {group_name}，"
            f"采用 {topology}，包含 {member_count} 个开发 Agent，"
            f"验收责任由 {acceptance_name} 承担{warning_suffix}"
        )

    def _upsert_requirement_dispatch_steps(
        self,
        *,
        task: dict[str, Any],
        group_entry: dict[str, Any],
        lead_agent: dict[str, Any],
        summary_line: str,
    ) -> None:
        task_id = self._text(task.get("id")) or "task"
        now = store.now_string()
        steps = deepcopy(store.task_steps.get(task_id, []))
        if not steps:
            steps = []

        completed_step_id = f"{task_id}-requirement-dispatch"
        ready_step_id = f"{task_id}-development-ready"
        completed_step = {
            "id": completed_step_id,
            "title": "需求下发完成",
            "status": "completed",
            "agent": DISPATCHER_AGENT_NAME,
            "started_at": now,
            "finished_at": now,
            "message": summary_line,
            "metadata": {
                "group_id": self._text(group_entry.get("id")) or None,
                "topology": self._text(group_entry.get("topology")) or None,
            },
            "tokens": 0,
        }
        ready_step = {
            "id": ready_step_id,
            "title": "等待开发启动",
            "status": "pending",
            "agent": self._text(lead_agent.get("name")) or self._text(group_entry.get("name")) or "开发组",
            "started_at": now,
            "finished_at": None,
            "message": (
                f"开发组已建立，当前负责人：{self._text(lead_agent.get('name')) or '-'}；"
                f"开发组编号：{self._text(group_entry.get('id')) or '-'}"
            ),
            "metadata": {
                "group_id": self._text(group_entry.get("id")) or None,
                "topology": self._text(group_entry.get("topology")) or None,
                "acceptance_agent_id": self._text((group_entry.get("acceptance_agent") or {}).get("id")) or None,
            },
            "tokens": 0,
        }

        replaced = False
        for index, step in enumerate(steps):
            step_id = self._text(step.get("id"))
            if step_id == completed_step_id:
                steps[index] = completed_step
                replaced = True
            elif step_id == ready_step_id:
                steps[index] = ready_step
                replaced = True

        if not any(self._text(step.get("id")) == completed_step_id for step in steps):
            if steps:
                last_index = len(steps) - 1
                last_step = deepcopy(steps[last_index])
                last_step.update(completed_step)
                steps[last_index] = last_step
            else:
                steps.append(completed_step)
        else:
            steps = [completed_step if self._text(step.get("id")) == completed_step_id else step for step in steps]

        if not any(self._text(step.get("id")) == ready_step_id for step in steps):
            steps.append(ready_step)
        else:
            steps = [ready_step if self._text(step.get("id")) == ready_step_id else step for step in steps]

        store.task_steps[task_id] = steps

    def _persist_task(self, task: dict[str, Any]) -> None:
        task_steps = store.task_steps.get(self._text(task.get("id")) or "", [])
        persist_execution_state = getattr(persistence_service, "persist_execution_state", None)
        if callable(persist_execution_state):
            if persist_execution_state(task=task, task_steps=task_steps):
                return
            if getattr(persistence_service, "enabled", False):
                return
        persistence_service.persist_runtime_state()

    def _group_registry(self) -> list[dict[str, Any]]:
        payload, authoritative = persistence_service.read_system_setting(GROUPS_SETTING_KEY)
        if authoritative and isinstance(payload, dict):
            stored_payload = payload.get("payload")
            if isinstance(stored_payload, dict) and isinstance(stored_payload.get("items"), list):
                items = deepcopy(stored_payload.get("items") or [])
                store.system_settings[GROUPS_SETTING_KEY] = {"items": items}
                return items

        cached = store.system_settings.get(GROUPS_SETTING_KEY)
        if isinstance(cached, dict) and isinstance(cached.get("items"), list):
            return deepcopy(cached.get("items") or [])
        return []

    def _upsert_group_entry(self, entry: dict[str, Any]) -> None:
        items = self._group_registry()
        group_id = self._text(entry.get("id"))
        if not group_id:
            return
        updated = False
        for index, item in enumerate(items):
            if self._text(item.get("id")) != group_id:
                continue
            next_entry = deepcopy(entry)
            next_entry["created_at"] = self._text(item.get("created_at")) or self._now_iso()
            next_entry["updated_at"] = self._now_iso()
            items[index] = next_entry
            updated = True
            break
        if not updated:
            items.append(deepcopy(entry))

        payload = {"items": items}
        store.system_settings[GROUPS_SETTING_KEY] = deepcopy(payload)
        persist_setting = getattr(persistence_service, "persist_system_setting", None)
        if callable(persist_setting):
            persist_setting(
                key=GROUPS_SETTING_KEY,
                payload=payload,
                updated_at=store.now_string(),
            )

    def _group_entry_for_task(self, task: dict[str, Any]) -> dict[str, Any] | None:
        group_id = self._text((self._dict(task.get("route_decision"))).get("group_id")) or self._group_id_for_task(task)
        for item in self._group_registry():
            if self._text(item.get("id")) == group_id:
                return item
        return None

    @staticmethod
    def _text(value: object) -> str:
        return str(value or "").strip()

    @staticmethod
    def _dict(value: object) -> dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def _list(value: object) -> list[Any]:
        return list(value) if isinstance(value, list) else []

    @staticmethod
    def _contains_any(text: str, hints: set[str]) -> bool:
        return any(hint in text for hint in hints)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    def _stable_identifier(self, value: str, *, max_length: int) -> str:
        normalized = "-".join(part for part in value.lower().replace("_", "-").split("-") if part)
        safe = "".join(character if character.isalnum() or character == "-" else "-" for character in normalized)
        collapsed = "-".join(part for part in safe.split("-") if part)
        if len(collapsed) <= max_length:
            return collapsed or "generated-agent"
        return collapsed[: max_length - 9].rstrip("-") + "-" + hex(abs(hash(collapsed)))[2:10]

    def _dedupe_identifiers(self, value: object) -> list[str]:
        items = value if isinstance(value, list) else [value] if value not in {None, ""} else []
        deduped: list[str] = []
        seen: set[str] = set()
        for item in items:
            normalized = self._text(item)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
        return deduped


requirement_dispatch_service = RequirementDispatchService()


def dispatch_requirement_task(task_id: str, *, trigger: str = "task_created") -> dict[str, Any]:
    return requirement_dispatch_service.dispatch_task(task_id, trigger=trigger)


def bootstrap_requirement_dispatch_state(*, limit: int = 50) -> dict[str, Any]:
    return requirement_dispatch_service.bootstrap(limit=limit)


def get_requirement_dispatch_group_for_task(task: dict[str, Any]) -> dict[str, Any] | None:
    return requirement_dispatch_service.group_for_task(task)
