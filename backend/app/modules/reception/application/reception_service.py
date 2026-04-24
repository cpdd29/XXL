from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.platform.contracts.payload_aliases import alias_bool, alias_text, route_decision_from_task
from app.modules.reception.application.routing_rules import dispatch_intent as default_dispatch_intent


def _normalize_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


CONTEXT_PATCH_CONTINUATION_MARKERS = (
    "补充一下",
    "补充",
    "等等",
    "等下",
    "稍等",
    "继续",
    "接着",
    "续上",
    "刚才",
    "前面",
    "上面",
    "在这个基础上",
    "基于上面",
    "顺着这个",
    "along that",
    "based on that",
    "follow up",
    "add context",
)
CONTEXT_PATCH_EDIT_MARKERS = (
    "更正式",
    "更口语",
    "更简洁",
    "更详细",
    "更具体",
    "改成",
    "改为",
    "强调",
    "突出",
    "补上",
    "加上",
    "增加",
    "去掉",
    "删掉",
    "压缩",
    "缩短",
    "展开",
    "细化",
    "中文输出",
    "英文输出",
)
CONTEXT_PATCH_NEW_TASK_MARKERS = (
    "新任务",
    "另一个任务",
    "另外一个任务",
    "换个任务",
    "换一个任务",
    "重新开一个",
    "重新来一个",
    "new task",
    "another task",
    "separate task",
)
CONTEXT_PATCH_NEW_REQUEST_MARKERS = (
    "请帮我",
    "帮我",
    "帮忙",
    "请搜索",
    "请查",
    "请写",
    "写一封",
    "写一份",
    "写个",
    "搜索",
    "检索",
    "查一下",
    "查找",
    "找一下",
    "生成",
    "总结",
    "整理",
    "翻译",
    "search ",
    "find ",
    "lookup",
    "write ",
    "draft",
    "summarize",
    "translate",
    "help me",
)
CONTEXT_PATCH_MAX_FOLLOW_UP_LENGTH = 80
PROFESSIONAL_CONFIRM_MARKERS = ("确认", "开始", "同意", "继续", "执行", "ok", "yes", "confirm", "proceed")
PROFESSIONAL_CANCEL_MARKERS = ("取消", "不用了", "停止", "驳回", "不执行", "cancel", "stop", "reject", "no")


@dataclass(slots=True)
class ReceptionPayload:
    text: str
    language: str
    channel: str
    user_id: str | None
    session_id: str | None
    metadata: dict[str, Any]


@dataclass(slots=True)
class ActiveTaskReference:
    task_id: str
    last_message_at: datetime


@dataclass(slots=True)
class ManagerUpdatePlan:
    manager_action: str
    next_owner: str
    handoff_summary: str
    reception_mode: str


@dataclass(slots=True)
class ContextPatchPlan:
    updated_description: str
    updated_at: str
    token_delta: int
    manager_update: ManagerUpdatePlan
    audit_entry: dict[str, Any]
    step_entry: dict[str, Any]
    realtime_metadata: dict[str, Any]


@dataclass(slots=True)
class ConfirmationTransition:
    action: str
    task_status: str
    completed_at: str | None
    dispatch_state: str
    manager_update: ManagerUpdatePlan
    step_title: str
    step_message: str
    step_status: str
    response_message: str


