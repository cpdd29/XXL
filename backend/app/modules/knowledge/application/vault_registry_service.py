from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from app.modules.knowledge.schemas import (
    CreateVaultRegistryRequest,
    KnowledgeVaultValidationResponse,
    UpdateVaultRegistryRequest,
    VaultRegistry,
    VaultRegistryActionResponse,
    VaultRegistryDeleteResponse,
    VaultRegistryListResponse,
)
from app.modules.knowledge.adapters import obsidian_filesystem_adapter
from app.modules.knowledge.storage import (
    KnowledgeVaultStore,
    system_setting_knowledge_vault_store,
)
from app.platform.persistence.runtime_store import store
from uuid import uuid4


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


class KnowledgeVaultRegistryService:
    """知识仓注册管理服务骨架。"""

    def __init__(
        self,
        *,
        vault_store: KnowledgeVaultStore | None = None,
        managed_vault_root: Path | None = None,
        external_vault_roots: Iterable[Path] | None = None,
    ) -> None:
        self._vault_store = vault_store or system_setting_knowledge_vault_store
        self._managed_vault_root = managed_vault_root or Path(__file__).resolve().parents[5]
        self._external_vault_roots = self._resolve_external_vault_roots(external_vault_roots)

    def _resolve_external_vault_roots(self, roots: Iterable[Path] | None) -> tuple[Path, ...]:
        candidates = list(roots or [self._managed_vault_root, self._managed_vault_root.parent])
        resolved: list[Path] = []
        seen: set[str] = set()
        for item in candidates:
            path = Path(item).expanduser().resolve(strict=False)
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            resolved.append(path)
        return tuple(resolved)

    @staticmethod
    def _normalize_vault_type(value: object) -> str:
        normalized = _normalize_text(value).lower() or "tenant"
        if normalized not in {"shared", "tenant"}:
            raise ValueError("vault_type must be 'shared' or 'tenant'")
        return normalized

    @staticmethod
    def _normalize_sync_mode(value: object) -> str:
        normalized = _normalize_text(value).lower() or "manual"
        if normalized not in {"manual", "scheduled"}:
            raise ValueError("sync_mode must be 'manual' or 'scheduled'")
        return normalized

    @staticmethod
    def _normalize_source_type(value: object) -> str:
        normalized = _normalize_text(value).lower() or "managed_fs"
        if normalized not in {"obsidian_fs", "managed_fs", "external_obsidian_fs"}:
            raise ValueError("source_type must be one of 'managed_fs', 'external_obsidian_fs', 'obsidian_fs'")
        return normalized

    def _validated_local_path(self, local_path: str) -> str:
        return obsidian_filesystem_adapter.validate_vault_path(local_path)

    @staticmethod
    def _path_within_root(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    def _validated_external_local_path(self, local_path: str) -> str:
        normalized_path = Path(self._validated_local_path(local_path)).resolve(strict=False)
        if any(self._path_within_root(normalized_path, root) for root in self._external_vault_roots):
            return str(normalized_path)

        allowed_roots = ", ".join(str(root) for root in self._external_vault_roots)
        raise ValueError(f"Vault path is outside allowed roots: {normalized_path}; allowed_roots={allowed_roots}")

    @staticmethod
    def _normalize_path_fragment(value: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip())
        normalized = normalized.strip("-_")
        return normalized or "default"

    def build_managed_vault_path(self, tenant_id: str) -> str:
        normalized_tenant_id = _normalize_text(tenant_id)
        if not normalized_tenant_id:
            raise ValueError("tenant_id is required for managed knowledge vault")
        directory_name = f"tenantid_{self._normalize_path_fragment(normalized_tenant_id)}"
        return str(self._managed_vault_root.joinpath(directory_name).resolve())

    def _resolve_local_path(
        self,
        *,
        source_type: str,
        tenant_id: str | None,
        local_path: str | None,
    ) -> str:
        if source_type == "managed_fs":
            managed_path = Path(self.build_managed_vault_path(str(tenant_id or "")))
            managed_path.mkdir(parents=True, exist_ok=True)
            return str(managed_path)

        normalized_local_path = _normalize_text(local_path)
        if not normalized_local_path:
            raise ValueError(f"local_path is required when source_type={source_type}")
        return self._validated_external_local_path(normalized_local_path)

    def _ensure_unique_constraints(
        self,
        *,
        vault_id: str | None,
        vault_type: str,
        tenant_id: str | None,
        local_path: str,
    ) -> None:
        for item in self._vault_store.list_vaults():
            if vault_id and item.vault_id == vault_id:
                continue
            if item.local_path == local_path:
                raise ValueError(f"Vault local_path already registered: {local_path}")
            if vault_type == "tenant" and item.vault_type == "tenant" and item.tenant_id == tenant_id:
                raise ValueError(f"Tenant vault already exists: tenant_id={tenant_id}")

    def _build_vault(
        self,
        *,
        vault_id: str,
        vault_name: str,
        vault_type: str,
        tenant_id: str | None,
        tenant_name: str | None,
        source_type: str,
        local_path: str | None,
        enabled: bool,
        sync_mode: str,
        remark: str | None,
        metadata: dict[str, object],
        last_sync_at: str | None = None,
        last_sync_status: str = "never_synced",
    ) -> VaultRegistry:
        normalized_vault_name = _normalize_text(vault_name)
        if not normalized_vault_name:
            raise ValueError("vault_name is required")

        normalized_vault_type = self._normalize_vault_type(vault_type)
        normalized_sync_mode = self._normalize_sync_mode(sync_mode)
        normalized_source_type = self._normalize_source_type(source_type)
        normalized_tenant_id = _normalize_text(tenant_id) or None
        normalized_tenant_name = _normalize_text(tenant_name) or None
        if normalized_vault_type == "tenant" and not normalized_tenant_id:
            raise ValueError("tenant_id is required when vault_type=tenant")
        if normalized_vault_type == "shared":
            normalized_tenant_id = None
            normalized_tenant_name = None
            if normalized_source_type == "managed_fs":
                raise ValueError("shared knowledge vault does not support managed_fs")

        normalized_local_path = self._resolve_local_path(
            source_type=normalized_source_type,
            tenant_id=normalized_tenant_id,
            local_path=local_path,
        )

        self._ensure_unique_constraints(
            vault_id=vault_id,
            vault_type=normalized_vault_type,
            tenant_id=normalized_tenant_id,
            local_path=normalized_local_path,
        )

        return VaultRegistry(
            vault_id=vault_id,
            vault_name=normalized_vault_name,
            vault_type=normalized_vault_type,  # type: ignore[arg-type]
            tenant_id=normalized_tenant_id,
            tenant_name=normalized_tenant_name,
            source_type=normalized_source_type,  # type: ignore[arg-type]
            local_path=normalized_local_path,
            enabled=bool(enabled),
            sync_mode=normalized_sync_mode,  # type: ignore[arg-type]
            last_sync_at=_normalize_text(last_sync_at) or None,
            last_sync_status=_normalize_text(last_sync_status).lower() or "never_synced",  # type: ignore[arg-type]
            remark=_normalize_text(remark) or None,
            metadata=dict(metadata or {}),
        )

    def list_vaults(
        self,
        *,
        vault_type: str | None = None,
        tenant_id: str | None = None,
        enabled: bool | None = None,
    ) -> VaultRegistryListResponse:
        """列出知识仓注册信息。"""
        items = self._vault_store.list_vaults(vault_type=vault_type, tenant_id=tenant_id, enabled=enabled)
        return VaultRegistryListResponse(
            items=items,
            total=len(items),
            updated_at=store.now_string(),
        )

    def get_vault(self, vault_id: str) -> VaultRegistry | None:
        """读取单个知识仓注册信息。"""
        return self._vault_store.get_vault(vault_id)

    def create_vault(self, payload: CreateVaultRegistryRequest) -> VaultRegistryActionResponse:
        """创建知识仓注册记录。"""
        vault = self._build_vault(
            vault_id=f"vault-{uuid4().hex[:12]}",
            vault_name=payload.vault_name,
            vault_type=payload.vault_type,
            tenant_id=payload.tenant_id,
            tenant_name=payload.tenant_name,
            source_type=payload.source_type,
            local_path=payload.local_path,
            enabled=payload.enabled,
            sync_mode=payload.sync_mode,
            remark=payload.remark,
            metadata=payload.metadata,
        )
        saved = self._vault_store.save_vault(vault)
        return VaultRegistryActionResponse(ok=True, message="知识仓已创建", vault=saved)

    def update_vault(
        self,
        vault_id: str,
        payload: UpdateVaultRegistryRequest,
    ) -> VaultRegistryActionResponse:
        """更新知识仓注册记录。"""
        current = self._vault_store.get_vault(vault_id)
        if current is None:
            raise KeyError(f"Knowledge vault '{vault_id}' not found")

        vault = self._build_vault(
            vault_id=current.vault_id,
            vault_name=payload.vault_name or current.vault_name,
            vault_type=current.vault_type,
            tenant_id=payload.tenant_id if payload.tenant_id is not None else current.tenant_id,
            tenant_name=payload.tenant_name if payload.tenant_name is not None else current.tenant_name,
            source_type=payload.source_type or current.source_type,
            local_path=payload.local_path or current.local_path,
            enabled=current.enabled if payload.enabled is None else payload.enabled,
            sync_mode=payload.sync_mode or current.sync_mode,
            remark=payload.remark if payload.remark is not None else current.remark,
            metadata=current.metadata if payload.metadata is None else payload.metadata,
            last_sync_at=current.last_sync_at,
            last_sync_status=current.last_sync_status,
        )
        saved = self._vault_store.save_vault(vault)
        return VaultRegistryActionResponse(ok=True, message="知识仓已更新", vault=saved)

    def delete_vault(self, vault_id: str) -> VaultRegistryDeleteResponse:
        """删除知识仓注册记录。"""
        deleted = self._vault_store.delete_vault(vault_id)
        if not deleted:
            raise KeyError(f"Knowledge vault '{vault_id}' not found")
        return VaultRegistryDeleteResponse(ok=True, message="知识仓已删除", vault_id=vault_id)

    def mark_sync_status(
        self,
        *,
        vault_id: str,
        status: str,
        last_sync_at: str | None = None,
    ) -> VaultRegistry | None:
        current = self._vault_store.get_vault(vault_id)
        if current is None:
            return None
        updated = current.model_copy(
            update={
                "last_sync_status": _normalize_text(status).lower() or current.last_sync_status,
                "last_sync_at": _normalize_text(last_sync_at) or store.now_string(),
            }
        )
        return self._vault_store.save_vault(updated)

    def resolve_effective_vaults(self, *, tenant_id: str) -> list[VaultRegistry]:
        """解析租户可见知识仓，后续用于两段检索。"""
        normalized_tenant_id = _normalize_text(tenant_id)
        if not normalized_tenant_id:
            return []

        tenant_vaults = self._vault_store.list_vaults(
            vault_type="tenant",
            tenant_id=normalized_tenant_id,
            enabled=True,
        )
        shared_vaults = self._vault_store.list_vaults(
            vault_type="shared",
            enabled=True,
        )
        return [
            *sorted(tenant_vaults, key=lambda item: item.vault_name.lower()),
            *sorted(shared_vaults, key=lambda item: item.vault_name.lower()),
        ]

    def validate_vault_source(self, vault: VaultRegistry) -> KnowledgeVaultValidationResponse:
        """校验知识仓数据源是否可访问。"""
        normalized_path = self._validated_local_path(vault.local_path)
        markdown_paths = obsidian_filesystem_adapter.iter_markdown_paths(normalized_path)
        sample_files = [str(path.relative_to(Path(normalized_path))) for path in markdown_paths[:10]]
        source_label = "外接目录" if vault.source_type != "managed_fs" else "平台托管目录"
        message = f"{source_label}可访问，当前识别到 {len(markdown_paths)} 个 Markdown 文件"
        return KnowledgeVaultValidationResponse(
            ok=True,
            message=message,
            vault_id=vault.vault_id,
            source_type=vault.source_type,
            local_path=normalized_path,
            markdown_file_count=len(markdown_paths),
            sample_files=sample_files,
            checked_at=store.now_string(),
        )


knowledge_vault_registry_service = KnowledgeVaultRegistryService()
