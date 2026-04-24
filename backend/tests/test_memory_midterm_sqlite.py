from __future__ import annotations

from pathlib import Path
import sqlite3

from app.modules.organization.memory_store.sqlite_memory_store import SQLiteMidTermMemoryStore
from app.modules.organization.application.memory_service import MemoryService


class NoRedisProvider:
    def get_client(self):
        return None


def _build_service(sqlite_path: Path) -> MemoryService:
    return MemoryService(
        redis_provider_override=NoRedisProvider(),
        mid_term_store_override=SQLiteMidTermMemoryStore(sqlite_path=str(sqlite_path)),
    )


def test_memory_service_persists_mid_term_summaries_to_sqlite(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "mid-term.sqlite3"
    service = _build_service(sqlite_path)

    service.ingest_message(
        user_id="telegram:sqlite-user",
        session_id="session-sqlite",
        role="user",
        content="请记录我偏好中文回复，并且每周一发送安全周报",
        detected_lang="zh",
    )
    service.ingest_message(
        user_id="telegram:sqlite-user",
        session_id="session-sqlite",
        role="assistant",
        content="好的，我会优先中文，并整理周报提醒。",
        detected_lang="zh",
    )

    distill_result = service.distill(
        user_id="telegram:sqlite-user",
        trigger="session_end",
        session_id="session-sqlite",
    )

    assert distill_result["created"] is True
    assert sqlite_path.exists() is True

    fresh_service = _build_service(sqlite_path)
    layers = fresh_service.get_layers("telegram:sqlite-user")

    assert layers["short_term_count"] == 0
    assert layers["mid_term_count"] == 1
    assert layers["mid_term"][0]["id"] == distill_result["mid_term"]["id"]
    assert layers["mid_term"][0]["session_id"] == "session-sqlite"


def test_memory_service_falls_back_when_sqlite_mid_term_store_unavailable(tmp_path: Path) -> None:
    invalid_path = tmp_path / "not-a-file"
    invalid_path.mkdir()
    service = _build_service(invalid_path)

    service.ingest_message(
        user_id="telegram:sqlite-fallback",
        session_id="session-fallback",
        role="user",
        content="记录我的提醒偏好",
        detected_lang="zh",
    )

    distill_result = service.distill(
        user_id="telegram:sqlite-fallback",
        trigger="daily",
        session_id="session-fallback",
    )
    layers = service.get_layers("telegram:sqlite-fallback")

    assert distill_result["created"] is True
    assert layers["mid_term_count"] == 1
    assert layers["mid_term"][0]["id"] == distill_result["mid_term"]["id"]


def test_memory_service_mid_term_summary_is_encrypted_at_rest_in_sqlite(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "mid-term-encrypted.sqlite3"
    service = _build_service(sqlite_path)

    service.ingest_message(
        user_id="telegram:sqlite-encrypted-user",
        session_id="session-sqlite-encrypted",
        role="user",
        content="请记录我偏好中文回复，并且每周一发送安全周报",
        detected_lang="zh",
    )
    service.ingest_message(
        user_id="telegram:sqlite-encrypted-user",
        session_id="session-sqlite-encrypted",
        role="assistant",
        content="好的，我会优先中文，并整理周报提醒。",
        detected_lang="zh",
    )
    service.distill(
        user_id="telegram:sqlite-encrypted-user",
        trigger="session_end",
        session_id="session-sqlite-encrypted",
    )

    connection = sqlite3.connect(str(sqlite_path))
    try:
        row = connection.execute(
            """
            SELECT summary, entities_json, events_json, keywords_json
            FROM mid_term_summaries
            LIMIT 1
            """
        ).fetchone()
    finally:
        connection.close()

    assert row is not None
    assert isinstance(row[0], str) and row[0].startswith("enc:v1:")
    assert isinstance(row[1], str) and row[1].startswith("enc:v1:")
    assert isinstance(row[2], str) and row[2].startswith("enc:v1:")
    assert isinstance(row[3], str) and row[3].startswith("enc:v1:")


def test_sqlite_mid_term_memory_store_deletes_by_tenant_or_user(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "mid-term-delete.sqlite3"
    store = SQLiteMidTermMemoryStore(sqlite_path=str(sqlite_path))

    for summary_id, user_id, tenant_id in (
        ("mid-delete-1", "tenant-user-delete", "tenant-delete"),
        ("mid-keep-1", "tenant-user-keep", "tenant-keep"),
    ):
        assert (
            store.save_summary(
                {
                    "id": summary_id,
                    "user_id": user_id,
                    "session_id": f"session-{summary_id}",
                    "trigger": "session_end",
                    "source_count": 2,
                    "summary": f"{summary_id} summary",
                    "entities": [],
                    "events": [],
                    "keywords": [],
                    "preferences": [],
                    "decisions": [],
                    "task_results": [],
                    "tenant_id": tenant_id,
                    "project_id": "default",
                    "environment": "test",
                    "created_at": "2026-04-18T10:00:00+00:00",
                }
            )
            is True
        )

    assert store.delete_summaries(tenant_id="tenant-delete") == 1

    deleted_items = store.list_summaries("tenant-user-delete")
    kept_items = store.list_summaries("tenant-user-keep")

    assert deleted_items == []
    assert kept_items is not None
    assert [item["id"] for item in kept_items] == ["mid-keep-1"]
