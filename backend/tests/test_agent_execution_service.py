from __future__ import annotations

import pytest

from app.services import agent_execution_service as agent_execution_module
from app.services.agent_execution_service import agent_execution_service
from app.services.agent_config_service import AgentConfigService
from app.services.document_search_service import document_search_service


def _stub_search_results(query: str, *, intent: str = "search", limit: int = 3) -> list[dict]:
    hits: list[dict] = []
    for index in range(min(limit, 3)):
        hits.append(
            {
                "source_name": f"doc-{intent}",
                "section": f"Section #{index + 1}",
                "excerpt": f"Excerpt for {query} ({intent})",
                "matched_terms": ["workbot", intent],
            }
        )
    return hits


@pytest.fixture(autouse=True)
def patch_document_search(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(document_search_service, "search", _stub_search_results)


def _build_run(intent: str) -> dict:
    return {"intent": intent}


def _build_task(description: str = "Please help with WorkBot guidance.") -> dict:
    return {
        "id": "task-1",
        "description": description,
        "preferred_language": "en",
        "user_key": "test-user",
        "session_id": "test-session",
    }


def _build_execution_agent(agent_type: str) -> dict:
    return {
        "id": f"{agent_type}-agent",
        "type": agent_type,
        "name": f"{agent_type.title()} Executor",
    }


def _fake_config_service(monkeypatch: pytest.MonkeyPatch, *, status: str | None):
    fake_service = AgentConfigService(config_root="nonexistent")
    monkeypatch.setattr(agent_execution_module, "agent_config_service", fake_service)
    monkeypatch.setattr(
        fake_service,
        "load_agent_config",
        lambda agent: {
            "status": status or "loaded",
            "version": "1.2.0",
            "agent": {
                "model": "gpt-4.1-mini",
                "version": "1.2.0",
                "capabilities": ["web_search", "document_retrieval"],
                "trigger_intents": ["search", "lookup"],
            },
            "tools": {"tools": [{"name": "web_search"}, {"name": "document_retrieval"}]},
        },
    )
    return fake_service


@pytest.mark.parametrize(
    "intent,agent_type,expected_kind,expected_prefix",
    [
        ("search", "search", "search_report", "Search target:"),
        ("write", "write", "draft_message", "Hello,"),
    ],
)
def test_agent_execution_branching(intent: str, agent_type: str, expected_kind: str, expected_prefix: str) -> None:
    task = _build_task(description="Search or write something about deployment.")
    run = _build_run(intent)
    run["dispatch_context"] = {
        "manager_packet": {
            "manager_action": "handoff_to_execution",
            "next_owner": "Search Executor" if intent == "search" else "Write Executor",
            "delivery_mode": "structured_result",
            "decomposition_hint": "direct_execute",
            "workflow_admission": "free_workflow",
        }
    }
    execution_agent = _build_execution_agent(agent_type)

    result = agent_execution_service.execute_task(task=task, run=run, execution_agent=execution_agent)

    assert result["kind"] == expected_kind
    assert result["content"].startswith(expected_prefix)
    assert result["references"][0]["title"].startswith(f"doc-{intent} / Section #1")
    assert len(result["execution_trace"]) >= 5
    stages = {item["stage"] for item in result["execution_trace"]}
    assert {
        "request_analysis",
        "knowledge_retrieval",
        "context_memory_injection",
        "manager_directive",
        "result_rendering",
        "execution_profile",
    }.issubset(stages)


def test_agent_execution_trace_exposes_manager_directive() -> None:
    task = _build_task(description="Please help with WorkBot guidance.")
    run = _build_run("help")
    run["dispatch_context"] = {
        "manager_packet": {
            "manager_action": "handoff_to_execution",
            "next_owner": "Write Executor",
            "delivery_mode": "structured_result",
            "decomposition_hint": "direct_execute",
            "workflow_admission": "free_workflow",
        }
    }
    execution_agent = _build_execution_agent("write")

    result = agent_execution_service.execute_task(task=task, run=run, execution_agent=execution_agent)

    directive = next(item for item in result["execution_trace"] if item["stage"] == "manager_directive")
    assert directive["metadata"]["manager_action"] == "handoff_to_execution"
    assert directive["metadata"]["next_owner"] == "Write Executor"


def test_help_intent_stays_help_note_when_agent_is_write() -> None:
    task = _build_task(description="Help me diagnose the WorkBot dispatcher.")
    run = _build_run("help")
    execution_agent = _build_execution_agent("write")

    result = agent_execution_service.execute_task(task=task, run=run, execution_agent=execution_agent)

    assert result["kind"] == "help_note"
    assert result["content"].lower().startswith("topic:")
    assert "Suggested response" in result["content"]
    assert any(item["stage"] == "execution_profile" for item in result["execution_trace"])


def test_greeting_message_returns_chat_reply() -> None:
    task = _build_task(description="你好")
    task["preferred_language"] = "zh"
    run = _build_run("help")
    execution_agent = _build_execution_agent("write")

    result = agent_execution_service.execute_task(task=task, run=run, execution_agent=execution_agent)

    assert result["kind"] == "chat_reply"
    assert result["text"].startswith("你好，我在。")
    assert result["content"].startswith("你好，我在。")
    assert result["bullets"] == []
    assert result["references"] == []


def test_small_talk_message_returns_natural_chat_reply_without_reference_tone() -> None:
    task = _build_task(description="能和我简单的聊天吗？")
    task["preferred_language"] = "zh"
    run = _build_run("help")
    execution_agent = _build_execution_agent("write")

    result = agent_execution_service.execute_task(task=task, run=run, execution_agent=execution_agent)

    assert result["kind"] == "chat_reply"
    assert "资料线索" not in result["text"]
    assert "继续拆" not in result["text"]
    assert "聊天" in result["text"] or "正常聊" in result["text"]
    assert result["references"] == []


def test_vague_help_message_uses_reception_clarification_tone() -> None:
    task = _build_task(description="我想请你帮我看看一个问题")
    task["preferred_language"] = "zh"
    task["route_decision"] = {"interaction_mode": "chat", "reception_mode": "clarify"}
    run = _build_run("help")
    execution_agent = _build_execution_agent("write")

    result = agent_execution_service.execute_task(task=task, run=run, execution_agent=execution_agent)

    assert result["kind"] == "chat_reply"
    assert "资料线索" not in result["text"]
    assert "最想解决" in result["text"] or "卡点" in result["text"]
    assert result["references"] == []


def test_direct_question_message_uses_question_reception_tone() -> None:
    task = _build_task(description="今天广州天气怎么样")
    task["preferred_language"] = "zh"
    task["route_decision"] = {"interaction_mode": "chat", "reception_mode": "direct_question"}
    run = _build_run("help")
    execution_agent = _build_execution_agent("write")

    result = agent_execution_service.execute_task(task=task, run=run, execution_agent=execution_agent)

    assert result["kind"] == "chat_reply"
    assert "你是在问" in result["text"]
    assert "广州天气怎么样" in result["text"]
    assert "实时外部数据源" in result["text"] or "最快怎么查" in result["text"]
    assert "资料线索" not in result["text"]
    assert result["references"] == []


def test_agent_execution_profile_is_reflected_in_result(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_service = _fake_config_service(monkeypatch, status="loaded")

    task = _build_task(description="Search or write something about deployment.")
    run = _build_run("search")
    execution_agent = _build_execution_agent("search")

    result = agent_execution_service.execute_task(task=task, run=run, execution_agent=execution_agent)

    assert result["kind"] == "search_report"
    assert any("Execution profile" in bullet for bullet in result["bullets"])
    assert fake_service.load_agent_config(execution_agent)["agent"]["model"] in result["content"] or any(
        fake_service.load_agent_config(execution_agent)["agent"]["model"] in bullet for bullet in result["bullets"]
    )
    profile_trace = next(item for item in result["execution_trace"] if item["stage"] == "execution_profile")
    assert profile_trace["metadata"]["model"] == "gpt-4.1-mini"
    assert profile_trace["metadata"]["profile_status"] == "loaded"


def test_agent_execution_config_load_failure_fails_open(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        agent_execution_module,
        "agent_config_service",
        AgentConfigService(config_root="nonexistent"),
    )
    monkeypatch.setattr(
        agent_execution_module.agent_config_service,
        "load_agent_config",
        lambda agent: (_ for _ in ()).throw(RuntimeError("broken front matter")),
    )

    task = _build_task(description="Help me diagnose the WorkBot dispatcher.")
    run = _build_run("help")
    execution_agent = _build_execution_agent("write")

    result = agent_execution_service.execute_task(task=task, run=run, execution_agent=execution_agent)

    assert result["kind"] == "help_note"
    assert any("Execution profile:" in bullet for bullet in result["bullets"])
    assert any("Config note:" in bullet for bullet in result["bullets"])
    profile_trace = next(item for item in result["execution_trace"] if item["stage"] == "execution_profile")
    assert profile_trace["metadata"]["profile_status"] == "error"


def test_agent_execution_uses_enabled_openapi_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    _fake_config_service(monkeypatch, status="loaded")
    monkeypatch.setattr(
        agent_execution_module,
        "get_agent_api_runtime_settings",
        lambda: {
            "providers": {
                "openapi": {
                    "enabled": True,
                    "base_url": "https://relay.example.com/v1",
                    "model": "relay-model",
                    "organization_id": "",
                    "project_id": "",
                    "group_id": "",
                    "endpoint_path": "/responses",
                    "notes": "",
                    "api_key": "relay-key-123",
                }
            }
        },
    )

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "output_text": (
                    '{"title":"Relay Draft","summary":"Generated by relay",'
                    '"content":"This came from the real relay provider.",'
                    '"bullets":["b1","b2"]}'
                ),
                "output": [
                    {
                        "content": [
                            {
                                "type": "output_text",
                                "text": (
                                    '{"title":"Relay Draft","summary":"Generated by relay",'
                                    '"content":"This came from the real relay provider.",'
                                    '"bullets":["b1","b2"]}'
                                ),
                            }
                        ]
                    }
                ]
            }

    class FakeClient:
        def __init__(self, *, timeout: float, trust_env: bool) -> None:
            captured["timeout"] = timeout
            captured["trust_env"] = trust_env

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]) -> FakeResponse:
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(agent_execution_module.httpx, "Client", FakeClient)

    task = _build_task(description="Write a short status update.")
    run = _build_run("write")
    execution_agent = _build_execution_agent("write")

    result = agent_execution_service.execute_task(task=task, run=run, execution_agent=execution_agent)

    assert result["kind"] == "draft_message"
    assert result["title"] == "Relay Draft"
    assert result["content"] == "This came from the real relay provider."
    assert captured["url"] == "https://relay.example.com/v1/responses"
    assert captured["trust_env"] is False
    assert captured["headers"]["authorization"] == "Bearer relay-key-123"
    assert captured["json"]["model"] == "relay-model"
    assert captured["json"]["input"][0]["role"] == "system"
    assert captured["json"]["input"][1]["role"] == "user"


