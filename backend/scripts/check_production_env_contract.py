from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


REQUIRED_KEYS = (
    "WORKBOT_ENVIRONMENT",
    "WORKBOT_DATABASE_URL",
    "WORKBOT_REDIS_URL",
    "WORKBOT_NATS_URL",
    "WORKBOT_DATA_ENCRYPTION_KEY",
)

DEFAULT_VALUE_MAP = {
    "WORKBOT_ENVIRONMENT": "development",
    "WORKBOT_DATABASE_URL": "postgresql+psycopg://workbot:workbot@localhost:5432/workbot",
    "WORKBOT_REDIS_URL": "redis://localhost:6379/0",
    "WORKBOT_NATS_URL": "nats://localhost:4222",
    "WORKBOT_DATA_ENCRYPTION_KEY": "",
}

WEAK_PASSWORD_SET = {
    "workbot",
    "password",
    "123456",
    "admin",
    "root",
    "changeme",
    "qwerty",
}

LOCALHOST_SET = {"localhost", "127.0.0.1", "::1"}


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _make_check(name: str, ok: bool, message: str, value: str | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "ok": ok,
        "message": message,
        "value": value,
    }


def _host_from_url(url: str) -> str | None:
    try:
        return urlparse(url).hostname
    except Exception:
        return None


def run_check(*, env_file: str | Path) -> dict[str, Any]:
    path = Path(env_file)
    checks: list[dict[str, Any]] = []

    if not path.exists():
        checks.append(_make_check("env_file_exists", False, "env 文件不存在。", str(path)))
        return {
            "env_file": str(path),
            "checks": checks,
            "ok": False,
        }

    env_values = _read_env_file(path)
    checks.append(_make_check("env_file_exists", True, "env 文件存在。", str(path)))

    for key in REQUIRED_KEYS:
        value = env_values.get(key, "")
        present = bool(value.strip())
        checks.append(
            _make_check(
                f"required:{key}",
                present,
                "存在且非空。" if present else "缺失或为空。",
                value or None,
            )
        )

        if not present:
            continue

        default_value = DEFAULT_VALUE_MAP.get(key)
        if default_value is not None:
            checks.append(
                _make_check(
                    f"non_default:{key}",
                    value != default_value,
                    "不是默认值。" if value != default_value else "仍是默认值。",
                    value,
                )
            )

    environment = env_values.get("WORKBOT_ENVIRONMENT", "")
    checks.append(
        _make_check(
            "production_environment",
            environment == "production",
            "环境必须是 production。" if environment != "production" else "环境为 production。",
            environment or None,
        )
    )

    database_url = env_values.get("WORKBOT_DATABASE_URL", "")
    if database_url:
        db_host = _host_from_url(database_url)
        checks.append(
            _make_check(
                "database_not_localhost",
                bool(db_host and db_host not in LOCALHOST_SET),
                "数据库 host 不能是 localhost。"
                if db_host in LOCALHOST_SET
                else "数据库 host 合法。",
                db_host,
            )
        )
        db_password = urlparse(database_url).password or ""
        weak_password = (db_password or "").lower() in WEAK_PASSWORD_SET or len(db_password) < 12
        checks.append(
            _make_check(
                "database_password_strong",
                not weak_password,
                "数据库口令强度通过。" if not weak_password else "数据库口令过弱。",
                "***" if db_password else None,
            )
        )

    nats_url = env_values.get("WORKBOT_NATS_URL", "")
    if nats_url:
        nats_host = _host_from_url(nats_url)
        checks.append(
            _make_check(
                "nats_not_localhost",
                bool(nats_host and nats_host not in LOCALHOST_SET),
                "NATS host 不能是 localhost。"
                if nats_host in LOCALHOST_SET
                else "NATS host 合法。",
                nats_host,
            )
        )

    redis_url = env_values.get("WORKBOT_REDIS_URL", "")
    if redis_url:
        redis_host = _host_from_url(redis_url)
        checks.append(
            _make_check(
                "redis_not_localhost",
                bool(redis_host and redis_host not in LOCALHOST_SET),
                "Redis host 不能是 localhost。"
                if redis_host in LOCALHOST_SET
                else "Redis host 合法。",
                redis_host,
            )
        )

    encryption_key = env_values.get("WORKBOT_DATA_ENCRYPTION_KEY", "")
    if encryption_key:
        key_looks_placeholder = "<" in encryption_key or ">" in encryption_key
        key_strong = len(encryption_key) >= 32 and not key_looks_placeholder
        checks.append(
            _make_check(
                "data_encryption_key_strong",
                key_strong,
                "加密密钥强度通过。" if key_strong else "加密密钥过短或仍为占位值。",
                "<redacted>",
            )
        )

    ok = all(bool(item["ok"]) for item in checks)
    return {
        "env_file": str(path),
        "checks": checks,
        "ok": ok,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate production env contract.")
    parser.add_argument("--env-file", default=str(Path(__file__).resolve().parents[1] / ".env.production"))
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    payload = run_check(env_file=args.env_file)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.strict and not payload["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
