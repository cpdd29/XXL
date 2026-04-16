from __future__ import annotations

from types import SimpleNamespace

import scripts.check_nats_contract as nats_contract_module
from scripts.check_nats_contract import run_check


class _DummyBus:
    def __init__(self, snapshot: dict[str, object]) -> None:
        self._snapshot = snapshot

    def connection_snapshot(self) -> dict[str, object]:
        return dict(self._snapshot)


def test_nats_contract_default_localhost_fallback_is_not_production_ready(monkeypatch) -> None:
    monkeypatch.setattr(
        nats_contract_module,
        "nats_event_bus",
        _DummyBus(
            {
                "nats_url": "nats://localhost:4222",
                "connected": False,
                "fallback_mode": True,
                "handler_registrations": 2,
                "subscription_registrations": 0,
                "last_error": {"stage": "connect", "type": "RuntimeError", "message": "dial failed"},
            }
        ),
    )
    monkeypatch.setattr(nats_contract_module, "get_settings", lambda: SimpleNamespace(nats_url="nats://localhost:4222"))

    payload = run_check()

    assert payload["ok"] is False
    assert payload["scheme"] == "nats"
    assert payload["host"] == "localhost"
    assert payload["port"] == 4222
    assert payload["uses_default_url"] is True
    assert payload["is_localhost"] is True
    assert payload["connected"] is False
    assert payload["fallback_mode"] is True
    assert payload["handler_registrations"] == 2
    assert payload["subscription_registrations"] == 0
    assert payload["last_error"] == {"stage": "connect", "type": "RuntimeError", "message": "dial failed"}
    assert payload["probe_error"] == "dial failed"
    assert payload["warnings"]


def test_nats_contract_remote_connected_ok(monkeypatch) -> None:
    monkeypatch.setattr(
        nats_contract_module,
        "nats_event_bus",
        _DummyBus(
            {
                "nats_url": "nats://nats.prod.internal:4222",
                "connected": True,
                "fallback_mode": False,
                "handler_registrations": 4,
                "subscription_registrations": 4,
                "last_error": None,
            }
        ),
    )
    monkeypatch.setattr(nats_contract_module, "get_settings", lambda: SimpleNamespace(nats_url="nats://nats.prod.internal:4222"))

    payload = run_check()

    assert payload["ok"] is True
    assert payload["uses_default_url"] is False
    assert payload["is_localhost"] is False
    assert payload["last_error"] is None
    assert payload["probe_error"] is None
    assert payload["warnings"] == []


def test_nats_contract_invalid_scheme_is_not_ok(monkeypatch) -> None:
    monkeypatch.setattr(
        nats_contract_module,
        "nats_event_bus",
        _DummyBus(
            {
                "nats_url": "http://localhost:4222",
                "connected": False,
                "fallback_mode": True,
                "handler_registrations": 1,
                "subscription_registrations": 0,
                "last_error": {"stage": "connect", "type": "ValueError", "message": "bad scheme"},
            }
        ),
    )
    monkeypatch.setattr(nats_contract_module, "get_settings", lambda: SimpleNamespace(nats_url="http://localhost:4222"))

    payload = run_check()

    assert payload["ok"] is False
    assert payload["probe_error"] == "bad scheme"
    assert any("scheme" in warning for warning in payload["warnings"])


def test_nats_contract_inconsistent_connected_and_fallback_is_not_ok(monkeypatch) -> None:
    monkeypatch.setattr(
        nats_contract_module,
        "nats_event_bus",
        _DummyBus(
            {
                "nats_url": "nats://localhost:4222",
                "connected": True,
                "fallback_mode": True,
                "handler_registrations": 2,
                "subscription_registrations": 1,
                "last_error": {"stage": "sync", "type": "RuntimeError", "message": "subscribe failed"},
            }
        ),
    )
    monkeypatch.setattr(nats_contract_module, "get_settings", lambda: SimpleNamespace(nats_url="nats://localhost:4222"))

    payload = run_check()

    assert payload["ok"] is False
    assert payload["probe_error"] == "subscribe failed"
    assert any("状态不一致" in warning for warning in payload["warnings"])


def test_nats_contract_remote_but_disconnected_is_not_ok(monkeypatch) -> None:
    monkeypatch.setattr(
        nats_contract_module,
        "nats_event_bus",
        _DummyBus(
            {
                "nats_url": "nats://nats.prod.internal:4222",
                "connected": False,
                "fallback_mode": False,
                "handler_registrations": 1,
                "subscription_registrations": 0,
                "last_error": {"stage": "connect", "type": "TimeoutError", "message": "probe timeout"},
            }
        ),
    )
    monkeypatch.setattr(nats_contract_module, "get_settings", lambda: SimpleNamespace(nats_url="nats://nats.prod.internal:4222"))

    payload = run_check()

    assert payload["ok"] is False
    assert payload["uses_default_url"] is False
    assert payload["is_localhost"] is False
    assert payload["probe_error"] == "probe timeout"
    assert any("未连接" in warning for warning in payload["warnings"])
