from __future__ import annotations

from scripts.check_persistence_contract import run_persistence_contract_check


def test_persistence_contract_ok_for_remote_non_default_database() -> None:
    payload = run_persistence_contract_check(
        database_url="postgresql+psycopg://user:pass@db.prod.internal:5432/workbot",
        probe=lambda _: True,
    )
    assert payload["ok"] is True
    assert payload["scheme"] == "postgresql+psycopg"
    assert payload["driver"] == "postgresql"
    assert payload["host"] == "db.prod.internal"
    assert payload["port"] == 5432
    assert payload["is_sqlite"] is False
    assert payload["is_localhost"] is False
    assert payload["uses_default_url"] is False
    assert payload["persistence_enabled"] is True
    assert payload["probe_error"] is None
    assert payload["warnings"] == []


def test_persistence_contract_warns_on_default_localhost_and_probe_failure() -> None:
    payload = run_persistence_contract_check(
        database_url="postgresql+psycopg://workbot:workbot@localhost:5432/workbot",
        probe=lambda _: False,
    )
    assert payload["ok"] is False
    assert payload["is_localhost"] is True
    assert payload["uses_default_url"] is True
    assert payload["persistence_enabled"] is False
    assert payload["probe_error"] is None
    warnings = payload["warnings"]
    assert any("默认值" in item for item in warnings)
    assert any("localhost" in item for item in warnings)
    assert any("持久化初始化未通过" in item for item in warnings)


def test_persistence_contract_marks_sqlite_as_not_ok_even_if_probe_passes() -> None:
    payload = run_persistence_contract_check(
        database_url="sqlite:////tmp/workbot.db",
        probe=lambda _: True,
    )
    assert payload["ok"] is False
    assert payload["driver"] == "sqlite"
    assert payload["is_sqlite"] is True
    assert payload["is_localhost"] is False
    assert payload["persistence_enabled"] is True
    assert payload["probe_error"] is None
    assert any("sqlite" in item for item in payload["warnings"])


def test_persistence_contract_handles_invalid_url() -> None:
    payload = run_persistence_contract_check(database_url="://broken-url")
    assert payload["ok"] is False
    assert payload["scheme"] == ""
    assert payload["driver"] == ""
    assert payload["host"] is None
    assert payload["port"] is None
    assert payload["persistence_enabled"] is False
    assert payload["probe_error"] is None
    warnings = payload["warnings"]
    assert any("缺少 scheme" in item for item in warnings)
    assert any("跳过持久化探测" in item for item in warnings)


def test_persistence_contract_surfaces_probe_error() -> None:
    payload = run_persistence_contract_check(
        database_url="postgresql+psycopg://workbot:workbot@db.prod.internal:5432/workbot",
        probe=lambda _: (False, "connection refused"),
    )

    assert payload["ok"] is False
    assert payload["probe_error"] == "connection refused"
    assert payload["persistence_enabled"] is False
