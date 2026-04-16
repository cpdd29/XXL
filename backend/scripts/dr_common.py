from __future__ import annotations

import json
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
import re
from typing import Any

from fastapi import HTTPException

from scripts.package_t_common import REPORTS_ROOT, render_markdown_report, write_json_report

from app.config import get_settings
from app.core.nats_event_bus import nats_event_bus
from app.services.dashboard_service import get_audit_logs
from app.services.external_agent_registry_service import external_agent_registry_service
from app.services.external_skill_registry_service import external_skill_registry_service
from app.services.persistence_service import persistence_service
from app.services.security_service import (
    get_security_report,
    list_active_security_penalties,
    list_security_rules,
)
from app.services.task_service import get_task, list_tasks
from app.services.tenancy_service import default_scope
from app.services.workflow_service import get_run, list_runs


BACKEND_ROOT = Path(__file__).resolve().parents[1]
ENV_REPO_ROOT = str(os.getenv("WORKBOT_REPO_ROOT") or "").strip()


def _resolve_repo_root() -> Path:
    candidates: list[Path] = []
    if ENV_REPO_ROOT:
        candidates.append(Path(ENV_REPO_ROOT).expanduser())
    candidates.extend([BACKEND_ROOT.parent, Path("/workspace")])
    for candidate in candidates:
        resolved = candidate.resolve()
        if (resolved / "docs" / "brain" / "BRAIN_DR_RUNBOOK.md").exists():
            return resolved
        if (resolved / "docker-compose.yml").exists() and (resolved / "backend").exists():
            return resolved
    return BACKEND_ROOT.parent.resolve()


REPO_ROOT = _resolve_repo_root()
RUNBOOK_PATH = REPO_ROOT / "docs" / "brain" / "BRAIN_DR_RUNBOOK.md"
RESULT_TEMPLATE_PATH = REPORTS_ROOT / "dr_drill_result_template.md"
DEFAULT_DR_REPORT_PREFIX = "dr"
DEFAULT_SCOPE = default_scope()
DR_OBJECTIVES = {
    "brain_api_failover_rto_seconds": 300,
    "external_reregistration_rto_seconds": 600,
    "observability_restore_rto_seconds": 600,
    "truth_source_rpo_seconds": 60,
    "audit_rpo_seconds": 0,
}
FAILOVER_STEP_PLAN = [
    {
        "order": 1,
        "step_key": "freeze_inbound",
        "title": "冻结入站",
        "kind": "manual_gate",
        "description": "停止新的 Adapter / Webhook / 手工入口写入，防止切换过程继续接单。",
        "automation_hint": "由 failover_prepare 输出冻结前基线与恢复后验证命令。",
    },
    {
        "order": 2,
        "step_key": "confirm_old_primary_unavailable",
        "title": "确认旧主失效",
        "kind": "manual_gate",
        "description": "确认旧主脑机房不可继续承载写流量，防止双主或脑裂。",
        "automation_hint": "在切换前记录故障窗口开始时间，供 post_failover_verify 计算 RTO。",
    },
    {
        "order": 3,
        "step_key": "promote_truth_source",
        "title": "提升数据库真源",
        "kind": "manual_gate",
        "description": "将 Standby 机房真源提升为唯一主源，并保持 audit / security 先行一致。",
        "automation_hint": "failover_prepare 提供 task/run/audit/security 基线快照。",
    },
    {
        "order": 4,
        "step_key": "activate_standby_brain",
        "title": "提升 Standby Brain",
        "kind": "manual_gate",
        "description": "启动备用主脑控制面并承接裁决权。",
        "automation_hint": "post_failover_verify 会验证主脑真源连续性。",
    },
    {
        "order": 5,
        "step_key": "restore_internal_nats",
        "title": "恢复 NATS",
        "kind": "check",
        "description": "恢复内部事件总线或确认 fallback in-process bus 正常可用。",
        "automation_hint": "post_failover_verify:nats_or_fallback_ready",
    },
    {
        "order": 6,
        "step_key": "restore_external_registry",
        "title": "恢复外接注册中心",
        "kind": "check",
        "description": "让外接 Agent / Skill 注册中心重新接受实例回连。",
        "automation_hint": "external_tentacle_recovery:registry_inventory_loaded",
    },
    {
        "order": 7,
        "step_key": "reregister_external_tentacles",
        "title": "触手重新注册",
        "kind": "check",
        "description": "校验外接 Agent / Skill / MCP 在备用机房重新注册并恢复心跳。",
        "automation_hint": "external_tentacle_recovery:family_recovered",
    },
    {
        "order": 8,
        "step_key": "reopen_ingress",
        "title": "恢复消息入口",
        "kind": "manual_gate",
        "description": "在主脑真源和触手恢复完成后重新开放消息入口。",
        "automation_hint": "仅在 post_failover_verify 通过后执行。",
    },
    {
        "order": 9,
        "step_key": "verify_control_plane_truths",
        "title": "校验协作 / 审计 / 安全中心",
        "kind": "check",
        "description": "验证 task/run/audit/security 真源连续，协作与控制面可读。",
        "automation_hint": "post_failover_verify:truth_source_continuity",
    },
]


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def parse_datetime(value: str | None) -> datetime | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(normalized, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


_REPORT_TIMESTAMP_RE = re.compile(r"(?P<stamp>\d{8}_\d{6})")


def _report_sort_key(path: Path) -> tuple[datetime, int, str]:
    stamp_match = None
    for match in _REPORT_TIMESTAMP_RE.finditer(path.stem):
        stamp_match = match

    parsed_stamp: datetime
    if stamp_match is not None:
        try:
            parsed_stamp = datetime.strptime(stamp_match.group("stamp"), "%Y%m%d_%H%M%S").replace(tzinfo=UTC)
        except ValueError:
            parsed_stamp = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    else:
        parsed_stamp = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)

    return (parsed_stamp, path.stat().st_mtime_ns, path.name)


