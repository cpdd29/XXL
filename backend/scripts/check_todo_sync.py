from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
DEFAULT_TODO_FILES = (
    "docs/stages/NEXT_STAGE_4_TODO.md",
    "docs/stages/NEXT_STAGE_3_TODO.md",
    "docs/archive/completed-stages/SECURITY_CENTER_TODO.md",
    "docs/archive/completed-stages/BRAIN_CORE_TODO.md",
    "docs/archive/completed-stages/NATS_PROTOCOL_TODO.md",
)
PATH_SUFFIXES = (".md", ".py", ".ts", ".tsx", ".json", ".sh")
ROOT_PREFIXES = ("backend/", "reception/", "docs/", "agents/", "skills/")
CODE_PATTERN = re.compile(r"`([^`]+)`")


def _looks_like_repo_path(value: str) -> bool:
    candidate = str(value or "").strip()
    if not candidate or "://" in candidate or candidate.startswith("app://"):
        return False
    if any(candidate.startswith(prefix) for prefix in ROOT_PREFIXES):
        return True
    return candidate.endswith(PATH_SUFFIXES) and " " not in candidate


def _extract_tracked_paths(line: str) -> list[str]:
    paths: list[str] = []
    for raw in CODE_PATTERN.findall(line):
        for token in str(raw or "").strip().split():
            candidate = token.strip(",)")
            if _looks_like_repo_path(candidate):
                paths.append(candidate)
    return paths


def _tracked_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("- [x]") or stripped.startswith("- 已")


def _missing_reference_items(doc_path: Path, repo_root: Path) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    for line_no, line in enumerate(doc_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not _tracked_line(line):
            continue
        for ref in _extract_tracked_paths(line):
            resolved = _resolve_reference_path(repo_root, ref)
            if resolved.exists():
                continue
            missing.append(
                {
                    "file": str(doc_path),
                    "line": str(line_no),
                    "reference": ref,
                }
            )
    return missing


def _resolve_reference_path(repo_root: Path, reference: str) -> Path:
    candidate = str(reference or "").strip()
    if any(candidate.startswith(prefix) for prefix in ROOT_PREFIXES):
        return (repo_root / candidate).resolve()
    if candidate.endswith(PATH_SUFFIXES) and "/" not in candidate:
        matches = sorted(repo_root.rglob(candidate))
        if len(matches) == 1:
            return matches[0].resolve()
    return (repo_root / candidate).resolve()


def _completed_package_status_gaps(doc_path: Path) -> list[dict[str, str]]:
    if doc_path.name != "NEXT_STAGE_3_TODO.md":
        return []
    text = doc_path.read_text(encoding="utf-8")
    sections = text.split("\n## ")
    gaps: list[dict[str, str]] = []
    for index, chunk in enumerate(sections):
        section = chunk if index == 0 else f"## {chunk}"
        if not section.startswith("## Package "):
            continue
        header = section.splitlines()[0].strip()
        checkbox_lines = [line.strip() for line in section.splitlines() if line.strip().startswith("- [")]
        if not checkbox_lines:
            continue
        all_done = all(line.startswith("- [x]") for line in checkbox_lines)
        has_status = "当前状态：" in section or "当前已完成：" in section
        if all_done and not has_status:
            gaps.append({"file": str(doc_path), "package": header})
    return gaps


def run_todo_sync_check(repo_root: Path, todo_files: list[str] | None = None) -> dict[str, Any]:
    files = [repo_root / item for item in (todo_files or list(DEFAULT_TODO_FILES))]
    existing_files = [path for path in files if path.exists()]
    missing_references = [
        item
        for path in existing_files
        for item in _missing_reference_items(path, repo_root)
    ]
    status_gaps = [
        item
        for path in existing_files
        for item in _completed_package_status_gaps(path)
    ]
    return {
        "ok": not missing_references and not status_gaps,
        "files_checked": [str(path) for path in existing_files],
        "missing_references": missing_references,
        "completed_package_without_status": status_gaps,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TODO documents are synced with completed work.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--todo-file", action="append", dest="todo_files")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    payload = run_todo_sync_check(Path(args.repo_root).resolve(), todo_files=args.todo_files)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.strict and not payload["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
