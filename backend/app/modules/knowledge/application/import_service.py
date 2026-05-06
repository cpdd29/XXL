from __future__ import annotations

from pathlib import Path, PurePosixPath

from app.modules.knowledge.schemas import (
    ImportKnowledgeVaultRequest,
    KnowledgeVaultImportResponse,
    VaultRegistry,
)


ALLOWED_IMPORT_SUFFIXES = {".md", ".markdown"}


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


class KnowledgeImportService:
    """平台托管知识仓导入服务。"""

    @staticmethod
    def _normalize_relative_path(file_name: str) -> str:
        normalized = _normalize_text(file_name).replace("\\", "/")
        if not normalized:
            raise ValueError("导入文件名不能为空")

        path = PurePosixPath(normalized)
        parts = [part for part in path.parts if part not in {"", "."}]
        if any(part == ".." for part in parts):
            raise ValueError(f"非法导入路径: {file_name}")
        if not parts:
            raise ValueError("导入文件名不能为空")

        relative_path = PurePosixPath(*parts)
        if relative_path.suffix.lower() not in ALLOWED_IMPORT_SUFFIXES:
            raise ValueError(f"仅支持导入 Markdown 文件: {file_name}")
        return str(relative_path)

    def import_files(
        self,
        *,
        vault: VaultRegistry,
        payload: ImportKnowledgeVaultRequest,
    ) -> KnowledgeVaultImportResponse:
        if vault.source_type != "managed_fs":
            raise ValueError("只有平台托管知识仓支持导入文件")

        if not payload.files:
            raise ValueError("请至少选择一个 Markdown 文件")

        vault_path = Path(vault.local_path).resolve()
        vault_path.mkdir(parents=True, exist_ok=True)

        imported_files: list[str] = []
        for item in payload.files:
            relative_path = self._normalize_relative_path(item.file_name)
            target_path = vault_path.joinpath(relative_path).resolve()
            if vault_path not in target_path.parents and target_path != vault_path:
                raise ValueError(f"非法导入目标路径: {item.file_name}")

            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(item.content, encoding="utf-8")
            imported_files.append(relative_path)

        return KnowledgeVaultImportResponse(
            ok=True,
            message=f"已导入 {len(imported_files)} 个 Markdown 文件",
            vault_id=vault.vault_id,
            vault_path=str(vault_path),
            imported_files=imported_files,
            total_files=len(imported_files),
        )


knowledge_import_service = KnowledgeImportService()
