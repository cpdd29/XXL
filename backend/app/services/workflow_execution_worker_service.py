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
from app.core.event_subjects import (
    WORKFLOW_EXECUTION_CLAIMED_SUBJECT,
    WORKFLOW_EXECUTION_COMPLETED_SUBJECT,
    WORKFLOW_EXECUTION_FAILED_SUBJECT,
    WORKFLOW_EXECUTION_STARTED_SUBJECT,
)
from app.core.nats_event_bus import nats_event_bus
from app.services.persistence_service import persistence_service
from app.services.scheduler_guard_service import scheduler_guard_service
from app.services.store import store
from app.services.workflow_dispatcher_service import (
    WORKFLOW_EXECUTION_QUEUE,
    WORKFLOW_EXECUTION_SUBJECT,
    workflow_dispatcher_service,
)


logger = logging.getLogger(__name__)
DEFAULT_EXECUTION_POLL_INTERVAL_SECONDS = 1.0
DEFAULT_EXECUTION_LEASE_SECONDS = 45.0
DEFAULT_EXECUTION_SCAN_LIMIT = 50
TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled"}
WORKFLOW_EXECUTION_RESULT_SUBJECT = "workflow.execution.result"
WORKFLOW_EXECUTION_EVENT_SUBJECT = "workflow.execution.event"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _run_workflow_policy(run: dict | None) -> dict:
    if not isinstance(run, dict):
        return {}
    dispatch_context = run.get("dispatch_context")
    if not isinstance(dispatch_context, dict):
        return {}
    policy = dispatch_context.get("workflow_policy")
    if not isinstance(policy, dict):
        policy = dispatch_context.get("workflowPolicy")
    return policy if isinstance(policy, dict) else {}


