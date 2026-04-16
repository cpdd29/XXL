from __future__ import annotations

from pathlib import Path

from scripts.check_production_env_contract import run_check


def _write_env(path: Path, content: str) -> None:
    path.write_text(content.strip() + "\n", encoding="utf-8")


def _check_map(payload: dict) -> dict[str, dict]:
    return {item["name"]: item for item in payload["checks"]}


def test_production_env_contract_missing_required_items(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.production"
    _write_env(
        env_file,
        """
        WORKBOT_ENVIRONMENT=production
        WORKBOT_DATABASE_URL=postgresql+psycopg://workbot:StrongPwd123!@db.prod.internal:5432/workbot
        """,
    )

    payload = run_check(env_file=env_file)
    checks = _check_map(payload)

    assert payload["ok"] is False
    assert checks["required:WORKBOT_REDIS_URL"]["ok"] is False
    assert checks["required:WORKBOT_NATS_URL"]["ok"] is False
    assert checks["required:WORKBOT_DATA_ENCRYPTION_KEY"]["ok"] is False


def test_production_env_contract_flags_default_and_localhost_and_weak_password(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.production"
    _write_env(
        env_file,
        """
        WORKBOT_ENVIRONMENT=development
        WORKBOT_DATABASE_URL=postgresql+psycopg://workbot:workbot@localhost:5432/workbot
        WORKBOT_REDIS_URL=redis://localhost:6379/0
        WORKBOT_NATS_URL=nats://localhost:4222
        WORKBOT_DATA_ENCRYPTION_KEY=short
        """,
    )

    payload = run_check(env_file=env_file)
    checks = _check_map(payload)

    assert payload["ok"] is False
    assert checks["non_default:WORKBOT_DATABASE_URL"]["ok"] is False
    assert checks["database_not_localhost"]["ok"] is False
    assert checks["database_password_strong"]["ok"] is False
    assert checks["redis_not_localhost"]["ok"] is False
    assert checks["nats_not_localhost"]["ok"] is False
    assert checks["data_encryption_key_strong"]["ok"] is False
    assert checks["production_environment"]["ok"] is False


def test_production_env_contract_passes_with_non_default_remote_and_strong_values(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.production"
    _write_env(
        env_file,
        """
        WORKBOT_ENVIRONMENT=production
        WORKBOT_DATABASE_URL=postgresql+psycopg://workbot:StrongPassword123!@db.prod.internal:5432/workbot
        WORKBOT_REDIS_URL=redis://redis.prod.internal:6379/0
        WORKBOT_NATS_URL=nats://nats.prod.internal:4222
        WORKBOT_DATA_ENCRYPTION_KEY=abcdef1234567890abcdef1234567890
        """,
    )

    payload = run_check(env_file=env_file)
    assert payload["ok"] is True
    assert all(item["ok"] for item in payload["checks"])
