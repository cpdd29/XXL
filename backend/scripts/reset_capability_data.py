from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import delete, select


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
DEFAULT_REGISTRY_FILE = PROJECT_ROOT / "deploy" / "external-registry" / "workbot_external_sources.local.json"
CLEAR_SYSTEM_SETTING_KEYS = ("brain_skill_library",)

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.models import SystemSettingRecord  # noqa: E402
from app.platform.persistence.persistence_service import StatePersistenceService  # noqa: E402
from app.platform.persistence.runtime_store import InMemoryStore  # noqa: E402


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _resolve_registry_file(path: str | None) -> Path:
    if path:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = PROJECT_ROOT / candidate
        return candidate
    return DEFAULT_REGISTRY_FILE


def _load_registry_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": _utc_now_iso().split("T", 1)[0], "mode": "external_only", "sources": [], "tools": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Registry JSON 解析失败: {path} -> {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Registry 顶层结构必须是对象: {path}")
    return payload


def _empty_registry_payload(existing: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": _utc_now_iso().split("T", 1)[0],
        "mode": str(existing.get("mode") or "external_only").strip() or "external_only",
        "sources": [],
        "tools": [],
    }


def _write_registry_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _database_report(service: StatePersistenceService) -> dict[str, Any]:
    agents = service.list_agents() or []
    setting_keys: list[str] = []
    if service.enabled and service._session_factory is not None:
        with service._session_factory() as session:
            setting_keys = list(session.scalars(select(SystemSettingRecord.key).order_by(SystemSettingRecord.key)).all())
    return {
        "agent_ids": [str(item.get("id") or "").strip() for item in agents if str(item.get("id") or "").strip()],
        "system_setting_keys": setting_keys,
    }


def _clear_database_capability_data(service: StatePersistenceService) -> dict[str, Any]:
    if not service.enabled or service._session_factory is None:
        return {
            "database_enabled": False,
            "deleted_agent_count": 0,
            "deleted_agent_ids": [],
            "deleted_setting_count": 0,
            "deleted_setting_keys": [],
        }

    report = _database_report(service)
    agent_ids = report["agent_ids"]
    deleted_agent_count = service.delete_agent_states(agent_ids=agent_ids)

    deleted_setting_count = 0
    with service._session_factory() as session:
        result = session.execute(
            delete(SystemSettingRecord).where(SystemSettingRecord.key.in_(CLEAR_SYSTEM_SETTING_KEYS))
        )
        session.commit()
        deleted_setting_count = int(result.rowcount or 0)

    return {
        "database_enabled": True,
        "deleted_agent_count": deleted_agent_count,
        "deleted_agent_ids": agent_ids,
        "deleted_setting_count": deleted_setting_count,
        "deleted_setting_keys": list(CLEAR_SYSTEM_SETTING_KEYS),
    }


def run_capability_reset(
    *,
    database_url: str,
    registry_file: str | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    runtime_store = InMemoryStore()
    service = StatePersistenceService(runtime_store=runtime_store, database_url=database_url)
    initialized = service.initialize()
    registry_path = _resolve_registry_file(registry_file)
    before_registry = _load_registry_payload(registry_path)
    before_database = _database_report(service) if initialized else {"agent_ids": [], "system_setting_keys": []}

    result = {
        "ok": True,
        "mode": "apply" if apply else "dry_run",
        "database_url": database_url,
        "registry_file": str(registry_path),
        "before": {
            "agent_count": len(before_database["agent_ids"]),
            "agent_ids": before_database["agent_ids"],
            "system_setting_keys": before_database["system_setting_keys"],
            "registry_source_count": len(before_registry.get("sources") or []),
            "registry_tool_count": len(before_registry.get("tools") or []),
        },
        "changes": {
            "database": {
                "database_enabled": bool(initialized and service.enabled),
                "deleted_agent_count": 0,
                "deleted_agent_ids": [],
                "deleted_setting_count": 0,
                "deleted_setting_keys": list(CLEAR_SYSTEM_SETTING_KEYS),
            },
            "registry": {
                "cleared_source_count": len(before_registry.get("sources") or []),
                "cleared_tool_count": len(before_registry.get("tools") or []),
            },
        },
    }

    if not apply:
        if initialized:
            service.close()
        return result

    if initialized:
        result["changes"]["database"] = _clear_database_capability_data(service)

    _write_registry_payload(registry_path, _empty_registry_payload(before_registry))
    after_registry = _load_registry_payload(registry_path)
    after_database = _database_report(service) if initialized else {"agent_ids": [], "system_setting_keys": []}

    result["after"] = {
        "agent_count": len(after_database["agent_ids"]),
        "agent_ids": after_database["agent_ids"],
        "system_setting_keys": after_database["system_setting_keys"],
        "registry_source_count": len(after_registry.get("sources") or []),
        "registry_tool_count": len(after_registry.get("tools") or []),
    }

    if initialized:
        service.close()
    return result


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="清空本地 capability 数据（agent / skill / MCP registry）")
    parser.add_argument("--database-url", required=True, help="后端持久化数据库连接串")
    parser.add_argument("--registry-file", help="外部 tool registry 文件路径")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="真正执行清理；默认只输出 dry-run 结果",
    )
    return parser


def main() -> int:
    args = _build_arg_parser().parse_args()
    result = run_capability_reset(
        database_url=args.database_url,
        registry_file=args.registry_file,
        apply=bool(args.apply),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
