from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import logging
from typing import Any

from sqlalchemy import delete, func, inspect, select, update
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.db.base import Base
from app.db.models import (
    AgentExecutionJobRecord,
    AgentRecord,
    AuditLogRecord,
    ConversationMessageRecord,
    InternalEventDeliveryRecord,
    MemorySessionStateRecord,
    OperationalLogRecord,
    SecuritySubjectStateRecord,
    SecurityRuleRecord,
    SystemSettingRecord,
    TaskRecord,
    TaskStepRecord,
    WorkflowDispatchJobRecord,
    WorkflowExecutionJobRecord,
    UserProfileRecord,
    UserRecord,
    WorkflowRecord,
    WorkflowRunRecord,
)
from app.modules.agent_config.registries.agent_config_service import build_agent_config_summary
from app.db.session import create_engine_for_url, create_session_factory
from app.platform.security.encryption_service import encryption_service
from app.platform.persistence.runtime_store import LEGACY_AGENT_IDS, LEGACY_WORKFLOW_IDS, store


logger = logging.getLogger(__name__)
TERMINAL_WORKFLOW_RUN_STATUSES = {"completed", "failed", "cancelled"}
JOB_PROTOCOL_KEYS = (
    "spec_version",
    "message_id",
    "message_type",
    "message_name",
    "request_id",
    "correlation_id",
    "causation_id",
    "idempotency_key",
    "attempt",
    "max_attempts",
    "emitted_at",
    "available_at",
    "deadline_at",
    "dead_letter",
    "dead_letter_reason",
    "source",
    "target",
    "last_error",
)

RUNTIME_SCHEMA_COMPAT_COLUMNS: dict[str, dict[str, str]] = {
    "workflow_dispatch_jobs": {
        "protocol": "JSON",
    },
    "workflow_execution_jobs": {
        "protocol": "JSON",
    },
    "agent_execution_jobs": {
        "protocol": "JSON",
    },
}


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


def _normalize_identifier_list(values: list[str] | tuple[str, ...] | set[str] | None) -> list[str]:
    if not values:
        return []
    items: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        items.append(normalized)
    return items


def _is_legacy_agent_id(agent_id: str | None) -> bool:
    normalized = str(agent_id or "").strip()
    return bool(normalized) and normalized in LEGACY_AGENT_IDS


def _is_legacy_workflow_id(workflow_id: str | None) -> bool:
    normalized = str(workflow_id or "").strip()
    return bool(normalized) and normalized in LEGACY_WORKFLOW_IDS


