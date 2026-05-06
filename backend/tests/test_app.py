from copy import deepcopy

from fastapi.testclient import TestClient

from app.main import app
from app.modules.dispatch.workflow_runtime.workflow_realtime_service import workflow_realtime_service
from app.platform.persistence.persistence_service import persistence_service
from app.platform.persistence.runtime_store import store


def _seed_task(task: dict, *, steps: list[dict] | None = None) -> None:
    copied_task = deepcopy(task)
    copied_steps = deepcopy(steps or [])
    store.tasks[:] = [copied_task]
    store.task_steps[str(copied_task["id"])] = copied_steps
    persistence_service.persist_execution_state(task=copied_task, task_steps=copied_steps)


def _seed_tasks(tasks: list[dict], *, steps_by_task: dict[str, list[dict]] | None = None) -> None:
    store.tasks[:] = []
    store.task_steps.clear()
    for task in tasks:
        copied_task = deepcopy(task)
        task_id = str(copied_task["id"])
        copied_steps = deepcopy((steps_by_task or {}).get(task_id, []))
        store.tasks.append(copied_task)
        store.task_steps[task_id] = copied_steps
        persistence_service.persist_execution_state(task=copied_task, task_steps=copied_steps)


def test_health_check() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_list_tasks(auth_headers) -> None:
    with TestClient(app) as client:
        _seed_task(
            {
                "id": "task-list-001",
                "title": "任务列表基线任务",
                "description": "用于校验任务列表接口",
                "status": "pending",
                "priority": "medium",
                "created_at": "2026-05-03T10:00:00+08:00",
                "completed_at": None,
                "agent": "需求分发 Agent",
                "tokens": 0,
            }
        )

        response = client.get("/api/tasks", headers=auth_headers)
        body = response.json()

        assert response.status_code == 200
        assert body["total"] >= 1
        assert isinstance(body["items"], list)


def test_root_task_list_defaults_to_cross_tenant_view_without_scope_headers(auth_headers) -> None:
    with TestClient(app) as client:
        _seed_task(
            {
                "id": "task-tenant-001",
                "title": "租户任务",
                "description": "用于校验管理员默认可见租户任务",
                "status": "pending",
                "priority": "medium",
                "created_at": "2026-05-05T17:00:00+08:00",
                "completed_at": None,
                "agent": "需求分发 Agent",
                "tokens": 0,
                "tenant_id": "tenant-20260505070630",
                "tenant_name": "测试",
            }
        )

        response = client.get("/api/tasks", headers=auth_headers)
        body = response.json()

        assert response.status_code == 200
        assert any(item["id"] == "task-tenant-001" for item in body["items"])
        target = next(item for item in body["items"] if item["id"] == "task-tenant-001")
        assert target["tenantId"] == "tenant-20260505070630"


def test_root_task_detail_defaults_to_cross_tenant_view_without_scope_headers(auth_headers) -> None:
    with TestClient(app) as client:
        _seed_task(
            {
                "id": "task-tenant-detail-001",
                "title": "租户任务详情",
                "description": "用于校验管理员默认可查看租户任务详情",
                "status": "pending",
                "priority": "medium",
                "created_at": "2026-05-05T17:05:00+08:00",
                "completed_at": None,
                "agent": "需求分发 Agent",
                "tokens": 0,
                "tenant_id": "tenant-20260505070630",
                "tenant_name": "测试",
            }
        )

        response = client.get("/api/tasks/task-tenant-detail-001", headers=auth_headers)
        body = response.json()

        assert response.status_code == 200
        assert body["id"] == "task-tenant-detail-001"
        assert body["tenantId"] == "tenant-20260505070630"


