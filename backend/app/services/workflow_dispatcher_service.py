from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from uuid import uuid4

from app.core.brain_payload_fields import alias_text, dispatch_context_from_run, route_decision_from_payload
from app.core.agent_protocol import (
    apply_protocol_to_run,
    build_protocol_envelope,
    protocol_from_dispatch_context,
)
from app.core.nats_event_bus import nats_event_bus
from app.services.persistence_service import persistence_service
from app.services.store import store


logger = logging.getLogger(__name__)
TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled"}
WORKFLOW_DISPATCH_SUBJECT = "workflow.dispatch.tick"
WORKFLOW_DISPATCH_QUEUE = "workflow_dispatchers"
WORKFLOW_EXECUTION_SUBJECT = "workflow.execution.run"
WORKFLOW_EXECUTION_QUEUE = "workflow_execution_workers"
DEFAULT_DISPATCH_LEASE_SECONDS = 30.0
DEFAULT_DISPATCH_FAILURE_RETRY_DELAY_SECONDS = 2.0
MAX_DISPATCH_FAILURE_RETRY_DELAY_SECONDS = 30.0
DISPATCH_FAILURE_WARNING_TEMPLATE = "调度推进失败，已延后 {delay:.1f}s 重试：{error}"
MAX_DISPATCH_FAILURE_COUNT = 6
DISPATCH_FAILURE_TERMINAL_WARNING_TEMPLATE = "调度推进连续失败，已达到最大重试次数并标记为失败：{error}"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _time_only(value: str) -> str:
    if "T" in value:
        return value.split("T", maxsplit=1)[1][:8]
    if " " in value:
        return value.rsplit(" ", maxsplit=1)[-1][:8]
    return value[:8]


def _dispatch_context_state(run: dict | None) -> str:
    if not isinstance(run, dict):
        return ""
    dispatch_context = run.get("dispatch_context")
    if not isinstance(dispatch_context, dict):
        return ""
    return str(
        dispatch_context.get("state")
        or dispatch_context.get("dispatch_state")
        or dispatch_context.get("dispatchState")
        or ""
    ).strip().lower()