def _extract_job_protocol_snapshot(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    nested_protocol = payload.get("protocol")
    nested = nested_protocol if isinstance(nested_protocol, dict) else {}
    snapshot: dict[str, Any] = {}
    for key in JOB_PROTOCOL_KEYS:
        if key in payload and payload.get(key) is not None:
            snapshot[key] = deepcopy(payload[key])
            continue
        if key in nested and nested.get(key) is not None:
            snapshot[key] = deepcopy(nested[key])
    return snapshot or None


def _flatten_job_protocol_snapshot(protocol: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(protocol, dict):
        return {}
    return {key: deepcopy(value) for key, value in protocol.items()}


class StatePersistenceService:
    def __init__(self, *, runtime_store: Any = None, database_url: str | None = None) -> None:
        self.runtime_store = runtime_store or store
        self.database_url = database_url or get_settings().database_url
        self._engine = None
        self._session_factory = None
        self.enabled = False

    def initialize(self) -> bool:
        try:
            self._engine = create_engine_for_url(self.database_url)
            self._session_factory = create_session_factory(self._engine)
            Base.metadata.create_all(self._engine)
            self._ensure_runtime_schema_compatibility()
            self.enabled = True
            self._bootstrap_runtime_state()
            return True
        except Exception as exc:  # pragma: no cover - exercised via failure path behavior
            logger.warning("Database persistence disabled: %s", exc)
            self.close()
            return False

    def close(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
        self._engine = None
        self._session_factory = None
        self.enabled = False

    def _ensure_runtime_schema_compatibility(self) -> None:
        if self._engine is None:
            return

        inspector = inspect(self._engine)
        existing_tables = set(inspector.get_table_names())
        pending_repairs: list[tuple[str, str, str]] = []
        for table_name, column_map in RUNTIME_SCHEMA_COMPAT_COLUMNS.items():
            if table_name not in existing_tables:
                continue
            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, ddl in column_map.items():
                if column_name in existing_columns:
                    continue
                pending_repairs.append((table_name, column_name, ddl))

        if not pending_repairs:
            return

        with self._engine.begin() as connection:
            for table_name, column_name, ddl in pending_repairs:
                connection.exec_driver_sql(
                    f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"
                )
                logger.info(
                    "Applied runtime schema compatibility patch: added %s.%s",
                    table_name,
                    column_name,
                )

    def persist_all(self) -> bool:
        return self._persist(
            include_agents=True,
            include_tasks=True,
            include_workflows=True,
            include_users=True,
            include_security=True,
            include_system_settings=True,
        )

    def persist_runtime_state(self) -> bool:
        return self._persist(
            include_agents=True,
            include_tasks=True,
            include_workflows=True,
            include_users=False,
            include_security=False,
            include_system_settings=False,
        )

    def persist_execution_state(
        self,
        *,
        task: dict[str, Any] | None = None,
        task_steps: list[dict[str, Any]] | None = None,
        workflow_run: dict[str, Any] | None = None,
    ) -> bool:
        if not self.enabled or self._session_factory is None:
            return False
        if task_steps is not None and task is None:
            logger.warning("Task steps cannot be persisted without a task payload")
            return False

        try:
            with self._session_factory() as session:
                if task is not None:
                    self._upsert_task(session, task)
                if task is not None and task_steps is not None:
                    self._replace_task_steps_for_task(session, str(task["id"]), task_steps)
                if workflow_run is not None:
                    self._upsert_workflow_run(session, workflow_run)
                session.commit()
            return True
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Invalid execution state payload ignored: %s", exc)
            return False
        except SQLAlchemyError as exc:
            logger.warning("Failed to persist execution state: %s", exc)
            return False

    def persist_agent_state(self, *, agent: dict[str, Any]) -> bool:
        if not self.enabled or self._session_factory is None:
            return False
        if _is_legacy_agent_id(agent.get("id")):
            return self.delete_agent_state(agent_id=str(agent.get("id") or ""))

        try:
            with self._session_factory() as session:
                self._upsert_agent(session, agent)
                session.commit()
            return True
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Invalid agent state payload ignored: %s", exc)
            return False
        except SQLAlchemyError as exc:
            logger.warning("Failed to persist agent state: %s", exc)
            return False

    def persist_workflow_state(self, *, workflow: dict[str, Any]) -> bool:
        if not self.enabled or self._session_factory is None:
            return False
        if _is_legacy_workflow_id(workflow.get("id")):
            return self.delete_workflow_state(workflow_id=str(workflow.get("id") or ""))

        try:
            with self._session_factory() as session:
                self._upsert_workflow(session, workflow)
                session.commit()
            return True
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Invalid workflow state payload ignored: %s", exc)
            return False
        except SQLAlchemyError as exc:
            logger.warning("Failed to persist workflow state: %s", exc)
            return False

    def delete_agent_state(self, *, agent_id: str) -> bool:
        if not self.enabled or self._session_factory is None:
            return False
        normalized_ids = _normalize_identifier_list([agent_id])
        if not normalized_ids:
            return False
        return self.delete_agent_states(agent_ids=normalized_ids) >= 0

    def delete_agent_states(self, *, agent_ids: list[str]) -> int:
        if not self.enabled or self._session_factory is None:
            return 0

        normalized_ids = _normalize_identifier_list(agent_ids)
        if not normalized_ids:
            return 0

        try:
            with self._session_factory() as session:
                deleted_count = self._delete_agents_by_ids(session, normalized_ids)
                session.commit()
            return deleted_count
        except SQLAlchemyError as exc:
            logger.warning("Failed to delete agent states: %s", exc)
            return 0

    def delete_workflow_state(self, *, workflow_id: str) -> bool:
        if not self.enabled or self._session_factory is None:
            return False
        normalized_ids = _normalize_identifier_list([workflow_id])
        if not normalized_ids:
            return False
        return self.delete_workflow_states(workflow_ids=normalized_ids) >= 0

    def delete_workflow_states(self, *, workflow_ids: list[str]) -> int:
        if not self.enabled or self._session_factory is None:
            return 0

        normalized_ids = _normalize_identifier_list(workflow_ids)
        if not normalized_ids:
            return 0

        try:
            with self._session_factory() as session:
                deleted_count = self._delete_workflows_by_ids(session, normalized_ids)
                session.commit()
            return deleted_count
        except SQLAlchemyError as exc:
            logger.warning("Failed to delete workflow states: %s", exc)
            return 0

    def persist_user_state(
        self,
        *,
        user: dict[str, Any] | None = None,
        profile: dict[str, Any] | None = None,
    ) -> bool:
        if user is None and profile is None:
            return self._persist(
                include_agents=False,
                include_tasks=False,
                include_workflows=False,
                include_users=True,
                include_security=False,
                include_system_settings=False,
            )

        if not self.enabled or self._session_factory is None:
            return False

        try:
            with self._session_factory() as session:
                if user is not None:
                    self._upsert_user(session, user)
                if profile is not None:
                    self._upsert_user_profile(session, profile)
                session.commit()
            return True
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Invalid user state payload ignored: %s", exc)
            return False
        except SQLAlchemyError as exc:
            logger.warning("Failed to persist user state: %s", exc)
            return False

    def append_audit_log(self, *, log: dict[str, Any]) -> bool:
        if not self.enabled or self._session_factory is None:
            return False

        try:
            with self._session_factory() as session:
                self._append_audit_log(session, log)
                session.commit()
            return True
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Invalid audit log payload ignored: %s", exc)
            return False
        except SQLAlchemyError as exc:
            logger.warning("Failed to append audit log: %s", exc)
            return False

    def persist_security_rule_state(self, *, rule: dict[str, Any]) -> bool:
        if not self.enabled or self._session_factory is None:
            return False

        try:
            with self._session_factory() as session:
                self._upsert_security_rule(session, rule)
                session.commit()
            return True
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Invalid security rule payload ignored: %s", exc)
            return False
        except SQLAlchemyError as exc:
            logger.warning("Failed to persist security rule state: %s", exc)
            return False

    def persist_security_state(self) -> bool:
        return self._persist(
            include_agents=False,
            include_tasks=False,
            include_workflows=False,
            include_users=False,
            include_security=True,
            include_system_settings=False,
        )

    def reset_database(self) -> None:
        if not self.enabled or self._session_factory is None:
            return
        with self._session_factory() as session:
            self._clear_all_tables(session)
            session.commit()

    def get_system_setting(self, key: str) -> dict[str, Any] | None:
        if not self.enabled or self._session_factory is None:
            return None

        normalized_key = str(key or "").strip()
        if not normalized_key:
            return None

        try:
            with self._session_factory() as session:
                row = session.get(SystemSettingRecord, normalized_key)
                if row is None:
                    return None
                return self._system_setting_record_to_payload(row)
        except SQLAlchemyError as exc:
            logger.warning("Failed to load system setting %s from database: %s", normalized_key, exc)
            return None

    def read_system_setting(self, key: str) -> tuple[dict[str, Any] | None, bool]:
        if not self.enabled or self._session_factory is None:
            return None, False

        normalized_key = str(key or "").strip()
        if not normalized_key:
            return None, False

        try:
            with self._session_factory() as session:
                row = session.get(SystemSettingRecord, normalized_key)
                if row is None:
                    return None, True
                return self._system_setting_record_to_payload(row), True
        except SQLAlchemyError as exc:
            logger.warning("Failed to load system setting %s from database: %s", normalized_key, exc)
            return None, False

    def persist_system_setting(
        self,
        *,
        key: str,
        payload: dict[str, Any],
        updated_at: str | None = None,
    ) -> bool:
        if not self.enabled or self._session_factory is None:
            return False

        try:
            with self._session_factory() as session:
                self._upsert_system_setting(
                    session,
                    key=key,
                    payload=payload,
                    updated_at=updated_at or datetime.now(UTC).isoformat(),
                )
                session.commit()
            return True
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Invalid system setting payload ignored: %s", exc)
            return False
        except SQLAlchemyError as exc:
            logger.warning("Failed to persist system setting: %s", exc)
            return False

    def list_agents(self) -> list[dict[str, Any]] | None:
        if not self.enabled or self._session_factory is None:
            return None

        try:
            with self._session_factory() as session:
                return [
                    self._agent_record_to_payload(row)
                    for row in session.scalars(select(AgentRecord).order_by(AgentRecord.sort_index)).all()
                    if not _is_legacy_agent_id(row.id)
                ]
        except SQLAlchemyError as exc:
            logger.warning("Failed to load agents from database: %s", exc)
            return None

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        if not self.enabled or self._session_factory is None:
            return None
        if _is_legacy_agent_id(agent_id):
            return None

        try:
            with self._session_factory() as session:
                row = session.get(AgentRecord, agent_id)
                if row is None:
                    return None
                return self._agent_record_to_payload(row)
        except SQLAlchemyError as exc:
            logger.warning("Failed to load agent %s from database: %s", agent_id, exc)
            return None

    def list_tasks(
        self,
        *,
        status_filter: str | None = None,
        search: str | None = None,
        priority_filter: str | None = None,
        agent_filter: str | None = None,
        channel_filter: str | None = None,
    ) -> list[dict[str, Any]] | None:
        if not self.enabled or self._session_factory is None:
            return None

        try:
            with self._session_factory() as session:
                items = [
                    self._task_record_to_payload(row)
                    for row in session.scalars(select(TaskRecord).order_by(TaskRecord.sort_index)).all()
                ]
        except SQLAlchemyError as exc:
            logger.warning("Failed to load tasks from database: %s", exc)
            return None

        if status_filter:
            items = [task for task in items if task["status"] == status_filter]
        if search:
            keyword = search.lower()
            items = [
                task
                for task in items
                if keyword in task["title"].lower() or keyword in task["description"].lower()
                or keyword in str(task.get("agent") or "").lower()
                or keyword in str(task.get("channel") or "").lower()
            ]
        if priority_filter:
            normalized_priority = priority_filter.strip().lower()
            items = [
                task
                for task in items
                if str(task.get("priority") or "").strip().lower() == normalized_priority
            ]
        if agent_filter:
            normalized_agent = agent_filter.strip().lower()
            items = [
                task
                for task in items
                if str(task.get("agent") or "").strip().lower() == normalized_agent
            ]
        if channel_filter:
            normalized_channel = channel_filter.strip().lower()
            items = [
                task
                for task in items
                if str(task.get("channel") or "").strip().lower() == normalized_channel
            ]
        return items

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        if not self.enabled or self._session_factory is None:
            return None

        try:
            with self._session_factory() as session:
                row = session.get(TaskRecord, task_id)
                if row is None:
                    return None
                return self._task_record_to_payload(row)
        except SQLAlchemyError as exc:
            logger.warning("Failed to load task %s from database: %s", task_id, exc)
            return None

    def get_task_steps(self, task_id: str) -> list[dict[str, Any]] | None:
        if not self.enabled or self._session_factory is None:
            return None

        try:
            with self._session_factory() as session:
                return [
                    self._task_step_record_to_payload(row)
                    for row in session.scalars(
                        select(TaskStepRecord)
                        .where(TaskStepRecord.task_id == task_id)
                        .order_by(TaskStepRecord.sort_index)
                    ).all()
                ]
        except SQLAlchemyError as exc:
            logger.warning("Failed to load task steps for %s from database: %s", task_id, exc)
            return None

    def get_security_subject_state(self, user_key: str) -> dict[str, Any] | None:
        if not self.enabled or self._session_factory is None:
            return None

        normalized_user_key = str(user_key or "").strip()
        if not normalized_user_key:
            return None

        try:
            with self._session_factory() as session:
                row = session.get(SecuritySubjectStateRecord, normalized_user_key)
                if row is None:
                    return None
                return self._security_subject_state_record_to_payload(row)
        except SQLAlchemyError as exc:
            logger.warning(
                "Failed to load security subject state for %s from database: %s",
                normalized_user_key,
                exc,
            )
            return None

    def list_security_subject_states(self) -> list[dict[str, Any]] | None:
        if not self.enabled or self._session_factory is None:
            return None

        try:
            with self._session_factory() as session:
                return [
                    self._security_subject_state_record_to_payload(row)
                    for row in session.scalars(
                        select(SecuritySubjectStateRecord).order_by(
                            SecuritySubjectStateRecord.updated_at.desc(),
                            SecuritySubjectStateRecord.user_key,
                        )
                    ).all()
                ]
        except SQLAlchemyError as exc:
            logger.warning("Failed to load security subject states from database: %s", exc)
            return None

    def read_security_subject_state(
        self,
        user_key: str,
    ) -> tuple[dict[str, Any] | None, bool]:
        if not self.enabled or self._session_factory is None:
            return None, False

        normalized_user_key = str(user_key or "").strip()
        if not normalized_user_key:
            return None, False

        try:
            with self._session_factory() as session:
                row = session.get(SecuritySubjectStateRecord, normalized_user_key)
                if row is None:
                    return None, True
                return self._security_subject_state_record_to_payload(row), True
        except SQLAlchemyError as exc:
            logger.warning(
                "Failed to load security subject state for %s from database: %s",
                normalized_user_key,
                exc,
            )
            return None, False

    def upsert_security_subject_state(self, state: dict[str, Any]) -> bool:
        if not self.enabled or self._session_factory is None:
            return False

        try:
            with self._session_factory() as session:
                self._upsert_security_subject_state(session, state)
                session.commit()
            return True
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Invalid security subject state payload ignored: %s", exc)
            return False
        except SQLAlchemyError as exc:
            logger.warning("Failed to persist security subject state: %s", exc)
            return False

    def find_latest_active_task_for_user(self, user_key: str) -> dict[str, Any] | None:
        if not self.enabled or self._session_factory is None:
            return None

        normalized_user_key = str(user_key or "").strip()
        if not normalized_user_key:
            return None

        try:
            with self._session_factory() as session:
                rows = session.scalars(
                    select(TaskRecord)
                    .where(TaskRecord.user_key == normalized_user_key)
                    .where(TaskRecord.status.in_(("pending", "running")))
                    .order_by(TaskRecord.sort_index)
                ).all()
                latest_task: dict[str, Any] | None = None
                latest_activity_at: datetime | None = None

                for row in rows:
                    task_payload = self._task_record_to_payload(row)
                    step_rows = session.scalars(
                        select(TaskStepRecord)
                        .where(TaskStepRecord.task_id == row.id)
                        .order_by(TaskStepRecord.sort_index)
                    ).all()
                    candidate_activity_at = self._task_latest_activity_at(task_payload, step_rows)
                    if latest_activity_at is None or (
                        candidate_activity_at is not None and candidate_activity_at > latest_activity_at
                    ):
                        latest_activity_at = candidate_activity_at
                        latest_task = task_payload

                return latest_task
        except SQLAlchemyError as exc:
            logger.warning(
                "Failed to resolve latest active task for user %s from database: %s",
                normalized_user_key,
                exc,
            )
            return None

    def list_workflows(self) -> list[dict[str, Any]] | None:
        if not self.enabled or self._session_factory is None:
            return None

        try:
            with self._session_factory() as session:
                return [
                    self._workflow_record_to_payload(row)
                    for row in session.scalars(select(WorkflowRecord).order_by(WorkflowRecord.sort_index)).all()
                    if not _is_legacy_workflow_id(row.id)
                ]
        except SQLAlchemyError as exc:
            logger.warning("Failed to load workflows from database: %s", exc)
            return None

    def get_workflow(self, workflow_id: str) -> dict[str, Any] | None:
        if not self.enabled or self._session_factory is None:
            return None
        if _is_legacy_workflow_id(workflow_id):
            return None

        try:
            with self._session_factory() as session:
                row = session.get(WorkflowRecord, workflow_id)
                if row is None:
                    return None
                return self._workflow_record_to_payload(row)
        except SQLAlchemyError as exc:
            logger.warning("Failed to load workflow %s from database: %s", workflow_id, exc)
            return None

    def list_workflow_runs(
        self,
        *,
        workflow_id: str | None = None,
        task_id: str | None = None,
    ) -> list[dict[str, Any]] | None:
        if not self.enabled or self._session_factory is None:
            return None

        try:
            with self._session_factory() as session:
                statement = select(WorkflowRunRecord).order_by(WorkflowRunRecord.sort_index)
                if workflow_id:
                    statement = statement.where(WorkflowRunRecord.workflow_id == workflow_id)
                if task_id:
                    statement = statement.where(WorkflowRunRecord.task_id == task_id)
                return [
                    self._workflow_run_record_to_payload(row)
                    for row in session.scalars(statement).all()
                ]
        except SQLAlchemyError as exc:
            logger.warning("Failed to load workflow runs from database: %s", exc)
            return None

    def get_workflow_run(self, run_id: str) -> dict[str, Any] | None:
        if not self.enabled or self._session_factory is None:
            return None

        try:
            with self._session_factory() as session:
                row = session.get(WorkflowRunRecord, run_id)
                if row is None:
                    return None
                return self._workflow_run_record_to_payload(row)
        except SQLAlchemyError as exc:
            logger.warning("Failed to load workflow run %s from database: %s", run_id, exc)
            return None

    def get_workflow_dispatch_job(self, run_id: str) -> dict[str, Any] | None:
        if not self.enabled or self._session_factory is None:
            return None

        try:
            with self._session_factory() as session:
                row = session.get(WorkflowDispatchJobRecord, run_id)
                if row is None:
                    return None
                return self._workflow_dispatch_job_record_to_payload(row)
        except SQLAlchemyError as exc:
            logger.warning(
                "Failed to load workflow dispatch job %s from database: %s",
                run_id,
                exc,
            )
            return None

    def list_workflow_dispatch_jobs(self) -> list[dict[str, Any]] | None:
        if not self.enabled or self._session_factory is None:
            return None

        try:
            with self._session_factory() as session:
                rows = session.scalars(
                    select(WorkflowDispatchJobRecord).order_by(
                        WorkflowDispatchJobRecord.available_at,
                        WorkflowDispatchJobRecord.run_id,
                    )
                ).all()
                return [self._workflow_dispatch_job_record_to_payload(row) for row in rows]
        except SQLAlchemyError as exc:
            logger.warning("Failed to load workflow dispatch jobs from database: %s", exc)
            return None

    def get_workflow_execution_job(self, run_id: str) -> dict[str, Any] | None:
        if not self.enabled or self._session_factory is None:
            return None

        try:
            with self._session_factory() as session:
                row = session.get(WorkflowExecutionJobRecord, run_id)
                if row is None:
                    return None
                return self._workflow_execution_job_record_to_payload(row)
        except SQLAlchemyError as exc:
            logger.warning(
                "Failed to load workflow execution job %s from database: %s",
                run_id,
                exc,
            )
            return None

    def list_workflow_execution_jobs(self) -> list[dict[str, Any]] | None:
        if not self.enabled or self._session_factory is None:
            return None

        try:
            with self._session_factory() as session:
                rows = session.scalars(
                    select(WorkflowExecutionJobRecord).order_by(
                        WorkflowExecutionJobRecord.available_at,
                        WorkflowExecutionJobRecord.run_id,
                    )
                ).all()
                return [self._workflow_execution_job_record_to_payload(row) for row in rows]
        except SQLAlchemyError as exc:
            logger.warning("Failed to load workflow execution jobs from database: %s", exc)
            return None

    def get_agent_execution_job(self, run_id: str) -> dict[str, Any] | None:
        if not self.enabled or self._session_factory is None:
            return None

        try:
            with self._session_factory() as session:
                row = session.get(AgentExecutionJobRecord, run_id)
                if row is None:
                    return None
                return self._agent_execution_job_record_to_payload(row)
        except SQLAlchemyError as exc:
            logger.warning(
                "Failed to load agent execution job %s from database: %s",
                run_id,
                exc,
            )
            return None

    def list_agent_execution_jobs(self) -> list[dict[str, Any]] | None:
        if not self.enabled or self._session_factory is None:
            return None

        try:
            with self._session_factory() as session:
                rows = session.scalars(
                    select(AgentExecutionJobRecord).order_by(
                        AgentExecutionJobRecord.available_at,
                        AgentExecutionJobRecord.run_id,
                    )
                ).all()
                return [self._agent_execution_job_record_to_payload(row) for row in rows]
        except SQLAlchemyError as exc:
            logger.warning("Failed to load agent execution jobs from database: %s", exc)
            return None

    def get_internal_event_delivery(self, delivery_id: str) -> dict[str, Any] | None:
        if not self.enabled or self._session_factory is None:
            return None

        normalized_delivery_id = delivery_id.strip()
        if not normalized_delivery_id:
            return None

        try:
            with self._session_factory() as session:
                row = session.get(InternalEventDeliveryRecord, normalized_delivery_id)
                if row is None:
                    return None
                return self._internal_event_delivery_record_to_payload(row)
        except SQLAlchemyError as exc:
            logger.warning(
                "Failed to load internal event delivery %s from database: %s",
                normalized_delivery_id,
                exc,
            )
            return None

    def list_internal_event_deliveries(
        self,
        *,
        status: str | None = None,
        event_name: str | None = None,
    ) -> list[dict[str, Any]] | None:
        if not self.enabled or self._session_factory is None:
            return None

        normalized_status = str(status or "").strip().lower() or None
        normalized_event_name = str(event_name or "").strip().lower() or None

        try:
            with self._session_factory() as session:
                statement = select(InternalEventDeliveryRecord)
                if normalized_status is not None:
                    statement = statement.where(
                        func.lower(InternalEventDeliveryRecord.status) == normalized_status
                    )
                if normalized_event_name is not None:
                    statement = statement.where(
                        func.lower(InternalEventDeliveryRecord.event_name) == normalized_event_name
                    )
                statement = statement.order_by(
                    InternalEventDeliveryRecord.updated_at.desc(),
                    InternalEventDeliveryRecord.created_at.desc(),
                )
                return [
                    self._internal_event_delivery_record_to_payload(row)
                    for row in session.scalars(statement).all()
                ]
        except SQLAlchemyError as exc:
            logger.warning("Failed to list internal event deliveries from database: %s", exc)
            return None

    def claim_due_internal_event_deliveries(
        self,
        *,
        claimed_at: str,
        retry_before: str | None = None,
        retrying_stale_before: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | None:
        if not self.enabled or self._session_factory is None:
            return None

        claimed_at_dt = _parse_datetime(claimed_at)
        retry_before_dt = _parse_datetime(retry_before) if retry_before is not None else datetime.now(UTC)
        retrying_stale_before_dt = (
            _parse_datetime(retrying_stale_before)
            if retrying_stale_before is not None
            else retry_before_dt
        )
        if claimed_at_dt is None or retry_before_dt is None or retrying_stale_before_dt is None:
            return []

        try:
            with self._session_factory() as session:
                rows = session.scalars(
                    select(InternalEventDeliveryRecord).order_by(
                        InternalEventDeliveryRecord.updated_at,
                        InternalEventDeliveryRecord.created_at,
                    )
                ).all()

                claimed_deliveries: list[dict[str, Any]] = []
                for row in rows:
                    if limit is not None and len(claimed_deliveries) >= limit:
                        break

                    claimed_delivery = self._claim_internal_event_delivery_row(
                        session,
                        row,
                        claimed_at=claimed_at,
                        retry_before_dt=retry_before_dt,
                        retrying_stale_before_dt=retrying_stale_before_dt,
                    )
                    if claimed_delivery is None:
                        continue

                    claimed_deliveries.append(claimed_delivery)

                session.commit()
                return claimed_deliveries
        except SQLAlchemyError as exc:
            logger.warning("Failed to claim due internal event deliveries from database: %s", exc)
            return None

    def find_internal_event_delivery_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        if not self.enabled or self._session_factory is None:
            return None

        normalized_key = idempotency_key.strip()
        if not normalized_key:
            return None

        try:
            with self._session_factory() as session:
                row = session.scalar(
                    select(InternalEventDeliveryRecord)
                    .where(InternalEventDeliveryRecord.idempotency_key == normalized_key)
                    .limit(1)
                )
                if row is None:
                    return None
                return self._internal_event_delivery_record_to_payload(row)
        except SQLAlchemyError as exc:
            logger.warning(
                "Failed to load internal event delivery for idempotency key %s from database: %s",
                normalized_key,
                exc,
            )
            return None

    def upsert_internal_event_delivery(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        if not self.enabled or self._session_factory is None:
            return None

        delivery_id = str(payload.get("id") or "").strip()
        event_name = str(payload.get("event_name") or "").strip()
        created_at = str(payload.get("created_at") or "").strip()
        updated_at = str(payload.get("updated_at") or created_at).strip()
        if not delivery_id or not event_name or not created_at or not updated_at:
            return None

        normalized_idempotency_key = str(payload.get("idempotency_key") or "").strip() or None

        try:
            with self._session_factory() as session:
                row = session.get(InternalEventDeliveryRecord, delivery_id)
                if row is None and normalized_idempotency_key is not None:
                    row = session.scalar(
                        select(InternalEventDeliveryRecord)
                        .where(InternalEventDeliveryRecord.idempotency_key == normalized_idempotency_key)
                        .limit(1)
                    )

                if row is None:
                    row = InternalEventDeliveryRecord(
                        id=delivery_id,
                        event_name=event_name,
                        source=str(payload.get("source") or "Internal Event Bus"),
                        payload=deepcopy(payload.get("payload")),
                        idempotency_key=normalized_idempotency_key,
                        status=str(payload.get("status") or "pending"),
                        attempt_count=int(payload.get("attempt_count", 0)),
                        last_error=str(payload.get("last_error") or "").strip() or None,
                        triggered_count=int(payload.get("triggered_count", 0)),
                        triggered_workflow_ids=deepcopy(payload.get("triggered_workflow_ids", [])),
                        triggered_run_ids=deepcopy(payload.get("triggered_run_ids", [])),
                        triggered_task_ids=deepcopy(payload.get("triggered_task_ids", [])),
                        primary_workflow=deepcopy(payload.get("primary_workflow")),
                        created_at=created_at,
                        updated_at=updated_at,
                        delivered_at=str(payload.get("delivered_at") or "").strip() or None,
                    )
                    session.add(row)
                else:
                    row.id = delivery_id
                    row.event_name = event_name
                    row.source = str(payload.get("source") or "Internal Event Bus")
                    row.payload = deepcopy(payload.get("payload"))
                    row.idempotency_key = normalized_idempotency_key
                    row.status = str(payload.get("status") or "pending")
                    row.attempt_count = int(payload.get("attempt_count", 0))
                    row.last_error = str(payload.get("last_error") or "").strip() or None
                    row.triggered_count = int(payload.get("triggered_count", 0))
                    row.triggered_workflow_ids = deepcopy(payload.get("triggered_workflow_ids", []))
                    row.triggered_run_ids = deepcopy(payload.get("triggered_run_ids", []))
                    row.triggered_task_ids = deepcopy(payload.get("triggered_task_ids", []))
                    row.primary_workflow = deepcopy(payload.get("primary_workflow"))
                    row.created_at = created_at
                    row.updated_at = updated_at
                    row.delivered_at = str(payload.get("delivered_at") or "").strip() or None

                session.commit()
                session.refresh(row)
                return self._internal_event_delivery_record_to_payload(row)
        except (TypeError, ValueError) as exc:
            logger.warning("Invalid internal event delivery payload ignored: %s", exc)
            return None
        except SQLAlchemyError as exc:
            logger.warning("Failed to upsert internal event delivery in database: %s", exc)
            return None

    def upsert_workflow_dispatch_job(
        self,
        run_id: str,
        *,
        available_at: str,
        step_delay_seconds: float | None = None,
        queued_at: str | None = None,
        dispatcher_id: str | None = None,
        claimed_at: str | None = None,
        lease_expires_at: str | None = None,
        **_: object,
    ) -> dict[str, Any] | None:
        if not self.enabled or self._session_factory is None:
            return None

        normalized_run_id = run_id.strip()
        if not normalized_run_id or _parse_datetime(available_at) is None:
            return None

        normalized_dispatcher_id = str(dispatcher_id or "").strip() or None
        normalized_claimed_at = claimed_at if claimed_at and _parse_datetime(claimed_at) else None
        normalized_lease_expires_at = (
            lease_expires_at
            if lease_expires_at and _parse_datetime(lease_expires_at)
            else None
        )
        normalized_queued_at = queued_at if queued_at and _parse_datetime(queued_at) else None
        timestamp = normalized_queued_at or datetime.now(UTC).isoformat()
        protocol_snapshot = _extract_job_protocol_snapshot(_)
        resolved_step_delay = (
            max(float(step_delay_seconds), 0.0)
            if step_delay_seconds is not None
            else None
        )

        try:
            with self._session_factory() as session:
                row = session.get(WorkflowDispatchJobRecord, normalized_run_id)
                if row is None:
                    row = WorkflowDispatchJobRecord(
                        run_id=normalized_run_id,
                        available_at=available_at,
                        step_delay_seconds=resolved_step_delay,
                        protocol=protocol_snapshot,
                        dispatcher_id=normalized_dispatcher_id,
                        claimed_at=normalized_claimed_at,
                        lease_expires_at=normalized_lease_expires_at,
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                    session.add(row)
                else:
                    row.available_at = available_at
                    row.step_delay_seconds = resolved_step_delay
                    if protocol_snapshot is not None:
                        row.protocol = protocol_snapshot
                    row.dispatcher_id = normalized_dispatcher_id
                    row.claimed_at = normalized_claimed_at
                    row.lease_expires_at = normalized_lease_expires_at
                    row.updated_at = timestamp

                session.commit()
                session.refresh(row)
                return self._workflow_dispatch_job_record_to_payload(row)
        except SQLAlchemyError as exc:
            logger.warning(
                "Failed to upsert workflow dispatch job %s in database: %s",
                normalized_run_id,
                exc,
            )
            return None

    def delete_workflow_dispatch_job(
        self,
        run_id: str,
        *,
        dispatcher_id: str | None = None,
        claimed_at: str | None = None,
    ) -> bool:
        if not self.enabled or self._session_factory is None:
            return False

        normalized_run_id = run_id.strip()
        if not normalized_run_id:
            return False

        try:
            with self._session_factory() as session:
                statement = delete(WorkflowDispatchJobRecord).where(
                    WorkflowDispatchJobRecord.run_id == normalized_run_id
                )
                if dispatcher_id is not None:
                    statement = statement.where(
                        self._nullable_column_match(
                            WorkflowDispatchJobRecord.dispatcher_id,
                            dispatcher_id,
                        )
                    )
                if claimed_at is not None:
                    statement = statement.where(
                        self._nullable_column_match(
                            WorkflowDispatchJobRecord.claimed_at,
                            claimed_at,
                        )
                    )
                result = session.execute(statement)
                session.commit()
                return result.rowcount == 1
        except SQLAlchemyError as exc:
            logger.warning(
                "Failed to delete workflow dispatch job %s from database: %s",
                normalized_run_id,
                exc,
            )
            return False

    def claim_due_workflow_dispatch_jobs(
        self,
        *,
        dispatcher_id: str,
        claimed_at: str,
        lease_expires_at: str,
        due_before: str | None = None,
        before: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | None:
        if not self.enabled or self._session_factory is None:
            return None

        normalized_dispatcher_id = dispatcher_id.strip()
        if not normalized_dispatcher_id:
            return []

        deadline_value = due_before if due_before is not None else before
        deadline = _parse_datetime(deadline_value) if deadline_value is not None else datetime.now(UTC)
        claimed_at_dt = _parse_datetime(claimed_at)
        lease_expires_at_dt = _parse_datetime(lease_expires_at)
        if deadline is None or claimed_at_dt is None or lease_expires_at_dt is None:
            return []

        try:
            with self._session_factory() as session:
                rows = session.scalars(
                    select(WorkflowDispatchJobRecord).order_by(
                        WorkflowDispatchJobRecord.available_at,
                        WorkflowDispatchJobRecord.run_id,
                    )
                ).all()

                claimed_jobs: list[dict[str, Any]] = []
                for row in rows:
                    if limit is not None and len(claimed_jobs) >= limit:
                        break

                    available_at = _parse_datetime(row.available_at)
                    if available_at is None or available_at > deadline:
                        continue

                    claimed_job = self._claim_workflow_dispatch_job_row(
                        session,
                        row,
                        dispatcher_id=normalized_dispatcher_id,
                        claimed_at=claimed_at,
                        claimed_at_dt=claimed_at_dt,
                        lease_expires_at=lease_expires_at,
                        due_before_dt=deadline,
                        respect_existing_owner=True,
                    )
                    if claimed_job is None:
                        continue

                    claimed_jobs.append(claimed_job)

                session.commit()
                return claimed_jobs
        except SQLAlchemyError as exc:
            logger.warning("Failed to claim due workflow dispatch jobs from database: %s", exc)
            return None

    def claim_workflow_dispatch_job(
        self,
        run_id: str,
        *,
        dispatcher_id: str,
        claimed_at: str,
        lease_expires_at: str,
        due_before: str | None = None,
        respect_existing_owner: bool = True,
    ) -> dict[str, Any] | None:
        if not self.enabled or self._session_factory is None:
            return None

        normalized_dispatcher_id = dispatcher_id.strip()
        if not normalized_dispatcher_id:
            return None

        claimed_at_dt = _parse_datetime(claimed_at)
        lease_expires_at_dt = _parse_datetime(lease_expires_at)
        due_before_dt = _parse_datetime(due_before) if due_before is not None else None
        if claimed_at_dt is None or lease_expires_at_dt is None:
            return None

        try:
            with self._session_factory() as session:
                row = session.get(WorkflowDispatchJobRecord, run_id)
                if row is None:
                    return None

                claimed_job = self._claim_workflow_dispatch_job_row(
                    session,
                    row,
                    dispatcher_id=normalized_dispatcher_id,
                    claimed_at=claimed_at,
                    claimed_at_dt=claimed_at_dt,
                    lease_expires_at=lease_expires_at,
                    due_before_dt=due_before_dt,
                    respect_existing_owner=respect_existing_owner,
                )
                session.commit()
                return claimed_job
        except SQLAlchemyError as exc:
            logger.warning(
                "Failed to claim workflow dispatch job %s from database: %s",
                run_id,
                exc,
            )
            return None

    def release_workflow_dispatch_job_claim(
        self,
        run_id: str,
        *,
        dispatcher_id: str,
        claimed_at: str | None = None,
    ) -> dict[str, Any] | None:
        if not self.enabled or self._session_factory is None:
            return None

        normalized_dispatcher_id = dispatcher_id.strip()
        if not normalized_dispatcher_id:
            return None

        try:
            with self._session_factory() as session:
                row = session.get(WorkflowDispatchJobRecord, run_id)
                if row is None:
                    return None

                released_job = self._release_workflow_dispatch_job_claim_row(
                    session,
                    row,
                    dispatcher_id=normalized_dispatcher_id,
                    claimed_at=claimed_at,
                )
                session.commit()
                return released_job
        except SQLAlchemyError as exc:
            logger.warning(
                "Failed to release workflow dispatch job claim %s from database: %s",
                run_id,
                exc,
            )
            return None

    def upsert_workflow_execution_job(
        self,
        run_id: str,
        *,
        available_at: str,
        queued_at: str,
        step_delay_seconds: float | None = None,
        worker_id: str | None = None,
        claimed_at: str | None = None,
        lease_expires_at: str | None = None,
        **_: object,
    ) -> dict[str, Any] | None:
        if not self.enabled or self._session_factory is None:
            return None

        normalized_run_id = run_id.strip()
        timestamp = queued_at.strip()
        if not normalized_run_id or not available_at.strip() or not timestamp:
            return None

        normalized_worker_id = str(worker_id or "").strip() or None
        normalized_claimed_at = str(claimed_at or "").strip() or None
        normalized_lease_expires_at = str(lease_expires_at or "").strip() or None
        protocol_snapshot = _extract_job_protocol_snapshot(_)
        resolved_step_delay = (
            float(step_delay_seconds)
            if step_delay_seconds is not None
            else None
        )

        try:
            with self._session_factory() as session:
                row = session.get(WorkflowExecutionJobRecord, normalized_run_id)
                if row is None:
                    row = WorkflowExecutionJobRecord(
                        run_id=normalized_run_id,
                        available_at=available_at,
                        step_delay_seconds=resolved_step_delay,
                        protocol=protocol_snapshot,
                        worker_id=normalized_worker_id,
                        claimed_at=normalized_claimed_at,
                        lease_expires_at=normalized_lease_expires_at,
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                    session.add(row)
                else:
                    row.available_at = available_at
                    row.step_delay_seconds = resolved_step_delay
                    if protocol_snapshot is not None:
                        row.protocol = protocol_snapshot
                    row.worker_id = normalized_worker_id
                    row.claimed_at = normalized_claimed_at
                    row.lease_expires_at = normalized_lease_expires_at
                    row.updated_at = timestamp

                session.commit()
                session.refresh(row)
                return self._workflow_execution_job_record_to_payload(row)
        except SQLAlchemyError as exc:
            logger.warning(
                "Failed to upsert workflow execution job %s in database: %s",
                normalized_run_id,
                exc,
            )
            return None

    def delete_workflow_execution_job(
        self,
        run_id: str,
        *,
        worker_id: str | None = None,
        claimed_at: str | None = None,
    ) -> bool:
        if not self.enabled or self._session_factory is None:
            return False

        normalized_run_id = run_id.strip()
        if not normalized_run_id:
            return False

        try:
            with self._session_factory() as session:
                statement = delete(WorkflowExecutionJobRecord).where(
                    WorkflowExecutionJobRecord.run_id == normalized_run_id
                )
                if worker_id is not None:
                    statement = statement.where(
                        self._nullable_column_match(
                            WorkflowExecutionJobRecord.worker_id,
                            worker_id,
                        )
                    )
                if claimed_at is not None:
                    statement = statement.where(
                        self._nullable_column_match(
                            WorkflowExecutionJobRecord.claimed_at,
                            claimed_at,
                        )
                    )
                result = session.execute(statement)
                session.commit()
                return result.rowcount == 1
        except SQLAlchemyError as exc:
            logger.warning(
                "Failed to delete workflow execution job %s from database: %s",
                normalized_run_id,
                exc,
            )
            return False

    def claim_due_workflow_execution_jobs(
        self,
        *,
        worker_id: str,
        claimed_at: str,
        lease_expires_at: str,
        due_before: str | None = None,
        before: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | None:
        if not self.enabled or self._session_factory is None:
            return None

        normalized_worker_id = worker_id.strip()
        if not normalized_worker_id:
            return []

        deadline_value = due_before if due_before is not None else before
        deadline = _parse_datetime(deadline_value) if deadline_value is not None else datetime.now(UTC)
        claimed_at_dt = _parse_datetime(claimed_at)
        lease_expires_at_dt = _parse_datetime(lease_expires_at)
        if deadline is None or claimed_at_dt is None or lease_expires_at_dt is None:
            return []

        try:
            with self._session_factory() as session:
                rows = session.scalars(
                    select(WorkflowExecutionJobRecord).order_by(
                        WorkflowExecutionJobRecord.available_at,
                        WorkflowExecutionJobRecord.run_id,
                    )
                ).all()

                claimed_jobs: list[dict[str, Any]] = []
                for row in rows:
                    if limit is not None and len(claimed_jobs) >= limit:
                        break

                    available_at = _parse_datetime(row.available_at)
                    if available_at is None or available_at > deadline:
                        continue

                    claimed_job = self._claim_workflow_execution_job_row(
                        session,
                        row,
                        worker_id=normalized_worker_id,
                        claimed_at=claimed_at,
                        claimed_at_dt=claimed_at_dt,
                        lease_expires_at=lease_expires_at,
                        due_before_dt=deadline,
                        respect_existing_owner=True,
                    )
                    if claimed_job is None:
                        continue

                    claimed_jobs.append(claimed_job)

                session.commit()
                return claimed_jobs
        except SQLAlchemyError as exc:
            logger.warning("Failed to claim due workflow execution jobs from database: %s", exc)
            return None

    def claim_workflow_execution_job(
        self,
        run_id: str,
        *,
        worker_id: str,
        claimed_at: str,
        lease_expires_at: str,
        due_before: str | None = None,
        respect_existing_owner: bool = True,
    ) -> dict[str, Any] | None:
        if not self.enabled or self._session_factory is None:
            return None

        normalized_worker_id = worker_id.strip()
        if not normalized_worker_id:
            return None

        claimed_at_dt = _parse_datetime(claimed_at)
        lease_expires_at_dt = _parse_datetime(lease_expires_at)
        due_before_dt = _parse_datetime(due_before) if due_before is not None else None
        if claimed_at_dt is None or lease_expires_at_dt is None:
            return None

        try:
            with self._session_factory() as session:
                row = session.get(WorkflowExecutionJobRecord, run_id)
                if row is None:
                    return None

                claimed_job = self._claim_workflow_execution_job_row(
                    session,
                    row,
                    worker_id=normalized_worker_id,
                    claimed_at=claimed_at,
                    claimed_at_dt=claimed_at_dt,
                    lease_expires_at=lease_expires_at,
                    due_before_dt=due_before_dt,
                    respect_existing_owner=respect_existing_owner,
                )
                session.commit()
                return claimed_job
        except SQLAlchemyError as exc:
            logger.warning(
                "Failed to claim workflow execution job %s from database: %s",
                run_id,
                exc,
            )
            return None

    def release_workflow_execution_job_claim(
        self,
        run_id: str,
        *,
        worker_id: str,
        claimed_at: str | None = None,
    ) -> dict[str, Any] | None:
        if not self.enabled or self._session_factory is None:
            return None

        normalized_worker_id = worker_id.strip()
        if not normalized_worker_id:
            return None

        try:
            with self._session_factory() as session:
                row = session.get(WorkflowExecutionJobRecord, run_id)
                if row is None:
                    return None

                released_job = self._release_workflow_execution_job_claim_row(
                    session,
                    row,
                    worker_id=normalized_worker_id,
                    claimed_at=claimed_at,
                )
                session.commit()
                return released_job
        except SQLAlchemyError as exc:
            logger.warning(
                "Failed to release workflow execution job claim %s from database: %s",
                run_id,
                exc,
            )
            return None

    def upsert_agent_execution_job(
        self,
        run_id: str,
        *,
        task_id: str,
        workflow_id: str,
        execution_agent_id: str | None,
        available_at: str,
        queued_at: str,
        step_delay_seconds: float | None = None,
        worker_id: str | None = None,
        claimed_at: str | None = None,
        lease_expires_at: str | None = None,
        **_: object,
    ) -> dict[str, Any] | None:
        if not self.enabled or self._session_factory is None:
            return None

        normalized_run_id = run_id.strip()
        normalized_task_id = task_id.strip()
        normalized_workflow_id = workflow_id.strip()
        timestamp = queued_at.strip()
        if (
            not normalized_run_id
            or not normalized_task_id
            or not normalized_workflow_id
            or not available_at.strip()
            or not timestamp
        ):
            return None

        normalized_execution_agent_id = str(execution_agent_id or "").strip() or None
        normalized_worker_id = str(worker_id or "").strip() or None
        normalized_claimed_at = str(claimed_at or "").strip() or None
        normalized_lease_expires_at = str(lease_expires_at or "").strip() or None
        protocol_snapshot = _extract_job_protocol_snapshot(_)
        resolved_step_delay = float(step_delay_seconds) if step_delay_seconds is not None else None

        try:
            with self._session_factory() as session:
                row = session.get(AgentExecutionJobRecord, normalized_run_id)
                if row is None:
                    row = AgentExecutionJobRecord(
                        run_id=normalized_run_id,
                        task_id=normalized_task_id,
                        workflow_id=normalized_workflow_id,
                        execution_agent_id=normalized_execution_agent_id,
                        available_at=available_at,
                        step_delay_seconds=resolved_step_delay,
                        protocol=protocol_snapshot,
                        worker_id=normalized_worker_id,
                        claimed_at=normalized_claimed_at,
                        lease_expires_at=normalized_lease_expires_at,
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                    session.add(row)
                else:
                    row.task_id = normalized_task_id
                    row.workflow_id = normalized_workflow_id
                    row.execution_agent_id = normalized_execution_agent_id
                    row.available_at = available_at
                    row.step_delay_seconds = resolved_step_delay
                    if protocol_snapshot is not None:
                        row.protocol = protocol_snapshot
                    row.worker_id = normalized_worker_id
                    row.claimed_at = normalized_claimed_at
                    row.lease_expires_at = normalized_lease_expires_at
                    row.updated_at = timestamp

                session.commit()
                session.refresh(row)
                return self._agent_execution_job_record_to_payload(row)
        except SQLAlchemyError as exc:
            logger.warning(
                "Failed to upsert agent execution job %s in database: %s",
                normalized_run_id,
                exc,
            )
            return None

    def delete_agent_execution_job(
        self,
        run_id: str,
        *,
        worker_id: str | None = None,
        claimed_at: str | None = None,
    ) -> bool:
        if not self.enabled or self._session_factory is None:
            return False

        normalized_run_id = run_id.strip()
        if not normalized_run_id:
            return False

        try:
            with self._session_factory() as session:
                statement = delete(AgentExecutionJobRecord).where(
                    AgentExecutionJobRecord.run_id == normalized_run_id
                )
                if worker_id is not None:
                    statement = statement.where(
                        self._nullable_column_match(
                            AgentExecutionJobRecord.worker_id,
                            worker_id,
                        )
                    )
                if claimed_at is not None:
                    statement = statement.where(
                        self._nullable_column_match(
                            AgentExecutionJobRecord.claimed_at,
                            claimed_at,
                        )
                    )
                result = session.execute(statement)
                session.commit()
                return result.rowcount == 1
        except SQLAlchemyError as exc:
            logger.warning(
                "Failed to delete agent execution job %s from database: %s",
                normalized_run_id,
                exc,
            )
            return False

    def claim_due_agent_execution_jobs(
        self,
        *,
        worker_id: str,
        claimed_at: str,
        lease_expires_at: str,
        due_before: str | None = None,
        before: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | None:
        if not self.enabled or self._session_factory is None:
            return None

        normalized_worker_id = worker_id.strip()
        if not normalized_worker_id:
            return []

        deadline_value = due_before if due_before is not None else before
        deadline = _parse_datetime(deadline_value) if deadline_value is not None else datetime.now(UTC)
        claimed_at_dt = _parse_datetime(claimed_at)
        lease_expires_at_dt = _parse_datetime(lease_expires_at)
        if deadline is None or claimed_at_dt is None or lease_expires_at_dt is None:
            return []

        try:
            with self._session_factory() as session:
                rows = session.scalars(
                    select(AgentExecutionJobRecord).order_by(
                        AgentExecutionJobRecord.available_at,
                        AgentExecutionJobRecord.run_id,
                    )
                ).all()

                claimed_jobs: list[dict[str, Any]] = []
                for row in rows:
                    if limit is not None and len(claimed_jobs) >= limit:
                        break

                    available_at = _parse_datetime(row.available_at)
                    if available_at is None or available_at > deadline:
                        continue

                    claimed_job = self._claim_agent_execution_job_row(
                        session,
                        row,
                        worker_id=normalized_worker_id,
                        claimed_at=claimed_at,
                        claimed_at_dt=claimed_at_dt,
                        lease_expires_at=lease_expires_at,
                        due_before_dt=deadline,
                        respect_existing_owner=True,
                    )
                    if claimed_job is None:
                        continue

                    claimed_jobs.append(claimed_job)

                session.commit()
                return claimed_jobs
        except SQLAlchemyError as exc:
            logger.warning("Failed to claim due agent execution jobs from database: %s", exc)
            return None

    def claim_agent_execution_job(
        self,
        run_id: str,
        *,
        worker_id: str,
        claimed_at: str,
        lease_expires_at: str,
        due_before: str | None = None,
        respect_existing_owner: bool = True,
    ) -> dict[str, Any] | None:
        if not self.enabled or self._session_factory is None:
            return None

        normalized_worker_id = worker_id.strip()
        if not normalized_worker_id:
            return None

        claimed_at_dt = _parse_datetime(claimed_at)
        lease_expires_at_dt = _parse_datetime(lease_expires_at)
        due_before_dt = _parse_datetime(due_before) if due_before is not None else None
        if claimed_at_dt is None or lease_expires_at_dt is None:
            return None

        try:
            with self._session_factory() as session:
                row = session.get(AgentExecutionJobRecord, run_id)
                if row is None:
                    return None

                claimed_job = self._claim_agent_execution_job_row(
                    session,
                    row,
                    worker_id=normalized_worker_id,
                    claimed_at=claimed_at,
                    claimed_at_dt=claimed_at_dt,
                    lease_expires_at=lease_expires_at,
                    due_before_dt=due_before_dt,
                    respect_existing_owner=respect_existing_owner,
                )
                session.commit()
                return claimed_job
        except SQLAlchemyError as exc:
            logger.warning(
                "Failed to claim agent execution job %s from database: %s",
                run_id,
                exc,
            )
            return None

    def release_agent_execution_job_claim(
        self,
        run_id: str,
        *,
        worker_id: str,
        claimed_at: str | None = None,
    ) -> dict[str, Any] | None:
        if not self.enabled or self._session_factory is None:
            return None

        normalized_worker_id = worker_id.strip()
        if not normalized_worker_id:
            return None

        try:
            with self._session_factory() as session:
                row = session.get(AgentExecutionJobRecord, run_id)
                if row is None:
                    return None

                released_job = self._release_agent_execution_job_claim_row(
                    session,
                    row,
                    worker_id=normalized_worker_id,
                    claimed_at=claimed_at,
                )
                session.commit()
                return released_job
        except SQLAlchemyError as exc:
            logger.warning(
                "Failed to release agent execution job claim %s from database: %s",
                run_id,
                exc,
            )
            return None

    def list_due_workflow_runs(
        self,
        *,
        due_before: str | None = None,
        before: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | None:
        if not self.enabled or self._session_factory is None:
            return None

        deadline_value = due_before if due_before is not None else before
        deadline = _parse_datetime(deadline_value) if deadline_value is not None else datetime.now(UTC)
        if deadline is None:
            return []

        try:
            with self._session_factory() as session:
                rows = session.scalars(
                    select(WorkflowRunRecord)
                    .where(WorkflowRunRecord.next_dispatch_at.is_not(None))
                    .order_by(WorkflowRunRecord.next_dispatch_at, WorkflowRunRecord.sort_index)
                ).all()
        except SQLAlchemyError as exc:
            logger.warning("Failed to load due workflow runs from database: %s", exc)
            return None

        due_runs: list[dict[str, Any]] = []
        for row in rows:
            if str(row.status or "").strip().lower() in TERMINAL_WORKFLOW_RUN_STATUSES:
                continue
            scheduled_at = _parse_datetime(row.next_dispatch_at)
            if scheduled_at is None or scheduled_at > deadline:
                continue
            due_runs.append(self._workflow_run_record_to_payload(row))
            if limit is not None and len(due_runs) >= limit:
                break
        return due_runs

    def claim_due_workflow_runs(
        self,
        *,
        dispatcher_id: str,
        claimed_at: str,
        lease_expires_at: str,
        due_before: str | None = None,
        before: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | None:
        if not self.enabled or self._session_factory is None:
            return None

        normalized_dispatcher_id = dispatcher_id.strip()
        if not normalized_dispatcher_id:
            return []

        deadline_value = due_before if due_before is not None else before
        deadline = _parse_datetime(deadline_value) if deadline_value is not None else datetime.now(UTC)
        claimed_at_dt = _parse_datetime(claimed_at)
        lease_expires_at_dt = _parse_datetime(lease_expires_at)
        if deadline is None or claimed_at_dt is None or lease_expires_at_dt is None:
            return []

        try:
            with self._session_factory() as session:
                rows = session.scalars(
                    select(WorkflowRunRecord)
                    .where(WorkflowRunRecord.next_dispatch_at.is_not(None))
                    .order_by(WorkflowRunRecord.next_dispatch_at, WorkflowRunRecord.sort_index)
                ).all()

                claimed_runs: list[dict[str, Any]] = []
                for row in rows:
                    if limit is not None and len(claimed_runs) >= limit:
                        break

                    if str(row.status or "").strip().lower() in TERMINAL_WORKFLOW_RUN_STATUSES:
                        continue

                    scheduled_at = _parse_datetime(row.next_dispatch_at)
                    if scheduled_at is None or scheduled_at > deadline:
                        continue

                    claimed_run = self._claim_workflow_run_row(
                        session,
                        row,
                        dispatcher_id=normalized_dispatcher_id,
                        claimed_at=claimed_at,
                        claimed_at_dt=claimed_at_dt,
                        lease_expires_at=lease_expires_at,
                        respect_existing_owner=True,
                        include_next_dispatch_at=True,
                    )
                    if claimed_run is None:
                        continue

                    claimed_runs.append(claimed_run)

                session.commit()
                return claimed_runs
        except SQLAlchemyError as exc:
            logger.warning("Failed to claim due workflow runs from database: %s", exc)
            return None

    def claim_workflow_run(
        self,
        run_id: str,
        *,
        dispatcher_id: str,
        claimed_at: str,
        lease_expires_at: str,
        respect_existing_owner: bool = True,
    ) -> dict[str, Any] | None:
        if not self.enabled or self._session_factory is None:
            return None

        normalized_dispatcher_id = dispatcher_id.strip()
        if not normalized_dispatcher_id:
            return None

        claimed_at_dt = _parse_datetime(claimed_at)
        lease_expires_at_dt = _parse_datetime(lease_expires_at)
        if claimed_at_dt is None or lease_expires_at_dt is None:
            return None

        try:
            with self._session_factory() as session:
                row = session.get(WorkflowRunRecord, run_id)
                if row is None:
                    return None

                claimed_run = self._claim_workflow_run_row(
                    session,
                    row,
                    dispatcher_id=normalized_dispatcher_id,
                    claimed_at=claimed_at,
                    claimed_at_dt=claimed_at_dt,
                    lease_expires_at=lease_expires_at,
                    respect_existing_owner=respect_existing_owner,
                    include_next_dispatch_at=True,
                )
                session.commit()
                return claimed_run
        except SQLAlchemyError as exc:
            logger.warning("Failed to claim workflow run %s from database: %s", run_id, exc)
            return None

    def release_workflow_run_claim(
        self,
        run_id: str,
        *,
        dispatcher_id: str,
    ) -> dict[str, Any] | None:
        if not self.enabled or self._session_factory is None:
            return None

        normalized_dispatcher_id = dispatcher_id.strip()
        if not normalized_dispatcher_id:
            return None

        try:
            with self._session_factory() as session:
                row = session.get(WorkflowRunRecord, run_id)
                if row is None:
                    return None

                released_run = self._release_workflow_run_claim_row(
                    session,
                    row,
                    dispatcher_id=normalized_dispatcher_id,
                )
                session.commit()
                return released_run
        except SQLAlchemyError as exc:
            logger.warning("Failed to release workflow run claim %s from database: %s", run_id, exc)
            return None

    def list_users(self, *, search: str | None = None) -> list[dict[str, Any]] | None:
        if not self.enabled or self._session_factory is None:
            return None

        try:
            with self._session_factory() as session:
                items = [
                    self._user_record_to_payload(row)
                    for row in session.scalars(select(UserRecord).order_by(UserRecord.sort_index)).all()
                ]
        except SQLAlchemyError as exc:
            logger.warning("Failed to load users from database: %s", exc)
            return None

        if search:
            keyword = search.lower()
            items = [
                user
                for user in items
                if keyword in user["name"].lower() or keyword in user["email"].lower()
            ]
        return items

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        if not self.enabled or self._session_factory is None:
            return None

        try:
            with self._session_factory() as session:
                row = session.get(UserRecord, user_id)
                if row is None:
                    return None
                return self._user_record_to_payload(row)
        except SQLAlchemyError as exc:
            logger.warning("Failed to load user %s from database: %s", user_id, exc)
            return None

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        if not self.enabled or self._session_factory is None:
            return None

        normalized_email = email.strip().lower()
        if not normalized_email:
            return None

        try:
            with self._session_factory() as session:
                row = session.scalar(
                    select(UserRecord)
                    .where(func.lower(UserRecord.email) == normalized_email)
                    .order_by(UserRecord.sort_index)
                    .limit(1)
                )
                if row is None:
                    return None
                return self._user_record_to_payload(row)
        except SQLAlchemyError as exc:
            logger.warning("Failed to load user by email %s from database: %s", email, exc)
            return None

    def get_user_profile(self, user_id: str) -> dict[str, Any] | None:
        if not self.enabled or self._session_factory is None:
            return None

        try:
            with self._session_factory() as session:
                row = session.get(UserProfileRecord, user_id)
                if row is None:
                    return None
                return self._decrypt_user_profile_payload(row.payload)
        except SQLAlchemyError as exc:
            logger.warning("Failed to load user profile %s from database: %s", user_id, exc)
            return None

    def list_user_profiles(self) -> list[dict[str, Any]] | None:
        if not self.enabled or self._session_factory is None:
            return None

        try:
            with self._session_factory() as session:
                return [
                    self._decrypt_user_profile_payload(row.payload)
                    for row in session.scalars(select(UserProfileRecord)).all()
                ]
        except SQLAlchemyError as exc:
            logger.warning("Failed to load user profiles from database: %s", exc)
            return None

    def delete_user_profiles(self, *, user_ids: list[str]) -> int:
        if not self.enabled or self._session_factory is None:
            return 0

        normalized_user_ids = _normalize_identifier_list(user_ids)
        if not normalized_user_ids:
            return 0

        try:
            with self._session_factory() as session:
                result = session.execute(
                    delete(UserProfileRecord).where(UserProfileRecord.user_id.in_(normalized_user_ids))
                )
                session.commit()
                return int(result.rowcount or 0)
        except SQLAlchemyError as exc:
            logger.warning("Failed to delete user profiles from database: %s", exc)
            return 0

    def find_user_profile_by_platform_account(
        self,
        *,
        platform: str,
        account_id: str,
    ) -> dict[str, Any] | None:
        if not self.enabled or self._session_factory is None:
            return None

        normalized_platform = platform.strip().lower()
        normalized_account_id = account_id.strip()
        if not normalized_platform or not normalized_account_id:
            return None

        try:
            with self._session_factory() as session:
                for row in session.scalars(select(UserProfileRecord)).all():
                    payload = self._decrypt_user_profile_payload(row.payload)
                    accounts = payload.get("platform_accounts") or payload.get("platformAccounts") or []
                    if not isinstance(accounts, list):
                        continue

                    for account in accounts:
                        if not isinstance(account, dict):
                            continue
                        account_platform = str(account.get("platform") or "").strip().lower()
                        profile_account_id = str(
                            account.get("account_id") or account.get("accountId") or ""
                        ).strip()
                        if (
                            account_platform == normalized_platform
                            and profile_account_id == normalized_account_id
                        ):
                            return payload
                return None
        except SQLAlchemyError as exc:
            logger.warning(
                "Failed to load user profile for %s:%s from database: %s",
                normalized_platform,
                normalized_account_id,
                exc,
            )
            return None

    def list_audit_logs(self) -> list[dict[str, Any]] | None:
        if not self.enabled or self._session_factory is None:
            return None

        try:
            with self._session_factory() as session:
                return [
                    self._audit_log_record_to_payload(row)
                    for row in session.scalars(
                        select(AuditLogRecord).order_by(
                            AuditLogRecord.timestamp.desc(),
                            AuditLogRecord.sort_index.desc(),
                        )
                    ).all()
                ]
        except SQLAlchemyError as exc:
            logger.warning("Failed to load audit logs from database: %s", exc)
            return None

    def list_operational_logs(self, *, limit: int | None = None) -> list[dict[str, Any]] | None:
        if not self.enabled or self._session_factory is None:
            return None

        normalized_limit = None if limit is None else max(1, int(limit))

        try:
            with self._session_factory() as session:
                statement = select(OperationalLogRecord).order_by(
                    OperationalLogRecord.timestamp.desc(),
                    OperationalLogRecord.sort_index.desc(),
                )
                if normalized_limit is not None:
                    statement = statement.limit(normalized_limit)
                return [
                    self._operational_log_record_to_payload(row)
                    for row in session.scalars(statement).all()
                ]
        except SQLAlchemyError as exc:
            logger.warning("Failed to load operational logs from database: %s", exc)
            return None

    def append_operational_log(self, *, log: dict[str, Any]) -> bool:
        if not self.enabled or self._session_factory is None:
            return False

        try:
            with self._session_factory() as session:
                self._append_operational_log(session, log)
                session.commit()
            return True
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Invalid operational log payload ignored: %s", exc)
            return False
        except SQLAlchemyError as exc:
            logger.warning("Failed to append operational log: %s", exc)
            return False

    def list_conversation_messages(
        self,
        *,
        user_id: str,
        session_id: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]] | None:
        if not self.enabled or self._session_factory is None:
            return None

        try:
            with self._session_factory() as session:
                statement = select(ConversationMessageRecord).where(
                    ConversationMessageRecord.user_id == user_id
                )
                if session_id is not None:
                    statement = statement.where(ConversationMessageRecord.session_id == session_id)
                if limit is not None:
                    rows = session.scalars(
                        statement.order_by(
                            ConversationMessageRecord.created_at.desc(),
                            ConversationMessageRecord.id.desc(),
                        ).limit(limit)
                    ).all()
                    rows = list(reversed(rows))
                else:
                    rows = session.scalars(
                        statement.order_by(
                            ConversationMessageRecord.created_at,
                            ConversationMessageRecord.id,
                        )
                    ).all()
                return [self._conversation_message_record_to_payload(row) for row in rows]
        except SQLAlchemyError as exc:
            logger.warning("Failed to load conversation messages from database: %s", exc)
            return None

    def append_conversation_message(self, payload: dict[str, Any]) -> bool:
        if not self.enabled or self._session_factory is None:
            return False

        try:
            with self._session_factory() as session:
                existing = session.get(ConversationMessageRecord, str(payload["id"]))
                if existing is not None:
                    return True
                session.add(
                    ConversationMessageRecord(
                        id=str(payload["id"]),
                        user_id=str(payload["user_id"]),
                        session_id=str(payload["session_id"]),
                        role=str(payload["role"]),
                        content=str(encryption_service.encrypt_text(str(payload["content"]))),
                        detected_lang=str(payload.get("detected_lang") or "zh"),
                        created_at=str(payload["created_at"]),
                    )
                )
                session.commit()
                return True
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Invalid conversation message payload ignored: %s", exc)
            return False
        except SQLAlchemyError as exc:
            logger.warning("Failed to append conversation message to database: %s", exc)
            return False

    def delete_conversation_messages(self, *, user_ids: list[str]) -> int:
        if not self.enabled or self._session_factory is None:
            return 0

        normalized_user_ids = _normalize_identifier_list(user_ids)
        if not normalized_user_ids:
            return 0

        try:
            with self._session_factory() as session:
                result = session.execute(
                    delete(ConversationMessageRecord).where(
                        ConversationMessageRecord.user_id.in_(normalized_user_ids)
                    )
                )
                session.commit()
                return int(result.rowcount or 0)
        except SQLAlchemyError as exc:
            logger.warning("Failed to delete conversation messages from database: %s", exc)
            return 0

    def get_memory_session_state(
        self,
        *,
        user_id: str,
        session_id: str,
    ) -> dict[str, Any] | None:
        if not self.enabled or self._session_factory is None:
            return None

        normalized_user_id = str(user_id or "").strip()
        normalized_session_id = str(session_id or "").strip()
        if not normalized_user_id or not normalized_session_id:
            return None

        try:
            with self._session_factory() as session:
                row = session.scalar(
                    select(MemorySessionStateRecord).where(
                        MemorySessionStateRecord.user_id == normalized_user_id,
                        MemorySessionStateRecord.session_id == normalized_session_id,
                    )
                )
                if row is None:
                    return None
                return self._memory_session_state_record_to_payload(row)
        except SQLAlchemyError as exc:
            logger.warning(
                "Failed to load memory session state for %s/%s from database: %s",
                normalized_user_id,
                normalized_session_id,
                exc,
            )
            return None

    def upsert_memory_session_state(self, state: dict[str, Any]) -> bool:
        if not self.enabled or self._session_factory is None:
            return False

        try:
            with self._session_factory() as session:
                self._upsert_memory_session_state(session, state)
                session.commit()
            return True
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Invalid memory session state payload ignored: %s", exc)
            return False
        except SQLAlchemyError as exc:
            logger.warning("Failed to persist memory session state: %s", exc)
            return False

    def delete_memory_session_states(self, *, user_ids: list[str]) -> int:
        if not self.enabled or self._session_factory is None:
            return 0

        normalized_user_ids = _normalize_identifier_list(user_ids)
        if not normalized_user_ids:
            return 0

        try:
            with self._session_factory() as session:
                result = session.execute(
                    delete(MemorySessionStateRecord).where(
                        MemorySessionStateRecord.user_id.in_(normalized_user_ids)
                    )
                )
                session.commit()
                return int(result.rowcount or 0)
        except SQLAlchemyError as exc:
            logger.warning("Failed to delete memory session states from database: %s", exc)
            return 0

    def list_security_rules(self) -> list[dict[str, Any]] | None:
        if not self.enabled or self._session_factory is None:
            return None

        try:
            with self._session_factory() as session:
                return [
                    self._security_rule_record_to_payload(row)
                    for row in session.scalars(
                        select(SecurityRuleRecord).order_by(SecurityRuleRecord.sort_index)
                    ).all()
                ]
        except SQLAlchemyError as exc:
            logger.warning("Failed to load security rules from database: %s", exc)
            return None

    def get_security_rule(self, rule_id: str) -> dict[str, Any] | None:
        if not self.enabled or self._session_factory is None:
            return None

        try:
            with self._session_factory() as session:
                row = session.get(SecurityRuleRecord, rule_id)
                if row is None:
                    return None
                return self._security_rule_record_to_payload(row)
        except SQLAlchemyError as exc:
            logger.warning("Failed to load security rule from database: %s", exc)
            return None

    @staticmethod
    def _system_setting_record_to_payload(row: SystemSettingRecord) -> dict[str, Any]:
        return {
            "key": row.key,
            "payload": deepcopy(row.payload),
            "updated_at": row.updated_at,
        }

    @staticmethod
    def _task_record_to_payload(row: TaskRecord) -> dict[str, Any]:
        return {
            "id": row.id,
            "title": row.title,
            "description": StatePersistenceService._decrypt_text_payload(row.description) or "",
            "status": row.status,
            "priority": row.priority,
            "created_at": row.created_at,
            "completed_at": row.completed_at,
            "agent": row.agent,
            "tokens": row.tokens,
            "duration": row.duration,
            "workflow_id": row.workflow_id,
            "workflow_run_id": row.workflow_run_id,
            "trace_id": row.trace_id,
            "channel": row.channel,
            "session_id": row.session_id,
            "user_key": row.user_key,
            "preferred_language": row.preferred_language,
            "detected_lang": row.detected_lang,
            "route_decision": deepcopy(row.route_decision),
            "result": StatePersistenceService._decrypt_json_payload(row.result),
        }

    @staticmethod
    def _task_latest_activity_at(
        task: dict[str, Any],
        step_rows: list[TaskStepRecord],
    ) -> datetime | None:
        latest_activity_at = _parse_datetime(str(task.get("created_at") or ""))
        for row in step_rows:
            if row.title != "上下文追加":
                continue
            candidate = _parse_datetime(row.finished_at or row.started_at)
            if candidate is None:
                continue
            if latest_activity_at is None or candidate > latest_activity_at:
                latest_activity_at = candidate
        return latest_activity_at

    @staticmethod
    def _agent_record_to_payload(row: AgentRecord) -> dict[str, Any]:
        config_snapshot = deepcopy(row.config_snapshot) if row.config_snapshot is not None else None
        return {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "type": row.type,
            "status": row.status,
            "enabled": row.enabled,
            "tasks_completed": row.tasks_completed,
            "tasks_total": row.tasks_total,
            "avg_response_time": row.avg_response_time,
            "tokens_used": row.tokens_used,
            "tokens_limit": row.tokens_limit,
            "success_rate": row.success_rate,
            "last_active": row.last_active,
            "config_summary": build_agent_config_summary(config_snapshot),
            "config_snapshot": config_snapshot,
        }

    @staticmethod
    def _task_step_record_to_payload(row: TaskStepRecord) -> dict[str, Any]:
        return {
            "id": row.id,
            "title": row.title,
            "status": row.status,
            "agent": row.agent,
            "started_at": row.started_at,
            "finished_at": row.finished_at,
            "message": StatePersistenceService._decrypt_text_payload(row.message) or "",
            "tokens": row.tokens,
        }

    @staticmethod
    def _workflow_record_to_payload(row: WorkflowRecord) -> dict[str, Any]:
        return {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "version": row.version,
            "status": row.status,
            "updated_at": row.updated_at,
            "node_count": row.node_count,
            "edge_count": row.edge_count,
            "trigger": deepcopy(row.trigger),
            "agent_bindings": deepcopy(row.agent_bindings),
            "nodes": deepcopy(row.nodes),
            "edges": deepcopy(row.edges),
        }

    @staticmethod
    def _workflow_run_record_to_payload(row: WorkflowRunRecord) -> dict[str, Any]:
        return {
            "id": row.id,
            "workflow_id": row.workflow_id,
            "workflow_name": row.workflow_name,
            "task_id": row.task_id,
            "trigger": row.trigger,
            "intent": row.intent,
            "status": row.status,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "started_at": row.started_at,
            "completed_at": row.completed_at,
            "next_dispatch_at": row.next_dispatch_at,
            "dispatch_failure_count": row.dispatch_failure_count,
            "last_dispatch_error": row.last_dispatch_error,
            "dispatcher_id": row.dispatcher_id,
            "dispatch_claimed_at": row.dispatch_claimed_at,
            "dispatch_lease_expires_at": row.dispatch_lease_expires_at,
            "current_stage": row.current_stage,
            "active_edges": deepcopy(row.active_edges),
            "nodes": deepcopy(row.nodes),
            "logs": StatePersistenceService._decrypt_json_payload(row.logs, default=[]),
            "dispatch_context": StatePersistenceService._decrypt_json_payload(
                row.message_dispatch_context
            ),
            "memory_hits": row.memory_hits,
            "warnings": StatePersistenceService._decrypt_json_payload(row.warnings, default=[]),
        }

    @staticmethod
    def _workflow_dispatch_job_record_to_payload(
        row: WorkflowDispatchJobRecord,
    ) -> dict[str, Any]:
        payload = {
            "run_id": row.run_id,
            "available_at": row.available_at,
            "step_delay_seconds": row.step_delay_seconds,
            "dispatcher_id": row.dispatcher_id,
            "dispatch_claimed_at": row.claimed_at,
            "dispatch_lease_expires_at": row.lease_expires_at,
            "claimed_at": row.claimed_at,
            "lease_expires_at": row.lease_expires_at,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        if row.protocol is not None:
            payload["protocol"] = deepcopy(row.protocol)
            payload.update(_flatten_job_protocol_snapshot(row.protocol))
        return payload

    @staticmethod
    def _workflow_execution_job_record_to_payload(
        row: WorkflowExecutionJobRecord,
    ) -> dict[str, Any]:
        payload = {
            "run_id": row.run_id,
            "available_at": row.available_at,
            "step_delay_seconds": row.step_delay_seconds,
            "worker_id": row.worker_id,
            "claimed_at": row.claimed_at,
            "lease_expires_at": row.lease_expires_at,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        if row.protocol is not None:
            payload["protocol"] = deepcopy(row.protocol)
            payload.update(_flatten_job_protocol_snapshot(row.protocol))
        return payload

    @staticmethod
    def _agent_execution_job_record_to_payload(
        row: AgentExecutionJobRecord,
    ) -> dict[str, Any]:
        payload = {
            "run_id": row.run_id,
            "task_id": row.task_id,
            "workflow_id": row.workflow_id,
            "execution_agent_id": row.execution_agent_id,
            "available_at": row.available_at,
            "step_delay_seconds": row.step_delay_seconds,
            "worker_id": row.worker_id,
            "claimed_at": row.claimed_at,
            "lease_expires_at": row.lease_expires_at,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        if row.protocol is not None:
            payload["protocol"] = deepcopy(row.protocol)
            payload.update(_flatten_job_protocol_snapshot(row.protocol))
        return payload

    @staticmethod
    def _internal_event_delivery_record_to_payload(
        row: InternalEventDeliveryRecord,
    ) -> dict[str, Any]:
        return {
            "id": row.id,
            "event_name": row.event_name,
            "source": row.source,
            "payload": deepcopy(row.payload),
            "idempotency_key": row.idempotency_key,
            "status": row.status,
            "attempt_count": row.attempt_count,
            "last_error": row.last_error,
            "triggered_count": row.triggered_count,
            "triggered_workflow_ids": deepcopy(row.triggered_workflow_ids),
            "triggered_run_ids": deepcopy(row.triggered_run_ids),
            "triggered_task_ids": deepcopy(row.triggered_task_ids),
            "primary_workflow": deepcopy(row.primary_workflow),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "delivered_at": row.delivered_at,
        }

    def _claim_internal_event_delivery_row(
        self,
        session,
        row: InternalEventDeliveryRecord,
        *,
        claimed_at: str,
        retry_before_dt: datetime,
        retrying_stale_before_dt: datetime,
    ) -> dict[str, Any] | None:
        status = str(row.status or "").strip().lower()
        updated_at_dt = _parse_datetime(row.updated_at) or _parse_datetime(row.created_at)
        if updated_at_dt is None:
            return None

        is_due_failed = status == "failed" and updated_at_dt <= retry_before_dt
        is_due_retrying = status == "retrying" and updated_at_dt <= retrying_stale_before_dt
        if not is_due_failed and not is_due_retrying:
            return None

        result = session.execute(
            update(InternalEventDeliveryRecord)
            .where(InternalEventDeliveryRecord.id == row.id)
            .where(InternalEventDeliveryRecord.status == row.status)
            .where(InternalEventDeliveryRecord.updated_at == row.updated_at)
            .values(
                status="retrying",
                updated_at=claimed_at,
            )
        )
        if result.rowcount != 1:
            return None

        session.refresh(row)
        return self._internal_event_delivery_record_to_payload(row)

    @staticmethod
    def _nullable_column_match(column, value):
        return column.is_(None) if value is None else column == value

    @staticmethod
    def _workflow_run_has_active_foreign_claim(
        row: WorkflowRunRecord,
        *,
        dispatcher_id: str,
        now: datetime,
    ) -> bool:
        owner = str(row.dispatcher_id or "").strip()
        active_lease_expires_at = _parse_datetime(row.dispatch_lease_expires_at)
        return bool(
            owner
            and owner != dispatcher_id
            and active_lease_expires_at is not None
            and active_lease_expires_at > now
        )

    @staticmethod
    def _workflow_dispatch_job_has_active_foreign_claim(
        row: WorkflowDispatchJobRecord,
        *,
        dispatcher_id: str,
        now: datetime,
    ) -> bool:
        owner = str(row.dispatcher_id or "").strip()
        active_lease_expires_at = _parse_datetime(row.lease_expires_at)
        return bool(
            owner
            and owner != dispatcher_id
            and active_lease_expires_at is not None
            and active_lease_expires_at > now
        )

    def _claim_workflow_run_row(
        self,
        session,
        row: WorkflowRunRecord,
        *,
        dispatcher_id: str,
        claimed_at: str,
        claimed_at_dt: datetime,
        lease_expires_at: str,
        respect_existing_owner: bool,
        include_next_dispatch_at: bool,
    ) -> dict[str, Any] | None:
        if str(row.status or "").strip().lower() in TERMINAL_WORKFLOW_RUN_STATUSES:
            return self._workflow_run_record_to_payload(row)

        if respect_existing_owner and self._workflow_run_has_active_foreign_claim(
            row,
            dispatcher_id=dispatcher_id,
            now=claimed_at_dt,
        ):
            return None

        statement = (
            update(WorkflowRunRecord)
            .where(WorkflowRunRecord.id == row.id)
            .where(WorkflowRunRecord.status == row.status)
            .where(self._nullable_column_match(WorkflowRunRecord.dispatcher_id, row.dispatcher_id))
            .where(
                self._nullable_column_match(
                    WorkflowRunRecord.dispatch_claimed_at,
                    row.dispatch_claimed_at,
                )
            )
            .where(
                self._nullable_column_match(
                    WorkflowRunRecord.dispatch_lease_expires_at,
                    row.dispatch_lease_expires_at,
                )
            )
            .values(
                dispatcher_id=dispatcher_id,
                dispatch_claimed_at=claimed_at,
                dispatch_lease_expires_at=lease_expires_at,
            )
        )
        if include_next_dispatch_at:
            statement = statement.where(
                self._nullable_column_match(
                    WorkflowRunRecord.next_dispatch_at,
                    row.next_dispatch_at,
                )
            )

        result = session.execute(statement)
        if result.rowcount != 1:
            return None

        session.refresh(row)
        return self._workflow_run_record_to_payload(row)

    def _claim_workflow_dispatch_job_row(
        self,
        session,
        row: WorkflowDispatchJobRecord,
        *,
        dispatcher_id: str,
        claimed_at: str,
        claimed_at_dt: datetime,
        lease_expires_at: str,
        due_before_dt: datetime | None,
        respect_existing_owner: bool,
    ) -> dict[str, Any] | None:
        available_at_dt = _parse_datetime(row.available_at)
        if available_at_dt is None:
            return None

        if due_before_dt is not None and available_at_dt > due_before_dt:
            return None

        if respect_existing_owner and self._workflow_dispatch_job_has_active_foreign_claim(
            row,
            dispatcher_id=dispatcher_id,
            now=claimed_at_dt,
        ):
            return None

        result = session.execute(
            update(WorkflowDispatchJobRecord)
            .where(WorkflowDispatchJobRecord.run_id == row.run_id)
            .where(WorkflowDispatchJobRecord.available_at == row.available_at)
            .where(
                self._nullable_column_match(
                    WorkflowDispatchJobRecord.dispatcher_id,
                    row.dispatcher_id,
                )
            )
            .where(
                self._nullable_column_match(
                    WorkflowDispatchJobRecord.claimed_at,
                    row.claimed_at,
                )
            )
            .where(
                self._nullable_column_match(
                    WorkflowDispatchJobRecord.lease_expires_at,
                    row.lease_expires_at,
                )
            )
            .values(
                dispatcher_id=dispatcher_id,
                claimed_at=claimed_at,
                lease_expires_at=lease_expires_at,
                updated_at=claimed_at,
            )
        )
        if result.rowcount != 1:
            return None

        session.refresh(row)
        return self._workflow_dispatch_job_record_to_payload(row)

    @staticmethod
    def _workflow_execution_job_has_active_foreign_claim(
        row: WorkflowExecutionJobRecord,
        *,
        worker_id: str,
        now: datetime,
    ) -> bool:
        owner = str(row.worker_id or "").strip()
        active_lease_expires_at = _parse_datetime(row.lease_expires_at)
        return bool(
            owner
            and owner != worker_id
            and active_lease_expires_at is not None
            and active_lease_expires_at > now
        )

    def _claim_workflow_execution_job_row(
        self,
        session,
        row: WorkflowExecutionJobRecord,
        *,
        worker_id: str,
        claimed_at: str,
        claimed_at_dt: datetime,
        lease_expires_at: str,
        due_before_dt: datetime | None,
        respect_existing_owner: bool,
    ) -> dict[str, Any] | None:
        available_at_dt = _parse_datetime(row.available_at)
        if available_at_dt is None:
            return None

        if due_before_dt is not None and available_at_dt > due_before_dt:
            return None

        if respect_existing_owner and self._workflow_execution_job_has_active_foreign_claim(
            row,
            worker_id=worker_id,
            now=claimed_at_dt,
        ):
            return None

        result = session.execute(
            update(WorkflowExecutionJobRecord)
            .where(WorkflowExecutionJobRecord.run_id == row.run_id)
            .where(WorkflowExecutionJobRecord.available_at == row.available_at)
            .where(
                self._nullable_column_match(
                    WorkflowExecutionJobRecord.worker_id,
                    row.worker_id,
                )
            )
            .where(
                self._nullable_column_match(
                    WorkflowExecutionJobRecord.claimed_at,
                    row.claimed_at,
                )
            )
            .where(
                self._nullable_column_match(
                    WorkflowExecutionJobRecord.lease_expires_at,
                    row.lease_expires_at,
                )
            )
            .values(
                worker_id=worker_id,
                claimed_at=claimed_at,
                lease_expires_at=lease_expires_at,
                updated_at=claimed_at,
            )
        )
        if result.rowcount != 1:
            return None

        session.refresh(row)
        return self._workflow_execution_job_record_to_payload(row)

    @staticmethod
    def _agent_execution_job_has_active_foreign_claim(
        row: AgentExecutionJobRecord,
        *,
        worker_id: str,
        now: datetime,
    ) -> bool:
        owner = str(row.worker_id or "").strip()
        active_lease_expires_at = _parse_datetime(row.lease_expires_at)
        return bool(
            owner
            and owner != worker_id
            and active_lease_expires_at is not None
            and active_lease_expires_at > now
        )

    def _claim_agent_execution_job_row(
        self,
        session,
        row: AgentExecutionJobRecord,
        *,
        worker_id: str,
        claimed_at: str,
        claimed_at_dt: datetime,
        lease_expires_at: str,
        due_before_dt: datetime | None,
        respect_existing_owner: bool,
    ) -> dict[str, Any] | None:
        available_at_dt = _parse_datetime(row.available_at)
        if available_at_dt is None:
            return None

        if due_before_dt is not None and available_at_dt > due_before_dt:
            return None

        if respect_existing_owner and self._agent_execution_job_has_active_foreign_claim(
            row,
            worker_id=worker_id,
            now=claimed_at_dt,
        ):
            return None

        result = session.execute(
            update(AgentExecutionJobRecord)
            .where(AgentExecutionJobRecord.run_id == row.run_id)
            .where(AgentExecutionJobRecord.available_at == row.available_at)
            .where(
                self._nullable_column_match(
                    AgentExecutionJobRecord.worker_id,
                    row.worker_id,
                )
            )
            .where(
                self._nullable_column_match(
                    AgentExecutionJobRecord.claimed_at,
                    row.claimed_at,
                )
            )
            .where(
                self._nullable_column_match(
                    AgentExecutionJobRecord.lease_expires_at,
                    row.lease_expires_at,
                )
            )
            .values(
                worker_id=worker_id,
                claimed_at=claimed_at,
                lease_expires_at=lease_expires_at,
                updated_at=claimed_at,
            )
        )
        if result.rowcount != 1:
            return None

        session.refresh(row)
        return self._agent_execution_job_record_to_payload(row)

    def _release_workflow_run_claim_row(
        self,
        session,
        row: WorkflowRunRecord,
        *,
        dispatcher_id: str,
    ) -> dict[str, Any] | None:
        status = str(row.status or "").strip().lower()
        owner = str(row.dispatcher_id or "").strip()
        if owner and owner != dispatcher_id and status not in TERMINAL_WORKFLOW_RUN_STATUSES:
            return self._workflow_run_record_to_payload(row)

        if not any((row.dispatcher_id, row.dispatch_claimed_at, row.dispatch_lease_expires_at)):
            return self._workflow_run_record_to_payload(row)

        result = session.execute(
            update(WorkflowRunRecord)
            .where(WorkflowRunRecord.id == row.id)
            .where(WorkflowRunRecord.status == row.status)
            .where(self._nullable_column_match(WorkflowRunRecord.dispatcher_id, row.dispatcher_id))
            .where(
                self._nullable_column_match(
                    WorkflowRunRecord.dispatch_claimed_at,
                    row.dispatch_claimed_at,
                )
            )
            .where(
                self._nullable_column_match(
                    WorkflowRunRecord.dispatch_lease_expires_at,
                    row.dispatch_lease_expires_at,
                )
            )
            .values(
                dispatcher_id=None,
                dispatch_claimed_at=None,
                dispatch_lease_expires_at=None,
            )
        )
        if result.rowcount != 1:
            refreshed_row = session.get(WorkflowRunRecord, row.id)
            return (
                self._workflow_run_record_to_payload(refreshed_row)
                if refreshed_row is not None
                else None
            )

        session.refresh(row)
        return self._workflow_run_record_to_payload(row)

    def _release_workflow_dispatch_job_claim_row(
        self,
        session,
        row: WorkflowDispatchJobRecord,
        *,
        dispatcher_id: str,
        claimed_at: str | None = None,
    ) -> dict[str, Any] | None:
        owner = str(row.dispatcher_id or "").strip()
        if owner and owner != dispatcher_id:
            return self._workflow_dispatch_job_record_to_payload(row)

        if claimed_at is not None and row.claimed_at != claimed_at:
            return self._workflow_dispatch_job_record_to_payload(row)

        if not any(
            (row.dispatcher_id, row.claimed_at, row.lease_expires_at)
        ):
            return self._workflow_dispatch_job_record_to_payload(row)

        result = session.execute(
            update(WorkflowDispatchJobRecord)
            .where(WorkflowDispatchJobRecord.run_id == row.run_id)
            .where(WorkflowDispatchJobRecord.available_at == row.available_at)
            .where(
                self._nullable_column_match(
                    WorkflowDispatchJobRecord.dispatcher_id,
                    row.dispatcher_id,
                )
            )
            .where(
                self._nullable_column_match(
                    WorkflowDispatchJobRecord.claimed_at,
                    row.claimed_at,
                )
            )
            .where(
                self._nullable_column_match(
                    WorkflowDispatchJobRecord.lease_expires_at,
                    row.lease_expires_at,
                )
            )
            .values(
                dispatcher_id=None,
                claimed_at=None,
                lease_expires_at=None,
                updated_at=datetime.now(UTC).isoformat(),
            )
        )
        if result.rowcount != 1:
            refreshed_row = session.get(WorkflowDispatchJobRecord, row.run_id)
            return (
                self._workflow_dispatch_job_record_to_payload(refreshed_row)
                if refreshed_row is not None
                else None
            )

        session.refresh(row)
        return self._workflow_dispatch_job_record_to_payload(row)

    def _release_workflow_execution_job_claim_row(
        self,
        session,
        row: WorkflowExecutionJobRecord,
        *,
        worker_id: str,
        claimed_at: str | None = None,
    ) -> dict[str, Any] | None:
        owner = str(row.worker_id or "").strip()
        if owner and owner != worker_id:
            return self._workflow_execution_job_record_to_payload(row)

        if claimed_at is not None and row.claimed_at != claimed_at:
            return self._workflow_execution_job_record_to_payload(row)

        if not any((row.worker_id, row.claimed_at, row.lease_expires_at)):
            return self._workflow_execution_job_record_to_payload(row)

        result = session.execute(
            update(WorkflowExecutionJobRecord)
            .where(WorkflowExecutionJobRecord.run_id == row.run_id)
            .where(WorkflowExecutionJobRecord.available_at == row.available_at)
            .where(
                self._nullable_column_match(
                    WorkflowExecutionJobRecord.worker_id,
                    row.worker_id,
                )
            )
            .where(
                self._nullable_column_match(
                    WorkflowExecutionJobRecord.claimed_at,
                    row.claimed_at,
                )
            )
            .where(
                self._nullable_column_match(
                    WorkflowExecutionJobRecord.lease_expires_at,
                    row.lease_expires_at,
                )
            )
            .values(
                worker_id=None,
                claimed_at=None,
                lease_expires_at=None,
                updated_at=datetime.now(UTC).isoformat(),
            )
        )
        if result.rowcount != 1:
            refreshed_row = session.get(WorkflowExecutionJobRecord, row.run_id)
            return (
                self._workflow_execution_job_record_to_payload(refreshed_row)
                if refreshed_row is not None
                else None
            )

        session.refresh(row)
        return self._workflow_execution_job_record_to_payload(row)

    def _release_agent_execution_job_claim_row(
        self,
        session,
        row: AgentExecutionJobRecord,
        *,
        worker_id: str,
        claimed_at: str | None = None,
    ) -> dict[str, Any] | None:
        owner = str(row.worker_id or "").strip()
        if owner and owner != worker_id:
            return self._agent_execution_job_record_to_payload(row)

        if claimed_at is not None and row.claimed_at != claimed_at:
            return self._agent_execution_job_record_to_payload(row)

        if not any((row.worker_id, row.claimed_at, row.lease_expires_at)):
            return self._agent_execution_job_record_to_payload(row)

        result = session.execute(
            update(AgentExecutionJobRecord)
            .where(AgentExecutionJobRecord.run_id == row.run_id)
            .where(AgentExecutionJobRecord.available_at == row.available_at)
            .where(
                self._nullable_column_match(
                    AgentExecutionJobRecord.worker_id,
                    row.worker_id,
                )
            )
            .where(
                self._nullable_column_match(
                    AgentExecutionJobRecord.claimed_at,
                    row.claimed_at,
                )
            )
            .where(
                self._nullable_column_match(
                    AgentExecutionJobRecord.lease_expires_at,
                    row.lease_expires_at,
                )
            )
            .values(
                worker_id=None,
                claimed_at=None,
                lease_expires_at=None,
                updated_at=datetime.now(UTC).isoformat(),
            )
        )
        if result.rowcount != 1:
            refreshed_row = session.get(AgentExecutionJobRecord, row.run_id)
            return (
                self._agent_execution_job_record_to_payload(refreshed_row)
                if refreshed_row is not None
                else None
            )

        session.refresh(row)
        return self._agent_execution_job_record_to_payload(row)

    @staticmethod
    def _user_record_to_payload(row: UserRecord) -> dict[str, Any]:
        return {
            "id": row.id,
            "name": row.name,
            "email": row.email,
            "role": row.role,
            "status": row.status,
            "last_login": row.last_login,
            "total_interactions": row.total_interactions,
            "created_at": row.created_at,
        }

    @staticmethod
    def _audit_log_record_to_payload(row: AuditLogRecord) -> dict[str, Any]:
        payload = {
            "id": row.id,
            "timestamp": row.timestamp,
            "action": row.action,
            "user": row.user,
            "resource": row.resource,
            "status": row.status,
            "ip": row.ip,
            "details": StatePersistenceService._decrypt_text_payload(row.details) or "",
        }
        if row.metadata_payload is not None:
            payload["metadata"] = StatePersistenceService._decrypt_json_payload(row.metadata_payload)
        return payload

    @staticmethod
    def _operational_log_record_to_payload(row: OperationalLogRecord) -> dict[str, Any]:
        payload = {
            "id": row.id,
            "timestamp": row.timestamp,
            "type": row.type,
            "agent": row.agent,
            "message": StatePersistenceService._decrypt_text_payload(row.message) or "",
            "source": row.source,
            "trace_id": row.trace_id,
            "task_id": row.task_id,
            "workflow_run_id": row.workflow_run_id,
        }
        if row.metadata_payload is not None:
            payload["metadata"] = StatePersistenceService._decrypt_json_payload(row.metadata_payload)
        return payload

    @staticmethod
    def _conversation_message_record_to_payload(
        row: ConversationMessageRecord,
    ) -> dict[str, Any]:
        return {
            "id": row.id,
            "user_id": row.user_id,
            "session_id": row.session_id,
            "role": row.role,
            "content": encryption_service.decrypt_text(row.content),
            "detected_lang": row.detected_lang,
            "created_at": row.created_at,
        }

    @staticmethod
    def _decrypt_user_profile_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
        decrypted = encryption_service.decrypt_json(payload)
        if not isinstance(decrypted, dict):
            return {}
        return deepcopy(decrypted)

    @staticmethod
    def _encrypt_text_payload(value: str | None) -> str | None:
        return encryption_service.encrypt_text(value)

    @staticmethod
    def _decrypt_text_payload(value: str | None) -> str | None:
        return encryption_service.decrypt_text(value)

    @staticmethod
    def _encrypt_json_payload(payload: Any) -> Any:
        return encryption_service.encrypt_json(payload)

    @staticmethod
    def _decrypt_json_payload(payload: Any, *, default: Any = None) -> Any:
        decrypted = encryption_service.decrypt_json(payload)
        if decrypted is None:
            return deepcopy(default)
        return deepcopy(decrypted)

    @staticmethod
    def _memory_session_state_record_to_payload(
        row: MemorySessionStateRecord,
    ) -> dict[str, Any]:
        return {
            "user_id": row.user_id,
            "session_id": row.session_id,
            "last_distilled_message_created_at": row.last_distilled_message_created_at,
            "last_distilled_message_ids_at_created_at": deepcopy(
                row.last_distilled_message_ids_at_created_at
            ),
            "updated_at": row.updated_at,
        }

    @staticmethod
    def _security_rule_record_to_payload(row: SecurityRuleRecord) -> dict[str, Any]:
        return {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "type": row.type,
            "enabled": row.enabled,
            "hit_count": row.hit_count,
            "last_triggered": row.last_triggered,
        }

    @staticmethod
    def _security_subject_state_record_to_payload(
        row: SecuritySubjectStateRecord,
    ) -> dict[str, Any]:
        return {
            "user_key": row.user_key,
            "rate_request_timestamps": deepcopy(row.rate_request_timestamps),
            "incident_timestamps": deepcopy(row.incident_timestamps),
            "active_penalty": deepcopy(row.active_penalty),
            "updated_at": row.updated_at,
        }

    def _purge_legacy_runtime_store(self) -> None:
        purge_runtime = getattr(self.runtime_store, "purge_legacy_runtime_state", None)
        if callable(purge_runtime):
            removed = purge_runtime()
            removed_agents = list(removed.get("agents") or []) if isinstance(removed, dict) else []
            removed_workflows = list(removed.get("workflows") or []) if isinstance(removed, dict) else []
            if removed_agents:
                logger.info(
                    "Purged legacy agents from runtime store: %s",
                    ", ".join(removed_agents),
                )
            if removed_workflows:
                logger.info(
                    "Purged legacy workflows from runtime store: %s",
                    ", ".join(removed_workflows),
                )
            return

        self.runtime_store.agents = [
            agent
            for agent in getattr(self.runtime_store, "agents", [])
            if not _is_legacy_agent_id(agent.get("id"))
        ]
        self.runtime_store.workflows = [
            workflow
            for workflow in getattr(self.runtime_store, "workflows", [])
            if not _is_legacy_workflow_id(workflow.get("id"))
        ]
        self.runtime_store.workflow_runs = [
            run
            for run in getattr(self.runtime_store, "workflow_runs", [])
            if not _is_legacy_workflow_id(run.get("workflow_id"))
        ]

    def _purge_legacy_persistence(self, session) -> tuple[int, int]:
        deleted_agents = self._delete_agents_by_ids(session, list(LEGACY_AGENT_IDS))
        deleted_workflows = self._delete_workflows_by_ids(session, list(LEGACY_WORKFLOW_IDS))
        return deleted_agents, deleted_workflows

    def _bootstrap_runtime_state(self) -> None:
        if not self.enabled or self._session_factory is None:
            return

        with self._session_factory() as session:
            deleted_agents, deleted_workflows = self._purge_legacy_persistence(session)
            if deleted_agents or deleted_workflows:
                session.commit()
                logger.info(
                    "Purged legacy registry state during bootstrap: %s agents, %s workflows",
                    deleted_agents,
                    deleted_workflows,
                )
            has_seeded_data = any(
                session.scalar(select(model.id if hasattr(model, "id") else model.user_id).limit(1))
                is not None
                for model in (TaskRecord, WorkflowRecord, UserRecord, SecurityRuleRecord, AuditLogRecord)
            )
            if not has_seeded_data:
                has_seeded_data = (
                    session.scalar(select(SystemSettingRecord.key).limit(1)) is not None
                )

        self._purge_legacy_runtime_store()
        if has_seeded_data:
            self._load_into_runtime_store()
        else:
            self.persist_all()

    def _persist(
        self,
        *,
        include_agents: bool,
        include_tasks: bool,
        include_workflows: bool,
        include_users: bool,
        include_security: bool,
        include_system_settings: bool,
    ) -> bool:
        if not self.enabled or self._session_factory is None:
            return False

        try:
            with self._session_factory() as session:
                if include_agents:
                    self._replace_agents(session)
                if include_tasks:
                    self._replace_tasks(session)
                if include_workflows:
                    self._replace_workflows(session)
                if include_users:
                    self._replace_users(session)
                if include_security:
                    self._replace_security(session)
                if include_system_settings:
                    self._replace_system_settings(session)
                session.commit()
            return True
        except SQLAlchemyError as exc:
            logger.warning("Failed to persist runtime state: %s", exc)
            return False

    def _load_into_runtime_store(self) -> None:
        if self._session_factory is None:
            return

        with self._session_factory() as session:
            loaded_agents = [
                self._agent_record_to_payload(row)
                for row in session.scalars(select(AgentRecord).order_by(AgentRecord.sort_index)).all()
                if not _is_legacy_agent_id(row.id)
            ]
            self.runtime_store.agents = loaded_agents

            loaded_tasks = [
                self._task_record_to_payload(row)
                for row in session.scalars(select(TaskRecord).order_by(TaskRecord.sort_index)).all()
            ]
            self.runtime_store.tasks = loaded_tasks

            steps_by_task: dict[str, list[dict[str, Any]]] = {}
            for row in session.scalars(select(TaskStepRecord).order_by(TaskStepRecord.task_id, TaskStepRecord.sort_index)).all():
                steps_by_task.setdefault(row.task_id, []).append(self._task_step_record_to_payload(row))
            self.runtime_store.task_steps = steps_by_task

            loaded_workflows = [
                self._workflow_record_to_payload(row)
                for row in session.scalars(select(WorkflowRecord).order_by(WorkflowRecord.sort_index)).all()
                if not _is_legacy_workflow_id(row.id)
            ]
            self.runtime_store.workflows = loaded_workflows

            loaded_runs = [
                self._workflow_run_record_to_payload(row)
                for row in session.scalars(select(WorkflowRunRecord).order_by(WorkflowRunRecord.sort_index)).all()
                if not _is_legacy_workflow_id(row.workflow_id)
            ]
            self.runtime_store.workflow_runs = loaded_runs

            loaded_users = [
                self._user_record_to_payload(row)
                for row in session.scalars(select(UserRecord).order_by(UserRecord.sort_index)).all()
            ]
            self.runtime_store.users = loaded_users

            loaded_profiles = {
                row.user_id: self._decrypt_user_profile_payload(row.payload)
                for row in session.scalars(select(UserProfileRecord)).all()
            }
            self.runtime_store.user_profiles = loaded_profiles

            loaded_audit_logs = [
                self._audit_log_record_to_payload(row)
                for row in session.scalars(
                    select(AuditLogRecord).order_by(
                        AuditLogRecord.timestamp.desc(),
                        AuditLogRecord.sort_index.desc(),
                    )
                ).all()
            ]
            self.runtime_store.audit_logs = loaded_audit_logs

            loaded_rules = [
                self._security_rule_record_to_payload(row)
                for row in session.scalars(select(SecurityRuleRecord).order_by(SecurityRuleRecord.sort_index)).all()
            ]
            self.runtime_store.security_rules = loaded_rules

            loaded_system_settings = {
                row.key: deepcopy(row.payload)
                for row in session.scalars(select(SystemSettingRecord)).all()
            }
            self.runtime_store.system_settings = loaded_system_settings
        self._purge_legacy_runtime_store()

    def _replace_system_settings(self, session) -> None:
        session.execute(delete(SystemSettingRecord))
        timestamp = datetime.now(UTC).isoformat()
        for key, payload in self.runtime_store.system_settings.items():
            normalized_key = str(key).strip()
            if not normalized_key:
                raise ValueError("System setting requires a non-empty key")
            session.add(
                SystemSettingRecord(
                    key=normalized_key,
                    payload=deepcopy(payload),
                    updated_at=timestamp,
                )
            )

    def _replace_agents(self, session) -> None:
        session.execute(delete(AgentRecord))
        active_agents = [
            agent
            for agent in self.runtime_store.agents
            if not _is_legacy_agent_id(agent.get("id"))
        ]
        session.add_all(
            AgentRecord(
                id=agent["id"],
                sort_index=index,
                name=agent["name"],
                description=agent["description"],
                type=agent["type"],
                status=agent["status"],
                enabled=bool(agent["enabled"]),
                tasks_completed=int(agent["tasks_completed"]),
                tasks_total=int(agent["tasks_total"]),
                avg_response_time=str(agent["avg_response_time"]),
                tokens_used=int(agent["tokens_used"]),
                tokens_limit=int(agent["tokens_limit"]),
                success_rate=float(agent["success_rate"]),
                last_active=str(agent["last_active"]),
            )
            for index, agent in enumerate(active_agents)
        )

    @staticmethod
    def _runtime_sort_index(items: list[dict[str, Any]], item_id: str) -> int | None:
        for index, item in enumerate(items):
            if str(item.get("id") or "").strip() == item_id:
                return index
        return None

    @staticmethod
    def _next_sort_index(session, model) -> int:
        current = session.scalar(select(func.max(model.sort_index)))
        return int(current) + 1 if current is not None else 0

    def _assign_sort_index(
        self,
        session,
        model,
        *,
        id_column,
        item_id: str,
        desired_sort_index: int | None,
        current_sort_index: int | None,
    ) -> int:
        if desired_sort_index is None:
            return (
                int(current_sort_index)
                if current_sort_index is not None
                else self._next_sort_index(session, model)
            )

        if current_sort_index is None:
            session.execute(
                update(model)
                .where(id_column != item_id)
                .where(model.sort_index >= desired_sort_index)
                .values(sort_index=model.sort_index + 1)
            )
            return desired_sort_index

        if desired_sort_index == current_sort_index:
            return desired_sort_index

        if desired_sort_index < current_sort_index:
            session.execute(
                update(model)
                .where(id_column != item_id)
                .where(model.sort_index >= desired_sort_index)
                .where(model.sort_index < current_sort_index)
                .values(sort_index=model.sort_index + 1)
            )
            return desired_sort_index

        session.execute(
            update(model)
            .where(id_column != item_id)
            .where(model.sort_index > current_sort_index)
            .where(model.sort_index <= desired_sort_index)
            .values(sort_index=model.sort_index - 1)
        )
        return desired_sort_index

    def _upsert_agent(self, session, agent: dict[str, Any]) -> None:
        agent_id = str(agent["id"])
        row = session.get(AgentRecord, agent_id)
        desired_sort_index = self._runtime_sort_index(self.runtime_store.agents, agent_id)
        assigned_sort_index = self._assign_sort_index(
            session,
            AgentRecord,
            id_column=AgentRecord.id,
            item_id=agent_id,
            desired_sort_index=desired_sort_index,
            current_sort_index=row.sort_index if row is not None else None,
        )

        if row is None:
            row = AgentRecord(
                id=agent_id,
                sort_index=assigned_sort_index,
                name=str(agent["name"]),
                description=str(agent["description"]),
                type=str(agent["type"]),
                status=str(agent["status"]),
                enabled=bool(agent.get("enabled", True)),
                tasks_completed=int(agent.get("tasks_completed", 0)),
                tasks_total=int(agent.get("tasks_total", 0)),
                avg_response_time=str(agent.get("avg_response_time") or ""),
                tokens_used=int(agent.get("tokens_used", 0)),
                tokens_limit=int(agent.get("tokens_limit", 0)),
                success_rate=float(agent.get("success_rate", 0.0)),
                last_active=str(agent.get("last_active") or ""),
                config_snapshot=deepcopy(agent.get("config_snapshot")),
            )
            session.add(row)
            return

        row.sort_index = assigned_sort_index
        row.name = str(agent["name"])
        row.description = str(agent["description"])
        row.type = str(agent["type"])
        row.status = str(agent["status"])
        row.enabled = bool(agent.get("enabled", True))
        row.tasks_completed = int(agent.get("tasks_completed", 0))
        row.tasks_total = int(agent.get("tasks_total", 0))
        row.avg_response_time = str(agent.get("avg_response_time") or "")
        row.tokens_used = int(agent.get("tokens_used", 0))
        row.tokens_limit = int(agent.get("tokens_limit", 0))
        row.success_rate = float(agent.get("success_rate", 0.0))
        row.last_active = str(agent.get("last_active") or "")
        row.config_snapshot = deepcopy(agent.get("config_snapshot"))

    def _upsert_user(self, session, user: dict[str, Any]) -> None:
        user_id = str(user["id"])
        row = session.get(UserRecord, user_id)
        desired_sort_index = self._runtime_sort_index(self.runtime_store.users, user_id)
        assigned_sort_index = self._assign_sort_index(
            session,
            UserRecord,
            id_column=UserRecord.id,
            item_id=user_id,
            desired_sort_index=desired_sort_index,
            current_sort_index=row.sort_index if row is not None else None,
        )

        if row is None:
            row = UserRecord(
                id=user_id,
                sort_index=assigned_sort_index,
                name=str(user["name"]),
                email=str(user["email"]),
                role=str(user["role"]),
                status=str(user["status"]),
                last_login=str(user.get("last_login") or ""),
                total_interactions=int(user.get("total_interactions", 0)),
                created_at=str(user["created_at"]),
            )
            session.add(row)
            return

        row.sort_index = assigned_sort_index
        row.name = str(user["name"])
        row.email = str(user["email"])
        row.role = str(user["role"])
        row.status = str(user["status"])
        row.last_login = str(user.get("last_login") or "")
        row.total_interactions = int(user.get("total_interactions", 0))
        row.created_at = str(user["created_at"])

    def _upsert_user_profile(self, session, profile: dict[str, Any]) -> None:
        user_id = str(profile.get("user_id") or profile.get("id") or "")
        if not user_id:
            raise KeyError("User profile requires id or user_id")

        row = session.get(UserProfileRecord, user_id)
        payload = encryption_service.encrypt_json(deepcopy(profile))
        if row is None:
            session.add(UserProfileRecord(user_id=user_id, payload=payload))
            return

        row.payload = payload

    def _upsert_system_setting(
        self,
        session,
        *,
        key: str,
        payload: dict[str, Any],
        updated_at: str,
    ) -> None:
        normalized_key = str(key).strip()
        if not normalized_key:
            raise KeyError("System setting requires key")
        normalized_updated_at = str(updated_at).strip()
        if not normalized_updated_at:
            raise ValueError("System setting requires updated_at")

        row = session.get(SystemSettingRecord, normalized_key)
        normalized_payload = deepcopy(payload)
        if row is None:
            session.add(
                SystemSettingRecord(
                    key=normalized_key,
                    payload=normalized_payload,
                    updated_at=normalized_updated_at,
                )
            )
            return

        row.payload = normalized_payload
        row.updated_at = normalized_updated_at

    def _upsert_task(self, session, task: dict[str, Any]) -> None:
        task_id = str(task["id"])
        row = session.get(TaskRecord, task_id)
        desired_sort_index = self._runtime_sort_index(self.runtime_store.tasks, task_id)
        assigned_sort_index = self._assign_sort_index(
            session,
            TaskRecord,
            id_column=TaskRecord.id,
            item_id=task_id,
            desired_sort_index=desired_sort_index,
            current_sort_index=row.sort_index if row is not None else None,
        )

        if row is None:
            row = TaskRecord(
                id=task_id,
                sort_index=assigned_sort_index,
                title=str(task["title"]),
                description=str(self._encrypt_text_payload(str(task["description"]))),
                status=str(task["status"]),
                priority=str(task["priority"]),
                created_at=str(task["created_at"]),
                completed_at=task.get("completed_at"),
                agent=str(task["agent"]),
                tokens=int(task.get("tokens", 0)),
                duration=task.get("duration"),
                workflow_id=task.get("workflow_id"),
                workflow_run_id=task.get("workflow_run_id"),
                trace_id=task.get("trace_id"),
                channel=task.get("channel"),
                session_id=task.get("session_id"),
                user_key=task.get("user_key"),
                preferred_language=task.get("preferred_language"),
                detected_lang=task.get("detected_lang"),
                route_decision=deepcopy(task.get("route_decision")),
                result=self._encrypt_json_payload(deepcopy(task.get("result"))),
            )
            session.add(row)
            return

        row.sort_index = assigned_sort_index
        row.title = str(task["title"])
        row.description = str(self._encrypt_text_payload(str(task["description"])))
        row.status = str(task["status"])
        row.priority = str(task["priority"])
        row.created_at = str(task["created_at"])
        row.completed_at = task.get("completed_at")
        row.agent = str(task["agent"])
        row.tokens = int(task.get("tokens", 0))
        row.duration = task.get("duration")
        row.workflow_id = task.get("workflow_id")
        row.workflow_run_id = task.get("workflow_run_id")
        row.trace_id = task.get("trace_id")
        row.channel = task.get("channel")
        row.session_id = task.get("session_id")
        row.user_key = task.get("user_key")
        row.preferred_language = task.get("preferred_language")
        row.detected_lang = task.get("detected_lang")
        row.route_decision = deepcopy(task.get("route_decision"))
        row.result = self._encrypt_json_payload(deepcopy(task.get("result")))

    def _replace_task_steps_for_task(
        self,
        session,
        task_id: str,
        steps: list[dict[str, Any]],
    ) -> None:
        session.execute(delete(TaskStepRecord).where(TaskStepRecord.task_id == task_id))
        session.add_all(
            TaskStepRecord(
                id=str(step["id"]),
                task_id=task_id,
                sort_index=index,
                title=str(step["title"]),
                status=str(step["status"]),
                agent=str(step["agent"]),
                started_at=str(step["started_at"]),
                finished_at=step.get("finished_at"),
                message=str(self._encrypt_text_payload(str(step["message"])) or ""),
                tokens=int(step.get("tokens", 0)),
            )
            for index, step in enumerate(steps)
        )

    def _upsert_workflow(self, session, workflow: dict[str, Any]) -> None:
        workflow_id = str(workflow["id"])
        row = session.get(WorkflowRecord, workflow_id)
        desired_sort_index = self._runtime_sort_index(self.runtime_store.workflows, workflow_id)
        assigned_sort_index = self._assign_sort_index(
            session,
            WorkflowRecord,
            id_column=WorkflowRecord.id,
            item_id=workflow_id,
            desired_sort_index=desired_sort_index,
            current_sort_index=row.sort_index if row is not None else None,
        )

        if row is None:
            row = WorkflowRecord(
                id=workflow_id,
                sort_index=assigned_sort_index,
                name=str(workflow["name"]),
                description=str(workflow["description"]),
                version=str(workflow["version"]),
                status=str(workflow["status"]),
                updated_at=str(workflow["updated_at"]),
                node_count=int(workflow.get("node_count", len(workflow.get("nodes", [])))),
                edge_count=int(workflow.get("edge_count", len(workflow.get("edges", [])))),
                trigger=deepcopy(workflow.get("trigger")),
                agent_bindings=deepcopy(workflow.get("agent_bindings", [])),
                nodes=deepcopy(workflow.get("nodes", [])),
                edges=deepcopy(workflow.get("edges", [])),
            )
            session.add(row)
            return

        row.sort_index = assigned_sort_index
        row.name = str(workflow["name"])
        row.description = str(workflow["description"])
        row.version = str(workflow["version"])
        row.status = str(workflow["status"])
        row.updated_at = str(workflow["updated_at"])
        row.node_count = int(workflow.get("node_count", len(workflow.get("nodes", []))))
        row.edge_count = int(workflow.get("edge_count", len(workflow.get("edges", []))))
        row.trigger = deepcopy(workflow.get("trigger"))
        row.agent_bindings = deepcopy(workflow.get("agent_bindings", []))
        row.nodes = deepcopy(workflow.get("nodes", []))
        row.edges = deepcopy(workflow.get("edges", []))

    def _upsert_workflow_run(self, session, run: dict[str, Any]) -> None:
        run_id = str(run["id"])
        row = session.get(WorkflowRunRecord, run_id)
        desired_sort_index = self._runtime_sort_index(self.runtime_store.workflow_runs, run_id)
        assigned_sort_index = self._assign_sort_index(
            session,
            WorkflowRunRecord,
            id_column=WorkflowRunRecord.id,
            item_id=run_id,
            desired_sort_index=desired_sort_index,
            current_sort_index=row.sort_index if row is not None else None,
        )

        if row is None:
            row = WorkflowRunRecord(
                id=run_id,
                sort_index=assigned_sort_index,
                workflow_id=str(run["workflow_id"]),
                workflow_name=str(run["workflow_name"]),
                task_id=str(run["task_id"]),
                trigger=str(run["trigger"]),
                intent=str(run["intent"]),
                status=str(run["status"]),
                created_at=str(run["created_at"]),
                updated_at=str(run["updated_at"]),
                started_at=str(run["started_at"]),
                completed_at=run.get("completed_at"),
                next_dispatch_at=run.get("next_dispatch_at"),
                dispatch_failure_count=int(run.get("dispatch_failure_count", 0)),
                last_dispatch_error=run.get("last_dispatch_error"),
                dispatcher_id=run.get("dispatcher_id"),
                dispatch_claimed_at=run.get("dispatch_claimed_at"),
                dispatch_lease_expires_at=run.get("dispatch_lease_expires_at"),
                current_stage=str(run.get("current_stage", "")),
                active_edges=deepcopy(run.get("active_edges", [])),
                nodes=deepcopy(run.get("nodes", [])),
                logs=self._encrypt_json_payload(deepcopy(run.get("logs", []))),
                message_dispatch_context=self._encrypt_json_payload(
                    deepcopy(run.get("dispatch_context"))
                ),
                memory_hits=int(run.get("memory_hits", 0)),
                warnings=self._encrypt_json_payload(deepcopy(run.get("warnings", []))),
            )
            session.add(row)
            return

        row.sort_index = assigned_sort_index
        row.workflow_id = str(run["workflow_id"])
        row.workflow_name = str(run["workflow_name"])
        row.task_id = str(run["task_id"])
        row.trigger = str(run["trigger"])
        row.intent = str(run["intent"])
        row.status = str(run["status"])
        row.created_at = str(run["created_at"])
        row.updated_at = str(run["updated_at"])
        row.started_at = str(run["started_at"])
        row.completed_at = run.get("completed_at")
        row.next_dispatch_at = run.get("next_dispatch_at")
        row.dispatch_failure_count = int(run.get("dispatch_failure_count", 0))
        row.last_dispatch_error = run.get("last_dispatch_error")
        row.dispatcher_id = run.get("dispatcher_id")
        row.dispatch_claimed_at = run.get("dispatch_claimed_at")
        row.dispatch_lease_expires_at = run.get("dispatch_lease_expires_at")
        row.current_stage = str(run.get("current_stage", ""))
        row.active_edges = deepcopy(run.get("active_edges", []))
        row.nodes = deepcopy(run.get("nodes", []))
        row.logs = self._encrypt_json_payload(deepcopy(run.get("logs", [])))
        row.message_dispatch_context = self._encrypt_json_payload(
            deepcopy(run.get("dispatch_context"))
        )
        row.memory_hits = int(run.get("memory_hits", 0))
        row.warnings = self._encrypt_json_payload(deepcopy(run.get("warnings", [])))

    def _delete_agents_by_ids(self, session, agent_ids: list[str]) -> int:
        normalized_ids = _normalize_identifier_list(agent_ids)
        if not normalized_ids:
            return 0

        session.execute(
            delete(AgentExecutionJobRecord).where(
                AgentExecutionJobRecord.execution_agent_id.in_(normalized_ids)
            )
        )
        result = session.execute(delete(AgentRecord).where(AgentRecord.id.in_(normalized_ids)))
        return int(result.rowcount or 0)

    def _delete_workflows_by_ids(self, session, workflow_ids: list[str]) -> int:
        normalized_ids = _normalize_identifier_list(workflow_ids)
        if not normalized_ids:
            return 0

        run_ids = list(
            session.scalars(
                select(WorkflowRunRecord.id).where(WorkflowRunRecord.workflow_id.in_(normalized_ids))
            ).all()
        )
        if run_ids:
            session.execute(
                delete(WorkflowDispatchJobRecord).where(WorkflowDispatchJobRecord.run_id.in_(run_ids))
            )
            session.execute(
                delete(WorkflowExecutionJobRecord).where(WorkflowExecutionJobRecord.run_id.in_(run_ids))
            )
        session.execute(
            delete(AgentExecutionJobRecord).where(AgentExecutionJobRecord.workflow_id.in_(normalized_ids))
        )
        session.execute(delete(WorkflowRunRecord).where(WorkflowRunRecord.workflow_id.in_(normalized_ids)))
        result = session.execute(delete(WorkflowRecord).where(WorkflowRecord.id.in_(normalized_ids)))
        return int(result.rowcount or 0)

    def _append_audit_log(self, session, log: dict[str, Any]) -> None:
        log_id = str(log["id"]).strip()
        if not log_id:
            raise ValueError("Audit log requires a non-empty id")
        if session.get(AuditLogRecord, log_id) is not None:
            return

        session.add(
            AuditLogRecord(
                id=log_id,
                sort_index=self._next_sort_index(session, AuditLogRecord),
                timestamp=str(log.get("timestamp") or ""),
                action=str(log.get("action") or ""),
                user=str(log.get("user") or ""),
                resource=str(log.get("resource") or ""),
                status=str(log.get("status") or ""),
                ip=str(log.get("ip") or "-"),
                details=str(self._encrypt_text_payload(str(log.get("details") or "")) or ""),
                metadata_payload=self._encrypt_json_payload(deepcopy(log.get("metadata"))),
            )
        )

    def _append_operational_log(self, session, log: dict[str, Any]) -> None:
        log_id = str(log["id"]).strip()
        if not log_id:
            raise ValueError("Operational log requires a non-empty id")
        if session.get(OperationalLogRecord, log_id) is not None:
            return

        session.add(
            OperationalLogRecord(
                id=log_id,
                sort_index=self._next_sort_index(session, OperationalLogRecord),
                timestamp=str(log.get("timestamp") or ""),
                type=str(log.get("type") or "info"),
                agent=str(log.get("agent") or "Runtime"),
                message=str(self._encrypt_text_payload(str(log.get("message") or "")) or ""),
                source=str(log.get("source") or "runtime"),
                trace_id=(
                    str(log.get("trace_id")).strip()
                    if log.get("trace_id") is not None and str(log.get("trace_id")).strip()
                    else None
                ),
                task_id=(
                    str(log.get("task_id")).strip()
                    if log.get("task_id") is not None and str(log.get("task_id")).strip()
                    else None
                ),
                workflow_run_id=(
                    str(log.get("workflow_run_id")).strip()
                    if log.get("workflow_run_id") is not None
                    and str(log.get("workflow_run_id")).strip()
                    else None
                ),
                metadata_payload=self._encrypt_json_payload(deepcopy(log.get("metadata"))),
            )
        )

    def _replace_tasks(self, session) -> None:
        session.execute(delete(TaskStepRecord))
        session.execute(delete(TaskRecord))
        session.add_all(
            TaskRecord(
                id=task["id"],
                sort_index=index,
                title=task["title"],
                description=self._encrypt_text_payload(str(task["description"])),
                status=task["status"],
                priority=task["priority"],
                created_at=task["created_at"],
                completed_at=task.get("completed_at"),
                agent=task["agent"],
                tokens=int(task.get("tokens", 0)),
                duration=task.get("duration"),
                workflow_id=task.get("workflow_id"),
                workflow_run_id=task.get("workflow_run_id"),
                trace_id=task.get("trace_id"),
                channel=task.get("channel"),
                session_id=task.get("session_id"),
                user_key=task.get("user_key"),
                preferred_language=task.get("preferred_language"),
                detected_lang=task.get("detected_lang"),
                result=self._encrypt_json_payload(deepcopy(task.get("result"))),
            )
            for index, task in enumerate(self.runtime_store.tasks)
        )
        step_rows: list[TaskStepRecord] = []
        for task_id, steps in self.runtime_store.task_steps.items():
            for index, step in enumerate(steps):
                step_rows.append(
                    TaskStepRecord(
                        id=step["id"],
                        task_id=task_id,
                        sort_index=index,
                        title=step["title"],
                        status=step["status"],
                        agent=step["agent"],
                        started_at=step["started_at"],
                        finished_at=step.get("finished_at"),
                        message=self._encrypt_text_payload(str(step["message"])) or "",
                        tokens=int(step.get("tokens", 0)),
                    )
                )
        session.add_all(step_rows)

    def _replace_workflows(self, session) -> None:
        session.execute(delete(WorkflowRunRecord))
        session.execute(delete(WorkflowRecord))
        active_workflows = [
            workflow
            for workflow in self.runtime_store.workflows
            if not _is_legacy_workflow_id(workflow.get("id"))
        ]
        session.add_all(
            WorkflowRecord(
                id=workflow["id"],
                sort_index=index,
                name=workflow["name"],
                description=workflow["description"],
                version=workflow["version"],
                status=workflow["status"],
                updated_at=workflow["updated_at"],
                node_count=int(workflow.get("node_count", len(workflow.get("nodes", [])))),
                edge_count=int(workflow.get("edge_count", len(workflow.get("edges", [])))),
                trigger=deepcopy(workflow.get("trigger")),
                agent_bindings=deepcopy(workflow.get("agent_bindings", [])),
                nodes=deepcopy(workflow.get("nodes", [])),
                edges=deepcopy(workflow.get("edges", [])),
            )
            for index, workflow in enumerate(active_workflows)
        )
        active_runs = [
            run
            for run in self.runtime_store.workflow_runs
            if not _is_legacy_workflow_id(run.get("workflow_id"))
        ]
        session.add_all(
            WorkflowRunRecord(
                id=run["id"],
                sort_index=index,
                workflow_id=run["workflow_id"],
                workflow_name=run["workflow_name"],
                task_id=run["task_id"],
                trigger=run["trigger"],
                intent=run["intent"],
                status=run["status"],
                created_at=run["created_at"],
                updated_at=run["updated_at"],
                started_at=run["started_at"],
                completed_at=run.get("completed_at"),
                next_dispatch_at=run.get("next_dispatch_at"),
                dispatch_failure_count=int(run.get("dispatch_failure_count", 0)),
                last_dispatch_error=run.get("last_dispatch_error"),
                dispatcher_id=run.get("dispatcher_id"),
                dispatch_claimed_at=run.get("dispatch_claimed_at"),
                dispatch_lease_expires_at=run.get("dispatch_lease_expires_at"),
                current_stage=run.get("current_stage", ""),
                active_edges=deepcopy(run.get("active_edges", [])),
                nodes=deepcopy(run.get("nodes", [])),
                logs=self._encrypt_json_payload(deepcopy(run.get("logs", []))),
                message_dispatch_context=self._encrypt_json_payload(
                    deepcopy(run.get("dispatch_context"))
                ),
                memory_hits=int(run.get("memory_hits", 0)),
                warnings=self._encrypt_json_payload(deepcopy(run.get("warnings", []))),
            )
            for index, run in enumerate(active_runs)
        )

    def _replace_users(self, session) -> None:
        session.execute(delete(UserProfileRecord))
        session.execute(delete(UserRecord))
        session.add_all(
            UserRecord(
                id=user["id"],
                sort_index=index,
                name=user["name"],
                email=user["email"],
                role=user["role"],
                status=user["status"],
                last_login=user["last_login"],
                total_interactions=int(user.get("total_interactions", 0)),
                created_at=user["created_at"],
            )
            for index, user in enumerate(self.runtime_store.users)
        )
        session.add_all(
            UserProfileRecord(
                user_id=user_id,
                payload=encryption_service.encrypt_json(deepcopy(profile)),
            )
            for user_id, profile in self.runtime_store.user_profiles.items()
        )

    def _replace_security(self, session) -> None:
        session.execute(delete(SecurityRuleRecord))
        for index, rule in enumerate(self.runtime_store.security_rules):
            rule_id = str(rule["id"]).strip()
            if not rule_id:
                raise ValueError("Security rule requires a non-empty id")

            session.add(
                SecurityRuleRecord(
                    id=rule_id,
                    sort_index=index,
                    name=str(rule["name"]),
                    description=str(rule["description"]),
                    type=str(rule["type"]),
                    enabled=bool(rule["enabled"]),
                    hit_count=int(rule.get("hit_count", 0)),
                    last_triggered=str(rule.get("last_triggered") or ""),
                )
            )

        next_sort_index_row = session.scalar(
            select(AuditLogRecord.sort_index).order_by(AuditLogRecord.sort_index.desc()).limit(1)
        )
        next_sort_index = int(next_sort_index_row) + 1 if next_sort_index_row is not None else 0
        for log in reversed(self.runtime_store.audit_logs):
            log_id = str(log.get("id") or "").strip()
            if not log_id or session.get(AuditLogRecord, log_id) is not None:
                continue
            session.add(
                AuditLogRecord(
                    id=log_id,
                    sort_index=next_sort_index,
                    timestamp=str(log.get("timestamp") or ""),
                    action=str(log.get("action") or ""),
                    user=str(log.get("user") or ""),
                    resource=str(log.get("resource") or ""),
                    status=str(log.get("status") or ""),
                    ip=str(log.get("ip") or "-"),
                    details=str(
                        self._encrypt_text_payload(str(log.get("details") or "")) or ""
                    ),
                    metadata_payload=self._encrypt_json_payload(deepcopy(log.get("metadata"))),
                )
            )
            next_sort_index += 1

    def _upsert_security_rule(self, session, rule: dict[str, Any]) -> None:
        rule_id = str(rule["id"]).strip()
        if not rule_id:
            raise ValueError("Security rule requires a non-empty id")

        row = session.get(SecurityRuleRecord, rule_id)
        assigned_sort_index = (
            int(row.sort_index)
            if row is not None
            else (
                self._runtime_sort_index(self.runtime_store.security_rules, rule_id)
                if self._runtime_sort_index(self.runtime_store.security_rules, rule_id) is not None
                else self._next_sort_index(session, SecurityRuleRecord)
            )
        )

        if row is None:
            session.add(
                SecurityRuleRecord(
                    id=rule_id,
                    sort_index=assigned_sort_index,
                    name=str(rule["name"]),
                    description=str(rule["description"]),
                    type=str(rule["type"]),
                    enabled=bool(rule["enabled"]),
                    hit_count=int(rule.get("hit_count", 0)),
                    last_triggered=str(rule.get("last_triggered") or ""),
                )
            )
            return

        row.sort_index = assigned_sort_index
        row.name = str(rule["name"])
        row.description = str(rule["description"])
        row.type = str(rule["type"])
        row.enabled = bool(rule["enabled"])
        row.hit_count = int(rule.get("hit_count", 0))
        row.last_triggered = str(rule.get("last_triggered") or "")

    def _upsert_security_subject_state(self, session, state: dict[str, Any]) -> None:
        user_key = str(state["user_key"]).strip()
        if not user_key:
            raise ValueError("Security subject state requires a non-empty user_key")

        row = session.get(SecuritySubjectStateRecord, user_key)
        updated_at = str(state["updated_at"]).strip()
        if not updated_at:
            raise ValueError("Security subject state requires updated_at")

        if row is None:
            session.add(
                SecuritySubjectStateRecord(
                    user_key=user_key,
                    rate_request_timestamps=deepcopy(state.get("rate_request_timestamps", [])),
                    incident_timestamps=deepcopy(state.get("incident_timestamps", [])),
                    active_penalty=deepcopy(state.get("active_penalty")),
                    updated_at=updated_at,
                )
            )
            return

        row.rate_request_timestamps = deepcopy(state.get("rate_request_timestamps", []))
        row.incident_timestamps = deepcopy(state.get("incident_timestamps", []))
        row.active_penalty = deepcopy(state.get("active_penalty"))
        row.updated_at = updated_at

    def _upsert_memory_session_state(self, session, state: dict[str, Any]) -> None:
        user_id = str(state["user_id"]).strip()
        session_id = str(state["session_id"]).strip()
        if not user_id or not session_id:
            raise ValueError("Memory session state requires non-empty user_id and session_id")

        last_distilled_message_created_at = str(
            state["last_distilled_message_created_at"]
        ).strip()
        if not last_distilled_message_created_at:
            raise ValueError("Memory session state requires last_distilled_message_created_at")

        updated_at = str(state["updated_at"]).strip()
        if not updated_at:
            raise ValueError("Memory session state requires updated_at")

        message_ids = [
            str(item).strip()
            for item in state.get("last_distilled_message_ids_at_created_at", [])
            if str(item).strip()
        ]

        row = session.scalar(
            select(MemorySessionStateRecord).where(
                MemorySessionStateRecord.user_id == user_id,
                MemorySessionStateRecord.session_id == session_id,
            )
        )

        if row is None:
            session.add(
                MemorySessionStateRecord(
                    user_id=user_id,
                    session_id=session_id,
                    last_distilled_message_created_at=last_distilled_message_created_at,
                    last_distilled_message_ids_at_created_at=message_ids,
                    updated_at=updated_at,
                )
            )
            return

        row.last_distilled_message_created_at = last_distilled_message_created_at
        row.last_distilled_message_ids_at_created_at = message_ids
        row.updated_at = updated_at

    def _clear_all_tables(self, session) -> None:
        for model in (
            SystemSettingRecord,
            InternalEventDeliveryRecord,
            MemorySessionStateRecord,
            ConversationMessageRecord,
            SecuritySubjectStateRecord,
            TaskStepRecord,
            TaskRecord,
            WorkflowDispatchJobRecord,
            WorkflowExecutionJobRecord,
            AgentExecutionJobRecord,
            WorkflowRunRecord,
            WorkflowRecord,
            UserProfileRecord,
            UserRecord,
            OperationalLogRecord,
            AuditLogRecord,
            SecurityRuleRecord,
            AgentRecord,
        ):
            session.execute(delete(model))


persistence_service = StatePersistenceService()
