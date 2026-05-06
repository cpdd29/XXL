from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.modules.knowledge.application import (
    knowledge_import_service,
    knowledge_retrieval_service,
    knowledge_sync_service,
    knowledge_vault_registry_service,
)
from app.modules.knowledge.application.entry_service import KnowledgeVaultEntryService
from app.modules.knowledge.application.import_service import KnowledgeImportService
from app.modules.knowledge.application.vault_registry_service import KnowledgeVaultRegistryService
from app.modules.knowledge.adapters import obsidian_filesystem_adapter
from app.modules.knowledge.schemas import (
    CreateKnowledgeVaultFolderRequest,
    CreateVaultRegistryRequest,
    ImportKnowledgeVaultRequest,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeRetrievalRequest,
    KnowledgeImportFileInput,
    UpdateVaultRegistryRequest,
)
from app.modules.knowledge.storage import (
    system_setting_knowledge_chunk_store,
    system_setting_knowledge_document_store,
    system_setting_knowledge_vault_store,
)


client = TestClient(app)


def _seed_document_and_chunk(
    *,
    document_id: str,
    vault_id: str,
    scope: str,
    tenant_id: str | None,
    title: str,
    source_path: str,
    content: str,
    tags: list[str] | None = None,
    status: str = "active",
) -> None:
    document = KnowledgeDocument(
        document_id=document_id,
        vault_id=vault_id,
        tenant_id=tenant_id,
        scope=scope,
        source_path=source_path,
        file_name=source_path.split("/")[-1],
        title=title,
        tags=list(tags or []),
        normalized_text=content,
        status=status,
        updated_at="2026-04-30T00:00:00+00:00",
    )
    chunk = KnowledgeChunk(
        chunk_id=f"chunk-{document_id}",
        document_id=document_id,
        vault_id=vault_id,
        tenant_id=tenant_id,
        scope=scope,
        title=title,
        summary=content,
        content=content,
        tags=list(tags or []),
        source_path=source_path,
        chunk_index=0,
    )
    system_setting_knowledge_document_store.save_document(document)
    system_setting_knowledge_chunk_store.replace_chunks_for_document(
        document_id=document_id,
        chunks=[chunk],
    )


def test_managed_vault_uses_auto_generated_tenant_directory(tmp_path: Path) -> None:
    service = KnowledgeVaultRegistryService(
        vault_store=system_setting_knowledge_vault_store,
        managed_vault_root=tmp_path,
    )

    response = service.create_vault(
        CreateVaultRegistryRequest(
            vault_name="Alpha 托管知识仓",
            tenant_id="tenant-alpha",
            tenant_name="Alpha Corp",
            source_type="managed_fs",
        )
    )

    expected_path = tmp_path.joinpath("tenantid_tenant-alpha").resolve()

    assert response.vault.source_type == "managed_fs"
    assert response.vault.local_path == str(expected_path)
    assert expected_path.exists()
    assert expected_path.is_dir()


def test_external_vault_requires_existing_local_directory(tmp_path: Path) -> None:
    external_path = tmp_path.joinpath("external-obsidian")
    external_path.mkdir(parents=True, exist_ok=True)

    service = KnowledgeVaultRegistryService(
        vault_store=system_setting_knowledge_vault_store,
        managed_vault_root=tmp_path,
    )

    response = service.create_vault(
        CreateVaultRegistryRequest(
            vault_name="Beta 外接知识仓",
            tenant_id="tenant-beta",
            tenant_name="Beta Corp",
            source_type="external_obsidian_fs",
            local_path=str(external_path),
        )
    )

    assert response.vault.source_type == "external_obsidian_fs"
    assert response.vault.local_path == str(external_path.resolve())


def test_managed_vault_supports_markdown_import(tmp_path: Path) -> None:
    registry_service = KnowledgeVaultRegistryService(
        vault_store=system_setting_knowledge_vault_store,
        managed_vault_root=tmp_path,
    )
    import_service = KnowledgeImportService()

    vault = registry_service.create_vault(
        CreateVaultRegistryRequest(
            vault_name="Gamma 托管知识仓",
            tenant_id="tenant-gamma",
            tenant_name="Gamma Corp",
            source_type="managed_fs",
        )
    ).vault

    response = import_service.import_files(
        vault=vault,
        payload=ImportKnowledgeVaultRequest(
            files=[
                KnowledgeImportFileInput(
                    file_name="welcome.md",
                    content="# Welcome\n这是导入内容。",
                )
            ]
        ),
    )

    imported_file = Path(vault.local_path).joinpath("welcome.md")

    assert response.ok is True
    assert response.total_files == 1
    assert response.imported_files == ["welcome.md"]
    assert imported_file.read_text(encoding="utf-8") == "# Welcome\n这是导入内容。"


