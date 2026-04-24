from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys
from typing import Any

from fastapi import HTTPException


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.modules.organization.application.memory_service import (  # noqa: E402
    MEMORY_SCOPE_GLOBAL,
    MEMORY_SCOPE_TENANT,
    WRITE_SOURCE_EXTERNAL_AGENT,
    MemoryService,
)


class _NoRedisProvider:
    def get_client(self):
        return None


class _NoopMidTermStore:
    def list_summaries(self, user_id: str):
        _ = user_id
        return None

    def save_summary(self, summary: dict) -> bool:
        _ = summary
        return False

    def clear(self) -> None:
        return None


class _NoopLongTermStore:
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


class _RawMessageStore:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []
        self.session_states: dict[tuple[str, str], dict[str, Any]] = {}

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


def _build_service() -> MemoryService:
    return MemoryService(
        redis_provider_override=_NoRedisProvider(),
        mid_term_store_override=_NoopMidTermStore(),
        long_term_store_override=_NoopLongTermStore(),
        raw_message_store_override=_RawMessageStore(),
    )


def _scope(tenant_id: str, project_id: str, environment: str = "prod") -> dict[str, str]:
    return {
        "tenant_id": tenant_id,
        "project_id": project_id,
        "environment": environment,
    }


def run_check() -> dict[str, Any]:
    service = _build_service()
    governance = MemoryService.governance_snapshot()

    alpha_scope = _scope("tenant-alpha", "project-a")
    beta_scope = _scope("tenant-beta", "project-b")

    service.ingest_message(
        user_id="telegram:scope-user",
        session_id="alpha-session",
        role="user",
        content="请记住 alpha 只看中文周报。",
        scope=alpha_scope,
    )
    service.ingest_message(
        user_id="telegram:scope-user",
        session_id="alpha-session",
        role="assistant",
        content="好的，我会保留 alpha 中文周报偏好。",
        scope=alpha_scope,
        write_source="brain_internal",
    )
    tenant_distill = service.distill(
        user_id="telegram:scope-user",
        session_id="alpha-session",
        scope=alpha_scope,
        memory_scope=MEMORY_SCOPE_TENANT,
    )

    service.ingest_message(
        user_id="telegram:scope-user",
        session_id="global-session",
        role="user",
        content="所有租户都需要遵守统一安全基线。",
        scope=alpha_scope,
        memory_scope=MEMORY_SCOPE_GLOBAL,
        write_source="brain_internal",
    )
    service.ingest_message(
        user_id="telegram:scope-user",
        session_id="global-session",
        role="assistant",
        content="已记录全局安全基线要求。",
        scope=alpha_scope,
        memory_scope=MEMORY_SCOPE_GLOBAL,
        write_source="brain_internal",
    )
    global_distill = service.distill(
        user_id="telegram:scope-user",
        session_id="global-session",
        scope=alpha_scope,
        memory_scope=MEMORY_SCOPE_GLOBAL,
    )

    cross_scope_result = service.retrieve(
        "telegram:scope-user",
        "安全基线",
        scope=beta_scope,
    )
    tenant_scope_result = service.retrieve(
        "telegram:scope-user",
        "中文周报",
        scope=beta_scope,
    )

    external_write_blocked = False
    try:
        service.ingest_message(
            user_id="telegram:external-user",
            session_id="external-session",
            role="user",
            content="请记住我偏好中文。",
            scope=alpha_scope,
        )
        service.distill(
            user_id="telegram:external-user",
            session_id="external-session",
            scope=alpha_scope,
            write_source=WRITE_SOURCE_EXTERNAL_AGENT,
        )
    except HTTPException as exc:
        external_write_blocked = exc.status_code == 403

    local_only_text = "临时调试密钥 local-debug-secret-778899 仅本地排障使用"
    service.ingest_message(
        user_id="telegram:local-only-user",
        session_id="local-session",
        role="user",
        content=f"长期偏好：每周三上午同步周报。{local_only_text}",
        scope=alpha_scope,
    )
    local_only_distill = service.distill(
        user_id="telegram:local-only-user",
        session_id="local-session",
        scope=alpha_scope,
    )
    local_only_text_render = "\n".join(
        str(item.get("memory_text") or "")
        for item in local_only_distill.get("long_term_items") or []
    )

    lifecycle_target = (local_only_distill.get("long_term_items") or [None])[0]
    lifecycle_archived = False
    if isinstance(lifecycle_target, dict):
        expired = dict(lifecycle_target)
        expired["expires_at"] = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        long_bucket = service._long_term.setdefault("telegram:local-only-user", [])
        for index, item in enumerate(long_bucket):
            if str(item.get("id") or "") == str(expired.get("id") or ""):
                long_bucket[index] = expired
                break
        lifecycle_result = service.apply_lifecycle(
            user_id="telegram:local-only-user",
            scope=alpha_scope,
        )
        lifecycle_archived = lifecycle_result.get("archived_count") == 1

    checks = {
        "long_term_whitelist_defined": {
            "ok": len(governance["long_term_whitelist"]) >= 5,
            "memory_types": [item["memory_type"] for item in governance["long_term_whitelist"]],
        },
        "external_long_term_write_blocked": {
            "ok": external_write_blocked,
        },
        "local_only_filtering_active": {
            "ok": local_only_text not in local_only_text_render
            and int((local_only_distill.get("distill_audit") or {}).get("local_only_filtered_count") or 0) >= 1,
            "filtered_count": int(
                (local_only_distill.get("distill_audit") or {}).get("local_only_filtered_count") or 0
            ),
            "filtered_reasons": list((local_only_distill.get("distill_audit") or {}).get("local_only_reasons") or []),
        },
        "tenant_scope_isolation": {
            "ok": tenant_scope_result.get("total") == 0,
            "cross_scope_total": int(tenant_scope_result.get("total") or 0),
        },
        "global_scope_fallback": {
            "ok": int(cross_scope_result.get("total") or 0) >= 1
            and int((cross_scope_result.get("scope_breakdown") or {}).get("tenant") or 0) == 0
            and int((cross_scope_result.get("scope_breakdown") or {}).get("global") or 0) >= 1,
            "scope_breakdown": dict(cross_scope_result.get("scope_breakdown") or {}),
        },
        "lifecycle_archive_active": {
            "ok": lifecycle_archived,
        },
        "distill_outputs_present": {
            "ok": bool(tenant_distill.get("created")) and bool(global_distill.get("created")),
        },
    }
    ok = all(bool(item.get("ok")) for item in checks.values())
    return {
        "ok": ok,
        "checks": checks,
        "governance": governance,
        "summary": {
            "passed_checks": sum(1 for item in checks.values() if item.get("ok")),
            "failed_checks": sum(1 for item in checks.values() if not item.get("ok")),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run repository-local memory governance acceptance checks.")
    parser.add_argument("--strict", action="store_true", help="Return non-zero when any governance check fails.")
    args = parser.parse_args(argv)

    payload = run_check()
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if args.strict and not bool(payload.get("ok")):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
