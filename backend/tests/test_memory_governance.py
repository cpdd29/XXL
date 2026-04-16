from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.services.memory_service import (
    MEMORY_SCOPE_GLOBAL,
    MEMORY_SCOPE_TENANT,
    TRUST_LEVEL_REVIEWABLE,
    TRUST_LEVEL_TRUSTED,
    WRITE_SOURCE_EXTERNAL_AGENT,
    MemoryService,
)
from app.services.store import store


client = TestClient(app)


def _pick(payload: dict, snake_key: str):
    camel_key = snake_key.split("_")[0] + "".join(part.capitalize() for part in snake_key.split("_")[1:])
    return payload.get(snake_key, payload.get(camel_key))


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
    def list_memories(self, user_id: str, filters: dict | None = None):
        _ = (user_id, filters)
        return None

    def query_memories(self, user_id: str, query: str, limit: int, filters: dict | None = None):
        _ = (user_id, query, limit, filters)
        return None

    def save_memory(self, memory: dict) -> bool:
        _ = memory
        return False

    def clear(self) -> None:
        return None

    def close(self) -> None:
        return None


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

    def get_memory_session_state(self, *, user_id: str, session_id: str) -> dict | None:
        return self.session_states.get((user_id, session_id))

    def upsert_memory_session_state(self, payload: dict) -> bool:
        self.session_states[(str(payload["user_id"]), str(payload["session_id"]))] = dict(payload)
        return True


def _build_memory_service(raw_store=None) -> MemoryService:
    return MemoryService(
        redis_provider_override=NoRedisProvider(),
        mid_term_store_override=NoopMidTermStore(),
        long_term_store_override=NoopLongTermStore(),
        raw_message_store_override=raw_store or FakeRawMessageStore(),
    )


def test_external_agent_cannot_distill_long_term_memory() -> None:
    service = _build_memory_service()
    service.ingest_message(
        user_id="telegram:governance-user",
        session_id="session-a",
        role="user",
        content="请记住我偏好中文。",
        scope={"tenant_id": "tenant-a", "project_id": "project-a", "environment": "prod"},
    )

    try:
        service.distill(
            user_id="telegram:governance-user",
            session_id="session-a",
            scope={"tenant_id": "tenant-a", "project_id": "project-a", "environment": "prod"},
            write_source=WRITE_SOURCE_EXTERNAL_AGENT,
        )
    except Exception as exc:
        assert "cannot write governed mid/long-term memory" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("external agent distill should be rejected")


def test_memory_retrieve_is_scope_isolated_and_global_memory_can_fallback() -> None:
    service = _build_memory_service()
    tenant_alpha = {"tenant_id": "tenant-alpha", "project_id": "project-a", "environment": "prod"}
    tenant_beta = {"tenant_id": "tenant-beta", "project_id": "project-b", "environment": "prod"}

    service.ingest_message(
        user_id="telegram:shared-user",
        session_id="alpha-session",
        role="user",
        content="请记住 alpha 只看中文周报。",
        scope=tenant_alpha,
    )
    service.ingest_message(
        user_id="telegram:shared-user",
        session_id="alpha-session",
        role="assistant",
        content="好的，我会保留 alpha 中文周报偏好。",
        scope=tenant_alpha,
        write_source="brain_internal",
    )
    service.distill(
        user_id="telegram:shared-user",
        session_id="alpha-session",
        scope=tenant_alpha,
    )

    service.ingest_message(
        user_id="telegram:shared-user",
        session_id="global-session",
        role="user",
        content="所有租户都需要遵守统一安全基线。",
        scope=tenant_alpha,
        memory_scope=MEMORY_SCOPE_GLOBAL,
        write_source="brain_internal",
    )
    service.ingest_message(
        user_id="telegram:shared-user",
        session_id="global-session",
        role="assistant",
        content="已记录全局安全基线要求。",
        scope=tenant_alpha,
        memory_scope=MEMORY_SCOPE_GLOBAL,
        write_source="brain_internal",
    )
    service.distill(
        user_id="telegram:shared-user",
        session_id="global-session",
        scope=tenant_alpha,
        memory_scope=MEMORY_SCOPE_GLOBAL,
    )

    alpha_layers = service.get_layers("telegram:shared-user", scope=tenant_alpha)
    beta_result = service.retrieve(
        "telegram:shared-user",
        "安全基线",
        scope=tenant_beta,
    )

    assert alpha_layers["long_term_count"] >= 2
    assert any(item["memory_scope"] == MEMORY_SCOPE_TENANT for item in alpha_layers["long_term"])
    assert any(item["memory_scope"] == MEMORY_SCOPE_GLOBAL for item in alpha_layers["long_term"])
    assert beta_result["total"] >= 1
    assert all(item["memory_scope"] == MEMORY_SCOPE_GLOBAL for item in beta_result["items"])
    assert beta_result["scope_breakdown"]["tenant"] == 0
    assert beta_result["scope_breakdown"]["global"] >= 1