def find_latest_report(prefix: str) -> Path | None:
    candidates = list(REPORTS_ROOT.glob(f"{prefix}_*.json"))
    if not candidates:
        return None
    return max(candidates, key=_report_sort_key)


def resolve_report_path(report_path: str | None, *, default_prefix: str) -> Path:
    if report_path:
        resolved = Path(report_path).expanduser().resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Report not found: {resolved}")
        return resolved
    latest = find_latest_report(default_prefix)
    if latest is None:
        raise FileNotFoundError(
            f"No report found for prefix '{default_prefix}' under {REPORTS_ROOT}"
        )
    return latest


def load_drill_report(report_path: str | None, *, default_prefix: str) -> tuple[Path, dict[str, Any]]:
    resolved = resolve_report_path(report_path, default_prefix=default_prefix)
    return resolved, load_json(resolved)


def drill_baseline_truth_sources(payload: dict[str, Any]) -> dict[str, Any]:
    baseline = payload.get("baseline") if isinstance(payload.get("baseline"), dict) else {}
    if isinstance(baseline.get("truth_sources"), dict):
        return dict(baseline.get("truth_sources") or {})
    if isinstance(payload.get("baseline_truth_sources"), dict):
        return dict(payload.get("baseline_truth_sources") or {})
    return {}


def drill_baseline_external_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    baseline = payload.get("baseline") if isinstance(payload.get("baseline"), dict) else {}
    if isinstance(baseline.get("external_manifest"), dict):
        return dict(baseline.get("external_manifest") or {})
    if isinstance(payload.get("baseline_external_manifest"), dict):
        return dict(payload.get("baseline_external_manifest") or {})
    return {}


def drill_failover_started_at(payload: dict[str, Any]) -> str | None:
    timeline = payload.get("timeline") if isinstance(payload.get("timeline"), dict) else {}
    return str(timeline.get("failover_started_at") or payload.get("failover_started_at") or "").strip() or None


def _status_counts(items: list[dict[str, Any]], field: str = "status") -> dict[str, int]:
    counter = Counter(str(item.get(field) or "unknown").strip().lower() or "unknown" for item in items)
    return dict(counter)


def _sample_ids(items: list[dict[str, Any]], *, limit: int = 10) -> list[str]:
    values: list[str] = []
    for item in items:
        identifier = str(item.get("id") or "").strip()
        if identifier:
            values.append(identifier)
        if len(values) >= limit:
            break
    return values


def _latest_timestamp(items: list[dict[str, Any]], fields: tuple[str, ...]) -> str | None:
    candidates = [
        parsed
        for item in items
        for field in fields
        if (parsed := parse_datetime(str(item.get(field) or "").strip())) is not None
    ]
    if not candidates:
        return None
    return max(candidates).isoformat()


