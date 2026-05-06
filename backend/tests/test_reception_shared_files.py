from __future__ import annotations

from pathlib import Path

import app.modules.reception.shared_files.service as shared_files_module


def test_shared_files_roots_resolve_from_backend_root_for_container_like_path(tmp_path, monkeypatch) -> None:
    backend_root = tmp_path / "backend-runtime"
    (backend_root / "app").mkdir(parents=True)
    (backend_root / "alembic.ini").write_text("", encoding="utf-8")

    module_dir = backend_root / "app" / "modules" / "reception" / "shared_files"
    module_dir.mkdir(parents=True)
    fake_file = module_dir / "service.py"
    fake_file.write_text("# fake module path for root resolution", encoding="utf-8")

    monkeypatch.setattr(shared_files_module, "__file__", str(fake_file))
    monkeypatch.delenv("HERMES_RECEPTION_ARTIFACT_DIR", raising=False)
    monkeypatch.delenv("WORKBOT_RECEPTION_SHARED_FILE_DIR", raising=False)

    assert shared_files_module._project_root() == backend_root

    source_root = shared_files_module._source_root()
    target_root = shared_files_module._target_root()

    assert source_root == backend_root / ".runtime" / "reception_artifacts"
    assert target_root == backend_root / ".runtime" / "reception_shared_files"
    assert source_root.exists()
    assert target_root.exists()
