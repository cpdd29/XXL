from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from app.platform.contracts.payload_aliases import (
    alias_value,
    dispatch_context_from_run,
    route_decision_from_payload,
    route_decision_from_task,
)
from app.modules.reception.application.orchestration_service import build_execution_plan_snapshot
from app.modules.dispatch.requirement_dispatch_agent.service import get_requirement_dispatch_group_for_task
from app.platform.persistence.persistence_service import persistence_service
from app.platform.persistence.runtime_store import store


FAILURE_STAGE_LABELS = {
    "route": "路由",
    "dispatch": "调度",
    "execution": "执行",
    "outbound": "回传",
}

DISPATCH_STATE_LABELS = {
    "queued": "等待调度",
    "dispatching": "调度中",
    "dispatched": "已派发",
    "agent_queued": "等待 Agent 执行",
    "executing": "执行中",
    "completed": "执行完成",
    "failed": "执行失败",
    "execution_timeout": "执行超时",
    "agent_execution_failed": "Agent 执行失败",
}


def _text(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


class TaskViewService:
    """Render lightweight task-facing summaries from task records."""

    def _normalize_identifier_list(self, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [
            normalized
            for normalized in dict.fromkeys(
                str(item or "").strip()
                for item in value
                if str(item or "").strip()
            )
        ]

    def _runtime_agent_metadata(self, agent_payload: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(agent_payload, dict):
            return {}
        snapshot = agent_payload.get("config_snapshot")
        if not isinstance(snapshot, dict):
            return {}
        runtime = snapshot.get("runtime")
        if isinstance(runtime, dict):
            metadata_binding = runtime.get("agent_metadata")
            if isinstance(metadata_binding, dict) and isinstance(metadata_binding.get("metadata"), dict):
                return deepcopy(metadata_binding.get("metadata") or {})
        agent_doc = snapshot.get("agent")
        if isinstance(agent_doc, dict) and isinstance(agent_doc.get("metadata"), dict):
            return deepcopy(agent_doc.get("metadata") or {})
        return {}

    def _runtime_model_binding(self, agent_payload: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(agent_payload, dict):
            return {}
        snapshot = agent_payload.get("config_snapshot")
        if not isinstance(snapshot, dict):
            return {}
        runtime = snapshot.get("runtime")
        if isinstance(runtime, dict):
            binding = runtime.get("agent_binding")
            if isinstance(binding, dict):
                return deepcopy(binding)
        agent_doc = snapshot.get("agent")
        if not isinstance(agent_doc, dict):
            return {}
        provider_key = _text(agent_doc.get("provider"))
        model = _text(agent_doc.get("model"))
        if provider_key is None and model is None:
            return {}
        return {
            "provider_key": provider_key,
            "model": model,
        }

    def _runtime_skill_binding(self, agent_payload: dict[str, Any] | None) -> list[str]:
        if not isinstance(agent_payload, dict):
            return []
        snapshot = agent_payload.get("config_snapshot")
        if not isinstance(snapshot, dict):
            return []
        runtime = snapshot.get("runtime")
        if isinstance(runtime, dict):
            binding = runtime.get("brain_skill_binding")
            if isinstance(binding, dict):
                return self._normalize_identifier_list(binding.get("skill_ids") or binding.get("skillIds") or [])
        agent_doc = snapshot.get("agent")
        if isinstance(agent_doc, dict):
            return self._normalize_identifier_list(agent_doc.get("skill_ids") or agent_doc.get("skillIds") or [])
        return []

    def _runtime_tool_binding(self, agent_payload: dict[str, Any] | None) -> list[str]:
        if not isinstance(agent_payload, dict):
            return []
        snapshot = agent_payload.get("config_snapshot")
        if not isinstance(snapshot, dict):
            return []
        runtime = snapshot.get("runtime")
        if isinstance(runtime, dict):
            binding = runtime.get("tool_binding")
            if isinstance(binding, dict):
                return self._normalize_identifier_list(
                    binding.get("tool_ids") or binding.get("toolIds") or binding.get("bound_tool_ids") or []
                )
        agent_doc = snapshot.get("agent")
        if isinstance(agent_doc, dict):
            return self._normalize_identifier_list(
                agent_doc.get("tool_ids") or agent_doc.get("toolIds") or agent_doc.get("bound_tool_ids") or []
            )
        return []

    def _all_agents_by_id(self) -> dict[str, dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        database_agents = persistence_service.list_agents()
        base_agents: list[dict[str, Any]]
        if isinstance(database_agents, list):
            base_agents = database_agents
        elif getattr(persistence_service, "enabled", False):
            base_agents = []
        else:
            base_agents = list(getattr(store, "agents", []))
        for item in base_agents:
            agent_id = _text(item.get("id"))
            if agent_id is not None:
                merged[agent_id] = deepcopy(item)
        for item in getattr(store, "agents", []):
            agent_id = _text(item.get("id"))
            if agent_id is not None:
                merged[agent_id] = deepcopy(item)
        return merged

    def _task_agent_member_projection(
        self,
        *,
        agent_payload: dict[str, Any] | None,
        role: str | None,
        branch_id: str | None,
        fallback_id: str | None,
        fallback_name: str | None,
    ) -> dict[str, Any]:
        metadata = self._runtime_agent_metadata(agent_payload)
        model_binding = self._runtime_model_binding(agent_payload)
        snapshot = agent_payload.get("config_snapshot") if isinstance(agent_payload, dict) else {}
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        return {
            "id": _text((agent_payload or {}).get("id")) or fallback_id,
            "name": _text((agent_payload or {}).get("name")) or fallback_name,
            "role": role,
            "branch_id": branch_id,
            "type": _text((agent_payload or {}).get("type")),
            "status": _text((agent_payload or {}).get("status")),
            "enabled": bool((agent_payload or {}).get("enabled")) if isinstance(agent_payload, dict) else None,
            "provider_key": _text(model_binding.get("provider_key") or model_binding.get("providerKey")),
            "provider_label": _text(model_binding.get("provider_label") or model_binding.get("providerLabel")),
            "model": _text(model_binding.get("model")),
            "bound_skill_ids": self._runtime_skill_binding(agent_payload),
            "bound_tool_ids": self._runtime_tool_binding(agent_payload),
            "requested_skill_ids": self._normalize_identifier_list(
                metadata.get("requested_skill_ids") or metadata.get("requestedSkillIds") or []
            ),
            "requested_tool_ids": self._normalize_identifier_list(
                metadata.get("requested_tool_ids") or metadata.get("requestedToolIds") or []
            ),
            "nats_subject": _text(metadata.get("nats_subject") or metadata.get("natsSubject")),
            "soul": _text(snapshot.get("soul")),
            "runtime_status": None,
            "current_step_id": None,
            "current_step_title": None,
            "current_step_message": None,
            "current_step_started_at": None,
            "current_step_finished_at": None,
            "selected_for_delivery": None,
        }

    def _step_metadata(self, step: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(step, dict):
            return {}
        metadata = step.get("metadata")
        return metadata if isinstance(metadata, dict) else {}

    def _step_matches_member(
        self,
        step: dict[str, Any] | None,
        *,
        member: dict[str, Any],
        role: str | None,
    ) -> bool:
        if not isinstance(step, dict):
            return False
        metadata = self._step_metadata(step)
        member_id = _text(member.get("id"))
        member_name = _text(member.get("name"))
        branch_id = _text(member.get("branch_id"))
        step_agent = _text(step.get("agent"))
        step_title = _text(step.get("title"))
        step_message = _text(step.get("message"))
        step_execution_agent_id = _text(metadata.get("execution_agent_id") or metadata.get("executionAgentId"))
        step_branch_id = _text(metadata.get("branch_id") or metadata.get("branchId"))
        step_acceptance_agent_id = _text(
            metadata.get("acceptance_agent_id") or metadata.get("acceptanceAgentId")
        )

        if member_id is not None and step_execution_agent_id == member_id:
            return True
        if branch_id is not None and step_branch_id == branch_id:
            return True
        if member_name is not None and step_agent == member_name:
            return True
        if member_id is not None and step_agent == member_id:
            return True

        if role == "acceptance":
            if member_id is not None and step_acceptance_agent_id == member_id:
                return True
            haystack = " ".join(
                value
                for value in (step_agent, step_title, step_message)
                if value is not None
            ).lower()
            if any(keyword in haystack for keyword in ("验收", "review", "复核")):
                return True
        return False

    def _matching_task_step_for_member(
        self,
        *,
        member: dict[str, Any],
        role: str | None,
        task_steps: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        for step in reversed(task_steps):
            if self._step_matches_member(step, member=member, role=role):
                return deepcopy(step)
        return None

    def _branch_result_for_member(
        self,
        *,
        member: dict[str, Any],
        branch_results: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        member_branch_id = _text(member.get("branch_id"))
        member_name = _text(member.get("name"))
        member_id = _text(member.get("id"))
        for item in branch_results:
            if not isinstance(item, dict):
                continue
            branch_id = _text(item.get("branch_id") or item.get("branchId"))
            agent_name = _text(item.get("agent"))
            if member_branch_id is not None and branch_id == member_branch_id:
                return deepcopy(item)
            if member_name is not None and agent_name == member_name:
                return deepcopy(item)
            if member_id is not None and agent_name == member_id:
                return deepcopy(item)
        return None

    def _task_agent_member_runtime(
        self,
        *,
        member: dict[str, Any],
        role: str | None,
        task: dict[str, Any],
        task_steps: list[dict[str, Any]],
        branch_results: list[dict[str, Any]],
        selected_branch_id: str | None,
        selected_agent: str | None,
        dispatch_context: dict[str, Any],
    ) -> dict[str, Any]:
        matched_step = self._matching_task_step_for_member(member=member, role=role, task_steps=task_steps)
        branch_result = self._branch_result_for_member(member=member, branch_results=branch_results)
        acceptance = dispatch_context.get("acceptance")
        acceptance = acceptance if isinstance(acceptance, dict) else {}

        runtime_status = _text((matched_step or {}).get("status"))
        current_step_id = _text((matched_step or {}).get("id"))
        current_step_title = _text((matched_step or {}).get("title"))
        current_step_message = _text((matched_step or {}).get("message"))
        current_step_started_at = _text((matched_step or {}).get("started_at") or (matched_step or {}).get("startedAt"))
        current_step_finished_at = _text((matched_step or {}).get("finished_at") or (matched_step or {}).get("finishedAt"))

        if runtime_status is None and isinstance(branch_result, dict):
            runtime_status = _text(branch_result.get("status"))
            current_step_title = current_step_title or "协同执行分支"
            current_step_message = current_step_message or (
                f"聚合记录状态：{runtime_status}" if runtime_status is not None else None
            )
            current_step_finished_at = current_step_finished_at or _text(task.get("completed_at"))

        if role == "acceptance":
            accepted = acceptance.get("accepted")
            if runtime_status is None and accepted is not None:
                runtime_status = "completed" if bool(accepted) else "failed"
                current_step_title = current_step_title or "验收结论"
                current_step_message = current_step_message or (
                    "验收通过，准备进入结果回传"
                    if bool(accepted)
                    else "验收未通过，已转向人工接管"
                )
            if runtime_status is None:
                task_status = str(task.get("status") or "").strip().lower()
                if task_status == "completed":
                    runtime_status = "completed"
                elif task_status == "failed" and accepted is False:
                    runtime_status = "failed"
                elif task_status in {"pending", "running"}:
                    runtime_status = "pending"
        else:
            if runtime_status is None:
                task_status = str(task.get("status") or "").strip().lower()
                execution_agent_id = _text(task.get("execution_agent_id"))
                if execution_agent_id is None:
                    route_decision = route_decision_from_task(task) or {}
                    execution_agent_id = _text(
                        route_decision.get("execution_agent_id") or route_decision.get("executionAgentId")
                    )
                if task_status == "running":
                    if _text(member.get("id")) == execution_agent_id or _text(member.get("name")) == _text(task.get("agent")):
                        runtime_status = "running"
                    else:
                        runtime_status = "pending"
                elif task_status == "pending":
                    runtime_status = "pending"
                elif task_status == "completed" and branch_result is not None:
                    runtime_status = _text(branch_result.get("status")) or "completed"
                elif task_status == "failed" and branch_result is not None:
                    runtime_status = _text(branch_result.get("status")) or "failed"

        selected_for_delivery = None
        member_branch_id = _text(member.get("branch_id"))
        member_name = _text(member.get("name"))
        if role != "acceptance":
            selected_for_delivery = bool(
                (member_branch_id is not None and selected_branch_id == member_branch_id)
                or (member_name is not None and selected_agent == member_name)
            )

        return {
            "runtime_status": runtime_status,
            "current_step_id": current_step_id,
            "current_step_title": current_step_title,
            "current_step_message": current_step_message,
            "current_step_started_at": current_step_started_at,
            "current_step_finished_at": current_step_finished_at,
            "selected_for_delivery": selected_for_delivery,
        }

    def _task_agent_runtime_timeline_entries(
        self,
        *,
        task: dict[str, Any],
        development_agents: list[dict[str, Any]],
        acceptance_agent: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        members = [*development_agents]
        if isinstance(acceptance_agent, dict):
            members.append(acceptance_agent)
        entries: list[dict[str, Any]] = []
        for member in members:
            role = _text(member.get("role")) or "development"
            runtime_status = _text(member.get("runtime_status"))
            title = _text(member.get("current_step_title"))
            message = _text(member.get("current_step_message"))
            timestamp = _text(member.get("current_step_finished_at")) or _text(member.get("current_step_started_at"))
            should_emit = runtime_status in {"running", "completed", "failed", "cancelled"} or title is not None or message is not None
            if not should_emit:
                continue
            role_label = "验收成员" if role == "acceptance" else "开发成员"
            status_label = {
                "running": "执行中",
                "completed": "已完成",
                "failed": "执行失败",
                "cancelled": "已取消",
                "pending": "待启动",
            }.get(runtime_status or "", runtime_status or "状态更新")
            entries.append(
                {
                    "id": f"{_text(task.get('id')) or 'task'}:runtime:{_text(member.get('id')) or role}:{runtime_status or 'update'}",
                    "kind": f"member_{runtime_status or 'updated'}",
                    "title": f"{role_label}{status_label}",
                    "detail": (
                        f"{_text(member.get('name')) or _text(member.get('id')) or '任务成员'}"
                        + (f" · {title}" if title is not None else "")
                        + (f" · {message}" if message is not None else "")
                    ),
                    "timestamp": timestamp,
                    "actor_agent_id": _text(member.get("id")),
                    "actor_agent_name": _text(member.get("name")),
                    "metadata": {
                        "role": role,
                        "runtime_status": runtime_status,
                        "current_step_id": _text(member.get("current_step_id")),
                        "current_step_title": title,
                        "selected_for_delivery": member.get("selected_for_delivery"),
                    },
                }
            )
        return entries

    def _task_agent_group_timeline_entry(self, entry: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(entry, dict):
            return None
        title = _text(entry.get("title"))
        if title is None:
            return None
        return {
            "id": _text(entry.get("id")),
            "kind": _text(entry.get("kind")),
            "title": title,
            "detail": _text(entry.get("detail")),
            "timestamp": _text(entry.get("timestamp")),
            "actor_agent_id": _text(entry.get("actor_agent_id") or entry.get("actorAgentId")),
            "actor_agent_name": _text(entry.get("actor_agent_name") or entry.get("actorAgentName")),
            "metadata": deepcopy(entry.get("metadata") or {}) if isinstance(entry.get("metadata"), dict) else {},
        }

    def _derived_task_agent_group_timeline(
        self,
        *,
        group_entry: dict[str, Any],
        development_agents: list[dict[str, Any]],
        acceptance_agent: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        group_id = _text(group_entry.get("id")) or "task-group"
        group_name = _text(group_entry.get("name")) or group_id
        created_at = _text(group_entry.get("created_at")) or _text(group_entry.get("updated_at"))
        topology = _text(group_entry.get("topology"))
        requested_skill_ids = self._normalize_identifier_list(group_entry.get("requested_skill_ids") or [])
        requested_tool_ids = self._normalize_identifier_list(group_entry.get("requested_tool_ids") or [])
        applied_skill_ids = self._normalize_identifier_list(group_entry.get("applied_skill_ids") or [])
        applied_tool_ids = self._normalize_identifier_list(group_entry.get("applied_tool_ids") or [])
        warnings = [
            str(item or "").strip()
            for item in list(group_entry.get("warnings") or [])
            if str(item or "").strip()
        ]
        rationale = group_entry.get("rationale") if isinstance(group_entry.get("rationale"), dict) else {}

        timeline: list[dict[str, Any]] = []
        timeline.append(
            {
                "id": f"{group_id}:group-created",
                "kind": "group_created",
                "title": "创建开发组",
                "detail": f"已为当前任务建立开发组 {group_name}。"
                + (f" 执行拓扑为 {topology}。" if topology else ""),
                "timestamp": created_at,
                "actor_agent_id": _text(group_entry.get("dispatcher_agent_id")),
                "actor_agent_name": "需求分发 Agent",
                "metadata": {
                    "decision_source": _text(rationale.get("source")),
                    "decision_reasons": deepcopy(rationale.get("reasons") or []),
                },
            }
        )
        timeline.append(
            {
                "id": f"{group_id}:capability-planned",
                "kind": "capability_planned",
                "title": "写入能力编排",
                "detail": (
                    f"请求 Skill {len(requested_skill_ids)} 项、请求 Tool/MCP {len(requested_tool_ids)} 项；"
                    f"实际绑定 Skill {len(applied_skill_ids)} 项、Tool/MCP {len(applied_tool_ids)} 项。"
                ),
                "timestamp": created_at,
                "actor_agent_id": _text(group_entry.get("dispatcher_agent_id")),
                "actor_agent_name": "需求分发 Agent",
                "metadata": {
                    "requested_skill_ids": requested_skill_ids,
                    "requested_tool_ids": requested_tool_ids,
                    "applied_skill_ids": applied_skill_ids,
                    "applied_tool_ids": applied_tool_ids,
                    "warnings": warnings,
                },
            }
        )

        for member in development_agents:
            agent_id = _text(member.get("id"))
            role = _text(member.get("role")) or "development"
            timeline.append(
                {
                    "id": f"{group_id}:member:{agent_id or role}",
                    "kind": "development_agent_provisioned",
                    "title": "生成开发成员",
                    "detail": f"{_text(member.get('name')) or agent_id or '开发 Agent'} 已加入开发组，承担 {role} 角色。",
                    "timestamp": created_at,
                    "actor_agent_id": agent_id,
                    "actor_agent_name": _text(member.get("name")),
                    "metadata": {
                        "role": role,
                        "nats_subject": _text(member.get("nats_subject")),
                        "model": _text(member.get("model")),
                    },
                }
            )

        if isinstance(acceptance_agent, dict):
            timeline.append(
                {
                    "id": f"{group_id}:acceptance",
                    "kind": "acceptance_agent_provisioned",
                    "title": "生成验收成员",
                    "detail": f"{_text(acceptance_agent.get('name')) or '验收 Agent'} 已加入开发组，承担最终验收。",
                    "timestamp": created_at,
                    "actor_agent_id": _text(acceptance_agent.get("id")),
                    "actor_agent_name": _text(acceptance_agent.get("name")),
                    "metadata": {
                        "role": _text(acceptance_agent.get("role")) or "acceptance",
                        "nats_subject": _text(acceptance_agent.get("nats_subject")),
                        "model": _text(acceptance_agent.get("model")),
                    },
                }
            )

        nats_subjects = deepcopy(group_entry.get("nats_subjects") or {})
        if nats_subjects:
            timeline.append(
                {
                    "id": f"{group_id}:nats-subjects",
                    "kind": "coordination_allocated",
                    "title": "分配协作主题",
                    "detail": "已为开发组分配广播、协调、负责人及成员级 NATS 通信主题。",
                    "timestamp": created_at,
                    "actor_agent_id": _text(group_entry.get("dispatcher_agent_id")),
                    "actor_agent_name": "需求分发 Agent",
                    "metadata": nats_subjects,
                }
            )
        return timeline

    def _build_task_agent_group_timeline(
        self,
        *,
        task: dict[str, Any],
        group_entry: dict[str, Any],
        development_agents: list[dict[str, Any]],
        acceptance_agent: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        runtime_entries = self._task_agent_runtime_timeline_entries(
            task=task,
            development_agents=development_agents,
            acceptance_agent=acceptance_agent,
        )
        explicit = group_entry.get("timeline")
        if isinstance(explicit, list):
            normalized = [
                item
                for item in (
                    self._task_agent_group_timeline_entry(entry if isinstance(entry, dict) else None)
                    for entry in explicit
                )
                if item is not None
            ]
            if normalized:
                seen_ids = {
                    str(item.get("id") or "").strip()
                    for item in normalized
                    if str(item.get("id") or "").strip()
                }
                combined = list(normalized)
                for entry in runtime_entries:
                    entry_id = str(entry.get("id") or "").strip()
                    if entry_id and entry_id in seen_ids:
                        continue
                    if entry_id:
                        seen_ids.add(entry_id)
                    combined.append(entry)
                return combined
        combined = self._derived_task_agent_group_timeline(
            group_entry=group_entry,
            development_agents=development_agents,
            acceptance_agent=acceptance_agent,
        )
        combined.extend(runtime_entries)
        return combined

    def _build_task_agent_group(
        self,
        task: dict[str, Any],
        *,
        run: dict[str, Any] | None = None,
        task_steps: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        group_entry = get_requirement_dispatch_group_for_task(task)
        if not isinstance(group_entry, dict):
            return None

        execution_plan = self.build_session_execution_plan(task, run=run)
        if not isinstance(execution_plan, dict):
            route_decision = route_decision_from_task(task) or {}
            execution_plan = route_decision.get("execution_plan") or route_decision.get("executionPlan")
            execution_plan = execution_plan if isinstance(execution_plan, dict) else {}
        coordination_mode = _text(
            execution_plan.get("coordination_mode") or execution_plan.get("coordinationMode")
        )
        steps = execution_plan.get("steps")
        step_items = steps if isinstance(steps, list) else []
        branch_results = execution_plan.get("branch_results")
        branch_results = branch_results if isinstance(branch_results, list) else []
        selected_branch_id = _text(
            execution_plan.get("selected_branch_id") or execution_plan.get("selectedBranchId")
        )
        selected_agent = _text(
            execution_plan.get("selected_agent") or execution_plan.get("selectedAgent")
        )
        dispatch_context = self._dispatch_context(run)
        runtime_steps = task_steps if isinstance(task_steps, list) else []
        branch_by_agent_id: dict[str, str | None] = {}
        for step in step_items:
            if not isinstance(step, dict):
                continue
            agent_id = _text(step.get("execution_agent_id") or step.get("executionAgentId"))
            if agent_id is None:
                continue
            branch_by_agent_id[agent_id] = _text(step.get("branch_id") or step.get("branchId"))

        agent_map = self._all_agents_by_id()
        development_agents = []
        for member in list(group_entry.get("development_agents") or []):
            if not isinstance(member, dict):
                continue
            member_id = _text(member.get("id"))
            member_role = _text(member.get("role"))
            member_projection = self._task_agent_member_projection(
                agent_payload=agent_map.get(member_id or ""),
                role=member_role,
                branch_id=branch_by_agent_id.get(member_id or ""),
                fallback_id=member_id,
                fallback_name=_text(member.get("name")),
            )
            member_projection.update(
                self._task_agent_member_runtime(
                    member=member_projection,
                    role=member_role,
                    task=task,
                    task_steps=runtime_steps,
                    branch_results=branch_results,
                    selected_branch_id=selected_branch_id,
                    selected_agent=selected_agent,
                    dispatch_context=dispatch_context,
                )
            )
            development_agents.append(member_projection)

        acceptance_entry = group_entry.get("acceptance_agent")
        acceptance_agent = None
        if isinstance(acceptance_entry, dict):
            acceptance_id = _text(acceptance_entry.get("id"))
            acceptance_agent = self._task_agent_member_projection(
                agent_payload=agent_map.get(acceptance_id or ""),
                role="acceptance",
                branch_id=None,
                fallback_id=acceptance_id,
                fallback_name=_text(acceptance_entry.get("name")),
            )
            acceptance_agent.update(
                self._task_agent_member_runtime(
                    member=acceptance_agent,
                    role="acceptance",
                    task=task,
                    task_steps=runtime_steps,
                    branch_results=branch_results,
                    selected_branch_id=selected_branch_id,
                    selected_agent=selected_agent,
                    dispatch_context=dispatch_context,
                )
            )

        return {
            "id": _text(group_entry.get("id")),
            "name": _text(group_entry.get("name")),
            "status": _text(group_entry.get("status")),
            "topology": _text(group_entry.get("topology")),
            "coordination_mode": coordination_mode,
            "dispatcher_agent_id": _text(group_entry.get("dispatcher_agent_id")),
            "development_agents": development_agents,
            "acceptance_agent": acceptance_agent,
            "requested_skill_ids": self._normalize_identifier_list(group_entry.get("requested_skill_ids") or []),
            "requested_tool_ids": self._normalize_identifier_list(group_entry.get("requested_tool_ids") or []),
            "applied_skill_ids": self._normalize_identifier_list(group_entry.get("applied_skill_ids") or []),
            "applied_tool_ids": self._normalize_identifier_list(group_entry.get("applied_tool_ids") or []),
            "nats_subjects": deepcopy(group_entry.get("nats_subjects") or {}),
            "timeline": self._build_task_agent_group_timeline(
                task=task,
                group_entry=group_entry,
                development_agents=development_agents,
                acceptance_agent=acceptance_agent,
            ),
            "warnings": [
                str(item or "").strip()
                for item in list(group_entry.get("warnings") or [])
                if str(item or "").strip()
            ],
        }

    def _dispatch_context(self, run: dict[str, Any] | None) -> dict[str, Any]:
        return dispatch_context_from_run(run) or {}

    def _dispatch_context_value(self, dispatch_context: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = _text(dispatch_context.get(key))
            if value is not None:
                return value
        return None

    def _normalize_failure_stage(self, value: object) -> str | None:
        normalized = str(value or "").strip().lower()
        if normalized in FAILURE_STAGE_LABELS:
            return normalized
        return None

    def _infer_failure_stage_from_step(self, step: dict[str, Any] | None) -> str | None:
        if not isinstance(step, dict):
            return None
        haystack = " ".join(
            str(step.get(key) or "").strip().lower()
            for key in ("title", "agent", "message")
        )
        if not haystack:
            return None
        if any(keyword in haystack for keyword in ("路由", "intent", "master bot")):
            return "route"
        if any(keyword in haystack for keyword in ("调度", "dispatcher")):
            return "dispatch"
        if any(keyword in haystack for keyword in ("回传", "发送结果", "输出")):
            return "outbound"
        if any(keyword in haystack for keyword in ("执行", "agent", "超时")):
            return "execution"
        return None

    def _latest_failed_step(self, steps: list[dict[str, Any]] | None) -> dict[str, Any] | None:
        if not isinstance(steps, list):
            return None
        for step in reversed(steps):
            if str(step.get("status") or "").strip().lower() == "failed":
                return step
        return None

    def _latest_active_step(self, steps: list[dict[str, Any]] | None) -> dict[str, Any] | None:
        if not isinstance(steps, list):
            return None
        for status_value in ("running", "pending"):
            for step in reversed(steps):
                if str(step.get("status") or "").strip().lower() == status_value:
                    return step
        return None

    def _derive_failure_stage(
        self,
        task: dict[str, Any],
        *,
        run: dict[str, Any] | None,
        steps: list[dict[str, Any]],
        delivery_status: str | None,
    ) -> str | None:
        dispatch_context = self._dispatch_context(run)
        explicit_failure_stage = self._normalize_failure_stage(
            dispatch_context.get("failure_stage") or dispatch_context.get("failureStage")
        )
        if explicit_failure_stage is not None:
            return explicit_failure_stage

        dispatch_state = self._dispatch_context_value(dispatch_context, "state", "dispatch_state", "dispatchState")
        if dispatch_state in {"execution_timeout", "agent_execution_failed"}:
            return "execution"

        if _text((run or {}).get("last_dispatch_error") or (run or {}).get("lastDispatchError")) is not None:
            return "dispatch"

        failed_step = self._latest_failed_step(steps)
        inferred_from_step = self._infer_failure_stage_from_step(failed_step)
        if inferred_from_step is not None:
            return inferred_from_step

        if str(task.get("status") or "").strip().lower() == "completed" and delivery_status == "failed":
            return "outbound"
        return None

    def _derive_failure_message(
        self,
        task: dict[str, Any],
        *,
        run: dict[str, Any] | None,
        steps: list[dict[str, Any]],
        failure_stage: str | None,
        delivery_status: str | None,
        delivery_message: str | None,
    ) -> str | None:
        dispatch_context = self._dispatch_context(run)
        explicit_message = self._dispatch_context_value(dispatch_context, "failure_message", "failureMessage")
        if explicit_message is not None:
            return explicit_message

        dispatch_error = _text((run or {}).get("last_dispatch_error") or (run or {}).get("lastDispatchError"))
        if dispatch_error is not None:
            return dispatch_error

        failed_step = self._latest_failed_step(steps)
        if failed_step is not None:
            failed_step_message = _text(failed_step.get("message"))
            if failed_step_message is not None:
                return failed_step_message

        if str(task.get("status") or "").strip().lower() == "completed" and failure_stage == "outbound":
            return delivery_message if delivery_status == "failed" else None
        return None

    def _derive_current_stage(
        self,
        task: dict[str, Any],
        *,
        run: dict[str, Any] | None,
        steps: list[dict[str, Any]],
    ) -> str:
        run_stage = _text((run or {}).get("current_stage") or (run or {}).get("currentStage"))
        if run_stage is not None:
            return run_stage

        active_step = self._latest_active_step(steps)
        if active_step is not None:
            return _text(active_step.get("title")) or "执行中"

        failed_step = self._latest_failed_step(steps)
        if failed_step is not None:
            return _text(failed_step.get("title")) or "执行失败"

        task_status = str(task.get("status") or "").strip().lower()
        if task_status == "completed":
            return "执行完成"
        if task_status == "failed":
            return "执行失败"
        if task_status == "cancelled":
            return "已取消"
        if task_status == "running":
            return "执行中"
        return "等待开始"

    def _build_status_reason(
        self,
        task: dict[str, Any],
        *,
        current_stage: str,
        dispatch_state: str | None,
        failure_stage: str | None,
        failure_message: str | None,
        delivery_status: str | None,
        delivery_message: str | None,
    ) -> str | None:
        task_status = str(task.get("status") or "").strip().lower()
        if task_status == "failed" and failure_stage is not None:
            stage_label = FAILURE_STAGE_LABELS.get(failure_stage, failure_stage)
            if failure_message is not None:
                return f"失败于{stage_label}阶段：{failure_message}"
            return f"失败于{stage_label}阶段"

        if delivery_status == "failed":
            return delivery_message or "结果已生成，但渠道回传失败"
        if delivery_status == "skipped":
            return delivery_message or "结果已生成，但当前未自动回传到外部渠道"

        if task_status in {"pending", "running"}:
            if current_stage:
                return f"当前阶段：{current_stage}"
            dispatch_label = DISPATCH_STATE_LABELS.get(str(dispatch_state or "").strip().lower())
            if dispatch_label is not None:
                return dispatch_label

        if task_status == "completed":
            if delivery_status == "sent":
                return "执行完成，结果已自动回传"
            return "执行完成"
        return None

    def build_task_projection(
        self,
        task: dict[str, Any],
        *,
        run: dict[str, Any] | None = None,
        steps: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload = deepcopy(task)
        route_decision = route_decision_from_payload(payload)
        if route_decision is not None:
            for payload_key, route_keys in (
                ("confirmation_status", ("confirmation_status", "confirmationStatus")),
                ("approval_status", ("approval_status", "approvalStatus")),
                ("approval_required", ("approval_required", "approvalRequired")),
                ("audit_id", ("audit_id", "auditId")),
                ("idempotency_key", ("idempotency_key", "idempotencyKey")),
                ("execution_scope", ("execution_scope", "executionScope")),
                ("schedule_plan", ("schedule_plan", "schedulePlan")),
            ):
                candidate = alias_value(route_decision, *route_keys)
                if candidate is not None:
                    payload.setdefault(payload_key, candidate)

        step_items = steps if isinstance(steps, list) else []
        dispatch_context = self._dispatch_context(run)

        manager_packet = payload.get("manager_packet")
        if not isinstance(manager_packet, dict):
            dispatch_manager_packet = dispatch_context.get("manager_packet") or dispatch_context.get("managerPacket")
            if isinstance(dispatch_manager_packet, dict):
                payload["manager_packet"] = deepcopy(dispatch_manager_packet)

        brain_dispatch_summary = payload.get("brain_dispatch_summary")
        if not isinstance(brain_dispatch_summary, dict):
            dispatch_summary = dispatch_context.get("brain_dispatch_summary") or dispatch_context.get("brainDispatchSummary")
            if isinstance(dispatch_summary, dict):
                payload["brain_dispatch_summary"] = deepcopy(dispatch_summary)

        memory_injection_summary = payload.get("memory_injection_summary")
        if not isinstance(memory_injection_summary, dict):
            dispatch_memory_injection = dispatch_context.get("memory_injection") or dispatch_context.get("memoryInjection")
            if isinstance(dispatch_memory_injection, dict):
                payload["memory_injection_summary"] = deepcopy(dispatch_memory_injection)

        state_machine = payload.get("state_machine")
        if not isinstance(state_machine, dict):
            dispatch_state_machine = dispatch_context.get("state_machine") or dispatch_context.get("stateMachine")
            if isinstance(dispatch_state_machine, dict):
                payload["state_machine"] = deepcopy(dispatch_state_machine)

        dispatch_state = self._dispatch_context_value(dispatch_context, "state", "dispatch_state", "dispatchState")
        delivery_status = self._dispatch_context_value(dispatch_context, "delivery_status", "deliveryStatus")
        delivery_message = self._dispatch_context_value(dispatch_context, "delivery_message", "deliveryMessage")
        failure_stage = self._derive_failure_stage(
            payload,
            run=run,
            steps=step_items,
            delivery_status=delivery_status,
        )
        failure_message = self._derive_failure_message(
            payload,
            run=run,
            steps=step_items,
            failure_stage=failure_stage,
            delivery_status=delivery_status,
            delivery_message=delivery_message,
        )
        current_stage = self._derive_current_stage(payload, run=run, steps=step_items)

        payload["current_stage"] = current_stage
        payload["dispatch_state"] = dispatch_state
        payload["failure_stage"] = failure_stage
        payload["failure_message"] = failure_message
        payload["delivery_status"] = delivery_status
        payload["delivery_message"] = delivery_message
        payload["status_reason"] = self._build_status_reason(
            payload,
            current_stage=current_stage,
            dispatch_state=dispatch_state,
            failure_stage=failure_stage,
            failure_message=failure_message,
            delivery_status=delivery_status,
            delivery_message=delivery_message,
        )
        task_agent_group = self._build_task_agent_group(
            payload,
            run=run,
            task_steps=step_items,
        )
        if task_agent_group is not None:
            payload["task_agent_group"] = task_agent_group
        return payload

    def build_scoped_task_projection(
        self,
        task: dict[str, Any],
        *,
        run: dict[str, Any] | None = None,
        steps: list[dict[str, Any]] | None = None,
        attach_scope_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        scoped_task = attach_scope_fn(task) if callable(attach_scope_fn) else deepcopy(task)
        return self.build_task_projection(scoped_task, run=run, steps=steps)

    def build_task_list_response(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        return {"items": items, "total": len(items)}

    def summarize(self, task: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": task.get("id"),
            "title": task.get("title"),
            "status": task.get("status"),
            "current_stage": task.get("current_stage") or task.get("dispatch_state"),
            "status_reason": task.get("status_reason"),
            "updated_at": task.get("updated_at"),
        }

    def build_manager_summary(self, manager_packet: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(manager_packet, dict) or not manager_packet:
            return None

        summary = {
            "manager_role": _text(manager_packet.get("manager_role")),
            "manager_action": _text(manager_packet.get("manager_action")),
            "next_owner": _text(manager_packet.get("next_owner")),
            "delivery_mode": _text(manager_packet.get("delivery_mode")),
            "task_shape": _text(manager_packet.get("task_shape")),
            "response_contract": _text(manager_packet.get("response_contract")),
            "clarify_required": bool(manager_packet.get("clarify_required"))
            if manager_packet.get("clarify_required") is not None
            else None,
            "clarify_question": _text(manager_packet.get("clarify_question")),
            "handoff_summary": _text(manager_packet.get("handoff_summary")),
            "session_state": _text(manager_packet.get("session_state")),
            "state_label": _text(manager_packet.get("state_label")),
        }
        if any(value is not None for value in summary.values()):
            return summary
        return None

    def build_session_execution_plan(
        self,
        task: dict[str, Any],
        *,
        run: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        task_plan = task.get("execution_plan")
        if isinstance(task_plan, dict) and task_plan:
            plan = deepcopy(task_plan)
        else:
            plan = None

        dispatch_context = self._dispatch_context(run)
        if plan is None and isinstance(dispatch_context, dict):
            snapshot = dispatch_context.get("execution_plan_snapshot")
            if isinstance(snapshot, dict) and snapshot:
                plan = deepcopy(snapshot)

        if plan is None:
            route_decision = route_decision_from_task(task)
            manager_packet = task.get("manager_packet") or task.get("managerPacket")
            if isinstance(dispatch_context, dict):
                if route_decision is None:
                    route_decision = route_decision_from_payload(dispatch_context)
                if not isinstance(manager_packet, dict):
                    manager_packet = dispatch_context.get("manager_packet") or dispatch_context.get("managerPacket")
            if route_decision is not None:
                plan = build_execution_plan_snapshot(
                    route_decision=route_decision,
                    manager_packet=manager_packet if isinstance(manager_packet, dict) else None,
                )

        if not isinstance(plan, dict) or not plan:
            return None

        if not isinstance(dispatch_context, dict):
            return plan

        aggregation_contract = dispatch_context.get("aggregation_contract") or dispatch_context.get("aggregationContract")
        aggregation_notes = dispatch_context.get("aggregation_notes") or dispatch_context.get("aggregationNotes")
        state_machine = dispatch_context.get("state_machine") or dispatch_context.get("stateMachine")

        if not isinstance(aggregation_contract, dict) and isinstance(state_machine, dict):
            aggregation_contract = {
                "mode": state_machine.get("coordination_mode"),
                "successful_agents": state_machine.get("successful_agents"),
                "failed_agents": state_machine.get("failed_agents"),
                "cancelled_agents": state_machine.get("cancelled_agents"),
                "branch_results": state_machine.get("branch_results"),
            }
        if not isinstance(aggregation_notes, dict) and isinstance(state_machine, dict):
            aggregation_notes = {
                "selected_branch_id": state_machine.get("selected_branch_id"),
                "selected_agent": state_machine.get("selected_agent"),
            }

        if isinstance(aggregation_contract, dict):
            if aggregation_contract.get("mode"):
                plan["coordination_mode"] = str(aggregation_contract.get("mode"))
            plan["successful_agents"] = int(aggregation_contract.get("successful_agents") or 0)
            plan["failed_agents"] = int(aggregation_contract.get("failed_agents") or 0)
            plan["cancelled_agents"] = int(aggregation_contract.get("cancelled_agents") or 0)
            branch_results = aggregation_contract.get("branch_results")
            if isinstance(branch_results, list):
                plan["branch_results"] = deepcopy(branch_results)

        if isinstance(aggregation_notes, dict):
            plan["selected_branch_id"] = (
                str(aggregation_notes.get("selected_branch_id") or "").strip() or None
            )
            plan["selected_agent"] = (
                str(aggregation_notes.get("selected_agent") or "").strip() or None
            )
        return plan

    def build_session_fallback_history(
        self,
        task: dict[str, Any],
        *,
        run: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        task_history = task.get("fallback_history") or task.get("fallbackHistory")
        if isinstance(task_history, list):
            return deepcopy(task_history)

        dispatch_context = self._dispatch_context(run)
        history = dispatch_context.get("fallback_history") or dispatch_context.get("fallbackHistory")
        if isinstance(history, list):
            return deepcopy(history)
        return []

    def build_ingest_response(
        self,
        *,
        result_message: str,
        entrypoint: str,
        unified_message: dict[str, Any],
        ok: bool = True,
        task_id: str | None = None,
        run_id: str | None = None,
        intent: str | None = None,
        trace_id: str | None = None,
        detected_lang: str | None = None,
        memory_hits: int = 0,
        warnings: list[str] | None = None,
        merged_into_task_id: str | None = None,
        interaction_mode: str | None = None,
        reception_mode: str | None = None,
        route_decision: dict[str, Any] | None = None,
        manager_packet: dict[str, Any] | None = None,
        brain_dispatch_summary: dict[str, Any] | None = None,
        hermes_protocol: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "ok": ok,
            "message": result_message,
            "entrypoint": entrypoint,
            "task_id": task_id,
            "run_id": run_id,
            "intent": intent,
            "unified_message": deepcopy(unified_message),
            "trace_id": trace_id,
            "detected_lang": detected_lang,
            "memory_hits": memory_hits,
            "warnings": list(warnings or []),
            "merged_into_task_id": merged_into_task_id,
            "interaction_mode": interaction_mode,
            "reception_mode": reception_mode,
            "route_decision": deepcopy(route_decision) if isinstance(route_decision, dict) else None,
            "manager_summary": self.build_manager_summary(manager_packet),
            "brain_dispatch_summary": (
                deepcopy(brain_dispatch_summary)
                if isinstance(brain_dispatch_summary, dict)
                else None
            ),
            "hermes_protocol": deepcopy(hermes_protocol) if isinstance(hermes_protocol, dict) else None,
        }

    def build_task_event_response(
        self,
        *,
        result_message: str,
        entrypoint: str,
        task: dict[str, Any],
        unified_message: dict[str, Any],
        ok: bool = True,
        run_id: str | None = None,
        intent: str | None = None,
        trace_id: str | None = None,
        detected_lang: str | None = None,
        memory_hits: int = 0,
        warnings: list[str] | None = None,
        merged_into_task_id: str | None = None,
        interaction_mode: str | None = None,
        reception_mode: str | None = None,
        include_task_route_decision: bool = True,
    ) -> dict[str, Any]:
        route_decision = None
        if include_task_route_decision:
            route_decision = route_decision_from_task(task)
        if interaction_mode is None and isinstance(route_decision, dict):
            interaction_mode = _text(route_decision.get("interaction_mode") or route_decision.get("interactionMode"))
        if reception_mode is None and isinstance(route_decision, dict):
            reception_mode = _text(route_decision.get("reception_mode") or route_decision.get("receptionMode"))
        resolved_run_id = _text(run_id) or _text(task.get("workflow_run_id") or task.get("workflowRunId"))
        resolved_task_id = _text(task.get("id"))
        return self.build_ingest_response(
            result_message=result_message,
            entrypoint=entrypoint,
            unified_message=unified_message,
            ok=ok,
            task_id=resolved_task_id,
            run_id=resolved_run_id,
            intent=intent,
            trace_id=trace_id,
            detected_lang=detected_lang,
            memory_hits=memory_hits,
            warnings=warnings,
            merged_into_task_id=merged_into_task_id,
            interaction_mode=interaction_mode,
            reception_mode=reception_mode,
            route_decision=route_decision,
            manager_packet=task.get("manager_packet") if isinstance(task.get("manager_packet"), dict) else None,
            brain_dispatch_summary=(
                task.get("brain_dispatch_summary")
                if isinstance(task.get("brain_dispatch_summary"), dict)
                else None
            ),
        )

    def build_context_patch_response(
        self,
        *,
        result_message: str,
        entrypoint: str,
        task: dict[str, Any] | None,
        task_id: str,
        unified_message: dict[str, Any],
        intent: str | None = None,
        trace_id: str | None = None,
        detected_lang: str | None = None,
        memory_hits: int = 0,
        warnings: list[str] | None = None,
        interaction_mode: str | None = "chat",
        reception_mode: str | None = "continuation",
    ) -> dict[str, Any]:
        if isinstance(task, dict):
            return self.build_task_event_response(
                result_message=result_message,
                entrypoint=entrypoint,
                task=task,
                run_id=_text(task.get("workflow_run_id") or task.get("workflowRunId")),
                intent=intent,
                unified_message=unified_message,
                trace_id=trace_id,
                detected_lang=detected_lang,
                memory_hits=memory_hits,
                warnings=warnings,
                merged_into_task_id=task_id,
                interaction_mode=interaction_mode,
                reception_mode=reception_mode,
                include_task_route_decision=False,
            )
        return self.build_ingest_response(
            result_message=result_message,
            entrypoint=entrypoint,
            task_id=task_id,
            intent=intent,
            unified_message=unified_message,
            trace_id=trace_id,
            detected_lang=detected_lang,
            memory_hits=memory_hits,
            warnings=warnings,
            merged_into_task_id=task_id,
            interaction_mode=interaction_mode,
            reception_mode=reception_mode,
        )


task_view_service = TaskViewService()
