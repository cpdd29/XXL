from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(slots=True, frozen=True)
class InfrastructureSettings:
    environment: str = os.getenv("WORKBOT_ENVIRONMENT", "local")
    request_timeout_seconds: float = float(os.getenv("WORKBOT_REQUEST_TIMEOUT_SECONDS", "15"))
    max_retry: int = int(os.getenv("WORKBOT_MAX_RETRY", "1"))

