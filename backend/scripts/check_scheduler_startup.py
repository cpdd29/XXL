from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import get_settings
from app.services.persistence_service import persistence_service
from app.services.scheduler_guard_service import scheduler_guard_service
from app.services.workflow_dispatch_poller_service import DEFAULT_DISPATCH_POLL_INTERVAL_SECONDS
from app.services.workflow_dispatcher_service import DEFAULT_DISPATCH_LEASE_SECONDS
from scripts.check_nats_contract import run_check as run_nats_contract_check
from scripts.check_persistence_contract import run_persistence_contract_check
from scripts.dr_common import platform_readiness


def _normalize_platform_readiness(
    readiness: dict[str, Any],
    *,
    persistence_contract: dict[str, Any],
    nats_contract: dict[str, Any],
) -> dict[str, Any]:
    normalized = dict(readiness)
    warnings = [
        str(item).strip()
        for item in (normalized.get("warnings") or [])
        if str(item).strip()
    ]

    if bool(persistence_contract.get("ok")):
        normalized["persistence_enabled"] = True
        warnings = [
            item for item in warnings if item != "当前未连接正式持久层，真源校验将基于内存/降级模式。"
        ]

    if (
        bool(nats_contract.get("ok"))
        and bool(nats_contract.get("connected"))
        and not bool(nats_contract.get("fallback_mode"))
    ):
        normalized["nats_connected"] = True
        warnings = [
            item for item in warnings if item != "NATS 当前未建立连接，将以 in-process fallback 视为可降级运行。"
        ]

    normalized["warnings"] = warnings
    return normalized


def _check_methods(target: object, method_names: tuple[str, ...]) -> dict[str, Any]:
    available = [name for name in method_names if callable(getattr(target, name, None))]
    missing = [name for name in method_names if name not in available]
    return {
        "available": available,
        "missing": missing,
        "count": len(available),
    }


def _runtime_mode(*, persistence_enabled: bool, required_methods: tuple[str, ...]) -> dict[str, Any]:
    method_state = _check_methods(persistence_service, required_methods)
    if persistence_enabled:
        ok = not method_state["missing"]
        mode = "persistent"
        warnings: list[str] = []
    else:
        ok = True
        mode = "fallback"
        warnings = ["当前未连接正式持久层，仅能以单实例/降级模式启动，不具备完整多实例守卫能力。"]
    return {
        "ok": ok,
        "mode": mode,
        "warnings": warnings,
        "methods": method_state,
    }


def run_check() -> dict[str, Any]:
    settings = get_settings()
    readiness = platform_readiness()
    persistence_contract = run_persistence_contract_check()
    nats_contract = run_nats_contract_check()
    readiness = _normalize_platform_readiness(
        readiness,
        persistence_contract=persistence_contract,
        nats_contract=nats_contract,
    )
    persistence_enabled = bool(getattr(persistence_service, "enabled", False)) or bool(
        persistence_contract.get("persistence_enabled")
    )

    dispatch_runtime = _runtime_mode(
        persistence_enabled=persistence_enabled,
        required_methods=(
            "claim_due_workflow_dispatch_jobs",
            "release_workflow_dispatch_job_claim",
            "list_workflow_dispatch_jobs",
            "claim_due_workflow_runs",
            "release_workflow_run_claim",
            "list_workflow_runs",
        ),
    )
    workflow_execution_runtime = _runtime_mode(
        persistence_enabled=persistence_enabled,
        required_methods=(
            "claim_due_workflow_execution_jobs",
            "claim_workflow_execution_job",
            "release_workflow_execution_job_claim",
            "delete_workflow_execution_job",
            "upsert_workflow_execution_job",
            "list_workflow_execution_jobs",
            "list_workflow_runs",
        ),
    )
    agent_execution_runtime = _runtime_mode(
        persistence_enabled=persistence_enabled,
        required_methods=(
            "claim_due_agent_execution_jobs",
            "claim_agent_execution_job",
            "release_agent_execution_job_claim",
            "delete_agent_execution_job",
            "upsert_agent_execution_job",
            "list_agent_execution_jobs",
            "list_workflow_runs",
            "list_tasks",
        ),
    )

    guard_methods = _check_methods(
        scheduler_guard_service,
        (
            "guard_dispatch_runtime",
            "guard_workflow_execution_runtime",
            "guard_agent_execution_runtime",
        ),
    )
    guard_runtime = {
        "ok": not guard_methods["missing"],
        "methods": guard_methods,
    }

    lease_check = {
        "ok": (
            DEFAULT_DISPATCH_LEASE_SECONDS > 0
            and DEFAULT_DISPATCH_POLL_INTERVAL_SECONDS > 0
            and settings.workflow_execution_lease_seconds > 0
            and settings.workflow_execution_poll_interval_seconds > 0
            and settings.workflow_execution_scan_limit > 0
        ),
        "summary": {
            "dispatch_lease_seconds": DEFAULT_DISPATCH_LEASE_SECONDS,
            "dispatch_poll_interval_seconds": DEFAULT_DISPATCH_POLL_INTERVAL_SECONDS,
            "workflow_execution_lease_seconds": settings.workflow_execution_lease_seconds,
            "workflow_execution_poll_interval_seconds": settings.workflow_execution_poll_interval_seconds,
            "workflow_execution_scan_limit": settings.workflow_execution_scan_limit,
        },
    }

    multi_instance_guard = {
        "ok": True,
        "mode": "enabled" if persistence_enabled else "degraded",
        "summary": {
            "persistence_enabled": persistence_enabled,
            "strict_multi_instance_ready": persistence_enabled,
        },
        "warnings": []
        if persistence_enabled
        else ["多实例守卫需要数据库真源；当前结果仅表示可启动，不表示已满足正式多实例部署条件。"],
    }

    checks = {
        "platform_readiness": {
            "ok": True,
            "summary": {
                **readiness,
                "persistence_contract": persistence_contract,
                "nats_contract": nats_contract,
            },
        },
        "dispatch_runtime": dispatch_runtime,
        "workflow_execution_runtime": workflow_execution_runtime,
        "agent_execution_runtime": agent_execution_runtime,
        "guard_runtime": guard_runtime,
        "lease_window": lease_check,
        "multi_instance_guard": multi_instance_guard,
    }
    return {
        "ok": all(bool(item.get("ok")) for item in checks.values()),
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run scheduler startup self-checks.")
    parser.add_argument("--strict", action="store_true")
    _ = parser.parse_args()

    payload = run_check()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if _.strict and not payload["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
