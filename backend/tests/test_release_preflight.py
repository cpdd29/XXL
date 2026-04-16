from __future__ import annotations

from pathlib import Path
from typing import Any

import scripts.check_release_preflight as preflight_module
from scripts.check_release_preflight import (
    build_release_matrix,
    load_alembic_chain,
    run_preflight,
    validate_alembic_chain,
    validate_acceptance_templates,
    validate_compose_guards,
    validate_live_database_migration,
)

REPO_ROOT = Path("/Users/xiaoyuge/Documents/XXL")


def _write_env_template(path: Path, content: str) -> None:
    path.write_text(content.strip() + "\n", encoding="utf-8")


def _check_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["name"]: item for item in payload["checks"]}


def _write_acceptance_templates(repo_root: Path, *, missing: set[str] | None = None) -> None:
    for key, relative_path in preflight_module.ACCEPTANCE_TEMPLATE_FILES.items():
        if key in (missing or set()):
            continue
        path = repo_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {key}\n", encoding="utf-8")


def test_validate_alembic_chain_accepts_single_head_chain() -> None:
    chain = [
        {"revision": "0001", "down_revision": "None", "file": "0001.py"},
        {"revision": "0002", "down_revision": "0001", "file": "0002.py"},
        {"revision": "0003", "down_revision": "0002", "file": "0003.py"},
    ]
    ok, summary = validate_alembic_chain(chain)
    assert ok is True
    assert summary["heads"] == ["0003"]
    assert summary["roots"] == ["0001"]


def test_load_alembic_chain_reads_real_repo_files() -> None:
    versions_root = Path("/Users/xiaoyuge/Documents/XXL/backend/alembic/versions")
    chain = load_alembic_chain(versions_root)
    assert len(chain) >= 1
    assert all("revision" in item for item in chain)


def test_release_matrix_contains_protocol_and_external_compatibility() -> None:
    payload = build_release_matrix(REPO_ROOT)
    assert payload["backend_agent_protocol"]
    assert payload["external_agent_compatibility"] == "brain-core-v1"
    assert payload["external_skill_compatibility"] == "brain-core-v1"


def test_run_preflight_is_green_for_current_repo() -> None:
    payload = run_preflight(REPO_ROOT)
    assert payload["ok"] is True
    assert payload["checks"]["alembic_chain"]["ok"] is True
    assert payload["checks"]["compose_guards"]["ok"] is True
    assert payload["checks"]["production_env_template"]["ok"] is True
    assert payload["checks"]["acceptance_templates"]["ok"] is True


def test_validate_compose_guards_requires_backend_migration_command() -> None:
    ok, summary = validate_compose_guards(REPO_ROOT)
    assert ok is True
    assert summary["backend_runs_migrations"] is True


def test_validate_acceptance_templates_accepts_current_repo() -> None:
    ok, summary = validate_acceptance_templates(REPO_ROOT)
    assert ok is True
    assert summary["missing"] == []
    assert summary["present"] == summary["total_required"] == 3


def test_validate_live_database_migration_accepts_database_at_head() -> None:
    ok, summary = validate_live_database_migration(
        database_url="postgresql+psycopg://db.prod.internal:5432/workbot",
        expected_heads=["20260415_0015"],
        version_loader=lambda _database_url: (["20260415_0015"], None),
    )
    assert ok is True
    assert summary["connected"] is True
    assert summary["at_head"] is True
    assert summary["missing_head_versions"] == []
    assert summary["unexpected_versions"] == []


def test_validate_live_database_migration_detects_database_behind_head() -> None:
    ok, summary = validate_live_database_migration(
        database_url="postgresql+psycopg://db.prod.internal:5432/workbot",
        expected_heads=["20260415_0015"],
        version_loader=lambda _database_url: (["20260408_0014"], None),
    )
    assert ok is False
    assert summary["connected"] is True
    assert summary["at_head"] is False
    assert summary["missing_head_versions"] == ["20260415_0015"]
    assert summary["unexpected_versions"] == ["20260408_0014"]


