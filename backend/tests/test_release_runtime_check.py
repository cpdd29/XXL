from __future__ import annotations

from pathlib import Path

import scripts.check_release_runtime as runtime_module


def test_run_release_runtime_check_covers_all_scenarios(tmp_path: Path, monkeypatch) -> None:
    snapshot_dir = tmp_path / "snapshots"
    selected = snapshot_dir / "20260416_000001"
    selected.mkdir(parents=True)
    (selected / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")

    monkeypatch.setattr(
        runtime_module,
        "run_persistence_contract_check",
        lambda: {
            "ok": True,
            "database_url": "postgresql+psycopg://db.prod.internal:5432/workbot",
        },
    )
    monkeypatch.setattr(
        runtime_module,
        "run_preflight",
        lambda *_args, **_kwargs: {"ok": True, "status": "passed"},
    )
    monkeypatch.setattr(
        runtime_module,
        "run_brain_prelaunch_check",
        lambda **_kwargs: {
            "ok": True,
            "startup_ready": True,
            "production_ready": True,
            "status": "production_ready",
        },
    )
    monkeypatch.setattr(
        runtime_module,
        "json_request",
        lambda **kwargs: {
            "ok": True,
            "status_code": 200,
            "text": '{"ok":true}',
            "json": {"ok": True},
            "error": None,
        },
    )
    monkeypatch.setattr(
        runtime_module,
        "run_external_tentacle_recovery",
        lambda **_kwargs: {"ok": True, "status": "passed", "failed_steps": []},
    )
    monkeypatch.setattr(
        runtime_module,
        "run_memory_governance_check",
        lambda: {"ok": True, "status": "passed", "failed_steps": []},
    )

    payload = runtime_module.run_release_runtime_check(
        scenario="all",
        snapshot_dir=str(snapshot_dir),
        write_report=True,
        output_dir=str(tmp_path / "reports"),
    )

    assert payload["ok"] is True
    assert payload["status"] == "passed"
    assert sorted(payload["scenarios"].keys()) == ["postdeploy", "recovery", "rollback"]
    assert Path(payload["artifacts"]["json_report"]).exists()
    assert Path(payload["artifacts"]["markdown_report"]).exists()
    assert payload["scenarios"]["rollback"]["checks"][0]["key"] == "rollback_snapshot_available"
    assert payload["scenarios"]["recovery"]["components"]["external_tentacle_recovery"]["ok"] is True


def test_run_release_runtime_check_fails_when_rollback_snapshot_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        runtime_module,
        "run_persistence_contract_check",
        lambda: {"ok": False, "database_url": ""},
    )
    monkeypatch.setattr(
        runtime_module,
        "run_preflight",
        lambda *_args, **_kwargs: {"ok": True, "status": "passed"},
    )
    monkeypatch.setattr(
        runtime_module,
        "run_brain_prelaunch_check",
        lambda **_kwargs: {
            "ok": True,
            "startup_ready": True,
            "production_ready": False,
            "status": "degraded_startable",
        },
    )
    monkeypatch.setattr(
        runtime_module,
        "json_request",
        lambda **kwargs: {
            "ok": True,
            "status_code": 200,
            "text": '{"ok":true}',
            "json": {"ok": True},
            "error": None,
        },
    )

    payload = runtime_module.run_release_runtime_check(
        scenario="rollback",
        snapshot_dir=str(tmp_path / "missing-snapshots"),
        write_report=False,
    )

    assert payload["ok"] is False
    assert payload["status"] == "failed"
    assert "rollback:rollback_snapshot_available" in payload["failed_steps"]


def test_run_release_runtime_check_can_require_control_plane_token(tmp_path: Path, monkeypatch) -> None:
    snapshot_dir = tmp_path / "snapshots"
    selected = snapshot_dir / "20260416_000001"
    selected.mkdir(parents=True)
    (selected / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")

    monkeypatch.setattr(
        runtime_module,
        "run_persistence_contract_check",
        lambda: {"ok": True, "database_url": "postgresql+psycopg://db.prod.internal:5432/workbot"},
    )
    monkeypatch.setattr(
        runtime_module,
        "run_preflight",
        lambda *_args, **_kwargs: {"ok": True, "status": "passed"},
    )
    monkeypatch.setattr(
        runtime_module,
        "run_brain_prelaunch_check",
        lambda **_kwargs: {
            "ok": True,
            "startup_ready": True,
            "production_ready": True,
            "status": "production_ready",
        },
    )
    monkeypatch.setattr(
        runtime_module,
        "json_request",
        lambda **kwargs: {
            "ok": True if kwargs["url"].endswith("/health") else False,
            "status_code": 200 if kwargs["url"].endswith("/health") else 401,
            "text": '{"ok":true}' if kwargs["url"].endswith("/health") else '{"detail":"Unauthorized"}',
            "json": {"ok": True} if kwargs["url"].endswith("/health") else {"detail": "Unauthorized"},
            "error": None if kwargs["url"].endswith("/health") else "HTTPError: Unauthorized",
        },
    )

    payload = runtime_module.run_release_runtime_check(
        scenario="postdeploy",
        snapshot_dir=str(snapshot_dir),
        require_control_plane=True,
        write_report=False,
    )

    assert payload["ok"] is False
    assert "postdeploy:runtime_control_plane_auth_ready" in payload["failed_steps"]
