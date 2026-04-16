from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Lock, Timer

from app.services.persistence_service import persistence_service
from app.services.store import store


TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled"}
SCHEDULED_CLAIM_LEASE_BUFFER_SECONDS = 1.0


def _utc_now() -> datetime:
    return datetime.now(UTC)


class WorkflowSchedulerService:
    def __init__(self, *, persistence=None) -> None:
        self._persistence = persistence or persistence_service
        self._timers: dict[str, Timer] = {}
        self._lock = Lock()

    def schedule(self, run_id: str, *, delay: float, step_delay: float) -> None:
        from app.services.workflow_dispatcher_service import workflow_dispatcher_service

        claimed_run = workflow_dispatcher_service.try_acquire_schedule_slot(run_id)
        if claimed_run is None:
            self._cancel_timer(run_id)
            workflow_dispatcher_service.release_run_claim(run_id)
            return

        if str(claimed_run.get("status") or "") in TERMINAL_RUN_STATUSES:
            self.cancel(run_id)
            return

        scheduled_at = _utc_now() + timedelta(seconds=max(delay, 0.0))
        claimed_run["next_dispatch_at"] = scheduled_at.isoformat()
        scheduled_lease_expires_at = scheduled_at + timedelta(
            seconds=SCHEDULED_CLAIM_LEASE_BUFFER_SECONDS
        )
        claimed_run["dispatch_lease_expires_at"] = scheduled_lease_expires_at.isoformat()
        self._persist_run(claimed_run)
        queued = self._upsert_dispatch_job(
            run_id,
            available_at=scheduled_at.isoformat(),
            step_delay=step_delay,
            run=claimed_run,
            claim_with_run=True,
        )

        # Keep a local timer even when the durable dispatch job is persisted.
        # In single-process fallback mode this timer guarantees progress if the
        # poller thread is not available; in normal multi-instance mode the
        # timer exits harmlessly when another claimant has already consumed the job.
        timer = Timer(delay, self._advance_run, args=(run_id, step_delay))
        timer.daemon = True

        with self._lock:
            existing = self._timers.pop(run_id, None)
            if existing is not None:
                existing.cancel()
            self._timers[run_id] = timer

        timer.start()

    def cancel(self, run_id: str) -> None:
        from app.services.workflow_dispatcher_service import workflow_dispatcher_service

        self._cancel_timer(run_id)
        run = self._find_run(run_id)
        cleared = self._clear_next_dispatch_at(
            run_id,
            dispatcher_id=workflow_dispatcher_service.dispatcher_id,
        )
        if cleared or str((run or {}).get("status") or "").strip().lower() in TERMINAL_RUN_STATUSES:
            self._delete_dispatch_job(run_id)
        workflow_dispatcher_service.release_run_claim(run_id)

    def defer(
        self,
        run_id: str,
        *,
        delay: float,
        step_delay: float | None = None,
        dispatcher_id: str | None = None,
    ) -> dict | None:
        self._cancel_timer(run_id)
        run = self._find_run(run_id)
        if run is None:
            return None

        status = str(run.get("status") or "").strip().lower()
        if status in TERMINAL_RUN_STATUSES:
            return run

        owner = str(run.get("dispatcher_id") or "").strip()
        if dispatcher_id and owner and owner != dispatcher_id:
            return run

        run["next_dispatch_at"] = (
            _utc_now() + timedelta(seconds=max(delay, 0.0))
        ).isoformat()
        self._persist_run(run)
        self._upsert_dispatch_job(
            run_id,
            available_at=run["next_dispatch_at"],
            step_delay=step_delay,
            run=run,
            claim_with_run=False,
        )
        return run

    def reset(self) -> None:
        with self._lock:
            timer_items = list(self._timers.items())
            self._timers.clear()

        for _, timer in timer_items:
            timer.cancel()

        from app.services.workflow_dispatcher_service import workflow_dispatcher_service

        cleared_runs: list[dict] = []
        for run_id, _ in timer_items:
            cleared_run = self._clear_next_dispatch_at(
                run_id,
                dispatcher_id=workflow_dispatcher_service.dispatcher_id,
                persist=False,
            )
            if cleared_run is not None:
                self._delete_dispatch_job(run_id)
                cleared_runs.append(cleared_run)
        if cleared_runs:
            self._persist_runs(cleared_runs)

        for run_id, _ in timer_items:
            workflow_dispatcher_service.release_run_claim(run_id)

    def _advance_run(self, run_id: str, step_delay: float) -> None:
        with self._lock:
            self._timers.pop(run_id, None)

        from app.services.workflow_dispatcher_service import workflow_dispatcher_service

        if not self._claim_due_dispatch_job(run_id):
            return

        claimed_run = workflow_dispatcher_service.try_acquire_schedule_slot(run_id)
        if claimed_run is None:
            return

        if str(claimed_run.get("status") or "") in TERMINAL_RUN_STATUSES:
            self.cancel(run_id)
            return

        event_bus = getattr(workflow_dispatcher_service, "_event_bus", None)
        event_bus_connected = bool(getattr(event_bus, "is_connected", lambda: False)())
        if event_bus_connected and workflow_dispatcher_service.dispatch_tick(run_id, step_delay=step_delay):
            return

        workflow_dispatcher_service.process_tick(run_id, step_delay=step_delay)

    def _cancel_timer(self, run_id: str) -> None:
        with self._lock:
            timer = self._timers.pop(run_id, None)
        if timer is not None:
            timer.cancel()

    def has_timer(self, run_id: str) -> bool:
        with self._lock:
            return run_id in self._timers

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

    def _persist_runs(self, runs: list[dict]) -> None:
        if not runs:
            return

        persist_execution_state = getattr(self._persistence, "persist_execution_state", None)
        if callable(persist_execution_state):
            all_persisted = True
            for run in runs:
                if not persist_execution_state(workflow_run=run):
                    all_persisted = False
            if all_persisted:
                return
            if getattr(self._persistence, "enabled", False):
                return

        self._persistence.persist_runtime_state()

    def _upsert_dispatch_job(
        self,
        run_id: str,
        *,
        available_at: str,
        step_delay: float | None = None,
        run: dict | None = None,
        claim_with_run: bool,
    ) -> bool:
        upsert_job = getattr(self._persistence, "upsert_workflow_dispatch_job", None)
        if not getattr(self._persistence, "enabled", False) or not callable(upsert_job):
            return False

        normalized_step_delay = (
            max(float(step_delay), 0.0) if step_delay is not None else None
        )
        return (
            upsert_job(
                run_id,
                available_at=available_at,
                step_delay_seconds=normalized_step_delay,
                dispatcher_id=run.get("dispatcher_id") if claim_with_run and run else None,
                claimed_at=(
                    run.get("dispatch_claimed_at") if claim_with_run and run else None
                ),
                lease_expires_at=(
                    run.get("dispatch_lease_expires_at") if claim_with_run and run else None
                ),
            )
            is not None
        )

    def _delete_dispatch_job(self, run_id: str) -> bool:
        delete_job = getattr(self._persistence, "delete_workflow_dispatch_job", None)
        if not getattr(self._persistence, "enabled", False) or not callable(delete_job):
            return False

        return bool(delete_job(run_id))

    def _claim_due_dispatch_job(self, run_id: str) -> bool:
        claim_job = getattr(self._persistence, "claim_workflow_dispatch_job", None)
        if not getattr(self._persistence, "enabled", False) or not callable(claim_job):
            return True

        from app.services.workflow_dispatcher_service import (
            DEFAULT_DISPATCH_LEASE_SECONDS,
            workflow_dispatcher_service,
        )

        dispatcher_id = str(getattr(workflow_dispatcher_service, "dispatcher_id", "") or "").strip()
        if not dispatcher_id:
            return True

        lease_seconds = float(
            getattr(workflow_dispatcher_service, "_lease_seconds", DEFAULT_DISPATCH_LEASE_SECONDS)
        )
        now = _utc_now()
        claimed_job = claim_job(
            run_id,
            dispatcher_id=dispatcher_id,
            claimed_at=now.isoformat(),
            lease_expires_at=(now + timedelta(seconds=max(lease_seconds, 0.0))).isoformat(),
            due_before=now.isoformat(),
            respect_existing_owner=True,
        )
        return claimed_job is not None

    def _clear_next_dispatch_at(
        self,
        run_id: str,
        *,
        dispatcher_id: str,
        persist: bool = True,
    ) -> dict | None:
        run = self._find_run(run_id)
        if run is None or run.get("next_dispatch_at") is None:
            return None

        owner = str(run.get("dispatcher_id") or "").strip()
        status = str(run.get("status") or "").strip().lower()
        if owner and owner != dispatcher_id and status not in TERMINAL_RUN_STATUSES:
            return None

        run["next_dispatch_at"] = None
        if persist:
            self._persist_run(run)
        return run

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


workflow_scheduler_service = WorkflowSchedulerService()


def reset_workflow_scheduler_state() -> None:
    workflow_scheduler_service.reset()