def test_task_detail_includes_task_agent_group_projection(auth_headers) -> None:
    with TestClient(app) as client:
        task_payload = {
            "id": "task-group-001",
            "title": "多智能体需求任务",
            "description": "用于校验任务域子智能体投影",
            "status": "pending",
            "priority": "medium",
            "created_at": "2026-05-05T18:00:00+08:00",
            "completed_at": None,
            "agent": "需求分发 Agent",
            "tokens": 0,
            "route_decision": {
                "group_id": "reqgrp-task-group-001",
                "execution_scope": "multi_agent",
                "execution_plan": {
                    "coordination_mode": "parallel",
                    "steps": [
                        {
                            "branch_id": "branch-frontend",
                            "role": "frontend",
                            "execution_agent_id": "reqgrp-task-group-001-frontend",
                            "execution_agent": "任务 001 · 前端开发 Agent",
                        }
                    ],
                },
            },
        }
        _seed_task(
            task_payload,
            steps=[
                {
                    "id": "task-group-001-member-running",
                    "title": "前端协同执行",
                    "status": "running",
                    "agent": "任务 001 · 前端开发 Agent",
                    "started_at": "2026-05-05T18:03:00+08:00",
                    "finished_at": None,
                    "message": "正在实现前端页面与交互逻辑",
                    "metadata": {
                        "execution_agent_id": "reqgrp-task-group-001-frontend",
                        "branch_id": "branch-frontend",
                    },
                    "tokens": 128,
                }
            ],
        )

        group_payload = {
            "items": [
                {
                    "id": "reqgrp-task-group-001",
                    "name": "任务 001 · 多智能体开发组",
                    "status": "provisioned",
                    "topology": "multi_agent",
                    "dispatcher_agent_id": "requirement_dispatcher",
                    "development_agents": [
                        {
                            "id": "reqgrp-task-group-001-frontend",
                            "name": "任务 001 · 前端开发 Agent",
                            "role": "frontend",
                        }
                    ],
                    "acceptance_agent": {
                        "id": "reqgrp-task-group-001-acceptance",
                        "name": "任务 001 · 验收 Agent",
                    },
                    "requested_skill_ids": ["skill-a"],
                    "requested_tool_ids": ["tool-a"],
                    "applied_skill_ids": ["skill-a"],
                    "applied_tool_ids": ["tool-a"],
                    "nats_subjects": {
                        "broadcast": "brain.requirement.groups.reqgrp-task-group-001.broadcast",
                    },
                    "timeline": [
                        {
                            "id": "reqgrp-task-group-001:group-created",
                            "kind": "group_created",
                            "title": "创建开发组",
                            "detail": "需求分发 Agent 已创建开发组。",
                            "timestamp": "2026-05-05T18:01:00+08:00",
                            "actor_agent_id": "requirement_dispatcher",
                            "actor_agent_name": "需求分发 Agent",
                            "metadata": {
                                "decision_source": "heuristic",
                                "group_id": "reqgrp-task-group-001",
                            },
                        }
                    ],
                    "warnings": ["示例提示"],
                }
            ]
        }
        store.system_settings["dispatch.requirement_dispatch_agent.groups"] = deepcopy(group_payload)
        persistence_service.persist_system_setting(
            key="dispatch.requirement_dispatch_agent.groups",
            payload=group_payload,
            updated_at=store.now_string(),
        )

        frontend_agent = {
            "id": "reqgrp-task-group-001-frontend",
            "name": "任务 001 · 前端开发 Agent",
            "description": "前端成员",
            "type": "default",
            "status": "idle",
            "enabled": True,
            "tasks_completed": 0,
            "tasks_total": 0,
            "avg_response_time": "--",
            "tokens_used": 0,
            "tokens_limit": 0,
            "success_rate": 0.0,
            "last_active": "未运行",
            "config_snapshot": {
                "status": "generated",
                "files_loaded": ["soul.md"],
                "soul": "# Frontend Soul",
                "agent": {
                    "agent_id": "reqgrp-task-group-001-frontend",
                    "name": "任务 001 · 前端开发 Agent",
                    "type": "default",
                    "metadata": {
                        "source": "requirement_dispatch_agent",
                        "task_id": "task-group-001",
                        "group_id": "reqgrp-task-group-001",
                        "group_role": "frontend",
                        "provisioned_at": "2026-05-05T18:01:10+08:00",
                        "requested_skill_ids": ["skill-a"],
                        "requested_tool_ids": ["tool-a"],
                        "nats_subject": "brain.requirement.groups.reqgrp-task-group-001.members.frontend",
                    },
                },
                "runtime": {
                    "agent_binding": {
                        "provider_key": "openai",
                        "provider_label": "OpenAI",
                        "model": "gpt-5.4",
                    },
                    "brain_skill_binding": {
                        "skill_ids": ["skill-a"],
                    },
                    "tool_binding": {
                        "tool_ids": ["tool-a"],
                    },
                    "agent_metadata": {
                        "metadata": {
                            "source": "requirement_dispatch_agent",
                            "task_id": "task-group-001",
                            "group_id": "reqgrp-task-group-001",
                            "group_role": "frontend",
                            "provisioned_at": "2026-05-05T18:01:10+08:00",
                            "requested_skill_ids": ["skill-a"],
                            "requested_tool_ids": ["tool-a"],
                            "nats_subject": "brain.requirement.groups.reqgrp-task-group-001.members.frontend",
                        }
                    },
                },
            },
        }
        acceptance_agent = {
            "id": "reqgrp-task-group-001-acceptance",
            "name": "任务 001 · 验收 Agent",
            "description": "验收成员",
            "type": "default",
            "status": "idle",
            "enabled": True,
            "tasks_completed": 0,
            "tasks_total": 0,
            "avg_response_time": "--",
            "tokens_used": 0,
            "tokens_limit": 0,
            "success_rate": 0.0,
            "last_active": "未运行",
            "config_snapshot": {
                "status": "generated",
                "files_loaded": ["soul.md"],
                "soul": "# Acceptance Soul",
                "agent": {
                    "agent_id": "reqgrp-task-group-001-acceptance",
                    "name": "任务 001 · 验收 Agent",
                    "type": "default",
                    "metadata": {
                        "source": "requirement_dispatch_agent",
                        "task_id": "task-group-001",
                        "group_id": "reqgrp-task-group-001",
                        "group_role": "acceptance",
                        "provisioned_at": "2026-05-05T18:01:20+08:00",
                    },
                },
            },
        }
        store.agents[:] = [frontend_agent, acceptance_agent]
        persistence_service.persist_agent_state(agent=frontend_agent)
        persistence_service.persist_agent_state(agent=acceptance_agent)

        response = client.get("/api/tasks/task-group-001", headers=auth_headers)
        body = response.json()

        assert response.status_code == 200
        assert body["taskAgentGroup"]["id"] == "reqgrp-task-group-001"
        assert body["taskAgentGroup"]["coordinationMode"] == "parallel"
        assert body["taskAgentGroup"]["developmentAgents"][0]["role"] == "frontend"
        assert body["taskAgentGroup"]["developmentAgents"][0]["model"] == "gpt-5.4"
        assert body["taskAgentGroup"]["developmentAgents"][0]["soul"] == "# Frontend Soul"
        assert body["taskAgentGroup"]["developmentAgents"][0]["runtimeStatus"] == "running"
        assert body["taskAgentGroup"]["developmentAgents"][0]["currentStepTitle"] == "前端协同执行"
        assert body["taskAgentGroup"]["acceptanceAgent"]["id"] == "reqgrp-task-group-001-acceptance"
        assert body["taskAgentGroup"]["timeline"][0]["kind"] == "group_created"
        assert body["taskAgentGroup"]["timeline"][0]["title"] == "创建开发组"
        assert body["taskAgentGroup"]["timeline"][0]["actorAgentId"] == "requirement_dispatcher"
        assert any(item["kind"] == "member_running" for item in body["taskAgentGroup"]["timeline"])