def test_external_vault_validation_returns_markdown_samples(tmp_path: Path) -> None:
    external_path = tmp_path.joinpath("external-validation")
    external_path.mkdir(parents=True, exist_ok=True)
    external_path.joinpath("intro.md").write_text("# Intro\nHello", encoding="utf-8")
    external_path.joinpath("guide.markdown").write_text("# Guide\nWorld", encoding="utf-8")

    service = KnowledgeVaultRegistryService(
        vault_store=system_setting_knowledge_vault_store,
        managed_vault_root=tmp_path,
    )

    vault = service.create_vault(
        CreateVaultRegistryRequest(
            vault_name="Delta 外接知识仓",
            tenant_id="tenant-delta",
            tenant_name="Delta Corp",
            source_type="external_obsidian_fs",
            local_path=str(external_path),
        )
    ).vault

    result = service.validate_vault_source(vault)

    assert result.ok is True
    assert result.markdown_file_count == 2
    assert result.sample_files == ["guide.markdown", "intro.md"]


def test_managed_vault_create_folder_is_visible_in_scan_preview(tmp_path: Path) -> None:
    registry_service = KnowledgeVaultRegistryService(
        vault_store=system_setting_knowledge_vault_store,
        managed_vault_root=tmp_path,
    )
    entry_service = KnowledgeVaultEntryService()

    vault = registry_service.create_vault(
        CreateVaultRegistryRequest(
            vault_name="Zeta 托管知识仓",
            tenant_id="tenant-zeta",
            tenant_name="Zeta Corp",
            source_type="managed_fs",
        )
    ).vault

    response = entry_service.create_folder(
        vault=vault,
        payload=CreateKnowledgeVaultFolderRequest(
            parent_path=None,
            name="playbooks",
        ),
    )

    preview = obsidian_filesystem_adapter.scan_vault(vault.local_path)

    assert response.ok is True
    assert response.next_path == "playbooks"
    assert Path(vault.local_path).joinpath("playbooks").is_dir()
    assert preview.file_count == 0
    assert "playbooks" in preview.directories


