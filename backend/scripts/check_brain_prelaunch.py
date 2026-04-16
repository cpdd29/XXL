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

from app.core.nats_event_bus import nats_event_bus
from scripts.dr_result_gate import run_dr_result_gate
from scripts.check_external_ingress_bypass import run_external_ingress_bypass_check
from scripts.check_nats_contract import run_check as run_nats_contract_check
from scripts.check_nats_roundtrip import run_check as run_nats_roundtrip_check
from scripts.check_persistence_contract import run_persistence_contract_check
from scripts.check_release_preflight import run_preflight
from scripts.check_scheduler_runtime_pg_acceptance import (
    run_check as run_scheduler_runtime_pg_acceptance_check,
)
from scripts.check_security_audit_persistence import run_security_audit_persistence_check
from scripts.check_security_controls import run_security_control_check
from scripts.check_scheduler_startup import run_check as run_scheduler_startup_check
from scripts.check_security_entrypoints import run_security_entrypoint_check
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


def _strict_gate(
    *,
    key: str,
    ok: bool,
    summary: dict[str, Any],
    blockers: list[str],
    failure_message: str,
) -> dict[str, Any]:
    if not ok:
        blockers.append(failure_message)
    return {"key": key, "ok": ok, "summary": summary}


def _maybe_run_scheduler_runtime_pg_acceptance(
    *, persistence_contract: dict[str, Any]
) -> dict[str, Any]:
    database_url = str(persistence_contract.get("database_url") or "").strip()
    if not bool(persistence_contract.get("ok")) or not database_url:
        return {
            "ok": False,
            "ran": False,
            "skipped": True,
            "database_url": database_url,
            "skip_reason": "persistence_contract_not_ready",
        }
    try:
        payload = run_scheduler_runtime_pg_acceptance_check(database_url=database_url)
    except Exception as exc:  # pragma: no cover
        return {
            "ok": False,
            "ran": True,
            "skipped": False,
            "database_url": database_url,
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }
    return {
        **payload,
        "ran": True,
        "skipped": False,
        "database_url": database_url,
    }


def _maybe_run_nats_roundtrip(*, nats_contract: dict[str, Any]) -> dict[str, Any]:
    nats_url = str(nats_contract.get("nats_url") or "").strip()
    if (
        not bool(nats_contract.get("ok"))
        or not bool(nats_contract.get("connected"))
        or bool(nats_contract.get("fallback_mode"))
        or not nats_url
    ):
        return {
            "ok": False,
            "ran": False,
            "skipped": True,
            "nats_url": nats_url,
            "skip_reason": "nats_contract_not_ready",
        }
    try:
        payload = run_nats_roundtrip_check(nats_url=nats_url)
    except Exception as exc:  # pragma: no cover
        return {
            "ok": False,
            "ran": True,
            "skipped": False,
            "nats_url": nats_url,
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }
    return {
        **payload,
        "ran": True,
        "skipped": False,
        "nats_url": nats_url,
    }