class ReceptionService:
    """Normalize inbound message payloads for routing/orchestration."""

    def normalize(self, payload: dict[str, Any] | None) -> ReceptionPayload:
        raw = payload or {}
        text = _normalize_text(raw.get("text") or raw.get("content") or raw.get("message"))
        language = _normalize_text(raw.get("language") or "zh").lower() or "zh"
        channel = _normalize_text(raw.get("channel") or raw.get("source") or "unknown") or "unknown"
        user_id = _normalize_text(raw.get("user_id") or raw.get("userId")) or None
        session_id = _normalize_text(raw.get("session_id") or raw.get("sessionId")) or None
        metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
        return ReceptionPayload(
            text=text,
            language=language,
            channel=channel,
            user_id=user_id,
            session_id=session_id,
            metadata=dict(metadata),
        )

    def should_merge_into_active_task(
        self,
        *,
        active_task: dict[str, Any] | None,
        message_text: str,
        dispatch_intent: Any | None = None,
    ) -> bool:
        intent_dispatcher = dispatch_intent or default_dispatch_intent
        normalized_message = self.normalize_message_text(message_text)
        if not normalized_message or not isinstance(active_task, dict):
            return False
        if self._message_has_marker(normalized_message, CONTEXT_PATCH_NEW_TASK_MARKERS):
            return False
        if self._message_has_marker(normalized_message, CONTEXT_PATCH_CONTINUATION_MARKERS):
            return True
        if self._looks_like_follow_up_instruction(normalized_message):
            return True
        active_intent = self.infer_task_intent(active_task, dispatch_intent=intent_dispatcher)
        incoming_intent = intent_dispatcher(normalized_message)
        if active_intent and incoming_intent != active_intent and self._looks_like_new_request(normalized_message):
            return False
        if self._looks_like_new_request(normalized_message):
            return False
        return False

    def should_context_patch(
        self,
        *,
        active_task: dict[str, Any] | None,
        last_message_at: datetime | None,
        received_at: datetime,
        message_text: str,
        message_debounce_seconds: float,
        dispatch_intent: Any | None = None,
    ) -> bool:
        if not isinstance(active_task, dict) or last_message_at is None:
            return False
        if str(active_task.get("status") or "").strip().lower() not in {"pending", "running"}:
            return False
        if (received_at - last_message_at).total_seconds() > float(message_debounce_seconds):
            return False
        return self.should_merge_into_active_task(
            active_task=active_task,
            message_text=message_text,
            dispatch_intent=dispatch_intent,
        )

    def normalize_message_text(self, text: str | None) -> str:
        return _normalize_text(text).lower()

    def confirmation_action(self, message_text: str) -> str | None:
        normalized = self.normalize_message_text(message_text)
        if not normalized:
            return None
        if self._message_has_marker(normalized, PROFESSIONAL_CONFIRM_MARKERS):
            return "confirm"
        if self._message_has_marker(normalized, PROFESSIONAL_CANCEL_MARKERS):
            return "cancel"
        return None

    def infer_message_intent(
        self,
        message_text: str | None,
        *,
        dispatch_intent: Any | None = None,
    ) -> str | None:
        normalized = self.normalize_message_text(message_text)
        if not normalized:
            return None
        intent_dispatcher = dispatch_intent or default_dispatch_intent
        inferred_intent = intent_dispatcher(normalized)
        if inferred_intent in {"search", "write", "help"}:
            return inferred_intent
        return None

    def is_professional_confirmation_pending(self, task: dict[str, Any] | None) -> bool:
        if not isinstance(task, dict):
            return False
        route_decision = route_decision_from_task(task)
        if route_decision is None:
            return False
        workflow_mode = str(alias_text(route_decision, "workflow_mode", "workflowMode") or "").lower()
        confirmation_required = alias_bool(route_decision, "confirmation_required", "confirmationRequired")
        confirmation_status = str(
            alias_text(route_decision, "confirmation_status", "confirmationStatus") or ""
        ).lower()
        return (
            workflow_mode == "professional_workflow"
            and bool(confirmation_required)
            and confirmation_status == "pending"
            and str(task.get("status") or "").strip().lower() == "pending"
        )

    def infer_task_intent(
        self,
        task: dict[str, Any] | None,
        *,
        dispatch_intent: Any | None = None,
    ) -> str | None:
        if not isinstance(task, dict):
            return None
        intent_dispatcher = dispatch_intent or default_dispatch_intent
        route_decision = route_decision_from_task(task)
        if route_decision is not None:
            intent = str(route_decision.get("intent") or "").strip().lower()
            if intent in {"search", "write", "help"}:
                return intent
        inferred_intent = intent_dispatcher(
            "\n".join(
                part
                for part in (
                    str(task.get("title") or "").strip(),
                    str(task.get("description") or "").strip(),
                )
                if part
            )
        )
        if inferred_intent in {"search", "write", "help"}:
            return inferred_intent
        return None

    def resolve_active_task_reference(
        self,
        *,
        user_key: str,
        active_tasks_by_user: dict[str, str],
        last_message_at_by_user: dict[str, datetime],
        find_task: Any,
        latest_message_at_for_task: Any,
        find_latest_active_task_for_user: Any | None = None,
    ) -> ActiveTaskReference | None:
        normalized_user_key = str(user_key or "").strip()
        if not normalized_user_key:
            return None

        task_id = active_tasks_by_user.get(normalized_user_key)
        last_message_at = last_message_at_by_user.get(normalized_user_key)
        if task_id and last_message_at:
            task = find_task(task_id)
            if isinstance(task, dict) and str(task.get("status") or "").strip().lower() in {"pending", "running"}:
                latest_message_at = latest_message_at_for_task(task)
                if latest_message_at > last_message_at:
                    last_message_at = latest_message_at
                    last_message_at_by_user[normalized_user_key] = latest_message_at
                active_tasks_by_user[normalized_user_key] = task_id
                return ActiveTaskReference(task_id=task_id, last_message_at=last_message_at)

        active_tasks_by_user.pop(normalized_user_key, None)
        last_message_at_by_user.pop(normalized_user_key, None)

        if not callable(find_latest_active_task_for_user):
            return None

        latest_task = find_latest_active_task_for_user(normalized_user_key)
        if not isinstance(latest_task, dict):
            return None

        latest_task_id = str(latest_task.get("id") or "").strip()
        if not latest_task_id:
            return None

        task = find_task(latest_task_id)
        if not isinstance(task, dict) or str(task.get("status") or "").strip().lower() not in {"pending", "running"}:
            return None

        latest_message_at = latest_message_at_for_task(task)
        active_tasks_by_user[normalized_user_key] = latest_task_id
        last_message_at_by_user[normalized_user_key] = latest_message_at
        return ActiveTaskReference(task_id=latest_task_id, last_message_at=latest_message_at)

    def build_context_patch_plan(
        self,
        *,
        task: dict[str, Any],
        message_text: str,
        trace_id: str,
        channel: str,
        user_key: str | None,
        preview_limit: int,
        truncate_text: Any,
        state_machine_version: str,
        now_string: Any,
    ) -> ContextPatchPlan:
        timestamp = now_string()
        manager_packet = task.get("manager_packet")
        session_state = str((manager_packet or {}).get("session_state") or "").strip() or None
        message_preview = truncate_text(message_text, preview_limit)
        return ContextPatchPlan(
            updated_description=f"{task['description']}\n补充上下文: {message_text}",
            updated_at=timestamp,
            token_delta=max(12, len(message_text) // 2),
            manager_update=ManagerUpdatePlan(
                manager_action="continue_active_task",
                next_owner=str(task.get("agent") or "").strip() or "Execution Agent",
                handoff_summary="用户补充了上下文，项目经理将当前任务继续交给执行链路",
                reception_mode="continuation",
            ),
            audit_entry={
                "patched_at": timestamp,
                "trace_id": trace_id,
                "message_preview": message_preview,
                "channel": channel,
                "session_state": session_state,
            },
            step_entry={
                "title": "上下文追加",
                "status": "completed",
                "agent": "Dispatcher Agent",
                "started_at": timestamp,
                "finished_at": timestamp,
                "message": f"收到用户补充消息，已注入当前任务上下文 (trace={trace_id})",
                "metadata": {
                    "state_machine_version": state_machine_version,
                    "trace_id": trace_id,
                    "message_preview": message_preview,
                    "session_state": session_state,
                },
                "tokens": 0,
            },
            realtime_metadata={
                "event": "context_patch_absorbed",
                "user_key": user_key,
                "manager_action": str((manager_packet or {}).get("manager_action") or "").strip() or None,
                "session_state": session_state,
            },
        )

    def build_confirmation_transition(
        self,
        *,
        task: dict[str, Any],
        action: str,
        now_string: Any,
    ) -> ConfirmationTransition:
        if action == "cancel":
            return ConfirmationTransition(
                action=action,
                task_status="cancelled",
                completed_at=now_string(),
                dispatch_state="confirmation_cancelled",
                manager_update=ManagerUpdatePlan(
                    manager_action="clarify_request",
                    next_owner="项目经理 Agent",
                    handoff_summary="用户已取消，项目经理终止本次专业流程",
                    reception_mode="clarify",
                ),
                step_title="确认取消",
                step_message="用户取消专业工作流，本次执行已终止",
                step_status="cancelled",
                response_message="Professional workflow cancelled by user confirmation",
            )

        return ConfirmationTransition(
            action=action,
            task_status="pending",
            completed_at=None,
            dispatch_state="queued",
            manager_update=ManagerUpdatePlan(
                manager_action="handoff_to_execution",
                next_owner=str(task.get("agent") or "").strip() or "Execution Agent",
                handoff_summary="用户已确认，项目经理将任务交给执行链路",
                reception_mode="task_handoff",
            ),
            step_title="确认放行",
            step_message="用户已确认专业工作流，主脑开始进入执行调度",
            step_status="completed",
            response_message="Professional workflow confirmed and dispatched",
        )

    def _looks_like_follow_up_instruction(self, message_text: str) -> bool:
        if len(message_text) > CONTEXT_PATCH_MAX_FOLLOW_UP_LENGTH:
            return False
        return self._message_has_marker(message_text, CONTEXT_PATCH_EDIT_MARKERS)

    def _looks_like_new_request(self, message_text: str) -> bool:
        return self._message_has_marker(message_text, CONTEXT_PATCH_NEW_REQUEST_MARKERS)

    def _message_has_marker(self, message_text: str, markers: tuple[str, ...]) -> bool:
        return any(marker in message_text for marker in markers)


reception_service = ReceptionService()
