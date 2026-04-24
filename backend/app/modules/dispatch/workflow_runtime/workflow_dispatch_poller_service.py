from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from threading import Event, Lock, Thread

from app.platform.contracts.agent_protocol import protocol_from_dispatch_context
from app.platform.persistence.persistence_service import persistence_service
from app.modules.dispatch.workflow_runtime.scheduler_guard_service import scheduler_guard_service
from app.platform.persistence.runtime_store import store
from app.modules.dispatch.workflow_runtime.workflow_dispatcher_service import (
    DEFAULT_DISPATCH_FAILURE_RETRY_DELAY_SECONDS,
    DEFAULT_DISPATCH_LEASE_SECONDS,
    workflow_dispatcher_service,
)
from app.modules.dispatch.workflow_runtime.workflow_execution_service import AUTO_STEP_DELAY_SECONDS
from app.modules.dispatch.workflow_runtime.workflow_scheduler_service import workflow_scheduler_service


logger = logging.getLogger(__name__)
DEFAULT_DISPATCH_POLL_INTERVAL_SECONDS = 1.0
DEFAULT_DUE_RUN_SCAN_LIMIT = 50
TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled"}


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


class WorkflowDispatchPollerService:
    def __init__(
        self,
        *,
        dispatcher=None,
        persistence=None,
        scheduler=None,
        poll_interval_seconds: float = DEFAULT_DISPATCH_POLL_INTERVAL_SECONDS,
        scan_limit: int = DEFAULT_DUE_RUN_SCAN_LIMIT,
    ) -> None:
        self._dispatcher = dispatcher or workflow_dispatcher_service
        self._persistence = persistence or persistence_service
        self._scheduler = scheduler or workflow_scheduler_service
        self._poll_interval_seconds = max(poll_interval_seconds, 0.1)
        self._scan_limit = max(scan_limit, 1)
        self._stop_event = Event()
        self._lock = Lock()
        self._thread: Thread | None = None

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = Thread(
                target=self._run_loop,
                daemon=True,
                name="workbot-workflow-dispatch-poller",
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            self._thread = None

        self._stop_event.set()
        if thread is not None:
            thread.join(timeout=self._poll_interval_seconds + 0.5)
        self._stop_event.clear()

    def poll_once(self, *, step_delay: float = AUTO_STEP_DELAY_SECONDS) -> dict[str, int]:
        summary = {
            "dispatched": 0,
            "skipped_claimed": 0,
            "skipped_scheduled": 0,
            "skipped_terminal": 0,
        }
        scheduler_guard_service.guard_dispatch_runtime(
            now=_utc_now(),
            persistence=self._persistence,
        )
        try:
            from app.modules.dispatch.workflow_runtime.workflow_service import poll_scheduled_workflows

            poll_scheduled_workflows(now=_utc_now())
        except Exception as exc:
            logger.warning("Workflow schedule poll failed: %s", exc)

        due_jobs = self._load_due_dispatch_jobs()
        if due_jobs is not None:
            claimed_job_run_ids = {
                str(job.get("run_id") or "").strip()
                for job in due_jobs
                if str(job.get("run_id") or "").strip()
            }
            self._poll_due_jobs(due_jobs, summary=summary, step_delay=step_delay)
            self._poll_due_runs(
                self._list_due_runs_for_job_repair(),
                summary=summary,
                step_delay=step_delay,
                skip_run_ids=claimed_job_run_ids,
                repair_dispatch_jobs=True,
            )
            return summary

        self._poll_due_runs(
            self._load_due_runs(),
            summary=summary,
            step_delay=step_delay,
        )

        return summary

    def _run_loop(self) -> None:
        while not self._stop_event.wait(timeout=self._poll_interval_seconds):
            try:
                self.poll_once()
            except Exception as exc:  # pragma: no cover - defensive runtime guard
                logger.warning("Workflow dispatch poller iteration failed: %s", exc)

    def _load_due_dispatch_jobs(self) -> list[dict] | None:
        deadline = _utc_now()
        dispatcher_id = str(getattr(self._dispatcher, "dispatcher_id", "") or "").strip()
        claim_due_jobs = getattr(self._persistence, "claim_due_workflow_dispatch_jobs", None)
        if not callable(claim_due_jobs) or not dispatcher_id:
            return None

        lease_seconds = float(
            getattr(self._dispatcher, "_lease_seconds", DEFAULT_DISPATCH_LEASE_SECONDS)
        )
        claimed_jobs = claim_due_jobs(
            dispatcher_id=dispatcher_id,
            claimed_at=deadline.isoformat(),
            lease_expires_at=(deadline + timedelta(seconds=max(lease_seconds, 0.0))).isoformat(),
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

    def _load_due_runs(self) -> list[dict]:
        deadline = _utc_now()
        persistence_enabled = bool(getattr(self._persistence, "enabled", False))
        dispatcher_id = str(getattr(self._dispatcher, "dispatcher_id", "") or "").strip()
        claim_due_runs = getattr(self._persistence, "claim_due_workflow_runs", None)
        if callable(claim_due_runs) and dispatcher_id:
            lease_seconds = float(
                getattr(self._dispatcher, "_lease_seconds", DEFAULT_DISPATCH_LEASE_SECONDS)
            )
            claimed_runs = claim_due_runs(
                dispatcher_id=dispatcher_id,
                claimed_at=deadline.isoformat(),
                lease_expires_at=(
                    deadline + timedelta(seconds=max(lease_seconds, 0.0))
                ).isoformat(),
                due_before=deadline.isoformat(),
                limit=self._scan_limit,
            )
            if claimed_runs is not None:
                return [
                    store.clone(run)
                    for run in sorted(
                        claimed_runs,
                        key=lambda run: (
                            _parse_datetime(run.get("next_dispatch_at")) or deadline,
                            str(run.get("id") or ""),
                        ),
                    )[: self._scan_limit]
                ]

        list_due_runs = getattr(self._persistence, "list_due_workflow_runs", None)
        if callable(list_due_runs):
            database_runs = list_due_runs(
                due_before=deadline.isoformat(),
                limit=self._scan_limit,
            )
            if database_runs is not None and (database_runs or persistence_enabled):
                candidates: dict[str, dict] = {}
                for run in database_runs:
                    run_id = str(run.get("id") or "").strip()
                    if not run_id:
                        continue
                    candidates[run_id] = self._sync_cached_run(run)
                ordered = sorted(
                    candidates.values(),
                    key=lambda run: (
                        _parse_datetime(run.get("next_dispatch_at")) or deadline,
                        str(run.get("id") or ""),
                    ),
                )
                return ordered[: self._scan_limit]
            if persistence_enabled:
                return []

        if persistence_enabled:
            return []

        candidates: dict[str, dict] = {}
        for run in list(store.workflow_runs):
            run_id = str(run.get("id") or "").strip()
            if not run_id or not self._is_due(run, deadline=deadline):
                continue
            candidates[run_id] = run

        ordered = sorted(
            candidates.values(),
            key=lambda run: (
                _parse_datetime(run.get("next_dispatch_at")) or deadline,
                str(run.get("id") or ""),
            ),
        )
        return ordered[: self._scan_limit]

    def _list_due_runs_for_job_repair(self) -> list[dict]:
        deadline = _utc_now()
        persistence_enabled = bool(getattr(self._persistence, "enabled", False))
        list_due_runs = getattr(self._persistence, "list_due_workflow_runs", None)
        if not callable(list_due_runs):
            return []

        database_runs = list_due_runs(
            due_before=deadline.isoformat(),
            limit=self._scan_limit,
        )
        if database_runs is None:
            return [] if persistence_enabled else []

        candidates: dict[str, dict] = {}
        for run in database_runs:
            run_id = str(run.get("id") or "").strip()
            if not run_id:
                continue
            candidates[run_id] = self._sync_cached_run(run)

        ordered = sorted(
            candidates.values(),
            key=lambda run: (
                _parse_datetime(run.get("next_dispatch_at")) or deadline,
                str(run.get("id") or ""),
            ),
        )
        return ordered[: self._scan_limit]

    def _poll_due_jobs(
        self,
        due_jobs: list[dict],
        *,
        summary: dict[str, int],
        step_delay: float,
    ) -> None:
        has_timer = getattr(self._scheduler, "has_timer", None)
        dispatcher_id = str(getattr(self._dispatcher, "dispatcher_id", "") or "").strip()

        for job in due_jobs:
            run_id = str(job.get("run_id") or "").strip()
            if not run_id:
                continue
            job_step_delay = self._step_delay_for_job(job, fallback=step_delay)

            if callable(has_timer) and has_timer(run_id):
                summary["skipped_scheduled"] += 1
                self._release_job_claim(job)
                continue

            run = self._find_run(run_id)
            if run is None:
                self._delete_job(job)
                continue

            if not self._job_matches_run_schedule(job, run):
                if not self._sync_job_with_run(job, run, step_delay=job_step_delay):
                    self._release_job_claim(job)
                continue

            if self._has_active_foreign_claim(run, dispatcher_id=dispatcher_id):
                summary["skipped_claimed"] += 1
                self._release_job_claim(job)
                continue

            claimed_by_self = self._is_actively_claimed_by_dispatcher(
                run,
                dispatcher_id=dispatcher_id,
            )
            claimed_run = run if claimed_by_self else self._dispatcher.try_acquire_schedule_slot(run_id)
            if claimed_run is None:
                summary["skipped_claimed"] += 1
                self._release_job_claim(job)
                continue

            if str(claimed_run.get("status") or "").strip().lower() in TERMINAL_RUN_STATUSES:
                self._scheduler.cancel(run_id)
                self._delete_job(job)
                summary["skipped_terminal"] += 1
                continue

            try:
                if self._dispatcher.dispatch_tick(run_id, step_delay=job_step_delay):
                    summary["dispatched"] += 1
                    continue

                self._dispatcher.process_tick(run_id, step_delay=job_step_delay)
                summary["dispatched"] += 1
                self._release_job_claim(job)
            except Exception as exc:
                logger.warning("Workflow dispatch poller failed for run %s: %s", run_id, exc)
                defer = getattr(self._scheduler, "defer", None)
                if callable(defer):
                    defer(
                        run_id,
                        delay=max(job_step_delay, DEFAULT_DISPATCH_FAILURE_RETRY_DELAY_SECONDS),
                        step_delay=job_step_delay,
                        dispatcher_id=getattr(self._dispatcher, "dispatcher_id", None),
                    )
                release_run_claim = getattr(self._dispatcher, "release_run_claim", None)
                if callable(release_run_claim):
                    release_run_claim(run_id)
                self._release_job_claim(job)

    def _poll_due_runs(
        self,
        due_runs: list[dict],
        *,
        summary: dict[str, int],
        step_delay: float,
        skip_run_ids: set[str] | None = None,
        repair_dispatch_jobs: bool = False,
    ) -> None:
        has_timer = getattr(self._scheduler, "has_timer", None)
        dispatcher_id = str(getattr(self._dispatcher, "dispatcher_id", "") or "").strip()
        blocked_run_ids = skip_run_ids or set()

        for candidate in due_runs:
            run_id = str(candidate.get("id") or "").strip()
            if not run_id or run_id in blocked_run_ids:
                continue

            if callable(has_timer) and has_timer(run_id):
                summary["skipped_scheduled"] += 1
                continue

            run = self._find_run(run_id)
            if run is None and candidate:
                run = self._sync_cached_run(candidate)
            if run is None:
                continue

            resolved_step_delay = step_delay
            if repair_dispatch_jobs:
                resolved_step_delay = self._repair_dispatch_job_for_due_run(
                    run,
                    step_delay=step_delay,
                )
                if resolved_step_delay is None:
                    continue

            if self._has_active_foreign_claim(run, dispatcher_id=dispatcher_id):
                summary["skipped_claimed"] += 1
                continue

            claimed_by_self = self._is_actively_claimed_by_dispatcher(
                run,
                dispatcher_id=dispatcher_id,
            )
            claimed_run = run if claimed_by_self else self._dispatcher.try_acquire_schedule_slot(run_id)
            if claimed_run is None:
                summary["skipped_claimed"] += 1
                continue

            if str(claimed_run.get("status") or "").strip().lower() in TERMINAL_RUN_STATUSES:
                self._scheduler.cancel(run_id)
                summary["skipped_terminal"] += 1
                continue

            try:
                if self._dispatcher.dispatch_tick(run_id, step_delay=resolved_step_delay):
                    summary["dispatched"] += 1
                    continue

                self._dispatcher.process_tick(run_id, step_delay=resolved_step_delay)
                summary["dispatched"] += 1
            except Exception as exc:
                logger.warning("Workflow dispatch poller failed for run %s: %s", run_id, exc)
                defer = getattr(self._scheduler, "defer", None)
                if callable(defer):
                    defer(
                        run_id,
                        delay=max(resolved_step_delay, DEFAULT_DISPATCH_FAILURE_RETRY_DELAY_SECONDS),
                        step_delay=resolved_step_delay,
                        dispatcher_id=getattr(self._dispatcher, "dispatcher_id", None),
                    )
                release_run_claim = getattr(self._dispatcher, "release_run_claim", None)
                if callable(release_run_claim):
                    release_run_claim(run_id)

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
        payload = store.clone(run_payload)
        for index, candidate in enumerate(store.workflow_runs):
            if str(candidate.get("id") or "").strip() != run_id:
                continue
            store.workflow_runs[index] = payload
            return payload

        store.workflow_runs.insert(0, payload)
        return payload

    def _sync_job_with_run(self, job: dict, run: dict, *, step_delay: float) -> bool:
        scheduled_at = str(run.get("next_dispatch_at") or "").strip()
        if not scheduled_at:
            self._delete_job(job)
            return True

        upsert_job = getattr(self._persistence, "upsert_workflow_dispatch_job", None)
        if not callable(upsert_job):
            return False

        return (
            upsert_job(
                str(job.get("run_id") or ""),
                available_at=scheduled_at,
                step_delay_seconds=step_delay,
                dispatcher_id=run.get("dispatcher_id"),
                claimed_at=run.get("dispatch_claimed_at"),
                lease_expires_at=run.get("dispatch_lease_expires_at"),
                **{
                    key: value
                    for key, value in protocol_from_dispatch_context(run).items()
                    if key not in {"available_at", "emitted_at"}
                },
            )
            is not None
        )

    def _delete_job(self, job: dict) -> None:
        delete_job = getattr(self._persistence, "delete_workflow_dispatch_job", None)
        if not callable(delete_job):
            return

        run_id = str(job.get("run_id") or "").strip()
        dispatcher_id = str(getattr(self._dispatcher, "dispatcher_id", "") or "").strip()
        if not run_id:
            return

        delete_job(
            run_id,
            dispatcher_id=dispatcher_id or None,
            claimed_at=job.get("claimed_at"),
        )

    def _release_job_claim(self, job: dict) -> None:
        release_job_claim = getattr(self._persistence, "release_workflow_dispatch_job_claim", None)
        if not callable(release_job_claim):
            return

        run_id = str(job.get("run_id") or "").strip()
        dispatcher_id = str(getattr(self._dispatcher, "dispatcher_id", "") or "").strip()
        if not run_id or not dispatcher_id:
            return

        release_job_claim(
            run_id,
            dispatcher_id=dispatcher_id,
            claimed_at=job.get("claimed_at"),
        )

    def _repair_dispatch_job_for_due_run(
        self,
        run: dict,
        *,
        step_delay: float,
    ) -> float | None:
        get_job = getattr(self._persistence, "get_workflow_dispatch_job", None)
        if not callable(get_job):
            return step_delay

        run_id = str(run.get("id") or "").strip()
        scheduled_at = str(run.get("next_dispatch_at") or "").strip()
        if not run_id or not scheduled_at:
            return step_delay

        persisted_job = get_job(run_id)
        dispatcher_id = str(getattr(self._dispatcher, "dispatcher_id", "") or "").strip()
        if persisted_job is not None:
            if self._job_matches_run_schedule(persisted_job, run):
                return None
            if self._has_active_foreign_job_claim(
                persisted_job,
                dispatcher_id=dispatcher_id,
            ):
                return None

        upsert_job = getattr(self._persistence, "upsert_workflow_dispatch_job", None)
        resolved_step_delay = (
            self._step_delay_for_job(persisted_job, fallback=step_delay)
            if persisted_job is not None
            else step_delay
        )
        if not callable(upsert_job):
            return resolved_step_delay

        upsert_job(
            run_id,
            available_at=scheduled_at,
            step_delay_seconds=resolved_step_delay,
            **{
                key: value
                for key, value in protocol_from_dispatch_context(run).items()
                if key not in {"available_at", "emitted_at"}
            },
        )
        return resolved_step_delay

    @staticmethod
    def _step_delay_for_job(job: dict, *, fallback: float) -> float:
        raw_value = job.get("step_delay_seconds")
        if raw_value is None:
            return fallback
        try:
            return max(float(raw_value), 0.0)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _job_matches_run_schedule(job: dict, run: dict) -> bool:
        available_at = str(job.get("available_at") or "").strip()
        scheduled_at = str(run.get("next_dispatch_at") or "").strip()
        return bool(available_at and scheduled_at and available_at == scheduled_at)

    @staticmethod
    def _is_due(run: dict, *, deadline: datetime) -> bool:
        scheduled_at = _parse_datetime(run.get("next_dispatch_at"))
        return scheduled_at is not None and scheduled_at <= deadline

    @staticmethod
    def _has_active_claim(run: dict) -> bool:
        lease_expires_at = _parse_datetime(run.get("dispatch_lease_expires_at"))
        return lease_expires_at is not None and lease_expires_at > _utc_now()

    @classmethod
    def _has_active_foreign_claim(cls, run: dict, *, dispatcher_id: str) -> bool:
        owner = str(run.get("dispatcher_id") or "").strip()
        return bool(owner and owner != dispatcher_id and cls._has_active_claim(run))

    @classmethod
    def _is_actively_claimed_by_dispatcher(cls, run: dict, *, dispatcher_id: str) -> bool:
        owner = str(run.get("dispatcher_id") or "").strip()
        return bool(dispatcher_id and owner == dispatcher_id and cls._has_active_claim(run))

    @classmethod
    def _has_active_foreign_job_claim(cls, job: dict, *, dispatcher_id: str) -> bool:
        owner = str(job.get("dispatcher_id") or "").strip()
        lease_expires_at = _parse_datetime(
            job.get("lease_expires_at") or job.get("dispatch_lease_expires_at")
        )
        return bool(owner and owner != dispatcher_id and lease_expires_at and lease_expires_at > _utc_now())


workflow_dispatch_poller_service = WorkflowDispatchPollerService()


def reset_workflow_dispatch_poller_state() -> None:
    workflow_dispatch_poller_service.stop()
