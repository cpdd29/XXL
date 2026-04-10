from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from threading import Event, Lock, Thread
from uuid import uuid4

from app.config import get_settings
from app.core.agent_protocol import (
    DEFAULT_MAX_ATTEMPTS,
    apply_protocol_to_run,
    build_protocol_envelope,
    payload_from_message,
    protocol_from_dispatch_context,
    protocol_from_message,
)
from app.core.nats_event_bus import nats_event_bus
from app.services.persistence_service import persistence_service
from app.services.store import store


logger = logging.getLogger(__name__)
AGENT_EXECUTION_SUBJECT = "agent.execution.run"
AGENT_EXECUTION_QUEUE = "agent_execution_workers"
DEFAULT_AGENT_EXECUTION_POLL_INTERVAL_SECONDS = 1.0
DEFAULT_AGENT_EXECUTION_LEASE_SECONDS = 45.0
DEFAULT_AGENT_EXECUTION_SCAN_LIMIT = 50
TERMINAL_TASK_STATUSES = {"completed", "failed", "cancelled"}
AGENT_EXECUTION_RESULT_SUBJECT = "agent.execution.result"
AGENT_EXECUTION_EVENT_SUBJECT = "agent.execution.event"


def _utc_now() -> datetime:
    return datetime.now(UTC)


