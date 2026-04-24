from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from threading import Lock

from app.platform.persistence.persistence_service import persistence_service
from app.platform.persistence.runtime_store import store
from app.modules.dispatch.workflow_runtime.workflow_execution_service import (
    AUTO_STEP_DELAY_SECONDS,
    get_workflow_run,
)
from app.modules.dispatch.workflow_runtime.workflow_dispatcher_service import (
    DEFAULT_DISPATCH_FAILURE_RETRY_DELAY_SECONDS,
    DEFAULT_DISPATCH_LEASE_SECONDS,
    workflow_dispatcher_service,
)
from app.modules.dispatch.workflow_runtime.workflow_scheduler_service import workflow_scheduler_service


logger = logging.getLogger(__name__)

RECOVERABLE_TASK_STATUSES = {"pending", "running"}
RECOVERABLE_RUN_STATUSES = {"pending", "running"}
DEFAULT_RECOVERY_DELAY_SECONDS = 0.2
DEFAULT_DUE_RUN_BATCH_LIMIT = 50
RECOVERY_WARNING = "Workflow scheduler recovered this run after service restart"
ORPHANED_RUN_WARNING = "Workflow recovery skipped because the linked task was not found"


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


class WorkflowRecoveryService:
    def __init__(self, *, scheduler=None, persistence=None, dispatcher=None) -> None:
        self._scheduler = scheduler or workflow_scheduler_service
        self._persistence = persistence or persistence_service
        self._dispatcher = dispatcher or workflow_dispatcher_service
        self._lock = Lock()
        self._recovered_run_ids: set[str] = set()

    def bootstrap(
        self,
        *,
        delay: float = DEFAULT_RECOVERY_DELAY_SECONDS,
        step_delay: float = AUTO_STEP_DELAY_SECONDS,
    ) -> dict[str, int]:
        summary = {
            "recovered": 0,
            "skipped_claimed": 0,
            "skipped_terminal": 0,
            "skipped_orphaned": 0,
        }
        runs_to_persist: list[dict] = []
        dispatcher_id = str(getattr(self._dispatcher, "dispatcher_id", "") or "").strip()

        for candidate in self._load_candidate_runs():
            run_id = str(candidate.get("id") or "").strip()
            if not run_id:
                continue

            with self._lock:
                if run_id in self._recovered_run_ids:
                    continue

            run = self._find_run(run_id)
            if run is None:
                continue

            task = self._find_task(str(run.get("task_id") or ""))
            if task is None:
                self._scheduler.cancel(run_id)
                if self._append_warning(run, ORPHANED_RUN_WARNING):
                    runs_to_persist.append(run)
                summary["skipped_orphaned"] += 1
                continue

            if str(task.get("status") or "") not in RECOVERABLE_TASK_STATUSES:
                self._scheduler.cancel(run_id)
                summary["skipped_terminal"] += 1
                continue

            if self._has_active_foreign_claim(run, dispatcher_id=dispatcher_id):
                summary["skipped_claimed"] += 1
                continue
            if not self._is_actively_claimed_by_dispatcher(run, dispatcher_id=dispatcher_id):
                if self._dispatcher.try_acquire_schedule_slot(run_id) is None:
                    summary["skipped_claimed"] += 1
                    continue

            get_workflow_run(run_id)
            run = self._find_run(run_id)
            if run is None:
                continue

            if self._append_warning(run, RECOVERY_WARNING):
                runs_to_persist.append(run)
            resolved_delay = self._resolve_recovery_delay(run, fallback_delay=delay)
            if resolved_delay <= 0:
                self._dispatch_due_run(run_id, step_delay=step_delay)
            else:
                self._scheduler.schedule(run_id, delay=resolved_delay, step_delay=step_delay)

            with self._lock:
                self._recovered_run_ids.add(run_id)
            summary["recovered"] += 1

        self._persist_runs(runs_to_persist)

        if summary["recovered"] or summary["skipped_orphaned"]:
            logger.info("Workflow recovery summary: %s", summary)
        return summary

    def recover_due_runs(
        self,
        *,
        step_delay: float = AUTO_STEP_DELAY_SECONDS,
        limit: int = DEFAULT_DUE_RUN_BATCH_LIMIT,
    ) -> dict[str, int]:
        summary = {
            "recovered": 0,
            "skipped_claimed": 0,
            "skipped_terminal": 0,
            "skipped_orphaned": 0,
            "skipped_scheduled": 0,
        }
        runs_to_persist: list[dict] = []
        dispatcher_id = str(getattr(self._dispatcher, "dispatcher_id", "") or "").strip()

        has_timer = getattr(self._scheduler, "has_timer", None)
        for candidate in self._load_due_candidate_runs(limit=limit):
            run_id = str(candidate.get("id") or "").strip()
            if not run_id:
                continue

            if callable(has_timer) and has_timer(run_id):
                summary["skipped_scheduled"] += 1
                continue

            run = self._find_run(run_id)
            if run is None:
                continue

            task = self._find_task(str(run.get("task_id") or ""))
            if task is None:
                self._scheduler.cancel(run_id)
                if self._append_warning(run, ORPHANED_RUN_WARNING):
                    runs_to_persist.append(run)
                summary["skipped_orphaned"] += 1
                continue

            if str(task.get("status") or "") not in RECOVERABLE_TASK_STATUSES:
                self._scheduler.cancel(run_id)
                summary["skipped_terminal"] += 1
                continue

            if self._has_active_foreign_claim(run, dispatcher_id=dispatcher_id):
                summary["skipped_claimed"] += 1
                continue
            if not self._is_actively_claimed_by_dispatcher(run, dispatcher_id=dispatcher_id):
                if self._dispatcher.try_acquire_schedule_slot(run_id) is None:
                    summary["skipped_claimed"] += 1
                    continue

            get_workflow_run(run_id)
            run = self._find_run(run_id)
            if run is None:
                continue

            self._dispatch_due_run(run_id, step_delay=step_delay)
            summary["recovered"] += 1

        self._persist_runs(runs_to_persist)

        if summary["recovered"] or summary["skipped_orphaned"]:
            logger.info("Workflow due-run recovery summary: %s", summary)
        return summary

    def reset(self) -> None:
        with self._lock:
            self._recovered_run_ids.clear()

    def _persist_runs(self, runs: list[dict]) -> None:
        if not runs:
            return

        deduped_runs: dict[str, dict] = {}
        for run in runs:
            run_id = str(run.get("id") or "").strip()
            if not run_id:
                continue
            deduped_runs[run_id] = run

        if not deduped_runs:
            return

        persist_execution_state = getattr(self._persistence, "persist_execution_state", None)
        if callable(persist_execution_state):
            all_persisted = True
            for run in deduped_runs.values():
                if not persist_execution_state(workflow_run=run):
                    all_persisted = False
            if all_persisted:
                return
            if getattr(self._persistence, "enabled", False):
                return

        self._persistence.persist_runtime_state()

    def _load_due_candidate_runs(self, *, limit: int) -> list[dict]:
        now = _utc_now()
        candidates: dict[str, dict] = {}
        persistence_enabled = bool(getattr(self._persistence, "enabled", False))

        dispatcher_id = str(getattr(self._dispatcher, "dispatcher_id", "") or "").strip()
        claim_due_runs = getattr(self._persistence, "claim_due_workflow_runs", None)
        if callable(claim_due_runs) and dispatcher_id:
            lease_seconds = float(
                getattr(self._dispatcher, "_lease_seconds", DEFAULT_DISPATCH_LEASE_SECONDS)
            )
            claimed_database_runs = claim_due_runs(
                dispatcher_id=dispatcher_id,
                claimed_at=now.isoformat(),
                lease_expires_at=(
                    now + timedelta(seconds=max(lease_seconds, 0.0))
                ).isoformat(),
                before=now.isoformat(),
                limit=limit,
            )
            if claimed_database_runs is not None:
                for run in claimed_database_runs:
                    run_id = str(run.get("id") or "").strip()
                    if not run_id:
                        continue
                    candidates[run_id] = self._sync_cached_run(run)
                return list(candidates.values())

        list_due_runs = getattr(self._persistence, "list_due_workflow_runs", None)
        if callable(list_due_runs):
            database_runs = list_due_runs(before=now.isoformat(), limit=limit)
            if database_runs is not None:
                for run in database_runs:
                    run_id = str(run.get("id") or "").strip()
                    if not run_id:
                        continue
                    candidates[run_id] = self._sync_cached_run(run)
                return list(candidates.values())
            if persistence_enabled:
                return []

        if persistence_enabled:
            return []

        for run in self._load_candidate_runs():
            run_id = str(run.get("id") or "").strip()
            if not run_id or run_id in candidates:
                continue
            if str(run.get("status") or "") not in RECOVERABLE_RUN_STATUSES:
                continue
            scheduled_at = _parse_datetime(run.get("next_dispatch_at"))
            if scheduled_at is None or scheduled_at > now:
                continue
            candidates[run_id] = run
            if len(candidates) >= limit:
                break
        return list(candidates.values())

    def _load_candidate_runs(self) -> list[dict]:
        candidates: dict[str, dict] = {}
        persistence_enabled = bool(getattr(self._persistence, "enabled", False))

        list_runs = getattr(self._persistence, "list_workflow_runs", None)
        if callable(list_runs):
            database_runs = list_runs()
            if database_runs is not None and (database_runs or persistence_enabled):
                for run in database_runs:
                    run_id = str(run.get("id") or "").strip()
                    if not run_id:
                        continue
                    candidates[run_id] = self._sync_cached_run(run)
                return list(candidates.values())
            if persistence_enabled:
                return []

        if persistence_enabled:
            return []

        for run in list(store.workflow_runs):
            run_id = str(run.get("id") or "").strip()
            if run_id and run_id not in candidates:
                candidates[run_id] = run
        return list(candidates.values())

    @staticmethod
    def _find_cached_run(run_id: str) -> dict | None:
        for run in store.workflow_runs:
            if str(run.get("id")) == run_id:
                return run
        return None

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

    def _load_database_task(self, task_id: str) -> tuple[dict | None, bool]:
        get_task = getattr(self._persistence, "get_task", None)
        if callable(get_task):
            database_task = get_task(task_id)
            if database_task is not None:
                return database_task, True

        if not getattr(self._persistence, "enabled", False):
            return None, False

        list_tasks = getattr(self._persistence, "list_tasks", None)
        if not callable(list_tasks):
            return None, True

        database_tasks = list_tasks()
        if database_tasks is None:
            return None, True

        for candidate in database_tasks:
            if str(candidate.get("id") or "").strip() == task_id:
                return candidate, True
        return None, True

    def _find_task(self, task_id: str) -> dict | None:
        database_task, database_authoritative = self._load_database_task(task_id)
        if database_authoritative:
            if database_task is None:
                return None
            return self._sync_cached_task(database_task)

        return self._find_cached_task(task_id)

    @staticmethod
    def _find_cached_task(task_id: str) -> dict | None:
        for task in store.tasks:
            if str(task.get("id")) == task_id:
                return task
        return None

    def _sync_cached_task(self, task_payload: dict) -> dict:
        task_id = str(task_payload.get("id") or "").strip()
        cached_task = self._find_cached_task(task_id)
        payload = store.clone(task_payload)
        if cached_task is None:
            store.tasks.append(payload)
            return payload

        cached_task.clear()
        cached_task.update(payload)
        return cached_task

    @staticmethod
    def _resolve_recovery_delay(run: dict, *, fallback_delay: float) -> float:
        scheduled_at = _parse_datetime(run.get("next_dispatch_at"))
        if scheduled_at is None:
            return fallback_delay

        remaining_seconds = (scheduled_at - _utc_now()).total_seconds()
        return max(remaining_seconds, 0.0)

    def _dispatch_due_run(self, run_id: str, *, step_delay: float) -> None:
        try:
            dispatch_tick = getattr(self._dispatcher, "dispatch_tick", None)
            if callable(dispatch_tick) and dispatch_tick(run_id, step_delay=step_delay):
                return

            process_tick = getattr(self._dispatcher, "process_tick", None)
            if callable(process_tick):
                process_tick(run_id, step_delay=step_delay)
                return

            self._scheduler.schedule(run_id, delay=0.0, step_delay=step_delay)
        except Exception as exc:
            logger.warning("Workflow recovery dispatch failed for run %s: %s", run_id, exc)
            defer = getattr(self._scheduler, "defer", None)
            if callable(defer):
                defer(
                    run_id,
                    delay=max(step_delay, DEFAULT_DISPATCH_FAILURE_RETRY_DELAY_SECONDS),
                    step_delay=step_delay,
                    dispatcher_id=getattr(self._dispatcher, "dispatcher_id", None),
                )
            release_run_claim = getattr(self._dispatcher, "release_run_claim", None)
            if callable(release_run_claim):
                release_run_claim(run_id)

    @staticmethod
    def _append_warning(run: dict, warning: str) -> bool:
        warnings = run.setdefault("warnings", [])
        if not isinstance(warnings, list):
            warnings = []
            run["warnings"] = warnings
        if warning in warnings:
            return False
        warnings.append(warning)
        return True

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


workflow_recovery_service = WorkflowRecoveryService()


def reset_workflow_recovery_state() -> None:
    workflow_recovery_service.reset()
