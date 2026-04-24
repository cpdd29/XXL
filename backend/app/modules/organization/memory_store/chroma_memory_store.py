from __future__ import annotations

import json
import logging
import math
import os
import re
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic_settings import BaseSettings

from app.config import get_settings
from app.platform.security.encryption_service import encryption_service


logger = logging.getLogger(__name__)
_CHROMADB_MODULE = None
_CHROMADB_ALLOWED_ENV_KEYS = {
    "CURL_CA_BUNDLE",
    "HOME",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LOGNAME",
    "NO_PROXY",
    "PATH",
    "PYTHONPATH",
    "REQUESTS_CA_BUNDLE",
    "SHELL",
    "SSL_CERT_DIR",
    "SSL_CERT_FILE",
    "TEMP",
    "TMP",
    "TMPDIR",
    "USER",
    "VIRTUAL_ENV",
    "http_proxy",
    "https_proxy",
    "no_proxy",
}
_CHROMADB_ALLOWED_ENV_PREFIXES = ("CHROMA_", "chroma_", "LC_")


EMBEDDING_DIMENSION = 64
WORD_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")
CJK_TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]+")


def _normalize_chroma_client_mode(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "persistent":
        return "persistent"
    return "http"


def _is_chromadb_safe_env_key(key: str) -> bool:
    if key in _CHROMADB_ALLOWED_ENV_KEYS:
        return True
    return any(key.startswith(prefix) for prefix in _CHROMADB_ALLOWED_ENV_PREFIXES)


@contextmanager
def _isolated_chromadb_settings_env():
    original_cwd = os.getcwd()
    original_env = os.environ.copy()
    original_base_settings_init = BaseSettings.__init__

    def _patched_base_settings_init(instance, *args, **kwargs):
        if instance.__class__.__module__.startswith("chromadb.") and "_env_file" not in kwargs:
            kwargs["_env_file"] = None
        return original_base_settings_init(instance, *args, **kwargs)

    safe_env = {
        key: value for key, value in original_env.items() if _is_chromadb_safe_env_key(key)
    }

    try:
        BaseSettings.__init__ = _patched_base_settings_init
        os.environ.clear()
        os.environ.update(safe_env)
        os.chdir(tempfile.gettempdir())
        yield
    finally:
        BaseSettings.__init__ = original_base_settings_init
        os.environ.clear()
        os.environ.update(original_env)
        os.chdir(original_cwd)


def _load_chromadb_module():
    global _CHROMADB_MODULE

    if _CHROMADB_MODULE is not None:
        return _CHROMADB_MODULE

    try:
        with _isolated_chromadb_settings_env():
            # chromadb may read the current working directory's `.env` and process
            # environment during import. Import it from a neutral environment so our
            # deployment variables do not leak into chromadb's BaseSettings.
            import chromadb as chromadb_module  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on runtime environment
        raise RuntimeError(f"chromadb import failed: {exc}") from exc

    _CHROMADB_MODULE = chromadb_module
    return _CHROMADB_MODULE


class HashingTextEmbeddingFunction:
    def __init__(self, dimension: int = EMBEDDING_DIMENSION) -> None:
        self.dimension = dimension

    def embed(self, text: str, keywords: list[str] | None = None) -> list[float]:
        vector = [0.0] * self.dimension
        weighted_tokens = self._tokenize(text)
        for token in keywords or []:
            weighted_tokens.extend([token.lower()] * 2)

        if not weighted_tokens:
            return vector

        for token in weighted_tokens:
            slot = hash(token) % self.dimension
            vector[slot] += 1.0

        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude <= 0:
            return vector
        return [round(value / magnitude, 8) for value in vector]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        normalized = re.sub(r"\s+", " ", text.lower()).strip()
        if not normalized:
            return []

        tokens = WORD_TOKEN_PATTERN.findall(normalized)
        for segment in CJK_TOKEN_PATTERN.findall(normalized):
            if len(segment) <= 1:
                tokens.append(segment)
                continue
            tokens.extend(segment[index : index + 2] for index in range(len(segment) - 1))
        return [token for token in tokens if token]


class LocalPersistentChromaCollection:
    def __init__(self, connection: sqlite3.Connection, collection_name: str) -> None:
        self._connection = connection
        self._collection_name = collection_name
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS long_term_memory (
                collection_name TEXT NOT NULL,
                memory_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                embedding_json TEXT NOT NULL,
                document TEXT,
                metadata_json TEXT,
                PRIMARY KEY (collection_name, memory_id)
            )
            """
        )
        self._connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_long_term_memory_collection_user
            ON long_term_memory (collection_name, user_id)
            """
        )
        self._connection.commit()

    def upsert(self, ids, embeddings, documents, metadatas) -> None:
        rows = []
        for memory_id, embedding, document, metadata in zip(ids, embeddings, documents, metadatas):
            payload = metadata if isinstance(metadata, dict) else {}
            rows.append(
                (
                    self._collection_name,
                    str(memory_id),
                    str(payload.get("user_id") or ""),
                    json.dumps(embedding),
                    document,
                    json.dumps(payload),
                )
            )
        self._connection.executemany(
            """
            INSERT INTO long_term_memory (
                collection_name,
                memory_id,
                user_id,
                embedding_json,
                document,
                metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(collection_name, memory_id) DO UPDATE SET
                user_id=excluded.user_id,
                embedding_json=excluded.embedding_json,
                document=excluded.document,
                metadata_json=excluded.metadata_json
            """,
            rows,
        )
        self._connection.commit()

    @staticmethod
    def _matches_where(metadata: dict[str, Any], where: dict[str, Any] | None) -> bool:
        if not where:
            return True
        for key, value in where.items():
            if value is None:
                continue
            if str(metadata.get(key) or "") != str(value):
                return False
        return True

    def get(self, where, include):
        rows = self._connection.execute(
            """
            SELECT memory_id, document, metadata_json
            FROM long_term_memory
            WHERE collection_name = ?
            ORDER BY memory_id
            """,
            (self._collection_name,),
        ).fetchall()
        filtered_rows = []
        for row in rows:
            metadata = json.loads(row[2]) if row[2] else {}
            if self._matches_where(metadata, where):
                filtered_rows.append((row[0], row[1], metadata))
        return {
            "ids": [row[0] for row in filtered_rows],
            "documents": [row[1] for row in filtered_rows],
            "metadatas": [row[2] for row in filtered_rows],
            "include": include,
        }

    def delete(self, ids=None, where=None) -> None:
        normalized_ids = [str(memory_id).strip() for memory_id in (ids or []) if str(memory_id).strip()]
        if not normalized_ids and where:
            result = self.get(where=where, include=[])
            normalized_ids = [
                str(memory_id).strip()
                for memory_id in (result.get("ids") or [])
                if str(memory_id).strip()
            ]
        if not normalized_ids:
            return
        self._connection.executemany(
            """
            DELETE FROM long_term_memory
            WHERE collection_name = ? AND memory_id = ?
            """,
            [(self._collection_name, memory_id) for memory_id in normalized_ids],
        )
        self._connection.commit()

    @staticmethod
    def _distance(left: list[float], right: list[float]) -> float:
        return sum((lval - rval) ** 2 for lval, rval in zip(left, right))

    def query(self, query_embeddings, n_results, where, include):
        query_embedding = query_embeddings[0]
        rows = self._connection.execute(
            """
            SELECT memory_id, embedding_json, document, metadata_json
            FROM long_term_memory
            WHERE collection_name = ?
            """,
            (self._collection_name,),
        ).fetchall()
        scored = []
        for memory_id, embedding_json, document, metadata_json in rows:
            embedding = json.loads(embedding_json) if embedding_json else []
            metadata = json.loads(metadata_json) if metadata_json else {}
            if not self._matches_where(metadata, where):
                continue
            scored.append(
                (
                    self._distance(query_embedding, embedding),
                    memory_id,
                    document,
                    metadata,
                )
            )
        scored.sort(key=lambda item: item[0])
        top = scored[: max(1, n_results)]
        return {
            "ids": [[row[1] for row in top]],
            "documents": [[row[2] for row in top]],
            "metadatas": [[row[3] for row in top]],
            "distances": [[row[0] for row in top]],
            "include": include,
        }