def test_tasks_realtime_stream_returns_filtered_snapshots(auth_headers) -> None:
    task_pending = {
        "id": "task-realtime-001",
        "title": "Hermes 接待后需求一",
        "description": "等待任务分发",
        "status": "pending",
        "priority": "medium",
        "created_at": "2026-05-03T10:00:00+08:00",
        "completed_at": None,
        "agent": "需求分发 Agent",
        "tokens": 0,
        "channel": "dingtalk",
        "session_id": "session-realtime-001",
        "trace_id": "trace-realtime-001",
        "workflow_id": "workflow-realtime-001",
        "workflow_run_id": "run-realtime-001",
    }
    task_completed = {
        "id": "task-realtime-002",
        "title": "Hermes 接待后需求二",
        "description": "已结束任务",
        "status": "completed",
        "priority": "low",
        "created_at": "2026-05-03T09:00:00+08:00",
        "completed_at": "2026-05-03T09:30:00+08:00",
        "agent": "需求分发 Agent",
        "tokens": 0,
        "channel": "dingtalk",
        "session_id": "session-realtime-002",
        "trace_id": "trace-realtime-002",
    }

    with TestClient(app) as client:
        _seed_tasks([task_pending, task_completed])

        with client.websocket_connect("/api/tasks/realtime?status=pending", headers=auth_headers) as websocket:
            payload = websocket.receive_json()
            assert any(item["id"] == "task-realtime-001" for item in payload["items"])
            target = next(item for item in payload["items"] if item["id"] == "task-realtime-001")
            assert target["status"] == "pending"

            store.tasks[0]["status"] = "running"
            persistence_service.persist_execution_state(task=store.tasks[0])
            workflow_realtime_service.publish_run_event(
                {
                    "id": "run-realtime-001",
                    "workflow_id": "workflow-realtime-001",
                    "status": "running",
                },
                "workflow_run.updated",
            )

            updated = websocket.receive_json()
            assert not any(item["id"] == "task-realtime-001" for item in updated["items"])


