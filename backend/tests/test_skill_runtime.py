from __future__ import annotations

import time

from app.services.skill_registry_service import SkillRegistryService
from app.services.skill_runtime_service import SkillRuntimeService


def test_skill_registry_registers_and_queries_by_type_tag_source_capability() -> None:
    registry = SkillRegistryService()
    registry.register_many(
        [
            {
                "name": "alpha_skill",
                "type": "skill",
                "source": "internal",
                "tags": ["task", "status"],
                "capabilities": ["task_status", "task_query"],
                "handler": lambda payload: {"payload": payload},
            },
            {
                "name": "beta_tool",
                "type": "tool",
                "source": "local_tool",
                "tags": ["search"],
                "capabilities": ["web_search"],
                "handler": lambda payload: {"payload": payload},
            },
            {
                "name": "gamma_mcp",
                "type": "mcp",
                "source": "mcp_server",
                "tags": ["search", "external"],
                "capabilities": ["web_search", "fact_checking"],
                "handler": lambda payload: {"payload": payload},
            },
        ]
    )

    assert registry.get_ability("alpha_skill") is not None
    assert len(registry.list_abilities(ability_type="skill")) == 1
    assert len(registry.list_abilities(tag="search")) == 2
    assert len(registry.list_abilities(source="mcp_server")) == 1
    assert len(registry.list_abilities(capability="web_search")) == 2

    ranked = registry.query_by_capabilities(["web_search", "fact_checking"])
    assert [item["name"] for item in ranked] == ["gamma_mcp", "beta_tool"]


def test_skill_runtime_executes_skill_and_records_trace() -> None:
    registry = SkillRegistryService()
    runtime = SkillRuntimeService(registry=registry)
    registry.register_ability(
        {
            "name": "echo_skill",
            "type": "skill",
            "source": "internal",
            "tags": ["echo"],
            "capabilities": ["echo"],
            "handler": lambda payload, context, ability: {
                "summary": f"echoed {payload.get('text')}",
                "context_value": context.get("scope"),
                "ability": ability["name"],
            },
        }
    )

    result = runtime.execute("echo_skill", payload={"text": "hello"}, context={"scope": "unit"})

    assert result["ok"] is True
    assert result["ability_name"] == "echo_skill"
    assert result["ability_type"] == "skill"
    assert result["result"]["ability"] == "echo_skill"
    assert result["result"]["context_value"] == "unit"
    assert "echoed hello" in result["result_summary"]
    assert result["trace_id"].startswith("trace_")

    traces = runtime.list_traces(limit=5)
    assert len(traces) == 1
    assert traces[0]["status"] == "success"
    assert traces[0]["trace_id"] == result["trace_id"]


def test_skill_runtime_supports_tool_and_mcp_abstractions() -> None:
    registry = SkillRegistryService()
    runtime = SkillRuntimeService(registry=registry)
    registry.register_many(
        [
            {
                "name": "local_tool_ping",
                "type": "tool",
                "source": "local_tool",
                "handler": lambda payload: {"summary": "tool ok", "payload": payload},
            },
            {
                "name": "external_mcp_ping",
                "type": "mcp",
                "source": "mcp_server",
                "handler": lambda payload: {"summary": "mcp ok", "payload": payload},
            },
        ]
    )

    tool_result = runtime.execute("local_tool_ping", payload={"value": 1})
    mcp_result = runtime.execute("external_mcp_ping", payload={"value": 2})

    assert tool_result["ok"] is True
    assert tool_result["ability_type"] == "tool"
    assert mcp_result["ok"] is True
    assert mcp_result["ability_type"] == "mcp"
    assert len(runtime.list_traces(limit=10)) == 2


def test_skill_runtime_returns_unified_not_found_error() -> None:
    runtime = SkillRuntimeService(registry=SkillRegistryService())

    result = runtime.execute("missing_skill")

    assert result["ok"] is False
    assert result["error"]["code"] == "ability_not_found"
    assert result["ability_name"] == "missing_skill"
    traces = runtime.list_traces(limit=1)
    assert traces[0]["status"] == "failed"
    assert traces[0]["error"]["code"] == "ability_not_found"


def test_skill_runtime_returns_timeout_error() -> None:
    registry = SkillRegistryService()
    runtime = SkillRuntimeService(registry=registry)

    def slow_handler(payload):
        time.sleep(0.15)
        return {"summary": "slow finished"}

    registry.register_ability(
        {
            "name": "slow_skill",
            "type": "skill",
            "source": "internal",
            "timeout_seconds": 1.0,
            "handler": slow_handler,
        }
    )

    result = runtime.execute("slow_skill", timeout_seconds=0.02)

    assert result["ok"] is False
    assert result["error"]["code"] == "runtime_timeout"
    assert result["meta"]["timeout_seconds"] == 0.02


def test_skill_runtime_returns_execution_error_for_exceptions() -> None:
    registry = SkillRegistryService()
    runtime = SkillRuntimeService(registry=registry)

    def broken_handler(payload):
        raise RuntimeError("boom")

    registry.register_ability(
        {
            "name": "broken_skill",
            "type": "skill",
            "source": "internal",
            "handler": broken_handler,
        }
    )

    result = runtime.execute("broken_skill")

    assert result["ok"] is False
    assert result["error"]["code"] == "runtime_execution_error"
    assert result["error"]["message"] == "boom"
    assert result["error"]["detail"]["exception_type"] == "RuntimeError"

