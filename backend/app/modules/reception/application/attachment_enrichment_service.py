from __future__ import annotations

from copy import deepcopy
import base64
from io import BytesIO
import ipaddress
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse
import xml.etree.ElementTree as ET
import zipfile

import httpx

from app.platform.config.settings_service import get_agent_api_runtime_settings


_TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".csv",
    ".json",
    ".yaml",
    ".yml",
    ".log",
}
_DOCX_EXTENSIONS = {".docx"}
_IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".bmp",
}
_MIME_TO_EXTENSION = {
    "text/plain": ".txt",
    "text/markdown": ".md",
    "application/json": ".json",
    "text/csv": ".csv",
    "application/x-yaml": ".yaml",
    "application/yaml": ".yaml",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
}
_EXCERPT_FIELDS = (
    "transcript",
    "ocr_text",
    "ocrText",
    "excerpt",
    "summary",
    "content",
    "text_content",
    "textContent",
    "description",
)
_MAX_DOWNLOAD_BYTES = 512 * 1024
_MAX_IMAGE_DOWNLOAD_BYTES = 2 * 1024 * 1024
_MAX_EXCERPT_CHARS = 360
_MAX_OCR_TEXT_CHARS = 1200
_BLOCKED_ATTACHMENT_HOSTS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "host.docker.internal",
}
_WORD_NAMESPACE = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
_OCR_PROVIDER_SELECTION_ORDER = ("openai", "gemini", "openapi", "codex", "kimi", "deepseek")
_OCR_SUPPORTED_ENDPOINT_SUFFIXES = ("/responses", "/chat/completions")
_OCR_EMPTY_RESPONSES = {
    "",
    "none",
    "no text",
    "no visible text",
    "未识别到文字",
    "未识别到明显文字",
    "图片中无可辨认文字",
    "图片中没有可辨认文字",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _excerpt_already_present(item: dict[str, Any]) -> bool:
    for field in _EXCERPT_FIELDS:
        if _text(item.get(field)):
            return True
    return False


def _is_safe_public_url(url: str) -> bool:
    normalized = _text(url)
    if not normalized:
        return False
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"}:
        return False
    hostname = _text(parsed.hostname).lower()
    if not hostname or hostname in _BLOCKED_ATTACHMENT_HOSTS or hostname.endswith(".local"):
        return False
    try:
        host_ip = ipaddress.ip_address(hostname)
    except ValueError:
        return True
    return not (
        host_ip.is_private
        or host_ip.is_loopback
        or host_ip.is_link_local
        or host_ip.is_multicast
        or host_ip.is_reserved
        or host_ip.is_unspecified
    )


def _infer_extension(item: dict[str, Any]) -> str:
    name = _text(item.get("name") or item.get("title") or item.get("file_name") or item.get("fileName"))
    if name:
        suffix = Path(name).suffix.lower()
        if suffix:
            return suffix
    url = _text(item.get("url") or item.get("download_url") or item.get("downloadUrl"))
    if url:
        suffix = Path(urlparse(url).path).suffix.lower()
        if suffix:
            return suffix
    mime_type = _text(item.get("mime_type") or item.get("mimeType")).lower()
    return _MIME_TO_EXTENSION.get(mime_type, "")


def _download_attachment_bytes(url: str) -> bytes:
    return _download_bytes(url, max_bytes=_MAX_DOWNLOAD_BYTES)


def _download_bytes(url: str, *, max_bytes: int) -> bytes:
    with httpx.Client(timeout=8.0, trust_env=False, follow_redirects=True) as client:
        response = client.get(
            url,
            headers={
                "User-Agent": "WorkBot-Reception/1.0",
                "Accept": "*/*",
            },
        )
        response.raise_for_status()
        content_length = response.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > max_bytes:
                    raise ValueError("attachment too large")
            except ValueError as exc:
                if str(exc) == "attachment too large":
                    raise
        body = response.content
    if len(body) > max_bytes:
        raise ValueError("attachment too large")
    return body


def _decode_text_bytes(raw_bytes: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("utf-8", errors="ignore")


def _extract_docx_text(raw_bytes: bytes) -> str:
    with zipfile.ZipFile(BytesIO(raw_bytes)) as archive:
        xml_bytes = archive.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", _WORD_NAMESPACE):
        texts = [node.text or "" for node in paragraph.findall(".//w:t", _WORD_NAMESPACE)]
        normalized = _collapse_whitespace("".join(texts))
        if normalized:
            paragraphs.append(normalized)
    return "\n".join(paragraphs)


def _extract_plain_text(raw_bytes: bytes, *, extension: str) -> str:
    if extension in _DOCX_EXTENSIONS:
        return _extract_docx_text(raw_bytes)
    return _decode_text_bytes(raw_bytes)


def _build_excerpt(text: str) -> str | None:
    normalized = _collapse_whitespace(text)
    if not normalized:
        return None
    if len(normalized) <= _MAX_EXCERPT_CHARS:
        return normalized
    return normalized[: _MAX_EXCERPT_CHARS - 1].rstrip() + "…"


def _stringify_message_content(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        chunks: list[str] = []
        for item in value:
            if isinstance(item, str):
                if item.strip():
                    chunks.append(item.strip())
                continue
            if isinstance(item, dict):
                text = str(item.get("text") or item.get("content") or "").strip()
                if text:
                    chunks.append(text)
        return "\n".join(chunk for chunk in chunks if chunk).strip()
    if isinstance(value, dict):
        return str(value.get("text") or value.get("content") or "").strip()
    return str(value or "").strip()


def _parse_provider_text(endpoint_path: str, payload: dict[str, Any]) -> str:
    normalized_path = endpoint_path.rstrip("/").lower()
    if normalized_path.endswith("/responses"):
        output_text = _stringify_message_content(payload.get("output_text"))
        if output_text:
            return output_text
        output = payload.get("output")
        if isinstance(output, list):
            chunks: list[str] = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if isinstance(content, list):
                    for content_item in content:
                        if not isinstance(content_item, dict):
                            continue
                        text = _stringify_message_content(
                            content_item.get("text") or content_item.get("content")
                        )
                        if text:
                            chunks.append(text)
            return "\n".join(chunk for chunk in chunks if chunk).strip()
        return ""

    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict):
            return _stringify_message_content(message.get("content"))
        text = choices[0].get("text") if isinstance(choices[0], dict) else None
        return _stringify_message_content(text)
    return ""


def _normalize_ocr_text(value: Any) -> str | None:
    normalized = _collapse_whitespace(_stringify_message_content(value))
    normalized = normalized.strip().strip('"').strip("'").strip()
    if normalized.lower() in _OCR_EMPTY_RESPONSES:
        return None
    if not normalized:
        return None
    if len(normalized) <= _MAX_OCR_TEXT_CHARS:
        return normalized
    return normalized[: _MAX_OCR_TEXT_CHARS - 1].rstrip() + "…"


def _mime_type(item: dict[str, Any]) -> str:
    return _text(item.get("mime_type") or item.get("mimeType")).lower()


def _is_image_attachment(item: dict[str, Any], extension: str) -> bool:
    mime_type = _mime_type(item)
    return extension in _IMAGE_EXTENSIONS or mime_type.startswith("image/")


def _provider_payloads() -> dict[str, Any]:
    runtime_settings = get_agent_api_runtime_settings()
    providers = runtime_settings.get("providers")
    if not isinstance(providers, dict):
        settings = runtime_settings.get("settings")
        if isinstance(settings, dict):
            providers = settings.get("providers")
    return providers if isinstance(providers, dict) else {}


def _resolve_ocr_provider() -> tuple[str, dict[str, Any]] | None:
    providers = _provider_payloads()
    for provider_key in _OCR_PROVIDER_SELECTION_ORDER:
        candidate = providers.get(provider_key)
        if not isinstance(candidate, dict):
            continue
        if not bool(candidate.get("enabled")):
            continue
        if not _text(candidate.get("api_key")):
            continue
        endpoint_path = _text(candidate.get("endpoint_path")).lower()
        if not endpoint_path.endswith(_OCR_SUPPORTED_ENDPOINT_SUFFIXES):
            continue
        if not _text(candidate.get("base_url")) or not _text(candidate.get("model")):
            continue
        return provider_key, candidate
    return None


def _join_url(base_url: str, endpoint_path: str) -> str:
    return f"{base_url.rstrip('/')}/{endpoint_path.lstrip('/')}"


def _provider_headers(provider: dict[str, Any]) -> dict[str, str]:
    headers = {
        "content-type": "application/json",
        "accept": "application/json",
        "authorization": f"Bearer {_text(provider.get('api_key'))}",
    }
    organization_id = _text(provider.get("organization_id"))
    project_id = _text(provider.get("project_id"))
    if organization_id:
        headers["OpenAI-Organization"] = organization_id
    if project_id:
        headers["OpenAI-Project"] = project_id
    return headers


def _image_data_url(raw_bytes: bytes, *, mime_type: str, extension: str) -> str:
    resolved_mime_type = mime_type or {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
    }.get(extension, "image/png")
    encoded = base64.b64encode(raw_bytes).decode("ascii")
    return f"data:{resolved_mime_type};base64,{encoded}"


def _ocr_system_prompt() -> str:
    return (
        "你是接待链路里的图片 OCR 组件。"
        "只提取图片中清晰可见的文字，按阅读顺序输出。"
        "不要总结，不要解释，不要补充推断。"
        "如果图片里没有可辨认文字，返回空字符串。"
    )


def _ocr_user_prompt(item: dict[str, Any]) -> str:
    name = _text(item.get("name") or item.get("title") or item.get("file_name") or item.get("fileName"))
    if name:
        return f"请识别这张客户图片中的可见文字。文件名：{name}"
    return "请识别这张客户图片中的可见文字。"


def _ocr_payload(
    *,
    provider: dict[str, Any],
    endpoint_path: str,
    image_url: str,
    item: dict[str, Any],
) -> dict[str, Any]:
    model_name = _text(provider.get("model"))
    system_prompt = _ocr_system_prompt()
    user_prompt = _ocr_user_prompt(item)
    normalized_path = endpoint_path.rstrip("/").lower()
    if normalized_path.endswith("/responses"):
        return {
            "model": model_name,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": user_prompt},
                        {"type": "input_image", "image_url": image_url},
                    ],
                },
            ],
        }
    return {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            },
        ],
        "temperature": 0,
    }