def test_memory_layers_and_retrieve_support_explicit_memory_scope_filter() -> None:
    service = _build_memory_service()
    scope = {"tenant_id": "tenant-alpha", "project_id": "project-a", "environment": "prod"}

    service.ingest_message(
        user_id="telegram:scope-filter-user",
        session_id="tenant-session",
        role="user",
        content="tenant 记忆：客户偏好中文周报。",
        scope=scope,
    )
    service.ingest_message(
        user_id="telegram:scope-filter-user",
        session_id="tenant-session",
        role="assistant",
        content="已记录 tenant 偏好。",
        scope=scope,
        write_source="brain_internal",
    )
    service.distill(
        user_id="telegram:scope-filter-user",
        session_id="tenant-session",
        scope=scope,
    )

    service.ingest_message(
        user_id="telegram:scope-filter-user",
        session_id="global-session",
        role="user",
        content="global 记忆：统一遵循安全基线。",
        scope=scope,
        memory_scope=MEMORY_SCOPE_GLOBAL,
        write_source="brain_internal",
    )
    service.ingest_message(
        user_id="telegram:scope-filter-user",
        session_id="global-session",
        role="assistant",
        content="已记录 global 安全基线。",
        scope=scope,
        memory_scope=MEMORY_SCOPE_GLOBAL,
        write_source="brain_internal",
    )
    service.distill(
        user_id="telegram:scope-filter-user",
        session_id="global-session",
        scope=scope,
        memory_scope=MEMORY_SCOPE_GLOBAL,
    )

    tenant_layers = service.get_layers(
        "telegram:scope-filter-user",
        scope=scope,
        memory_scope=MEMORY_SCOPE_TENANT,
    )
    global_layers = service.get_layers(
        "telegram:scope-filter-user",
        scope=scope,
        memory_scope=MEMORY_SCOPE_GLOBAL,
    )
    global_retrieve = service.retrieve(
        "telegram:scope-filter-user",
        "安全基线",
        scope=scope,
        memory_scope=MEMORY_SCOPE_GLOBAL,
    )

    assert tenant_layers["scope_breakdown"] == {"tenant": tenant_layers["short_term_count"] + tenant_layers["mid_term_count"] + tenant_layers["long_term_count"], "global": 0, "total": tenant_layers["short_term_count"] + tenant_layers["mid_term_count"] + tenant_layers["long_term_count"]}
    assert global_layers["scope_breakdown"]["tenant"] == 0
    assert global_layers["scope_breakdown"]["global"] >= 3
    assert all(item["memory_scope"] == MEMORY_SCOPE_GLOBAL for item in global_layers["short_term"] + global_layers["mid_term"] + global_layers["long_term"])
    assert global_retrieve["total"] >= 1
    assert global_retrieve["scope_breakdown"]["tenant"] == 0
    assert all(item["memory_scope"] == MEMORY_SCOPE_GLOBAL for item in global_retrieve["items"])


