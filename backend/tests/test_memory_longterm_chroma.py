from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.chroma_memory_store import ChromaLongTermMemoryStore, LocalPersistentChromaClient
from app.core.sqlite_memory_store import SQLiteMidTermMemoryStore
from app.services.memory_service import MemoryService


class NoRedisProvider:
    def get_client(self):
        return None


class FakeChromaCollection:
    def __init__(self) -> None:
        self.records: dict[str, dict] = {}

    def upsert(self, ids, embeddings, documents, metadatas) -> None:
        for memory_id, embedding, document, metadata in zip(ids, embeddings, documents, metadatas):
            self.records[memory_id] = {
                "embedding": embedding,
                "document": document,
                "metadata": metadata,
            }

    def get(self, where, include):
        ids = [
            memory_id
            for memory_id, row in self.records.items()
            if all(str(row["metadata"].get(key) or "") == str(value) for key, value in (where or {}).items())
        ]
        documents = [self.records[memory_id]["document"] for memory_id in ids]
        metadatas = [self.records[memory_id]["metadata"] for memory_id in ids]
        return {"ids": ids, "documents": documents, "metadatas": metadatas, "include": include}

    def delete(self, ids=None, where=None) -> None:
        target_ids = [str(memory_id) for memory_id in (ids or []) if str(memory_id)]
        if not target_ids and where:
            target_ids = list(self.get(where=where, include=[]).get("ids") or [])
        for memory_id in target_ids:
            self.records.pop(memory_id, None)

    @staticmethod
    def _distance(left: list[float], right: list[float]) -> float:
        return sum((lval - rval) ** 2 for lval, rval in zip(left, right))

    def query(self, query_embeddings, n_results, where, include):
        user_id = where["user_id"]
        query_embedding = query_embeddings[0]
        scored = []
        for memory_id, row in self.records.items():
            if row["metadata"]["user_id"] != user_id:
                continue
            scored.append((self._distance(query_embedding, row["embedding"]), memory_id, row))
        scored.sort(key=lambda item: item[0])
        top = scored[:n_results]
        return {
            "ids": [[memory_id for _, memory_id, _ in top]],
            "documents": [[row["document"] for _, _, row in top]],
            "metadatas": [[row["metadata"] for _, _, row in top]],
            "distances": [[distance for distance, _, _ in top]],
            "include": include,
        }


class FakeChromaClient:
    def __init__(self) -> None:
        self.collections: dict[str, FakeChromaCollection] = {}

    def get_or_create_collection(self, name: str):
        return self.collections.setdefault(name, FakeChromaCollection())

    def delete_collection(self, name: str) -> None:
        self.collections.pop(name, None)

    def close(self) -> None:
        return None


class RecordingChromaModule:
    def __init__(self) -> None:
        self.http_calls: list[dict] = []
        self.persistent_calls: list[dict] = []

    def HttpClient(self, *, host: str, port: int, ssl: bool):
        self.http_calls.append({"host": host, "port": port, "ssl": ssl})
        return FakeChromaClient()

    def PersistentClient(self, *, path: str):
        self.persistent_calls.append({"path": path})
        return FakeChromaClient()


class EnvSensitiveChromaModule:
    class _HttpClientSettings(BaseSettings):
        tenant: str = "default"
        model_config = SettingsConfigDict(env_prefix="WORKBOT_", extra="forbid")

    def HttpClient(self, *, host: str, port: int, ssl: bool):
        _ = (host, port, ssl)
        self._HttpClientSettings()
        return FakeChromaClient()


def test_chroma_long_term_memory_store_builds_http_client(monkeypatch) -> None:
    fake_module = RecordingChromaModule()
    monkeypatch.setattr("app.core.chroma_memory_store._load_chromadb_module", lambda: fake_module)

    store = ChromaLongTermMemoryStore(
        chroma_url="https://memory.example:9443",
        chroma_client_mode="http",
        collection_name="http_collection",
    )

    client = store._build_client()

    assert isinstance(client, FakeChromaClient)
    assert fake_module.http_calls == [{"host": "memory.example", "port": 9443, "ssl": True}]
    assert fake_module.persistent_calls == []