class WorkflowExecutionWorkerService:
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
        self.worker_id = worker_id or f"worker-{uuid4().hex[:12]}"
        self._stop_event = Event()
        self._lock = Lock()
        self._thread: Thread | None = None
        self._event_bus.subscribe(
            WORKFLOW_EXECUTION_SUBJECT,
            self._handle_execution_message,
            queue_group=WORKFLOW_EXECUTION_QUEUE,
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
                name="workbot-workflow-execution-worker",
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

    def poll_once(self) -> dict[str, int]:
        summary = {
            "executed": 0,
            "repaired": 0,
            "skipped_claimed": 0,
            "skipped_terminal": 0,
        }
        guard_summary = scheduler_guard_service.guard_workflow_execution_runtime(
            now=_utc_now(),
            persistence=self._persistence,
        )
        summary["repaired"] += int(guard_summary.get("repaired_missing_jobs") or 0)

        due_jobs = self._load_due_execution_jobs()
        if due_jobs is not None:
            for job in due_jobs:
                result = self._consume_execution_job(job)
                if result in summary:
                    summary[result] += 1

        repaired_runs = self._repair_missing_execution_jobs()
        if repaired_runs:
            summary["repaired"] += len(repaired_runs)
            for run in repaired_runs:
                claimed_job = self._claim_execution_job(
                    str(run.get("id") or "").strip(),
                    due_before=run.get("updated_at"),
                )
                if claimed_job is None:
                    continue
                result = self._consume_execution_job(claimed_job)
                if result in summary:
                    summary[result] += 1

        return summary

    def _run_loop(self) -> None:
        while not self._stop_event.wait(timeout=self._poll_interval_seconds):
            try:
                self.poll_once()
            except Exception as exc:  # pragma: no cover - defensive runtime guard
                logger.warning("Workflow execution worker iteration failed: %s", exc)

    def _handle_execution_message(self, _: str, payload: dict) -> None:
        normalized_payload = payload_from_message(payload)
        protocol = protocol_from_message(payload)
        if protocol.get("message_type") and protocol.get("message_type") != "command":
            return

        run_id = str(normalized_payload.get("run_id") or normalized_payload.get("runId") or "").strip()
        if not run_id:
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
        self._ensure_execution_job(
            run_id,
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
                "step_delay_seconds": step_delay,
                "claimed_at": None,
                **protocol,
            }
        if claimed_job is None:
            return
        self._consume_execution_job(
            claimed_job,
            dispatcher_id=str(
                normalized_payload.get("dispatcher_id") or normalized_payload.get("dispatcherId") or ""
            ).strip()
            or None,
        )

    def _load_due_execution_jobs(self) -> list[dict] | None:
        claim_due_jobs = getattr(self._persistence, "claim_due_workflow_execution_jobs", None)
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

        return [
            store.clone(job)
            for job in sorted(
                claimed_jobs,
                key=lambda job: (
                    _parse_datetime(job.get("available_at")) or deadline,
                    str(job.get("run_id") or ""),
                ),
            )[: self._scan_limit]
        ]

    def _repair_missing_execution_jobs(self) -> list[dict]:
        runs = self._list_dispatched_runs()
        if not runs:
            return []

        repaired: list[dict] = []
        for run in runs:
            run_id = str(run.get("id") or "").strip()
            if not run_id:
                continue
            if self._get_execution_job(run_id) is not None:
                continue
            if not self._ensure_execution_job(
                run_id,
                available_at=str(run.get("updated_at") or run.get("started_at") or "").strip()
                or _utc_now().isoformat(),
                step_delay=self._step_delay_for_run(run),
                protocol=protocol_from_dispatch_context(run),
            ):
                continue
            repaired.append(run)
        return repaired

    def _list_dispatched_runs(self) -> list[dict]:
        if getattr(self._persistence, "enabled", False):
            list_runs = getattr(self._persistence, "list_workflow_runs", None)
            if callable(list_runs):
                runs = list_runs()
                if runs is None:
                    return []
                source_runs = runs
            else:
                return []
        else:
            source_runs = store.workflow_runs

        candidates: list[dict] = []
        for run in source_runs:
            if str(run.get("status") or "").strip().lower() in TERMINAL_RUN_STATUSES:
                continue
            dispatch_context = run.get("dispatch_context")
            if not isinstance(dispatch_context, dict):
                continue
            state = str(dispatch_context.get("state") or "").strip().lower()
            if state != "dispatched":
                continue
            candidates.append(store.clone(run))

        candidates.sort(
            key=lambda run: (
                _parse_datetime(run.get("updated_at")) or _utc_now(),
                str(run.get("id") or ""),
            )
        )
        return candidates[: self._scan_limit]

    def _step_delay_for_run(self, run: dict) -> float:
        next_dispatch_at = _parse_datetime(str(run.get("next_dispatch_at") or "").strip())
        updated_at = _parse_datetime(str(run.get("updated_at") or "").strip()) or _utc_now()
        if next_dispatch_at is None:
            policy = _run_workflow_policy(run)
            try:
                return max(float(policy.get("step_delay_seconds") or policy.get("stepDelaySeconds") or 0.0), 0.0)
            except (TypeError, ValueError):
                return 0.0
        return max((next_dispatch_at - updated_at).total_seconds(), 0.0)

    def _execution_timed_out(self, run: dict | None, *, now: datetime) -> bool:
        if not isinstance(run, dict):
            return False
        if str(run.get("status") or "").strip().lower() in TERMINAL_RUN_STATUSES:
            return False

        policy = _run_workflow_policy(run)
        if not policy:
            return False
        try:
            timeout_seconds = float(
                policy.get("execution_timeout_seconds")
                or policy.get("executionTimeoutSeconds")
                or 45.0
            )
        except (TypeError, ValueError):
            timeout_seconds = 45.0
        if timeout_seconds <= 0:
            timeout_seconds = 45.0

        dispatch_context = run.get("dispatch_context")
        started_at = None
        if isinstance(dispatch_context, dict):
            started_at = _parse_datetime(
                str(dispatch_context.get("dispatched_at") or dispatch_context.get("dispatchedAt") or "")
            )
        if started_at is None:
            started_at = _parse_datetime(
                str(run.get("started_at") or run.get("updated_at") or run.get("created_at") or "")
            )
        if started_at is None:
            return False
        return started_at + timedelta(seconds=timeout_seconds) <= now

    def _consume_execution_job(
        self,
        job: dict,
        *,
        dispatcher_id: str | None = None,
    ) -> str:
        run_id = str(job.get("run_id") or "").strip()
        if not run_id:
            return "skipped_claimed"

        from app.services import workflow_execution_service
        from app.services.workflow_scheduler_service import workflow_scheduler_service

        run = self._find_run(run_id)
        protocol = self._resolve_protocol(job, run)
        if run is None and getattr(self._persistence, "enabled", False):
            self._delete_execution_job(run_id, claimed_at=job.get("claimed_at"))
            self._release_dispatch_claim(run_id, dispatcher_id=dispatcher_id)
            return "skipped_terminal"
        if run is not None and str(run.get("status") or "").strip().lower() in TERMINAL_RUN_STATUSES:
            self._delete_execution_job(run_id, claimed_at=job.get("claimed_at"))
            self._release_dispatch_claim(
                run_id,
                dispatcher_id=dispatcher_id or str(run.get("dispatcher_id") or "").strip() or None,
            )
            return "skipped_terminal"

        if self._execution_timed_out(run, now=_utc_now()):
            failure_message = "工作流执行超过超时阈值，已标记失败"
            workflow_execution_service.fail_workflow_run_due_execution_timeout(
                run_id,
                failure_message=failure_message,
            )
            self._delete_execution_job(run_id, claimed_at=job.get("claimed_at"))
            self._release_dispatch_claim(
                run_id,
                dispatcher_id=dispatcher_id or str((run or {}).get("dispatcher_id") or "").strip() or None,
            )
            return "executed"

        if str(job.get("claimed_at") or "").strip():
            self._publish_execution_event(
                run=run,
                protocol=protocol,
                message_name="workflow.execution.claimed",
                dispatcher_id=dispatcher_id or str((run or {}).get("dispatcher_id") or "").strip() or None,
                emitted_at=str(job.get("claimed_at") or "").strip() or _utc_now().isoformat(),
                status="claimed",
                lease_until=str(job.get("lease_expires_at") or "").strip() or None,
                subject=WORKFLOW_EXECUTION_CLAIMED_SUBJECT,
                legacy_subject=WORKFLOW_EXECUTION_EVENT_SUBJECT,
            )

        self._publish_execution_event(
            run=run,
            protocol=protocol,
            message_name="workflow.execution.started",
            dispatcher_id=dispatcher_id or str((run or {}).get("dispatcher_id") or "").strip() or None,
            emitted_at=_utc_now().isoformat(),
            status="started",
            lease_until=str(job.get("lease_expires_at") or "").strip() or None,
            subject=WORKFLOW_EXECUTION_STARTED_SUBJECT,
            legacy_subject=WORKFLOW_EXECUTION_EVENT_SUBJECT,
        )
        try:
            result = workflow_execution_service.execute_workflow_run(run_id)
        except Exception as exc:  # pragma: no cover - defensive worker guard
            logger.warning("Workflow execution worker failed for run %s: %s", run_id, exc)
            current_attempt = max(int(protocol.get("attempt") or 1), 1)
            max_attempts = self._max_attempts_for_protocol(protocol, run)
            if current_attempt >= max_attempts:
                dead_letter_protocol = {
                    **protocol,
                    "dead_letter": True,
                    "dead_letter_reason": str(exc),
                    "last_error": str(exc),
                }
                if run is not None:
                    apply_protocol_to_run(run, dead_letter_protocol)
                    self._persist_run(run)
                dead_letter_at = _utc_now().isoformat()
                self._publish_execution_event(
                    run=run,
                    protocol=dead_letter_protocol,
                    message_name="workflow.execution.dead_lettered",
                    dispatcher_id=dispatcher_id or str((run or {}).get("dispatcher_id") or "").strip() or None,
                    emitted_at=dead_letter_at,
                    error_message=str(exc),
                    status="dead_lettered",
                    dead_letter=True,
                    dead_letter_reason=str(exc),
                    subject=WORKFLOW_EXECUTION_FAILED_SUBJECT,
                    legacy_subject=WORKFLOW_EXECUTION_EVENT_SUBJECT,
                )
                workflow_execution_service.fail_workflow_run_due_agent_execution_error(
                    run_id,
                    failure_message=f"工作流执行失败并进入死信：{exc}",
                )
                self._delete_execution_job(run_id, claimed_at=job.get("claimed_at"))
                self._release_dispatch_claim(
                    run_id,
                    dispatcher_id=dispatcher_id or str((run or {}).get("dispatcher_id") or "").strip() or None,
                )
                return "skipped_claimed"

            retry_protocol = {
                **protocol,
                "attempt": current_attempt + 1,
                "dead_letter": False,
                "dead_letter_reason": None,
                "last_error": str(exc),
            }
            if run is not None:
                apply_protocol_to_run(run, retry_protocol)
                self._persist_run(run)
            step_delay = float(job.get("step_delay_seconds") or 0.0)
            workflow_scheduler_service.defer(
                run_id,
                delay=max(step_delay, 0.5),
                step_delay=step_delay,
                dispatcher_id=dispatcher_id or str((run or {}).get("dispatcher_id") or "").strip() or None,
            )
            self._publish_execution_event(
                run=run,
                protocol=retry_protocol,
                message_name="workflow.execution.deferred",
                dispatcher_id=dispatcher_id or str((run or {}).get("dispatcher_id") or "").strip() or None,
                error_message=str(exc),
                emitted_at=_utc_now().isoformat(),
                status="retry_scheduled",
            )
            self._delete_execution_job(run_id, claimed_at=job.get("claimed_at"))
            self._release_dispatch_claim(
                run_id,
                dispatcher_id=dispatcher_id or str((run or {}).get("dispatcher_id") or "").strip() or None,
            )
            return "skipped_claimed"

        refreshed_run = self._find_run(run_id) or result or run
        self._publish_execution_event(
            run=refreshed_run,
            protocol=self._resolve_protocol(job, refreshed_run),
            message_name="workflow.execution.completed",
            dispatcher_id=dispatcher_id
            or str((result or {}).get("dispatcher_id") or "").strip()
            or str((run or {}).get("dispatcher_id") or "").strip()
            or None,
            emitted_at=_utc_now().isoformat(),
            result_payload={"status": str((result or {}).get("status") or "").strip() or None},
            subject=WORKFLOW_EXECUTION_COMPLETED_SUBJECT,
            legacy_subject=WORKFLOW_EXECUTION_RESULT_SUBJECT,
            message_type="result",
        )
        self._delete_execution_job(run_id, claimed_at=job.get("claimed_at"))
        self._release_dispatch_claim(
            run_id,
            dispatcher_id=dispatcher_id
            or str((result or {}).get("dispatcher_id") or "").strip()
            or str((run or {}).get("dispatcher_id") or "").strip()
            or None,
        )
        return "executed"

    def _ensure_execution_job(
        self,
        run_id: str,
        *,
        available_at: str,
        step_delay: float,
        protocol: dict | None = None,
    ) -> bool:
        upsert_job = getattr(self._persistence, "upsert_workflow_execution_job", None)
        if not getattr(self._persistence, "enabled", False) or not callable(upsert_job):
            return False

        return (
            upsert_job(
                run_id,
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

    def _claim_execution_job(self, run_id: str, *, due_before: str | None = None) -> dict | None:
        claim_job = getattr(self._persistence, "claim_workflow_execution_job", None)
        if not getattr(self._persistence, "enabled", False) or not callable(claim_job):
            return None

        now = _utc_now()
        return claim_job(
            run_id,
            worker_id=self.worker_id,
            claimed_at=now.isoformat(),
            lease_expires_at=(now + timedelta(seconds=self._lease_seconds)).isoformat(),
            due_before=due_before or now.isoformat(),
            respect_existing_owner=True,
        )

    def _get_execution_job(self, run_id: str) -> dict | None:
        get_job = getattr(self._persistence, "get_workflow_execution_job", None)
        if not getattr(self._persistence, "enabled", False) or not callable(get_job):
            return None
        return get_job(run_id)

    def _delete_execution_job(self, run_id: str, *, claimed_at: str | None = None) -> None:
        delete_job = getattr(self._persistence, "delete_workflow_execution_job", None)
        if not getattr(self._persistence, "enabled", False) or not callable(delete_job):
            return
        delete_job(run_id, worker_id=self.worker_id, claimed_at=claimed_at)

    def _find_run(self, run_id: str) -> dict | None:
        if getattr(self._persistence, "enabled", False):
            get_run = getattr(self._persistence, "get_workflow_run", None)
            if callable(get_run):
                return get_run(run_id)
            return None
        for run in store.workflow_runs:
            if str(run.get("id") or "").strip() == run_id:
                return run
        return None

    def _release_dispatch_claim(self, run_id: str, *, dispatcher_id: str | None) -> None:
        normalized_dispatcher_id = str(dispatcher_id or "").strip()
        if not normalized_dispatcher_id:
            return

        release_claim = getattr(self._persistence, "release_workflow_run_claim", None)
        if getattr(self._persistence, "enabled", False) and callable(release_claim):
            released = release_claim(run_id, dispatcher_id=normalized_dispatcher_id)
            if released is not None:
                return

        workflow_dispatcher_service.release_run_claim(run_id)

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

    @staticmethod
    def _max_attempts_for_protocol(protocol: dict | None, run: dict | None) -> int:
        if isinstance(protocol, dict):
            try:
                resolved = int(protocol.get("max_attempts") or 0)
            except (TypeError, ValueError):
                resolved = 0
            if resolved > 0:
                return resolved
        policy = _run_workflow_policy(run)
        try:
            resolved = int(policy.get("max_dispatch_retry") or policy.get("maxDispatchRetry") or 0)
        except (TypeError, ValueError):
            resolved = 0
        return max(resolved, DEFAULT_MAX_ATTEMPTS, 1)

    def _publish_execution_event(
        self,
        *,
        run: dict | None,
        protocol: dict,
        message_name: str,
        dispatcher_id: str | None,
        emitted_at: str,
        error_message: str | None = None,
        result_payload: dict | None = None,
        status: str | None = None,
        lease_until: str | None = None,
        dead_letter: bool = False,
        dead_letter_reason: str | None = None,
        subject: str = WORKFLOW_EXECUTION_EVENT_SUBJECT,
        legacy_subject: str | None = None,
        message_type: str = "event",
    ) -> None:
        payload = {
            "run_id": str((run or {}).get("id") or "").strip() or None,
            "task_id": str((run or {}).get("task_id") or "").strip() or None,
            "workflow_id": str((run or {}).get("workflow_id") or "").strip() or None,
            "dispatcher_id": dispatcher_id,
            "status": status or str((run or {}).get("status") or "").strip() or None,
        }
        if lease_until:
            payload["lease_until"] = lease_until
        if error_message:
            payload["error_message"] = error_message
        if isinstance(result_payload, dict):
            payload.update(result_payload)
        envelope, resolved_protocol = build_protocol_envelope(
            message_name=message_name,
            message_type=message_type,
            payload=payload,
            protocol=protocol,
            dispatch_context=(run or {}).get("dispatch_context") if isinstance(run, dict) else None,
            run_id=str((run or {}).get("id") or "").strip() or None,
            attempt=protocol.get("attempt"),
            emitted_at=emitted_at,
            available_at=emitted_at,
            dead_letter=dead_letter,
            dead_letter_reason=dead_letter_reason,
            last_error=error_message,
            source={"kind": "workflow_execution_worker", "id": self.worker_id},
            target={"kind": "workflow_dispatcher", "id": dispatcher_id or "unknown"},
        )
        if isinstance(run, dict):
            apply_protocol_to_run(run, resolved_protocol)
            self._persist_run(run)
        self._publish_to_subjects([subject, legacy_subject], envelope)

    def _publish_to_subjects(self, subjects: list[str | None], payload: dict) -> bool:
        if not getattr(self._persistence, "enabled", False):
            return False
        published = False
        seen: set[str] = set()
        for subject in subjects:
            normalized = str(subject or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            published = self._event_bus.publish_json(normalized, payload) or published
        return published


workflow_execution_worker_service = WorkflowExecutionWorkerService()
