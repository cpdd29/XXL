from __future__ import annotations

from pathlib import Path

import scripts.collect_security_acceptance_evidence as script_module


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


def test_run_collect_security_acceptance_evidence_packages_gate_results(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        script_module,
        "run_security_entrypoint_check",
        lambda repo_root: {"ok": True, "summary": {"failed_checks": 0}, "checks": []},
    )
    monkeypatch.setattr(
        script_module,
        "run_security_control_check",
        lambda: {"ok": True, "summary": {"failed_checks": 0}, "checks": []},
    )
    monkeypatch.setattr(
        script_module,
        "run_security_audit_persistence_check",
        lambda database_path=None: {"ok": True, "summary": {"failed_checks": 0}, "checks": []},
    )
    monkeypatch.setattr(
        script_module,
        "run_external_ingress_bypass_check",
        lambda repo_root: {"ok": True, "summary": {"failed_public_routes": 0}, "routes": []},
    )

    def opener(req, timeout=0):
        if req.full_url.endswith("/api/security/report"):
            return _FakeResponse(200, '{"windowHours":24,"rules":[],"alerts":[]}')
        if req.full_url.endswith("/api/dashboard/logs?limit=20"):
            return _FakeResponse(200, '{"items":[],"total":0}')
        raise AssertionError(f"unexpected url {req.full_url}")

    payload = script_module.run_collect_security_acceptance_evidence(
        backend_base_url="http://127.0.0.1:8080",
        access_token="operator-token",
        output_dir=str(tmp_path),
        write_report=True,
        opener=opener,
    )

    assert payload["ok"] is True
    assert payload["auth"]["snapshot_attempted"] is True
    assert payload["control_plane_snapshots"]["security_report"]["status_code"] == 200
    assert Path(payload["artifacts"]["json_report"]).exists()
    assert Path(payload["artifacts"]["markdown_report"]).exists()