class LocalPersistentChromaClient:
    def __init__(self, path: str) -> None:
        self._db_path = self._resolve_db_path(path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self._db_path)

    @staticmethod
    def _resolve_db_path(path: str) -> Path:
        candidate = Path(path).expanduser()
        if candidate.suffix.lower() in {".sqlite", ".sqlite3", ".db"}:
            return candidate
        return candidate / "long_term_memory.sqlite3"

    def get_or_create_collection(self, name: str):
        return LocalPersistentChromaCollection(self._connection, name)

    def delete_collection(self, name: str) -> None:
        self._connection.execute(
            "DELETE FROM long_term_memory WHERE collection_name = ?",
            (name,),
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()


class ChromaLongTermMemoryStore:
    def __init__(
        self,
        *,
        chroma_url: str | None = None,
        chroma_client_mode: str | None = None,
        chroma_persist_path: str | None = None,
        collection_name: str | None = None,
        embedding_function: HashingTextEmbeddingFunction | None = None,
        client_factory_override=None,
    ) -> None:
        settings = get_settings()
        self.chroma_url = chroma_url or settings.chroma_url
        self.chroma_client_mode = _normalize_chroma_client_mode(
            chroma_client_mode or settings.chroma_client_mode
        )
        self.chroma_persist_path = chroma_persist_path or settings.chroma_persist_path
        self.collection_name = collection_name or settings.chroma_collection_name
        self.embedding_function = embedding_function or HashingTextEmbeddingFunction()
        self._client_factory_override = client_factory_override
        self._client = None
        self._collection = None
        self._warned_unavailable = False

    def _build_client(self):
        if self._client_factory_override is not None:
            return self._client_factory_override()

        if self.chroma_client_mode == "persistent":
            persist_path = str(self.chroma_persist_path or "data/chroma").strip() or "data/chroma"
            return LocalPersistentChromaClient(path=persist_path)

        chromadb = _load_chromadb_module()
        parsed = urlparse(self.chroma_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 8000
        ssl = parsed.scheme == "https"
        with _isolated_chromadb_settings_env():
            return chromadb.HttpClient(host=host, port=port, ssl=ssl)

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            self._client = self._build_client()
            self._warned_unavailable = False
            return self._client
        except Exception as exc:  # pragma: no cover - depends on runtime environment
            if not self._warned_unavailable:
                logger.warning("Chroma long-term memory disabled, using in-memory fallback: %s", exc)
                self._warned_unavailable = True
            self._client = None
            return None

    def _get_collection(self):
        if self._collection is not None:
            return self._collection
        client = self._get_client()
        if client is None:
            return None
        try:
            self._collection = client.get_or_create_collection(name=self.collection_name)
            self._warned_unavailable = False
            return self._collection
        except Exception as exc:  # pragma: no cover - depends on runtime environment
            if not self._warned_unavailable:
                logger.warning("Chroma collection unavailable, using in-memory fallback: %s", exc)
                self._warned_unavailable = True
            self._collection = None
            return None

    @staticmethod
    def _to_metadata(memory: dict) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "user_id": memory["user_id"],
            "source_mid_term_id": memory["source_mid_term_id"],
            "memory_type": memory.get("memory_type", "session_summary"),
            "summary": encryption_service.encrypt_text(
                str(memory.get("summary") or "")
            ),
            "created_at": memory["created_at"],
            "keywords_json": encryption_service.encrypt_text(
                json.dumps(memory.get("keywords", []), ensure_ascii=False)
            ),
            "memory_scope": memory.get("memory_scope", "tenant"),
            "memory_layer_kind": memory.get("memory_layer_kind", "conversation"),
            "write_source": memory.get("write_source", "brain_internal"),
            "trust_level": memory.get("trust_level", "trusted"),
            "memory_status": memory.get("memory_status", "active"),
            "review_status": memory.get("review_status", "approved"),
            "reviewed_by": memory.get("reviewed_by"),
            "reviewed_at": memory.get("reviewed_at"),
            "review_note": memory.get("review_note"),
            "tenant_id": memory.get("tenant_id", "default"),
            "project_id": memory.get("project_id", "default"),
            "environment": memory.get("environment", "development"),
            "expires_at": memory.get("expires_at"),
            "archived_at": memory.get("archived_at"),
            "deleted_at": memory.get("deleted_at"),
            "corrected_at": memory.get("corrected_at"),
            "retention_policy": memory.get("retention_policy", "default"),
            "local_only_reasons_json": encryption_service.encrypt_text(
                json.dumps(memory.get("local_only_reasons", []), ensure_ascii=False)
            ),
            "local_only_filtered_count": int(memory.get("local_only_filtered_count") or 0),
        }
        return metadata

    @staticmethod
    def _from_record(memory_id: str, document: str | None, metadata: dict[str, Any] | None) -> dict:
        payload = metadata or {}
        decrypted_summary = encryption_service.decrypt_text(str(payload.get("summary") or ""))
        decrypted_memory_text = encryption_service.decrypt_text(str(document or ""))
        decoded_keywords = str(
            encryption_service.decrypt_text(str(payload.get("keywords_json") or "[]")) or "[]"
        )
        try:
            keywords = json.loads(decoded_keywords)
            if not isinstance(keywords, list):
                keywords = []
        except Exception:
            keywords = []
        decoded_local_only_reasons = str(
            encryption_service.decrypt_text(str(payload.get("local_only_reasons_json") or "[]")) or "[]"
        )
        try:
            local_only_reasons = json.loads(decoded_local_only_reasons)
            if not isinstance(local_only_reasons, list):
                local_only_reasons = []
        except Exception:
            local_only_reasons = []
        return {
            "id": memory_id,
            "user_id": payload.get("user_id", ""),
            "source_mid_term_id": payload.get("source_mid_term_id", ""),
            "memory_type": payload.get("memory_type", "session_summary"),
            "summary": decrypted_summary,
            "memory_text": decrypted_memory_text or "",
            "keywords": keywords,
            "created_at": payload.get("created_at", ""),
            "memory_scope": payload.get("memory_scope", "tenant"),
            "memory_layer_kind": payload.get("memory_layer_kind", "conversation"),
            "write_source": payload.get("write_source", "brain_internal"),
            "trust_level": payload.get("trust_level", "trusted"),
            "memory_status": payload.get("memory_status", "active"),
            "review_status": payload.get("review_status", "approved"),
            "reviewed_by": payload.get("reviewed_by"),
            "reviewed_at": payload.get("reviewed_at"),
            "review_note": payload.get("review_note"),
            "tenant_id": payload.get("tenant_id", "default"),
            "project_id": payload.get("project_id", "default"),
            "environment": payload.get("environment", "development"),
            "expires_at": payload.get("expires_at"),
            "archived_at": payload.get("archived_at"),
            "deleted_at": payload.get("deleted_at"),
            "corrected_at": payload.get("corrected_at"),
            "retention_policy": payload.get("retention_policy", "default"),
            "local_only_reasons": local_only_reasons,
            "local_only_filtered_count": int(payload.get("local_only_filtered_count") or 0),
        }

    def save_memory(self, memory: dict) -> bool:
        collection = self._get_collection()
        if collection is None:
            return False

        try:
            collection.upsert(
                ids=[memory["id"]],
                embeddings=[self.embedding_function.embed(memory["memory_text"], memory.get("keywords", []))],
                documents=[str(encryption_service.encrypt_text(str(memory["memory_text"])))],
                metadatas=[self._to_metadata(memory)],
            )
            self._warned_unavailable = False
            return True
        except Exception as exc:  # pragma: no cover - depends on runtime environment
            logger.warning("Chroma long-term memory write failed, using in-memory fallback: %s", exc)
            return False

    def list_memories(self, user_id: str, filters: dict[str, Any] | None = None) -> list[dict] | None:
        collection = self._get_collection()
        if collection is None:
            return None

        try:
            where = {"user_id": user_id, **(filters or {})}
            result = collection.get(where=where, include=["documents", "metadatas"])
            ids = result.get("ids") or []
            documents = result.get("documents") or []
            metadatas = result.get("metadatas") or []
            items = [
                self._from_record(
                    memory_id=memory_id,
                    document=documents[index] if index < len(documents) else None,
                    metadata=metadatas[index] if index < len(metadatas) else None,
                )
                for index, memory_id in enumerate(ids)
            ]
            items.sort(key=lambda item: (item.get("created_at", ""), item["id"]))
            return items
        except Exception as exc:  # pragma: no cover - depends on runtime environment
            logger.warning("Chroma long-term memory read failed, using in-memory fallback: %s", exc)
            return None

    def query_memories(
        self,
        user_id: str,
        query: str,
        limit: int,
        filters: dict[str, Any] | None = None,
    ) -> list[dict] | None:
        collection = self._get_collection()
        if collection is None:
            return None

        try:
            query_tokens: list[str] = []
            seen_query_tokens: set[str] = set()
            for token in self.embedding_function._tokenize(query):
                if token in seen_query_tokens:
                    continue
                seen_query_tokens.add(token)
                query_tokens.append(token)

            result = collection.query(
                query_embeddings=[self.embedding_function.embed(query)],
                n_results=max(1, limit),
                where={"user_id": user_id, **(filters or {})},
                include=["documents", "metadatas", "distances"],
            )
            ids = (result.get("ids") or [[]])[0]
            documents = (result.get("documents") or [[]])[0]
            metadatas = (result.get("metadatas") or [[]])[0]
            distances = (result.get("distances") or [[]])[0]

            items: list[dict] = []
            for index, memory_id in enumerate(ids):
                record = self._from_record(
                    memory_id=memory_id,
                    document=documents[index] if index < len(documents) else None,
                    metadata=metadatas[index] if index < len(metadatas) else None,
                )
                distance = float(distances[index]) if index < len(distances) else 1.0
                vector_score = round(1.0 / (1.0 + max(distance, 0.0)), 4)
                lexical_text = " ".join(
                    [
                        str(record.get("memory_text") or ""),
                        str(record.get("summary") or ""),
                        " ".join(str(keyword) for keyword in (record.get("keywords") or [])),
                    ]
                )
                lexical_terms = set(self.embedding_function._tokenize(lexical_text))
                matched_terms = [term for term in query_tokens if term in lexical_terms][:8]
                items.append(
                    {
                        "memory_id": record["id"],
                        "source_mid_term_id": record["source_mid_term_id"],
                        "memory_type": record.get("memory_type", "session_summary"),
                        "memory_text": record["memory_text"],
                        "summary": record.get("summary"),
                        "keywords": record.get("keywords", []),
                        "score": vector_score,
                        "vector_score": vector_score,
                        "distance": round(distance, 8),
                        "matched_terms": matched_terms,
                        "created_at": record["created_at"],
                        "retention_policy": record.get("retention_policy", "default"),
                        "local_only_reasons": record.get("local_only_reasons", []),
                        "local_only_filtered_count": int(
                            record.get("local_only_filtered_count") or 0
                        ),
                    }
                )
            return items
        except Exception as exc:  # pragma: no cover - depends on runtime environment
            logger.warning("Chroma long-term memory query failed, using in-memory fallback: %s", exc)
            return None

    def delete_memories(
        self,
        *,
        tenant_id: str | None = None,
        user_ids: list[str] | tuple[str, ...] | set[str] | None = None,
    ) -> int:
        collection = self._get_collection()
        if collection is None:
            return 0

        normalized_tenant_id = str(tenant_id or "").strip()
        normalized_user_ids = [
            str(user_id).strip()
            for user_id in (user_ids or [])
            if str(user_id).strip()
        ]
        if not normalized_tenant_id and not normalized_user_ids:
            return 0

        delete_records = getattr(collection, "delete", None)
        if delete_records is None:
            return 0

        candidate_ids: set[str] = set()
        try:
            if normalized_tenant_id:
                tenant_result = collection.get(where={"tenant_id": normalized_tenant_id}, include=["metadatas"])
                candidate_ids.update(
                    str(memory_id).strip()
                    for memory_id in (tenant_result.get("ids") or [])
                    if str(memory_id).strip()
                )

            for user_id in normalized_user_ids:
                user_result = collection.get(where={"user_id": user_id}, include=["metadatas"])
                candidate_ids.update(
                    str(memory_id).strip()
                    for memory_id in (user_result.get("ids") or [])
                    if str(memory_id).strip()
                )

            if not candidate_ids:
                return 0

            delete_records(ids=sorted(candidate_ids))
            self._warned_unavailable = False
            return len(candidate_ids)
        except Exception as exc:  # pragma: no cover - depends on runtime environment
            logger.warning("Chroma long-term memory delete failed, using in-memory fallback: %s", exc)
            return 0

    def clear(self) -> None:
        client = self._get_client()
        if client is None:
            return
        try:
            client.delete_collection(name=self.collection_name)
        except Exception:
            pass
        self._collection = None

    def close(self) -> None:
        if self._client is not None and hasattr(self._client, "close"):
            try:
                self._client.close()
            except Exception:  # pragma: no cover - defensive shutdown path
                pass
        self._client = None
        self._collection = None


chroma_long_term_memory_store = ChromaLongTermMemoryStore()
