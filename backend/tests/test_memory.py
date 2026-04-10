from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.services.memory_service import MemoryService
from app.services import workflow_service


client = TestClient(app)


class NoRedisProvider:
    def get_client(self):
        return None


class NoopMidTermStore:
    def list_summaries(self, user_id: str):
        _ = user_id
        return None

    def save_summary(self, summary: dict) -> bool:
        _ = summary
        return False

    def clear(self) -> None:
        return None


class NoopLongTermStore:
    def list_memories(self, user_id: str):
        _ = user_id
        return None

    def query_memories(self, user_id: str, query: str, limit: int):
        _ = (user_id, query, limit)
        return None

    def save_memory(self, memory: dict) -> bool:
        _ = memory
        return False

    def clear(self) -> None:
        return None

    def close(self) -> None:
        return None


class VectorOnlyLongTermStore(NoopLongTermStore):
    def query_memories(self, user_id: str, query: str, limit: int):
        _ = (user_id, query, limit)
        return [
            {
                "memory_id": "lng-vector-only-1",
                "source_mid_term_id": "mid-vector-only",
                "memory_type": "session_summary",
                "memory_text": "project retrospective archive",
                "summary": "retrospective archive",
                "keywords": ["project", "archive"],
                "score": 0.92,
                "vector_score": 0.92,
                "distance": 0.08695652,
                "matched_terms": [],
                "created_at": "2026-04-03T09:00:00+00:00",
            }
        ]


