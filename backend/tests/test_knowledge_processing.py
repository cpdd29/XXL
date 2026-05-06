from __future__ import annotations

from pathlib import Path

from app.modules.knowledge.application import (
    knowledge_chunk_service,
    knowledge_import_service,
    knowledge_parser_service,
    knowledge_retrieval_service,
    knowledge_sync_service,
)
from app.modules.knowledge.application.vault_registry_service import KnowledgeVaultRegistryService
from app.modules.knowledge.schemas import (
    CreateVaultRegistryRequest,
    ImportKnowledgeVaultRequest,
    KnowledgeDocument,
    KnowledgeImportFileInput,
    KnowledgeRetrievalRequest,
)


def test_parser_extracts_frontmatter_and_body() -> None:
    raw_markdown = (
        "---\n"
        "title: 接待 FAQ\n"
        "category: reception\n"
        "tags:\n"
        "  - 接待\n"
        "  - FAQ\n"
        "aliases: [客户接待, FAQ]\n"
        "---\n\n"
        "# 接待 FAQ\n\n"
        "这里是正文。\n"
    )

    frontmatter, body = knowledge_parser_service.extract_frontmatter(raw_markdown)

    assert frontmatter["title"] == "接待 FAQ"
    assert frontmatter["category"] == "reception"
    assert frontmatter["tags"] == ["接待", "FAQ"]
    assert frontmatter["aliases"] == ["客户接待", "FAQ"]
    assert body.startswith("\n# 接待 FAQ")


def test_parser_build_document_resolves_heading_title_and_links() -> None:
    raw_markdown = (
        "---\n"
        "category: service\n"
        "tags: [接待, 流程]\n"
        "---\n\n"
        "# 客户接待流程\n\n"
        "请参考 [[售后说明]] 与 [[产品清单|产品目录]]。\n"
    )

    document = knowledge_parser_service.build_document(
        document_id="doc-001",
        vault_id="vault-001",
        tenant_id="tenant-alpha",
        scope="tenant",
        source_path="playbooks/reception.md",
        file_name="reception.md",
        raw_markdown=raw_markdown,
        checksum="checksum-001",
    )

    assert document.title == "客户接待流程"
    assert document.category == "service"
    assert document.tags == ["接待", "流程"]
    assert document.links == ["售后说明", "产品清单"]
    assert "客户接待流程" in document.normalized_text


def test_chunk_service_splits_sections_and_long_paragraphs() -> None:
    long_paragraph = "A" * 950
    document = KnowledgeDocument(
        document_id="doc-002",
        vault_id="vault-002",
        tenant_id="tenant-alpha",
        scope="tenant",
        source_path="guide.md",
        file_name="guide.md",
        title="实施指南",
        category="service",
        tags=["实施"],
        normalized_text=(
            "# 第一部分\n\n"
            "这是第一部分内容。\n\n"
            "## 第二部分\n\n"
            f"{long_paragraph}\n"
        ),
    )

    chunks = knowledge_chunk_service.build_chunks(
        document=document,
        max_chunk_chars=300,
        overlap_chars=60,
    )

    assert len(chunks) >= 4
    assert chunks[0].heading_path == "第一部分"
    assert any(chunk.heading_path == "第一部分 / 第二部分" for chunk in chunks)
    assert all((chunk.summary is None or len(chunk.summary) <= 123) for chunk in chunks)
    assert all((chunk.token_estimate or 0) > 0 for chunk in chunks)


def test_retrieval_deduplicates_multiple_chunks_from_same_document(tmp_path: Path) -> None:
    registry_service = KnowledgeVaultRegistryService(managed_vault_root=tmp_path)
    vault = registry_service.create_vault(
        CreateVaultRegistryRequest(
            vault_name="Dedup Tenant Vault",
            tenant_id="tenant-alpha",
            tenant_name="Alpha Corp",
            source_type="managed_fs",
        )
    ).vault

    knowledge_import_service.import_files(
        vault=vault,
        payload=ImportKnowledgeVaultRequest(
            files=[
                KnowledgeImportFileInput(
                    file_name="playbook.md",
                    content=(
                        "# 售后SLA\n\n"
                        "售后SLA 先确认响应等级。\n\n"
                        "## 追加说明\n\n"
                        "售后SLA 再确认是否需要升级工单。\n"
                    ),
                )
            ]
        ),
    )
    sync_response = knowledge_sync_service.sync_vault(vault_id=vault.vault_id)
    assert sync_response.ok is True

    response = knowledge_retrieval_service.retrieve(
        KnowledgeRetrievalRequest(
            tenant_id="tenant-alpha",
            query="售后SLA",
            scene="reception",
            top_k_tenant=5,
            top_k_shared=0,
        )
    )

    assert response.total == 1
    assert response.items[0].metadata.document_id is not None
    assert response.items[0].metadata.vault_id == vault.vault_id
