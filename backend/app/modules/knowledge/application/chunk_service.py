from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import re

from app.modules.knowledge.schemas import KnowledgeChunk, KnowledgeDocument


HEADING_PATTERN = re.compile(r"^\s*(#{1,6})\s+(.+?)\s*$")
DEFAULT_MAX_CHUNK_CHARS = 800
DEFAULT_OVERLAP_CHARS = 120
MAX_SUMMARY_LENGTH = 120


def _now_string() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


class KnowledgeChunkService:
    """知识文档切片服务骨架。"""

    def build_chunks(
        self,
        *,
        document: KnowledgeDocument,
        max_chunk_chars: int | None = None,
        overlap_chars: int | None = None,
    ) -> list[KnowledgeChunk]:
        """根据文档内容生成可检索切片。"""
        normalized_text = _normalize_text(document.normalized_text)
        if not normalized_text:
            return []

        resolved_max_chunk_chars = max(int(max_chunk_chars or DEFAULT_MAX_CHUNK_CHARS), 200)
        resolved_overlap_chars = max(int(overlap_chars or DEFAULT_OVERLAP_CHARS), 0)
        sections = self._split_sections(document)
        chunks: list[KnowledgeChunk] = []
        chunk_index = 0
        for heading_path, title, content in sections:
            for piece in self._split_content(
                content,
                max_chunk_chars=resolved_max_chunk_chars,
                overlap_chars=resolved_overlap_chars,
            ):
                chunk_index += 1
                payload = f"{document.document_id}|{chunk_index}|{heading_path or ''}|{piece}"
                chunk_id = f"chunk-{hashlib.sha1(payload.encode('utf-8')).hexdigest()[:16]}"
                timestamp = _now_string()
                chunks.append(
                    KnowledgeChunk(
                        chunk_id=chunk_id,
                        document_id=document.document_id,
                        vault_id=document.vault_id,
                        tenant_id=document.tenant_id,
                        scope=document.scope,
                        title=title,
                        heading_path=heading_path,
                        summary=self.summarize_chunk(piece),
                        content=piece,
                        tags=list(document.tags),
                        source_path=document.source_path,
                        chunk_index=chunk_index,
                        token_estimate=self.estimate_tokens(piece),
                        embedding_status="pending",
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                )
        return chunks

    def summarize_chunk(self, content: str) -> str | None:
        """生成切片摘要。"""
        normalized = " ".join(_normalize_text(content).split())
        if not normalized:
            return None
        if len(normalized) <= MAX_SUMMARY_LENGTH:
            return normalized
        return normalized[:MAX_SUMMARY_LENGTH].rstrip() + "..."

    def estimate_tokens(self, content: str) -> int | None:
        """估算切片 token 数量。"""
        normalized = _normalize_text(content)
        if not normalized:
            return None
        return max(len(normalized) // 2, 1)

    def _split_sections(self, document: KnowledgeDocument) -> list[tuple[str | None, str, str]]:
        lines = document.normalized_text.split("\n")
        heading_stack: list[str] = []
        current_lines: list[str] = []
        current_heading_path: str | None = None
        current_title = document.title
        sections: list[tuple[str | None, str, str]] = []

        def flush() -> None:
            content = "\n".join(current_lines).strip()
            if not content:
                return
            sections.append((current_heading_path, current_title, content))

        for line in lines:
            match = HEADING_PATTERN.match(line)
            if match:
                flush()
                current_lines = []
                level = len(match.group(1))
                heading = _normalize_text(match.group(2)) or document.title
                heading_stack[:] = heading_stack[: level - 1]
                heading_stack.append(heading)
                current_heading_path = " / ".join(heading_stack)
                current_title = heading
                continue
            current_lines.append(line)
        flush()
        if not sections:
            return [(None, document.title, document.normalized_text)]
        return sections

    def _split_content(
        self,
        content: str,
        *,
        max_chunk_chars: int,
        overlap_chars: int,
    ) -> list[str]:
        paragraphs = [item.strip() for item in re.split(r"\n{2,}", content) if item.strip()]
        if not paragraphs:
            return [content.strip()]

        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            candidate = paragraph if not current else f"{current}\n\n{paragraph}"
            if len(candidate) <= max_chunk_chars:
                current = candidate
                continue
            if current:
                chunks.append(current.strip())
            if len(paragraph) <= max_chunk_chars:
                current = paragraph
                continue
            slices = self._split_long_paragraph(
                paragraph,
                max_chunk_chars=max_chunk_chars,
                overlap_chars=overlap_chars,
            )
            chunks.extend(slices[:-1])
            current = slices[-1]
        if current:
            chunks.append(current.strip())
        return [item for item in chunks if item]

    def _split_long_paragraph(
        self,
        paragraph: str,
        *,
        max_chunk_chars: int,
        overlap_chars: int,
    ) -> list[str]:
        if len(paragraph) <= max_chunk_chars:
            return [paragraph]
        items: list[str] = []
        start = 0
        step = max(max_chunk_chars - overlap_chars, 1)
        while start < len(paragraph):
            piece = paragraph[start : start + max_chunk_chars].strip()
            if piece:
                items.append(piece)
            start += step
        return items


knowledge_chunk_service = KnowledgeChunkService()