def truth_source_snapshot(*, scope: dict[str, str] | None = None) -> dict[str, Any]:
    resolved_scope = scope or DEFAULT_SCOPE
    tasks_payload = list_tasks(scope=resolved_scope)
    task_items = list(tasks_payload.get("items") or [])
    runs_payload = list_runs(scope=resolved_scope)
    run_items = list(runs_payload.get("items") or [])
    audits_payload = get_audit_logs(limit=50, scope=resolved_scope)
    audit_items = list(audits_payload.get("items") or [])
    security_report = get_security_report(window_hours=24)
    penalties = list_active_security_penalties()
    rules = list_security_rules()
    recent_incidents = list(security_report.get("recent_incidents") or [])

    return {
        "captured_at": utc_now_iso(),
        "scope": dict(resolved_scope),
        "tasks": {
            "total": int(tasks_payload.get("total") or 0),
            "by_status": _status_counts(task_items),
            "sample_ids": _sample_ids(task_items),
            "latest_created_at": _latest_timestamp(task_items, ("created_at", "completed_at")),
        },
        "runs": {
            "total": int(runs_payload.get("total") or 0),
            "by_status": _status_counts(run_items),
            "sample_ids": _sample_ids(run_items),
            "latest_updated_at": _latest_timestamp(run_items, ("updated_at", "created_at")),
        },
        "audit": {
            "total": int(audits_payload.get("total") or 0),
            "by_status": _status_counts(audit_items),
            "sample_ids": _sample_ids(audit_items),
            "latest_timestamp": _latest_timestamp(audit_items, ("timestamp",)),
        },
        "security": {
            "summary": dict(security_report.get("summary") or {}),
            "active_penalties": int(penalties.get("total") or 0),
            "rule_total": int(rules.get("total") or 0),
            "recent_incident_ids": _sample_ids(recent_incidents, limit=8),
            "latest_incident_at": _latest_timestamp(recent_incidents, ("timestamp",)),
        },
    }


def _heartbeat_age_seconds(value: str | None, *, now: datetime) -> float | None:
    parsed = parse_datetime(value)
    if parsed is None:
        return None
    return round((now - parsed).total_seconds(), 2)


def external_recovery_manifest(*, max_heartbeat_age_seconds: int = 600) -> dict[str, Any]:
    now = datetime.now(UTC)
    agent_items = external_agent_registry_service.list_agents(include_offline=True)
    skill_items = external_skill_registry_service.list_skills(include_offline=True)

    def normalize_agent(item: dict[str, Any]) -> dict[str, Any]:
        config_summary = item.get("config_summary") if isinstance(item.get("config_summary"), dict) else {}
        invocation = config_summary.get("invocation") if isinstance(config_summary.get("invocation"), dict) else {}
        heartbeat_age = _heartbeat_age_seconds(item.get("last_heartbeat_at"), now=now)
        return {
            "capability_type": "agent",
            "id": str(item.get("id") or ""),
            "family": str(item.get("agent_family") or item.get("id") or ""),
            "name": str(item.get("name") or item.get("id") or ""),
            "version": str(item.get("version") or ""),
            "status": str(item.get("runtime_status") or item.get("status") or "unknown"),
            "routable": bool(item.get("routable")),
            "circuit_state": str(item.get("circuit_state") or ""),
            "last_heartbeat_at": item.get("last_heartbeat_at"),
            "heartbeat_age_seconds": heartbeat_age,
            "stale_heartbeat": heartbeat_age is not None and heartbeat_age > max_heartbeat_age_seconds,
            "base_url": invocation.get("base_url"),
            "invoke_path": invocation.get("invoke_path"),
            "health_path": invocation.get("health_path"),
        }

    def normalize_skill(item: dict[str, Any]) -> dict[str, Any]:
        invocation = item.get("invocation") if isinstance(item.get("invocation"), dict) else {}
        heartbeat_age = _heartbeat_age_seconds(item.get("last_heartbeat_at"), now=now)
        return {
            "capability_type": "skill",
            "id": str(item.get("id") or ""),
            "family": str(item.get("skill_family") or item.get("id") or ""),
            "name": str(item.get("name") or item.get("id") or ""),
            "version": str(item.get("version") or ""),
            "status": str(item.get("health_status") or "unknown"),
            "routable": bool(item.get("routable")),
            "circuit_state": str(item.get("circuit_state") or ""),
            "last_heartbeat_at": item.get("last_heartbeat_at"),
            "heartbeat_age_seconds": heartbeat_age,
            "stale_heartbeat": heartbeat_age is not None and heartbeat_age > max_heartbeat_age_seconds,
            "base_url": invocation.get("base_url"),
            "invoke_path": invocation.get("invoke_path"),
            "health_path": invocation.get("health_path"),
        }

    agents = [normalize_agent(item) for item in agent_items]
    skills = [normalize_skill(item) for item in skill_items]
    all_items = [*agents, *skills]
    stale_items = [
        {
            "capability_type": item["capability_type"],
            "id": item["id"],
            "family": item["family"],
            "heartbeat_age_seconds": item["heartbeat_age_seconds"],
        }
        for item in all_items
        if item["stale_heartbeat"]
    ]
    return {
        "captured_at": utc_now_iso(),
        "summary": {
            "agent_families": len({item["family"] for item in agents if item["family"]}),
            "skill_families": len({item["family"] for item in skills if item["family"]}),
            "agent_instances": len(agents),
            "skill_instances": len(skills),
            "routable_instances": len([item for item in all_items if item["routable"]]),
            "offline_instances": len([item for item in all_items if item["status"] in {"offline", "unknown"}]),
            "open_circuits": len([item for item in all_items if item["circuit_state"] == "open"]),
            "stale_heartbeats": len(stale_items),
        },
        "stale_items": stale_items,
        "agents": agents,
        "skills": skills,
    }