class WorkflowDispatcherService:
    def __init__(
        self,
        *,
        event_bus=None,
        persistence=None,
        dispatcher_id: str | None = None,
        lease_seconds: float = DEFAULT_DISPATCH_LEASE_SECONDS,
    ) -> None:
        self._event_bus = event_bus or nats_event_bus
        self._persistence = persistence or persistence_service
        self.dispatcher_id = dispatcher_id or f"dispatcher-{uuid4().hex[:12]}"
        self._lease_seconds = lease_seconds
        self._event_bus.subscribe(
            WORKFLOW_DISPATCH_SUBJECT,
            self._handle_dispatch_message,
            queue_group=WORKFLOW_DISPATCH_QUEUE,
        )

    def dispatch_tick(self, run_id: str, *, step_delay: float) -> bool:
        if not getattr(self._persistence, "enabled", False):
            return False
        if not bool(getattr(self._event_bus, "is_connected", lambda: False)()):
            return False
        return self._event_bus.publish_json(
            WORKFLOW_DISPATCH_SUBJECT,
            {
                "run_id": run_id,
                "step_delay": step_delay,
            },
        )

    def dispatch_execution(
        self,
        run_id: str,
        *,
        step_delay: float,
        published_at: str | None = None,
    ) -> bool:
        run = self._find_run(run_id)
        if run is None:
            return False

        queued_at = published_at or _utc_now().isoformat()

        dispatch_context = dispatch_context_from_run(run) or {}
        route_decision = route_decision_from_payload(dispatch_context) or {}

        execution_agent_id = (
            alias_text(dispatch_context, "execution_agent_id", "executionAgentId")
            or alias_text(route_decision, "execution_agent_id", "executionAgentId")
            or ""
        ).strip()
        dispatch_state = str(
            dispatch_context.get("state")
            or dispatch_context.get("dispatch_state")
            or dispatch_context.get("dispatchState")
            or ""
        ).strip()

        payload = {
            "run_id": str(run.get("id") or run_id),
            "task_id": str(run.get("task_id") or ""),
            "workflow_id": str(run.get("workflow_id") or ""),
            "step_delay": step_delay,
            "dispatch_context": {
                "state": dispatch_state or None,
                "execution_agent_id": execution_agent_id or None,
            },
            "dispatcher_id": self.dispatcher_id,
            "published_at": queued_at,
        }
        envelope, protocol = build_protocol_envelope(
            message_name="workflow.execution.request",
            message_type="command",
            payload=payload,
            dispatch_context=dispatch_context,
            run_id=str(run.get("id") or run_id),
            default_max_attempts=self._dispatch_protocol_max_attempts(run),
            attempt=self._execution_attempt_for_run(run),
            emitted_at=queued_at,
            available_at=queued_at,
            source={"kind": "workflow_dispatcher", "id": self.dispatcher_id},
            target={"kind": "workflow_execution_worker", "id": WORKFLOW_EXECUTION_QUEUE},
        )
        apply_protocol_to_run(run, protocol)
        self._persist_run(run)
        self._enqueue_execution_job(run_id, step_delay=step_delay, queued_at=queued_at, protocol=protocol)
        if not getattr(self._persistence, "enabled", False):
            return False
        if not bool(getattr(self._event_bus, "is_connected", lambda: False)()):
            return False
        return self._event_bus.publish_json(WORKFLOW_EXECUTION_SUBJECT, envelope)

    def try_acquire_schedule_slot(self, run_id: str) -> dict | None:
        return self._claim_run(run_id, respect_existing_owner=True)

    def process_tick(self, run_id: str, *, step_delay: float) -> dict | None:
        run = self._claim_run(run_id, respect_existing_owner=False)
        if run is None:
            return self._find_run(run_id)
        if str(run.get("status") or "") in TERMINAL_RUN_STATUSES:
            self.release_run_claim(run_id)
            return run

        from app.services.workflow_scheduler_service import workflow_scheduler_service

        try:
            from app.services.workflow_execution_service import (
                dispatch_workflow_run,
                execute_workflow_run,
            )

            run = dispatch_workflow_run(run_id)
            if run is not None:
                run = self._clear_dispatch_failure(run) or run
            if run is None:
                return None
            if _dispatch_context_state(run) in {"agent_queued", "executing"}:
                self.release_run_claim(run_id)
                return self._find_run(run_id)
            if run.get("status") in TERMINAL_RUN_STATUSES:
                self.release_run_claim(run_id)
                workflow_scheduler_service.cancel(run_id)
                return run
            published_at = _utc_now().isoformat()
            execution_publish_succeeded = self.dispatch_execution(
                run_id,
                step_delay=step_delay,
                published_at=published_at,
            )
            eager_fallback_attempted = False
            if not execution_publish_succeeded:
                eager_fallback_attempted = True
                try:
                    from app.services.workflow_execution_service import (
                        complete_agent_execution_job,
                        execute_workflow_run,
                    )

                    eager_run = execute_workflow_run(run_id)
                    eager_execution_agent_id = None
                    eager_dispatch_context = (
                        eager_run.get("dispatch_context")
                        if isinstance(eager_run, dict)
                        else None
                    )
                    if isinstance(eager_dispatch_context, dict):
                        eager_execution_agent_id = (
                            str(
                                eager_dispatch_context.get("execution_agent_id")
                                or eager_dispatch_context.get("executionAgentId")
                                or ""
                            ).strip()
                            or None
                        )
                    if (
                        isinstance(eager_run, dict)
                        and str(eager_run.get("status") or "").strip() not in TERMINAL_RUN_STATUSES
                    ):
                        complete_agent_execution_job(
                            run_id,
                            execution_agent_id=eager_execution_agent_id,
                        )
                except Exception as exc:
                    logger.warning(
                        "Workflow execution eager fallback failed for run %s: %s",
                        run_id,
                        exc,
                    )
            execution_job_durable = self._has_execution_job(run_id)
            if execution_publish_succeeded or execution_job_durable:
                self._claim_run(run_id, respect_existing_owner=False)
                workflow_scheduler_service.schedule(run_id, delay=step_delay, step_delay=step_delay)
                return self._find_run(run_id)
            if eager_fallback_attempted:
                fallback_run = self._find_run(run_id)
                if fallback_run is not None:
                    if str(fallback_run.get("status") or "").strip() in TERMINAL_RUN_STATUSES:
                        workflow_scheduler_service.cancel(run_id)
                    else:
                        self._claim_run(run_id, respect_existing_owner=False)
                        workflow_scheduler_service.schedule(
                            run_id,
                            delay=step_delay,
                            step_delay=step_delay,
                        )
                    return fallback_run
            run = execute_workflow_run(run_id)
        except Exception as exc:
            logger.warning("Workflow dispatch tick failed for run %s: %s", run_id, exc)
            now = _utc_now()
            run = self._mark_dispatch_failure(run_id, exc, now=now)
            retry_delay = self._retry_delay_for_failure(run, step_delay=step_delay)

            if run is not None:
                run["updated_at"] = now.isoformat()
                if self._should_fail_after_dispatch_error(run):
                    warning_message = DISPATCH_FAILURE_TERMINAL_WARNING_TEMPLATE.format(
                        error=str(exc),
                    )
                else:
                    warning_message = DISPATCH_FAILURE_WARNING_TEMPLATE.format(
                        delay=retry_delay,
                        error=str(exc),
                    )
                self._append_warning(run, warning_message)
                self._append_log(run, now=now, message=warning_message)

                if self._should_fail_after_dispatch_error(run):
                    from app.services.workflow_execution_service import (
                        fail_workflow_run_due_dispatch_failure,
                    )

                    return fail_workflow_run_due_dispatch_failure(
                        run_id,
                        failure_message=warning_message,
                    )

            workflow_scheduler_service.defer(
                run_id,
                delay=retry_delay,
                step_delay=step_delay,
                dispatcher_id=self.dispatcher_id,
            )
            self.release_run_claim(run_id)
            return self._find_run(run_id)

        if run.get("status") in TERMINAL_RUN_STATUSES:
            self.release_run_claim(run_id)
            workflow_scheduler_service.cancel(run_id)
        else:
            self._claim_run(run_id, respect_existing_owner=False)
            workflow_scheduler_service.schedule(run_id, delay=step_delay, step_delay=step_delay)
        return run

    def release_run_claim(self, run_id: str) -> dict | None:
        run = self._find_run(run_id)
        if run is None:
            return None

        release_claim = getattr(self._persistence, "release_workflow_run_claim", None)
        if getattr(self._persistence, "enabled", False) and callable(release_claim):
            released_run = release_claim(run_id, dispatcher_id=self.dispatcher_id)
            if released_run is None:
                return None
            return self._sync_cached_run(released_run)

        owner = str(run.get("dispatcher_id") or "").strip()
        if owner and owner != self.dispatcher_id and str(run.get("status") or "") not in TERMINAL_RUN_STATUSES:
            return run

        if not any(
            run.get(field)
            for field in ("dispatcher_id", "dispatch_claimed_at", "dispatch_lease_expires_at")
        ):
            return run

        run["dispatcher_id"] = None
        run["dispatch_claimed_at"] = None
        run["dispatch_lease_expires_at"] = None
        self._persist_run(run)
        return run

    def _handle_dispatch_message(self, _: str, payload: dict) -> None:
        run_id = str(payload.get("run_id") or payload.get("runId") or "").strip()
        if not run_id:
            return

        step_delay = float(payload.get("step_delay") or payload.get("stepDelay") or 0.0)
        self.process_tick(run_id, step_delay=step_delay)

    def _enqueue_execution_job(
        self,
        run_id: str,
        *,
        step_delay: float,
        queued_at: str,
        protocol: dict | None = None,
    ) -> dict | None:
        upsert_job = getattr(self._persistence, "upsert_workflow_execution_job", None)
        if not getattr(self._persistence, "enabled", False) or not callable(upsert_job):
            return None

        return upsert_job(
            run_id,
            available_at=queued_at,
            queued_at=queued_at,
            step_delay_seconds=step_delay,
            **{
                key: value
                for key, value in (protocol or {}).items()
                if key not in {"available_at", "emitted_at"}
            },
        )

    def _has_execution_job(self, run_id: str) -> bool:
        get_job = getattr(self._persistence, "get_workflow_execution_job", None)
        if not getattr(self._persistence, "enabled", False) or not callable(get_job):
            return False
        return get_job(run_id) is not None

    def _claim_run(self, run_id: str, *, respect_existing_owner: bool) -> dict | None:
        run = self._find_run(run_id)
        if run is None or str(run.get("status") or "") in TERMINAL_RUN_STATUSES:
            return run

        claim_run = getattr(self._persistence, "claim_workflow_run", None)
        if getattr(self._persistence, "enabled", False) and callable(claim_run):
            now = _utc_now()
            claimed_run = claim_run(
                run_id,
                dispatcher_id=self.dispatcher_id,
                claimed_at=now.isoformat(),
                lease_expires_at=(now + timedelta(seconds=self._lease_seconds)).isoformat(),
                respect_existing_owner=respect_existing_owner,
            )
            if claimed_run is None:
                return None
            return self._sync_cached_run(claimed_run)

        if respect_existing_owner and self._has_active_foreign_claim(run):
            return None

        now = _utc_now()
        run["dispatcher_id"] = self.dispatcher_id
        run["dispatch_claimed_at"] = now.isoformat()
        run["dispatch_lease_expires_at"] = (
            now + timedelta(seconds=self._lease_seconds)
        ).isoformat()
        self._persist_run(run)
        return run

    def _has_active_foreign_claim(self, run: dict) -> bool:
        owner = str(run.get("dispatcher_id") or "").strip()
        if not owner or owner == self.dispatcher_id:
            return False

        lease_expires_at = _parse_datetime(run.get("dispatch_lease_expires_at"))
        return lease_expires_at is not None and lease_expires_at > _utc_now()

    def _load_database_run(self, run_id: str) -> tuple[dict | None, bool]:
        get_run = getattr(self._persistence, "get_workflow_run", None)
        if callable(get_run):
            database_run = get_run(run_id)
            if database_run is not None:
                return database_run, True

        if not getattr(self._persistence, "enabled", False):
            return None, False

        list_runs = getattr(self._persistence, "list_workflow_runs", None)
        if not callable(list_runs):
            return None, True

        database_runs = list_runs()
        if database_runs is None:
            return None, True

        for candidate in database_runs:
            if str(candidate.get("id") or "").strip() == run_id:
                return candidate, True
        return None, True

    def _find_run(self, run_id: str) -> dict | None:
        database_run, database_authoritative = self._load_database_run(run_id)
        if database_authoritative:
            if database_run is None:
                return None
            return self._sync_cached_run(database_run)

        return self._find_cached_run(run_id)

    @staticmethod
    def _find_cached_run(run_id: str) -> dict | None:
        for run in store.workflow_runs:
            if str(run.get("id")) == run_id:
                return run
        return None

    def _sync_cached_run(self, run_payload: dict) -> dict:
        run_id = str(run_payload.get("id") or "").strip()
        cached_run = self._find_cached_run(run_id)
        payload = store.clone(run_payload)
        if cached_run is None:
            store.workflow_runs.insert(0, payload)
            return payload

        cached_run.clear()
        cached_run.update(payload)
        return cached_run

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

    def _mark_dispatch_failure(self, run_id: str, exc: Exception, *, now: datetime) -> dict | None:
        run = self._find_run(run_id)
        if run is None:
            return None

        run["updated_at"] = now.isoformat()
        run["dispatch_failure_count"] = max(int(run.get("dispatch_failure_count", 0)), 0) + 1
        run["last_dispatch_error"] = str(exc)
        protocol = protocol_from_dispatch_context(run)
        if protocol or str(run.get("id") or "").strip():
            protocol["attempt"] = run["dispatch_failure_count"] + 1
            protocol["max_attempts"] = self._dispatch_protocol_max_attempts(run)
            protocol["last_error"] = str(exc)
            protocol["dead_letter"] = self._should_fail_after_dispatch_error(run)
            protocol["dead_letter_reason"] = str(exc) if protocol["dead_letter"] else None
            apply_protocol_to_run(run, protocol)
        self._persist_run(run)
        return run

    def _clear_dispatch_failure(self, run: dict | None) -> dict | None:
        if run is None:
            return None

        persisted_run = self._find_run(str(run.get("id") or ""))
        if persisted_run is None:
            return run

        updated = False
        if int(persisted_run.get("dispatch_failure_count", 0)) != 0:
            persisted_run["dispatch_failure_count"] = 0
            updated = True
        if persisted_run.get("last_dispatch_error") is not None:
            persisted_run["last_dispatch_error"] = None
            updated = True
        protocol = protocol_from_dispatch_context(persisted_run)
        if protocol.get("dead_letter") or protocol.get("last_error"):
            protocol["dead_letter"] = False
            protocol["dead_letter_reason"] = None
            protocol["last_error"] = None
            apply_protocol_to_run(persisted_run, protocol)
            updated = True
        if updated:
            self._persist_run(persisted_run)
        run["dispatch_failure_count"] = persisted_run.get("dispatch_failure_count", 0)
        run["last_dispatch_error"] = persisted_run.get("last_dispatch_error")
        return run

    @staticmethod
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

    @classmethod
    def _retry_delay_for_failure(cls, run: dict | None, *, step_delay: float) -> float:
        policy = cls._run_workflow_policy(run)
        policy_backoff = policy.get("dispatch_retry_backoff_seconds") or policy.get(
            "dispatchRetryBackoffSeconds"
        )
        try:
            normalized_backoff = float(policy_backoff)
        except (TypeError, ValueError):
            normalized_backoff = DEFAULT_DISPATCH_FAILURE_RETRY_DELAY_SECONDS
        base_delay = max(
            step_delay,
            normalized_backoff if normalized_backoff > 0 else DEFAULT_DISPATCH_FAILURE_RETRY_DELAY_SECONDS,
            DEFAULT_DISPATCH_FAILURE_RETRY_DELAY_SECONDS,
        )
        failure_count = max(int((run or {}).get("dispatch_failure_count", 0)), 1)
        return min(base_delay * (2 ** (failure_count - 1)), MAX_DISPATCH_FAILURE_RETRY_DELAY_SECONDS)

    @classmethod
    def _should_fail_after_dispatch_error(cls, run: dict | None) -> bool:
        if run is None:
            return False
        policy = cls._run_workflow_policy(run)
        max_retry = policy.get("max_dispatch_retry") or policy.get("maxDispatchRetry")
        try:
            normalized_max_retry = int(max_retry)
        except (TypeError, ValueError):
            normalized_max_retry = MAX_DISPATCH_FAILURE_COUNT
        if normalized_max_retry <= 0:
            normalized_max_retry = MAX_DISPATCH_FAILURE_COUNT
        return int(run.get("dispatch_failure_count", 0)) >= normalized_max_retry

    @staticmethod
    def _append_warning(run: dict, warning: str) -> None:
        warnings = run.setdefault("warnings", [])
        if not isinstance(warnings, list):
            warnings = []
            run["warnings"] = warnings
        if warning not in warnings:
            warnings.append(warning)

    @staticmethod
    def _append_log(run: dict, *, now: datetime, message: str) -> None:
        logs = run.setdefault("logs", [])
        if not isinstance(logs, list):
            logs = []
            run["logs"] = logs
        logs.append(
            {
                "id": f"log-dispatch-{uuid4().hex[:10]}",
                "timestamp": _time_only(now.isoformat()),
                "occurred_at": now.isoformat(),
                "type": "warning",
                "agent": "Workflow Dispatcher",
                "source": "dispatcher",
                "message": message,
            }
        )

    @staticmethod
    def _execution_attempt_for_run(run: dict | None) -> int:
        if not isinstance(run, dict):
            return 1
        dispatch_context = dispatch_context_from_run(run) or {}
        protocol = protocol_from_dispatch_context(dispatch_context)
        try:
            protocol_attempt = int(protocol.get("attempt") or 1)
        except (TypeError, ValueError):
            protocol_attempt = 1
        try:
            dispatch_attempt = max(int(run.get("dispatch_failure_count") or 0), 0) + 1
        except (TypeError, ValueError):
            dispatch_attempt = 1
        return max(protocol_attempt, dispatch_attempt, 1)

    @classmethod
    def _dispatch_protocol_max_attempts(cls, run: dict | None) -> int:
        policy = cls._run_workflow_policy(run)
        max_retry = policy.get("max_dispatch_retry") or policy.get("maxDispatchRetry")
        try:
            normalized = int(max_retry)
        except (TypeError, ValueError):
            normalized = MAX_DISPATCH_FAILURE_COUNT
        return max(normalized, 1)


workflow_dispatcher_service = WorkflowDispatcherService()
