from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
import logging
import re
from typing import Any

import yaml

from app.config import get_settings


logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
INTENT_CAPABILITY_HINTS: dict[str, set[str]] = {
    "search": {"search", "lookup", "web_search", "document_retrieval", "research", "fact_checking"},
    "write": {"write", "draft", "drafting", "rewriting", "summarization", "translation"},
    "help": {"help", "summarization", "translation", "response_formatting", "localization"},
}
AGENT_TYPE_INTENT_COMPAT: dict[str, set[str]] = {
    "search": {"search"},
    "write": {"write", "help"},
    "output": {"help"},
}


def build_agent_config_summary(config_snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    if config_snapshot is None:
        return None

    tools_payload = config_snapshot.get("tools")
    if isinstance(tools_payload, dict) and isinstance(tools_payload.get("tools"), list):
        tools_count = len(tools_payload["tools"])
    elif isinstance(tools_payload, list):
        tools_count = len(tools_payload)
    elif isinstance(tools_payload, dict):
        tools_count = len(tools_payload)
    else:
        tools_count = 0

    return {
        "status": str(config_snapshot.get("status") or "missing"),
        "directory": config_snapshot.get("directory"),
        "version": config_snapshot.get("version"),
        "files_loaded": list(config_snapshot.get("files_loaded") or []),
        "tools_count": tools_count,
        "examples_count": len(config_snapshot.get("examples") or []),
        "memory_rules_present": config_snapshot.get("memory_rules") is not None,
        "soul_present": config_snapshot.get("soul") is not None,
        "warnings": list(config_snapshot.get("warnings") or []),
    }


class AgentConfigService:
    def __init__(self, *, config_root: str | Path | None = None) -> None:
        self._config_root_override = Path(config_root) if config_root is not None else None

    def resolve_agent_directory_path(self, agent: dict[str, Any]) -> Path | None:
        return self._resolve_agent_directory(agent)

    def resolve_config_root_path(self) -> Path:
        return self._resolve_config_root()

    def load_agent_config(self, agent: dict[str, Any]) -> dict[str, Any]:
        normalized_agent = deepcopy(agent)
        agent_id = str(normalized_agent.get("id") or "").strip()
        directory = self._resolve_agent_directory(normalized_agent)
        warnings: list[str] = []

        if directory is None:
            return {
                "agent_id": agent_id,
                "status": "missing",
                "directory": None,
                "version": None,
                "loaded_at": self._now_iso(),
                "files_loaded": [],
                "warnings": ["未找到 Agent 配置目录。"],
                "agent": None,
                "soul": None,
                "tools": None,
                "memory_rules": None,
                "examples": [],
            }

        files_loaded: list[str] = []
        agent_doc, agent_path = self._load_primary_agent_doc(directory)
        if agent_doc is None:
            warnings.append("缺少 agent.md 或 agents.md。")
        else:
            files_loaded.append(agent_path.name)

        soul_doc = self._load_markdown_doc(directory / "soul.md")
        if soul_doc is not None:
            files_loaded.append("soul.md")
        else:
            warnings.append("缺少 soul.md。")

        tools_doc = self._load_yaml_doc(directory / "tools.yaml", warnings)
        if tools_doc is not None:
            files_loaded.append("tools.yaml")
        else:
            warnings.append("缺少 tools.yaml。")

        memory_rules_doc = self._load_markdown_doc(directory / "memory_rules.md")
        if memory_rules_doc is not None:
            files_loaded.append("memory_rules.md")
        else:
            warnings.append("缺少 memory_rules.md。")

        examples = self._load_examples(directory / "examples", warnings)
        if examples:
            files_loaded.append("examples/")
        else:
            warnings.append("缺少 few-shot examples。")

        if not files_loaded:
            status = "missing"
        elif warnings:
            status = "partial"
        else:
            status = "loaded"

        version = None
        if agent_doc is not None:
            version = str(agent_doc.get("version") or "").strip() or None

        return {
            "agent_id": agent_id,
            "status": status,
            "directory": self._relative_path(directory),
            "version": version,
            "loaded_at": self._now_iso(),
            "files_loaded": files_loaded,
            "warnings": warnings,
            "agent": agent_doc,
            "soul": soul_doc,
            "tools": tools_doc,
            "memory_rules": memory_rules_doc,
            "examples": examples,
        }

    def evaluate_agent_intent_support(
        self,
        agent: dict[str, Any] | None,
        intent: str | None,
    ) -> dict[str, Any]:
        normalized_intent = self._normalize_intent(intent)
        if not isinstance(agent, dict):
            return {
                "supported": False if normalized_intent else None,
                "intent": normalized_intent,
                "source": "missing",
                "reason": "missing agent payload",
                "config_status": "missing",
                "supported_intents": [],
                "capabilities": [],
                "warnings": ["missing agent payload"],
            }

        if normalized_intent is None:
            return {
                "supported": None,
                "intent": None,
                "source": "none",
                "reason": "intent is not routable",
                "config_status": str((agent.get("config_snapshot") or {}).get("status") or "unknown"),
                "supported_intents": [],
                "capabilities": [],
                "warnings": [],
            }

        snapshot, load_warning = self._ensure_agent_snapshot(agent)
        warnings: list[str] = []
        if load_warning:
            warnings.append(load_warning)
        config_status = str((snapshot or {}).get("status") or "missing")

        agent_doc = (snapshot or {}).get("agent")
        if not isinstance(agent_doc, dict):
            agent_doc = {}

        supported_intents = self._normalize_text_list(agent_doc.get("trigger_intents"))
        capabilities = self._normalize_text_list(agent_doc.get("capabilities"))
        agent_type = str(agent.get("type") or "").strip().lower()

        if normalized_intent in supported_intents:
            return {
                "supported": True,
                "intent": normalized_intent,
                "source": "explicit_intent",
                "reason": f'intent "{normalized_intent}" declared in trigger_intents',
                "config_status": config_status,
                "supported_intents": supported_intents,
                "capabilities": capabilities,
                "warnings": warnings,
            }

        if set(capabilities) & INTENT_CAPABILITY_HINTS.get(normalized_intent, set()):
            return {
                "supported": True,
                "intent": normalized_intent,
                "source": "capability_hint",
                "reason": f'intent "{normalized_intent}" inferred from capabilities',
                "config_status": config_status,
                "supported_intents": supported_intents,
                "capabilities": capabilities,
                "warnings": warnings,
            }

        if normalized_intent in AGENT_TYPE_INTENT_COMPAT.get(agent_type, set()):
            return {
                "supported": True,
                "intent": normalized_intent,
                "source": "agent_type_fallback",
                "reason": f'agent type "{agent_type}" allows intent "{normalized_intent}"',
                "config_status": config_status,
                "supported_intents": supported_intents,
                "capabilities": capabilities,
                "warnings": warnings,
            }

        if config_status == "missing":
            reason = (
                f'agent config missing and agent type "{agent_type or "unknown"}" '
                f'does not allow intent "{normalized_intent}"'
            )
        else:
            reason = (
                f'intent "{normalized_intent}" is not declared in trigger_intents/capabilities '
                f'for agent type "{agent_type or "unknown"}"'
            )

        return {
            "supported": False,
            "intent": normalized_intent,
            "source": "unsupported",
            "reason": reason,
            "config_status": config_status,
            "supported_intents": supported_intents,
            "capabilities": capabilities,
            "warnings": warnings,
        }

    def _load_primary_agent_doc(
        self,
        directory: Path,
    ) -> tuple[dict[str, Any] | None, Path | None]:
        preferred_paths = [directory / "agent.md", directory / "agents.md"]
        for path in preferred_paths:
            document = self._load_markdown_doc(path)
            if document is not None:
                return document, path
        return None, None

    def _load_markdown_doc(self, path: Path) -> dict[str, Any] | None:
        if not path.exists() or not path.is_file():
            return None

        raw = path.read_text(encoding="utf-8")
        metadata, content = self._split_front_matter(raw)
        payload: dict[str, Any] = {
            "path": self._relative_path(path),
            "content": content,
        }
        if isinstance(metadata, dict):
            payload.update(metadata)
        elif metadata is not None:
            payload["metadata"] = metadata
        return payload

    def _load_yaml_doc(
        self,
        path: Path,
        warnings: list[str],
    ) -> dict[str, Any] | list[Any] | None:
        if not path.exists() or not path.is_file():
            return None

        try:
            parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            logger.warning("Failed to parse agent tools config %s: %s", path, exc)
            warnings.append(f"tools.yaml 解析失败：{exc}")
            return None
        if parsed is None:
            return {"path": self._relative_path(path), "tools": []}
        if isinstance(parsed, dict):
            payload = deepcopy(parsed)
            payload["path"] = self._relative_path(path)
            return payload
        return parsed

    def _load_examples(self, directory: Path, warnings: list[str]) -> list[dict[str, Any]]:
        if not directory.exists() or not directory.is_dir():
            return []

        examples: list[dict[str, Any]] = []
        parse_failed = False
        for path in sorted(directory.glob("*.md")):
            try:
                raw = path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("Failed to read agent example %s: %s", path, exc)
                parse_failed = True
                continue
            metadata, content = self._split_front_matter(raw)
            example: dict[str, Any] = {
                "name": path.stem,
                "path": self._relative_path(path),
                "content": content,
            }
            if isinstance(metadata, dict):
                example.update(metadata)
            elif metadata is not None:
                example["metadata"] = metadata
            examples.append(example)

        if parse_failed:
            warnings.append("部分 few-shot examples 读取失败。")
        return examples

    def _resolve_agent_directory(self, agent: dict[str, Any]) -> Path | None:
        config_root = self._resolve_config_root()
        if not config_root.exists() or not config_root.is_dir():
            return None

        for candidate in self._candidate_directory_names(agent):
            directory = config_root / candidate
            if directory.exists() and directory.is_dir():
                return directory
        return None

    def _resolve_config_root(self) -> Path:
        if self._config_root_override is not None:
            return self._config_root_override

        raw_root = str(get_settings().agent_config_root or "agents").strip()
        path = Path(raw_root)
        if path.is_absolute():
            return path
        return PROJECT_ROOT / path

    def _candidate_directory_names(self, agent: dict[str, Any]) -> list[str]:
        candidates: list[str] = []
        for value in (
            agent.get("id"),
            agent.get("type"),
            f"{agent.get('type')}_agent" if agent.get("type") else None,
            self._slugify(agent.get("name")),
            self._slugify(agent.get("description")),
        ):
            normalized = str(value or "").strip().lower()
            if normalized and normalized not in candidates:
                candidates.append(normalized)
        return candidates

    def _ensure_agent_snapshot(self, agent: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
        snapshot = agent.get("config_snapshot")
        if isinstance(snapshot, dict):
            return snapshot, None

        try:
            loaded = self.load_agent_config(agent)
        except Exception as exc:  # pragma: no cover - defensive fail-open path
            return None, f"agent config load failed: {exc}"

        if isinstance(loaded, dict):
            agent["config_snapshot"] = loaded
            agent["config_summary"] = build_agent_config_summary(loaded)
            return loaded, None
        return None, "agent config load returned invalid payload"

    @staticmethod
    def _normalize_intent(value: Any) -> str | None:
        normalized = str(value or "").strip().lower()
        if normalized in {"search", "write", "help"}:
            return normalized
        return None

    @staticmethod
    def _normalize_text_list(values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        normalized: list[str] = []
        for value in values:
            item = str(value or "").strip().lower()
            if item and item not in normalized:
                normalized.append(item)
        return normalized

    @staticmethod
    def _slugify(value: Any) -> str:
        text = str(value or "").strip().lower()
        text = re.sub(r"[^a-z0-9]+", "_", text)
        return text.strip("_")

    @staticmethod
    def _split_front_matter(raw: str) -> tuple[dict[str, Any] | Any | None, str]:
        if not raw.startswith("---"):
            return None, raw.strip()

        lines = raw.splitlines()
        if not lines or lines[0].strip() != "---":
            return None, raw.strip()

        closing_index = None
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                closing_index = index
                break

        if closing_index is None:
            return None, raw.strip()

        metadata_block = "\n".join(lines[1:closing_index]).strip()
        content = "\n".join(lines[closing_index + 1 :]).strip()
        if not metadata_block:
            return {}, content
        parsed = yaml.safe_load(metadata_block)
        return parsed, content

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _relative_path(path: Path) -> str:
        try:
            return path.relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            return path.as_posix()


agent_config_service = AgentConfigService()
