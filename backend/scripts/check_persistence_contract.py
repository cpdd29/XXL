from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Callable
from urllib.parse import urlparse

from sqlalchemy import text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import Settings, get_settings
from app.db.session import create_engine_for_url


_LOCALHOST_SET = {"localhost", "127.0.0.1", "::1"}


def _probe_persistence_enabled(database_url: str) -> tuple[bool, str | None]:
    engine = create_engine_for_url(database_url)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True, None
    except Exception as exc:
        return False, str(exc)
    finally:
        engine.dispose()


def _normalize_probe_result(result: object) -> tuple[bool, str | None]:
    if isinstance(result, tuple) and len(result) == 2:
        return bool(result[0]), str(result[1]) if result[1] else None
    return bool(result), None


def run_persistence_contract_check(
    *,
    database_url: str | None = None,
    probe: Callable[[str], object] | None = None,
) -> dict[str, Any]:
    resolved_url = (database_url or get_settings().database_url).strip()
    parsed = urlparse(resolved_url)
    scheme = (parsed.scheme or "").strip()
    driver = scheme.split("+", 1)[0] if scheme else ""
    host = parsed.hostname
    port = parsed.port
    is_sqlite = driver == "sqlite"
    is_localhost = bool(host and host in _LOCALHOST_SET)
    uses_default_url = resolved_url == str(Settings.model_fields["database_url"].default)

    warnings: list[str] = []
    if not scheme:
        warnings.append("database_url 缺少 scheme，无法识别数据库驱动。")
    if uses_default_url:
        warnings.append("database_url 仍为默认值。")
    if is_sqlite:
        warnings.append("database_url 使用 sqlite，不符合生产真源约束。")
    if is_localhost:
        warnings.append("database_url 指向 localhost，本机真源不符合生产部署约束。")

    persistence_enabled = False
    probe_error: str | None = None
    if scheme:
        try:
            checker = probe or _probe_persistence_enabled
            persistence_enabled, probe_error = _normalize_probe_result(checker(resolved_url))
        except Exception as exc:  # pragma: no cover - defensive fallback
            warnings.append(f"持久化探测失败: {exc}")
            persistence_enabled = False
            probe_error = str(exc)
    else:
        warnings.append("跳过持久化探测：database_url 不合法。")

    if not persistence_enabled:
        warnings.append("持久化初始化未通过。")

    ok = bool(
        scheme
        and persistence_enabled
        and not is_sqlite
        and not is_localhost
        and not uses_default_url
    )
    return {
        "ok": ok,
        "database_url": resolved_url,
        "scheme": scheme,
        "driver": driver,
        "host": host,
        "port": port,
        "is_sqlite": is_sqlite,
        "is_localhost": is_localhost,
        "uses_default_url": uses_default_url,
        "persistence_enabled": persistence_enabled,
        "probe_error": probe_error,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check database truth-source persistence contract.")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    payload = run_persistence_contract_check(database_url=args.database_url)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.strict and not payload["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