def run_brain_prelaunch_check(*, repo_root: Path | None = None) -> dict[str, Any]:
    resolved_repo_root = (repo_root or REPO_ROOT).resolve()
    readiness = platform_readiness()
    persistence_contract = run_persistence_contract_check()
    nats_contract = run_nats_contract_check()
    readiness = _normalize_platform_readiness(
        readiness,
        persistence_contract=persistence_contract,
        nats_contract=nats_contract,
    )
    scheduler = run_scheduler_startup_check()
    scheduler_runtime_pg_acceptance = _maybe_run_scheduler_runtime_pg_acceptance(
        persistence_contract=persistence_contract
    )
    nats_roundtrip = _maybe_run_nats_roundtrip(nats_contract=nats_contract)
    release_preflight = run_preflight(
        resolved_repo_root,
        database_url=str(persistence_contract.get("database_url") or "").strip() or None,
        include_live_database=bool(persistence_contract.get("ok")),
    )
    security_controls = run_security_control_check()
    security_entrypoints = run_security_entrypoint_check(repo_root=resolved_repo_root)
    security_audit_persistence = run_security_audit_persistence_check()
    external_ingress_bypass = run_external_ingress_bypass_check(repo_root=resolved_repo_root)
    dr_result_gate = run_dr_result_gate(write_report=False)
    nats_transport = nats_event_bus.connection_snapshot()

    startup_ready = bool(scheduler.get("ok"))
    strict_blockers: list[str] = []
    strict_checks = [
        _strict_gate(
            key="persistent_truth_source_ready",
            ok=bool(persistence_contract.get("ok")),
            summary={
                "persistence_enabled": bool(readiness.get("persistence_enabled")),
                "contract": persistence_contract,
            },
            blockers=strict_blockers,
            failure_message="未接入正式数据库真源，当前仍处于 fallback/degraded 启动模式。",
        ),
        _strict_gate(
            key="nats_transport_ready",
            ok=bool(nats_contract.get("connected"))
            and bool(nats_contract.get("ok"))
            and (not nats_roundtrip.get("ran") or bool(nats_roundtrip.get("ok"))),
            summary={
                "nats_connected": bool(readiness.get("nats_connected")),
                "fallback_event_bus_available": bool(readiness.get("fallback_event_bus_available")),
                "transport": nats_transport,
                "contract": nats_contract,
                "roundtrip": nats_roundtrip,
            },
            blockers=strict_blockers,
            failure_message="NATS 未建立正式连接，或真实 roundtrip/queue-group 验收未通过。",
        ),
        _strict_gate(
            key="scheduler_multi_instance_ready",
            ok=bool(
                ((scheduler.get("checks") or {}).get("multi_instance_guard") or {}).get("summary", {})
                .get("strict_multi_instance_ready")
            )
            and (
                not scheduler_runtime_pg_acceptance.get("ran")
                or bool(scheduler_runtime_pg_acceptance.get("ok"))
            ),
            summary={
                "multi_instance_guard": ((scheduler.get("checks") or {}).get("multi_instance_guard") or {}),
                "pg_acceptance": scheduler_runtime_pg_acceptance,
            },
            blockers=strict_blockers,
            failure_message="调度守卫尚未进入 strict multi-instance ready 状态，或真实数据库 claim/takeover 验收未通过。",
        ),
        _strict_gate(
            key="scheduler_runtime_persistent",
            # 真数据库接上后，要求 claim/release/reclaim/reopen 的运行态验收也通过。
            ok=all(
                str((((scheduler.get("checks") or {}).get(key_name) or {}).get("mode") or "")).strip()
                == "persistent"
                for key_name in (
                    "dispatch_runtime",
                    "workflow_execution_runtime",
                    "agent_execution_runtime",
                )
            )
            and (
                not scheduler_runtime_pg_acceptance.get("ran")
                or bool(scheduler_runtime_pg_acceptance.get("ok"))
            ),
            summary={
                "dispatch_runtime": ((scheduler.get("checks") or {}).get("dispatch_runtime") or {}),
                "workflow_execution_runtime": (
                    (scheduler.get("checks") or {}).get("workflow_execution_runtime") or {}
                ),
                "agent_execution_runtime": (
                    (scheduler.get("checks") or {}).get("agent_execution_runtime") or {}
                ),
                "pg_acceptance": scheduler_runtime_pg_acceptance,
            },
            blockers=strict_blockers,
            failure_message="dispatcher / worker 仍未全部进入 persistent runtime 模式，或真实数据库运行态验收未通过。",
        ),
        _strict_gate(
            key="security_entrypoint_coverage",
            ok=bool(security_entrypoints.get("ok")),
            summary={
                **security_entrypoints,
            },
            blockers=strict_blockers,
            failure_message="外部入口未全部纳入统一安全检查链路。",
        ),
        _strict_gate(
            key="security_controls_ready",
            ok=bool(security_controls.get("ok")),
            summary=security_controls,
            blockers=strict_blockers,
            failure_message="统一安全控制烟雾验收未通过。",
        ),
        _strict_gate(
            key="security_audit_persistence_ready",
            ok=bool(security_audit_persistence.get("ok")),
            summary=security_audit_persistence,
            blockers=strict_blockers,
            failure_message="安全审计未稳定落入数据库真源或关键 metadata 丢失。",
        ),
        _strict_gate(
            key="external_ingress_bypass_scan_ready",
            ok=bool(external_ingress_bypass.get("ok")),
            summary=external_ingress_bypass,
            blockers=strict_blockers,
            failure_message="外部入口绕过扫描未通过，仍存在未纳入基线保护的公开入口。",
        ),
        _strict_gate(
            key="dr_result_gate_ready",
            ok=bool(dr_result_gate.get("ok")),
            summary=dr_result_gate,
            blockers=strict_blockers,
            failure_message="容灾结果门禁未通过，缺少完整演练结果包或关键 RTO/RPO/人工介入统计。",
        ),
        _strict_gate(
            key="release_preflight_green",
            ok=bool(release_preflight.get("ok")),
            summary=release_preflight,
            blockers=strict_blockers,
            failure_message="发布预检未通过，当前代码或部署面仍有阻塞项。",
        ),
        _strict_gate(
            key="runbook_and_result_template_ready",
            ok=bool(readiness.get("runbook_exists")) and bool(readiness.get("result_template_exists")),
            summary={
                "runbook_exists": bool(readiness.get("runbook_exists")),
                "result_template_exists": bool(readiness.get("result_template_exists")),
            },
            blockers=strict_blockers,
            failure_message="容灾 runbook 或结果模板缺失，无法进入正式上线窗口。",
        ),
    ]
    production_ready = all(item["ok"] for item in strict_checks)
    status = "production_ready" if production_ready else ("degraded_startable" if startup_ready else "blocked")
    return {
        "ok": startup_ready,
        "startup_ready": startup_ready,
        "production_ready": production_ready,
        "status": status,
        "checks": {
            "platform_readiness": readiness,
            "persistence_contract": persistence_contract,
            "nats_contract": nats_contract,
            "scheduler_startup": scheduler,
            "scheduler_runtime_pg_acceptance": scheduler_runtime_pg_acceptance,
            "release_preflight": release_preflight,
            "security_controls": security_controls,
            "security_entrypoints": security_entrypoints,
            "security_audit_persistence": security_audit_persistence,
            "external_ingress_bypass": external_ingress_bypass,
            "dr_result_gate": dr_result_gate,
            "nats_roundtrip": nats_roundtrip,
            "nats_transport": nats_transport,
            "strict_gates": strict_checks,
        },
        "strict_blockers": strict_blockers,
        "summary": {
            "degraded_startable": startup_ready and not production_ready,
            "strict_gate_count": len(strict_checks),
            "strict_passed": len([item for item in strict_checks if item["ok"]]),
            "strict_failed": len([item for item in strict_checks if not item["ok"]]),
            "strict_failed_keys": [item["key"] for item in strict_checks if not item["ok"]],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run brain prelaunch readiness gates.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--strict-startup", action="store_true")
    parser.add_argument("--strict-production", action="store_true")
    args = parser.parse_args()

    payload = run_brain_prelaunch_check(repo_root=Path(args.repo_root))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.strict_production and not payload["production_ready"]:
        return 1
    if args.strict_startup and not payload["startup_ready"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