def test_agent_execution_falls_back_to_agent_profile_model_when_provider_model_is_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    _fake_config_service(monkeypatch, status="loaded")
    monkeypatch.setattr(
        agent_execution_module,
        "get_agent_api_runtime_settings",
        lambda: {
            "providers": {
                "openapi": {
                    "enabled": True,
                    "base_url": "https://relay.example.com/v1",
                    "model": "",
                    "organization_id": "",
                    "project_id": "",
                    "group_id": "",
                    "endpoint_path": "/responses",
                    "notes": "",
                    "api_key": "relay-key-123",
                }
            }
        },
    )

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "output_text": (
                    '{"title":"Relay Draft","summary":"Generated by relay",'
                    '"content":"This came from the real relay provider.",'
                    '"bullets":["b1","b2"]}'
                )
            }

    class FakeClient:
        def __init__(self, *, timeout: float, trust_env: bool) -> None:
            return None

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]) -> FakeResponse:
            captured["url"] = url
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(agent_execution_module.httpx, "Client", FakeClient)

    task = _build_task(description="Write a short status update.")
    run = _build_run("write")
    execution_agent = _build_execution_agent("write")

    result = agent_execution_service.execute_task(task=task, run=run, execution_agent=execution_agent)

    assert result["kind"] == "draft_message"
    assert captured["url"] == "https://relay.example.com/v1/responses"
    assert captured["json"]["model"] == "gpt-4.1-mini"


