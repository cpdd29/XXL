from __future__ import annotations

import logging
import time

from redis import Redis

from app.config import get_settings


logger = logging.getLogger(__name__)
RETRY_INTERVAL_SECONDS = 30


class RedisProvider:
    def __init__(self, redis_url: str | None = None) -> None:
        self.redis_url = redis_url or get_settings().redis_url
        self._client: Redis | None = None
        self._last_attempt_at = 0.0
        self._warned_unavailable = False

    def get_client(self) -> Redis | None:
        if self._client is not None:
            return self._client

        now = time.monotonic()
        if now - self._last_attempt_at < RETRY_INTERVAL_SECONDS:
            return None

        self._last_attempt_at = now
        try:
            client = Redis.from_url(self.redis_url, decode_responses=True)
            client.ping()
            self._client = client
            self._warned_unavailable = False
            return client
        except Exception as exc:  # pragma: no cover - depends on runtime environment
            if not self._warned_unavailable:
                logger.warning("Redis integration disabled, using in-memory fallback: %s", exc)
                self._warned_unavailable = True
            self._client = None
            return None

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:  # pragma: no cover - defensive shutdown path
                pass
        self._client = None
        self._last_attempt_at = 0.0


redis_provider = RedisProvider()
