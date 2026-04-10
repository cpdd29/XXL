from __future__ import annotations

from fastapi import HTTPException

from app.config import get_settings
from app.schemas.messages import ChannelType, UnifiedMessage
from app.services.memory_service import MemoryService
from app.services.security_gateway_service import SecurityGatewayService


class FakeRedisProvider:
    def __init__(self, client) -> None:
        self._client = client

    def get_client(self):
        return self._client


class FakeRedisClient:
    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}
        self.sorted_sets: dict[str, dict[str, float]] = {}
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    @staticmethod
    def _slice(values: list[str], start: int, end: int) -> list[str]:
        if not values:
            return []

        size = len(values)
        if start < 0:
            start = max(size + start, 0)
        if end < 0:
            end = size + end
        end = min(end, size - 1)
        if start > end or start >= size:
            return []
        return values[start : end + 1]

    def ping(self) -> bool:
        return True

    def close(self) -> None:
        return None

    def rpush(self, key: str, *values: str) -> int:
        bucket = self.lists.setdefault(key, [])
        bucket.extend(values)
        return len(bucket)

    def ltrim(self, key: str, start: int, end: int) -> bool:
        self.lists[key] = self._slice(self.lists.get(key, []), start, end)
        return True

    def llen(self, key: str) -> int:
        return len(self.lists.get(key, []))

    def lrange(self, key: str, start: int, end: int) -> list[str]:
        return self._slice(self.lists.get(key, []), start, end)

    def zremrangebyscore(self, key: str, min_score: float, max_score: float) -> int:
        bucket = self.sorted_sets.setdefault(key, {})
        removable = [
            member for member, score in bucket.items() if float(min_score) <= score <= float(max_score)
        ]
        for member in removable:
            del bucket[member]
        return len(removable)

    def zcard(self, key: str) -> int:
        return len(self.sorted_sets.get(key, {}))

    def zadd(self, key: str, mapping: dict[str, float]) -> int:
        bucket = self.sorted_sets.setdefault(key, {})
        bucket.update(mapping)
        return len(mapping)

    def expire(self, key: str, seconds: int) -> bool:
        self.ttls[key] = seconds
        return True

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def setex(self, key: str, seconds: int, value: str) -> bool:
        self.values[key] = value
        self.ttls[key] = seconds
        return True

    def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if self.lists.pop(key, None) is not None:
                removed += 1
            if self.sorted_sets.pop(key, None) is not None:
                removed += 1
            if self.values.pop(key, None) is not None:
                removed += 1
            self.ttls.pop(key, None)
        return removed

    def scan_iter(self, match: str):
        prefix = match[:-1] if match.endswith("*") else match
        seen: set[str] = set()
        for key in [*self.lists.keys(), *self.sorted_sets.keys(), *self.values.keys()]:
            if key.startswith(prefix) and key not in seen:
                seen.add(key)
                yield key


def _build_message(user_id: str) -> UnifiedMessage:
    return UnifiedMessage(
        message_id="msg-1",
        channel=ChannelType.TELEGRAM,
        platform_user_id=user_id,
        chat_id="chat-1",
        text="请帮我整理安全周报",
        received_at="2026-04-02T10:00:00+00:00",
        raw_payload={},
        metadata={},
    )


def test_memory_service_uses_redis_for_short_term_storage() -> None:
    fake_client = FakeRedisClient()
    service = MemoryService(redis_provider_override=FakeRedisProvider(fake_client))

    first = service.ingest_message(
        user_id="telegram:user-redis",
        session_id="session-1",
        role="user",
        content="请记录我偏好中文回复",
        detected_lang="zh",
    )
    second = service.ingest_message(
        user_id="telegram:user-redis",
        session_id="session-1",
        role="assistant",
        content="好的，我会优先中文。",
        detected_lang="zh",
    )

    assert first["short_term_count"] == 1
    assert second["short_term_count"] == 2
    assert service.get_layers("telegram:user-redis")["short_term_count"] == 2
    assert service._short_term == {}
    assert fake_client.llen("memory:short:telegram:user-redis") == 2

    distill_result = service.distill(
        user_id="telegram:user-redis",
        trigger="session_end",
        session_id="session-1",
    )

    assert distill_result["created"] is True
    assert distill_result["short_term_remaining"] == 0
    assert service.retrieve("telegram:user-redis", "中文回复")["total"] >= 1
    assert fake_client.llen("memory:short:telegram:user-redis") == 0


def test_security_gateway_uses_redis_for_rate_limiting() -> None:
    fake_client = FakeRedisClient()
    service = SecurityGatewayService(redis_provider_override=FakeRedisProvider(fake_client))
    settings = get_settings()

    for _ in range(settings.message_rate_limit_per_minute):
        result = service.inspect(_build_message("redis-rate-user"), auth_scope="messages:ingest")
        assert result["user_key"] == "telegram:redis-rate-user"

    assert service._recent_requests == {}
    assert fake_client.zcard("security:rate:telegram:redis-rate-user") == settings.message_rate_limit_per_minute

    try:
        service.inspect(_build_message("redis-rate-user"), auth_scope="messages:ingest")
    except HTTPException as exc:
        assert exc.status_code == 429
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Expected rate limit exception for redis-backed gateway")