def test_review_memory_controls_visibility_and_correction() -> None:
    service = _build_memory_service()
    scope = {"tenant_id": "tenant-a", "project_id": "project-a", "environment": "prod"}
    now = datetime(2026, 4, 10, 8, 0, tzinfo=UTC).isoformat()
    memory_id = "lng-review-1"
    service._long_term["telegram:review-user"] = [
        {
            "id": memory_id,
            "user_id": "telegram:review-user",
            "source_mid_term_id": "mid-review",
            "memory_type": "user_preference",
            "summary": "用户偏好待审核",
            "memory_text": "待审核的记忆内容",
            "keywords": ["审核", "记忆"],
            "created_at": now,
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "environment": "prod",
            "memory_scope": MEMORY_SCOPE_TENANT,
            "memory_layer_kind": "fact",
            "write_source": "external_skill",
            "trust_level": TRUST_LEVEL_REVIEWABLE,
            "memory_status": "active",
            "review_status": "pending",
            "reviewed_by": None,
            "reviewed_at": None,
            "review_note": None,
            "expires_at": None,
            "archived_at": None,
            "deleted_at": None,
            "corrected_at": None,
        }
    ]

    default_result = service.retrieve(
        "telegram:review-user",
        "审核 记忆",
        scope=scope,
    )
    include_reviewable = service.retrieve(
        "telegram:review-user",
        "审核 记忆",
        scope=scope,
        include_untrusted=True,
    )
    assert default_result["total"] == 0
    assert include_reviewable["total"] == 1

    approved = service.review_memory(
        user_id="telegram:review-user",
        memory_id=memory_id,
        action="approve",
        reviewed_by="auditor@example.test",
        scope=scope,
        note="人工审核通过",
    )
    assert approved["item"]["trust_level"] == TRUST_LEVEL_TRUSTED

    corrected = service.review_memory(
        user_id="telegram:review-user",
        memory_id=memory_id,
        action="correct",
        reviewed_by="auditor@example.test",
        scope=scope,
        corrected_memory_text="已修正的记忆内容",
        corrected_summary="修正后摘要",
    )
    assert corrected["item"]["memory_text"] == "已修正的记忆内容"

    visible = service.retrieve(
        "telegram:review-user",
        "修正 记忆",
        scope=scope,
    )
    assert visible["total"] == 1

    deleted = service.review_memory(
        user_id="telegram:review-user",
        memory_id=memory_id,
        action="delete",
        reviewed_by="auditor@example.test",
        scope=scope,
    )
    assert deleted["item"]["memory_status"] == "deleted"
    assert service.retrieve("telegram:review-user", "修正 记忆", scope=scope)["total"] == 0


def test_memory_lifecycle_archives_expired_records() -> None:
    service = _build_memory_service()
    scope = {"tenant_id": "tenant-a", "project_id": "project-a", "environment": "prod"}
    past = datetime.now(UTC) - timedelta(days=2)
    service._long_term["telegram:lifecycle-user"] = [
        {
            "id": "lng-expired-1",
            "user_id": "telegram:lifecycle-user",
            "source_mid_term_id": "mid-expired",
            "memory_type": "event_digest",
            "summary": "过期摘要",
            "memory_text": "应该被归档",
            "keywords": ["归档"],
            "created_at": (past - timedelta(days=10)).isoformat(),
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "environment": "prod",
            "memory_scope": MEMORY_SCOPE_TENANT,
            "memory_layer_kind": "conversation",
            "write_source": "distillation",
            "trust_level": TRUST_LEVEL_TRUSTED,
            "memory_status": "active",
            "review_status": "approved",
            "reviewed_by": None,
            "reviewed_at": None,
            "review_note": None,
            "expires_at": past.isoformat(),
            "archived_at": None,
            "deleted_at": None,
            "corrected_at": None,
        }
    ]

    result = service.apply_lifecycle(user_id="telegram:lifecycle-user", scope=scope)
    assert result["archived_count"] == 1
    assert service._long_term["telegram:lifecycle-user"][0]["memory_status"] == "archived"