def _extract_image_ocr_text(item: dict[str, Any], *, extension: str) -> str | None:
    provider_result = _resolve_ocr_provider()
    if provider_result is None:
        raise RuntimeError("no compatible OCR provider configured")
    _, provider = provider_result

    image_url = _text(item.get("url") or item.get("download_url") or item.get("downloadUrl"))
    mime_type = _mime_type(item)
    raw_bytes = _download_bytes(image_url, max_bytes=_MAX_IMAGE_DOWNLOAD_BYTES)
    encoded_image_url = _image_data_url(raw_bytes, mime_type=mime_type, extension=extension)

    base_url = _text(provider.get("base_url"))
    endpoint_path = _text(provider.get("endpoint_path"))
    payload = _ocr_payload(
        provider=provider,
        endpoint_path=endpoint_path,
        image_url=encoded_image_url,
        item=item,
    )
    with httpx.Client(timeout=30.0, trust_env=False) as client:
        response = client.post(
            _join_url(base_url, endpoint_path),
            headers=_provider_headers(provider),
            json=payload,
        )
        response.raise_for_status()
        response_payload = response.json()
    if not isinstance(response_payload, dict):
        return None
    return _normalize_ocr_text(_parse_provider_text(endpoint_path, response_payload))


class AttachmentEnrichmentService:
    def enrich_attachments(self, attachments: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
        enriched = deepcopy(attachments)
        warnings: list[str] = []
        for index, item in enumerate(enriched[:3]):
            if not isinstance(item, dict) or _excerpt_already_present(item):
                continue
            extension = _infer_extension(item)
            url = _text(item.get("url") or item.get("download_url") or item.get("downloadUrl"))
            if not _is_safe_public_url(url):
                continue
            try:
                if extension in _TEXT_EXTENSIONS | _DOCX_EXTENSIONS:
                    raw_bytes = _download_attachment_bytes(url)
                    extracted_text = _extract_plain_text(raw_bytes, extension=extension)
                    excerpt = _build_excerpt(extracted_text)
                    if excerpt:
                        item["excerpt"] = excerpt
                    continue
                if _is_image_attachment(item, extension):
                    ocr_text = _extract_image_ocr_text(item, extension=extension)
                    if ocr_text:
                        item["ocr_text"] = ocr_text
                        excerpt = _build_excerpt(ocr_text)
                        if excerpt:
                            item["excerpt"] = excerpt
            except Exception as exc:
                warnings.append(f"attachment[{index}] enrich failed: {exc}")
        return enriched, warnings


attachment_enrichment_service = AttachmentEnrichmentService()