def test_chroma_long_term_memory_store_isolates_workbot_env_for_http_client(monkeypatch) -> None:
    monkeypatch.setenv("WORKBOT_ENVIRONMENT", "docker-compose")
    monkeypatch.setenv("WORKBOT_MESSAGE_RATE_LIMIT_PER_MINUTE", "9")
    monkeypatch.setattr(
        "app.core.chroma_memory_store._load_chromadb_module",
        lambda: EnvSensitiveChromaModule(),
    )

    store = ChromaLongTermMemoryStore(
        chroma_url="https://memory.example:9443",
        chroma_client_mode="http",
        collection_name="isolated_env_collection",
    )

    client = store._build_client()

    assert isinstance(client, FakeChromaClient)


def test_chroma_long_term_memory_store_builds_persistent_client(monkeypatch, tmp_path) -> None:
    fake_module = RecordingChromaModule()
    monkeypatch.setattr("app.core.chroma_memory_store._load_chromadb_module", lambda: fake_module)
    persist_path = tmp_path / "chroma-data"

    store = ChromaLongTermMemoryStore(
        chroma_url="http://localhost:8000",
        chroma_client_mode="persistent",
        chroma_persist_path=str(persist_path),
        collection_name="persistent_collection",
    )

    client = store._build_client()

    assert isinstance(client, LocalPersistentChromaClient)
    assert Path(client._db_path) == persist_path / "long_term_memory.sqlite3"
    assert fake_module.http_calls == []
    assert fake_module.persistent_calls == []
    client.close()


def test_chroma_long_term_memory_store_round_trips_records() -> None:
    fake_client = FakeChromaClient()
    store = ChromaLongTermMemoryStore(
        chroma_url="http://fake:8000",
        collection_name="test_collection",
        client_factory_override=lambda: fake_client,
    )

    payload = {
        "id": "lng-1",
        "user_id": "telegram:chroma-user",
        "source_mid_term_id": "mid-1",
        "memory_text": "用户偏好中文回复，每周一发送安全周报",
        "keywords": ["中文", "周报"],
        "created_at": "2026-04-03T09:00:00+00:00",
    }

    assert store.save_memory(payload) is True
    listed = store.list_memories("telegram:chroma-user")
    queried = store.query_memories("telegram:chroma-user", "中文周报", 5)

    assert listed is not None
    assert queried is not None
    assert listed[0]["id"] == "lng-1"
    assert queried[0]["memory_id"] == "lng-1"
    assert queried[0]["score"] > 0
    assert queried[0]["vector_score"] == queried[0]["score"]
    assert queried[0]["distance"] >= 0
    assert "中文" in queried[0]["matched_terms"] or "周报" in queried[0]["matched_terms"]
    stored = fake_client.collections["test_collection"].records["lng-1"]
    assert stored["document"].startswith("enc:v1:")
    assert stored["metadata"]["summary"].startswith("enc:v1:")
    assert stored["metadata"]["keywords_json"].startswith("enc:v1:")


def test_memory_service_uses_chroma_long_term_store_for_layers_and_retrieval(tmp_path) -> None:
    fake_client = FakeChromaClient()
    service = MemoryService(
        redis_provider_override=NoRedisProvider(),
        mid_term_store_override=SQLiteMidTermMemoryStore(sqlite_path=str(tmp_path / "midterm.sqlite3")),
        long_term_store_override=ChromaLongTermMemoryStore(
            chroma_url="http://fake:8000",
            collection_name="memory_service_collection",
            client_factory_override=lambda: fake_client,
        ),
    )

    service.ingest_message(
        user_id="telegram:memory-chroma",
        session_id="session-chroma",
        role="user",
        content="请记录我偏好中文回复，并且每周一发送安全周报",
        detected_lang="zh",
    )
    service.ingest_message(
        user_id="telegram:memory-chroma",
        session_id="session-chroma",
        role="assistant",
        content="好的，我会优先中文，并整理周报提醒。",
        detected_lang="zh",
    )

    distill_result = service.distill(
        user_id="telegram:memory-chroma",
        trigger="session_end",
        session_id="session-chroma",
    )
    layers = service.get_layers("telegram:memory-chroma")
    retrieve_result = service.retrieve("telegram:memory-chroma", "中文周报提醒", limit=5)

    assert distill_result["created"] is True
    assert layers["long_term_count"] >= 3
    assert distill_result["long_term"]["id"] in {item["id"] for item in layers["long_term"]}
    assert retrieve_result["total"] >= 1
    assert any(
        item["source_mid_term_id"] == distill_result["mid_term"]["id"]
        for item in retrieve_result["items"]
    )


