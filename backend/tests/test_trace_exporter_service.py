from __future__ import annotations

import json
from pathlib import Path

from app.services.trace_exporter_service import TraceExporterService


class _Settings:
    def __init__(
        self,
        *,
        enabled: bool = True,
        endpoint: str | None = None,
        file_path: str | None = None,
        timeout_seconds: float = 1.0,
    ) -> None:
        self.trace_export_enabled = enabled
        self.trace_export_endpoint = endpoint
        self.trace_export_file_path = file_path
        self.trace_export_timeout_seconds = timeout_seconds


def _audit_payload() -> dict:
    return {
        "id": "audit-trace-export-1",
        "timestamp": "2026-04-08T10:00:00+00:00",
        "action": "安全网关放行",
        "user": "telegram:test-user",
        "resource": "Security Gateway",
        "status": "success",
        "ip": "-",
        "details": "消息已通过 5 层安全检查",
        "metadata": {
            "trace": {
                "trace_id": "trace-export-1",
                "span_id": "span-export-1",
                "layer": "security_pass",
                "outcome": "allowed",
            },
            "prompt_injection_assessment": {"verdict": "allow", "rule_score": 0, "classifier_score": 0},
        },
    }


def test_trace_exporter_writes_ndjson_file(tmp_path: Path, monkeypatch) -> None:
    exporter = TraceExporterService()
    output_path = tmp_path / "traces" / "audit.ndjson"
    monkeypatch.setattr(
        exporter,
        "_settings",
        lambda: _Settings(file_path=str(output_path)),
    )

    assert exporter.export_audit_event(_audit_payload()) is True

    lines = output_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["schemaVersion"] == "workbot.trace.v1"
    assert payload["audit"]["id"] == "audit-trace-export-1"
    assert payload["trace"]["trace_id"] == "trace-export-1"


def test_trace_exporter_posts_json_to_http_endpoint(monkeypatch) -> None:
    exporter = TraceExporterService()
    captured: dict[str, object] = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def _fake_urlopen(request, timeout=0):  # noqa: ANN001
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["content_type"] = request.headers.get("Content-type")
        return _Response()

    monkeypatch.setattr(
        exporter,
        "_settings",
        lambda: _Settings(endpoint="http://collector.local/traces", timeout_seconds=2.5),
    )
    monkeypatch.setattr("app.services.trace_exporter_service.urllib_request.urlopen", _fake_urlopen)

    assert exporter.export_audit_event(_audit_payload()) is True
    assert captured["url"] == "http://collector.local/traces"
    assert captured["timeout"] == 2.5
    assert captured["content_type"] == "application/json"
    assert captured["body"]["trace"]["trace_id"] == "trace-export-1"


def test_trace_exporter_skips_payload_without_trace(monkeypatch) -> None:
    exporter = TraceExporterService()
    output_path = Path("/tmp/trace-exporter-should-not-write.ndjson")
    monkeypatch.setattr(
        exporter,
        "_settings",
        lambda: _Settings(file_path=str(output_path)),
    )

    assert exporter.export_audit_event({"metadata": {}}) is False