def test_knowledge_document_routes_return_synced_documents(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(knowledge_vault_registry_service, "_managed_vault_root", tmp_path)

    vault = knowledge_vault_registry_service.create_vault(
        CreateVaultRegistryRequest(
            vault_name="Epsilon 托管知识仓",
            tenant_id="tenant-epsilon",
            tenant_name="Epsilon Corp",
            source_type="managed_fs",
        )
    ).vault

    knowledge_import_service.import_files(
        vault=vault,
        payload=ImportKnowledgeVaultRequest(
            files=[
                KnowledgeImportFileInput(
                    file_name="faq.md",
                    content=(
                        "---\n"
                        "title: 广州天气查询\n"
                        "category: reception\n"
                        "tags:\n"
                        "  - 接待\n"
                        "  - FAQ\n"
                        "---\n\n"
                        "# 广州天气查询\n\n"
                        "客户咨询广州天气时，先确认时间范围，再给出建议。\n"
                    ),
                )
            ]
        ),
    )

    sync_response = knowledge_sync_service.sync_vault(vault_id=vault.vault_id)

    assert sync_response.ok is True
    assert sync_response.job.status == "success"

    list_response = client.get(
        "/api/knowledge/documents",
        params={"vaultId": vault.vault_id},
    )
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["title"] == "广州天气查询"
    assert payload["items"][0]["category"] == "reception"

    document_id = payload["items"][0]["documentId"]
    detail_response = client.get(f"/api/knowledge/documents/{document_id}")

    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["document"]["documentId"] == document_id
    assert detail_payload["document"]["sourcePath"] == "faq.md"
    assert detail_payload["chunks"]
    assert "广州天气" in detail_payload["chunks"][0]["content"]


def test_retrieval_keeps_tenant_and_shared_boundary(tmp_path: Path) -> None:
    service = KnowledgeVaultRegistryService(
        vault_store=system_setting_knowledge_vault_store,
        managed_vault_root=tmp_path,
    )
    tenant_alpha_vault = service.create_vault(
        CreateVaultRegistryRequest(
            vault_name="Alpha Tenant Vault",
            vault_type="tenant",
            tenant_id="tenant-alpha",
            tenant_name="Alpha Corp",
            source_type="managed_fs",
        )
    ).vault
    tenant_beta_vault = service.create_vault(
        CreateVaultRegistryRequest(
            vault_name="Beta Tenant Vault",
            vault_type="tenant",
            tenant_id="tenant-beta",
            tenant_name="Beta Corp",
            source_type="managed_fs",
        )
    ).vault
    shared_path = tmp_path.joinpath("shared-vault")
    shared_path.mkdir(parents=True, exist_ok=True)
    shared_vault = service.create_vault(
        CreateVaultRegistryRequest(
            vault_name="Shared Vault",
            vault_type="shared",
            source_type="external_obsidian_fs",
            local_path=str(shared_path),
        )
    ).vault

    _seed_document_and_chunk(
        document_id="doc-tenant-alpha-1",
        vault_id=tenant_alpha_vault.vault_id,
        scope="tenant",
        tenant_id="tenant-alpha",
        title="Alpha 售后流程",
        source_path="tenant-alpha/after-sales.md",
        content="售后流程包含工单登记、响应时效和升级路径。",
        tags=["接待", "faq"],
    )
    _seed_document_and_chunk(
        document_id="doc-tenant-beta-1",
        vault_id=tenant_beta_vault.vault_id,
        scope="tenant",
        tenant_id="tenant-beta",
        title="Beta 售后流程",
        source_path="tenant-beta/after-sales.md",
        content="售后流程包含工单登记、响应时效和升级路径。",
        tags=["接待", "faq"],
    )
    _seed_document_and_chunk(
        document_id="doc-shared-1",
        vault_id=shared_vault.vault_id,
        scope="shared",
        tenant_id=None,
        title="共享售后 FAQ",
        source_path="shared/after-sales.md",
        content="售后流程统一要求先确认服务级别，再给处理时限。",
        tags=["faq"],
    )

    response = knowledge_retrieval_service.retrieve(
        KnowledgeRetrievalRequest(
            tenant_id="tenant-alpha",
            query="售后流程",
            scene="reception",
            top_k_tenant=5,
            top_k_shared=5,
        )
    )

    assert response.total == 2
    assert response.tenant_hits == 1
    assert response.shared_hits == 1
    assert {item.scope for item in response.items} == {"tenant", "shared"}
    assert all(item.metadata.document_id != "doc-tenant-beta-1" for item in response.items)


def test_resolve_effective_vaults_cuts_off_disabled_vaults(tmp_path: Path) -> None:
    service = KnowledgeVaultRegistryService(
        vault_store=system_setting_knowledge_vault_store,
        managed_vault_root=tmp_path,
    )
    enabled_tenant = service.create_vault(
        CreateVaultRegistryRequest(
            vault_name="Alpha Tenant Vault",
            vault_type="tenant",
            tenant_id="tenant-alpha",
            tenant_name="Alpha Corp",
            source_type="managed_fs",
            enabled=True,
        )
    ).vault
    shared_path = tmp_path.joinpath("shared-vault")
    shared_path.mkdir(parents=True, exist_ok=True)
    enabled_shared = service.create_vault(
        CreateVaultRegistryRequest(
            vault_name="Shared Vault",
            vault_type="shared",
            source_type="external_obsidian_fs",
            local_path=str(shared_path),
            enabled=True,
        )
    ).vault
    before_disable = service.resolve_effective_vaults(tenant_id="tenant-alpha")
    before_disable_ids = {item.vault_id for item in before_disable}
    assert enabled_tenant.vault_id in before_disable_ids
    assert enabled_shared.vault_id in before_disable_ids

    service.update_vault(
        enabled_tenant.vault_id,
        UpdateVaultRegistryRequest(enabled=False),
    )

    effective = service.resolve_effective_vaults(tenant_id="tenant-alpha")
    effective_ids = {item.vault_id for item in effective}

    assert enabled_shared.vault_id in effective_ids
    assert enabled_tenant.vault_id not in effective_ids