def platform_readiness() -> dict[str, Any]:
    settings = get_settings()
    warnings: list[str] = []
    if not getattr(persistence_service, "enabled", False):
        warnings.append("当前未连接正式持久层，真源校验将基于内存/降级模式。")
    if not nats_event_bus.is_connected():
        warnings.append("NATS 当前未建立连接，将以 in-process fallback 视为可降级运行。")
    if not RUNBOOK_PATH.exists():
        warnings.append("未找到 docs/brain/BRAIN_DR_RUNBOOK.md。")
    if not RESULT_TEMPLATE_PATH.exists():
        warnings.append("未找到容灾演练结果模板。")
    return {
        "captured_at": utc_now_iso(),
        "environment": str(settings.environment or "").strip() or "development",
        "persistence_enabled": bool(getattr(persistence_service, "enabled", False)),
        "nats_connected": nats_event_bus.is_connected(),
        "fallback_event_bus_available": True,
        "runbook_exists": RUNBOOK_PATH.exists(),
        "result_template_exists": RESULT_TEMPLATE_PATH.exists(),
        "warnings": warnings,
    }


def runbook_step_plan() -> list[dict[str, Any]]:
    return [dict(item) for item in FAILOVER_STEP_PLAN]


def build_drill_result_template(
    *,
    drill_name: str,
    scenario: str,
    drill_kind: str = "formal",
    evidence_level: str = "full",
    operator_notes: str = "",
    failover_started_at: str | None = None,
    baseline_truth_sources: dict[str, Any] | None = None,
    baseline_external_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "drill_name": drill_name,
        "scenario": scenario,
        "generated_at": utc_now_iso(),
        "objectives": dict(DR_OBJECTIVES),
        "timeline": {
            "failover_started_at": failover_started_at,
            "verified_at": None,
        },
        "baseline": {
            "truth_sources": baseline_truth_sources or {},
            "external_manifest": baseline_external_manifest or {},
        },
        "post_state": {
            "truth_sources": {},
            "external_manifest": {},
        },
        "checks": [],
        "failed_steps": [],
        "evidence": {
            "drill_kind": str(drill_kind or "formal").strip().lower() or "formal",
            "evidence_level": str(evidence_level or "full").strip().lower() or "full",
            "operator_notes": str(operator_notes or "").strip(),
        },
        "measurements": {
            "rto_seconds": None,
            "external_recovery_rto_seconds": None,
            "estimated_rpo_seconds": None,
            "estimated_lost_records": 0,
        },
        "status": "pending",
    }


