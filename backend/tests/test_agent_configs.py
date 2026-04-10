from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from app.services import agent_service
from app.services.agent_config_service import AgentConfigService
from app.services.persistence_service import StatePersistenceService
from app.services.store import InMemoryStore, store


def _replace_global_store(seeded_store: InMemoryStore) -> None:
    store.__dict__.clear()
    store.__dict__.update(store.clone(seeded_store.__dict__))


def _sqlite_service(tmp_path: Path, seeded_store: InMemoryStore) -> StatePersistenceService:
    database_path = tmp_path / "agent-configs.db"
    _replace_global_store(seeded_store)
    service = StatePersistenceService(
        runtime_store=store,
        database_url=f"sqlite:///{database_path}",
    )
    assert service.initialize() is True
    return service


def _write_agent_config_tree(root: Path, agent_dir: str) -> None:
    directory = root / agent_dir
    examples_dir = directory / "examples"
    examples_dir.mkdir(parents=True, exist_ok=True)

    (directory / "agent.md").write_text(
        """---
agent_id: "search-agent"
version: "1.0.0"
name: "搜索助理"
model: "gpt-4.1-mini"
capabilities:
  - web_search
  - fact_checking
trigger_intents:
  - search
  - lookup
execution:
  max_iterations: 4
  timeout_seconds: 45
---
负责搜索和资料整理。
""",
        encoding="utf-8",
    )
    (directory / "soul.md").write_text(
        """---
agent_id: "search-agent"
persona_name: "探索者"
personality:
  tone: professional_friendly
  language_style: concise
system_prompt: |
  你是搜索助理，优先验证来源。
---
保持结构化和可追溯。
""",
        encoding="utf-8",
    )
    (directory / "tools.yaml").write_text(
        """tools:
  - name: web_search
    provider: tavily
    timeout: 10
  - name: url_fetcher
    max_content_length: 50000
""",
        encoding="utf-8",
    )
    (directory / "memory_rules.md").write_text(
        """# Memory Rules

- 记住用户常用检索偏好
- 不保留敏感原文
""",
        encoding="utf-8",
    )
    (examples_dir / "good.md").write_text(
        """---
label: good
---
用户问最新政策时，先说明检索时间并给出来源。
""",
        encoding="utf-8",
    )
    (examples_dir / "bad.md").write_text(
        """---
label: bad
---
不要在没有来源时编造答案。
""",
        encoding="utf-8",
    )


def test_reload_agent_loads_config_snapshot_and_persists_to_database(
    tmp_path: Path,
    monkeypatch,
) -> None:
    seeded_store = InMemoryStore()
    seeded_store.agents = [
        {
            "id": "search_agent",
            "name": "搜索 Agent",
            "description": "在知识库中搜索相关文档和信息",
            "type": "search",
            "status": "running",
            "enabled": True,
            "tasks_completed": 100,
            "tasks_total": 120,
            "avg_response_time": "66ms",
            "tokens_used": 2048,
            "tokens_limit": 4096,
            "success_rate": 98.0,
            "last_active": "刚刚",
        }
    ]

    config_root = tmp_path / "agents"
    _write_agent_config_tree(config_root, "search_agent")
    service = _sqlite_service(tmp_path, seeded_store)
    original_persistence_service = agent_service.persistence_service
    original_agent_config_service = agent_service.agent_config_service
    monkeypatch.setattr(agent_service, "persistence_service", service)
    monkeypatch.setattr(agent_service, "agent_config_service", AgentConfigService(config_root=config_root))

    try:
        payload = agent_service.reload_agent("search_agent")
        listed = agent_service.list_agents()
        fetched = agent_service.get_agent("search_agent")
        persisted = service.get_agent("search_agent")
    finally:
        monkeypatch.setattr(agent_service, "persistence_service", original_persistence_service)
        monkeypatch.setattr(agent_service, "agent_config_service", original_agent_config_service)
        service.close()

    assert payload["ok"] is True
    assert payload["agent"]["status"] == "idle"
    assert payload["agent"]["config_snapshot"]["status"] == "loaded"
    assert payload["agent"]["config_snapshot"]["agent"]["model"] == "gpt-4.1-mini"
    assert payload["agent"]["config_summary"]["tools_count"] == 2
    assert payload["agent"]["config_summary"]["examples_count"] == 2
    assert payload["agent"]["config_summary"]["memory_rules_present"] is True
    assert listed["items"][0]["config_summary"]["status"] == "loaded"
    assert "config_snapshot" not in listed["items"][0]
    assert fetched["config_snapshot"]["examples"][0]["name"] == "bad"
    assert persisted is not None
    assert persisted["config_snapshot"]["tools"]["tools"][0]["name"] == "web_search"
    assert persisted["config_summary"]["files_loaded"] == [
        "agent.md",
        "soul.md",
        "tools.yaml",
        "memory_rules.md",
        "examples/",
    ]


def test_reload_agent_missing_config_is_fail_soft_and_persists_missing_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    seeded_store = InMemoryStore()
    seeded_store.agents = [
        {
            "id": "write_agent",
            "name": "写作 Agent",
            "description": "生成高质量的文本内容和回复",
            "type": "write",
            "status": "running",
            "enabled": True,
            "tasks_completed": 10,
            "tasks_total": 12,
            "avg_response_time": "120ms",
            "tokens_used": 512,
            "tokens_limit": 2048,
            "success_rate": 99.0,
            "last_active": "刚刚",
        }
    ]

    config_root = tmp_path / "agents"
    config_root.mkdir(parents=True, exist_ok=True)
    service = _sqlite_service(tmp_path, seeded_store)
    original_persistence_service = agent_service.persistence_service
    original_agent_config_service = agent_service.agent_config_service
    monkeypatch.setattr(agent_service, "persistence_service", service)
    monkeypatch.setattr(agent_service, "agent_config_service", AgentConfigService(config_root=config_root))

    try:
        payload = agent_service.reload_agent("write_agent")
        persisted = service.get_agent("write_agent")
    finally:
        monkeypatch.setattr(agent_service, "persistence_service", original_persistence_service)
        monkeypatch.setattr(agent_service, "agent_config_service", original_agent_config_service)
        service.close()

    assert payload["ok"] is True
    assert payload["agent"]["status"] == "idle"
    assert payload["agent"]["config_snapshot"]["status"] == "missing"
    assert payload["agent"]["config_summary"]["status"] == "missing"
    assert payload["agent"]["config_summary"]["tools_count"] == 0
    assert persisted is not None
    assert persisted["config_snapshot"]["warnings"] == ["未找到 Agent 配置目录。"]
    assert persisted["config_summary"]["examples_count"] == 0
