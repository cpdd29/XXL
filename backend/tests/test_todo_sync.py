from __future__ import annotations

from pathlib import Path

from scripts.check_todo_sync import run_todo_sync_check


def test_todo_sync_passes_when_completed_entries_point_to_existing_files(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "docs").mkdir()
    (repo_root / "docs" / "stages").mkdir()
    (repo_root / "backend").mkdir()
    (repo_root / "backend" / "scripts").mkdir()
    (repo_root / "backend" / "scripts" / "ok.py").write_text("print('ok')\n", encoding="utf-8")
    (repo_root / "docs" / "stages" / "NEXT_STAGE_3_TODO.md").write_text(
        "\n".join(
            [
                "## Package Z",
                "",
                "- [x] 新增 `backend/scripts/ok.py`",
                "",
                "当前状态：",
                "",
                "- 已新增 `backend/scripts/ok.py`",
            ]
        ),
        encoding="utf-8",
    )

    payload = run_todo_sync_check(repo_root, todo_files=["docs/stages/NEXT_STAGE_3_TODO.md"])

    assert payload["ok"] is True
    assert payload["missing_references"] == []
    assert payload["completed_package_without_status"] == []


def test_todo_sync_fails_when_completed_entry_points_to_missing_file(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "docs").mkdir()
    (repo_root / "docs" / "stages").mkdir()
    (repo_root / "docs" / "stages" / "NEXT_STAGE_3_TODO.md").write_text(
        "## Package Z\n\n- [x] 新增 `backend/scripts/missing.py`\n",
        encoding="utf-8",
    )

    payload = run_todo_sync_check(repo_root, todo_files=["docs/stages/NEXT_STAGE_3_TODO.md"])

    assert payload["ok"] is False
    assert payload["missing_references"][0]["reference"] == "backend/scripts/missing.py"


def test_todo_sync_fails_when_completed_package_has_no_status_block(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "docs").mkdir()
    (repo_root / "docs" / "stages").mkdir()
    (repo_root / "backend").mkdir()
    (repo_root / "backend" / "scripts").mkdir()
    (repo_root / "backend" / "scripts" / "ok.py").write_text("print('ok')\n", encoding="utf-8")
    (repo_root / "docs" / "stages" / "NEXT_STAGE_3_TODO.md").write_text(
        "## Package Z\n\n- [x] 新增 `backend/scripts/ok.py`\n",
        encoding="utf-8",
    )

    payload = run_todo_sync_check(repo_root, todo_files=["docs/stages/NEXT_STAGE_3_TODO.md"])

    assert payload["ok"] is False
    assert payload["completed_package_without_status"][0]["package"] == "## Package Z"
