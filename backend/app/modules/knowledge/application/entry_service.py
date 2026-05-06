from __future__ import annotations

from pathlib import Path, PurePosixPath
import shutil

from app.modules.knowledge.adapters import obsidian_filesystem_adapter
from app.modules.knowledge.schemas import (
    CreateKnowledgeVaultFolderRequest,
    DeleteKnowledgeVaultEntryRequest,
    KnowledgeVaultEntryActionResponse,
    RenameKnowledgeVaultEntryRequest,
    VaultRegistry,
)


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


class KnowledgeVaultEntryService:
    """平台托管知识仓内文件节点管理。"""

    @staticmethod
    def _require_managed_vault(vault: VaultRegistry) -> Path:
        if vault.source_type != "managed_fs":
            raise ValueError("只有平台托管知识仓支持目录节点操作")
        vault_path = obsidian_filesystem_adapter.normalize_vault_path(vault.local_path)
        vault_path.mkdir(parents=True, exist_ok=True)
        return vault_path

    @staticmethod
    def _normalize_relative_path(value: str) -> PurePosixPath:
        normalized = _normalize_text(value).replace("\\", "/")
        if not normalized:
            raise ValueError("节点路径不能为空")

        path = PurePosixPath(normalized)
        parts = [part for part in path.parts if part not in {"", "."}]
        if not parts or any(part == ".." for part in parts):
            raise ValueError("节点路径非法")
        return PurePosixPath(*parts)

    @staticmethod
    def _resolve_entry(vault_path: Path, relative_path: PurePosixPath) -> Path:
        target = vault_path.joinpath(*relative_path.parts).resolve(strict=False)
        if vault_path not in target.parents and target != vault_path:
            raise ValueError("节点路径超出知识仓范围")
        if not target.exists():
            raise KeyError(f"知识节点不存在: {relative_path}")
        return target

    @staticmethod
    def _normalize_entry_name(value: str, *, is_file: bool, current_suffix: str) -> str:
        normalized = _normalize_text(value)
        if not normalized:
            raise ValueError("节点名称不能为空")
        if "/" in normalized or "\\" in normalized:
            raise ValueError("节点名称不能包含路径分隔符")
        if normalized in {".", ".."}:
            raise ValueError("节点名称非法")
        if is_file and Path(normalized).suffix == "":
            return f"{normalized}{current_suffix or '.md'}"
        return normalized

    def create_folder(
        self,
        *,
        vault: VaultRegistry,
        payload: CreateKnowledgeVaultFolderRequest,
    ) -> KnowledgeVaultEntryActionResponse:
        vault_path = self._require_managed_vault(vault)
        parent_dir = vault_path
        parent_relative = _normalize_text(payload.parent_path)
        if parent_relative:
            normalized_parent = self._normalize_relative_path(parent_relative)
            parent_dir = self._resolve_entry(vault_path, normalized_parent)
            if not parent_dir.is_dir():
                raise ValueError("父节点必须是目录")

        folder_name = self._normalize_entry_name(
            payload.name,
            is_file=False,
            current_suffix="",
        )
        target = parent_dir.joinpath(folder_name).resolve(strict=False)
        if vault_path not in target.parents and target != vault_path:
            raise ValueError("目录创建目标超出知识仓范围")
        if target.exists():
            raise ValueError(f"目标目录已存在: {folder_name}")

        target.mkdir(parents=False, exist_ok=False)
        next_relative_path = str(target.relative_to(vault_path)).replace("\\", "/")
        return KnowledgeVaultEntryActionResponse(
            ok=True,
            message="知识目录已创建",
            vault_id=vault.vault_id,
            entry_kind="folder",
            path=next_relative_path,
            next_path=next_relative_path,
        )

    def rename_entry(
        self,
        *,
        vault: VaultRegistry,
        payload: RenameKnowledgeVaultEntryRequest,
    ) -> KnowledgeVaultEntryActionResponse:
        vault_path = self._require_managed_vault(vault)
        relative_path = self._normalize_relative_path(payload.path)
        source = self._resolve_entry(vault_path, relative_path)

        next_name = self._normalize_entry_name(
            payload.new_name,
            is_file=source.is_file(),
            current_suffix=source.suffix,
        )
        target = source.with_name(next_name).resolve(strict=False)
        if vault_path not in target.parents and target != vault_path:
            raise ValueError("重命名目标超出知识仓范围")
        if target.exists():
            raise ValueError(f"目标节点已存在: {next_name}")

        source.rename(target)
        next_relative_path = str(target.relative_to(vault_path)).replace("\\", "/")
        return KnowledgeVaultEntryActionResponse(
            ok=True,
            message="知识节点已重命名",
            vault_id=vault.vault_id,
            entry_kind="file" if target.is_file() else "folder",
            path=str(relative_path),
            next_path=next_relative_path,
        )

    def delete_entry(
        self,
        *,
        vault: VaultRegistry,
        payload: DeleteKnowledgeVaultEntryRequest,
    ) -> KnowledgeVaultEntryActionResponse:
        vault_path = self._require_managed_vault(vault)
        relative_path = self._normalize_relative_path(payload.path)
        target = self._resolve_entry(vault_path, relative_path)
        entry_kind = "file" if target.is_file() else "folder"

        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()

        return KnowledgeVaultEntryActionResponse(
            ok=True,
            message="知识节点已删除",
            vault_id=vault.vault_id,
            entry_kind=entry_kind,
            path=str(relative_path),
            next_path=None,
        )


knowledge_vault_entry_service = KnowledgeVaultEntryService()
