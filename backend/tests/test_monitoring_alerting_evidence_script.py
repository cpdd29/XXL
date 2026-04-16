from __future__ import annotations

from pathlib import Path

from scripts.collect_monitoring_alerting_evidence import (
    DEFAULT_ENDPOINTS,
    collect_monitoring_alerting_evidence,
    run_monitoring_alerting_evidence,
)


class _FakeResponse:
    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self._body = body.encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def _normalized_headers(request_obj) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in request_obj.header_items()}


def test_collect_monitoring_alerting_evidence_uses_metrics_token_for_metrics_only() -> None:
    seen_headers: dict[str, dict[str, str]] = {}

    def opener(req, timeout=0):
        seen_headers[req.full_url] = _normalized_headers(req)
        return _FakeResponse(200, "ok")

    payload = collect_monitoring_alerting_evidence(
        access_token="access-token-123",
        metrics_token="metrics-token-456",
        opener=opener,
    )

    assert payload["ok"] is True
    assert seen_headers[DEFAULT_ENDPOINTS["metrics"]]["x-workbot-metrics-token"] == "metrics-token-456"
    assert "authorization" not in seen_headers[DEFAULT_ENDPOINTS["metrics"]]
    assert seen_headers[DEFAULT_ENDPOINTS["alerts"]]["authorization"] == "Bearer access-token-123"
    assert seen_headers[DEFAULT_ENDPOINTS["dashboard_stats"]]["authorization"] == "Bearer access-token-123"


def test_run_monitoring_alerting_evidence_can_login_and_write_report(tmp_path: Path) -> None:
    seen_headers: dict[str, dict[str, str]] = {}

    def opener(req, timeout=0):
        seen_headers[req.full_url] = _normalized_headers(req)
        if req.full_url.endswith("/api/auth/login"):
            return _FakeResponse(200, '{"accessToken":"login-token-xyz"}')
        return _FakeResponse(200, "ok")

    payload = run_monitoring_alerting_evidence(
        backend_base_url="http://127.0.0.1:8080",
        email="admin@workbot.ai",
        password="workbot123",
        output_dir=str(tmp_path),
        write_report=True,
        opener=opener,
    )

    assert payload["ok"] is True
    assert payload["auth"]["login"]["used_login"] is True
    assert seen_headers[DEFAULT_ENDPOINTS["alerts"]]["authorization"] == "Bearer login-token-xyz"
    assert Path(payload["artifacts"]["json_report"]).exists()
    assert Path(payload["artifacts"]["markdown_report"]).exists()