def test_memory_routes_enforce_scope_headers_and_review_flow(
    auth_headers_factory,
) -> None:
    from app.services.memory_service import memory_service

    scope_headers = {
        **auth_headers_factory(role="operator"),
        "X-WorkBot-Tenant-Id": "tenant-alpha",
        "X-WorkBot-Project-Id": "project-a",
        "X-WorkBot-Environment": "prod",
    }

    ingest = client.post(
        "/api/memory/messages",
        json={
            "userId": "telegram:route-user",
            "sessionId": "session-a",
            "role": "user",
            "content": "请记住路由层的租户隔离。",
            "detectedLang": "zh",
        },
        headers=scope_headers,
    )
    assert ingest.status_code == 200

    distill = client.post(
        "/api/memory/telegram:route-user/distill",
        json={"trigger": "session_end", "sessionId": "session-a"},
        headers=scope_headers,
    )
    assert distill.status_code == 200
    memory_id = distill.json()["longTerm"]["id"]

    for item in memory_service._long_term["telegram:route-user"]:
        item["trust_level"] = "reviewable"
        item["review_status"] = "pending"

    hidden = client.get(
        "/api/memory/telegram:route-user/retrieve",
        params={"query": "租户隔离"},
        headers=scope_headers,
    )
    assert hidden.status_code == 200
    assert hidden.json()["total"] == 0

    approved = client.post(
        f"/api/memory/telegram:route-user/long-term/{memory_id}/review",
        json={"action": "approve", "note": "审核通过"},
        headers=scope_headers,
    )
    assert approved.status_code == 200

    visible = client.get(
        "/api/memory/telegram:route-user/retrieve",
        params={"query": "租户隔离"},
        headers=scope_headers,
    )
    assert visible.status_code == 200
    assert visible.json()["total"] >= 1

    viewer_id = "viewer-memory-user"
    store.user_profiles[viewer_id] = {
        "id": viewer_id,
        "tenant_id": "tenant-alpha",
        "project_id": "project-a",
        "environment": "prod",
    }
    denied = client.get(
        "/api/memory/telegram:route-user/layers",
        headers={
            **auth_headers_factory(role="viewer", user_id=viewer_id, email="viewer.memory@example.test"),
            "X-WorkBot-Tenant-Id": "tenant-beta",
            "X-WorkBot-Project-Id": "project-b",
            "X-WorkBot-Environment": "prod",
        },
    )
    assert denied.status_code == 403