def test_run_preflight_includes_live_database_check_when_requested(monkeypatch) -> None:
    monkeypatch.setattr(
        preflight_module,
        "validate_live_database_migration",
        lambda *, database_url, expected_heads: (
            True,
            {
                "database_url": database_url,
                "connected": True,
                "expected_heads": expected_heads,
                "current_versions": expected_heads,
                "missing_head_versions": [],
                "unexpected_versions": [],
                "at_head": True,
                "error": None,
            },
        ),
    )

    payload = run_preflight(
        REPO_ROOT,
        database_url="postgresql+psycopg://db.prod.internal:5432/workbot",
        include_live_database=True,
    )

    assert payload["ok"] is True
    assert payload["checks"]["live_database_migration"]["ok"] is True


def test_run_preflight_fails_when_production_env_template_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(preflight_module, "load_alembic_chain", lambda _versions_root: [])
    monkeypatch.setattr(preflight_module, "validate_alembic_chain", lambda _chain: (True, {}))
    monkeypatch.setattr(preflight_module, "validate_compose_guards", lambda _repo_root: (True, {}))
    monkeypatch.setattr(preflight_module, "build_release_matrix", lambda _repo_root: {"backend_agent_protocol": "agentbus.v1"})

    repo_root = tmp_path / "repo"
    (repo_root / "backend").mkdir(parents=True)
    payload = run_preflight(repo_root)
    contract_payload = payload["checks"]["production_env_template"]["summary"]

    assert payload["ok"] is False
    assert payload["checks"]["production_env_template"]["ok"] is False
    assert contract_payload["missing"] is True
    assert contract_payload["checks"] == []


def test_run_preflight_fails_when_production_env_template_contract_is_invalid(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(preflight_module, "load_alembic_chain", lambda _versions_root: [])
    monkeypatch.setattr(preflight_module, "validate_alembic_chain", lambda _chain: (True, {}))
    monkeypatch.setattr(preflight_module, "validate_compose_guards", lambda _repo_root: (True, {}))
    monkeypatch.setattr(preflight_module, "build_release_matrix", lambda _repo_root: {"backend_agent_protocol": "agentbus.v1"})

    repo_root = tmp_path / "repo"
    env_template = repo_root / "backend" / ".env.production.example"
    env_template.parent.mkdir(parents=True)
    _write_env_template(
        env_template,
        """
        WORKBOT_ENVIRONMENT=development
        WORKBOT_DATABASE_URL=postgresql+psycopg://workbot:workbot@localhost:5432/workbot
        WORKBOT_REDIS_URL=redis://localhost:6379/0
        WORKBOT_NATS_URL=nats://localhost:4222
        WORKBOT_DATA_ENCRYPTION_KEY=short
        """,
    )

    payload = run_preflight(repo_root)
    contract_payload = payload["checks"]["production_env_template"]["summary"]
    contract_checks = _check_map(contract_payload)

    assert payload["ok"] is False
    assert payload["checks"]["production_env_template"]["ok"] is False
    assert contract_checks["production_environment"]["ok"] is False


def test_run_preflight_fails_when_acceptance_template_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(preflight_module, "load_alembic_chain", lambda _versions_root: [])
    monkeypatch.setattr(preflight_module, "validate_alembic_chain", lambda _chain: (True, {}))
    monkeypatch.setattr(preflight_module, "validate_compose_guards", lambda _repo_root: (True, {}))
    monkeypatch.setattr(preflight_module, "build_release_matrix", lambda _repo_root: {"backend_agent_protocol": "agentbus.v1"})
    monkeypatch.setattr(preflight_module, "validate_production_env_template", lambda _repo_root: (True, {"ok": True}))

    repo_root = tmp_path / "repo"
    _write_acceptance_templates(repo_root, missing={"package_e_security"})

    payload = run_preflight(repo_root)
    templates_summary = payload["checks"]["acceptance_templates"]["summary"]

    assert payload["ok"] is False
    assert payload["checks"]["acceptance_templates"]["ok"] is False
    assert templates_summary["missing"] == ["package_e_security"]
    assert templates_summary["present"] == 2
