from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import sys
from typing import Any, Callable

from sqlalchemy import text


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.agent_protocol import PROTOCOL_SPEC_VERSION
from app.db.session import create_engine_for_url
from app.config import get_settings
from app.services.external_agent_registry_service import DEFAULT_COMPATIBILITY as AGENT_COMPATIBILITY
from app.services.external_skill_registry_service import DEFAULT_COMPATIBILITY as SKILL_COMPATIBILITY
from scripts.check_production_env_contract import run_check as run_production_env_contract_check

ACCEPTANCE_TEMPLATE_FILES = {
    "package_a_multi_instance": "backend/docs/PACKAGE_A_MULTI_INSTANCE_ACCEPTANCE_TEMPLATE.md",
    "package_d_external_tentacles": "backend/docs/PACKAGE_D_EXTERNAL_ACCEPTANCE_TEMPLATE.md",
    "package_e_security": "backend/docs/PACKAGE_E_SECURITY_ACCEPTANCE_TEMPLATE.md",
}


def load_frontend_version(repo_root: Path) -> str:
    package_json = json.loads((repo_root / "reception" / "package.json").read_text(encoding="utf-8"))
    return str(package_json.get("version") or "0.0.0")


def load_alembic_chain(versions_root: Path) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for path in sorted(versions_root.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        values: dict[str, str] = {"file": str(path.name)}
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                continue
            key = node.targets[0].id
            if key not in {"revision", "down_revision"}:
                continue
            if isinstance(node.value, ast.Constant):
                values[key] = str(node.value.value) if node.value.value is not None else "None"
        items.append(values)
    return items


def validate_alembic_chain(chain: list[dict[str, str]]) -> tuple[bool, dict[str, Any]]:
    revision_map = {item.get("revision"): item for item in chain if item.get("revision")}
    down_refs = [
        item.get("down_revision")
        for item in chain
        if item.get("down_revision") not in {None, "None", ""}
    ]
    heads = [item["revision"] for item in chain if item.get("revision") not in down_refs]
    roots = [item["revision"] for item in chain if item.get("down_revision") in {None, "None", ""}]
    missing_down_revisions = sorted({ref for ref in down_refs if ref not in revision_map})
    ok = len(heads) == 1 and len(roots) == 1 and not missing_down_revisions
    return ok, {
        "total_revisions": len(chain),
        "heads": heads,
        "roots": roots,
        "missing_down_revisions": missing_down_revisions,
    }


def validate_compose_guards(repo_root: Path) -> tuple[bool, dict[str, Any]]:
    compose_text = (repo_root / "docker-compose.yml").read_text(encoding="utf-8")
    required_services = ("postgres:", "redis:", "nats:", "chromadb:", "backend:", "frontend:")
    missing_services = [name.rstrip(":") for name in required_services if name not in compose_text]
    required_healthchecks = ("postgres:", "redis:")
    healthcheck_gaps = [
        name.rstrip(":")
        for name in required_healthchecks
        if f"{name}\n" in compose_text and "healthcheck:" not in compose_text.split(name, 1)[1].split("\n\n", 1)[0]
    ]
    backend_has_depends_on = "backend:" in compose_text and "depends_on:" in compose_text.split("backend:", 1)[1]
    legacy_external_services = (
        "search-mcp:",
        "pdf-mcp:",
        "writer-mcp:",
        "weather-mcp:",
        "order-query-mcp:",
        "crm-query-mcp:",
    )
    leaked_external_services = [name.rstrip(":") for name in legacy_external_services if f"\n  {name}" in compose_text]
    backend_section = compose_text.split("backend:", 1)[1] if "backend:" in compose_text else ""
    backend_has_external_registry_mount = "deploy/external-registry" in backend_section
    backend_has_external_registry_env = "WORKBOT_EXTERNAL_TOOL_SOURCES_FILE" in backend_section
    backend_has_host_gateway = "host.docker.internal:host-gateway" in backend_section
    backend_runs_migrations = "alembic upgrade head" in backend_section
    ok = (
        not missing_services
        and not healthcheck_gaps
        and backend_has_depends_on
        and not leaked_external_services
        and backend_has_external_registry_mount
        and backend_has_external_registry_env
        and backend_has_host_gateway
        and backend_runs_migrations
    )
    return ok, {
        "missing_services": missing_services,
        "healthcheck_gaps": healthcheck_gaps,
        "backend_has_depends_on": backend_has_depends_on,
        "leaked_external_services": leaked_external_services,
        "backend_has_external_registry_mount": backend_has_external_registry_mount,
        "backend_has_external_registry_env": backend_has_external_registry_env,
        "backend_has_host_gateway": backend_has_host_gateway,
        "backend_runs_migrations": backend_runs_migrations,
    }


def build_release_matrix(repo_root: Path) -> dict[str, Any]:
    return {
        "frontend_version": load_frontend_version(repo_root),
        "backend_agent_protocol": PROTOCOL_SPEC_VERSION,
        "external_agent_compatibility": AGENT_COMPATIBILITY,
        "external_skill_compatibility": SKILL_COMPATIBILITY,
    }


def validate_production_env_template(repo_root: Path) -> tuple[bool, dict[str, Any]]:
    env_template_path = repo_root / "backend" / ".env.production.example"
    if not env_template_path.exists():
        return False, {
            "env_file": str(env_template_path),
            "missing": True,
            "ok": False,
            "checks": [],
        }

    payload = run_production_env_contract_check(env_file=env_template_path)
    return bool(payload.get("ok")), payload


def validate_acceptance_templates(repo_root: Path) -> tuple[bool, dict[str, Any]]:
    templates: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for key, relative_path in ACCEPTANCE_TEMPLATE_FILES.items():
        path = repo_root / relative_path
        exists = path.exists()
        templates[key] = {
            "path": str(path),
            "exists": exists,
        }
        if not exists:
            missing.append(key)

    return not missing, {
        "templates": templates,
        "missing": missing,
        "total_required": len(ACCEPTANCE_TEMPLATE_FILES),
        "present": len(ACCEPTANCE_TEMPLATE_FILES) - len(missing),
    }


def _load_database_alembic_versions(database_url: str) -> tuple[list[str], str | None]:
    engine = create_engine_for_url(database_url)
    try:
        with engine.connect() as connection:
            rows = connection.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num"))
            versions = [str(row[0]).strip() for row in rows if row[0] not in {None, ""}]
        return sorted(set(versions)), None
    except Exception as exc:
        return [], str(exc)
    finally:
        engine.dispose()


def validate_live_database_migration(
    *,
    database_url: str,
    expected_heads: list[str],
    version_loader: Callable[[str], tuple[list[str], str | None]] | None = None,
) -> tuple[bool, dict[str, Any]]:
    resolved_database_url = str(database_url or "").strip()
    if not resolved_database_url:
        return False, {
            "database_url": resolved_database_url,
            "connected": False,
            "expected_heads": sorted(expected_heads),
            "current_versions": [],
            "missing_head_versions": sorted(expected_heads),
            "unexpected_versions": [],
            "error": "database_url_missing",
        }

    loader = version_loader or _load_database_alembic_versions
    current_versions, error = loader(resolved_database_url)
    current_versions = sorted({str(item).strip() for item in current_versions if str(item).strip()})
    expected = sorted({str(item).strip() for item in expected_heads if str(item).strip()})
    missing_head_versions = sorted([item for item in expected if item not in current_versions])
    unexpected_versions = sorted([item for item in current_versions if item not in expected])
    connected = error is None
    ok = connected and not missing_head_versions and not unexpected_versions
    return ok, {
        "database_url": resolved_database_url,
        "connected": connected,
        "expected_heads": expected,
        "current_versions": current_versions,
        "missing_head_versions": missing_head_versions,
        "unexpected_versions": unexpected_versions,
        "at_head": ok,
        "error": error,
    }


def run_preflight(
    repo_root: Path,
    *,
    database_url: str | None = None,
    include_live_database: bool = False,
) -> dict[str, Any]:
    alembic_chain = load_alembic_chain(repo_root / "backend" / "alembic" / "versions")
    alembic_ok, alembic_summary = validate_alembic_chain(alembic_chain)
    compose_ok, compose_summary = validate_compose_guards(repo_root)
    release_matrix = build_release_matrix(repo_root)
    production_env_ok, production_env_summary = validate_production_env_template(repo_root)
    acceptance_templates_ok, acceptance_templates_summary = validate_acceptance_templates(repo_root)
    checks = {
        "alembic_chain": {"ok": alembic_ok, "summary": alembic_summary},
        "compose_guards": {"ok": compose_ok, "summary": compose_summary},
        "production_env_template": {"ok": production_env_ok, "summary": production_env_summary},
        "acceptance_templates": {
            "ok": acceptance_templates_ok,
            "summary": acceptance_templates_summary,
        },
        "release_matrix": {"ok": True, "summary": release_matrix},
    }
    if include_live_database:
        resolved_database_url = str(database_url or get_settings().database_url).strip()
        live_database_ok, live_database_summary = validate_live_database_migration(
            database_url=resolved_database_url,
            expected_heads=list(alembic_summary.get("heads") or []),
        )
        checks["live_database_migration"] = {"ok": live_database_ok, "summary": live_database_summary}
    return {
        "ok": all(item["ok"] for item in checks.values()),
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run release preflight checks.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--include-live-database", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    payload = run_preflight(
        Path(args.repo_root),
        database_url=args.database_url,
        include_live_database=bool(args.include_live_database),
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.strict and not payload["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