def test_memory_routes_expose_scope_breakdown_and_memory_scope_filter(auth_headers_factory) -> None:
    scope_headers = {
        **auth_headers_factory(role="operator"),
        "X-WorkBot-Tenant-Id": "tenant-alpha",
        "X-WorkBot-Project-Id": "project-a",
        "X-WorkBot-Environment": "prod",
    }

    tenant_ingest = client.post(
        "/api/memory/messages",
        json={
            "userId": "telegram:route-scope-user",
            "sessionId": "tenant-session",
            "role": "user",
            "content": "tenant only 偏好",
            "detectedLang": "zh",
        },
        headers=scope_headers,
    )
    assert tenant_ingest.status_code == 200
    assert tenant_ingest.json()["item"]["memoryScope"] == "tenant"

    global_ingest = client.post(
        "/api/memory/messages",
        json={
            "userId": "telegram:route-scope-user",
            "sessionId": "global-session",
            "role": "user",
            "content": "global 安全基线",
            "detectedLang": "zh",
            "memoryScope": "global",
            "writeSource": "brain_internal",
        },
        headers=scope_headers,
    )
    assert global_ingest.status_code == 200
    assert global_ingest.json()["item"]["memoryScope"] == "global"

    client.post(
        "/api/memory/messages",
        json={
            "userId": "telegram:route-scope-user",
            "sessionId": "tenant-session",
            "role": "assistant",
            "content": "tenant only 已确认",
            "detectedLang": "zh",
            "writeSource": "brain_internal",
        },
        headers=scope_headers,
    )
    client.post(
        "/api/memory/messages",
        json={
            "userId": "telegram:route-scope-user",
            "sessionId": "global-session",
            "role": "assistant",
            "content": "global 安全基线已确认",
            "detectedLang": "zh",
            "memoryScope": "global",
            "writeSource": "brain_internal",
        },
        headers=scope_headers,
    )
    client.post(
        "/api/memory/telegram:route-scope-user/distill",
        json={"trigger": "session_end", "sessionId": "tenant-session"},
        headers=scope_headers,
    )
    client.post(
        "/api/memory/telegram:route-scope-user/distill",
        json={
            "trigger": "session_end",
            "sessionId": "global-session",
            "memoryScope": "global",
            "writeSource": "brain_internal",
        },
        headers=scope_headers,
    )

    layers = client.get(
        "/api/memory/telegram:route-scope-user/layers",
        params={"memoryScope": "global"},
        headers=scope_headers,
    )
    assert layers.status_code == 200
    assert layers.json()["scopeBreakdown"]["tenant"] == 0
    assert layers.json()["scopeBreakdown"]["global"] >= 2

    retrieve = client.get(
        "/api/memory/telegram:route-scope-user/retrieve",
        params={"query": "安全基线", "memoryScope": "global"},
        headers=scope_headers,
    )
    assert retrieve.status_code == 200
    assert retrieve.json()["scopeBreakdown"]["tenant"] == 0
    assert all(item["memoryScope"] == "global" for item in retrieve.json()["items"])


def test_distill_long_term_memory_does_not_store_sensitive_raw_values(auth_headers_factory) -> None:
    platform_user_id = "memory-sensitive-user"
    user_id = f"telegram:{platform_user_id}"
    session_id = "memory-sensitive-session"
    raw_email = "ops.sec@example.com"
    raw_api_key = "sk-proj-abcdefghijklmnopqrstuvwx1234567890"
    raw_bearer = "Bearer abcdefghijklmnop123456"
    raw_otp = "654321"

    scope_headers = {
        **auth_headers_factory(role="operator"),
        "X-WorkBot-Tenant-Id": "tenant-alpha",
        "X-WorkBot-Project-Id": "project-a",
        "X-WorkBot-Environment": "prod",
    }

    ingest = client.post(
        "/api/memory/messages",
        json={
            "userId": user_id,
            "sessionId": session_id,
            "role": "user",
            "content": (
                f"请记录邮箱 {raw_email}，OpenAI key {raw_api_key}，"
                f"{raw_bearer}，验证码 {raw_otp}"
            ),
            "detectedLang": "zh",
        },
        headers=scope_headers,
    )
    assert ingest.status_code == 200

    distill = client.post(
        f"/api/memory/{user_id}/distill",
        json={"trigger": "session_end", "sessionId": session_id},
        headers=scope_headers,
    )
    assert distill.status_code == 200
    body = distill.json()
    assert body["created"] is True
    assert isinstance(body["longTerm"], dict)
    assert len(body["longTermItems"]) >= 1

    combined_memory_text = "\n".join(
        [
            str(body["longTerm"].get("memoryText") or ""),
            str(body["longTerm"].get("summary") or ""),
            *[
                f"{item.get('memoryText') or ''}\n{item.get('summary') or ''}"
                for item in body["longTermItems"]
            ],
        ]
    )

    assert "脱敏" in combined_memory_text

    assert raw_email not in combined_memory_text
    assert raw_api_key not in combined_memory_text
    assert raw_bearer not in combined_memory_text
    assert raw_otp not in combined_memory_text