def drill_gate_stats(
    *,
    failed_steps: list[str] | None = None,
    step_plan: list[dict[str, Any]] | None = None,
    manual_intervention_steps: list[str] | None = None,
) -> dict[str, int]:
    resolved_failed_steps = [str(item).strip() for item in (failed_steps or []) if str(item).strip()]
    if manual_intervention_steps is not None:
        manual_steps = [str(item).strip() for item in manual_intervention_steps if str(item).strip()]
    else:
        manual_steps = [
            str(item.get("step_key") or item.get("title") or "").strip()
            for item in (step_plan or [])
            if str(item.get("kind") or "").strip() == "manual_gate"
            and str(item.get("step_key") or item.get("title") or "").strip()
        ]
    return {
        "failed": len(resolved_failed_steps),
        "manual_intervention": len(manual_steps),
    }


def _task_exists(task_id: str) -> bool:
    try:
        get_task(task_id, scope=DEFAULT_SCOPE)
        return True
    except HTTPException:
        return False


def _run_exists(run_id: str) -> bool:
    try:
        get_run(run_id, scope=DEFAULT_SCOPE)
        return True
    except HTTPException:
        return False


def _audit_ids(limit: int = 200) -> set[str]:
    payload = get_audit_logs(limit=limit, scope=DEFAULT_SCOPE)
    return {
        str(item.get("id") or "").strip()
        for item in payload.get("items") or []
        if str(item.get("id") or "").strip()
    }


def estimate_rpo_seconds(baseline: dict[str, Any], current: dict[str, Any]) -> float:
    candidate_pairs = (
        (
            parse_datetime(baseline.get("tasks", {}).get("latest_created_at")),
            parse_datetime(current.get("tasks", {}).get("latest_created_at")),
        ),
        (
            parse_datetime(baseline.get("runs", {}).get("latest_updated_at")),
            parse_datetime(current.get("runs", {}).get("latest_updated_at")),
        ),
        (
            parse_datetime(baseline.get("audit", {}).get("latest_timestamp")),
            parse_datetime(current.get("audit", {}).get("latest_timestamp")),
        ),
        (
            parse_datetime(baseline.get("security", {}).get("latest_incident_at")),
            parse_datetime(current.get("security", {}).get("latest_incident_at")),
        ),
    )
    deltas = []
    for baseline_ts, current_ts in candidate_pairs:
        if baseline_ts is None or current_ts is None:
            continue
        if current_ts < baseline_ts:
            deltas.append((baseline_ts - current_ts).total_seconds())
    if not deltas:
        return 0.0
    return round(max(deltas), 2)


def compare_truth_source_snapshots(
    baseline: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any]:
    baseline_task_ids = list(baseline.get("tasks", {}).get("sample_ids") or [])
    baseline_run_ids = list(baseline.get("runs", {}).get("sample_ids") or [])
    baseline_audit_ids = list(baseline.get("audit", {}).get("sample_ids") or [])
    baseline_incident_ids = list(baseline.get("security", {}).get("recent_incident_ids") or [])

    missing_task_ids = [item for item in baseline_task_ids if not _task_exists(item)]
    missing_run_ids = [item for item in baseline_run_ids if not _run_exists(item)]
    current_audit_ids = _audit_ids(limit=max(200, len(baseline_audit_ids) * 10 or 50))
    missing_audit_ids = [item for item in baseline_audit_ids if item not in current_audit_ids]
    current_incident_ids = set(current.get("security", {}).get("recent_incident_ids") or [])
    missing_incident_ids = [item for item in baseline_incident_ids if item not in current_incident_ids]

    checks = [
        {
            "key": "task_truth_continuity",
            "ok": not missing_task_ids and int(current.get("tasks", {}).get("total") or 0) >= int(baseline.get("tasks", {}).get("total") or 0),
            "details": {
                "baseline_total": int(baseline.get("tasks", {}).get("total") or 0),
                "current_total": int(current.get("tasks", {}).get("total") or 0),
                "missing_task_ids": missing_task_ids,
            },
        },
        {
            "key": "run_truth_continuity",
            "ok": not missing_run_ids and int(current.get("runs", {}).get("total") or 0) >= int(baseline.get("runs", {}).get("total") or 0),
            "details": {
                "baseline_total": int(baseline.get("runs", {}).get("total") or 0),
                "current_total": int(current.get("runs", {}).get("total") or 0),
                "missing_run_ids": missing_run_ids,
            },
        },
        {
            "key": "audit_truth_continuity",
            "ok": not missing_audit_ids and int(current.get("audit", {}).get("total") or 0) >= int(baseline.get("audit", {}).get("total") or 0),
            "details": {
                "baseline_total": int(baseline.get("audit", {}).get("total") or 0),
                "current_total": int(current.get("audit", {}).get("total") or 0),
                "missing_audit_ids": missing_audit_ids,
            },
        },
        {
            "key": "security_truth_continuity",
            "ok": (
                not missing_incident_ids
                and int(current.get("security", {}).get("rule_total") or 0) >= int(baseline.get("security", {}).get("rule_total") or 0)
                and int((current.get("security", {}).get("summary") or {}).get("active_rules") or 0)
                >= int((baseline.get("security", {}).get("summary") or {}).get("active_rules") or 0)
            ),
            "details": {
                "baseline_rules": int(baseline.get("security", {}).get("rule_total") or 0),
                "current_rules": int(current.get("security", {}).get("rule_total") or 0),
                "missing_incident_ids": missing_incident_ids,
            },
        },
    ]
    failed_steps = [item["key"] for item in checks if not item["ok"]]
    estimated_lost_records = (
        len(missing_task_ids)
        + len(missing_run_ids)
        + len(missing_audit_ids)
        + len(missing_incident_ids)
    )
    return {
        "ok": not failed_steps,
        "checks": checks,
        "failed_steps": failed_steps,
        "estimated_rpo_seconds": estimate_rpo_seconds(baseline, current),
        "estimated_lost_records": estimated_lost_records,
    }


