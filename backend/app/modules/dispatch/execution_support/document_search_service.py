from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from html import unescape
import math
from pathlib import Path
import re

from app.config import get_settings


PROJECT_ROOT = Path(__file__).resolve().parents[5]
DOCS_ROOT_CANDIDATES = (
    PROJECT_ROOT / "docs",
    PROJECT_ROOT / "backend" / "docs",
)
MAX_CHUNK_CHARS = 720
SVG_LAYER_PREFIXES = ("①", "②", "③", "④", "⑤")
SECURITY_SECTION_ALIASES = {
    "③ prompt injection dual check": "③ Prompt injection scan",
    "③ prompt injection dual-check": "③ Prompt injection scan",
}
MEMORY_STAGE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Short-term", re.compile(r"^[①-⑤]\s*short[- ]term(?:\s+memory)?$", flags=re.IGNORECASE)),
    ("Mid-term", re.compile(r"^[①-⑤]\s*mid[- ]term(?:\s+memory)?$", flags=re.IGNORECASE)),
    ("Long-term", re.compile(r"^[①-⑤]\s*long[- ]term(?:\s+memory)?$", flags=re.IGNORECASE)),
)
INTENT_HINTS = {
    "search": ("搜索", "检索", "部署", "接入", "安全", "工作流", "记忆", "架构", "文档"),
    "write": ("项目", "架构", "目标", "优先级", "工作流", "安全", "记忆", "Agent", "MVP"),
    "help": ("说明", "步骤", "配置", "接入", "安全", "工作流", "Agent", "记忆"),
}
FALLBACK_KEYWORDS = {
    "search": ("部署", "开发环境", "接入", "安全", "工作流", "架构", "文档"),
    "write": ("项目背景", "产品目标", "架构", "开发优先级", "MVP", "安全", "工作流"),
    "help": ("接入", "安全", "工作流", "配置", "语言", "记忆", "Agent"),
}
SVG_SEARCH_ALIASES = {
    "security_gateway_pipeline.svg": "安全网关 五层流水线 限流 认证 RBAC prompt injection 双检 content policy 审计 遥测 trusted input",
    "memory_distillation_lifecycle.svg": "记忆蒸馏 生命周期 短期记忆 中期记忆 长期记忆 Redis SQLite ChromaDB 用户画像 偏好 语义检索",
}
VIRTUAL_MARKDOWN_DOCUMENTS: dict[str, str] = {
    "WorkBot_开发全指南.md": """# WorkBot 开发全指南

## Deployment
WorkBot deployment uses dispatch orchestration, document retrieval, and execution support services.

## Architecture
The platform combines workflow runtime, single-agent execution, and security controls for grounded task delivery.
""",
    "开发指南补充.md": """# 开发指南补充

## 安全网关 / 审计追踪
安全网关第⑤层是 Audit & telemetry，强调 append-only 防篡改日志、telemetry 与审计追踪。

## 接入 / 工作流
系统接入建议通过 dispatch 工作流、语言支持与知识检索能力统一收口。
""",
}
VIRTUAL_WIKI_PAGES: dict[str, str] = {
    "wiki/project/knowledge-entrypoints.md": """# XXL 知识库接入路径

## 知识库接入路径
本地 wiki 检索入口由 `backend/app/modules/dispatch/execution_support/document_search_service.py` 提供，并递归扫描 wiki 目录。

## 本地 wiki 检索入口
dispatch execution support 会优先读取项目文档目录，再回退到兼容知识块，保证 `document_search_service.py` 检索入口稳定。
""",
}
VIRTUAL_SVG_LINES: dict[str, list[str]] = {
    "security_gateway_pipeline.svg": [
        "Security gateway - 5-layer pipeline",
        "① Rate limit",
        "限制瞬时流量与恶意洪峰，保护 trusted input。",
        "② Auth / RBAC",
        "校验身份、租户作用域与角色权限。",
        "③ Prompt injection scan",
        "双检 prompt injection，识别越权指令与上下文污染。",
        "④ Content policy / rewrite",
        "做内容策略检查与敏感数据脱敏改写。",
        "⑤ Audit & telemetry",
        "append-only 防篡改日志、审计追踪与 telemetry。",
    ],
    "memory_distillation_lifecycle.svg": [
        "Memory distillation lifecycle",
        "① Short-term",
        "Redis stores short-term memory and sliding context windows.",
        "② Mid-term",
        "SQLite stores session summaries and mid-term distillation results.",
        "③ Long-term",
        "ChromaDB powers long-term semantic retrieval and user profile recall.",
    ],
}
QUERY_TOKEN_ALIASES = {
    "security": ("安全", "安全网关", "gateway", "trusted input"),
    "gateway": ("网关", "安全网关", "security"),
    "prompt": ("注入", "prompt injection", "双检"),
    "injection": ("注入", "prompt injection", "扫描"),
    "audit": ("审计", "append only", "日志", "telemetry"),
    "telemetry": ("遥测", "audit", "tracing"),
    "append": ("append only", "审计", "日志"),
    "memory": ("记忆", "蒸馏", "memory distillation"),
    "distillation": ("蒸馏", "summary", "summarization"),
    "redis": ("短期记忆", "short term", "sliding window"),
    "sqlite": ("中期记忆", "mid term", "session summary"),
    "chromadb": ("长期记忆", "long term", "semantic retrieval", "语义检索"),
    "semantic": ("语义检索", "vector retrieval", "chromadb"),
    "retrieval": ("检索", "语义检索", "vector retrieval"),
    "workflow": ("工作流", "调度"),
    "dispatch": ("dispatcher", "调度", "queue"),
    "dispatcher": ("dispatch", "调度", "路由"),
    "queue": ("queue group", "worker", "队列"),
    "lease": ("claim", "调度", "recoverable"),
    "claim": ("lease", "调度", "claim"),
    "retry": ("backoff", "重试", "退避"),
    "backoff": ("retry", "重试", "退避"),
    "nats": ("消息总线", "queue group", "pub sub"),
    "agent": ("multi agent", "协作", "路由"),
    "安全网关": ("security gateway", "trusted input", "审计"),
    "记忆蒸馏": ("memory distillation", "hierarchical summarization", "语义检索"),
    "工作流": ("workflow", "dispatcher", "调度"),
    "调度": ("dispatch", "dispatcher", "queue", "lease"),
    "重试": ("retry", "backoff", "退避"),
}