def test_task_detail_realtime_stream_returns_initial_snapshot_and_updates(auth_headers) -> None:
    with TestClient(app) as client:
        task_payload = {
            "id": "task-detail-realtime-001",
            "title": "任务详情实时流",
            "description": "用于校验任务详情实时推送",
            "status": "pending",
            "priority": "medium",
            "created_at": "2026-05-06T10:00:00+08:00",
            "completed_at": None,
            "agent": "需求分发 Agent",
            "tokens": 0,
            "workflow_id": "workflow-detail-realtime-001",
            "workflow_run_id": "run-detail-realtime-001",
        }
        step_items = [
            {
                "id": "task-detail-realtime-001-step-1",
                "title": "等待执行",
                "status": "pending",
                "agent": "需求分发 Agent",
                "started_at": "2026-05-06T10:00:05+08:00",
                "finished_at": None,
                "message": "任务已进入实时同步链路",
                "tokens": 0,
            }
        ]
        _seed_task(task_payload, steps=step_items)

        workflow_run = {
            "id": "run-detail-realtime-001",
            "workflow_id": "workflow-detail-realtime-001",
            "workflow_name": "detail realtime workflow",
            "task_id": "task-detail-realtime-001",
            "status": "pending",
            "started_at": "2026-05-06T10:00:00+08:00",
            "updated_at": "2026-05-06T10:00:00+08:00",
            "created_at": "2026-05-06T10:00:00+08:00",
            "trigger": "manual",
            "tasks_total": 1,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "tasks_running": 0,
            "tasks_pending": 1,
            "progress_percent": 0,
            "current_stage": "等待执行",
            "execution_path": [],
        }
        store.workflow_runs[:] = [deepcopy(workflow_run)]
        persistence_service.persist_execution_state(workflow_run=workflow_run)

        with client.websocket_connect("/api/tasks/task-detail-realtime-001/realtime", headers=auth_headers) as websocket:
            initial = websocket.receive_json()
            assert initial["type"] == "task.snapshot"
            assert initial["messageType"] == "snapshot"
            assert initial["task"]["id"] == "task-detail-realtime-001"
            assert initial["steps"]["total"] == 1
            assert initial["steps"]["items"][0]["status"] == "pending"

            store.tasks[0]["status"] = "running"
            store.task_steps["task-detail-realtime-001"][0]["status"] = "running"
            store.task_steps["task-detail-realtime-001"][0]["message"] = "任务正在执行中"
            persistence_service.persist_execution_state(
                task=store.tasks[0],
                task_steps=store.task_steps["task-detail-realtime-001"],
            )

            workflow_realtime_service.publish_run_event(
                {
                    "id": "run-detail-realtime-001",
                    "workflow_id": "workflow-detail-realtime-001",
                    "status": "running",
                },
                "workflow_run.updated",
            )

            updated = websocket.receive_json()
            assert updated["type"] == "task.snapshot"
            assert updated["task"]["status"] == "running"
            assert updated["steps"]["items"][0]["status"] == "running"
            assert updated["steps"]["items"][0]["message"] == "任务正在执行中"


def test_dashboard_realtime_stream_returns_stats_and_refreshes_on_workflow_events(auth_headers) -> None:
    with TestClient(app) as client:
        task_payload = {
            "id": "dashboard-realtime-task-001",
            "title": "总控台实时验证",
            "description": "用于校验 dashboard realtime",
            "status": "running",
            "priority": "medium",
            "created_at": "2026-05-06T11:00:00+08:00",
            "completed_at": None,
            "agent": "需求分发 Agent",
            "tokens": 32,
            "workflow_id": "dashboard-workflow-001",
            "workflow_run_id": "dashboard-run-001",
        }
        _seed_task(task_payload)

        workflow_run = {
            "id": "dashboard-run-001",
            "workflow_id": "dashboard-workflow-001",
            "workflow_name": "dashboard realtime workflow",
            "task_id": "dashboard-realtime-task-001",
            "status": "running",
            "started_at": "2026-05-06T11:00:00+08:00",
            "updated_at": "2026-05-06T11:00:00+08:00",
            "created_at": "2026-05-06T11:00:00+08:00",
            "trigger": "manual",
            "tasks_total": 1,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "tasks_running": 1,
            "tasks_pending": 0,
            "progress_percent": 50,
            "current_stage": "执行中",
            "execution_path": [],
        }
        store.workflow_runs[:] = [deepcopy(workflow_run)]
        persistence_service.persist_execution_state(workflow_run=workflow_run)

        with client.websocket_connect("/api/dashboard/realtime", headers=auth_headers) as websocket:
            initial = websocket.receive_json()
            initial_pending = next(item for item in initial["stats"] if item["key"] == "pending_tasks")
            assert initial_pending["value"] == 1

            store.tasks[0]["status"] = "completed"
            store.tasks[0]["completed_at"] = "2026-05-06T11:05:00+08:00"
            persistence_service.persist_execution_state(task=store.tasks[0], task_steps=store.task_steps["dashboard-realtime-task-001"])

            workflow_realtime_service.publish_run_event(
                {
                    **workflow_run,
                    "status": "completed",
                    "tasks_completed": 1,
                    "tasks_running": 0,
                    "progress_percent": 100,
                    "current_stage": "执行完成",
                },
                "workflow_run.completed",
            )

            updated = websocket.receive_json()
            updated_pending = next(item for item in updated["stats"] if item["key"] == "pending_tasks")
            assert updated_pending["value"] == 0