def test_distill_filters_local_only_content_and_returns_local_only_audit_fields() -> None:
    service = _build_memory_service()
    scope = {"tenant_id": "tenant-local-only", "project_id": "project-a", "environment": "prod"}
    user_id = "telegram:local-only-user"
    session_id = "local-only-session"
    local_only_text = "临时调试密钥 local-debug-secret-778899 仅本地排障使用"

    service.ingest_message(
        user_id=user_id,
        session_id=session_id,
        role="user",
        content=f"长期偏好：每周三上午同步周报。{local_only_text}",
        scope=scope,
    )
    service.ingest_message(
        user_id=user_id,
        session_id=session_id,
        role="assistant",
        content="收到，长期偏好已记录。",
        scope=scope,
        write_source="brain_internal",
    )
    distilled = service.distill(
        user_id=user_id,
        session_id=session_id,
        scope=scope,
    )

    assert distilled["created"] is True
    long_term_items = list(distilled["long_term_items"])
    assert len(long_term_items) >= 1

    long_term_text = "\n".join(
        f"{item.get('memory_text') or ''}\n{item.get('summary') or ''}"
        for item in long_term_items
    )
    assert "每周三上午同步周报" in long_term_text
    assert local_only_text not in long_term_text

    mid_term = distilled["mid_term"] or {}
    long_term = distilled["long_term"] or {}
    assert int(mid_term.get("local_only_filtered_count", 0)) >= 1
    assert int(long_term.get("local_only_filtered_count", 0)) >= 1
    assert isinstance(mid_term.get("local_only_reasons"), list)
    assert isinstance(long_term.get("local_only_reasons"), list)
    assert mid_term.get("local_only_reasons")
    assert long_term.get("local_only_reasons")


def test_memory_distill_route_exposes_local_only_audit_and_local_only_text_not_retrievable(
    auth_headers_factory,
) -> None:
    scope_headers = {
        **auth_headers_factory(role="operator"),
        "X-WorkBot-Tenant-Id": "tenant-local-only",
        "X-WorkBot-Project-Id": "project-a",
        "X-WorkBot-Environment": "prod",
    }
    user_id = "telegram:route-local-only-user"
    session_id = "local-only-route-session"
    local_only_text = "仅本地排障日志片段 trace-debug-token-123456"

    first_ingest = client.post(
        "/api/memory/messages",
        json={
            "userId": user_id,
            "sessionId": session_id,
            "role": "user",
            "content": f"长期偏好：中文日报。{local_only_text}",
            "detectedLang": "zh",
        },
        headers=scope_headers,
    )
    assert first_ingest.status_code == 200
    second_ingest = client.post(
        "/api/memory/messages",
        json={
            "userId": user_id,
            "sessionId": session_id,
            "role": "assistant",
            "content": "已记录长期偏好。",
            "detectedLang": "zh",
            "writeSource": "brain_internal",
        },
        headers=scope_headers,
    )
    assert second_ingest.status_code == 200

    distill = client.post(
        f"/api/memory/{user_id}/distill",
        json={"trigger": "session_end", "sessionId": session_id},
        headers=scope_headers,
    )
    assert distill.status_code == 200
    body = distill.json()
    assert body["created"] is True
    assert int(_pick(body["midTerm"], "local_only_filtered_count") or 0) >= 1
    assert int(_pick(body["longTerm"], "local_only_filtered_count") or 0) >= 1
    assert _pick(body["midTerm"], "local_only_reasons")
    assert _pick(body["longTerm"], "local_only_reasons")

    retrieve_local_only = client.get(
        f"/api/memory/{user_id}/retrieve",
        params={"query": "trace-debug-token-123456"},
        headers=scope_headers,
    )
    assert retrieve_local_only.status_code == 200
    assert retrieve_local_only.json()["total"] == 0
