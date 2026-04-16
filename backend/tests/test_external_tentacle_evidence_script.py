from __future__ import annotations

import json
from pathlib import Path

from scripts.collect_external_tentacle_evidence import (
    run_collect_external_tentacle_evidence,
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


def test_run_collect_external_tentacle_evidence_compares_registry_and_control_plane(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "sources": [
                    {"id": "registered-agent-reach", "kind": "external_repo"},
                    {"id": "registered-mcp", "kind": "mcp_registry"},
                ],
                "tools": [
                    {"id": "skill-tool-1"},
                    {"id": "skill-tool-2"},
                ],
            }
        ),
        encoding="utf-8",
    )

    def opener(req, timeout=0):
        if req.full_url.endswith("/api/tool-sources/scan"):
            return _FakeResponse(200, '{"ok":true,"items":[],"total":0,"summary":{}}')
        if req.full_url.endswith("/api/external-connections/health"):
            return _FakeResponse(200, '{"items":[],"total":0,"summary":{}}')
        if req.full_url.endswith("/api/external-connections/governance"):
            return _FakeResponse(200, '{"items":[],"total":0,"summary":{}}')
        if req.full_url.endswith("/api/tool-sources?refresh=true"):
            return _FakeResponse(
                200,
                '{"items":[{"id":"registered-agent-reach"},{"id":"registered-mcp"}],"total":2,"summary":{}}',
            )
        if req.full_url.endswith("/api/tools/health?refresh=true"):
            return _FakeResponse(200, '{"items":[],"total":2,"summary":{"healthy":2}}')
        raise AssertionError(f"unexpected url {req.full_url}")

    payload = run_collect_external_tentacle_evidence(
        backend_base_url="http://127.0.0.1:8080",
        registry_path=str(registry_path),
        access_token="operator-token",
        scan_sources=True,
        output_dir=str(tmp_path),
        write_report=True,
        opener=opener,
    )

    assert payload["ok"] is True
    assert payload["registry"]["source_count"] == 2
    assert payload["registry"]["tool_count"] == 2
    assert payload["scan_sources"]["requested"] is True
    assert Path(payload["artifacts"]["json_report"]).exists()
    assert Path(payload["artifacts"]["markdown_report"]).exists()