def test_agent_execution_prefers_agent_bound_model_over_provider_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        agent_execution_module,
        "get_agent_api_runtime_settings",
        lambda: {
            "providers": {
                "openai": {
                    "enabled": True,
                    "base_url": "https://api.openai.example/v1",
                    "model": "gpt-5.4",
                    "organization_id": "",
                    "project_id": "",
                    "group_id": "",
                    "endpoint_path": "/responses",
                    "notes": "",
                    "api_key": "relay-key-123",
                }
            }
        },
    )

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "output_text": (
                    '{"title":"Bound Draft","summary":"Generated by relay",'
                    '"content":"This came from the bound model.",'
                    '"bullets":["b1","b2"]}'
                )
            }

    class FakeClient:
        def __init__(self, *, timeout: float, trust_env: bool) -> None:
            return None

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]) -> FakeResponse:
            captured["url"] = url
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(agent_execution_module.httpx, "Client", FakeClient)

    task = _build_task(description="Write a short status update.")
    run = _build_run("write")
    execution_agent = _build_execution_agent("write")
    execution_agent["config_snapshot"] = {
        "status": "manual",
        "agent": {
            "model": "gpt-4.1-mini",
            "provider": "openai",
        },
        "runtime": {
            "agent_binding": {
                "provider_key": "openai",
                "model": "gpt-4.1-mini",
                "source": "manual",
            }
        },
    }

    result = agent_execution_service.execute_task(task=task, run=run, execution_agent=execution_agent)

    assert result["kind"] == "draft_message"
    assert captured["url"] == "https://api.openai.example/v1/responses"
    assert captured["json"]["model"] == "gpt-4.1-mini"


def test_agent_execution_falls_back_when_provider_request_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        agent_execution_module,
        "get_agent_api_runtime_settings",
        lambda: {
            "providers": {
                "openapi": {
                    "enabled": True,
                    "base_url": "https://relay.example.com/v1",
                    "model": "relay-model",
                    "organization_id": "",
                    "project_id": "",
                    "group_id": "",
                    "endpoint_path": "/responses",
                    "notes": "",
                    "api_key": "relay-key-123",
                }
            }
        },
    )

    class FailingClient:
        def __init__(self, *, timeout: float, trust_env: bool) -> None:
            return None

        def __enter__(self) -> "FailingClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]):
            raise RuntimeError("upstream unavailable")

    monkeypatch.setattr(agent_execution_module.httpx, "Client", FailingClient)

    task = _build_task(description="Write a short status update.")
    run = _build_run("write")
    execution_agent = _build_execution_agent("write")

    result = agent_execution_service.execute_task(task=task, run=run, execution_agent=execution_agent)

    assert result["kind"] == "draft_message"
    assert result["content"].startswith("Hello,")
