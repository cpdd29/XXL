from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import os
from pathlib import Path
import re
import shutil
from threading import Lock
from typing import Any
from uuid import uuid4

from app.config import get_settings


_ALLOWED_EXTENSIONS = {
    ".md",
    ".pdf",
    ".docx",
    ".xlsx",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".bmp",
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".webm",
}
_TOKEN_RE = re.compile(r"^[a-zA-Z0-9_-]{12,80}$")
_DEFAULT_MAX_BYTES = 100 * 1024 * 1024


def _project_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "docker-compose.yml").exists() or (parent / "run-brain.sh").exists():
            return parent
        if (parent / "alembic.ini").exists() and (parent / "app").is_dir():
            return parent
    return current.parents[4]


def _source_root() -> Path:
    configured = str(os.getenv("HERMES_RECEPTION_ARTIFACT_DIR") or "").strip()
    if configured:
        root = Path(configured).expanduser().resolve()
    else:
        root = (_project_root() / ".runtime" / "reception_artifacts").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _target_root() -> Path:
    configured = str(os.getenv("WORKBOT_RECEPTION_SHARED_FILE_DIR") or "").strip()
    if configured:
        root = Path(configured).expanduser().resolve()
    else:
        root = (_project_root() / ".runtime" / "reception_shared_files").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_filename(name: str) -> str:
    normalized = re.sub(r"[^\w.\-]+", "_", str(name or "").strip())
    normalized = normalized.strip("._")
    return normalized or f"attachment_{uuid4().hex[:8]}"


def _is_under_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


class ReceptionSharedFilesService:
    def __init__(self) -> None:
        self._source_root = _source_root()
        self._target_root = _target_root()
        self._max_bytes = int(os.getenv("WORKBOT_RECEPTION_SHARED_FILE_MAX_BYTES") or _DEFAULT_MAX_BYTES)
        self._items: dict[str, dict[str, Any]] = {}
        self._lock = Lock()

    def _download_path(self, token: str) -> str:
        return f"/api/reception/shared-files/{token}/download"

    def _base_url(self, request_base_url: str | None = None) -> str:
        base = str(request_base_url or "").strip().rstrip("/")
        if base:
            return base
        fallback = str(get_settings().reception_public_base_url or "").strip().rstrip("/")
        return fallback

    def _copy(self, *, source_path: str, title: str, file_name: str, tenant_id: str | None, customer_id: str | None) -> dict[str, Any]:
        resolved = Path(source_path).expanduser().resolve()
        if not resolved.exists() or not resolved.is_file():
            raise ValueError(f"附件不存在: {source_path}")
        if not _is_under_root(resolved, self._source_root):
            raise ValueError("附件路径不在允许目录内")

        ext = resolved.suffix.lower()
        if ext not in _ALLOWED_EXTENSIONS:
            raise ValueError(f"不支持的附件类型: {ext or 'unknown'}")
        size_bytes = int(resolved.stat().st_size)
        if size_bytes > self._max_bytes:
            raise ValueError("附件超过大小限制")

        day_dir = self._target_root / datetime.now(UTC).strftime("%Y%m%d")
        day_dir.mkdir(parents=True, exist_ok=True)
        target_name = _safe_filename(file_name)
        token = f"sf_{uuid4().hex}"
        target = day_dir / f"{token}_{target_name}"
        shutil.copy2(resolved, target)

        record = {
            "token": token,
            "title": str(title or "").strip() or target_name,
            "file_name": target_name,
            "mime_type": "application/octet-stream",
            "kind": None,
            "format": ext.lstrip(".") or None,
            "size_bytes": size_bytes,
            "tenant_id": str(tenant_id or "").strip() or None,
            "customer_id": str(customer_id or "").strip() or None,
            "source_path": str(resolved),
            "storage_path": str(target),
            "created_at": datetime.now(UTC).isoformat(),
        }
        with self._lock:
            self._items[token] = deepcopy(record)
        return record

    def register_attachments(
        self,
        *,
        attachments: list[dict[str, Any]],
        tenant_id: str | None,
        customer_id: str | None,
        request_base_url: str | None = None,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        registered: list[dict[str, Any]] = []
        errors: list[str] = []
        for index, item in enumerate(attachments):
            if not isinstance(item, dict):
                errors.append(f"attachment[{index}] 格式无效")
                continue
            file_path = str(item.get("file_path") or item.get("filePath") or "").strip()
            file_name = str(item.get("file_name") or item.get("fileName") or "").strip()
            title = str(item.get("title") or file_name).strip()
            mime_type = str(item.get("mime_type") or item.get("mimeType") or "").strip() or "application/octet-stream"
            kind = str(item.get("kind") or "").strip() or None
            format_value = str(item.get("format") or "").strip() or None
            if not file_path or not file_name:
                errors.append(f"attachment[{index}] 缺少 file_path/file_name")
                continue
            try:
                saved = self._copy(
                    source_path=file_path,
                    title=title,
                    file_name=file_name,
                    tenant_id=tenant_id,
                    customer_id=customer_id,
                )
            except Exception as exc:
                errors.append(f"attachment[{index}] 注册失败: {exc}")
                continue

            download_path = self._download_path(saved["token"])
            base_url = self._base_url(request_base_url)
            public_url = f"{base_url}{download_path}" if base_url else download_path
            registered.append(
                {
                    "token": saved["token"],
                    "title": saved["title"],
                    "file_name": saved["file_name"],
                    "mime_type": mime_type,
                    "kind": kind,
                    "format": format_value or saved.get("format"),
                    "size_bytes": saved["size_bytes"],
                    "download_path": download_path,
                    "download_url": public_url,
                    "created_at": saved["created_at"],
                }
            )
        return registered, errors

    def resolve_download(self, token: str) -> dict[str, Any] | None:
        normalized = str(token or "").strip()
        if not _TOKEN_RE.match(normalized):
            return None
        with self._lock:
            record = deepcopy(self._items.get(normalized))
        if not isinstance(record, dict):
            return None
        path = Path(str(record.get("storage_path") or "")).expanduser()
        if not path.exists() or not path.is_file():
            return None
        record["storage_path"] = str(path.resolve())
        return record


reception_shared_files_service = ReceptionSharedFilesService()