def compare_external_manifests(
    baseline: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any]:
    baseline_agents = {item.get("family") for item in baseline.get("agents") or [] if item.get("family")}
    baseline_skills = {item.get("family") for item in baseline.get("skills") or [] if item.get("family")}
    current_agents = {item.get("family") for item in current.get("agents") or [] if item.get("family")}
    current_skills = {item.get("family") for item in current.get("skills") or [] if item.get("family")}
    baseline_summary = baseline.get("summary") if isinstance(baseline.get("summary"), dict) else {}
    current_summary = current.get("summary") if isinstance(current.get("summary"), dict) else {}
    baseline_instance_total = int(baseline_summary.get("agent_instances") or 0) + int(
        baseline_summary.get("skill_instances") or 0
    )
    current_instance_total = int(current_summary.get("agent_instances") or 0) + int(
        current_summary.get("skill_instances") or 0
    )

    missing_agent_families = sorted(baseline_agents - current_agents)
    missing_skill_families = sorted(baseline_skills - current_skills)
    stale_items = list(current.get("stale_items") or [])
    open_circuits = int(current_summary.get("open_circuits") or 0)

    checks = [
        {
            "key": "registry_inventory_loaded",
            "ok": current_instance_total > 0 or baseline_instance_total == 0,
            "details": {
                "baseline_instance_total": baseline_instance_total,
                "current_instance_total": current_instance_total,
                **current_summary,
            },
        },
        {
            "key": "family_recovered",
            "ok": not missing_agent_families and not missing_skill_families,
            "details": {
                "missing_agent_families": missing_agent_families,
                "missing_skill_families": missing_skill_families,
            },
        },
        {
            "key": "stale_heartbeats_cleared",
            "ok": not stale_items,
            "details": {"stale_items": stale_items},
        },
        {
            "key": "open_circuits_cleared",
            "ok": open_circuits == 0,
            "details": {"open_circuits": open_circuits},
        },
    ]
    failed_steps = [item["key"] for item in checks if not item["ok"]]
    return {
        "ok": not failed_steps,
        "checks": checks,
        "failed_steps": failed_steps,
        "missing_agent_families": missing_agent_families,
        "missing_skill_families": missing_skill_families,
    }


def elapsed_seconds(started_at: str | None, finished_at: str | None = None) -> float | None:
    started = parse_datetime(started_at)
    finished = parse_datetime(finished_at) if finished_at else datetime.now(UTC)
    if started is None or finished is None:
        return None
    return round(max(0.0, (finished - started).total_seconds()), 2)


def write_drill_report(
    *,
    prefix: str,
    title: str,
    payload: dict[str, Any],
    sections: list[tuple[str, dict[str, Any]]],
) -> tuple[Path, Path]:
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    json_path = REPORTS_ROOT / f"{prefix}_{timestamp}.json"
    md_path = REPORTS_ROOT / f"{prefix}_{timestamp}.md"
    write_json_report(json_path, payload)
    md_path.write_text(render_markdown_report(title, sections), encoding="utf-8")
    return json_path, md_path
