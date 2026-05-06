from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from pathlib import Path

from app.platform.contracts.api_model import APIModel


MARKDOWN_SUFFIXES = {".md", ".markdown"}
SKIPPED_DIRECTORY_NAMES = {".git", ".obsidian", ".trash", "__pycache__"}


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _isoformat_from_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=UTC).isoformat()


class ObsidianMarkdownFile(APIModel):
    absolute_path: str
    relative_path: str
    file_name: str
    checksum: str
    updated_at: str
    size_bytes: int
    raw_markdown: str


class ObsidianVaultScanResult(APIModel):
    vault_path: str
    file_count: int = 0
    directories: list[str] = []
    items: list[ObsidianMarkdownFile]


class ObsidianFilesystemAdapter:
    """Obsidian 本地文件系统适配器。"""

    def normalize_vault_path(self, local_path: str) -> Path:
        normalized = _normalize_text(local_path)
        if not normalized:
            raise ValueError("Vault local_path is required")

        path = Path(normalized).expanduser()
        if not path.is_absolute():
            path = path.resolve()
        else:
            path = path.resolve(strict=False)
        return path

    def validate_vault_path(self, local_path: str) -> str:
        path = self.normalize_vault_path(local_path)
        if not path.exists():
            raise ValueError(f"Vault path does not exist: {path}")
        if not path.is_dir():
            raise ValueError(f"Vault path is not a directory: {path}")
        return str(path)

    def iter_markdown_paths(self, local_path: str) -> list[Path]:
        vault_path = Path(self.validate_vault_path(local_path))
        items: list[Path] = []
        for path in vault_path.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in MARKDOWN_SUFFIXES:
                continue
            if self._should_skip(path, vault_path=vault_path):
                continue
            items.append(path)
        items.sort(key=lambda item: str(item.relative_to(vault_path)).lower())
        return items

    def iter_directory_paths(self, local_path: str) -> list[Path]:
        vault_path = Path(self.validate_vault_path(local_path))
        items: list[Path] = []
        for path in vault_path.rglob("*"):
            if not path.is_dir():
                continue
            if self._should_skip_directory(path, vault_path=vault_path):
                continue
            items.append(path)
        items.sort(key=lambda item: str(item.relative_to(vault_path)).lower())
        return items

    def read_markdown_file(self, *, vault_path: str, file_path: str | Path) -> ObsidianMarkdownFile:
        resolved_vault_path = Path(self.validate_vault_path(vault_path))
        path = Path(file_path)
        if not path.is_absolute():
            path = resolved_vault_path.joinpath(path)
        path = path.resolve(strict=True)

        if self._should_skip(path, vault_path=resolved_vault_path):
            raise ValueError(f"Markdown file is not allowed for scan: {path}")
        if path.suffix.lower() not in MARKDOWN_SUFFIXES:
            raise ValueError(f"Unsupported markdown file: {path}")
        if not path.is_file():
            raise ValueError(f"Markdown file does not exist: {path}")

        raw_bytes = path.read_bytes()
        raw_markdown = raw_bytes.decode("utf-8")
        stat = path.stat()
        return ObsidianMarkdownFile(
            absolute_path=str(path),
            relative_path=str(path.relative_to(resolved_vault_path)),
            file_name=path.name,
            checksum=hashlib.sha256(raw_bytes).hexdigest(),
            updated_at=_isoformat_from_timestamp(stat.st_mtime),
            size_bytes=int(stat.st_size),
            raw_markdown=raw_markdown,
        )

    def scan_vault(self, local_path: str, *, limit: int | None = None) -> ObsidianVaultScanResult:
        resolved_vault_path = self.validate_vault_path(local_path)
        directory_paths = self.iter_directory_paths(resolved_vault_path)
        markdown_paths = self.iter_markdown_paths(resolved_vault_path)
        if isinstance(limit, int) and limit >= 0:
            markdown_paths = markdown_paths[:limit]

        items = [
            self.read_markdown_file(vault_path=resolved_vault_path, file_path=path)
            for path in markdown_paths
        ]
        return ObsidianVaultScanResult(
            vault_path=resolved_vault_path,
            file_count=len(items),
            directories=[str(path.relative_to(resolved_vault_path)).replace("\\", "/") for path in directory_paths],
            items=items,
        )

    def _should_skip_directory(self, path: Path, *, vault_path: Path) -> bool:
        try:
            relative = path.relative_to(vault_path)
        except ValueError:
            return True
        for part in relative.parts:
            if part in SKIPPED_DIRECTORY_NAMES or part.startswith("."):
                return True
        return False

    def _should_skip(self, path: Path, *, vault_path: Path) -> bool:
        try:
            relative = path.relative_to(vault_path)
        except ValueError:
            return True
        for part in relative.parts[:-1]:
            if part in SKIPPED_DIRECTORY_NAMES or part.startswith("."):
                return True
        return False


obsidian_filesystem_adapter = ObsidianFilesystemAdapter()