class AgentExecutionWorkerService:
    def __init__(
        self,
        *,
        event_bus=None,
        persistence=None,
        poll_interval_seconds: float | None = None,
        lease_seconds: float | None = None,
        scan_limit: int | None = None,
        worker_id: str | None = None,
    ) -> None:
        settings = get_settings()
        self._event_bus = event_bus or nats_event_bus
        self._persistence = persistence or persistence_service
        self._poll_interval_seconds = max(
            float(
                poll_interval_seconds
                if poll_interval_seconds is not None
                else settings.workflow_execution_poll_interval_seconds
            ),
            0.1,
        )
        self._lease_seconds = max(
            float(
                lease_seconds
                if lease_seconds is not None
                else settings.workflow_execution_lease_seconds
            ),
            1.0,
        )
        self._scan_limit = max(
            int(
                scan_limit
                if scan_limit is not None
                else settings.workflow_execution_scan_limit
            ),
            1,
        )
        self.worker_id = worker_id or f"agent-worker-{uuid4().hex[:12]}"
        self._stop_event = Event()
        self._lock = Lock()
        self._thread: Thread | None = None
        self._event_bus.subscribe(
            AGENT_EXECUTION_SUBJECT,
            self._handle_execution_message,
            queue_group=AGENT_EXECUTION_QUEUE,
        )

    def start(self) -> bool:
        initialize = getattr(self._event_bus, "initialize", None)
        event_bus_ready = bool(initialize()) if callable(initialize) else False
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return event_bus_ready
            self._stop_event.clear()
            self._thread = Thread(
                target=self._run_loop,
                daemon=True,
                name="workbot-agent-execution-worker",
            )
            self._thread.start()
        return event_bus_ready

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            self._thread = None

        self._stop_event.set()
        if thread is not None:
            thread.join(timeout=self._poll_interval_seconds + 0.5)
        self._stop_event.clear()

    def enqueue_execution(
        self,
        *,
        run_id: str,
        task_id: str,
        workflow_id: str,
        execution_agent_id: str | None,
        step_delay: float,
        published_at: str | None = None,
        protocol: dict | None = None,
    ) -> bool:
        normalized_run_id = str(run_id or "").strip()
        normalized_task_id = str(task_id or "").strip()
        normalized_workflow_id = str(workflow_id or "").strip()
        if not normalized_run_id or not normalized_task_id or not normalized_workflow_id:
            return False

        queued_at = str(published_at or _utc_now().isoformat()).strip()
        payload = {
            "run_id": normalized_run_id,
            "task_id": normalized_task_id,
            "workflow_id": normalized_workflow_id,
            "execution_agent_id": str(execution_agent_id or "").strip() or None,
            "step_delay": step_delay,
            "published_at": queued_at,
        }
        run = self._find_run(normalized_run_id)
        envelope, resolved_protocol = build_protocol_envelope(
            message_name="agent.execution.request",
            message_type="command",
            payload=payload,
            protocol=protocol,
            dispatch_context=(run or {}).get("dispatch_context") if isinstance(run, dict) else None,
            run_id=normalized_run_id,
            default_max_attempts=DEFAULT_MAX_ATTEMPTS,
            attempt=(protocol or {}).get("attempt"),
            emitted_at=queued_at,
            available_at=queued_at,
            source={"kind": "agent_execution_dispatcher", "id": self.worker_id},
            target={"kind": "agent_execution_worker", "id": AGENT_EXECUTION_QUEUE},
        )
        if run is not None:
            apply_protocol_to_run(run, resolved_protocol)
            self._persist_run(run)
        durable = self._ensure_agent_execution_job(
            normalized_run_id,
            task_id=normalized_task_id,
            workflow_id=normalized_workflow_id,
            execution_agent_id=str(execution_agent_id or "").strip() or None,
            available_at=queued_at,
            step_delay=step_delay,
            protocol=resolved_protocol,
        )
        published = self._event_bus.publish_json(AGENT_EXECUTION_SUBJECT, envelope)
        return durable or published

    def poll_once(self) -> dict[str, int]:
        summary = {
            "executed": 0,
            "skipped_terminal": 0,
            "skipped_claimed": 0,
        }

        due_jobs = self._load_due_execution_jobs()
        if due_jobs is None:
            return summary

        for job in due_jobs:
            result = self._consume_execution_job(job)
            if result in summary:
                summary[result] += 1
        return summary

    def _run_loop(self) -> None:
        while not self._stop_event.wait(timeout=self._poll_interval_seconds):
            try:
                self.poll_once()
            except Exception as exc:  # pragma: no cover - defensive runtime guard
                logger.warning("Agent execution worker iteration failed: %s", exc)

    def _handle_execution_message(self, _: str, payload: dict) -> None:
        normalized_payload = payload_from_message(payload)
        protocol = protocol_from_message(payload)
        if protocol.get("message_type") and protocol.get("message_type") != "command":
            return

        run_id = str(normalized_payload.get("run_id") or normalized_payload.get("runId") or "").strip()
        task_id = str(normalized_payload.get("task_id") or normalized_payload.get("taskId") or "").strip()
        workflow_id = str(
            normalized_payload.get("workflow_id") or normalized_payload.get("workflowId") or ""
        ).strip()
        if not run_id or not task_id or not workflow_id:
            return

        step_delay = float(
            normalized_payload.get("step_delay") or normalized_payload.get("stepDelay") or 0.0
        )
        run = self._find_run(run_id)
        if run is not None and protocol.get("request_id"):
            apply_protocol_to_run(
                run,
                {
                    **protocol_from_dispatch_context(run),
                    **protocol,
                },
            )
            self._persist_run(run)
        self._ensure_agent_execution_job(
            run_id,
            task_id=task_id,
            workflow_id=workflow_id,
            execution_agent_id=str(
                normalized_payload.get("execution_agent_id")
                or normalized_payload.get("executionAgentId")
                or ""
            ).strip()
            or None,
            available_at=str(
                normalized_payload.get("published_at")
                or normalized_payload.get("publishedAt")
                or protocol.get("available_at")
                or protocol.get("emitted_at")
                or ""
            ).strip()
            or _utc_now().isoformat(),
            step_delay=step_delay,
            protocol=protocol,
        )
        claimed_job = self._claim_execution_job(run_id)
        if claimed_job is None and not getattr(self._persistence, "enabled", False):
            claimed_job = {
                "run_id": run_id,
                "task_id": task_id,
                "workflow_id": workflow_id,
                "execution_agent_id": str(
                    payload.get("execution_agent_id") or payload.get("executionAgentId") or ""
                ).strip()
                or None,
                "step_delay_seconds": step_delay,
                "claimed_at": None,
                **protocol,
            }
        if claimed_job is None:
            return
        self._consume_execution_job(claimed_job)

    def _load_due_execution_jobs(self) -> list[dict] | None:
        claim_due_jobs = getattr(self._persistence, "claim_due_agent_execution_jobs", None)
        if not getattr(self._persistence, "enabled", False) or not callable(claim_due_jobs):
            return None

        deadline = _utc_now()
        claimed_jobs = claim_due_jobs(
            worker_id=self.worker_id,
            claimed_at=deadline.isoformat(),
            lease_expires_at=(deadline + timedelta(seconds=self._lease_seconds)).isoformat(),
            due_before=deadline.isoformat(),
            limit=self._scan_limit,
        )
        if claimed_jobs is None:
            return None
        return [store.clone(job) for job in claimed_jobs[: self._scan_limit]]

    def _consume_execution_job(self, job: dict) -> str:
        run_id = str(job.get("run_id") or "").strip()
        task_id = str(job.get("task_id") or "").strip()
        if not run_id or not task_id:
            return "skipped_claimed"

        from app.services import workflow_execution_service

        task = self._find_task(task_id)
        run = self._find_run(run_id)
        protocol = self._resolve_protocol(job, run)
        if task is None:
            self._delete_execution_job(run_id, claimed_at=job.get("claimed_at"))
            return "skipped_terminal"
        if str(task.get("status") or "").strip().lower() in TERMINAL_TASK_STATUSES:
            self._delete_execution_job(run_id, claimed_at=job.get("claimed_at"))
            return "skipped_terminal"

        try:
            completed_run = workflow_execution_service.complete_agent_execution_job(
                run_id,
                execution_agent_id=str(job.get("execution_agent_id") or "").strip() or None,
            )
        except Exception as exc:  # pragma: no cover - defensive worker guard
            logger.warning("Agent execution worker failed for run %s: %s", run_id, exc)
            current_attempt = max(int(protocol.get("attempt") or 1), 1)
            max_attempts = max(int(protocol.get("max_attempts") or DEFAULT_MAX_ATTEMPTS), 1)
            if current_attempt < max_attempts:
                requeued_at = _utc_now().isoformat()
                self._delete_execution_job(run_id, claimed_at=job.get("claimed_at"))
                self.enqueue_execution(
                    run_id=run_id,
                    task_id=task_id,
                    workflow_id=str(job.get("workflow_id") or "").strip(),
                    execution_agent_id=str(job.get("execution_agent_id") or "").strip() or None,
                    step_delay=float(job.get("step_delay_seconds") or 0.0),
                    published_at=requeued_at,
                    protocol={
                        **protocol,
                        "attempt": current_attempt + 1,
                        "last_error": str(exc),
                        "dead_letter": False,
                        "dead_letter_reason": None,
                    },
                )
                self._publish_execution_event(
                    run_id=run_id,
                    task_id=task_id,
                    workflow_id=str(job.get("workflow_id") or "").strip() or None,
                    execution_agent_id=str(job.get("execution_agent_id") or "").strip() or None,
                    protocol={
                        **protocol,
                        "last_error": str(exc),
                    },
                    message_name="agent.execution.retry_scheduled",
                    emitted_at=requeued_at,
                    error_message=f"Agent 执行失败，准备第 {current_attempt + 1} 次重试：{exc}",
                )
                return "skipped_claimed"

            dead_letter_at = _utc_now().isoformat()
            dead_letter_protocol = {
                **protocol,
                "dead_letter": True,
                "dead_letter_reason": str(exc),
                "last_error": str(exc),
            }
            if run is not None:
                apply_protocol_to_run(run, dead_letter_protocol)
                self._persist_run(run)
            self._publish_execution_event(
                run_id=run_id,
                task_id=task_id,
                workflow_id=str(job.get("workflow_id") or "").strip() or None,
                execution_agent_id=str(job.get("execution_agent_id") or "").strip() or None,
                protocol=dead_letter_protocol,
                message_name="agent.execution.dead_lettered",
                emitted_at=dead_letter_at,
                error_message=str(exc),
                dead_letter=True,
                dead_letter_reason=str(exc),
            )
            workflow_execution_service.fail_workflow_run_due_agent_execution_error(
                run_id,
                failure_message=f"Agent 执行失败并进入死信：{exc}",
            )
            self._delete_execution_job(run_id, claimed_at=job.get("claimed_at"))
            return "skipped_claimed"

        refreshed_run = self._find_run(run_id) or completed_run
        if refreshed_run is not None:
            self._publish_execution_event(
                run_id=run_id,
                task_id=task_id,
                workflow_id=str(job.get("workflow_id") or "").strip() or None,
                execution_agent_id=str(job.get("execution_agent_id") or "").strip() or None,
                protocol=protocol,
                message_name="agent.execution.completed",
                emitted_at=_utc_now().isoformat(),
                status=str(refreshed_run.get("status") or "").strip() or None,
                subject=AGENT_EXECUTION_RESULT_SUBJECT,
                message_type="result",
            )
        self._delete_execution_job(run_id, claimed_at=job.get("claimed_at"))
        return "executed"

    def _ensure_agent_execution_job(
        self,
        run_id: str,
        *,
        task_id: str,
        workflow_id: str,
        execution_agent_id: str | None,
        available_at: str,
        step_delay: float,
        protocol: dict | None = None,
    ) -> bool:
        upsert_job = getattr(self._persistence, "upsert_agent_execution_job", None)
        if not getattr(self._persistence, "enabled", False) or not callable(upsert_job):
            return False

        return (
            upsert_job(
                run_id,
                task_id=task_id,
                workflow_id=workflow_id,
                execution_agent_id=execution_agent_id,
                available_at=available_at,
                queued_at=available_at,
                step_delay_seconds=step_delay,
                **{
                    key: value
                    for key, value in (protocol or {}).items()
                    if key not in {"available_at", "emitted_at"}
                },
            )
            is not None
        )

    def _claim_execution_job(self, run_id: str) -> dict | None:
        claim_job = getattr(self._persistence, "claim_agent_execution_job", None)
        if not getattr(self._persistence, "enabled", False) or not callable(claim_job):
            return None

        now = _utc_now()
        return claim_job(
            run_id,
            worker_id=self.worker_id,
            claimed_at=now.isoformat(),
            lease_expires_at=(now + timedelta(seconds=self._lease_seconds)).isoformat(),
            due_before=now.isoformat(),
            respect_existing_owner=True,
        )

    def _delete_execution_job(self, run_id: str, *, claimed_at: str | None = None) -> None:
        delete_job = getattr(self._persistence, "delete_agent_execution_job", None)
        if not getattr(self._persistence, "enabled", False) or not callable(delete_job):
            return
        delete_job(run_id, worker_id=self.worker_id, claimed_at=claimed_at)

    def _find_task(self, task_id: str) -> dict | None:
        if getattr(self._persistence, "enabled", False):
            get_task = getattr(self._persistence, "get_task", None)
            if callable(get_task):
                return get_task(task_id)
        for task in store.tasks:
            if str(task.get("id") or "").strip() == task_id:
                return task
        return None

    def _find_run(self, run_id: str) -> dict | None:
        if getattr(self._persistence, "enabled", False):
            get_run = getattr(self._persistence, "get_workflow_run", None)
            if callable(get_run):
                return get_run(run_id)
        for run in store.workflow_runs:
            if str(run.get("id") or "").strip() == run_id:
                return run
        return None

    def _persist_run(self, run: dict | None) -> None:
        if run is None:
            return

        persist_execution_state = getattr(self._persistence, "persist_execution_state", None)
        if callable(persist_execution_state):
            if persist_execution_state(workflow_run=run):
                return
            if getattr(self._persistence, "enabled", False):
                return

        self._persistence.persist_runtime_state()

    @staticmethod
    def _resolve_protocol(job: dict | None, run: dict | None) -> dict:
        protocol = protocol_from_dispatch_context(run)
        message_protocol = protocol_from_message(job)
        protocol.update({key: value for key, value in message_protocol.items() if value is not None})
        return protocol

    def _publish_execution_event(
        self,
        *,
        run_id: str,
        task_id: str,
        workflow_id: str | None,
        execution_agent_id: str | None,
        protocol: dict,
        message_name: str,
        emitted_at: str,
        error_message: str | None = None,
        dead_letter: bool = False,
        dead_letter_reason: str | None = None,
        status: str | None = None,
        subject: str = AGENT_EXECUTION_EVENT_SUBJECT,
        message_type: str = "event",
    ) -> None:
        run = self._find_run(run_id)
        payload = {
            "run_id": run_id,
            "task_id": task_id,
            "workflow_id": workflow_id,
            "execution_agent_id": execution_agent_id,
            "status": status,
        }
        if error_message:
            payload["error_message"] = error_message
        envelope, resolved_protocol = build_protocol_envelope(
            message_name=message_name,
            message_type=message_type,
            payload=payload,
            protocol=protocol,
            dispatch_context=(run or {}).get("dispatch_context") if isinstance(run, dict) else None,
            run_id=run_id,
            attempt=protocol.get("attempt"),
            emitted_at=emitted_at,
            available_at=emitted_at,
            dead_letter=dead_letter,
            dead_letter_reason=dead_letter_reason,
            last_error=error_message,
            source={"kind": "agent_execution_worker", "id": self.worker_id},
            target={"kind": "workflow_execution", "id": workflow_id or "direct-agent-run"},
        )
        if run is not None:
            apply_protocol_to_run(run, resolved_protocol)
            self._persist_run(run)
        self._event_bus.publish_json(subject, envelope)


agent_execution_worker_service = AgentExecutionWorkerService()