def test_chroma_long_term_memory_store_deletes_by_tenant_or_user() -> None:
    fake_client = FakeChromaClient()
    store = ChromaLongTermMemoryStore(
        chroma_url="http://fake:8000",
        collection_name="delete_collection",
        client_factory_override=lambda: fake_client,
    )

    assert (
        store.save_memory(
            {
                "id": "lng-delete-1",
                "user_id": "tenant-user-delete",
                "source_mid_term_id": "mid-delete-1",
                "memory_text": "待删除长期记忆",
                "summary": "待删除",
                "keywords": ["删除"],
                "tenant_id": "tenant-delete",
                "created_at": "2026-04-18T10:00:00+00:00",
            }
        )
        is True
    )
    assert (
        store.save_memory(
            {
                "id": "lng-keep-1",
                "user_id": "tenant-user-keep",
                "source_mid_term_id": "mid-keep-1",
                "memory_text": "保留长期记忆",
                "summary": "保留",
                "keywords": ["保留"],
                "tenant_id": "tenant-keep",
                "created_at": "2026-04-18T10:01:00+00:00",
            }
        )
        is True
    )

    assert store.delete_memories(tenant_id="tenant-delete") == 1

    deleted_items = store.list_memories("tenant-user-delete")
    kept_items = store.list_memories("tenant-user-keep")

    assert deleted_items == []
    assert kept_items is not None
    assert [item["id"] for item in kept_items] == ["lng-keep-1"]


def test_memory_service_chroma_retrieve_supports_dynamic_window_and_hybrid_scores(tmp_path) -> None:
    fake_client = FakeChromaClient()
    service = MemoryService(
        redis_provider_override=NoRedisProvider(),
        mid_term_store_override=SQLiteMidTermMemoryStore(sqlite_path=str(tmp_path / "midterm_dynamic.sqlite3")),
        long_term_store_override=ChromaLongTermMemoryStore(
            chroma_url="http://fake:8000",
            collection_name="memory_dynamic_collection",
            client_factory_override=lambda: fake_client,
        ),
    )

    user_id = "telegram:memory-chroma-dynamic"
    base_time = datetime(2026, 4, 4, 8, 0, tzinfo=UTC)
    service._long_term[user_id] = []

    for index in range(9):
        payload = {
            "id": f"lng-chroma-dynamic-{index}",
            "user_id": user_id,
            "source_mid_term_id": "mid-shared" if index < 4 else f"mid-{index}",
            "memory_type": "session_summary",
            "summary": "偏好中文，每周一安全周报提醒",
            "memory_text": f"请保持中文输出，并在每周一发送安全周报提醒（chroma 样本 {index}）",
            "keywords": ["中文", "周报", "安全", "每周一"],
            "created_at": (base_time + timedelta(minutes=index)).isoformat(),
        }
        service._long_term[user_id].append(dict(payload))
        assert service._long_term_store is not None
        assert service._long_term_store.save_memory(payload) is True

    result = service.retrieve(
        user_id=user_id,
        query="请继续中文安全周报每周一提醒",
        limit=5,
    )

    assert 5 <= result["total"] <= 9
    assert result["query_expanded_terms"]
    assert len({item["memory_id"] for item in result["items"]}) == result["total"]
    assert len({item["source_mid_term_id"] for item in result["items"][:3]}) >= 2
    assert all("lexical_score" in item for item in result["items"])
    assert all("vector_score" in item for item in result["items"])
    assert all("phrase_hit_count" in item for item in result["items"])
    assert all("matched_terms" in item for item in result["items"])
    assert all(isinstance(item["lexical_score"], float) for item in result["items"])
    assert all(isinstance(item["phrase_hit_count"], int) for item in result["items"])
    assert all(isinstance(item["matched_terms"], list) for item in result["items"])
    assert all(item["vector_score"] is not None for item in result["items"])