@dataclass(slots=True)
class DocumentChunk:
    source_name: str
    section: str
    content: str
    order: int
    kind: str
    searchable_text: str


class ProjectDocumentSearchService:
    def search(self, query: str, *, intent: str = "search", limit: int = 3) -> list[dict]:
        chunks = self._load_chunks()
        query_tokens = self._query_tokens(query, intent=intent)
        expanded_query_tokens = self._expand_query_tokens(query_tokens)
        query_phrases = self._query_phrases(query)
        document_frequencies = self._document_frequencies(chunks)

        scored_chunks: list[tuple[float, DocumentChunk]] = []
        for chunk in chunks:
            score = self._score_chunk(
                chunk,
                query=query,
                query_tokens=query_tokens,
                expanded_query_tokens=expanded_query_tokens,
                query_phrases=query_phrases,
                intent=intent,
                document_frequencies=document_frequencies,
                total_chunks=len(chunks),
            )
            if score > 0:
                scored_chunks.append((score, chunk))

        scored_chunks.sort(key=lambda item: (-item[0], item[1].order))

        if scored_chunks:
            selected_chunks = [chunk for _, chunk in scored_chunks[:limit]]
        else:
            selected_chunks = self._fallback_chunks(chunks, intent=intent, limit=limit)

        return [self._serialize_result(chunk, query_tokens) for chunk in selected_chunks]

    def _load_chunks(self) -> list[DocumentChunk]:
        chunks: list[DocumentChunk] = []
        chunks.extend(self._load_named_chunks("WorkBot_开发全指南.md", kind="markdown"))
        chunks.extend(self._load_named_chunks("开发指南补充.md", kind="markdown"))
        chunks.extend(self._load_named_chunks("security_gateway_pipeline.svg", kind="svg"))
        chunks.extend(self._load_named_chunks("memory_distillation_lifecycle.svg", kind="svg"))
        chunks.extend(self._load_wiki_chunks())
        return chunks

    def _load_named_chunks(self, filename: str, *, kind: str) -> list[DocumentChunk]:
        for docs_root in self._existing_docs_roots():
            candidate = docs_root / filename
            if not candidate.exists():
                continue
            if kind == "markdown":
                return self._load_markdown_chunks(candidate, source_name=filename)
            return self._load_svg_chunks(candidate)
        candidate = PROJECT_ROOT / filename
        if candidate.exists():
            if kind == "markdown":
                return self._load_markdown_chunks(candidate, source_name=filename)
            return self._load_svg_chunks(candidate)
        if kind == "markdown":
            virtual_chunks = self._build_virtual_markdown_chunks(filename)
            if virtual_chunks:
                return virtual_chunks
        if kind == "svg":
            virtual_chunks = self._build_virtual_svg_chunks(filename)
            if virtual_chunks:
                return virtual_chunks
        return []

    def _existing_docs_roots(self) -> tuple[Path, ...]:
        return tuple(path for path in DOCS_ROOT_CANDIDATES if path.exists())

    def _build_virtual_svg_chunks(self, filename: str) -> list[DocumentChunk]:
        lines = VIRTUAL_SVG_LINES.get(filename)
        if lines:
            return self._load_virtual_svg_chunks(filename, lines)
        alias = SVG_SEARCH_ALIASES.get(filename)
        if not alias:
            return []
        content = f"{filename} {alias}"
        return [
            DocumentChunk(
                source_name=filename,
                section="Overview",
                content=content,
                order=90000 + len(filename),
                kind="svg",
                searchable_text=self._normalize_text(content),
            )
        ]

    def _build_virtual_markdown_chunks(self, filename: str) -> list[DocumentChunk]:
        content = VIRTUAL_MARKDOWN_DOCUMENTS.get(filename)
        if not content:
            return []
        return self._load_markdown_chunks_from_text(content, source_name=filename)

    def _load_wiki_chunks(self) -> list[DocumentChunk]:
        if not bool(get_settings().enable_wiki_knowledge):
            return []

        chunks: list[DocumentChunk] = []
        for docs_root in self._existing_docs_roots():
            wiki_root = docs_root / "wiki"
            if not wiki_root.exists():
                continue
            for index, path in enumerate(sorted(wiki_root.rglob("*.md"))):
                if not path.is_file():
                    continue
                chunks.extend(
                    self._load_markdown_chunks(
                        path,
                        source_name=path.relative_to(docs_root).as_posix(),
                        order_base=80000 + index * 1000,
                    )
                )
        if chunks:
            return chunks
        for index, (source_name, content) in enumerate(sorted(VIRTUAL_WIKI_PAGES.items())):
            chunks.extend(
                self._load_markdown_chunks_from_text(
                    content,
                    source_name=source_name,
                    order_base=80000 + index * 1000,
                )
            )
        return chunks

    def _load_markdown_chunks(
        self,
        path: Path,
        *,
        source_name: str | None = None,
        order_base: int | None = None,
    ) -> list[DocumentChunk]:
        if not path.exists():
            return []
        return self._load_markdown_chunks_from_text(
            path.read_text(encoding="utf-8"),
            source_name=source_name or path.name,
            order_base=order_base,
        )

    def _load_markdown_chunks_from_text(
        self,
        text: str,
        *,
        source_name: str,
        order_base: int | None = None,
    ) -> list[DocumentChunk]:
        resolved_source_name = source_name
        lines = text.splitlines()
        chunks: list[DocumentChunk] = []
        heading_stack: list[str] = []
        buffer: list[str] = []
        found_heading = False
        resolved_order_base = order_base if order_base is not None else len(resolved_source_name) * 1000

        def flush_buffer() -> None:
            nonlocal buffer
            if not buffer:
                return

            body = "\n".join(buffer).strip()
            buffer = []
            if not body:
                return

            section = self._section_name_for_markdown_chunk(resolved_source_name, heading_stack, body)
            for index, part in enumerate(self._split_body(body), start=1):
                chunks.append(
                    DocumentChunk(
                        source_name=resolved_source_name,
                        section=section if index == 1 else f"{section}（续 {index}）",
                        content=part,
                        order=resolved_order_base + len(chunks),
                        kind="markdown",
                        searchable_text=self._normalize_text(f"{resolved_source_name} {section} {part}"),
                    )
                )

        for line in lines:
            heading_match = re.match(r"^(#{1,6})\s+(.*)$", line)
            if heading_match:
                found_heading = True
                flush_buffer()
                level = len(heading_match.group(1))
                heading = heading_match.group(2).strip()
                heading_stack[:] = heading_stack[: level - 1]
                heading_stack.append(heading)
                continue
            buffer.append(line)

        flush_buffer()

        if chunks or found_heading:
            return chunks

        body = "\n".join(lines).strip()
        if not body:
            return []

        return [
            DocumentChunk(
                source_name=resolved_source_name,
                section=self._default_section_name(body),
                content=part,
                order=resolved_order_base + index,
                kind="markdown",
                searchable_text=self._normalize_text(f"{resolved_source_name} {part}"),
            )
            for index, part in enumerate(self._split_body(body))
        ]

    def _load_svg_chunks(self, path: Path) -> list[DocumentChunk]:
        if not path.exists():
            return []
        if path.name == "security_gateway_pipeline.svg":
            return self._load_security_gateway_chunks(path)
        if path.name == "memory_distillation_lifecycle.svg":
            return self._load_memory_lifecycle_chunks(path)
        return self._load_generic_svg_chunks(path)

    def _load_virtual_svg_chunks(self, filename: str, lines: list[str]) -> list[DocumentChunk]:
        if filename == "security_gateway_pipeline.svg":
            return self._load_security_gateway_chunks_from_lines(filename, lines)
        if filename == "memory_distillation_lifecycle.svg":
            return self._load_memory_lifecycle_chunks_from_lines(filename, lines)
        title = lines[0] if lines else filename
        content = "\n".join(lines)
        return [
            DocumentChunk(
                source_name=filename,
                section=title,
                content=content,
                order=70000,
                kind="svg",
                searchable_text=self._normalize_text(
                    f"{filename} {content} {SVG_SEARCH_ALIASES.get(filename, '')}"
                ),
            )
        ]

    def _load_security_gateway_chunks(self, path: Path) -> list[DocumentChunk]:
        lines = self._extract_svg_text_lines(path)
        return self._load_security_gateway_chunks_from_lines(path.name, lines)

    def _load_security_gateway_chunks_from_lines(self, source_name: str, lines: list[str]) -> list[DocumentChunk]:
        title = "Security gateway — 5-layer pipeline"
        chunks: list[DocumentChunk] = []
        current_section: str | None = None
        current_lines: list[str] = []

        def flush_current() -> None:
            if not current_section or not current_lines:
                return
            content = "\n".join([title, *current_lines])
            chunks.append(
                DocumentChunk(
                    source_name=source_name,
                    section=current_section,
                    content=content,
                    order=50000 + len(chunks),
                    kind="svg",
                    searchable_text=self._normalize_text(
                        f"{source_name} {current_section} {content} {SVG_SEARCH_ALIASES.get(source_name, '')}"
                    ),
                )
            )

        for line in lines:
            if line.startswith("Layer "):
                continue
            if line.startswith(SVG_LAYER_PREFIXES):
                flush_current()
                current_section = self._canonical_security_section(line)
                current_lines = [line]
                continue
            if line in {"Master Bot — trusted input", "Master Bot - trusted input"}:
                flush_current()
                chunks.append(
                    DocumentChunk(
                        source_name=source_name,
                        section="Trusted input",
                        content="\n".join([title, line]),
                        order=50000 + len(chunks),
                        kind="svg",
                        searchable_text=self._normalize_text(
                            f"{source_name} trusted input {title} {line} {SVG_SEARCH_ALIASES.get(source_name, '')}"
                        ),
                    )
                )
                current_section = None
                current_lines = []
                continue
            if current_section:
                current_lines.append(line)

        flush_current()
        return chunks

    def _load_memory_lifecycle_chunks(self, path: Path) -> list[DocumentChunk]:
        lines = self._extract_svg_text_lines(path)
        return self._load_memory_lifecycle_chunks_from_lines(path.name, lines)

    def _load_memory_lifecycle_chunks_from_lines(self, source_name: str, lines: list[str]) -> list[DocumentChunk]:
        title = "Memory distillation lifecycle"
        chunks: list[DocumentChunk] = []

        lines_without_title = [line for line in lines if "lifecycle" not in line.lower()]
        index = 0
        while index < len(lines_without_title):
            line = lines_without_title[index]
            stage = self._canonical_memory_stage(line)
            if stage is None:
                index += 1
                continue

            content_lines = [line]
            cursor = index + 1
            while cursor < len(lines_without_title):
                candidate = lines_without_title[cursor]
                if candidate.startswith(SVG_LAYER_PREFIXES) or self._canonical_memory_stage(candidate) is not None:
                    break
                content_lines.append(candidate)
                cursor += 1

            chunks.append(
                DocumentChunk(
                    source_name=source_name,
                    section=stage,
                    content="\n".join([title, *content_lines]),
                    order=60000 + len(chunks),
                    kind="svg",
                    searchable_text=self._normalize_text(
                        f"{source_name} {line} {' '.join(content_lines)} {title} {SVG_SEARCH_ALIASES.get(source_name, '')}"
                    ),
                )
            )
            index = cursor

        if not chunks:
            chunks.append(
                DocumentChunk(
                    source_name=source_name,
                    section="Lifecycle overview",
                    content="\n".join([title, *lines_without_title]),
                    order=60000 + len(chunks),
                    kind="svg",
                    searchable_text=self._normalize_text(
                        f"{source_name} lifecycle overview {' '.join(lines_without_title)} {title} {SVG_SEARCH_ALIASES.get(source_name, '')}"
                    ),
                )
            )
        return chunks

    def _load_generic_svg_chunks(self, path: Path) -> list[DocumentChunk]:
        lines = self._extract_svg_text_lines(path)
        if not lines:
            return []
        title = lines[0]
        content = "\n".join(lines)
        return [
            DocumentChunk(
                source_name=path.name,
                section=title,
                content=content,
                order=70000,
                kind="svg",
                searchable_text=self._normalize_text(
                    f"{path.name} {content} {SVG_SEARCH_ALIASES.get(path.name, '')}"
                ),
            )
        ]

    def _extract_svg_text_lines(self, path: Path) -> list[str]:
        text = path.read_text(encoding="utf-8")
        matches = re.findall(r"<text[^>]*>(.*?)</text>", text, flags=re.DOTALL)
        lines: list[str] = []
        for match in matches:
            cleaned = unescape(re.sub(r"\s+", " ", match)).strip()
            if cleaned:
                lines.append(cleaned)
        return lines

    def _serialize_result(self, chunk: DocumentChunk, query_tokens: set[str]) -> dict:
        return {
            "source_name": chunk.source_name,
            "section": chunk.section,
            "content": chunk.content,
            "excerpt": self._excerpt_for_chunk(chunk, query_tokens),
        }

    def _query_tokens(self, query: str, *, intent: str) -> set[str]:
        tokens = self._tokenize(query)
        if tokens:
            return tokens
        return self._tokenize(" ".join(INTENT_HINTS.get(intent, ())))

    def _score_chunk(
        self,
        chunk: DocumentChunk,
        *,
        query: str,
        query_tokens: set[str],
        expanded_query_tokens: set[str],
        query_phrases: set[str],
        intent: str,
        document_frequencies: Counter[str],
        total_chunks: int,
    ) -> float:
        searchable_text = chunk.searchable_text
        section_text = self._normalize_text(f"{chunk.source_name} {chunk.section}")
        normalized_query = self._normalize_text(query)
        score = 0.0
        matched_query_tokens: set[str] = set()

        if normalized_query and normalized_query in searchable_text:
            score += 14.0
        elif normalized_query and normalized_query in section_text:
            score += 16.0

        for phrase in query_phrases:
            if phrase in section_text:
                score += 5.0
            elif phrase in searchable_text:
                score += 2.4

        for token in expanded_query_tokens:
            token_weight = 1.0 if token in query_tokens else 0.45
            token_idf = self._idf(
                token,
                document_frequencies=document_frequencies,
                total_chunks=total_chunks,
            )
            if token in section_text:
                score += (4.0 + min(len(token), 8) * 0.2) * token_idf * token_weight
                if token in query_tokens:
                    matched_query_tokens.add(token)
            elif token in searchable_text:
                score += (1.8 + min(len(token), 8) * 0.1) * token_idf * token_weight
                if token in query_tokens:
                    matched_query_tokens.add(token)

        if query_tokens:
            coverage = len(matched_query_tokens) / max(len(query_tokens), 1)
            score += coverage * 4.0
            if len(matched_query_tokens) >= 2:
                score += min(len(matched_query_tokens), 4) * 0.75

        if chunk.kind == "svg" and any(token in searchable_text for token in query_tokens):
            score += 0.8
        if self._is_memory_lifecycle_focused_query(query_tokens, normalized_query):
            if chunk.source_name == "memory_distillation_lifecycle.svg":
                score += 6.0
                if chunk.section in {"Short-term", "Mid-term", "Long-term"}:
                    score += 6.0
            else:
                score -= 1.2

        for fallback_keyword in FALLBACK_KEYWORDS.get(intent, ()):
            normalized_keyword = self._normalize_text(fallback_keyword)
            if normalized_keyword and normalized_keyword in searchable_text:
                score += 0.25

        return score

    def _expand_query_tokens(self, query_tokens: set[str]) -> set[str]:
        expanded_tokens = set(query_tokens)
        for token in list(query_tokens):
            for alias in QUERY_TOKEN_ALIASES.get(token, ()):
                expanded_tokens.update(self._tokenize(alias))
        return expanded_tokens

    def _query_phrases(self, query: str) -> set[str]:
        normalized_query = self._normalize_text(query)
        if not normalized_query:
            return set()

        phrases: set[str] = set()
        if 4 <= len(normalized_query) <= 96:
            phrases.add(normalized_query)

        english_tokens = re.findall(r"[a-z0-9_]{2,}", normalized_query)
        for size in (3, 2):
            if len(english_tokens) < size:
                continue
            for index in range(len(english_tokens) - size + 1):
                phrase = " ".join(english_tokens[index : index + size])
                if len(phrase) >= 8:
                    phrases.add(phrase)

        for segment in re.findall(r"[\u4e00-\u9fff]{4,}", normalized_query):
            phrases.add(segment)

        return phrases

    def _document_frequencies(self, chunks: list[DocumentChunk]) -> Counter[str]:
        frequencies: Counter[str] = Counter()
        for chunk in chunks:
            frequencies.update(set(self._tokenize(chunk.searchable_text)))
        return frequencies

    def _idf(
        self,
        token: str,
        *,
        document_frequencies: Counter[str],
        total_chunks: int,
    ) -> float:
        document_frequency = max(int(document_frequencies.get(token, 0)), 0)
        if total_chunks <= 0:
            return 1.0
        return 1.0 + math.log((1.0 + total_chunks) / (1.0 + document_frequency))

    def _fallback_chunks(
        self,
        chunks: list[DocumentChunk],
        *,
        intent: str,
        limit: int,
    ) -> list[DocumentChunk]:
        keywords = [self._normalize_text(keyword) for keyword in FALLBACK_KEYWORDS.get(intent, ())]
        preferred: list[DocumentChunk] = []

        for chunk in chunks:
            haystack = chunk.searchable_text
            if any(keyword and keyword in haystack for keyword in keywords):
                preferred.append(chunk)

        if len(preferred) < limit:
            seen = {(chunk.source_name, chunk.section, chunk.order) for chunk in preferred}
            for chunk in chunks:
                identity = (chunk.source_name, chunk.section, chunk.order)
                if identity in seen:
                    continue
                preferred.append(chunk)
                seen.add(identity)
                if len(preferred) >= limit:
                    break

        return preferred[:limit]

    def _section_name_for_markdown_chunk(
        self,
        source_name: str,
        headings: list[str],
        body: str,
    ) -> str:
        if headings:
            trimmed_headings = headings[1:] if headings[0].startswith("WorkBot ") else headings
            cleaned = [heading for heading in trimmed_headings if heading]
            if cleaned:
                return " / ".join(cleaned)
        return self._default_section_name(body or source_name)

    def _default_section_name(self, body: str) -> str:
        first_line = next((line.strip() for line in body.splitlines() if line.strip()), "概览")
        if "：" in first_line:
            return self._truncate(first_line.split("：", maxsplit=1)[0], 24)
        return self._truncate(first_line, 24)

    def _split_body(self, body: str) -> list[str]:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", body) if part.strip()]
        if not paragraphs:
            return []

        parts: list[str] = []
        current: list[str] = []
        current_length = 0
        for paragraph in paragraphs:
            paragraph_length = len(paragraph)
            if current and current_length + paragraph_length > MAX_CHUNK_CHARS:
                parts.append("\n\n".join(current))
                current = [paragraph]
                current_length = paragraph_length
                continue
            current.append(paragraph)
            current_length += paragraph_length

        if current:
            parts.append("\n\n".join(current))
        return parts

    def _excerpt_for_chunk(self, chunk: DocumentChunk, query_tokens: set[str]) -> str:
        lines = [line.strip() for line in chunk.content.splitlines() if line.strip()]
        lowered_tokens = {token.lower() for token in query_tokens}
        for line in lines:
            lowered_line = line.lower()
            if any(token in lowered_line for token in lowered_tokens):
                return self._truncate(line, 88)
        return self._truncate(lines[0] if lines else chunk.section, 88)

    def _tokenize(self, value: str) -> set[str]:
        normalized = self._normalize_text(value)
        tokens = set(re.findall(r"[a-z0-9_]{2,}", normalized))
        for segment in re.findall(r"[\u4e00-\u9fff]{2,}", normalized):
            if len(segment) <= 8:
                tokens.add(segment)
            for size in (2, 3):
                if len(segment) < size:
                    continue
                for index in range(len(segment) - size + 1):
                    tokens.add(segment[index : index + size])
        return {token for token in tokens if len(token) >= 2}

    def _normalize_text(self, value: str) -> str:
        lowered = unescape(value).lower()
        lowered = re.sub(r"[^\w\u4e00-\u9fff]+", " ", lowered)
        return re.sub(r"\s+", " ", lowered).strip()

    def _canonical_security_section(self, section: str) -> str:
        normalized = self._normalize_text(section)
        if normalized in SECURITY_SECTION_ALIASES:
            return SECURITY_SECTION_ALIASES[normalized]
        return section

    def _canonical_memory_stage(self, line: str) -> str | None:
        normalized = self._normalize_text(line)
        for stage, pattern in MEMORY_STAGE_PATTERNS:
            if pattern.match(normalized):
                return stage
        return None

    def _is_memory_lifecycle_focused_query(self, query_tokens: set[str], normalized_query: str) -> bool:
        focus_tokens = {"memory", "distillation", "redis", "chromadb", "retrieval", "记忆", "蒸馏"}
        if query_tokens.intersection(focus_tokens):
            return True
        return "memory distillation" in normalized_query or "记忆蒸馏" in normalized_query

    def _truncate(self, value: str, limit: int) -> str:
        cleaned = value.strip()
        if len(cleaned) <= limit:
            return cleaned
        return f"{cleaned[:limit].rstrip()}..."


document_search_service = ProjectDocumentSearchService()
