from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from threading import Lock

from app.config import get_settings
from app.services.encryption_service import encryption_service


logger = logging.getLogger(__name__)


class SQLiteMidTermMemoryStore:
    def __init__(self, sqlite_path: str | None = None) -> None:
        self.sqlite_path = sqlite_path or get_settings().memory_sqlite_path
        self._lock = Lock()
        self._warned_unavailable = False

    def _connect(self) -> sqlite3.Connection | None:
        try:
            if self.sqlite_path != ":memory:":
                path = Path(self.sqlite_path)
                path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.sqlite_path)
            connection.row_factory = sqlite3.Row
            self._ensure_schema(connection)
            self._warned_unavailable = False
            return connection
        except Exception as exc:  # pragma: no cover - depends on runtime filesystem state
            if not self._warned_unavailable:
                logger.warning("SQLite mid-term memory disabled, using in-memory fallback: %s", exc)
                self._warned_unavailable = True
            return None

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS mid_term_summaries (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                trigger TEXT NOT NULL,
                source_count INTEGER NOT NULL,
                summary TEXT NOT NULL,
                entities_json TEXT NOT NULL,
                events_json TEXT NOT NULL,
                keywords_json TEXT NOT NULL,
                preferences_json TEXT NOT NULL DEFAULT '[]',
                decisions_json TEXT NOT NULL DEFAULT '[]',
                task_results_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            )
            """
        )
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(mid_term_summaries)").fetchall()
        }
        for column_name in ("preferences_json", "decisions_json", "task_results_json"):
            if column_name in existing_columns:
                continue
            connection.execute(
                f"ALTER TABLE mid_term_summaries ADD COLUMN {column_name} TEXT NOT NULL DEFAULT '[]'"
            )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_mid_term_summaries_user_created
            ON mid_term_summaries (user_id, created_at)
            """
        )
        connection.commit()

    def save_summary(self, summary: dict) -> bool:
        connection = self._connect()
        if connection is None:
            return False

        with self._lock:
            try:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO mid_term_summaries (
                        id,
                        user_id,
                        session_id,
                        trigger,
                        source_count,
                        summary,
                        entities_json,
                        events_json,
                        keywords_json,
                        preferences_json,
                        decisions_json,
                        task_results_json,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        summary["id"],
                        summary["user_id"],
                        summary["session_id"],
                        summary["trigger"],
                        int(summary["source_count"]),
                        str(encryption_service.encrypt_text(str(summary["summary"]))),
                        str(
                            encryption_service.encrypt_text(
                                json.dumps(summary.get("entities", []), ensure_ascii=False)
                            )
                        ),
                        str(
                            encryption_service.encrypt_text(
                                json.dumps(summary.get("events", []), ensure_ascii=False)
                            )
                        ),
                        str(
                            encryption_service.encrypt_text(
                                json.dumps(summary.get("keywords", []), ensure_ascii=False)
                            )
                        ),
                        str(
                            encryption_service.encrypt_text(
                                json.dumps(summary.get("preferences", []), ensure_ascii=False)
                            )
                        ),
                        str(
                            encryption_service.encrypt_text(
                                json.dumps(summary.get("decisions", []), ensure_ascii=False)
                            )
                        ),
                        str(
                            encryption_service.encrypt_text(
                                json.dumps(summary.get("task_results", []), ensure_ascii=False)
                            )
                        ),
                        summary["created_at"],
                    ),
                )
                connection.commit()
                return True
            except Exception as exc:
                logger.warning("SQLite mid-term memory write failed, using in-memory fallback: %s", exc)
                return False
            finally:
                connection.close()

    def list_summaries(self, user_id: str) -> list[dict] | None:
        connection = self._connect()
        if connection is None:
            return None

        try:
            rows = connection.execute(
                """
                SELECT
                    id,
                    user_id,
                    session_id,
                    trigger,
                    source_count,
                    summary,
                    entities_json,
                    events_json,
                    keywords_json,
                    preferences_json,
                    decisions_json,
                    task_results_json,
                    created_at
                FROM mid_term_summaries
                WHERE user_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (user_id,),
            ).fetchall()
            return [
                {
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "session_id": row["session_id"],
                    "trigger": row["trigger"],
                    "source_count": row["source_count"],
                    "summary": str(
                        encryption_service.decrypt_text(str(row["summary"])) or ""
                    ),
                    "entities": self._decode_json_field(row["entities_json"]),
                    "events": self._decode_json_field(row["events_json"]),
                    "keywords": self._decode_json_field(row["keywords_json"]),
                    "preferences": self._decode_json_field(row["preferences_json"]),
                    "decisions": self._decode_json_field(row["decisions_json"]),
                    "task_results": self._decode_json_field(row["task_results_json"]),
                    "created_at": row["created_at"],
                }
                for row in rows
            ]
        except Exception as exc:
            logger.warning("SQLite mid-term memory read failed, using in-memory fallback: %s", exc)
            return None
        finally:
            connection.close()

    def clear(self) -> None:
        connection = self._connect()
        if connection is None:
            return

        with self._lock:
            try:
                connection.execute("DELETE FROM mid_term_summaries")
                connection.commit()
            except Exception as exc:
                logger.warning("SQLite mid-term memory clear failed: %s", exc)
            finally:
                connection.close()

    @staticmethod
    def _decode_json_field(value: object) -> list:
        decoded = str(encryption_service.decrypt_text(str(value or "")) or "")
        if not decoded:
            return []
        try:
            parsed = json.loads(decoded)
        except Exception:
            return []
        return parsed if isinstance(parsed, list) else []


sqlite_mid_term_memory_store = SQLiteMidTermMemoryStore()