class FakeRawMessageStore:
    def __init__(self) -> None:
        self.items: list[dict] = []
        self.session_states: dict[tuple[str, str], dict] = {}

    def append_conversation_message(self, payload: dict) -> bool:
        self.items.append(dict(payload))
        return True

    def list_conversation_messages(
        self,
        *,
        user_id: str,
        session_id: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        items = [item for item in self.items if item["user_id"] == user_id]
        if session_id is not None:
            items = [item for item in items if item["session_id"] == session_id]
        items = sorted(items, key=lambda item: (item["created_at"], item["id"]))
        if limit is not None:
            items = items[-limit:]
        return [dict(item) for item in items]

    def get_memory_session_state(
        self,
        *,
        user_id: str,
        session_id: str,
    ) -> dict | None:
        state = self.session_states.get((user_id, session_id))
        return dict(state) if state is not None else None

    def upsert_memory_session_state(self, payload: dict) -> bool:
        key = (str(payload["user_id"]), str(payload["session_id"]))
        self.session_states[key] = dict(payload)
        return True


def _build_memory_service(
    *,
    session_idle_seconds: int = 900,
    weekly_distill_seconds: int = 604800,
    raw_message_store_override=None,
) -> MemoryService:
    return MemoryService(
        redis_provider_override=NoRedisProvider(),
        mid_term_store_override=NoopMidTermStore(),
        long_term_store_override=NoopLongTermStore(),
        raw_message_store_override=raw_message_store_override,
        session_idle_seconds_override=session_idle_seconds,
        weekly_distill_seconds_override=weekly_distill_seconds,
    )


def test_memory_layers_distill_and_retrieve(auth_headers) -> None:
    first = client.post(
        "/api/memory/messages",
        json={
            "userId": "telegram:memory-user",
            "sessionId": "session-a",
            "role": "user",
            "content": "请记录我偏好中文回复，并且每周一发送安全周报",
            "detectedLang": "zh",
        },
        headers=auth_headers,
    )
    second = client.post(
        "/api/memory/messages",
        json={
            "userId": "telegram:memory-user",
            "sessionId": "session-a",
            "role": "assistant",
            "content": "好的，我会优先中文，并整理周报提醒。",
            "detectedLang": "zh",
        },
        headers=auth_headers,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["autoWeeklyDistilled"] is False
    assert second.json()["autoWeeklyDistilled"] is False

    layers = client.get("/api/memory/telegram:memory-user/layers", headers=auth_headers)
    assert layers.status_code == 200
    assert layers.json()["shortTermCount"] == 2

    distill = client.post(
        "/api/memory/telegram:memory-user/distill",
        json={"trigger": "session_end", "sessionId": "session-a"},
        headers=auth_headers,
    )
    assert distill.status_code == 200
    body = distill.json()
    assert body["created"] is True
    assert body["midTerm"]["sourceCount"] == 2
    assert body["midTerm"]["preferences"]
    assert body["longTerm"]["sourceMidTermId"] == body["midTerm"]["id"]
    assert body["longTerm"]["memoryType"] == "session_summary"
    assert body["longTermItems"]
    assert {"session_summary", "user_preference", "agent_decision"} <= {
        item["memoryType"] for item in body["longTermItems"]
    }

    retrieve = client.get(
        "/api/memory/telegram:memory-user/retrieve",
        params={"query": "中文周报提醒", "limit": 5},
        headers=auth_headers,
    )
    assert retrieve.status_code == 200
    retrieve_body = retrieve.json()
    assert retrieve_body["total"] >= 1
    assert "memoryText" in retrieve_body["items"][0]
    assert any(
        item["sourceMidTermId"] == body["midTerm"]["id"]
        for item in retrieve_body["items"]
    )


def test_memory_service_auto_distills_idle_session_on_rollover() -> None:
    service = _build_memory_service(session_idle_seconds=60)
    base_time = datetime(2026, 4, 3, 8, 0, tzinfo=UTC)
    timestamps = [
        base_time,
        base_time + timedelta(seconds=20),
        base_time + timedelta(seconds=130),
        base_time + timedelta(seconds=130),
        base_time + timedelta(seconds=130),
    ]

    def fake_now() -> datetime:
        return timestamps.pop(0) if timestamps else base_time + timedelta(seconds=130)

    service._now = fake_now

    first = service.ingest_message(
        user_id="telegram:rollover-user",
        session_id="session-rollover",
        role="user",
        content="请记住我偏好中文回复，并在每周一提醒我看安全周报。",
        detected_lang="zh",
    )
    second = service.ingest_message(
        user_id="telegram:rollover-user",
        session_id="session-rollover",
        role="assistant",
        content="好的，后续我会优先中文，并继续保留周报提醒。",
        detected_lang="zh",
    )
    third = service.ingest_message(
        user_id="telegram:rollover-user",
        session_id="session-rollover",
        role="user",
        content="新一轮对话开始了，请继续帮我整理今天的更新。",
        detected_lang="zh",
    )

    layers = service.get_layers("telegram:rollover-user")

    assert first["auto_distilled_sessions"] == []
    assert second["auto_distilled_sessions"] == []
    assert third["auto_distilled_sessions"] == ["session-rollover"]
    assert first["auto_weekly_distilled"] is False
    assert second["auto_weekly_distilled"] is False
    assert third["auto_weekly_distilled"] is False
    assert layers["short_term_count"] == 1
    assert layers["mid_term_count"] == 1
    assert layers["long_term_count"] >= 3
    assert any(item["memory_type"] == "session_summary" for item in layers["long_term"])
    assert layers["mid_term"][0]["trigger"] == "session_rollover"


def test_memory_service_auto_weekly_distills_current_session_before_appending_new_message() -> None:
    raw_store = FakeRawMessageStore()
    service = _build_memory_service(
        raw_message_store_override=raw_store,
        session_idle_seconds=10 * 24 * 60 * 60,
        weekly_distill_seconds=7 * 24 * 60 * 60,
    )
    base_time = datetime(2026, 4, 1, 8, 0, tzinfo=UTC)
    current_time = base_time

    def fake_now() -> datetime:
        return current_time

    service._now = fake_now

    first = service.ingest_message(
        user_id="telegram:weekly-memory-user",
        session_id="session-weekly",
        role="user",
        content="请记住我偏好中文回复，并每周同步一次项目风险。",
        detected_lang="zh",
    )
    current_time = base_time + timedelta(minutes=10)
    second = service.ingest_message(
        user_id="telegram:weekly-memory-user",
        session_id="session-weekly",
        role="assistant",
        content="好的，我会优先中文，并保留每周风险同步。",
        detected_lang="zh",
    )
    current_time = base_time + timedelta(days=8)
    third = service.ingest_message(
        user_id="telegram:weekly-memory-user",
        session_id="session-weekly",
        role="user",
        content="这是第八天的新消息，请继续跟进本周计划。",
        detected_lang="zh",
    )

    layers = service.get_layers("telegram:weekly-memory-user")

    assert first["auto_weekly_distilled"] is False
    assert second["auto_weekly_distilled"] is False
    assert third["auto_weekly_distilled"] is True
    assert third["auto_distilled_sessions"] == []
    assert third["short_term_count"] == 1
    assert third["item"]["content"] == "这是第八天的新消息，请继续跟进本周计划。"
    assert layers["short_term_count"] == 1
    assert [item["content"] for item in layers["short_term"]] == ["这是第八天的新消息，请继续跟进本周计划。"]
    assert layers["mid_term_count"] == 1
    assert layers["long_term_count"] >= 3
    assert any(item["memory_type"] == "session_summary" for item in layers["long_term"])
    assert layers["mid_term"][0]["trigger"] == "weekly"
    assert layers["mid_term"][0]["source_count"] == 2


def test_memory_service_does_not_auto_weekly_distill_before_interval() -> None:
    raw_store = FakeRawMessageStore()
    service = _build_memory_service(
        raw_message_store_override=raw_store,
        session_idle_seconds=10 * 24 * 60 * 60,
        weekly_distill_seconds=7 * 24 * 60 * 60,
    )
    base_time = datetime(2026, 4, 1, 8, 0, tzinfo=UTC)
    current_time = base_time

    def fake_now() -> datetime:
        return current_time

    service._now = fake_now

    service.ingest_message(
        user_id="telegram:weekly-memory-pending-user",
        session_id="session-weekly-pending",
        role="user",
        content="请记住我偏好中文回复，并每周同步一次项目风险。",
        detected_lang="zh",
    )
    current_time = base_time + timedelta(minutes=10)
    service.ingest_message(
        user_id="telegram:weekly-memory-pending-user",
        session_id="session-weekly-pending",
        role="assistant",
        content="好的，我会优先中文，并保留每周风险同步。",
        detected_lang="zh",
    )
    current_time = base_time + timedelta(days=6)
    third = service.ingest_message(
        user_id="telegram:weekly-memory-pending-user",
        session_id="session-weekly-pending",
        role="user",
        content="还没到一周，先继续当前对话。",
        detected_lang="zh",
    )

    layers = service.get_layers("telegram:weekly-memory-pending-user")

    assert third["auto_weekly_distilled"] is False
    assert layers["mid_term_count"] == 0
    assert layers["long_term_count"] == 0
    assert layers["short_term_count"] >= 1
    assert layers["short_term"][-1]["content"] == "还没到一周，先继续当前对话。"


def test_memory_service_distill_builds_structured_summary() -> None:
    service = _build_memory_service()
    service.ingest_message(
        user_id="telegram:structured-memory-user",
        session_id="session-structured",
        role="user",
        content="请记住我偏好中文回复，并且每周一发送安全周报提醒。",
        detected_lang="zh",
    )
    service.ingest_message(
        user_id="telegram:structured-memory-user",
        session_id="session-structured",
        role="assistant",
        content="好的，后续我会优先中文，并把周报提醒安排到每周一。",
        detected_lang="zh",
    )

    result = service.distill(
        user_id="telegram:structured-memory-user",
        trigger="session_end",
        session_id="session-structured",
    )

    assert result["created"] is True
    assert result["mid_term"]["preferences"]
    assert result["mid_term"]["decisions"]
    assert "偏好：" in result["mid_term"]["summary"]
    assert "决策：" in result["mid_term"]["summary"]
    assert result["long_term"]["memory_type"] == "session_summary"
    assert "偏好：" in result["long_term"]["memory_text"]
    assert {"session_summary", "user_preference", "agent_decision"} <= {
        item["memory_type"] for item in result["long_term_items"]
    }


def test_memory_service_distill_dedupes_preference_variants() -> None:
    service = _build_memory_service()
    service.ingest_message(
        user_id="telegram:dedupe-pref-user",
        session_id="session-dedupe-pref",
        role="user",
        content="请记住我偏好中文回复，并每周一发送安全周报提醒。",
        detected_lang="zh",
    )
    service.ingest_message(
        user_id="telegram:dedupe-pref-user",
        session_id="session-dedupe-pref",
        role="user",
        content="请记住 我 偏好 中文 回复，并每周一发送安全周报提醒！",
        detected_lang="zh",
    )
    service.ingest_message(
        user_id="telegram:dedupe-pref-user",
        session_id="session-dedupe-pref",
        role="assistant",
        content="好的，我会优先中文回复，并保留每周一周报提醒。",
        detected_lang="zh",
    )

    result = service.distill(
        user_id="telegram:dedupe-pref-user",
        trigger="session_end",
        session_id="session-dedupe-pref",
    )

    assert result["created"] is True
    assert len(result["mid_term"]["preferences"]) == 1
    assert result["mid_term"]["preferences"][0].startswith("请记住")


def test_memory_service_distill_emits_internal_workflow_event_after_success(
    monkeypatch,
) -> None:
    service = _build_memory_service()
    emitted: list[dict] = []

    def fake_trigger_workflow_internal(
        event_name: str,
        payload: dict | None = None,
        *,
        source: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        emitted.append(
            {
                "event_name": event_name,
                "payload": dict(payload or {}),
                "source": source,
                "idempotency_key": idempotency_key,
            }
        )
        return {"ok": True, "run_id": "run-memory-distilled"}

    monkeypatch.setattr(workflow_service, "has_internal_event_subscribers", lambda event_name: True)
    monkeypatch.setattr(workflow_service, "trigger_workflow_internal", fake_trigger_workflow_internal)

    service.ingest_message(
        user_id="telegram:memory-event-user",
        session_id="session-memory-event",
        role="user",
        content="请记住我偏好中文回复，并在每周一整理安全周报。",
        detected_lang="zh",
    )
    service.ingest_message(
        user_id="telegram:memory-event-user",
        session_id="session-memory-event",
        role="assistant",
        content="好的，我会优先中文，并保留周报整理提醒。",
        detected_lang="zh",
    )

    result = service.distill(
        user_id="telegram:memory-event-user",
        trigger="session_end",
        session_id="session-memory-event",
    )

    assert result["created"] is True
    assert emitted == [
        {
            "event_name": "memory.distilled",
            "payload": {
                "userId": "telegram:memory-event-user",
                "sessionId": "session-memory-event",
                "trigger": "session_end",
                "midTermId": result["mid_term"]["id"],
                "longTermId": result["long_term"]["id"],
                "longTermIds": [item["id"] for item in result["long_term_items"]],
                "longTermCount": len(result["long_term_items"]),
                "memoryTypes": [item["memory_type"] for item in result["long_term_items"]],
                "sourceCount": 2,
                "keywords": result["mid_term"]["keywords"][:6],
            },
            "source": "Memory Service",
            "idempotency_key": (
                f"memory.distilled:{result['mid_term']['id']}:{result['long_term']['id']}"
            ),
        }
    ]


def test_memory_service_distill_is_fail_open_when_internal_event_trigger_fails(
    monkeypatch,
) -> None:
    service = _build_memory_service()

    def failing_trigger_workflow_internal(
        event_name: str,
        payload: dict | None = None,
        *,
        source: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        _ = (event_name, payload, source, idempotency_key)
        raise RuntimeError("workflow bus unavailable")

    monkeypatch.setattr(workflow_service, "trigger_workflow_internal", failing_trigger_workflow_internal)

    service.ingest_message(
        user_id="telegram:memory-fail-open-user",
        session_id="session-memory-fail-open",
        role="user",
        content="请记住我偏好英文回复，并在每周五整理项目风险。",
        detected_lang="zh",
    )
    service.ingest_message(
        user_id="telegram:memory-fail-open-user",
        session_id="session-memory-fail-open",
        role="assistant",
        content="好的，后续我会优先英文，并保留每周五的风险整理提醒。",
        detected_lang="zh",
    )

    result = service.distill(
        user_id="telegram:memory-fail-open-user",
        trigger="session_end",
        session_id="session-memory-fail-open",
    )

    assert result["created"] is True
    assert result["mid_term"]["source_count"] == 2
    assert result["long_term"]["source_mid_term_id"] == result["mid_term"]["id"]


def test_memory_service_distill_skips_internal_event_when_no_workflow_subscribers(
    monkeypatch,
) -> None:
    service = _build_memory_service()
    triggered: list[str] = []

    monkeypatch.setattr(workflow_service, "has_internal_event_subscribers", lambda event_name: False)
    monkeypatch.setattr(
        workflow_service,
        "trigger_workflow_internal",
        lambda *args, **kwargs: triggered.append("called") or {"ok": True},
    )

    service.ingest_message(
        user_id="telegram:memory-no-subscriber-user",
        session_id="session-memory-no-subscriber",
        role="user",
        content="请记住我偏好中文回复。",
        detected_lang="zh",
    )
    service.ingest_message(
        user_id="telegram:memory-no-subscriber-user",
        session_id="session-memory-no-subscriber",
        role="assistant",
        content="好的，我会优先中文。",
        detected_lang="zh",
    )

    result = service.distill(
        user_id="telegram:memory-no-subscriber-user",
        trigger="session_end",
        session_id="session-memory-no-subscriber",
    )

    assert result["created"] is True
    assert triggered == []


def test_memory_service_distills_from_persisted_raw_messages_when_short_term_cache_is_cold() -> None:
    raw_store = FakeRawMessageStore()
    service = _build_memory_service(raw_message_store_override=raw_store)
    service.ingest_message(
        user_id="telegram:raw-log-user",
        session_id="session-raw-log",
        role="user",
        content="请记住我偏好英文回复，并在每周五整理项目风险。",
        detected_lang="zh",
    )
    service.ingest_message(
        user_id="telegram:raw-log-user",
        session_id="session-raw-log",
        role="assistant",
        content="好的，后续我会优先英文，并保留每周五的风险整理提醒。",
        detected_lang="zh",
    )

    assert len(raw_store.items) == 2

    service._short_term.clear()
    result = service.distill(
        user_id="telegram:raw-log-user",
        trigger="session_end",
        session_id="session-raw-log",
    )

    assert result["created"] is True
    assert result["mid_term"]["source_count"] == 2
    assert "偏好：" in result["mid_term"]["summary"]


def test_memory_service_does_not_rehydrate_already_distilled_messages_into_cold_short_term() -> None:
    raw_store = FakeRawMessageStore()
    service = _build_memory_service(raw_message_store_override=raw_store)
    service.ingest_message(
        user_id="telegram:raw-watermark-user",
        session_id="session-raw-watermark",
        role="user",
        content="请记住我偏好英文回复，并在每周五整理项目风险。",
        detected_lang="zh",
    )
    service.ingest_message(
        user_id="telegram:raw-watermark-user",
        session_id="session-raw-watermark",
        role="assistant",
        content="好的，后续我会优先英文，并保留每周五的风险整理提醒。",
        detected_lang="zh",
    )

    first_distill = service.distill(
        user_id="telegram:raw-watermark-user",
        trigger="session_end",
        session_id="session-raw-watermark",
    )
    service._short_term.clear()

    layers = service.get_layers("telegram:raw-watermark-user")
    second_distill = service.distill(
        user_id="telegram:raw-watermark-user",
        trigger="session_end",
        session_id="session-raw-watermark",
    )

    assert first_distill["created"] is True
    assert layers["short_term_count"] == 0
    assert layers["short_term"] == []
    assert second_distill["created"] is False
    assert second_distill["short_term_remaining"] == 0


def test_memory_service_lists_persisted_raw_messages_when_short_term_cache_is_cold() -> None:
    raw_store = FakeRawMessageStore()
    service = _build_memory_service(raw_message_store_override=raw_store)
    service.ingest_message(
        user_id="telegram:raw-list-user",
        session_id="session-raw-list",
        role="user",
        content="请记住我偏好中文回复。",
        detected_lang="zh",
    )
    service.ingest_message(
        user_id="telegram:raw-list-user",
        session_id="session-raw-list",
        role="assistant",
        content="好的，后续我会优先中文。",
        detected_lang="zh",
    )

    service._short_term.clear()
    listed = service.list_messages(
        "telegram:raw-list-user",
        session_id="session-raw-list",
        limit=10,
    )

    assert listed["total"] == 2
    assert [item["role"] for item in listed["items"]] == ["user", "assistant"]


def test_memory_service_layers_use_persisted_raw_messages_when_short_term_cache_is_cold() -> None:
    raw_store = FakeRawMessageStore()
    service = _build_memory_service(raw_message_store_override=raw_store)
    service.ingest_message(
        user_id="telegram:raw-layer-user",
        session_id="session-raw-layer",
        role="user",
        content="请记住我偏好中文回复。",
        detected_lang="zh",
    )
    service.ingest_message(
        user_id="telegram:raw-layer-user",
        session_id="session-raw-layer",
        role="assistant",
        content="好的，后续我会优先中文。",
        detected_lang="zh",
    )

    service._short_term.clear()
    layers = service.get_layers("telegram:raw-layer-user")

    assert layers["short_term_count"] == 2
    assert [item["role"] for item in layers["short_term"]] == ["user", "assistant"]


def test_memory_service_does_not_reload_already_distilled_raw_messages_after_restart() -> None:
    raw_store = FakeRawMessageStore()
    service = _build_memory_service(raw_message_store_override=raw_store)
    service.ingest_message(
        user_id="telegram:watermark-user",
        session_id="session-watermark",
        role="user",
        content="请记住我偏好中文回复，并整理每周安全周报。",
        detected_lang="zh",
    )
    service.ingest_message(
        user_id="telegram:watermark-user",
        session_id="session-watermark",
        role="assistant",
        content="好的，后续我会优先中文，并保留周报整理提醒。",
        detected_lang="zh",
    )

    distilled = service.distill(
        user_id="telegram:watermark-user",
        trigger="session_end",
        session_id="session-watermark",
    )
    fresh_service = _build_memory_service(raw_message_store_override=raw_store)
    layers = fresh_service.get_layers("telegram:watermark-user")
    listed = fresh_service.list_messages(
        "telegram:watermark-user",
        session_id="session-watermark",
        limit=10,
    )
    redistilled = fresh_service.distill(
        user_id="telegram:watermark-user",
        trigger="session_end",
        session_id="session-watermark",
    )

    assert distilled["created"] is True
    assert raw_store.get_memory_session_state(
        user_id="telegram:watermark-user",
        session_id="session-watermark",
    ) is not None
    assert layers["short_term_count"] == 0
    assert layers["short_term"] == []
    assert listed["total"] == 2
    assert [item["role"] for item in listed["items"]] == ["user", "assistant"]
    assert redistilled["created"] is False
    assert redistilled["short_term_remaining"] == 0


def test_memory_messages_route_lists_raw_conversation_messages(auth_headers) -> None:
    first = client.post(
        "/api/memory/messages",
        json={
            "userId": "telegram:memory-route-user",
            "sessionId": "session-route-a",
            "role": "user",
            "content": "请记住我偏好中文回复。",
            "detectedLang": "zh",
        },
        headers=auth_headers,
    )
    second = client.post(
        "/api/memory/messages",
        json={
            "userId": "telegram:memory-route-user",
            "sessionId": "session-route-a",
            "role": "assistant",
            "content": "好的，后续我会优先中文。",
            "detectedLang": "zh",
        },
        headers=auth_headers,
    )
    listed = client.get(
        "/api/memory/telegram:memory-route-user/messages",
        params={"sessionId": "session-route-a", "limit": 10},
        headers=auth_headers,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 2
    assert [item["role"] for item in body["items"]] == ["user", "assistant"]


def test_memory_service_retrieve_uses_dynamic_window_and_diversity_rerank() -> None:
    service = _build_memory_service()
    user_id = "telegram:retrieve-hybrid-user"
    base_time = datetime(2026, 4, 4, 8, 0, tzinfo=UTC)
    service._long_term[user_id] = []

    for index in range(8):
        source_mid_term_id = "mid-shared" if index < 4 else f"mid-{index}"
        service._long_term[user_id].append(
            {
                "id": f"lng-hybrid-{index}",
                "user_id": user_id,
                "source_mid_term_id": source_mid_term_id,
                "memory_type": "session_summary",
                "summary": "偏好中文，每周一安全周报提醒",
                "memory_text": f"请保持中文输出，并在每周一发送安全周报提醒（样本 {index}）",
                "keywords": ["中文", "周报", "安全", "每周一"],
                "created_at": (base_time + timedelta(minutes=index)).isoformat(),
            }
        )

    dynamic_result = service.retrieve(
        user_id=user_id,
        query="请继续中文安全周报每周一提醒",
        limit=5,
    )
    small_limit_result = service.retrieve(
        user_id=user_id,
        query="请继续中文安全周报每周一提醒",
        limit=3,
    )

    assert 5 <= dynamic_result["total"] <= 8
    assert dynamic_result["query_expanded_terms"]
    assert len({item["memory_id"] for item in dynamic_result["items"]}) == dynamic_result["total"]
    assert len({item["source_mid_term_id"] for item in dynamic_result["items"][:3]}) >= 2
    assert all("lexical_score" in item for item in dynamic_result["items"])
    assert all("phrase_hit_count" in item for item in dynamic_result["items"])
    assert all("matched_terms" in item for item in dynamic_result["items"])
    assert all(isinstance(item["lexical_score"], float) for item in dynamic_result["items"])
    assert all(isinstance(item["phrase_hit_count"], int) for item in dynamic_result["items"])
    assert all(isinstance(item["matched_terms"], list) for item in dynamic_result["items"])
    assert any(item["matched_terms"] for item in dynamic_result["items"])
    assert all(item["vector_score"] is None for item in dynamic_result["items"])
    assert small_limit_result["total"] <= 3


def test_memory_service_retrieve_does_not_inject_when_no_match() -> None:
    service = _build_memory_service()
    user_id = "telegram:retrieve-no-match-user"
    service._long_term[user_id] = [
        {
            "id": "lng-unrelated-1",
            "user_id": user_id,
            "source_mid_term_id": "mid-unrelated-1",
            "memory_type": "session_summary",
            "summary": "天气和运动记录",
            "memory_text": "今天阳光很好，适合跑步和散步。",
            "keywords": ["天气", "运动"],
            "created_at": "2026-04-03T09:00:00+00:00",
        }
    ]

    result = service.retrieve(
        user_id=user_id,
        query="数据库索引优化与查询计划",
        limit=5,
    )

    assert result["total"] == 0
    assert result["items"] == []


def test_memory_service_retrieve_keeps_vector_only_candidate_when_score_is_strong() -> None:
    service = MemoryService(
        redis_provider_override=NoRedisProvider(),
        mid_term_store_override=NoopMidTermStore(),
        long_term_store_override=VectorOnlyLongTermStore(),
    )

    result = service.retrieve(
        user_id="telegram:vector-only-user",
        query="database indexing strategy",
        limit=5,
    )

    assert result["total"] == 1
    assert result["items"][0]["memory_id"] == "lng-vector-only-1"
    assert result["items"][0]["vector_score"] == 0.92


def test_memory_service_distill_creates_layered_long_term_memories() -> None:
    service = _build_memory_service()
    service.ingest_message(
        user_id="telegram:layered-memory-user",
        session_id="session-layered",
        role="user",
        content="请记住我偏好中文回复，并在每周一发送安全周报。",
        detected_lang="zh",
    )
    service.ingest_message(
        user_id="telegram:layered-memory-user",
        session_id="session-layered",
        role="assistant",
        content="好的，我会优先中文，并继续保留每周一的周报提醒。",
        detected_lang="zh",
    )
    service.ingest_message(
        user_id="telegram:layered-memory-user",
        session_id="session-layered",
        role="assistant",
        content="本周周报草稿已经整理完成，后续会继续发送。",
        detected_lang="zh",
    )

    result = service.distill(
        user_id="telegram:layered-memory-user",
        trigger="session_end",
        session_id="session-layered",
    )

    memory_types = {item["memory_type"] for item in result["long_term_items"]}
    assert result["created"] is True
    assert memory_types >= {"session_summary", "user_preference", "agent_decision", "task_result"}
    assert all(item["source_mid_term_id"] == result["mid_term"]["id"] for item in result["long_term_items"])


def test_memory_service_retrieve_prefers_focused_preference_memory() -> None:
    service = _build_memory_service()
    user_id = "telegram:retrieve-preference-user"
    base_time = datetime(2026, 4, 5, 8, 0, tzinfo=UTC)
    service._long_term[user_id] = [
        {
            "id": "lng-pref-summary",
            "user_id": user_id,
            "source_mid_term_id": "mid-pref-1",
            "memory_type": "session_summary",
            "summary": "会话总结",
            "memory_text": "会话总结：用户偏好中文回复，并保留安全周报提醒。",
            "keywords": ["中文", "周报", "偏好"],
            "created_at": base_time.isoformat(),
        },
        {
            "id": "lng-pref-focused",
            "user_id": user_id,
            "source_mid_term_id": "mid-pref-1",
            "memory_type": "user_preference",
            "summary": "用户偏好：优先中文回复；每周一发送安全周报。",
            "memory_text": "用户偏好（会话 session-pref）：优先中文回复；每周一发送安全周报。",
            "keywords": ["中文", "周报", "偏好"],
            "created_at": (base_time + timedelta(minutes=1)).isoformat(),
        },
    ]

    result = service.retrieve(
        user_id=user_id,
        query="用户偏好是什么，继续按中文周报提醒处理",
        limit=5,
    )

    assert result["total"] >= 1
    assert result["items"][0]["memory_type"] == "user_preference"


def test_memory_service_retrieve_dedupes_near_duplicate_memories() -> None:
    service = _build_memory_service()
    user_id = "telegram:retrieve-dedupe-user"
    base_time = datetime(2026, 4, 5, 8, 0, tzinfo=UTC)
    service._long_term[user_id] = [
        {
            "id": "lng-dedupe-1",
            "user_id": user_id,
            "source_mid_term_id": "mid-dedupe-1",
            "memory_type": "user_preference",
            "summary": "用户偏好：优先中文回复；每周一发送安全周报。",
            "memory_text": "用户偏好（会话 session-a）：优先中文回复；每周一发送安全周报。",
            "keywords": ["中文", "周报", "偏好"],
            "created_at": base_time.isoformat(),
        },
        {
            "id": "lng-dedupe-2",
            "user_id": user_id,
            "source_mid_term_id": "mid-dedupe-2",
            "memory_type": "user_preference",
            "summary": "用户偏好: 优先中文回复, 每周一发送安全周报",
            "memory_text": "用户偏好（会话 session-b）：优先中文回复, 每周一发送安全周报!",
            "keywords": ["中文", "周报", "偏好"],
            "created_at": (base_time + timedelta(minutes=1)).isoformat(),
        },
        {
            "id": "lng-dedupe-3",
            "user_id": user_id,
            "source_mid_term_id": "mid-dedupe-3",
            "memory_type": "session_summary",
            "summary": "会话总结",
            "memory_text": "会话总结：用户还提到每周三同步风险清单。",
            "keywords": ["风险", "每周三"],
            "created_at": (base_time + timedelta(minutes=2)).isoformat(),
        },
    ]

    result = service.retrieve(
        user_id=user_id,
        query="继续按中文周报偏好执行",
        limit=5,
    )

    returned_ids = [item["memory_id"] for item in result["items"]]
    assert "lng-dedupe-1" in returned_ids or "lng-dedupe-2" in returned_ids
    assert not ({"lng-dedupe-1", "lng-dedupe-2"} <= set(returned_ids))
