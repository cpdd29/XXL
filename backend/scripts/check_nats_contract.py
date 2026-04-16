from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlparse


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import Settings, get_settings
from app.core.nats_event_bus import nats_event_bus


def _default_nats_url() -> str:
    field = Settings.model_fields.get("nats_url")
    if field is None:
        return "nats://localhost:4222"
    return str(field.default)


def _parse_nats_url(raw_url: str) -> tuple[dict[str, Any], list[str], bool]:
    warnings: list[str] = []
    parsed = urlparse(raw_url)

    scheme = str(parsed.scheme or "").strip().lower()
    host = str(parsed.hostname or "").strip()
    port = parsed.port
    parse_ok = True

    if scheme not in {"nats", "tls"}:
        warnings.append(f"nats_url scheme 非预期: {scheme or 'empty'}")
        parse_ok = False
    if not host:
        warnings.append("nats_url 缺少 host。")
        parse_ok = False
    if port is None:
        warnings.append("nats_url 缺少 port。")
        parse_ok = False

    return {
        "scheme": scheme,
        "host": host,
        "port": port,
    }, warnings, parse_ok


def _snapshot_with_probe() -> dict[str, Any]:
    initial_snapshot = dict(nats_event_bus.connection_snapshot())
    if bool(initial_snapshot.get("connected")):
        return initial_snapshot

    initialize = getattr(nats_event_bus, "initialize", None)
    close = getattr(nats_event_bus, "close", None)
    if not callable(initialize):
        return initial_snapshot

    attempted_probe = False
    try:
        attempted_probe = True
        initialize()
        return dict(nats_event_bus.connection_snapshot())
    finally:
        if attempted_probe and callable(close):
            close()


def run_check() -> dict[str, Any]:
    settings = get_settings()
    snapshot = _snapshot_with_probe()

    nats_url = str(snapshot.get("nats_url") or settings.nats_url)
    parse_result, warnings, parse_ok = _parse_nats_url(nats_url)

    scheme = parse_result["scheme"]
    host = parse_result["host"]
    port = parse_result["port"]

    connected = bool(snapshot.get("connected"))
    fallback_mode = bool(snapshot.get("fallback_mode"))
    handler_registrations = int(snapshot.get("handler_registrations") or 0)
    subscription_registrations = int(snapshot.get("subscription_registrations") or 0)
    last_error = snapshot.get("last_error")
    probe_error = None
    if isinstance(last_error, dict):
        message = str(last_error.get("message") or "").strip()
        probe_error = message or None

    if connected and fallback_mode:
        warnings.append("connected=true 但 fallback_mode=true，状态不一致。")
    if not connected:
        warnings.append("NATS 未连接，当前处于降级/回退路径。")
    if subscription_registrations > handler_registrations:
        warnings.append("subscription_registrations 大于 handler_registrations，状态异常。")
    if handler_registrations < 0 or subscription_registrations < 0:
        warnings.append("registrations 出现负值，状态异常。")

    default_url = _default_nats_url()
    uses_default_url = nats_url == default_url
    is_localhost = host in {"localhost", "127.0.0.1", "::1"}
    if uses_default_url:
        warnings.append("nats_url 仍为默认值。")
    if is_localhost:
        warnings.append("nats_url 指向 localhost，本机 NATS 不符合生产部署约束。")

    status_ok = (
        parse_ok
        and connected
        and handler_registrations >= 0
        and subscription_registrations >= 0
        and subscription_registrations <= handler_registrations
        and not fallback_mode
        and not uses_default_url
        and not is_localhost
    )

    return {
        "ok": status_ok,
        "nats_url": nats_url,
        "scheme": scheme,
        "host": host,
        "port": port,
        "uses_default_url": uses_default_url,
        "is_localhost": is_localhost,
        "connected": connected,
        "fallback_mode": fallback_mode,
        "handler_registrations": handler_registrations,
        "subscription_registrations": subscription_registrations,
        "last_error": last_error,
        "probe_error": probe_error,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run NATS contract self-check.")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    payload = run_check()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.strict and not payload["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
