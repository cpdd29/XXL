from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import re
from typing import Any

from app.modules.knowledge.schemas import KnowledgeDocument


LINK_PATTERN = re.compile(r"\[\[([^\]]+)\]\]")
HEADING_PATTERN = re.compile(r"^\s*#{1,6}\s+(.+?)\s*$")
LIST_ITEM_PATTERN = re.compile(r"^\s*-\s+(.+?)\s*$")


def _now_string() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _normalize_list(value: object) -> list[str]:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            raw_items = stripped[1:-1].split(",")
        else:
            raw_items = [stripped]
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = []
    items: list[str] = []
    seen: set[str] = set()
    for raw in raw_items:
        candidate = _normalize_text(str(raw).strip().strip("'\""))
        if not candidate:
            continue
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(candidate)
    return items


class KnowledgeParserService:
    """知识源 Markdown 解析服务骨架。"""

    def extract_frontmatter(self, raw_markdown: str) -> tuple[dict[str, Any], str]:
        """拆出 frontmatter 与正文。"""
        normalized = raw_markdown.replace("\r\n", "\n").replace("\r", "\n")
        if not normalized.startswith("---\n"):
            return {}, normalized

        lines = normalized.split("\n")
        end_index = None
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                end_index = index
                break
        if end_index is None:
            return {}, normalized

        metadata = self._parse_frontmatter_lines(lines[1:end_index])
        body = "\n".join(lines[end_index + 1 :])
        return metadata, body

    def normalize_markdown(self, raw_markdown: str) -> str:
        """将原始 Markdown 归一化为平台可切片文本。"""
        normalized = raw_markdown.replace("\r\n", "\n").replace("\r", "\n")
        lines = [line.rstrip() for line in normalized.split("\n")]
        compacted: list[str] = []
        blank_count = 0
        for line in lines:
            if not line.strip():
                blank_count += 1
                if blank_count > 1:
                    continue
                compacted.append("")
                continue
            blank_count = 0
            compacted.append(line)
        return "\n".join(compacted).strip()

    def collect_links(self, normalized_text: str) -> list[str]:
        """抽取文档中的内部链接或外链。"""
        items: list[str] = []
        seen: set[str] = set()
        for match in LINK_PATTERN.findall(normalized_text):
            candidate = _normalize_text(match.split("|", maxsplit=1)[0])
            if not candidate:
                continue
            key = candidate.lower()
            if key in seen:
                continue
            seen.add(key)
            items.append(candidate)
        return items

    def build_document(
        self,
        *,
        document_id: str,
        vault_id: str,
        tenant_id: str | None,
        scope: str,
        source_path: str,
        file_name: str,
        raw_markdown: str,
        checksum: str | None = None,
        source_updated_at: str | None = None,
    ) -> KnowledgeDocument:
        """将单个知识源文件构造成平台文档对象。"""
        frontmatter, body = self.extract_frontmatter(raw_markdown)
        normalized_text = self.normalize_markdown(body)
        title = self._resolve_title(
            frontmatter=frontmatter,
            normalized_text=normalized_text,
            file_name=file_name,
        )
        tags = _normalize_list(frontmatter.get("tags") or frontmatter.get("tag"))
        aliases = _normalize_list(frontmatter.get("aliases") or frontmatter.get("alias"))
        category = _normalize_text(frontmatter.get("category")) or None
        document_updated_at = _normalize_text(source_updated_at or frontmatter.get("updated_at")) or None
        timestamp = _now_string()
        return KnowledgeDocument(
            document_id=document_id,
            vault_id=vault_id,
            tenant_id=_normalize_text(tenant_id) or None,
            scope=_normalize_text(scope) or "tenant",
            source_path=source_path,
            file_name=file_name,
            title=title,
            category=category,
            tags=tags,
            aliases=aliases,
            raw_markdown=raw_markdown,
            normalized_text=normalized_text,
            frontmatter=frontmatter,
            links=self.collect_links(normalized_text),
            checksum=_normalize_text(checksum) or None,
            version=1,
            status="active",
            created_at=timestamp,
            updated_at=timestamp,
            source_updated_at=document_updated_at,
        )

    def _parse_frontmatter_lines(self, lines: list[str]) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        current_key: str | None = None
        for raw_line in lines:
            line = raw_line.rstrip()
            if not line.strip():
                continue
            list_match = LIST_ITEM_PATTERN.match(line)
            if list_match and current_key:
                metadata.setdefault(current_key, [])
                if isinstance(metadata[current_key], list):
                    metadata[current_key].append(_normalize_text(list_match.group(1)).strip("'\""))
                continue
            current_key = None
            if ":" not in line:
                continue
            key, value = line.split(":", maxsplit=1)
            normalized_key = _normalize_text(key)
            normalized_value = value.strip()
            if not normalized_key:
                continue
            if not normalized_value:
                metadata[normalized_key] = []
                current_key = normalized_key
                continue
            if normalized_value.startswith("[") and normalized_value.endswith("]"):
                metadata[normalized_key] = _normalize_list(normalized_value)
                continue
            metadata[normalized_key] = normalized_value.strip("'\"")
        return metadata

    def _resolve_title(
        self,
        *,
        frontmatter: dict[str, Any],
        normalized_text: str,
        file_name: str,
    ) -> str:
        title = _normalize_text(frontmatter.get("title"))
        if title:
            return title
        for line in normalized_text.split("\n"):
            match = HEADING_PATTERN.match(line)
            if match:
                return _normalize_text(match.group(1)) or Path(file_name).stem
        return Path(file_name).stem


knowledge_parser_service = KnowledgeParserService()
